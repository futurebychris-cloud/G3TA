"""12306 Train Query Service — REAL railway schedule & pricing from 12306.cn.

Uses the *public* query API which does NOT require login:
    GET https://kyfw.12306.cn/otn/leftTicket/query?...

This is the same API that powers 12306's web search page. It returns real-time
train schedules, seat availability, and ticket prices for all Chinese railway routes.

No API key needed — 12306's query endpoint is openly accessible (only booking
requires authentication).

Usage:
    from services.train12306_service import search_trains
    trains = search_trains("北京", "上海", "2026-08-05")
    # Returns list of {train_no, type, departure, arrival, duration,
    #                   price_second, price_first, price_business, seats_left}
"""
from __future__ import annotations

import json
import re
import ssl
import urllib.parse
import urllib.request
from datetime import date as _date

# ---------------------------------------------------------------------------
# 12306 Station Name → Code mapping (major stations)
# ---------------------------------------------------------------------------
STATION_CODES: dict[str, str] = {
    # 直辖市 / 省会
    "北京": "BJP", "beijing": "BJP",
    "上海": "SHH", "shanghai": "SHH",
    "广州": "GZQ", "guangzhou": "GZQ",
    "深圳": "SZQ", "shenzhen": "SZQ",
    "杭州": "HZH", "hangzhou": "HZH",
    "成都": "CDW", "chengdu": "CDW",
    "重庆": "CQW", "chongqing": "CQW",
    "西安": "XAY", "xian": "XAY", "xi'an": "XAY",
    "南京": "NJH", "nanjing": "NJH",
    "武汉": "WHN", "wuhan": "WHN",
    "厦门": "XMS", "xiamen": "XMS",
    "昆明": "KMM", "kunming": "KMM",
    "青岛": "QDK", "qingdao": "QDK",
    "大连": "DLT", "dalian": "DLT",
    "苏州": "SZH", "suzhou": "SZH",
    "三亚": "SEQ", "sanya": "SEQ",
    "天津": "TJP", "tianjin": "TJP",
    "长沙": "CSQ", "changsha": "CSQ",
    "郑州": "ZZF", "zhengzhou": "ZZF",
    "济南": "JNK", "jinan": "JNK",
    "福州": "FZS", "fuzhou": "FZS",
    "合肥": "HFH", "hefei": "HFH",
    "南昌": "NCG", "nanchang": "NCG",
    "南宁": "NNZ", "nanning": "NNZ",
    "贵阳": "GIW", "guiyang": "GIW",
    "兰州": "LZJ", "lanzhou": "LZJ",
    "西宁": "XNO", "xining": "XNO",
    "银川": "YIJ", "yinchuan": "YIJ",
    "呼和浩特": "HHC", "hohhot": "HHC",
    "乌鲁木齐": "WMR", "urumqi": "WMR",
    "拉萨": "LSO", "lhasa": "LSO",
    "哈尔滨": "HBB", "harbin": "HBB",
    "长春": "CCT", "changchun": "CCT",
    "沈阳": "SYT", "shenyang": "SYT",
    "石家庄": "SJP", "shijiazhuang": "SJP",
    "太原": "TYV", "taiyuan": "TYV",
    # 热门旅游 / 地级市
    "桂林": "GLZ", "guilin": "GLZ",
    "丽江": "LHM", "lijiang": "LHM",
    "大理": "DKM", "dali": "DKM",
    "黄山": "HKH", "huangshan": "HKH",
    "张家界": "DIQ", "zhangjiajie": "DIQ",
    "洛阳": "LYF", "luoyang": "LYF",
    "开封": "KFF", "kaifeng": "KFF",
    "宁波": "NGH", "ningbo": "NGH",
    "无锡": "WXH", "wuxi": "WXH",
    "常州": "CZH", "changzhou": "CZH",
    "温州": "RZH", "wenzhou": "RZH",
    "珠海": "ZIQ", "zhuhai": "ZIQ",
    "佛山": "FSQ", "foshan": "FSQ",
    "东莞": "RTQ", "dongguan": "RTQ",
    "徐州": "XCH", "xuzhou": "XCH",
    "烟台": "YAK", "yantai": "YAK",
    "威海": "WKK", "weihai": "WKK",
    "宜昌": "YCN", "yichang": "YCN",
    "襄阳": "XFN", "xiangyang": "XFN",
    "海口": "VUQ", "haikou": "VUQ",
    "北海": "BHZ", "beihai": "BHZ",
}

