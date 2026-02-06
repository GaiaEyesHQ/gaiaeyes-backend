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


async def _get_json(url: str) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=30.0, headers=HEADERS) as cx:
        r = await cx.get(url)
        r.raise_for_status()
        return r.json()


async def _points(lat: float, lon: float) -> Dict[str, Any]:
    """Return NWS /points doc for the given coordinates."""
    return await _get_json(f"{BASE}/points/{lat:.4f},{lon:.4f}")


async def _gridpoints(pts_or_lat: Any, maybe_lon: Optional[float] = None) -> Dict[str, Any]:
    """
    Get forecast grid data for a /points response, or for lat/lon directly.
    Returns the full grid JSON (we'll read props.* fields from it).
    """
    if isinstance(pts_or_lat, dict):
        pts = pts_or_lat
    else:
        pts = await _points(float(pts_or_lat), float(maybe_lon))

    grid_url = pts.get("properties", {}).get("forecastGridData")
    if not grid_url:
        return {}
    return await _get_json(grid_url)


def _grid_first_value(props: Dict[str, Any], field: str) -> Optional[float]:
    """
    Read the first value from a gridpoints field:
      props[field].values[0].value
    """
    block = props.get(field) or {}
    values = block.get("values") or []
    if not values:
        return None
    val = values[0].get("value")
    if val is None:
        return None
    try:
        return float(val)
    except Exception:
        return None


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


async def _station_pressure_hpa(points: Dict[str, Any]) -> Optional[float]:
    """
    Resolve pressure (hPa) from the nearest station observations.
    Avoids 400s by using only a 'start' param window; then falls back to 'latest'.
    """
    sid = await _nearest_station_id(points)
    if not sid:
        return None

    # Try a recent 6h window using only 'start' (no 'end' → fewer 400s)
    start_iso = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=6)).isoformat()
    try:
        data = await _get_json(f"{BASE}/stations/{sid}/observations?require_qc=true&start={start_iso}")
        feats = data.get("features") or []
        if feats:
            props = feats[-1].get("properties") or {}
            hpa = _extract_pressure_hpa(props)
            if hpa is not None:
                return hpa
    except httpx.HTTPError:
        # ignore and try 'latest' below
        pass

    # Fallback: latest observation (require_qc)
    try:
        latest = await _get_json(f"{BASE}/stations/{sid}/observations/latest?require_qc=true")
        return _extract_pressure_hpa(latest.get("properties") or {})
    except httpx.HTTPError:
        return None


def _parse_obs_props(props: Dict[str, Any]) -> Dict[str, Optional[float | str]]:
    """
    Extract temperature (C), humidity (%), barometric pressure (hPa), and timestamp
    from an observations feature.properties block.
    """
    t = props.get("temperature", {}).get("value")
    rh = props.get("relativeHumidity", {}).get("value")
    pa = props.get("barometricPressure", {}).get("value")
    ts = props.get("timestamp")
    return {
        "temp_c": float(t) if t is not None else None,
        "humidity_pct": float(rh) if rh is not None else None,
        "pressure_hpa": (float(pa) / 100.0) if isinstance(pa, (int, float)) else None,
        "obs_time": ts,
    }


async def _station_latest_conditions(points: Dict[str, Any]) -> Dict[str, Optional[float | str]]:
    """
    Resolve latest **observed** conditions from the nearest station:
      1) /observations/latest?require_qc=true
      2) If missing or stale, /observations?require_qc=true&start=now-6h (no end param).
    Returns: { temp_c, humidity_pct, pressure_hpa, obs_time } (all Optional, obs_time is ISO string)
    """
    sid = await _nearest_station_id(points)
    out: Dict[str, Optional[float | str]] = {
        "temp_c": None,
        "humidity_pct": None,
        "pressure_hpa": None,
        "obs_time": None,
    }
    if not sid:
        return out

    # First try "latest"
    try:
        latest = await _get_json(f"{BASE}/stations/{sid}/observations/latest?require_qc=true")
        cand = _parse_obs_props((latest or {}).get("properties") or {})
        if cand.get("temp_c") is not None or cand.get("humidity_pct") is not None:
            return cand
    except httpx.HTTPError:
        pass

    # Then try a rolling 6h window (no 'end' → avoids 400s)
    start_iso = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=6)).isoformat()
    try:
        data = await _get_json(f"{BASE}/stations/{sid}/observations?require_qc=true&start={start_iso}")
        feats = (data or {}).get("features") or []
        if feats:
            # Pick the last (most recent) feature with usable fields
            for feat in reversed(feats):
                cand = _parse_obs_props((feat or {}).get("properties") or {})
                if cand.get("temp_c") is not None or cand.get("humidity_pct") is not None:
                    return cand
    except httpx.HTTPError:
        pass

    return out


