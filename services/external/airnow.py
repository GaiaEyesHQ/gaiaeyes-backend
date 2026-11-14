import logging
import math
import os
from typing import Any, Dict, List

import httpx

API_KEY = os.getenv("AIRNOW_API_KEY", "")
ZIP_BASE = "https://www.airnowapi.org/aq/observation/current/ziplatlong/"
LATLON_BASE = ZIP_BASE
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
        try:
            r = await cx.get(base, params=payload)
            r.raise_for_status()
        except httpx.HTTPError as exc:
            # Never propagate a credential-bearing request URL to consumers.
            if isinstance(exc, httpx.HTTPStatusError):
                raise httpx.HTTPStatusError(
                    f"AirNow request failed ({exc.response.status_code})",
                    request=exc.request, response=exc.response,
                ) from None
            raise httpx.RequestError(
                f"AirNow request failed ({type(exc).__name__})", request=exc.request,
            ) from None
        rows = r.json() if r.text.strip() else []
        if not isinstance(rows, list):
            # Provider error envelopes may arrive with HTTP 200. Do not log them.
            raise ValueError("unexpected AirNow response shape")
        observations = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            value = row.get("nowcastAQI")
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            if not math.isfinite(value) or value < 0:
                continue
            observations.append({
                "AQI": value,
                "Category": {"Name": row.get("aqiCategoryName")},
                "ParameterName": "O3" if row.get("parameterName") == "OZONE" else row.get("parameterName"),
            })
        return observations


async def current_by_zip(zip_code: str, distance_miles: int | None = None) -> List[Dict[str, Any]]:
    # Replacement service controls its own search area; retain signature only.
    return await _request(
        ZIP_BASE,
        {
            "zipCode": zip_code,
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
        },
    )
