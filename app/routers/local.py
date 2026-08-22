import asyncio
import os
from datetime import datetime, timedelta

from fastapi import APIRouter, Query

from services.forecast_outlook import ensure_local_forecast_daily_via_pool, serialize_local_forecast_rows
from services.geo.zip_lookup import zip_to_latlon
from services.local_signals.aggregator import assemble_for_zip, ensure_weather_fields
from services.local_signals.cache import latest_for_zip, latest_row, nearest_row_to, upsert_zip_payload

router = APIRouter(prefix="/v1/local", tags=["local"])

LOCAL_FORECAST_ATTACH_TIMEOUT_SECONDS = float(os.getenv("LOCAL_FORECAST_ATTACH_TIMEOUT_SECONDS", "6.0"))


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
    if not isinstance(allergens, dict) or not allergens or not allergens.get("source"):
        return True
    signal_keys = (
        "state",
        "overall_level",
        "overall_index",
        "primary_type",
        "primary_label",
        "tree_level",
        "tree_index",
        "grass_level",
        "grass_index",
        "weed_level",
        "weed_index",
    )
    return not any(allergens.get(key) is not None for key in signal_keys)


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


def _merge_section(primary: dict | None, fallback: dict | None) -> dict:
    merged = dict(fallback) if isinstance(fallback, dict) else {}
    if isinstance(primary, dict):
        merged.update({key: value for key, value in primary.items() if value is not None})
    return merged


def _previous_cached_payload(zip_code: str) -> dict | None:
    try:
        row = latest_row(zip_code)
    except Exception:
        return None
    if not isinstance(row, dict):
        return None
    current_asof = row.get("asof")
    if not isinstance(current_asof, datetime):
        return None

    for minutes_back, window_hours in ((15, 3), (60, 6)):
        try:
            candidate = nearest_row_to(
                zip_code,
                current_asof - timedelta(minutes=minutes_back),
                window_hours=window_hours,
            )
        except Exception:
            continue
        if not isinstance(candidate, dict):
            continue
        candidate_asof = candidate.get("asof")
        payload = candidate.get("payload")
        if candidate_asof == current_asof or not isinstance(payload, dict):
            continue
        return payload
    return None


def _restore_partial_cached_payload(primary: dict, fallback: dict | None) -> tuple[dict, bool]:
    if not isinstance(primary, dict) or not isinstance(fallback, dict):
        return primary, False

    restored = dict(primary)
    changed = False

    if _aqi_missing(primary) and not _aqi_missing(fallback):
        restored["air"] = _merge_section(primary.get("air"), fallback.get("air"))
        changed = True

    if _allergens_missing(primary) and not _allergens_missing(fallback):
        restored["allergens"] = _merge_section(primary.get("allergens"), fallback.get("allergens"))
        changed = True

    if changed:
        primary_health = primary.get("health") if isinstance(primary.get("health"), dict) else {}
        fallback_health = fallback.get("health") if isinstance(fallback.get("health"), dict) else {}
        merged_health = dict(primary_health)
        merged_flags = _merge_section(primary_health.get("flags"), fallback_health.get("flags"))
        if merged_flags:
            merged_health["flags"] = merged_flags
        if not merged_health.get("messages") and isinstance(fallback_health.get("messages"), list):
            merged_health["messages"] = fallback_health["messages"]
        if merged_health:
            restored["health"] = merged_health

    return restored, changed


async def _attach_forecast_daily(conn, zip_code: str, payload: dict) -> dict:
    if not isinstance(payload, dict):
        return payload

    where_info = payload.get("where") if isinstance(payload.get("where"), dict) else {}
    lat = where_info.get("lat")
    lon = where_info.get("lon")
    if zip_code:
        try:
            lat, lon = await asyncio.to_thread(zip_to_latlon, zip_code)
        except Exception:
            pass
    try:
        rows = await ensure_local_forecast_daily(conn, zip_code=zip_code, lat=lat, lon=lon)
    except Exception:
        rows = []
    payload["forecast_daily"] = serialize_local_forecast_rows(rows)
    return payload


async def _attach_forecast_daily_best_effort(
    zip_code: str,
    payload: dict,
    *,
    refresh_if_stale: bool = True,
) -> dict:
    if not isinstance(payload, dict):
        return payload

    where_info = payload.get("where") if isinstance(payload.get("where"), dict) else {}
    lat = where_info.get("lat")
    lon = where_info.get("lon")
    if zip_code:
        try:
            lat, lon = await asyncio.to_thread(zip_to_latlon, zip_code)
        except Exception:
            pass

    try:
        async with asyncio.timeout(LOCAL_FORECAST_ATTACH_TIMEOUT_SECONDS):
            rows = []
            if lat is not None and lon is not None:
                try:
                    rows = await ensure_local_forecast_daily_via_pool(
                        zip_code=zip_code,
                        lat=lat,
                        lon=lon,
                        prefer_geo=True,
                        refresh_if_stale=refresh_if_stale,
                    )
                except Exception:
                    rows = []
            if not rows:
                rows = await ensure_local_forecast_daily_via_pool(
                    zip_code=zip_code,
                    lat=None,
                    lon=None,
                    refresh_if_stale=refresh_if_stale,
                )
            payload["forecast_daily"] = serialize_local_forecast_rows(rows)
            return payload
    except Exception:
        return payload


@router.get("/check")
async def check(zip: str = Query(..., min_length=5, max_length=10)):
    cached = latest_for_zip(zip)
    if cached:
        had_missing = _weather_needs_repair(cached)
        repaired = ensure_weather_fields(zip, cached)
        repaired, restored_sections = _restore_partial_cached_payload(
            repaired,
            _previous_cached_payload(zip) if (_aqi_missing(repaired) or _allergens_missing(repaired)) else None,
        )
        if had_missing or restored_sections:
            upsert_zip_payload(zip, repaired)
        return await _attach_forecast_daily_best_effort(
            zip,
            repaired,
            refresh_if_stale=False,
        )
    payload = await assemble_for_zip(zip)
    payload = ensure_weather_fields(zip, payload)
    upsert_zip_payload(zip, payload)
    return await _attach_forecast_daily_best_effort(zip, payload)
