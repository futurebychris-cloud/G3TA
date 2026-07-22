"""Cultural / traditional-fashion advisor.

This is a small built-in reference table keyed by destination country. It is
intentionally isolated behind `CultureAdvisor` so it can later be swapped for
a real cultural-data API without touching `categories/clothing.py`.
"""

from dataclasses import dataclass, field


@dataclass
class CultureNote:
    traditional_wear: list[str] = field(default_factory=list)
    fashion_norms: list[str] = field(default_factory=list)
    modesty_notes: list[str] = field(default_factory=list)


_CULTURE_TABLE: dict[str, CultureNote] = {
    "japan": CultureNote(
        traditional_wear=["yukata (rentable at many festivals/onsen towns)"],
        fashion_norms=["neat, modest streetwear is the norm; swimwear only at pools/beaches"],
        modesty_notes=["remove shoes before entering homes, some restaurants, and temples"],
    ),
    "india": CultureNote(
        traditional_wear=["kurta or saree for temple visits/festivals (optional for tourists)"],
        fashion_norms=["cover shoulders and knees at religious sites"],
        modesty_notes=["carry a scarf/shawl for temples and mosques"],
    ),
    "thailand": CultureNote(
        traditional_wear=["light, loose linen clothing suits the tropical climate"],
        fashion_norms=["cover shoulders and knees when visiting temples (sarongs often available to rent)"],
        modesty_notes=["remove shoes before entering temples and many homes"],
    ),
    "united arab emirates": CultureNote(
        traditional_wear=[],
        fashion_norms=["modest clothing recommended in public (shoulders/knees covered)"],
        modesty_notes=["swimwear limited to pools/private beaches"],
    ),
    "italy": CultureNote(
        traditional_wear=[],
        fashion_norms=["smart-casual is common; churches require covered shoulders and knees"],
        modesty_notes=["carry a light scarf for cathedral visits"],
    ),
    "morocco": CultureNote(
        traditional_wear=["djellaba seen in markets/medinas (not required for tourists)"],
        fashion_norms=["modest, loose-fitting clothing is respectful, especially outside tourist zones"],
        modesty_notes=["cover shoulders/knees, particularly for women, when away from resorts"],
    ),
    "south korea": CultureNote(
        traditional_wear=["hanbok (rentable near palaces, e.g. Gyeongbokgung)"],
        fashion_norms=["fashion-forward streetwear is common and welcomed"],
        modesty_notes=[],
    ),
    "mexico": CultureNote(
        traditional_wear=["embroidered blouses/huipil available in markets for festivals"],
        fashion_norms=["casual, colorful clothing is common"],
        modesty_notes=[],
    ),
}

_DEFAULT_NOTE = CultureNote(
    traditional_wear=[],
    fashion_norms=["general modest/casual clothing is a safe default; observe local norms on arrival"],
    modesty_notes=["carry a light layer to cover shoulders/knees for religious or formal sites"],
)


class CultureAdvisor:
    def lookup(self, destination_country: str) -> CultureNote:
        return _CULTURE_TABLE.get(destination_country.strip().lower(), _DEFAULT_NOTE)
