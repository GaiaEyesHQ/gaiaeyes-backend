from typing import Dict, Any
from datetime import datetime, timezone
from .cache import latest_and_ref, get_previous_approx
from services.geo.zip_lookup import zip_to_latlon
from ..external import nws, airnow
from ..time.moon import moon_phase

def _delta(curr, prev):
    try:
        if curr is None or prev is None:
            return None
        return round(float(curr) - float(prev), 1)
    except Exception:
        return None

def _trend(delta: float | None, tol: float = 1.5) -> str | None:
    """
    Classify short-term change with a tolerance.
    Returns 'rising', 'falling', 'steady', or None if delta is None.
    """
    if delta is None:
        return None
    try:
        d = float(delta)
    except Exception:
        return None
    if d >= tol:
        return "rising"
    if d <= -tol:
        return "falling"
    return "steady"

def _aqi_bucket(aqi: Any, category_name: str | None) -> str | None:
    """
    Map AQI numeric or category name to a bucket: good/moderate/usg/unhealthy/very_unhealthy/hazardous.
    """
    try:
        if aqi is not None:
            n = float(aqi)
            if n <= 50:
                return "good"
            if n <= 100:
                return "moderate"
            if n <= 150:
                return "usg"  # Unhealthy for Sensitive Groups
            if n <= 200:
                return "unhealthy"
            if n <= 300:
                return "very_unhealthy"
            return "hazardous"
    except Exception:
        pass
    if not category_name:
        return None
    name = category_name.lower()
    if "good" in name:
        return "good"
    if "moderate" in name:
        return "moderate"
    if "sensitive" in name or "usg" in name:
        return "usg"
    if "very" in name and "unhealthy" in name:
        return "very_unhealthy"
    if "unhealthy" in name:
        return "unhealthy"
    if "hazard" in name:
        return "hazardous"
    return None

