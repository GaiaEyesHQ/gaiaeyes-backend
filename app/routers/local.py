import asyncio

from fastapi import APIRouter, Query

from app.db import get_pool
from services.forecast_outlook import ensure_local_forecast_daily, serialize_local_forecast_rows
from services.local_signals.aggregator import assemble_for_zip, ensure_weather_fields
from services.local_signals.cache import latest_for_zip, upsert_zip_payload

router = APIRouter(prefix="/v1/local", tags=["local"])


def _weather_needs_repair(payload: dict) -> bool:
    weather = payload.get("weather") if isinstance(payload, dict) else {}
    return not isinstance(weather, dict) or any(
        weather.get(key) is None
        for key in ("temp_delta_24h_c", "baro_delta_24h_hpa", "baro_trend")
    )


def _aqi_missing(payload: dict) -> bool:
    air = payload.get("air") if isinstance(payload, dict) else {}
    return not isinstance(air, dict) or air.get("aqi") is None


def _allergens_missing(payload: dict) -> bool:
    allergens = payload.get("allergens") if isinstance(payload, dict) else {}
    return not isinstance(allergens, dict) or not allergens or not allergens.get("source")


def _merge_payload(primary: dict, fallback: dict) -> dict:
    merged = dict(fallback) if isinstance(fallback, dict) else {}
    if not isinstance(primary, dict):
        return merged
    for key, value in primary.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            section = dict(merged[key])
            section.update({item_key: item_value for item_key, item_value in value.items() if item_value is not None})
            merged[key] = section
        elif value is not None:
            merged[key] = value
        elif key not in merged:
            merged[key] = value
    return merged


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


async def _attach_forecast_daily_best_effort(zip_code: str, payload: dict) -> dict:
    if not isinstance(payload, dict):
        return payload

    try:
        pool = await get_pool()
        async with asyncio.timeout(1.5):
            async with pool.connection() as conn:
                return await _attach_forecast_daily(conn, zip_code, payload)
    except Exception:
        return payload


@router.get("/check")
async def check(zip: str = Query(..., min_length=5, max_length=10)):
    cached = latest_for_zip(zip)
    if cached:
        had_missing = _weather_needs_repair(cached)
        repaired = ensure_weather_fields(zip, cached)
        if _aqi_missing(repaired) or _allergens_missing(repaired):
            try:
                refreshed = ensure_weather_fields(zip, await assemble_for_zip(zip))
                repaired = _merge_payload(refreshed, repaired)
            except Exception:
                pass
            upsert_zip_payload(zip, repaired)
        elif had_missing:
            upsert_zip_payload(zip, repaired)
        return await _attach_forecast_daily_best_effort(zip, repaired)
    payload = await assemble_for_zip(zip)
    payload = ensure_weather_fields(zip, payload)
    upsert_zip_payload(zip, payload)
    return await _attach_forecast_daily_best_effort(zip, payload)
