"""Cultural fashion and clothing recommendation service.

Provides destination-specific clothing advice beyond temperature:
1. Cultural norms (modest dress for temples, local fashion trends)
2. Traditional clothing recommendations
3. Seasonal fashion guidance
4. Shopping suggestions for local fashion

Replaces the temperature-only _clothing_by_temperature() with rich cultural context.
"""
from __future__ import annotations


# Cultural dress codes by destination type
_CULTURAL_DRESS_CODES: dict[str, dict] = {
    "japan": {
        "temple_shrine": "Cover shoulders and knees. Remove shoes where indicated.",
        "traditional": "Kimono/yukata rental available in Kyoto, Asakusa (Tokyo).",
        "general": "Clean, neat appearance valued. No ripped clothing in formal settings.",
        "fashion_trends": "Harajuku street style, Uniqlo basics, Muji minimalist aesthetic.",
        "shopping_districts": "Shibuya 109, Ginza, Omotesando, Shimokitazawa vintage.",
    },
    "thailand": {
        "temple": "Cover shoulders and knees mandatory. Sarongs often provided at entrance.",
        "traditional": "Thai silk (Jim Thompson), traditional chut thai for special occasions.",
        "general": "Light, breathable fabrics. Modest dress in rural areas.",
        "fashion_trends": "Bangkok street fashion, Chatuchak market finds, resort wear.",
        "shopping_districts": "Siam Paragon, Chatuchak Weekend Market, MBK Center.",
    },
    "china": {
        "temple": "Modest dress for temples. Remove hats in worship areas.",
        "traditional": "Qipao/cheongsam in Shanghai, Hanfu experience in historic cities.",
        "general": "Smart casual widely accepted. Avoid overly revealing in conservative areas.",
        "fashion_trends": "Shanghai fashion week, Taobao trends, street style in Chengdu/Beijing.",
        "shopping_districts": "Nanjing Road (Shanghai), Wangfujing (Beijing), Chunxi Road (Chengdu).",
    },
    "india": {
        "temple": "Cover shoulders, knees. Remove shoes. Head covering may be required.",
        "traditional": "Sari, salwar kameez, kurta — widely worn and available for purchase.",
        "general": "Modest dress recommended. Loose, breathable cotton ideal.",
        "fashion_trends": "Indo-western fusion, handloom textiles, designer boutiques in Mumbai/Delhi.",
        "shopping_districts": "Colaba Causeway (Mumbai), Connaught Place (Delhi), Commercial Street (Bangalore).",
    },
    "uae": {
        "temple_mosque": "Women: cover hair, arms, legs. Abaya provided at mosque entrances. Men: long pants.",
        "traditional": "Abaya, kandura — traditional but not required for tourists.",
        "general": "Modest dress in public. Swimwear only at beach/pool. No public displays in sheer clothing.",
        "fashion_trends": "Dubai Mall luxury brands, Gold Souk, designer abayas.",
        "shopping_districts": "Dubai Mall, Mall of the Emirates, Gold Souk, Global Village.",
    },
    "singapore": {
        "temple": "Cover shoulders and knees for temples and mosques.",
        "traditional": "Peranakan kebaya, cheongsam — cultural heritage fashion.",
        "general": "Smart casual. Light fabrics for humidity. Air-con indoors can be cold.",
        "fashion_trends": "Orchard Road luxury, Haji Lane indie boutiques, Bugis Street bargains.",
        "shopping_districts": "Orchard Road, Marina Bay Sands, Bugis Street, Haji Lane.",
    },
    "france": {
        "church": "Cover shoulders in churches. Remove hats.",
        "traditional": "Breton stripes, beret, chic Parisian style.",
        "general": "Effortlessly chic. Neutral colors, quality fabrics. Avoid athletic wear in nice restaurants.",
        "fashion_trends": "Paris Fashion Week, Le Marais boutiques, vintage in Saint-Ouen.",
        "shopping_districts": "Champs-Élysées, Le Marais, Galeries Lafayette, Saint-Germain.",
    },
    "italy": {
        "church": "Cover shoulders and knees in churches (strictly enforced at Vatican).",
        "traditional": "Italian leather goods, silk scarves, tailored suits.",
        "general": "La bella figura — always well-presented. No flip-flops in cities.",
        "fashion_trends": "Milan Fashion Week, artisan leather in Florence, Venetian glass jewelry.",
        "shopping_districts": "Via Montenapoleone (Milan), Via Condotti (Rome), Ponte Vecchio (Florence).",
    },
    "korea": {
        "temple": "Modest dress for temples. Remove shoes.",
        "traditional": "Hanbok rental available at Gyeongbokgung and Bukchon (Seoul).",
        "general": "Trendy, well-groomed. K-fashion influences. Cover up in traditional areas.",
        "fashion_trends": "Myeongdong K-beauty, Dongdaemun fashion, Hongdae street style.",
        "shopping_districts": "Myeongdong, Gangnam, Hongdae, Dongdaemun, Garosu-gil.",
    },
}