# Train type classification by prefix
TRAIN_TYPES = {
    "G": "高铁 (High-speed)", "D": "动车 (EMU)",
    "C": "城际 (Intercity)", "Z": "直达 (Express)",
    "T": "特快 (Express)", "K": "快速 (Fast)",
    "Y": "旅游 (Tourist)", "S": "市郊 (Suburban)",
    "L": "临客 (Temporary)",
}

# Price-per-km estimates by train type (CNY), used ONLY as last-resort fallback
# G-train ≈ 0.46/km, D-train ≈ 0.31/km, K ≈ 0.15/km, etc.
PRICE_PER_KM = {"G": 0.46, "D": 0.31, "C": 0.35, "Z": 0.20, "T": 0.18, "K": 0.15}

# 12306 seat type codes → human-readable names
SEAT_TYPE_MAP: dict[str, str] = {
    "O": "二等座", "M": "一等座", "9": "商务座", "P": "特等座",
    "6": "高级软卧", "4": "软卧", "3": "硬卧", "2": "软座", "1": "硬座",
}

# Seat type codes to query (by train type prefix)
# G/D trains have second/first/business; K/T/Z trains have hard/soft sleepers
SEAT_CODES_BY_TYPE: dict[str, list[str]] = {
    "G": ["O", "M", "9"],  # 二等座, 一等座, 商务座
    "D": ["O", "M", "9", "P"],
    "C": ["O", "M", "P"],
    "Z": ["4", "3", "2", "1"],  # 软卧, 硬卧, 软座, 硬座
    "T": ["4", "3", "2", "1"],
    "K": ["4", "3", "2", "1"],
}

# Approximate distances between major city pairs (km)
_DISTANCES: dict[tuple[str, str], int] = {
    ("BJP", "SHH"): 1318, ("BJP", "GZQ"): 2298, ("BJP", "XAY"): 1216,
    ("BJP", "NJH"): 1023, ("BJP", "WHN"): 1229, ("BJP", "CDW"): 1874,
    ("BJP", "HZH"): 1478, ("BJP", "TJP"): 137,  ("SHH", "GZQ"): 1790,
    ("SHH", "NJH"): 301,  ("SHH", "HZH"): 169,  ("SHH", "XAY"): 1509,
    ("SHH", "CDW"): 2001, ("SHH", "WHN"): 811,  ("SHH", "CSQ"): 1080,
    ("GZQ", "SZQ"): 147,  ("GZQ", "CSQ"): 707,  ("GZQ", "WHN"): 1069,
    ("GZQ", "XAY"): 2116, ("GZQ", "CDW"): 1590, ("GZQ", "HZH"): 1602,
    ("CDW", "CQW"): 308,  ("CDW", "XAY"): 842,  ("CDW", "KMM"): 1100,
    ("HZH", "NJH"): 256,  ("HZH", "SZH"): 150,  ("HZH", "WHN"): 750,
    ("XAY", "WHN"): 1045, ("XAY", "NJH"): 1206, ("XAY", "CQW"): 740,
    ("NJH", "WHN"): 517,  ("NJH", "TJP"): 1022, ("NJH", "CSQ"): 830,
    ("WHN", "CSQ"): 362,  ("WHN", "CQW"): 880,  ("WHN", "ZZF"): 536,
    ("XMS", "SZQ"): 510,  ("XMS", "FZS"): 276,  ("QDK", "JNK"): 393,
    ("DLT", "SYT"): 397,  ("SZH", "SHH"): 84,   ("KMM", "GIW"): 638,
}


