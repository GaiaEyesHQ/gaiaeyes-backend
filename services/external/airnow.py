import os
from typing import Any, Dict, List

import httpx

API_KEY = os.getenv("AIRNOW_API_KEY", "")
BASE = "https://www.airnowapi.org/aq/observation/zipCode/current/"
DEFAULT_RADIUS_MI = int(os.getenv("LOCAL_SIGNALS_AIRNOW_RADIUS_MI", "25"))


async def current_by_zip(zip_code: str, distance_miles: int | None = None) -> List[Dict[str, Any]]:
    if not API_KEY:
        return []
    params = {
        "format": "application/json",
        "zipCode": zip_code,
        "distance": distance_miles or DEFAULT_RADIUS_MI,
        "API_KEY": API_KEY,
    }
    async with httpx.AsyncClient(timeout=30.0) as cx:
        r = await cx.get(BASE, params=params)
        r.raise_for_status()
        return r.json() if r.text.strip() else []