# Destination → country mapping for cultural lookup
_DESTINATION_COUNTRY_MAP: dict[str, str] = {
    "shanghai": "china", "beijing": "china", "guangzhou": "china",
    "shenzhen": "china", "hangzhou": "china", "chengdu": "china",
    "chongqing": "china", "xian": "china", "nanjing": "china",
    "suzhou": "china", "xiamen": "china", "kunming": "china",
    "tokyo": "japan", "osaka": "japan", "kyoto": "japan",
    "seoul": "korea", "busan": "korea",
    "bangkok": "thailand", "chiang mai": "thailand", "phuket": "thailand",
    "singapore": "singapore",
    "paris": "france", "nice": "france", "lyon": "france",
    "rome": "italy", "milan": "italy", "florence": "italy", "venice": "italy",
    "mumbai": "india", "delhi": "india", "jaipur": "india", "goa": "india",
    "dubai": "uae", "abu dhabi": "uae",
    "london": "uk",
    "new york": "usa", "los angeles": "usa", "san francisco": "usa",
}


def _get_country_culture(destination: str) -> dict | None:
    """Get cultural dress guidance for a destination."""
    key = destination.lower().strip().split(",")[0].strip()
    country = _DESTINATION_COUNTRY_MAP.get(key, "")
    if not country:
        country = key
    return _CULTURAL_DRESS_CODES.get(country)


def get_cultural_clothing(destination: str) -> dict:
    """Get destination-specific cultural clothing recommendations.

    Returns: {
        dress_codes: [{rule, context}],
        traditional_wear: str,
        fashion_trends: str,
        shopping_areas: [str],
        packing_tips: [str],
    }
    """
    culture = _get_country_culture(destination)

    if not culture:
        return {
            "dress_codes": [{"rule": "Research local customs before travel.", "context": "general"}],
            "traditional_wear": "Check local tourism office for traditional clothing information.",
            "fashion_trends": "Search social media for current local fashion trends.",
            "shopping_areas": ["Local markets and shopping districts"],
            "packing_tips": [
                "Pack versatile pieces that can be layered.",
                "Bring one modest outfit for religious sites.",
                "Comfortable walking shoes are essential.",
            ],
            "source": "generic",
        }

    dress_codes = []
    for key, value in culture.items():
        if key in ("temple", "temple_shrine", "temple_mosque", "church"):
            dress_codes.append({"rule": value, "context": "religious_sites"})
        elif key == "general":
            dress_codes.append({"rule": value, "context": "general"})
        elif key == "traditional":
            pass  # handled separately
        elif key == "fashion_trends":
            pass  # handled separately
        elif key == "shopping_districts":
            pass  # handled separately

    return {
        "dress_codes": dress_codes,
        "traditional_wear": culture.get("traditional", ""),
        "fashion_trends": culture.get("fashion_trends", ""),
        "shopping_areas": culture.get("shopping_districts", "").split(", "),
        "packing_tips": [
            culture.get("general", "Dress respectfully for local customs."),
            "Pack one modest outfit for visiting religious or cultural sites.",
            culture.get("traditional", "Consider experiencing local traditional clothing."),
            "Check the weather forecast and pack layers accordingly.",
        ],
        "source": "cultural_database",
    }


def get_fashion_search_query(destination: str, season: str = "") -> str:
    """Generate a Google/web search query for local fashion and what to wear."""
    country = _DESTINATION_COUNTRY_MAP.get(destination.lower().strip().split(",")[0].strip(), destination)
    season_str = f" {season}" if season else ""
    return f"what to wear in {destination}{season_str} fashion tips traditional clothing {country} travel guide"


def get_clothing_recommendations(
    destination: str,
    weather_data: dict | None = None,
    preferences: list[str] | None = None,
) -> dict:
    """Get complete clothing recommendations combining culture + weather.

    Returns: {
        cultural_advice: {...},
        weather_based_items: [...],
        complete_packing_tips: [...],
        shopping_suggestions: [...],
        cultural_note: str,
    }
    """
    cultural = get_cultural_clothing(destination)

    weather_items = []
    if weather_data:
        daily = weather_data.get("daily", [])
        if daily:
            highs = [float(d.get("high_c", 25)) for d in daily if d.get("high_c")]
            lows = [float(d.get("low_c", 15)) for d in daily if d.get("low_c")]
            rain = any(d.get("rain_chance", 0) >= 0.4 for d in daily)

            if lows and min(lows) < 10:
                weather_items.append("Warm jacket or coat")
                weather_items.append("Sweaters/layers")
            if lows and min(lows) <= 0:
                weather_items.append("Thermal base layers")
                weather_items.append("Gloves + warm hat")
            if highs and max(highs) > 26:
                weather_items.append("Lightweight, breathable tops")
                weather_items.append("Sun hat + sunglasses")
            if rain:
                weather_items.append("Compact umbrella")
                weather_items.append("Water-resistant shoes")

    return {
        "cultural_advice": cultural,
        "weather_based_items": weather_items,
        "complete_packing_tips": cultural.get("packing_tips", []),
        "shopping_suggestions": (
            cultural.get("shopping_areas", [])
        ),
        "cultural_note": (
            f"Local fashion in this region emphasizes {cultural.get('fashion_trends', 'smart casual dress')}. "
            f"{cultural.get('traditional_wear', '')}"
        ),
        "source": cultural.get("source", "cultural_database"),
    }
