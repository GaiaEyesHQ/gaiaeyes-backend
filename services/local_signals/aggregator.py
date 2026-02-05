from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from ..external import airnow, nws
from ..geo.zip_lookup import zip_to_latlon
from ..time.moon import moon_phase


def _delta(v_now: Optional[float], v_then: Optional[float]) -> Optional[float]:
    if v_now is None or v_then is None:
        return None
    return round(v_now - v_then, 2)


def _first_float(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)):
        return float(value)
    return None


async def assemble_for_zip(zip_code: str) -> Dict[str, Any]:
    lat, lon = zip_to_latlon(zip_code)
    p = await nws.points(lat, lon)
    props = p.get("properties", {})
    grid_id = props.get("gridId")
    grid_x = props.get("gridX")
    grid_y = props.get("gridY")

    hourly = await nws.grid_hourly(grid_id, grid_x, grid_y)
    periods = hourly.get("properties", {}).get("periods", [])
    now = periods[0] if periods else {}
    then_target = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()[:13]
    then = next(
        (pd for pd in periods if pd.get("startTime", "")[:13] == then_target),
        None,
    )

    def _t(pd):
        return _first_float(pd.get("temperature"))

    def _u(pd):
        return _first_float(pd.get("relativeHumidity", {}).get("value"))

    def _p(pd):
        return _first_float(pd.get("probabilityOfPrecipitation", {}).get("value"))

    temp_now = _t(now)
    temp_then = _t(then) if then else None
    rh_now = _u(now)
    pop_now = _p(now)

    baro_now = None
    baro_then = None

    aq_list = await airnow.current_by_zip(zip_code)
    aqi = category = pollutant = None
    if aq_list:
        best = max(aq_list, key=lambda a: a.get("AQI", 0) or 0)
        aqi = best.get("AQI")
        category = (best.get("Category") or {}).get("Name")
        pollutant = best.get("ParameterName")

    moon = moon_phase(datetime.now(timezone.utc))

    temp_c = round((temp_now - 32) * 5 / 9, 1) if temp_now is not None else None
    temp_then_c = round((temp_then - 32) * 5 / 9, 1) if temp_then is not None else None

    return {
        "ok": True,
        "where": {"zip": zip_code, "lat": lat, "lon": lon},
        "weather": {
            "temp_c": temp_c,
            "temp_delta_24h_c": _delta(temp_c, temp_then_c),
            "humidity_pct": rh_now,
            "precip_prob_pct": pop_now,
            "pressure_hpa": baro_now,
            "baro_delta_24h_hpa": _delta(baro_now, baro_then),
        },
        "air": {"aqi": aqi, "category": category, "pollutant": pollutant},
        "moon": moon,
        "asof": datetime.now(timezone.utc).isoformat(),
    }
