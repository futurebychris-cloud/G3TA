"""Security boundary for the local/demo API.

Core planning remains available on localhost without accounts. Endpoints that
store traveler identity data or drive a provider browser are disabled unless an
operator explicitly enables them and supplies a server-side access token.
"""
from __future__ import annotations

import os
import secrets

from fastapi import Header, HTTPException


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


def require_booking_access(
    x_g3ta_booking_token: str | None = Header(default=None),
) -> None:
    """Protect provider automation and traveler/booking records."""
    if not booking_automation_enabled():
        raise HTTPException(
            status_code=503,
            detail=(
                "Booking automation is disabled. Search and compare options in G3TA, "
                "then complete the purchase on the provider."
            ),
        )
    expected = os.getenv("BOOKING_API_TOKEN", "")
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="BOOKING_API_TOKEN is required when booking automation is enabled.",
        )
    if not x_g3ta_booking_token or not secrets.compare_digest(
        x_g3ta_booking_token,
        expected,
    ):
        raise HTTPException(status_code=401, detail="Invalid booking access token.")
