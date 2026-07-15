from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Iterable, Mapping

import httpx
import psycopg
from psycopg.rows import dict_row

from services.external.pollen import current_snapshot

from .regions import RegionAnchor


OPENWEATHER_CURRENT_URL = "https://api.openweathermap.org/data/2.5/weather"
OPENWEATHER_AIR_URL = "https://api.openweathermap.org/data/2.5/air_pollution"
GOOGLE_POLLEN_URL = "https://pollen.googleapis.com/v1/forecast:lookup"


def _jsonable(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _safe_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


async def _get_json(client: httpx.AsyncClient, url: str, params: dict[str, Any]) -> dict[str, Any]:
    response = await client.get(url, params=params)
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, dict) else {}


async def collect_anchor_observation(
    client: httpx.AsyncClient,
    anchor: RegionAnchor,
    *,
    openweather_key: str,
    pollen_key: str = "",
    previous: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    weather_task = _get_json(
        client,
        OPENWEATHER_CURRENT_URL,
        {"lat": anchor.lat, "lon": anchor.lon, "units": "metric", "appid": openweather_key},
    )
    air_task = _get_json(
        client,
        OPENWEATHER_AIR_URL,
        {"lat": anchor.lat, "lon": anchor.lon, "appid": openweather_key},
    )
    tasks: list[Any] = [weather_task, air_task]
    if pollen_key:
        tasks.append(
            _get_json(
                client,
                GOOGLE_POLLEN_URL,
                {
                    "location.latitude": anchor.lat,
                    "location.longitude": anchor.lon,
                    "days": 1,
                    "plantsDescription": "false",
                    "key": pollen_key,
                },
            )
        )
    results = await asyncio.gather(*tasks, return_exceptions=True)
    weather_raw = results[0] if isinstance(results[0], dict) else {}
    air_raw = results[1] if isinstance(results[1], dict) else {}
    pollen_raw = results[2] if len(results) > 2 and isinstance(results[2], dict) else {}

    main = weather_raw.get("main") if isinstance(weather_raw.get("main"), dict) else {}
    wind = weather_raw.get("wind") if isinstance(weather_raw.get("wind"), dict) else {}
    weather_items = weather_raw.get("weather") if isinstance(weather_raw.get("weather"), list) else []
    weather_item = weather_items[0] if weather_items and isinstance(weather_items[0], dict) else {}
    rain = weather_raw.get("rain") if isinstance(weather_raw.get("rain"), dict) else {}
    snow = weather_raw.get("snow") if isinstance(weather_raw.get("snow"), dict) else {}
    air_items = air_raw.get("list") if isinstance(air_raw.get("list"), list) else []
    air_item = air_items[0] if air_items and isinstance(air_items[0], dict) else {}
    air_main = air_item.get("main") if isinstance(air_item.get("main"), dict) else {}
    components = air_item.get("components") if isinstance(air_item.get("components"), dict) else {}
    pollen = current_snapshot(pollen_raw)
    prior_weather = (previous or {}).get("weather") if isinstance((previous or {}).get("weather"), Mapping) else {}

    temp_c = _safe_float(main.get("temp"))
    pressure_hpa = _safe_float(main.get("pressure"))
    prior_temp = _safe_float(prior_weather.get("temp_c"))
    prior_pressure = _safe_float(prior_weather.get("pressure_hpa"))
    observed_at = datetime.fromtimestamp(
        int(weather_raw.get("dt") or datetime.now(timezone.utc).timestamp()),
        tz=timezone.utc,
    )

    return {
        "anchor_id": anchor.anchor_id,
        "region_key": anchor.region_key,
        "region_label": anchor.region_label,
        "macro_region": anchor.macro_region,
        "location_label": anchor.location_label,
        "lat": anchor.lat,
        "lon": anchor.lon,
        "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
        "weather": {
            "temp_c": temp_c,
            "feels_like_c": _safe_float(main.get("feels_like")),
            "temp_delta_24h_c": round(temp_c - prior_temp, 1) if temp_c is not None and prior_temp is not None else None,
            "pressure_hpa": pressure_hpa,
            "pressure_delta_24h_hpa": round(pressure_hpa - prior_pressure, 1) if pressure_hpa is not None and prior_pressure is not None else None,
            "humidity_pct": _safe_float(main.get("humidity")),
            "wind_speed_mps": _safe_float(wind.get("speed")),
            "wind_gust_mps": _safe_float(wind.get("gust")),
            "condition_code": weather_item.get("id"),
            "condition": weather_item.get("main"),
            "condition_summary": weather_item.get("description"),
            "rain_1h_mm": _safe_float(rain.get("1h")),
            "snow_1h_mm": _safe_float(snow.get("1h")),
        },
        "air": {
            "openweather_aqi": air_main.get("aqi"),
            "pm2_5": _safe_float(components.get("pm2_5")),
            "pm10": _safe_float(components.get("pm10")),
            "o3": _safe_float(components.get("o3")),
        },
        "pollen": pollen,
        "provider_status": {
            "weather": bool(weather_raw),
            "air": bool(air_raw),
            "pollen": bool(pollen_raw) if pollen_key else None,
        },
    }


async def collect_anchor_observations(
    anchors: Iterable[RegionAnchor],
    *,
    openweather_key: str,
    pollen_key: str = "",
    previous_by_anchor: Mapping[str, Mapping[str, Any]] | None = None,
    concurrency: int = 8,
) -> list[dict[str, Any]]:
    if not openweather_key:
        raise RuntimeError("OPENWEATHER_API_KEY is required for public regional sampling")
    semaphore = asyncio.Semaphore(max(1, concurrency))
    previous_by_anchor = previous_by_anchor or {}

    async with httpx.AsyncClient(timeout=30.0) as client:
        async def collect(anchor: RegionAnchor) -> dict[str, Any]:
            async with semaphore:
                try:
                    return await collect_anchor_observation(
                        client,
                        anchor,
                        openweather_key=openweather_key,
                        pollen_key=pollen_key,
                        previous=previous_by_anchor.get(anchor.anchor_id),
                    )
                except Exception as exc:
                    return {
                        "anchor_id": anchor.anchor_id,
                        "region_key": anchor.region_key,
                        "region_label": anchor.region_label,
                        "macro_region": anchor.macro_region,
                        "location_label": anchor.location_label,
                        "lat": anchor.lat,
                        "lon": anchor.lon,
                        "error": str(exc),
                        "provider_status": {
                            "weather": False,
                            "air": False,
                            "pollen": False if pollen_key else None,
                        },
                    }

        return await asyncio.gather(*(collect(anchor) for anchor in anchors))


def _fetch_one(conn: psycopg.Connection, queries: tuple[str, ...]) -> dict[str, Any]:
    for query in queries:
        try:
            with conn.cursor() as cursor:
                cursor.execute(query)
                row = cursor.fetchone()
                if row:
                    return _jsonable(dict(row))
        except Exception:
            continue
    return {}


def _fetch_all(conn: psycopg.Connection, query: str) -> list[dict[str, Any]]:
    try:
        with conn.cursor() as cursor:
            cursor.execute(query)
            return [_jsonable(dict(row)) for row in cursor.fetchall()]
    except Exception:
        return []


def _schumann_harmonics_available(row: Mapping[str, Any] | None) -> bool:
    return bool(row) and any(row.get(key) is not None for key in ("f0", "f1", "f2", "f3", "f4", "f5"))


def _fetch_schumann_context(conn: psycopg.Connection) -> dict[str, Any]:
    v2 = _fetch_one(
        conn,
        (
            """
            select day, generated_at, f0, f1, f2, f3, f4, f5, combined_f1,
                   'marts.schumann_daily_v2' as source
            from marts.schumann_daily_v2
            where coalesce(f0, f1, f2, f3, f4, f5) is not null
            order by day desc
            limit 1
            """,
        ),
    )
    if _schumann_harmonics_available(v2):
        return v2

    daily = _fetch_one(
        conn,
        (
            """
            select day,
                   (day::timestamp at time zone 'UTC') as generated_at,
                   avg(f0_avg_hz)::float as f0,
                   avg(f1_avg_hz)::float as f1,
                   avg(f2_avg_hz)::float as f2,
                   avg(f3_avg_hz)::float as f3,
                   avg(f4_avg_hz)::float as f4,
                   avg(f5_avg_hz)::float as f5,
                   null::float as combined_f1,
                   array_agg(station_id order by station_id) as stations_used,
                   'marts.schumann_daily' as source
            from marts.schumann_daily
            where coalesce(f0_avg_hz, f1_avg_hz, f2_avg_hz, f3_avg_hz, f4_avg_hz, f5_avg_hz) is not null
            group by day
            order by day desc
            limit 1
            """,
        ),
    )
    return daily if _schumann_harmonics_available(daily) else {}


def collect_existing_public_context(db_url: str) -> dict[str, Any]:
    with psycopg.connect(db_url, row_factory=dict_row, autocommit=True) as conn:
        space = _fetch_one(
            conn,
            (
                """
                select * from marts.space_weather_daily
                order by day desc limit 1
                """,
            ),
        )
        schumann = _fetch_schumann_context(conn)
        ulf = _fetch_one(
            conn,
            (
                """
                select ts_utc, stations_used, regional_intensity, regional_coherence,
                       regional_persistence, context_class, confidence_score, quality_flags
                from marts.ulf_context_5m order by ts_utc desc limit 1
                """,
            ),
        )
        hazards = _fetch_all(
            conn,
            """
            select source, kind, title, location, severity, started_at, ended_at, payload, ingested_at
            from ext.global_hazards
            where coalesce(started_at, ingested_at) >= now() - interval '48 hours'
            order by coalesce(started_at, ingested_at) desc
            limit 40
            """,
        )
    return {"space": space, "schumann": schumann, "ulf": ulf, "hazards": hazards}