def _station_distance(code_a: str, code_b: str) -> int:
    """Get approximate railway distance between two station codes."""
    pair = (code_a, code_b)
    rev = (code_b, code_a)
    return _DISTANCES.get(pair) or _DISTANCES.get(rev) or 500


def _query_ticket_price(
    internal_train_no: str,
    from_station_no: str,
    to_station_no: str,
    seat_types: list[str],
    train_date: str,
) -> dict[str, float]:
    """Query REAL ticket prices from 12306's price API.

    12306 has a separate public endpoint for querying ticket prices:
        GET https://kyfw.12306.cn/otn/leftTicket/queryTicketPrice

    This endpoint does NOT require login — it returns real-time prices
    for any route within the 15-day booking window.

    Args:
        internal_train_no: Internal train number (field[2] from leftTicket query),
                          NOT the display code like G102
        from_station_no: Station sequence number (field[16] from query)
        to_station_no: Station sequence number (field[17] from query)
        seat_types: List of seat type codes, e.g. ["O", "M", "9"]
        train_date: Date in YYYY-MM-DD format

    Returns:
        Dict mapping seat type codes to prices, e.g. {"O": 553.0, "M": 933.0, "9": 1874.0}
    """
    if not seat_types:
        return {}

    seat_str = ",".join(seat_types)
    url = (
        "https://kyfw.12306.cn/otn/leftTicket/queryTicketPrice?"
        + urllib.parse.urlencode({
            "train_no": internal_train_no,
            "from_station_no": from_station_no,
            "to_station_no": to_station_no,
            "seat_types": seat_str,
            "train_date": train_date,
        })
    )

    try:
        opener = _get_12306_opener()
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0",
            "Referer": "https://kyfw.12306.cn/otn/leftTicket/init",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Cache-Control": "no-cache",
            "X-Requested-With": "XMLHttpRequest",
        })
        with opener.open(req, timeout=10) as r:
            raw = r.read()
            data = json.loads(raw.decode("utf-8-sig") if raw.startswith(b'\xef\xbb\xbf') else raw.decode("utf-8"))

        if not data.get("status") and data.get("httpstatus") != 200:
            print(f"[12306] price API error: {data.get('messages', 'unknown')}")
            return {}

        price_data = data.get("data", {})
        prices: dict[str, float] = {}

        # Price data structure: { "O": "¥553.0", "M": "¥933.0", ... }
        for seat_code, price_str in price_data.items():
            if seat_code in SEAT_TYPE_MAP:
                try:
                    # Strip ¥ prefix and convert to float
                    clean = str(price_str).replace("¥", "").replace(",", "").strip()
                    if clean and clean != "--" and clean != "*":
                        prices[seat_code] = float(clean)
                except (ValueError, AttributeError):
                    pass

        if prices:
            print(f"[12306] real prices for {internal_train_no}: "
                  f"{', '.join(f'{SEAT_TYPE_MAP.get(k,k)}:¥{v:.0f}' for k,v in prices.items())}")
        else:
            print(f"[12306] no prices returned for {internal_train_no} (may be outside booking window)")

        return prices

    except urllib.error.HTTPError as e:
        print(f"[12306] price query HTTP {e.code}: {e.reason}")
        return {}
    except Exception as e:
        print(f"[12306] price query failed: {e}")
        return {}


# ---------------------------------------------------------------------------
# Public 12306 Query API
# ---------------------------------------------------------------------------

