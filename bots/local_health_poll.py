import asyncio
import json
import logging
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from services.db import pg
from services.external import nws
from services.forecast_outlook import build_location_key, summarize_local_forecast_days
from services.geo.zip_lookup import zip_to_latlon
from services.local_signals.aggregator import assemble_for_zip
from services.local_signals.cache import upsert_zip_payload

LOG_LEVEL = os.getenv("GAIA_LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)


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
                condition_code, condition_summary, aqi_forecast, raw, updated_at
            )
            values (
                %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s::jsonb, %s
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

    hourly_payload, grid_payload = await asyncio.gather(
        nws.forecast_hourly_by_latlon(resolved_lat, resolved_lon),
        nws.gridpoints_by_latlon(resolved_lat, resolved_lon),
    )
    rows = summarize_local_forecast_days(
        hourly_payload,
        grid_payload,
        location_key=location_key,
        zip_code=zip_code,
        lat=resolved_lat,
        lon=resolved_lon,
    )
    if not rows:
        return 0
    _upsert_local_forecast_rows(rows)
    return len(rows)


async def main() -> None:
    rows = pg.fetch(
        """
        select distinct zip, lat, lon
          from app.user_locations
         where zip is not null
            or (lat is not null and lon is not null)
        """
    )
    for row in rows:
        zip_code = row.get("zip")
        lat = _safe_float(row.get("lat"))
        lon = _safe_float(row.get("lon"))
        try:
            if zip_code:
                payload = await assemble_for_zip(zip_code)
                upsert_zip_payload(zip_code, payload)
                logger.info("[poll] cached local snapshot zip=%s", zip_code)
            forecast_rows = await _refresh_local_forecast(zip_code, lat, lon)
            if forecast_rows:
                logger.info("[poll] upserted %s local forecast rows for %s", forecast_rows, zip_code or f"{lat},{lon}")
        except Exception as exc:
            logger.exception("[poll] %s failed: %s", zip_code or f"{lat},{lon}", exc)


if __name__ == "__main__":
    asyncio.run(main())
