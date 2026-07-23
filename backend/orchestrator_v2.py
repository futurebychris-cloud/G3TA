"""Orchestrator v2 — SERIAL pipeline with agent-to-agent data handoffs.

Pipeline: Budget → Transportation → Activity → Food → Housing (parallel) → Planning → Synthesis
"""
from __future__ import annotations
import hashlib, json
from concurrent.futures import ThreadPoolExecutor

from llm.deepseek_client import chat_json
from booking.shared_db import init_shared_db, save_trip

_AGENTS = {}
def _load():
    global _AGENTS
    if _AGENTS: return
    from agents import activity_agent, budget_agent, food_agent, housing_agent, planning_agent, transportation_agent
    _AGENTS = {k: v.run for k, v in [("budget", budget_agent), ("transportation", transportation_agent),
        ("activity", activity_agent), ("food", food_agent), ("housing", housing_agent), ("planning", planning_agent)]}

SYNTHESIS_PROMPT = (
    "You are the Orchestrator of a multi-agent trip planner. Produce a day-by-day itinerary. "
    "Use ONLY supplied lodging, meals, transport, activities. Never invent places from another city. "
    "Return ONLY JSON: {summary, schedule: [{day, date, title, items: [{time, type (arrival|departure|lodging|meal|activity), title, detail}]}]}"
)

def with_budget_guidance(ti: dict, bo: dict) -> dict:
    g = dict(ti)
    dc = bo.get("daily_caps", {})
    if "neural_allocation" in bo: dc = bo["neural_allocation"].get("daily_caps", dc)
    g["_budget_caps"] = dc; g["_budget_ratios"] = bo.get("ratios", {}); g["_cost_index"] = bo.get("cost_index", {})
    g["_budget_allocations"] = bo.get("allocations", {})
    return g

LEGACY_TY = {"tokyo","asakusa","shibuya","ginza","shinjuku","akihabara","senso-ji","nrt","haneda","mt. fuji","hakone"}
def _geoguard(ti, outputs):
    d = ti["location"].strip()
    for a, o in outputs.items():
        od = str(o.get("destination", d)).strip()
        if od.casefold() != d.casefold():
            raise ValueError(f"{a.title()} Agent returned data for '{od}' instead of '{d}'.")
    if "tokyo" not in d.casefold() and "japan" not in d.casefold():
        if any(m in json.dumps(outputs, ensure_ascii=False).casefold() for m in LEGACY_TY):
            raise ValueError(f"Geography guard rejected stale Tokyo data for {d} trip.")

from agents.base import trip_days as _td
def _reconcile(ti, outputs, log):
    nd = len(_td(ti)); tb = float(ti["budget"]["total"]); cy = ti["budget"].get("currency","CNY")
    ta = outputs.get("transportation",{})
    tc = float(ta.get("cost",0) or 0); tr = ta.get("recommended",{})
    if tc<=0:
        o=ti.get("origin",""); d=ti["location"]
        if o and d:
            try:
                from services.gaode_service import city_distance_km, CITY_COST_KM
                tc=round(city_distance_km(o,d)*CITY_COST_KM,2)
            except: tc=600.0
    lt = float(ta.get("local_transport_cost",0) or 0)
    if lt<=0: lt=round(30.0*nd,2)
    ha=outputs.get("housing",{}); hc=ha.get("cost"); hr=ha.get("recommended",{}) or {}
    ni=max(nd-1,1); MR=100000
    pp=hr.get("price_per_night") if isinstance(hr,dict) else None
    if pp and float(pp)>MR:
        opts=[o for o in ha.get("options",[]) or [] if o.get("price_per_night") and 0<float(o["price_per_night"])<MR]
        if opts: hr=min(opts,key=lambda o:o["price_per_night"]); ha["recommended"]=hr
    if hc is None or (isinstance(hc,(int,float)) and hc>MR*ni):
        hc=float(hr.get("price_per_night",0))*ni if hr.get("price_per_night") else 0.0
    hc=float(hc)
    fc=float(outputs.get("food",{}).get("cost",0) or 0)
    ac=float(outputs.get("activity",{}).get("cost",0) or 0)
    sc=0.0
    bci=outputs.get("budget",{}).get("cost_index",{})
    sdi=bci.get("daily_index",{}) if bci else {}
    sd=float(sdi.get("shopping",0) or 0)
    sc=round(sd*nd,2) if sd>0 else round(max(tb-tc,0)/max(nd,1)*0.10*nd,2)
    ei=[]
    if tc>0: ei.append({"category":"transportation","label":"Intercity transport","amount":round(tc,2),"currency":cy,
        "detail":f"{tr.get('carrier','')} {tr.get('flight_number',tr.get('train_number',''))} {tr.get('from','')} → {tr.get('to','')}"})
    if hc>0: ei.append({"category":"housing","label":"Accommodation","amount":round(hc,2),"currency":cy,
        "detail":f"{hr.get('name','Hotel')} × {ni} nights"})
    if fc>0: ei.append({"category":"food","label":"Food & dining","amount":round(fc,2),"currency":cy,"detail":f"{nd} days of meals"})
    if ac>0:
        ar=outputs.get("activity",{}).get("recommended",[])
        an=", ".join(a.get("name","") for a in (ar or [])[:3])
        ei.append({"category":"activity","label":"Activities","amount":round(ac,2),"currency":cy,"detail":an or f"{len(ar or [])} activities"})
    if lt>0: ei.append({"category":"local_transport","label":"Local transport","amount":round(lt,2),"currency":cy,"detail":f"{nd} days"})
    if sc>0: ei.append({"category":"shopping","label":"Shopping","amount":round(sc,2),"currency":cy,"detail":f"{nd} days"})
    gt=tc+hc+fc+ac+lt+sc
    if gt>tb: log.append({"agent":"Orchestrator","note":f"Plan costs {cy} {gt:,.0f}, over budget {gt-tb:,.0f}."})
    return {"currency":cy,"total":round(gt,2),"budget":tb,"within_budget":gt<=tb,
        "breakdown":{"transportation":round(tc,2),"housing":round(hc,2),"food":round(fc,2),"activity":round(ac,2),
                      "local_transport":round(lt,2),"shopping":round(sc,2)},
        "pie_data":outputs.get("budget",{}).get("pie_data",[]),
        "allocations":outputs.get("budget",{}).get("allocations",{}),"expense_items":ei}

