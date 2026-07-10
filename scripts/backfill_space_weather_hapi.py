#!/usr/bin/env python3
"""Backfill solar-wind speed and Bz from NOAA's active-spacecraft HAPI archive.

Required environment:
  SUPABASE_DB_URL
  BACKFILL_START_UTC  ISO-8601 inclusive start
  BACKFILL_END_UTC    ISO-8601 exclusive end

The active datasets preserve SWPC's operational spacecraft selection across
SOLAR-1, ACE, and other supported spacecraft. Only nominal-quality values are
written. Existing Kp values are preserved.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import asyncpg
import httpx


HAPI_BASE = os.getenv("SWPC_HAPI_BASE", "https://tlv-swpc.woc.noaa.gov/hapi")
PLASMA_DATASET = "active-plasma-pt1m"
MAG_DATASET = "active-mag-pt1m"


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required env: {name}")
    return value


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_hapi_csv(text: str, value_field: str) -> dict[datetime, dict]:
    parsed: dict[datetime, dict] = {}
    for row in csv.DictReader(io.StringIO(text)):
        try:
            timestamp = parse_time(row["time_tag"])
            value = float(row[value_field])
            quality = int(row.get("quality") or -1)
        except (KeyError, TypeError, ValueError):
            continue
        if quality != 0 or value <= -1e29:
            continue
        parsed[timestamp] = {
            "value": value,
            "quality": quality,
            "source_code": row.get("source"),
        }
    return parsed


async def fetch_dataset(
    client: httpx.AsyncClient,
    dataset: str,
    value_field: str,
    start: datetime,
    end: datetime,
) -> dict[datetime, dict]:
    response = await client.get(
        f"{HAPI_BASE}/data",
        params={
            "id": dataset,
            "parameters": f"{value_field},source,quality",
            "time.min": start.isoformat().replace("+00:00", "Z"),
            "time.max": end.isoformat().replace("+00:00", "Z"),
        },
    )
    response.raise_for_status()
    return parse_hapi_csv(response.text, value_field)


UPSERT_SQL = """
insert into ext.space_weather as existing (ts_utc, kp_index, bz_nt, sw_speed_kms, src, meta)
values ($1, null, $2, $3, 'noaa-swpc-hapi-backfill', $4::jsonb)
on conflict (ts_utc) do update
set bz_nt        = coalesce(excluded.bz_nt, existing.bz_nt),
    sw_speed_kms = coalesce(excluded.sw_speed_kms, existing.sw_speed_kms),
    meta         = (coalesce(existing.meta, '{}'::jsonb) || excluded.meta)
                   || jsonb_build_object(
                        'measurements',
                        coalesce(existing.meta->'measurements', '{}'::jsonb)
                        || coalesce(excluded.meta->'measurements', '{}'::jsonb)
                      );
"""


async def main() -> None:
    database_url = required_env("SUPABASE_DB_URL")
    start = parse_time(required_env("BACKFILL_START_UTC"))
    end = parse_time(required_env("BACKFILL_END_UTC"))
    if start >= end:
        raise SystemExit("BACKFILL_START_UTC must be earlier than BACKFILL_END_UTC")

    merged: dict[datetime, dict] = {}
    timeout = httpx.Timeout(60.0, connect=10.0)
    headers = {"User-Agent": os.getenv("HTTP_USER_AGENT", "GaiaEyes/space-weather-backfill")}
    async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
        chunk_start = start
        while chunk_start < end:
            chunk_end = min(chunk_start + timedelta(days=1), end)
            plasma, mag = await asyncio.gather(
                fetch_dataset(client, PLASMA_DATASET, "speed", chunk_start, chunk_end),
                fetch_dataset(client, MAG_DATASET, "bz_gsm", chunk_start, chunk_end),
            )
            for timestamp, record in plasma.items():
                merged.setdefault(timestamp, {})["speed"] = record
            for timestamp, record in mag.items():
                merged.setdefault(timestamp, {})["bz"] = record
            chunk_start = chunk_end

    rows = []
    for timestamp, record in sorted(merged.items()):
        speed = record.get("speed")
        bz = record.get("bz")
        measurements = {}
        if speed:
            measurements["sw_speed_kms"] = {
                "spacecraft": "SWPC active",
                "source_code": speed.get("source_code"),
                "overall_quality": speed.get("quality"),
                "dataset": PLASMA_DATASET,
            }
        if bz:
            measurements["bz_nt"] = {
                "spacecraft": "SWPC active",
                "source_code": bz.get("source_code"),
                "overall_quality": bz.get("quality"),
                "dataset": MAG_DATASET,
            }
        meta = {
            "hapi_source": HAPI_BASE,
            "measurements": measurements,
        }
        rows.append((
            timestamp,
            bz.get("value") if bz else None,
            speed.get("value") if speed else None,
            json.dumps(meta),
        ))

    if not rows:
        raise SystemExit("No nominal-quality HAPI rows were returned")

    connection = await asyncpg.connect(dsn=database_url, statement_cache_size=0)
    try:
        for offset in range(0, len(rows), 2000):
            await connection.executemany(UPSERT_SQL, rows[offset:offset + 2000])
    finally:
        await connection.close()
    print(f"Backfilled {len(rows)} active-spacecraft rows from {start.isoformat()} to {end.isoformat()}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (httpx.HTTPError, asyncpg.PostgresError) as exc:
        print(f"Backfill failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
