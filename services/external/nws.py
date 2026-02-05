# services/external/nws.py
import os
import datetime as dt
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


# --- Helper functions for observations deltas and extraction ---

async def _nearest_station_id(points: Dict[str, Any]) -> Optional[str]:
    """
    From a /points response, resolve the nearest observation station id (e.g., 'KSAT').
    """
    stations_url = points.get("properties", {}).get("observationStations")
    if not stations_url:
        return None
    data = await _get_json(stations_url)
    stations = data.get("features") or []
    if not stations:
        return None
    return stations[0]["properties"]["stationIdentifier"]

def _extract_pressure_hpa(props: Dict[str, Any]) -> Optional[float]:
    """
    Prefer seaLevelPressure.value (Pa), else barometricPressure.value (Pa) → hPa.
    """
    pa = None
    slp = props.get("seaLevelPressure") or {}
    if isinstance(slp, dict) and slp.get("value") is not None:
        pa = slp.get("value")
    if pa is None:
        bp = props.get("barometricPressure") or {}
        if isinstance(bp, dict) and bp.get("value") is not None:
            pa = bp.get("value")
    if isinstance(pa, (int, float)):
        try:
            return round(float(pa) / 100.0, 1)
        except Exception:
            return None
    return None

def _extract_temp_c_from_obs(props: Dict[str, Any]) -> Optional[float]:
    """
    Extract temperature in °C from an observations properties block.
    NWS observations often expose 'temperature.value' (degC);
    fall back to 'airTemperature.value' if present.
    """
    t = None
    t_block = props.get("temperature") or {}
    if isinstance(t_block, dict) and t_block.get("value") is not None:
        t = t_block.get("value")
    if t is None:
        at = props.get("airTemperature") or {}
        if isinstance(at, dict) and at.get("value") is not None:
            t = at.get("value")
    if isinstance(t, (int, float)):
        try:
            return float(t)
        except Exception:
            return None
    return None

async def _latest_obs_props(station_id: str) -> Dict[str, Any]:
    """
    Return properties of the latest observation for a station (require_qc).
    """
    data = await _get_json(f"{BASE}/stations/{station_id}/observations/latest?require_qc=true")
    return data.get("properties") or {}

async def _obs_props_in_window(station_id: str, start_iso: str, end_iso: str) -> Optional[Dict[str, Any]]:
    """
    Return the last good observation properties within [start, end].
    """
    data = await _get_json(f"{BASE}/stations/{station_id}/observations?require_qc=true&start={start_iso}&end={end_iso}")
    feats = data.get("features") or []
    if not feats:
        return None
    # choose the most recent in the window
    props = feats[-1].get("properties") or {}
    return props

async def _pressure_snapshot(points: Dict[str, Any]) -> (Optional[float], Optional[float]):
    """
    Returns (pressure_hpa_now, baro_delta_24h_hpa).
    Delta is current minus ~24h-ago in a 22–26h window for resilience.
    """
    sid = await _nearest_station_id(points)
    if not sid:
        return None, None
    latest = await _latest_obs_props(sid)
    now_hpa = _extract_pressure_hpa(latest)
    ts_iso = latest.get("timestamp")
    if now_hpa is None:
        return None, None

    # derive a window around 24h ago
    if ts_iso:
        now_dt = dt.datetime.fromisoformat(ts_iso.replace("Z", "+00:00"))
    else:
        now_dt = dt.datetime.now(dt.timezone.utc)
    start = (now_dt - dt.timedelta(hours=26)).isoformat()
    end = (now_dt - dt.timedelta(hours=22)).isoformat()
    past = await _obs_props_in_window(sid, start, end)
    if not past:
        return now_hpa, None
    past_hpa = _extract_pressure_hpa(past)
    delta = round(now_hpa - past_hpa, 1) if past_hpa is not None else None
    return now_hpa, delta

async def _temp_delta_24h(points: Dict[str, Any]) -> Optional[float]:
    """
    Returns temperature delta over ~24h (current - 24h-ago) in °C using observations.
    """
    sid = await _nearest_station_id(points)
    if not sid:
        return None
    latest = await _latest_obs_props(sid)
    now_c = _extract_temp_c_from_obs(latest)
    ts_iso = latest.get("timestamp")
    if now_c is None:
        return None

    if ts_iso:
        now_dt = dt.datetime.fromisoformat(ts_iso.replace("Z", "+00:00"))
    else:
        now_dt = dt.datetime.now(dt.timezone.utc)
    start = (now_dt - dt.timedelta(hours=26)).isoformat()
    end = (now_dt - dt.timedelta(hours=22)).isoformat()
    past = await _obs_props_in_window(sid, start, end)
    if not past:
        return None
    past_c = _extract_temp_c_from_obs(past)
    if past_c is None:
        return None
    return round(now_c - past_c, 1)

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
      - temp_delta_24h_c      (float)
      - baro_delta_24h_hpa    (float)
    """
    pts = await _points(lat, lon)

    # forecastHourly URL is provided by points
    fh_url = pts.get("properties", {}).get("forecastHourly")
    if not fh_url:
        # No hourly URL; try to at least provide pressure and deltas
        pressure_hpa = await _latest_pressure_hpa(pts)
        # Add observational deltas
        pressure_now_hpa, baro_delta_24h_hpa = await _pressure_snapshot(pts)
        if pressure_now_hpa is not None:
            pressure_hpa = pressure_now_hpa  # prefer observations result if present
        temp_delta_24h_c = await _temp_delta_24h(pts)
        return {
            "temp_c": None,
            "humidity_pct": None,
            "precip_prob_pct": None,
            "pressure_hpa": pressure_hpa,
            "temp_delta_24h_c": temp_delta_24h_c,
            "baro_delta_24h_hpa": baro_delta_24h_hpa,
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

    # Add observational deltas
    pressure_now_hpa, baro_delta_24h_hpa = await _pressure_snapshot(pts)
    if pressure_now_hpa is not None:
        pressure_hpa = pressure_now_hpa  # prefer observations result if present
    temp_delta_24h_c = await _temp_delta_24h(pts)

    return {
        "temp_c": temp_c,
        "humidity_pct": humidity_pct,
        "precip_prob_pct": precip_prob_pct,
        "pressure_hpa": pressure_hpa,
        "temp_delta_24h_c": temp_delta_24h_c,
        "baro_delta_24h_hpa": baro_delta_24h_hpa,
    }