def _get_12306_station_name_map() -> dict[str, str]:
    """Fetch the official station name→code mapping from 12306 (cached in memory)."""
    if hasattr(_get_12306_station_name_map, "_cache"):
        return getattr(_get_12306_station_name_map, "_cache")  # type: ignore[no-any-return]

    url = "https://kyfw.12306.cn/otn/resources/js/framework/station_name.js?station_version=1.9360"
    try:
        opener = _get_12306_opener()
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0",
            "Referer": "https://kyfw.12306.cn/otn/leftTicket/init",
        })
        with opener.open(req, timeout=10) as r:
            raw = r.read()
            text = raw.decode("utf-8-sig") if raw.startswith(b'\xef\xbb\xbf') else raw.decode("utf-8")
        # Parse: var station_names ='@bjb|北京北|VAP|beijingbei|bjb|0|...'
        m = re.search(r"station_names\s*=\s*'([^']+)'", text)
        if m:
            stations: dict[str, str] = {}
            for entry in m.group(1).split("@"):
                if not entry:
                    continue
                parts = entry.split("|")
                if len(parts) >= 3:
                    name = parts[1]  # Chinese name
                    code = parts[2]  # Station code
                    stations[name] = code
            setattr(_get_12306_station_name_map, "_cache", stations)
            return stations
    except Exception as e:
        print(f"[12306] station name map fetch failed: {e}")

    setattr(_get_12306_station_name_map, "_cache", {})
    return {}


_12306_OPENER: urllib.request.OpenerDirector | None = None


def _get_12306_opener() -> urllib.request.OpenerDirector:
    """Create or reuse an opener with 12306 session cookies.
    12306 now requires session cookies (JSESSIONID, route, BIGipServerotn)
    obtained by visiting the main page before querying the API."""
    global _12306_OPENER
    if _12306_OPENER is not None:
        return _12306_OPENER

    import http.cookiejar
    ctx = ssl.create_default_context()
    https_handler = urllib.request.HTTPSHandler(context=ctx)
    cj = http.cookiejar.CookieJar()
    cookie_handler = urllib.request.HTTPCookieProcessor(cj)
    _12306_OPENER = urllib.request.build_opener(https_handler, cookie_handler)

    # Visit the main page to get session cookies
    try:
        req = urllib.request.Request(
            "https://kyfw.12306.cn/otn/leftTicket/init",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0"},
        )
        with _12306_OPENER.open(req, timeout=15) as r:
            _ = r.read()
        print(f"[12306] session cookies acquired: {[c.name for c in cj]}")
    except Exception as e:
        print(f"[12306] session init failed (non-fatal): {e}")

    return _12306_OPENER


def resolve_station_code(city: str) -> str | None:
    """Resolve a city name to a 12306 station code.

    Tries: built-in mapping → online station list → fuzzy match.
    """
    key = city.strip().lower()
    if key in STATION_CODES:
        return STATION_CODES[key]

    # Check Chinese name in built-in mapping
    for name, code in STATION_CODES.items():
        if name == city.strip():
            return code

    # Try online station name map
    online = _get_12306_station_name_map()
    if city.strip() in online:
        return online[city.strip()]

    # Fuzzy match: find station names that start with city name
    for name, code in online.items():
        if name.startswith(city.strip()):
            print(f"[12306] fuzzy match: '{city}' → '{name}' ({code})")
            return code

    # Last resort: direct lookup by first 2 chars
    for name, code in online.items():
        if city.strip()[:2] in name:
            print(f"[12306] partial match: '{city}' → '{name}' ({code})")
            return code

    return None


