"""Ctrip hotel booking pipeline package.

Public entry points used by the FastAPI layer in backend/main.py:
    from booking import pipeline
    pipeline.search_and_filter(request)
    pipeline.confirm_booking(request)
    pipeline.mark_paid(route_id, order_no)
"""
from . import pipeline, db, schemas, ctrip  # noqa: F401

__all__ = ["pipeline", "db", "schemas", "ctrip"]
