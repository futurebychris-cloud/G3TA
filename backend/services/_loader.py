"""Shared helper for loading mock JSON files.

Only the service functions in this package touch the mock files. Agents never
read a mock file directly — they call a service function. This is the single
seam where a teammate swaps a mock for a real API (see README "Adding Real APIs").
"""
import json
import os
from functools import lru_cache

_MOCKS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "mocks")


@lru_cache(maxsize=None)
def load_mock(filename: str) -> dict:
    path = os.path.join(_MOCKS_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
