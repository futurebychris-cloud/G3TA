import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "")
OPENWEATHER_BASE_URL = "https://api.openweathermap.org"

_DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PLANNING_DATA_DIR = Path(os.getenv("PLANNING_DATA_DIR", str(_DEFAULT_DATA_DIR))).resolve()
WEATHER_CACHE_TTL_SECONDS = int(os.getenv("WEATHER_CACHE_TTL_SECONDS", "900"))

PLANNING_DATA_DIR.mkdir(parents=True, exist_ok=True)

if not OPENWEATHER_API_KEY:
    raise RuntimeError(
        "OPENWEATHER_API_KEY is not set. Add it to a .env file or export it "
        "as an environment variable before starting the planning agent."
    )
