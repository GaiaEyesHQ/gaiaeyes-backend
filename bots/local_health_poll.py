import asyncio
import argparse
import json
import logging
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from services.db import pg
from services.external import nws, pollen
from services.forecast_outlook import (
    LOCAL_FORECAST_DAYS,
    POLLEN_FORECAST_DAYS,
    build_location_key,
    summarize_local_forecast_days,
)
from services.geo.zip_lookup import zip_to_latlon
from services.local_signals.aggregator import assemble_for_zip
from services.local_signals.cache import upsert_zip_payload

LOG_LEVEL = os.getenv("GAIA_LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)
# httpx logs full request URLs at INFO, including provider API-key query params.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


def _safe_float(value):
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _upsert_local_forecast_rows(rows: list[dict]) -> None:
    for row in rows:
        payload = dict(row)
        raw = payload.get("raw")
        if isinstance(raw, dict):
            raw = json.dumps(raw)
        payload["raw"] = raw or "{}"
        pg.execute(
            """
            insert into marts.local_forecast_daily (
                location_key, day, source, issued_at, location_zip, lat, lon,
                temp_high_c, temp_low_c, temp_delta_from_prior_day_c,
                pressure_hpa, pressure_delta_from_prior_day_hpa,
                humidity_avg, precip_probability, wind_speed, wind_gust,
                condition_code, condition_summary, aqi_forecast,
                pollen_tree_level, pollen_grass_level, pollen_weed_level, pollen_mold_level,
                pollen_overall_level, pollen_primary_type, pollen_source, pollen_updated_at,
                pollen_tree_index, pollen_grass_index, pollen_weed_index, pollen_mold_index, pollen_overall_index,
                raw, updated_at
            )
            values (
                %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s::jsonb, %s
            )
            on conflict (location_key, day) do update
            set source = excluded.source,
                issued_at = excluded.issued_at,
                location_zip = excluded.location_zip,
                lat = excluded.lat,
                lon = excluded.lon,
                temp_high_c = excluded.temp_high_c,
                temp_low_c = excluded.temp_low_c,
                temp_delta_from_prior_day_c = excluded.temp_delta_from_prior_day_c,
                pressure_hpa = excluded.pressure_hpa,
                pressure_delta_from_prior_day_hpa = excluded.pressure_delta_from_prior_day_hpa,
                humidity_avg = excluded.humidity_avg,
                precip_probability = excluded.precip_probability,
                wind_speed = excluded.wind_speed,
                wind_gust = excluded.wind_gust,
                condition_code = excluded.condition_code,
                condition_summary = excluded.condition_summary,
                aqi_forecast = excluded.aqi_forecast,
                pollen_tree_level = excluded.pollen_tree_level,
                pollen_grass_level = excluded.pollen_grass_level,
                pollen_weed_level = excluded.pollen_weed_level,
                pollen_mold_level = excluded.pollen_mold_level,
                pollen_overall_level = excluded.pollen_overall_level,
                pollen_primary_type = excluded.pollen_primary_type,
                pollen_source = excluded.pollen_source,
                pollen_updated_at = excluded.pollen_updated_at,
                pollen_tree_index = excluded.pollen_tree_index,
                pollen_grass_index = excluded.pollen_grass_index,
                pollen_weed_index = excluded.pollen_weed_index,
                pollen_mold_index = excluded.pollen_mold_index,
                pollen_overall_index = excluded.pollen_overall_index,
                raw = excluded.raw,
                updated_at = excluded.updated_at
            """,
            payload.get("location_key"),
            payload.get("day"),
            payload.get("source"),
            payload.get("issued_at"),
            payload.get("location_zip"),
            payload.get("lat"),
            payload.get("lon"),
            payload.get("temp_high_c"),
            payload.get("temp_low_c"),
            payload.get("temp_delta_from_prior_day_c"),
            payload.get("pressure_hpa"),
            payload.get("pressure_delta_from_prior_day_hpa"),
            payload.get("humidity_avg"),
            payload.get("precip_probability"),
            payload.get("wind_speed"),
            payload.get("wind_gust"),
            payload.get("condition_code"),
            payload.get("condition_summary"),
            payload.get("aqi_forecast"),
            payload.get("pollen_tree_level"),
            payload.get("pollen_grass_level"),
            payload.get("pollen_weed_level"),
            payload.get("pollen_mold_level"),
            payload.get("pollen_overall_level"),
            payload.get("pollen_primary_type"),
            payload.get("pollen_source"),
            payload.get("pollen_updated_at"),
            payload.get("pollen_tree_index"),
            payload.get("pollen_grass_index"),
            payload.get("pollen_weed_index"),
            payload.get("pollen_mold_index"),
            payload.get("pollen_overall_index"),
            payload.get("raw"),
            payload.get("updated_at"),
        )


async def _refresh_local_forecast(zip_code: str | None, lat: float | None, lon: float | None) -> int:
    resolved_lat = _safe_float(lat)
    resolved_lon = _safe_float(lon)
    if (resolved_lat is None or resolved_lon is None) and zip_code:
        try:
            resolved_lat, resolved_lon = zip_to_latlon(zip_code)
        except Exception as exc:
            logger.warning("[poll] forecast coords unavailable zip=%s error=%s", zip_code, exc)
            return 0
    if resolved_lat is None or resolved_lon is None:
        return 0

    location_key = build_location_key(zip_code, resolved_lat, resolved_lon)
    if not location_key:
        return 0

    hourly_payload, grid_payload, allergen_payload = await asyncio.gather(
        nws.forecast_hourly_by_latlon(resolved_lat, resolved_lon),
        nws.gridpoints_by_latlon(resolved_lat, resolved_lon),
        pollen.forecast_by_latlon(resolved_lat, resolved_lon, days=POLLEN_FORECAST_DAYS),
    )
    rows = summarize_local_forecast_days(
        hourly_payload,
        grid_payload,
        allergen_payload=allergen_payload,
        location_key=location_key,
        zip_code=zip_code,
        lat=resolved_lat,
        lon=resolved_lon,
        max_days=LOCAL_FORECAST_DAYS,
    )
    if not rows:
        return 0
    _upsert_local_forecast_rows(rows)
    return len(rows)


def _dedupe_locations(rows: list[dict]) -> list[dict]:
    unique: dict[tuple, dict] = {}
    for row in rows:
        zip_code = str(row.get("zip") or "").strip()
        if zip_code:
            key = ("zip", zip_code)
        else:
            lat = _safe_float(row.get("lat"))
            lon = _safe_float(row.get("lon"))
            key = ("coords", round(lat, 4) if lat is not None else None, round(lon, 4) if lon is not None else None)
        unique.setdefault(key, row)
    return list(unique.values())


async def run(mode: str = "both") -> dict[str, int]:
    if mode not in {"current", "forecast", "both"}:
        raise ValueError(f"unsupported local poll mode: {mode}")

    rows = pg.fetch(
        """
        select distinct zip, lat, lon
          from app.user_locations
         where zip is not null
            or (lat is not null and lon is not null)
        """
    )
    rows = _dedupe_locations(rows)
    stats = {
        "locations": len(rows),
        "current_updated": 0,
        "forecast_updated": 0,
        "failures": 0,
    }
    for row in rows:
        zip_code = row.get("zip")
        lat = _safe_float(row.get("lat"))
        lon = _safe_float(row.get("lon"))
        try:
            if mode in {"current", "both"} and zip_code:
                payload = await assemble_for_zip(zip_code)
                upsert_zip_payload(zip_code, payload)
                stats["current_updated"] += 1
                logger.info("[poll] cached local snapshot zip=%s", zip_code)
            if mode in {"forecast", "both"}:
                forecast_rows = await _refresh_local_forecast(zip_code, lat, lon)
                stats["forecast_updated"] += forecast_rows
                if forecast_rows:
                    logger.info("[poll] upserted %s local forecast rows for %s", forecast_rows, zip_code or f"{lat},{lon}")
        except Exception as exc:
            stats["failures"] += 1
            logger.exception("[poll] %s failed: %s", zip_code or f"{lat},{lon}", exc)

    logger.info("[poll] done mode=%s stats=%s", mode, stats)
    if stats["failures"]:
        raise RuntimeError(f"local poll completed with {stats['failures']} location failure(s)")
    return stats


async def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh Gaia Eyes local conditions and forecasts.")
    parser.add_argument(
        "--mode",
        choices=("current", "forecast", "both"),
        default="both",
        help="Refresh current conditions, multi-day forecast, or both (default).",
    )
    args = parser.parse_args()
    await run(args.mode)


if __name__ == "__main__":
    asyncio.run(main())
