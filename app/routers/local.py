from fastapi import APIRouter, Depends, Query

from app.db import get_db
from services.forecast_outlook import ensure_local_forecast_daily, serialize_local_forecast_rows
from services.local_signals.aggregator import assemble_for_zip, ensure_weather_fields
from services.local_signals.cache import latest_for_zip, upsert_zip_payload

router = APIRouter(prefix="/v1/local", tags=["local"])


async def _attach_forecast_daily(conn, zip_code: str, payload: dict) -> dict:
    if not isinstance(payload, dict):
        return payload

    where_info = payload.get("where") if isinstance(payload.get("where"), dict) else {}
    lat = where_info.get("lat")
    lon = where_info.get("lon")
    try:
        rows = await ensure_local_forecast_daily(conn, zip_code=zip_code, lat=lat, lon=lon)
    except Exception:
        rows = []
    payload["forecast_daily"] = serialize_local_forecast_rows(rows)
    return payload


@router.get("/check")
async def check(zip: str = Query(..., min_length=5, max_length=10), conn=Depends(get_db)):
    cached = latest_for_zip(zip)
    if cached:
        weather = cached.get("weather") if isinstance(cached, dict) else {}
        had_missing = not isinstance(weather, dict) or any(
            weather.get(key) is None
            for key in ("temp_delta_24h_c", "baro_delta_24h_hpa", "baro_trend")
        )
        repaired = ensure_weather_fields(zip, cached)
        if had_missing:
            upsert_zip_payload(zip, repaired)
        return await _attach_forecast_daily(conn, zip, repaired)
    payload = await assemble_for_zip(zip)
    payload = ensure_weather_fields(zip, payload)
    upsert_zip_payload(zip, payload)
    return await _attach_forecast_daily(conn, zip, payload)