async def _forecast_hourly_snapshot(points: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """
    Fallback to forecastHourly for temp/humidity/PoP when gridpoints are unavailable.
    """
    out: Dict[str, Optional[float]] = {
        "temp_c": None,
        "humidity_pct": None,
        "precip_prob_pct": None,
    }
    fh_url = points.get("properties", {}).get("forecastHourly")
    if not fh_url:
        return out

    try:
        fh = await _get_json(fh_url)
        periods = fh.get("properties", {}).get("periods") or []
        p0 = periods[0] if periods else {}

        # temperature can be C or F depending on the office; convert if needed
        temp = p0.get("temperature")
        unit = (p0.get("temperatureUnit") or "").upper()
        if temp is not None:
            t = float(temp)
            out["temp_c"] = t if unit == "C" else round((t - 32.0) * 5.0 / 9.0, 1)

        rh = p0.get("relativeHumidity") or {}
        if rh.get("value") is not None:
            out["humidity_pct"] = float(rh["value"])

        pop = p0.get("probabilityOfPrecipitation") or {}
        if pop.get("value") is not None:
            out["precip_prob_pct"] = float(pop["value"])
    except httpx.HTTPError:
        pass

    return out


async def hourly_by_latlon(lat: float, lon: float) -> Dict[str, Optional[float | str]]:
    """
    Return a compact snapshot for "now" (station-observed first, then grid/forecast fallbacks):
      - temp_c              (float, prefer station observations; fallback gridpoints/forecastHourly)
      - humidity_pct        (float, prefer station observations; fallback gridpoints/forecastHourly)
      - precip_prob_pct     (float, from gridpoints.probabilityOfPrecipitation; fallback forecastHourly)
      - pressure_hpa        (float, prefer station observations; fallback gridpoints/forecastHourly, then station-only)
      - obs_time            (ISO string; observation timestamp if available, else grid/forecast start time or now)
      - temp_delta_24h_c    (None; computed by aggregator cache when prior snapshot exists)
      - baro_delta_24h_hpa  (None; computed by aggregator cache when prior snapshot exists)
    """
    pts = await _points(lat, lon)

    # 1) Try latest station observations for "now"
    obs = await _station_latest_conditions(pts)
    temp_c = obs.get("temp_c")
    humidity_pct = obs.get("humidity_pct")
    pressure_hpa = obs.get("pressure_hpa")
    obs_time = obs.get("obs_time")  # may be None

    precip_prob_pct: Optional[float] = None

    # 2) Gridpoints fallbacks for missing fields (and PoP always comes from grid/forecast)
    try:
        grid = await _gridpoints(pts)
        gprops = grid.get("properties", {}) if grid else {}

        if temp_c is None:
            temp_c = _grid_first_value(gprops, "temperature")
        if humidity_pct is None:
            humidity_pct = _grid_first_value(gprops, "relativeHumidity")
        if precip_prob_pct is None:
            precip_prob_pct = _grid_first_value(gprops, "probabilityOfPrecipitation")
        if pressure_hpa is None:
            pressure_pa = _grid_first_value(gprops, "barometricPressure")
            if pressure_pa is not None:
                pressure_hpa = round(pressure_pa / 100.0, 1)
    except httpx.HTTPError:
        pass

    # 3) Forecast hourly fallback (for anything still missing and for a timestamp if needed)
    if temp_c is None or humidity_pct is None or precip_prob_pct is None or obs_time is None:
        fh = await _forecast_hourly_snapshot(pts)
        if temp_c is None:
            temp_c = fh.get("temp_c")
        if humidity_pct is None:
            humidity_pct = fh.get("humidity_pct")
        if precip_prob_pct is None:
            precip_prob_pct = fh.get("precip_prob_pct")
        # Use forecast start time as a weak "asof" if we still lack an observation time
        if obs_time is None:
            # We don't have the precise forecast start on-hand, so approximate with now (UTC)
            obs_time = dt.datetime.now(dt.timezone.utc).isoformat()

    return {
        "temp_c": temp_c,
        "humidity_pct": humidity_pct,
        "precip_prob_pct": precip_prob_pct,
        "pressure_hpa": pressure_hpa,
        "obs_time": obs_time,
        # Leave deltas None; aggregator cache will compute when prior snapshot exists
        "temp_delta_24h_c": None,
        "baro_delta_24h_hpa": None,
    }