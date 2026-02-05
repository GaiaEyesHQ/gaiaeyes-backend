# services/external/nws.py
import os
from typing import Any, Dict, Optional

import httpx

BASE = "https://api.weather.gov"
WEATHER_UA = os.getenv("WEATHER_UA", "(gaiaeyes.com, gaiaeyes7.83@gmail.com)")
HEADERS = {
    "Accept": "application/geo+json, application/json",
    "User-Agent": WEATHER_UA,
}

def _f_to_c(v: Optional[float]) -> Optional[float]:
    if v is None:
        return None
    return (v - 32.0) * 5.0 / 9.0

async def _get_json(url: str) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=30.0, headers=HEADERS) as cx:
        r = await cx.get(url)
        r.raise_for_status()
        return r.json()

async def _points(lat: float, lon: float) -> Dict[str, Any]:
    return await _get_json(f"{BASE}/points/{lat:.4f},{lon:.4f}")

async def _latest_pressure_hpa(points: Dict[str, Any]) -> Optional[float]:
    """
    Pull pressure from the latest observation:
      Prefer seaLevelPressure.value (Pa), else barometricPressure.value (Pa) → hPa.
      Return None if not available.
    """
    stations_url = points.get("properties", {}).get("observationStations")
    if not stations_url:
        return None

    data = await _get_json(stations_url)
    stations = data.get("features") or []
    if not stations:
        return None

    station_id = stations[0]["properties"]["stationIdentifier"]
    latest = await _get_json(f"{BASE}/stations/{station_id}/observations/latest")
    props = latest.get("properties", {}) or {}

    # Values are in Pascals per NWS; convert to hPa = Pa / 100
    pa = None
    slp = props.get("seaLevelPressure") or {}
    if isinstance(slp, dict) and slp.get("value") is not None:
        pa = slp.get("value")
    if pa is None:
        bp = props.get("barometricPressure") or {}
        if isinstance(bp, dict) and bp.get("value") is not None:
            pa = bp.get("value")

    if pa is None:
        return None
    try:
        return round(float(pa) / 100.0, 1)
    except Exception:
        return None

async def hourly_by_latlon(lat: float, lon: float) -> Dict[str, Optional[float]]:
    """
    Return a compact snapshot for the current hour:
      - temp_c          (float)
      - humidity_pct    (float)
      - precip_prob_pct (float)
      - pressure_hpa    (float)
    """
    pts = await _points(lat, lon)

    # forecastHourly URL is provided by points
    fh_url = pts.get("properties", {}).get("forecastHourly")
    if not fh_url:
        # No hourly URL; try to at least provide pressure
        return {
            "temp_c": None,
            "humidity_pct": None,
            "precip_prob_pct": None,
            "pressure_hpa": await _latest_pressure_hpa(pts),
        }

    fh = await _get_json(fh_url)
    periods = fh.get("properties", {}).get("periods") or []
    p0 = periods[0] if periods else {}

    temp = p0.get("temperature")
    unit = p0.get("temperatureUnit")

    # Convert to °C if needed
    temp_c: Optional[float]
    if temp is None:
        temp_c = None
    elif unit and unit.upper() == "C":
        temp_c = float(temp)
    else:
        temp_c = round(_f_to_c(float(temp)), 1)

    # Relative humidity can appear as {"unitCode":"wmoUnit:percent","value":58}
    rh = p0.get("relativeHumidity") or {}
    humidity_pct = rh.get("value")
    if humidity_pct is not None:
        try:
            humidity_pct = float(humidity_pct)
        except Exception:
            humidity_pct = None

    # PoP: probabilityOfPrecipitation.value
    pop = p0.get("probabilityOfPrecipitation") or {}
    precip_prob_pct = pop.get("value")
    if precip_prob_pct is not None:
        try:
            precip_prob_pct = float(precip_prob_pct)
        except Exception:
            precip_prob_pct = None

    pressure_hpa = await _latest_pressure_hpa(pts)

    return {
        "temp_c": temp_c,
        "humidity_pct": humidity_pct,
        "precip_prob_pct": precip_prob_pct,
        "pressure_hpa": pressure_hpa,
    }