def search_trains(origin: str, destination: str, date_str: str) -> list[dict]:
    """Search real-time trains on 12306.

    Args:
        origin: City name (e.g. "北京", "Shanghai")
        destination: City name
        date_str: Date in YYYY-MM-DD format

    Returns:
        List of train dicts: {train_no, type, departure_time, arrival_time,
                              duration, price_second, price_first, price_business,
                              from_station, to_station, seats_left, source}
    """
    from_code = resolve_station_code(origin)
    to_code = resolve_station_code(destination)

    if not from_code:
        print(f"[12306] could not resolve station code for '{origin}'")
        return []
    if not to_code:
        print(f"[12306] could not resolve station code for '{destination}'")
        return []

    # Validate date — 12306 only allows ~15 days in advance
    try:
        trip_date = _date.fromisoformat(date_str)
        today = _date.today()
        if trip_date < today:
            print(f"[12306] date {date_str} is in the past, skipping")
            return []
        days_ahead = (trip_date - today).days
        if days_ahead > 14:
            print(f"[12306] date {date_str} is {days_ahead}d ahead (>14d limit), skipping")
            return []
    except Exception:
        pass

    url = (
        "https://kyfw.12306.cn/otn/leftTicket/query?"
        + urllib.parse.urlencode({
            "leftTicketDTO.train_date": date_str,
            "leftTicketDTO.from_station": from_code,
            "leftTicketDTO.to_station": to_code,
            "purpose_codes": "ADULT",
        })
    )

    print(f"[12306] querying: {origin}({from_code}) → {destination}({to_code}) on {date_str}")

    try:
        opener = _get_12306_opener()
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0",
            "Referer": "https://kyfw.12306.cn/otn/leftTicket/init",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "If-Modified-Since": "0",
            "Cache-Control": "no-cache",
            "X-Requested-With": "XMLHttpRequest",
        })
        with opener.open(req, timeout=15) as r:
            raw = r.read()
            # 12306 often returns UTF-8 with BOM
            data = json.loads(raw.decode("utf-8-sig") if raw.startswith(b'\xef\xbb\xbf') else raw.decode("utf-8"))

        if not data.get("status") and data.get("httpstatus") != 200:
            print(f"[12306] API error: {data.get('messages', 'unknown')}")
            return []

        result = data.get("data", {}).get("result", [])
        station_map = data.get("data", {}).get("map", {})

        if not result:
            print(f"[12306] no trains found for this route/date")
            return []

        trains: list[dict] = []
        # Batch query REAL prices: first collect all trains, then query prices in batch
        raw_trains: list[dict] = []
        for item in result:
            fields = item.split("|")
            if len(fields) < 30:
                continue

            # Field reference (12306's documented format):
            # 0: secretStr, 1: buttonText (预订),
            # 2: train_no (internal hash — used for price query),
            # 3: station_train_code (e.g. "G102"),
            # 4: start_station_telecode, 5: end_station_telecode,
            # 6: from_station_telecode, 7: to_station_telecode,
            # 8: start_time, 9: arrive_time, 10: lishi (duration),
            # ...
            # 16: from_station_no (used for price query),
            # 17: to_station_no (used for price query),
            # ...
            # Seat availability (count or "有"/"无"):
            # 23: swz (商务座), 24: tz (特等座),
            # 25: zy (一等座), 26: ze (二等座),
            # 27: gr (高级软卧), 28: rw (软卧),
            # 29: yw (硬卧), 30: wz (无座),

            train_code = fields[3]  # e.g. "G102"
            internal_train_no = fields[2]  # internal hash for price API
            from_station_code = fields[6]
            to_station_code = fields[7]
            depart_time = fields[8]
            arrive_time = fields[9]
            duration = fields[10]
            start_station_code = fields[4]
            end_station_code = fields[5]
            from_station_no = fields[16] if len(fields) > 16 else ""
            to_station_no = fields[17] if len(fields) > 17 else ""

            # Seat availability counts (indices 23-30)
            def _parse_seats(val: str) -> int:
                if val.isdigit() and int(val) > 0:
                    return int(val)
                if val in ("有", "*"):
                    return 99  # "available"
                return 0

            ze_count = fields[26] if len(fields) > 26 else ""  # 二等座 at index 26
            zy_count = fields[25] if len(fields) > 25 else ""  # 一等座 at index 25
            swz_count = fields[23] if len(fields) > 23 else ""  # 商务座 at index 23

            train_type_prefix = train_code[0] if train_code else "K"
            train_type = TRAIN_TYPES.get(train_type_prefix, f"其他 ({train_type_prefix})")

            from_name = station_map.get(from_station_code, from_station_code)
            to_name = station_map.get(to_station_code, to_station_code)
            start_name = station_map.get(start_station_code, start_station_code)
            end_name = station_map.get(end_station_code, end_station_code)

            raw_trains.append({
                "train_no": train_code,
                "internal_train_no": internal_train_no,
                "from_station_no": from_station_no,
                "to_station_no": to_station_no,
                "type": train_type,
                "type_prefix": train_type_prefix,
                "departure_time": depart_time,
                "arrival_time": arrive_time,
                "duration": duration,
                "from_station": from_name,
                "to_station": to_name,
                "start_station": start_name,
                "end_station": end_name,
                "seats_second": _parse_seats(ze_count),
                "seats_first": _parse_seats(zy_count),
                "seats_business": _parse_seats(swz_count),
                "currency": "CNY",
                "from": origin,
                "to": destination,
            })

        # ---- Query REAL prices from 12306 price API (one request per train) ----
        real_price_count = 0
        for rt in raw_trains:
            seat_codes = SEAT_CODES_BY_TYPE.get(rt["type_prefix"], ["O", "M"])
            real_prices = {}

            if rt["internal_train_no"] and rt["from_station_no"] and rt["to_station_no"]:
                real_prices = _query_ticket_price(
                    rt["internal_train_no"],
                    rt["from_station_no"],
                    rt["to_station_no"],
                    seat_codes,
                    date_str,
                )

            price_source = "12306_real_price" if real_prices else "12306_estimated"

            if real_prices:
                real_price_count += 1
                # Map seat codes to price fields
                # O=二等座, M=一等座, 9=商务座, 4=软卧, 3=硬卧
                price_second = real_prices.get("O", 0)
                price_first = real_prices.get("M", 0)
                price_business = real_prices.get("9", real_prices.get("P", 0))
                # For non-HSR trains, use sleeper prices
                if not price_second and "4" in real_prices:
                    price_second = real_prices["4"]  # soft sleeper
                    price_first = real_prices.get("3", price_second * 0.7)  # hard sleeper
            else:
                # Fallback: distance-based estimation (clearly marked)
                dist = _station_distance(from_code, to_code)
                price_km = PRICE_PER_KM.get(rt["type_prefix"], 0.15)
                price_second = round(dist * price_km, 0)
                price_first = round(price_second * 1.6, 0)
                price_business = round(price_second * 3.0, 0)
                print(f"[12306] using ESTIMATED prices for {rt['train_no']} "
                      f"(distance={dist}km, rate={price_km}/km)")

            trains.append({
                "train_no": rt["train_no"],
                "type": rt["type"],
                "departure_time": rt["departure_time"],
                "arrival_time": rt["arrival_time"],
                "duration": rt["duration"],
                "from_station": rt["from_station"],
                "to_station": rt["to_station"],
                "start_station": rt["start_station"],
                "end_station": rt["end_station"],
                "price_second": price_second,
                "price_first": price_first,
                "price_business": price_business,
                "seats_second": rt["seats_second"],
                "seats_first": rt["seats_first"],
                "seats_business": rt["seats_business"],
                "currency": "CNY",
                "source": price_source,
                "from": origin,
                "to": destination,
            })

        if real_price_count:
            print(f"[12306] GOT REAL PRICES for {real_price_count}/{len(trains)} trains")
        elif trains:
            print(f"[12306] NO real prices available (all {len(trains)} trains using estimates — "
                  f"date may be outside 15-day booking window)")

        print(f"[12306] found {len(trains)} trains: "
              f"{', '.join(t['train_no'] for t in trains[:5])}"
              f"{'...' if len(trains) > 5 else ''}")

        return trains

    except urllib.error.HTTPError as e:
        print(f"[12306] HTTP {e.code}: {e.reason}")
        return []
    except Exception as e:
        print(f"[12306] query failed: {e}")
        return []


# ---------------------------------------------------------------------------
# Quick test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    trains = search_trains("北京", "上海", "2026-07-28")
    for t in trains[:5]:
        print(f"  {t['train_no']} {t['type']} {t['departure_time']}→{t['arrival_time']} "
              f"({t['duration']}) ¥{t['price_second']}/¥{t['price_first']} "
              f"余票: {t['seats_second']}")