def _map_pts(outputs, dest=""):
    pts=[]; city=dest or outputs.get("activity",{}).get("destination",""); cc=None
    if city:
        try:
            from services.gaode_service import geocode_city; cc=geocode_city(city)
        except: pass
    h=outputs.get("housing",{}).get("recommended",{})
    if h and h.get("name"):
        if not(h.get("lat") and h.get("lng")):
            try:
                from services.gaode_service import geocode_poi; co=geocode_poi(h.get("name",""),city)
                if co: h["lat"],h["lng"]=co
                elif cc: h["lat"],h["lng"]=cc
            except:
                if cc: h["lat"],h["lng"]=cc
        if h.get("lat") and h.get("lng"):
            pts.append({"label":h["name"],"type":"housing","area":h.get("area",city),"lat":h["lat"],"lng":h["lng"],
                "image":(h.get("images",[]) or [None])[0],"description":h.get("description",""),"star_rating":h.get("star_rating"),"url":h.get("url","")})
    acts=outputs.get("activity",{}).get("recommended",[])
    if acts:
        try:
            from services.gaode_service import geocode_activities; geocode_activities(acts,city)
        except: pass
    for a in acts or []:
        if not(a.get("lat") and a.get("lng")):
            if cc: a["lat"],a["lng"]=cc
            else: continue
        pts.append({"label":a["name"],"type":"activity","area":a.get("area",a.get("location",city)),
            "lat":a["lat"],"lng":a["lng"],"image":(a.get("images",[]) or [a.get("image_url")])[0],
            "description":a.get("description",""),"ticket_price":a.get("ticket_price"),"url":a.get("url","")})
    tr=outputs.get("transportation",{}).get("recommended",{})
    if tr:
        for ln in [tr.get("from",""),tr.get("to","")]:
            if not ln: continue
            try:
                from services.gaode_service import geocode_city; co=geocode_city(ln)
                if co: pts.append({"label":f"{ln} (Station/Airport)","type":"transport","area":ln,"lat":co[0],"lng":co[1],
                    "description":f"{tr.get('carrier','')} {tr.get('flight_number',tr.get('train_number',''))}","url":""})
            except: pass

    # ---- NEW: Restaurant markers from Food Agent output ----
    food_daily = outputs.get("food", {}).get("daily_meals", [])
    seen_restaurants = set()
    for day_plan in food_daily:
        for meal in day_plan.get("meals", []):
            rname = meal.get("restaurant", "")
            if not rname or rname in seen_restaurants:
                continue
            seen_restaurants.add(rname)

            # Use coordinates from food agent if available
            rlat = meal.get("lat")
            rlng = meal.get("lng")

            # Geocode if coordinates not available
            if not (rlat and rlng):
                try:
                    from services.gaode_service import geocode_poi
                    co = geocode_poi(rname, city)
                    if co:
                        rlat, rlng = co
                except Exception:
                    pass

            # Fall back to city center
            if not (rlat and rlng) and cc:
                rlat, rlng = cc

            if rlat and rlng:
                pts.append({
                    "label": rname,
                    "type": "restaurant",
                    "area": meal.get("area", city),
                    "lat": rlat,
                    "lng": rlng,
                    "description": f"{meal.get('cuisine', '')} · {meal.get('name', '')} · ¥{meal.get('price', 0)}",
                    "rating": meal.get("rating", 0),
                    "cuisine": meal.get("cuisine", ""),
                    "dish": meal.get("name", ""),
                    "price": meal.get("price", 0),
                    "source": meal.get("source", ""),
                })

    if len(pts)==0 and cc: pts.append({"label":city,"type":"activity","area":city,"lat":cc[0],"lng":cc[1],"description":"City center"})
    return pts

