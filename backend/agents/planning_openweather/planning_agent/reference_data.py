"""Static reference data used by the planning subagent's rule engines.

None of this is fetched from an external service — it is the agent's built-in
knowledge base. Keeping it in one module makes it easy for a future subagent
(e.g. a real culture/visa API) to replace a single lookup without touching
the rule logic in `categories/`.
"""

# ---------------------------------------------------------------------------
# Clothing: temperature bands -> garment recommendations (Celsius)
# Bands are checked low-to-high; `max_c` is exclusive.
# ---------------------------------------------------------------------------
TEMPERATURE_BANDS = [
    {"max_c": 0, "label": "freezing", "garments": [
        "heavy insulated coat", "thermal base layers", "wool sweater",
        "winter gloves", "beanie", "scarf", "insulated waterproof boots",
    ]},
    {"max_c": 10, "label": "cold", "garments": [
        "winter jacket", "sweater or fleece", "long pants", "gloves",
        "warm socks", "closed-toe boots",
    ]},
    {"max_c": 16, "label": "cool", "garments": [
        "light jacket or coat", "long sleeve shirt", "sweater/cardigan for evening",
        "long pants",
    ]},
    {"max_c": 22, "label": "mild", "garments": [
        "light layers", "long sleeve or t-shirt", "light cardigan for evening",
        "jeans or light pants",
    ]},
    {"max_c": 28, "label": "warm", "garments": [
        "t-shirts", "shorts or light pants", "breathable fabrics",
        "light layer for air conditioning",
    ]},
    {"max_c": 999, "label": "hot", "garments": [
        "lightweight breathable t-shirts", "shorts", "sun hat",
        "moisture-wicking fabric",
    ]},
]

HUMIDITY_ADDONS = {
    "high": (70, [
        "moisture-wicking / quick-dry fabric", "extra changes of clothes",
        "antiperspirant", "breathable footwear (avoid heavy cotton)",
    ]),
    "low": (30, [
        "moisturizer for skin", "lip balm", "reusable water bottle (dry air dehydrates)",
    ]),
}

WEATHER_CONDITION_ADDONS = {
    "rain": ["rain jacket / poncho", "compact umbrella", "waterproof shoes or covers"],
    "snow": ["waterproof snow boots", "insulated waterproof jacket", "thermal socks"],
    "thunderstorm": ["rain jacket / poncho", "waterproof phone pouch"],
    "drizzle": ["light rain jacket", "compact umbrella"],
    "clear": ["sunglasses", "sun hat"],
}

# ---------------------------------------------------------------------------
# Supportive category: weather-driven health risk -> advice
# ---------------------------------------------------------------------------
SICKNESS_RISK_RULES = [
    {
        "condition": lambda avg_temp, avg_humid, main: avg_temp < 12 and main in ("rain", "drizzle", "snow"),
        "risk": "cold / cough / flu",
        "advice": [
            "pack cold & flu medicine (decongestant, antihistamine)",
            "cough drops / throat lozenges",
            "keep a spare warm layer to avoid getting chilled and wet",
        ],
    },
    {
        "condition": lambda avg_temp, avg_humid, main: avg_temp >= 27 and avg_humid >= 60,
        "risk": "heat exhaustion / dehydration",
        "advice": [
            "electrolyte packets / oral rehydration salts",
            "carry water and take shade breaks",
            "avoid strenuous activity during peak heat hours",
        ],
    },
    {
        "condition": lambda avg_temp, avg_humid, main: avg_temp >= 22 and avg_humid >= 65,
        "risk": "pests (mosquitoes / insects)",
        "advice": [
            "insect repellent (DEET or picaridin based)",
            "after-bite / anti-itch cream",
            "consider long sleeves at dusk in high-mosquito areas",
        ],
    },
    {
        "condition": lambda avg_temp, avg_humid, main: avg_humid < 30,
        "risk": "dry throat / sinus irritation",
        "advice": ["saline nasal spray", "lozenges", "stay hydrated"],
    },
]

GENERAL_SUPPORTIVE_ITEMS = [
    "personal prescription medication (enough for the full trip + buffer days)",
    "basic first-aid kit (band-aids, antiseptic wipes, pain reliever)",
    "motion sickness tablets if traveling by boat/winding roads",
]

# ---------------------------------------------------------------------------
# Supportive: hotel-amenity checklist loop
# ---------------------------------------------------------------------------
DAILY_ESSENTIALS = [
    "toothbrush", "toothpaste", "shampoo", "conditioner", "body wash / soap",
    "lotion / moisturizer", "razor", "deodorant", "hair dryer", "towel",
]

# ---------------------------------------------------------------------------
# Legal category
# ---------------------------------------------------------------------------
NATIONAL_DOCS = ["government-issued photo ID"]
INTERNATIONAL_DOCS_BASE = [
    "passport (valid 6+ months beyond return date, per common entry rules)",
    "printed/digital copy of passport stored separately from the original",
]

# ---------------------------------------------------------------------------
# Devices: default accessory suggestions per device keyword
# ---------------------------------------------------------------------------
DEVICE_ACCESSORY_MAP = {
    "phone": ["charger", "power bank"],
    "laptop": ["laptop charger", "protective sleeve"],
    "ipad": ["ipad charger / cable"],
    "tablet": ["tablet charger / cable"],
    "camera": ["camera charger / spare battery", "extra memory card"],
    "headphones": ["charging cable (if wireless)"],
    "e-reader": ["charging cable"],
}
DEFAULT_ENTERTAINMENT_SUGGESTIONS = ["a book or e-reader", "headphones", "offline-downloaded music/shows"]
UNIVERSAL_ADAPTER_NOTE = "universal power adapter (destination may use different plug/voltage)"

# ---------------------------------------------------------------------------
# Flight & travel restriction reminders (general IATA / TSA-style guidance;
# always verify against the specific airline before departure).
# ---------------------------------------------------------------------------
FLIGHT_INFO_NOTES = [
    "Carry-on baggage: most airlines allow one bag up to ~7-10 kg (15-22 lb) and "
    "linear dimensions around 56 x 36 x 23 cm (22 x 14 x 9 in) — confirm with your airline.",
    "Checked baggage: economy allowance is typically 20-23 kg (44-50 lb) per bag; "
    "overweight bags incur extra fees.",
    "Liquids, gels & aerosols in carry-on must be in containers of 100 ml (3.4 oz) "
    "or less, all fitting in a single 1-quart / 1-liter clear resealable bag.",
    "Spare lithium batteries and power banks must go in carry-on, not checked luggage.",
    "Sharp objects (scissors, razors blades, knives) are not allowed in carry-on.",
    "Keep medication in original labeled packaging and carry a copy of the prescription.",
    "Arrive at the airport 2-3 hours early for international flights, 1.5-2 hours for domestic.",
]
