import logging
import os
from typing import Any, Dict, List

import httpx

API_KEY = os.getenv("AIRNOW_API_KEY", "")
ZIP_BASE = "https://www.airnowapi.org/aq/observation/zipCode/current/"
LATLON_BASE = "https://www.airnowapi.org/aq/observation/latLong/current/"
DEFAULT_RADIUS_MI = int(os.getenv("LOCAL_SIGNALS_AIRNOW_RADIUS_MI", "25"))
REQUEST_TIMEOUT_SECONDS = 10.0
# One location's complete search, shared by both endpoints and every radius.
CURRENT_TOTAL_BUDGET_SECONDS = 12.0

# AirNow authenticates in query parameters. HTTP client INFO/DEBUG logs expose
# request URLs; apply the cron's existing safeguard to API callers as well.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


async def _request(base: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not API_KEY:
        return []
    payload = {"format": "application/json", "API_KEY": API_KEY, **params}
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as cx:
        r = await cx.get(base, params=payload)
        r.raise_for_status()
        return r.json() if r.text.strip() else []


async def current_by_zip(zip_code: str, distance_miles: int | None = None) -> List[Dict[str, Any]]:
    return await _request(
        ZIP_BASE,
        {
            "zipCode": zip_code,
            "distance": distance_miles or DEFAULT_RADIUS_MI,
        },
    )


async def current_by_latlon(
    latitude: float,
    longitude: float,
    distance_miles: int | None = None,
) -> List[Dict[str, Any]]:
    return await _request(
        LATLON_BASE,
        {
            "latitude": latitude,
            "longitude": longitude,
            "distance": distance_miles or DEFAULT_RADIUS_MI,
        },
    )