async def assemble_for_zip(zip_code: str) -> Dict[str, Any]:
    """
    Assemble a compact local-health snapshot for a ZIP.

    Uses the NWS hourly snapshot helper (which also fetches pressure from latest
    station obs when available) + AirNow AQ + moon phase. If a cached snapshot
    ~24h ago exists, compute 24h deltas (temp and pressure) using the cache.
    """
    lat, lon = zip_to_latlon(zip_code)

    try:
        nws_snap = await nws.hourly_by_latlon(lat, lon) or {}
    except Exception as e:
        print(f"[local_signals] NWS hourly error for zip={zip_code}: {e}")
        nws_snap = {}

    obs_iso = nws_snap.get("obs_time")

    temp_c = nws_snap.get("temp_c")
    rh_now = nws_snap.get("humidity_pct")
    pop_now = nws_snap.get("precip_prob_pct")
    baro_now = nws_snap.get("pressure_hpa")

    # Prefer NWS-provided deltas (computed from observations); fall back to cache
    temp_delta = nws_snap.get("temp_delta_24h_c")
    baro_delta = nws_snap.get("baro_delta_24h_hpa")

    # Try to pull a reference snapshot ~24h ago from cache to compute deltas
    prev_temp = None
    prev_baro = None
    try:
        latest, ref = latest_and_ref(zip_code, ref_hours=24, window_hours=3)

        # If no ref found in the tight window, fall back to an approximate previous snapshot
        if not ref and latest and isinstance(latest.get("asof"), datetime):
            ref = get_previous_approx(zip_code, latest["asof"], min_hours=18, max_hours=36)

        # Defensive decode in case jsonb comes back as a string in some DB driver paths
        if ref and isinstance(ref.get("payload"), str):
            import json as _json
            ref["payload"] = _json.loads(ref["payload"])

        if ref and isinstance(ref.get("payload"), dict):
            prev_weather = ref["payload"].get("weather") or {}
            prev_temp = prev_weather.get("temp_c")
            prev_baro = prev_weather.get("pressure_hpa")
    except Exception as e:
        # Soft-fail: deltas remain None if cache is empty or unavailable
        print(f"[local_signals] cache ref lookup failed for zip={zip_code}: {e}")

    if temp_delta is None:
        temp_delta = _delta(temp_c, prev_temp)
    if baro_delta is None:
        baro_delta = _delta(baro_now, prev_baro)
    if temp_delta is None and baro_delta is None and (prev_temp is not None or prev_baro is not None):
        print(f"[local_signals] deltas still null zip={zip_code} temp_c={temp_c} prev_temp={prev_temp} baro={baro_now} prev_baro={prev_baro}")

    # Compute ~3h short-term deltas using cache reference
    temp_delta_3h = None
    baro_delta_3h = None
    try:
        _latest3, ref3 = latest_and_ref(zip_code, ref_hours=3, window_hours=2)
        if ref3 and isinstance(ref3.get("payload"), dict):
            prev3_weather = ref3["payload"].get("weather") or {}
            prev3_temp = prev3_weather.get("temp_c")
            prev3_baro = prev3_weather.get("pressure_hpa")
            temp_delta_3h = _delta(temp_c, prev3_temp)
            baro_delta_3h = _delta(baro_now, prev3_baro)
    except Exception:
        pass

    temp_trend_3h = _trend(temp_delta_3h, tol=1.5)  # ≈ ±1.5°C ~ meaningful perceived change
    baro_trend_3h = _trend(baro_delta_3h, tol=1.5)  # ≈ ±1.5 hPa over 3h

    # Air quality (pick the highest AQI among any pollutants returned)
    aq_list = await airnow.current_by_zip(zip_code)
    aqi = category = pollutant = None
    if aq_list:
        best = max(aq_list, key=lambda a: (a.get("AQI") or 0))
        aqi = best.get("AQI")
        category = (best.get("Category") or {}).get("Name")
        pollutant = best.get("ParameterName")

    aqi_flag = _aqi_bucket(aqi, category)

    # Moon
    m = moon_phase(datetime.now(timezone.utc))

    phase_str = (m or {}).get("phase") or ""
    moon_sensitivity = None
    if isinstance(phase_str, str):
        lower = phase_str.lower()
        if "full" in lower:
            moon_sensitivity = "full"
        elif "new" in lower:
            moon_sensitivity = "new"

    # Derived health flags & messages
    flags: Dict[str, Any] = {
        "temp_trend_3h": temp_trend_3h,          # 'rising' | 'falling' | 'steady' | None
        "baro_trend_3h": baro_trend_3h,          # same as above
        "pressure_rapid_drop": (baro_delta_3h is not None and baro_delta_3h <= -3.0),
        "big_temp_shift_24h": (temp_delta is not None and abs(float(temp_delta)) >= 8.0),
        "aqi_flag": aqi_flag,                    # bucket or None
        "moon_sensitivity": moon_sensitivity,    # 'full' | 'new' | None
    }

    messages: list[str] = []
    if flags["pressure_rapid_drop"]:
        messages.append("Pressure falling quickly—headache/migraine risk; hydrate and pace.")
    if flags["big_temp_shift_24h"]:
        messages.append("Sharp 24h temperature swing—sleep & joint flare risk; layer and pre‑hydrate.")
    if aqi_flag in ("usg", "unhealthy", "very_unhealthy", "hazardous"):
        # Show the canonical category if available
        cat_txt = category or aqi_flag.replace("_", " ").title()
        messages.append(f"Air quality {cat_txt}—limit outdoor exertion.")
    if moon_sensitivity == "full":
        messages.append("Full Moon—sleep sensitivity is higher for many; wind down early.")
    elif moon_sensitivity == "new":
        messages.append("New Moon—sleep/wind‑down habits matter; dim evening light.")

    health = {"flags": flags, "messages": messages}

    return {
        "ok": True,
        "where": {"zip": zip_code, "lat": lat, "lon": lon},
        "weather": {
            "temp_c": temp_c,
            "temp_delta_24h_c": temp_delta,
            "humidity_pct": rh_now,
            "precip_prob_pct": pop_now,
            "pressure_hpa": baro_now,
            "obs_time": obs_iso,
            "baro_delta_24h_hpa": baro_delta,
        },
        "air": {"aqi": aqi, "category": category, "pollutant": pollutant},
        "moon": m,
        "health": health,
        "asof": obs_iso or datetime.now(timezone.utc).isoformat(),
    }