def _mt(m): return m.get("restaurant",m.get("name",""))
def _md(m): return f"{m.get('cuisine','')} {m.get('dish_category','') or m.get('name','')}".strip()
def _fs(ti, outputs):
    days=_td(ti); acts=outputs.get("activity",{}).get("recommended",[])
    mbd={d["date"]:d for d in outputs.get("food",{}).get("daily_meals",[])}
    h=outputs.get("housing",{}).get("recommended",{}); t=outputs.get("transportation",{}).get("recommended",{}) or {}
    sched=[]
    for i,date in enumerate(days):
        items=[]
        if i==0:
            c=t.get("carrier","Flight"); fl=t.get("from",ti.get("origin",""))
            hn=h.get("name","your hotel") if h else "your hotel"
            items.append({"time":"Morning","type":"arrival","title":f"Arrive via {c}",
                "detail":f"{f'From {fl}. ' if fl else ''}Check in at {hn}."})
        dm=mbd.get(date,{}).get("meals",[]); act=acts[i] if i<len(acts) else None
        if dm: items.append({"time":"08:30","type":"meal","title":_mt(dm[0]),"detail":_md(dm[0])})
        if act: items.append({"time":"10:30","type":"activity","title":act["name"],
            "detail":f"{act.get('style',act.get('type',''))} · {act.get('duration','')} · {act.get('area',act.get('location',''))}".strip(" ·")})
        if len(dm)>1: items.append({"time":"13:00","type":"meal","title":_mt(dm[1]),"detail":_md(dm[1])})
        if len(dm)>2: items.append({"time":"19:00","type":"meal","title":_mt(dm[2]),"detail":_md(dm[2])})
        if i==len(days)-1: items.append({"time":"Evening","type":"departure","title":f"Depart via {c}","detail":"Head to airport for return."})
        sched.append({"day":i+1,"date":date,"title":act["name"] if act else "Explore","items":items})
    return {"summary":f"A {len(days)}-day trip to {ti['location']} staying at {hn}, "
        f"balancing {outputs.get('planning',{}).get('weather_summary','seasonal weather')}.","schedule":sched}

def _vs(ti, synth, outputs):
    if not isinstance(synth,dict) or not isinstance(synth.get("schedule"),list): return False
    days=_td(ti); s=synth["schedule"]
    if len(s)!=len(days) or [d.get("date") for d in s]!=days: return False
    aa={a["name"].strip().casefold() for a in outputs.get("activity",{}).get("recommended",[])}
    am={_mt(m).strip().casefold() for dl in outputs.get("food",{}).get("daily_meals",[]) for m in dl["meals"]}
    at=[]
    for day in s:
        if not isinstance(day.get("items"),list): return False
        for it in day["items"]:
            if it.get("type")=="activity":
                t=str(it.get("title","")).strip().casefold()
                if not t or t not in aa: return False
                at.append(t)
            if it.get("type")=="meal":
                t=str(it.get("title","")).strip().casefold()
                if not t or t not in am: return False
    return len(at)==min(len(days),len(aa)) and len(at)==len(set(at))

