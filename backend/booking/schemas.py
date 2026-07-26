"""Pydantic models for the Ctrip hotel pipeline API.

These mirror the shapes the frontend sends/receives. Kept separate from the
pipeline logic so the endpoint layer and the scraping/booking layer stay decoupled.
"""
from datetime import date

from pydantic import BaseModel, Field, field_validator, model_validator

from security import validate_ctrip_hotel_url


# --- Search ------------------------------------------------------------------ #
class HotelSearchRequest(BaseModel):
    location: str = Field(min_length=1, max_length=200)
    check_in: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    check_out: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    adults: int = Field(default=1, ge=1, le=100)
    children: int = Field(default=0, ge=0, le=100)
    rooms: int = Field(default=1, ge=1, le=20)
    max_price_per_night: float | None = Field(default=None, gt=0)
    min_rating: float | None = Field(default=None, ge=0, le=5)
    preferences: list[str] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def validate_dates(self):
        start = date.fromisoformat(self.check_in)
        end = date.fromisoformat(self.check_out)
        if end <= start:
            raise ValueError("check_out must be after check_in.")
        if (end - start).days > 31:
            raise ValueError("Hotel searches are limited to 31 nights.")
        return self


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
    id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=300)
    url: str = Field(default="", max_length=2048)
    room_type: str | None = Field(default=None, max_length=200)
    price_total: float | None = Field(default=None, ge=0)
    currency: str = Field(default="CNY", pattern=r"^[A-Za-z]{3}$")

    @field_validator("url")
    @classmethod
    def validate_provider_url(cls, value: str) -> str:
        return validate_ctrip_hotel_url(value)


class BookingConfirmRequest(BaseModel):
    # One-time traveler identity for the provider request. The pipeline does not
    # persist these fields in G3TA.
    id_number: str = Field(min_length=1, max_length=100)
    name: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=50)
    hotel: HotelSelection
    check_in: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    check_out: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    rooms: int = Field(default=1, ge=1, le=20)
    adults: int = Field(default=1, ge=1, le=100)
    children: int = Field(default=0, ge=0, le=100)
    payment_method: str = Field(default="wechat", pattern=r"^(wechat|alipay)$")


class BookingResult(BaseModel):
    status: str                     # usually "pending_payment" | "failed"
    order_no: str | None = None
    message: str = ""
    route: dict | None = None
