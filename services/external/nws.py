import os
from typing import Any, Dict

import httpx

UA = os.getenv("WEATHER_UA", "(gaiaeyes.com, gaiaeyes7.83@gmail.com)")
HEADERS = {"User-Agent": UA, "Accept": "application/geo+json"}

BASE = "https://api.weather.gov"


async def points(lat: float, lon: float) -> Dict[str, Any]:
    url = f"{BASE}/points/{lat:.4f},{lon:.4f}"
    async with httpx.AsyncClient(timeout=30.0, headers=HEADERS) as cx:
        r = await cx.get(url)
        r.raise_for_status()
        return r.json()


async def grid_hourly(grid_id: str, x: int, y: int) -> Dict[str, Any]:
    url = f"{BASE}/gridpoints/{grid_id}/{x},{y}/forecast/hourly"
    async with httpx.AsyncClient(timeout=30.0, headers=HEADERS) as cx:
        r = await cx.get(url)
        r.raise_for_status()
        return r.json()
