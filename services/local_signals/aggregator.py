from typing import Dict, Any
from datetime import datetime, timezone
from .cache import latest_and_ref

def _delta(curr, prev):
    try:
        if curr is None or prev is None:
            return None
        return round(float(curr) - float(prev), 1)
    except Exception:
        return None

async def assemble_for_zip(zip_code: str) -> Dict[str, Any]:
    """
    Assemble a compact local-health snapshot for a ZIP.

    Uses the NWS hourly snapshot helper (which also fetches pressure from latest
    station obs when available) + AirNow AQ + moon phase. If a cached snapshot
    ~24h ago exists, compute 24h deltas (temp and pressure) using the cache.
    """
    lat, lon = zip_to_latlon(zip_code)

    # NWS snapshot (temp/humidity/PoP/pressure); values already normalized
    nws_snap = await nws.hourly_by_latlon(lat, lon)

    temp_c = nws_snap.get("temp_c")
    rh_now = nws_snap.get("humidity_pct")
    pop_now = nws_snap.get("precip_prob_pct")
    baro_now = nws_snap.get("pressure_hpa")

    # Try to pull a reference snapshot ~24h ago from cache to compute deltas
    prev_temp = None
    prev_baro = None
    try:
        latest, ref = latest_and_ref(zip_code, ref_hours=24, window_hours=3)
        if ref and isinstance(ref.get("payload"), dict):
            prev_weather = ref["payload"].get("weather") or {}
            prev_temp = prev_weather.get("temp_c")
            prev_baro = prev_weather.get("pressure_hpa")
    except Exception:
        # Soft-fail: deltas remain None if cache is empty or unavailable
        pass

    # Air quality (pick the highest AQI among any pollutants returned)
    aq_list = await airnow.current_by_zip(zip_code)
    aqi = category = pollutant = None
    if aq_list:
        best = max(aq_list, key=lambda a: (a.get("AQI") or 0))
        aqi = best.get("AQI")
        category = (best.get("Category") or {}).get("Name")
        pollutant = best.get("ParameterName")

    # Moon
    m = moon_phase(datetime.now(timezone.utc))

    return {
        "ok": True,
        "where": {"zip": zip_code, "lat": lat, "lon": lon},
        "weather": {
            "temp_c": temp_c,
            "temp_delta_24h_c": _delta(temp_c, prev_temp),
            "humidity_pct": rh_now,
            "precip_prob_pct": pop_now,
            "pressure_hpa": baro_now,
            "baro_delta_24h_hpa": _delta(baro_now, prev_baro),
        },
        "air": {"aqi": aqi, "category": category, "pollutant": pollutant},
        "moon": m,
        "asof": datetime.now(timezone.utc).isoformat(),
    }
