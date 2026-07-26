"""Security boundary for the local/demo API.

Core planning remains available on localhost without accounts. Endpoints that
store traveler identity data or drive a provider browser are disabled unless an
operator explicitly enables them and supplies a server-side access token.
"""
from __future__ import annotations

import os
import secrets
from urllib.parse import urlsplit

from fastapi import HTTPException, Request


TRUE_VALUES = {"1", "true", "yes", "on"}
LOCAL_ORIGINS = (
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://127.0.0.1:8000",
    "http://localhost:8000",
)


def env_enabled(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().casefold() in TRUE_VALUES


def cors_allowed_origins() -> list[str]:
    """Return explicit CORS origins; wildcard access is never the default."""
    configured = os.getenv("CORS_ALLOWED_ORIGINS", "")
    if not configured.strip():
        return list(LOCAL_ORIGINS)
    origins = [value.strip() for value in configured.split(",") if value.strip()]
    if "*" in origins and not env_enabled("ALLOW_INSECURE_CORS"):
        raise RuntimeError(
            "Wildcard CORS requires ALLOW_INSECURE_CORS=1. "
            "Set CORS_ALLOWED_ORIGINS to explicit frontend origins instead."
        )
    return origins


def booking_automation_enabled() -> bool:
    return env_enabled("BOOKING_AUTOMATION_ENABLED")


def require_booking_access(request: Request) -> None:
    """Protect provider automation and traveler/booking records.

    A configured ``BOOKING_API_TOKEN`` must be sent in the request header. Query
    parameters are deliberately rejected because URLs are commonly persisted in
    browser history, reverse-proxy logs, and monitoring systems.

    A tokenless localhost demo is available only through the explicit
    ``ALLOW_LOCAL_BOOKING_WITHOUT_TOKEN=1`` opt-in. It is never the default.
    """
    if not booking_automation_enabled():
        raise HTTPException(
            status_code=503,
            detail=(
                "Booking automation is disabled. Search and compare options in G3TA, "
                "then complete the purchase on the provider."
            ),
        )
    expected = os.getenv("BOOKING_API_TOKEN", "").strip()
    if expected:
        if len(expected) < 32:
            raise HTTPException(
                status_code=503,
                detail="BOOKING_API_TOKEN must contain at least 32 characters.",
            )
        token = request.headers.get("x-g3ta-booking-token") if request is not None else None
        if not token or not secrets.compare_digest(token, expected):
            raise HTTPException(status_code=401, detail="Invalid booking access token.")
        return

    if not env_enabled("ALLOW_LOCAL_BOOKING_WITHOUT_TOKEN"):
        raise HTTPException(
            status_code=503,
            detail=(
                "Booking automation requires BOOKING_API_TOKEN. For an isolated "
                "localhost demo only, explicitly set "
                "ALLOW_LOCAL_BOOKING_WITHOUT_TOKEN=1."
            ),
        )

    # Explicit local-demo override: still reject non-loopback clients.
    client = request.client.host if request is not None and request.client else None
    if client in ("127.0.0.1", "::1", "localhost"):
        return
    raise HTTPException(
        status_code=401,
        detail=(
            "BOOKING_API_TOKEN is not configured and this request did not come from "
            "localhost. Set BOOKING_API_TOKEN; the tokenless override is localhost-only."
        ),
    )


def validate_ctrip_hotel_url(value: str) -> str:
    """Allow only HTTPS Ctrip hotel URLs before a browser navigates to them."""
    value = (value or "").strip()
    if not value:
        return ""
    try:
        parsed = urlsplit(value)
        hostname = (parsed.hostname or "").casefold().rstrip(".")
        valid_host = hostname == "ctrip.com" or hostname.endswith(".ctrip.com")
        valid_port = parsed.port in (None, 443)
    except ValueError as exc:
        raise ValueError("Invalid Ctrip hotel URL.") from exc
    if (
        parsed.scheme.casefold() != "https"
        or not valid_host
        or not valid_port
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("Hotel URL must be an HTTPS URL on ctrip.com.")
    return value
