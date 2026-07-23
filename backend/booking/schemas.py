"""Pydantic models for the Ctrip hotel pipeline API.

These mirror the shapes the frontend sends/receives. Kept separate from the
pipeline logic so the endpoint layer and the scraping/booking layer stay decoupled.
"""
from pydantic import BaseModel, Field


# --- Search ------------------------------------------------------------------ #
class HotelSearchRequest(BaseModel):
    location: str                              # city name, e.g. "上海" or "Shanghai"
    check_in: str                              # YYYY-MM-DD
    check_out: str                             # YYYY-MM-DD
    adults: int = 1
    children: int = 0
    rooms: int = 1
    max_price_per_night: float | None = None   # budget agent's housing cap (CNY)
    min_rating: float | None = None            # planning-agent preference (stars)
    preferences: list[str] = Field(default_factory=list)  # e.g. ["central", "quiet"]


class RoomInfo(BaseModel):
    """Single room type extracted from Ctrip detail page."""
    name: str = ""                       # e.g. "高级双床房"
    price_per_night: float | None = None # price in CNY per night
    bed_type: str = ""                   # e.g. "大床", "双人床"
    includes: str = ""                   # e.g. "含早餐", "无早"
    cancellation: str = ""               # e.g. "免费取消"


class HotelResult(BaseModel):
    id: str
    name: str
    price_per_night: float | None = None   # None => price not available (e.g. OpenStreetMap)
    rating: float | None = None
    area: str = ""
    tags: list[str] = Field(default_factory=list)
    url: str = ""
    currency: str = "CNY"
    source: str = "ctrip"          # "ctrip" (live) | "api" | "openstreetmap"

    # --- Extended detail fields (populated by ctrip_detail scraper) ---
    images: list[str] = Field(default_factory=list)         # hotel gallery image URLs
    description: str = ""                                    # brief hotel intro
    star_rating: float | None = None                         # stars from Ctrip (e.g. 4.5)
    lat: float | None = None                                 # latitude (for Google Maps / 高德地图)
    lng: float | None = None                                 # longitude
    labels: list[str] = Field(default_factory=list)          # amenity labels (bathtub, breakfast, wifi...)
    rooms: list[RoomInfo] = Field(default_factory=list)      # available room types + prices
    total_cost: float | None = None                          # calculated: lowest room * nights - discount
    discount: float | None = None                            # discount/coupon amount in CNY


# --- User / identity --------------------------------------------------------- #
class UserRequest(BaseModel):
    name: str
    id_number: str                  # used to auto-fill the Ctrip guest form
    phone: str


# --- Confirm / book ---------------------------------------------------------- #
class HotelSelection(BaseModel):
    id: str
    name: str
    url: str = ""
    room_type: str | None = None
    price_total: float | None = None
    currency: str = "CNY"


class BookingConfirmRequest(BaseModel):
    # One-time traveler identity for the provider request. The pipeline does not
    # persist these fields in G3TA.
    id_number: str
    name: str | None = None
    phone: str | None = None
    hotel: HotelSelection
    check_in: str
    check_out: str
    rooms: int = 1
    adults: int = 1
    children: int = 0
    payment_method: str = "wechat"  # "wechat" | "alipay"


class BookingResult(BaseModel):
    status: str                     # usually "pending_payment" | "failed"
    order_no: str | None = None
    message: str = ""
    route: dict | None = None
