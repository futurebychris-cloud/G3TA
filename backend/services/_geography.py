"""Small, field-aware guards for the retired Tokyo demo catalogue.

Free text can legitimately mention Tokyo (for example a layover or a restaurant
brand), so callers must use these helpers only on route endpoints or selected
place records that are supposed to belong to the requested destination.
"""
import re


RETIRED_TOKYO_RECORD_IDS = {
    "fl_ana_01", "fl_jal_01", "fl_ua_01", "fl_dl_01", "fl_zip_01",
    "ht_shinjuku_business", "ht_asakusa_ryokan", "ht_shibuya_tower",
    "ht_ueno_hostel", "ht_ginza_luxe",
    "ac_senso", "ac_teamlab", "ac_shibuya", "ac_fuji", "ac_skytree",
    "ac_gokart", "ac_meiji", "ac_sumo", "ac_cooking",
    "fd_sushidai", "fd_ichiran", "fd_gonpachi", "fd_tsukiji", "fd_afuri",
    "fd_tempura", "fd_curry", "fd_veg", "fd_cafe",
}

_RETIRED_TOKYO_PLACE_NAMES = {
    "shinjuku granbell hotel",
    "asakusa view ryokan",
    "shibuya sky tower hotel",
    "ueno nordic hostel",
    "ginza grand luxe",
    "senso-ji temple & nakamise street",
    "teamlab planets digital art museum",
    "shibuya crossing & shopping",
    "mt. fuji & hakone day trip",
    "tokyo skytree observation deck",
    "akihabara street go-kart tour",
    "meiji jingu shrine & yoyogi park",
    "grand sumo tournament (ryogoku)",
}

_RETIRED_TOKYO_NAME_PHRASES = {
    "senso-ji temple",
    "teamlab planets",
    "shibuya crossing",
    "mt. fuji & hakone",
    "tokyo skytree",
    "akihabara street go-kart",
    "meiji jingu shrine",
    "grand sumo tournament (ryogoku)",
}

_RETIRED_TOKYO_AREAS = {
    "tokyo", "asakusa", "shibuya", "ginza", "shinjuku", "akihabara",
    "ueno", "toyosu", "hakone", "sumida", "harajuku", "ryogoku",
    "nishiazabu", "tsukiji", "ebisu", "tomigaya",
}

_TOKYO_ROUTE_ENDPOINT = re.compile(
    r"(?<![a-z0-9])(?:tokyo|nrt|hnd|narita|haneda)(?![a-z0-9])",
    re.IGNORECASE,
)
_TOKYO_ENDPOINT_CJK = ("东京", "東京", "成田", "羽田")


def _normalized(value) -> str:
    return str(value or "").strip().casefold()


def location_allows_tokyo_airport(value) -> bool:
    """Return whether Tokyo airports are plausible endpoints for the input place."""
    normalized = _normalized(value)
    english_aliases = (
        "tokyo", "japan", "yokohama", "kawasaki", "chiba", "saitama",
        "narita", "haneda",
    )
    cjk_aliases = (
        "东京", "東京", "日本", "横滨", "横浜", "川崎", "千叶", "千葉",
        "埼玉", "成田", "羽田",
    )
    return (
        any(
            re.search(rf"(?<![a-z0-9]){alias}(?![a-z0-9])", normalized)
            for alias in english_aliases
        )
        or any(alias in normalized for alias in cjk_aliases)
    )


def destination_allows_retired_tokyo_places(value) -> bool:
    """Return whether retired Tokyo place signatures match the destination itself."""
    normalized = _normalized(value)
    return (
        any(
            re.search(rf"(?<![a-z0-9]){alias}(?![a-z0-9])", normalized)
            for alias in ("tokyo", "japan")
        )
        or any(alias in normalized for alias in ("东京", "東京", "日本"))
    )


def tokyo_endpoint_marker(value) -> str | None:
    """Return the Tokyo airport/city marker in a strong route-endpoint field."""
    text = str(value or "")
    match = _TOKYO_ROUTE_ENDPOINT.search(text)
    if match:
        return match.group(0)
    return next((marker for marker in _TOKYO_ENDPOINT_CJK if marker in text), None)


def coordinates_are_tokyo_endpoint(lat, lng) -> bool:
    """Recognize Tokyo/Haneda/Narita coordinates from the retired route data."""
    try:
        latitude = float(lat)
        longitude = float(lng)
    except (TypeError, ValueError):
        return False
    central_tokyo_or_haneda = (
        35.45 <= latitude <= 35.85 and 139.55 <= longitude <= 140.05
    )
    narita = 35.65 <= latitude <= 35.90 and 140.20 <= longitude <= 140.55
    return central_tokyo_or_haneda or narita


def _contains_bounded_phrase(value: str, phrase: str) -> bool:
    return bool(re.search(
        rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])",
        value,
    ))


def retired_tokyo_record_field(record: dict, *, include_name: bool = True) -> tuple[str, str] | None:
    """Identify an exact retired-demo signature in a selected place record."""
    record_id = _normalized(record.get("id"))
    if record_id in RETIRED_TOKYO_RECORD_IDS:
        return "id", str(record.get("id"))
    area = _normalized(record.get("area"))
    area_match = area == "tokyo" or any(
        _contains_bounded_phrase(area, retired_area)
        for retired_area in _RETIRED_TOKYO_AREAS - {"tokyo"}
    )
    if area_match:
        return "area", str(record.get("area"))
    name = _normalized(record.get("name"))
    name_match = name in _RETIRED_TOKYO_PLACE_NAMES or any(
        _contains_bounded_phrase(name, phrase)
        for phrase in _RETIRED_TOKYO_NAME_PHRASES
    )
    if include_name and name_match:
        return "name", str(record.get("name"))
    return None