def reconcile_and_synthesize(ti, outputs):
    _geoguard(ti, outputs)
    rl=[]
    lb={"budget":"Budget","transportation":"Transportation","housing":"Housing","food":"Food","activity":"Activity","planning":"Planning"}
    for k,n in lb.items():
        note=outputs.get(k,{}).get("reasoning")
        if note: rl.append({"agent":n,"note":note})
    for w in outputs.get("budget",{}).get("warnings",[]): rl.append({"agent":"Budget","note":f"⚠ {w}"})
    cost=_reconcile(ti,outputs,rl)
    br={}
    for an in ["transportation","food","housing"]:
        ao=outputs.get(an,{})
        if ao.get("booking_result"): br[an]=ao["booking_result"]
    synth=None
    try:
        p={"destination":ti["location"],"strict_destination_rule":f"Every place must be in {ti['location']}.",
           "dates":ti["dates"],"arrival":outputs.get("transportation",{}).get("recommended",{}),
           "lodging":outputs.get("housing",{}).get("recommended",{}),
           "daily_meals":outputs.get("food",{}).get("daily_meals",[]),
           "activities":outputs.get("activity",{}).get("recommended",[]),
           "daily_weather":outputs.get("planning",{}).get("daily_weather",[]),
           "pacing_notes":outputs.get("planning",{}).get("pacing_notes","")}
        synth=chat_json(SYNTHESIS_PROMPT,json.dumps(p,ensure_ascii=False),temperature=0.5)
        if not _vs(ti,synth,outputs): synth=None
    except: synth=None
    if synth is None: synth=_fs(ti,outputs)
    return {"destination":ti["location"],"dates":ti["dates"],"summary":synth.get("summary",""),
        "schedule":synth["schedule"],"cost":cost,"map_points":_map_pts(outputs,ti["location"]),
        "packing_list":outputs.get("planning",{}).get("packing_list",[]),
        "weather_summary":outputs.get("planning",{}).get("weather_summary",""),
        "reasoning_log":rl,"agent_outputs":outputs,"booking_results":br,
        "transport_scrape_status":outputs.get("transportation",{}).get("scrape_status","ok"),
        "transport_errors":outputs.get("transportation",{}).get("errors",[]),
        # NEW: Food agent frontend data
        "popularity_cost_table":outputs.get("food",{}).get("popularity_cost_table",[]),
        "pending_meal_confirmations":outputs.get("food",{}).get("pending_confirmation",[]),
        # NEW: Planning agent hotel amenities
        "hotel_amenities":outputs.get("planning",{}).get("hotel_amenities"),
        "shopping_budget":outputs.get("planning",{}).get("shopping_budget",0),
    }

def plan(ti):
    """SERIAL pipeline: Budget→Transport→Activity→Food+Housing→Planning→Synthesis"""
    _load()
    init_shared_db()
    tid=hashlib.sha256(f"{ti['location']}{ti['dates']['start']}{ti.get('origin','')}".encode()).hexdigest()[:12]
    ti["trip_id"]=tid
    save_trip(trip_id=tid,location=ti["location"],origin=ti.get("origin",""),start_date=ti["dates"]["start"],
              end_date=ti["dates"]["end"],total_budget=float(ti["budget"]["total"]),currency=ti["budget"].get("currency","CNY"))
    outputs={}
    # Step 1: Budget
    print("[ov2] 1/6 Budget Agent"); outputs["budget"]=_AGENTS["budget"](ti)
    gi=with_budget_guidance(ti,outputs["budget"])
    # Step 2: Transportation
    print("[ov2] 2/6 Transportation Agent"); outputs["transportation"]=_AGENTS["transportation"](gi)
    # Step 3: Activity
    print("[ov2] 3/6 Activity Agent"); outputs["activity"]=_AGENTS["activity"](gi)
    # Inject meal slots for Food Agent
    ams={}
    for a in outputs["activity"].get("recommended",[]):
        if a.get("meal_slot"):
            d=a.get("date",""); ams.setdefault(d,[]).append({"activity_name":a["name"],"meal_slot":a["meal_slot"],
                "start_time":a.get("start_time",""),"end_time":a.get("end_time",""),"location":a.get("location",outputs["activity"].get("destination",""))})
    gi["_activity_meal_slots"]=ams
    # Step 4: Food + Housing (parallel)
    print("[ov2] 4/6 Food+Housing (parallel)")
    with ThreadPoolExecutor(max_workers=2) as ex:
        ff=ex.submit(_AGENTS["food"],gi); hf=ex.submit(_AGENTS["housing"],gi)
        outputs["food"]=ff.result(); outputs["housing"]=hf.result()
    
    # NEW: Inject housing + activity data into trip input for Planning Agent
    housing_rec = outputs["housing"].get("recommended", {}) or {}
    if housing_rec.get("name"):
        gi["_hotel_name"] = housing_rec["name"]
    gi["_housing_data"] = housing_rec
    
    # Inject activity outputs for Planning Agent gear recommendations
    gi["_activity_outputs"] = outputs["activity"].get("recommended", [])
    
    # Inject shopping budget for Planning Agent
    budget_alloc = outputs["budget"].get("allocations", {})
    if "shopping" in budget_alloc:
        gi["_budget_allocations"]["shopping"] = budget_alloc["shopping"]
    elif "other" in budget_alloc:
        gi["_budget_allocations"]["shopping"] = budget_alloc["other"]
    
    # Step 5: Planning
    print("[ov2] 5/6 Planning Agent"); outputs["planning"]=_AGENTS["planning"](gi)
    # Step 6: Synthesize
    print("[ov2] 6/6 Synthesis"); r=reconcile_and_synthesize(ti,outputs); r["trip_id"]=tid
    r["pipeline_version"]="v2_serial"; r["confirmation_required"]=True
    r["confirmation_message"]="以上行程由 AI 自动规划，所有价格来自携程/12306/高德实时数据。请确认每项安排。"
    return r
