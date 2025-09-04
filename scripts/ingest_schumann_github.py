#!/usr/bin/env python3
"""
Ingest Schumann now JSON from gennwu/gaiaeyes-media into ext.schumann (and stations/assets).

JSON: https://raw.githubusercontent.com/gennwu/gaiaeyes-media/main/data/schumann_now.json

- stations: 'tomsk', 'cumiana'
- per station we ingest:
  - fundamental_hz  -> channel 'fundamental_hz'
  - harmonics_hz    -> channels 'F1'..'F5' (ignore non-harmonic keys like 'trace_x_offset')
  - timestamp_utc   -> ts_utc
  - confidence, last_modified, overlay_path -> station meta
- images:
  - images/tomsk_overlay.png
  - images/cumiana_overlay.png
"""

import os, sys, json, asyncio
from datetime import datetime, timezone
import asyncpg, httpx

RAW_JSON = "https://raw.githubusercontent.com/gennwu/gaiaeyes-media/main/data/schumann_now.json"
RAW_IMG_BASE = "https://raw.githubusercontent.com/gennwu/gaiaeyes-media/main/images/"

DB = os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL")
if not DB:
    print("Set SUPABASE_DB_URL or DATABASE_URL (Supabase Pooler DSN)", file=sys.stderr)
    sys.exit(2)

UPSERT_STATION = """
insert into ext.schumann_station (station_id, name, lat, lon, meta)
values ($1,$2,$3,$4,$5::jsonb)
on conflict (station_id) do update
set name = excluded.name,
    lat  = coalesce(excluded.lat, ext.schumann_station.lat),
    lon  = coalesce(excluded.lon, ext.schumann_station.lon),
    meta = excluded.meta;
"""

UPSERT_ROW = """
insert into ext.schumann (station_id, ts_utc, channel, value_num, unit, meta)
values ($1,$2,$3,$4,$5,$6::jsonb)
on conflict (station_id, ts_utc, channel) do update
set value_num = excluded.value_num,
    unit      = excluded.unit,
    meta      = excluded.meta;
"""

UPSERT_ASSET = """
insert into content.asset (storage_path, mime, alt_text, meta)
values ($1,$2,$3,$4::jsonb)
on conflict (storage_path) do update
set mime     = excluded.mime,
    alt_text = excluded.alt_text,
    meta     = excluded.meta;
"""

def parse_ts(s: str | None) -> datetime | None:
    if not s: return None
    s = s.strip()
    try:
        if s.endswith("Z"): return datetime.fromisoformat(s.replace("Z","+00:00"))
        return datetime.fromisoformat(s)
    except Exception:
        return None

def is_harmonic_key(k: str) -> bool:
    # Accept F1..F9; ignore helpers like 'trace_x_offset'
    return k and k[0] == "F" and k[1:].isdigit()

async def fetch_json(client: httpx.AsyncClient, url: str) -> dict:
    r = await client.get(url, timeout=30, follow_redirects=True)
    r.raise_for_status()
    return r.json()

async def main():
    conn = await asyncpg.connect(dsn=DB, statement_cache_size=0)
    try:
        async with httpx.AsyncClient() as client:
            doc = await fetch_json(client, RAW_JSON)

        sources = doc.get("sources", {}) or {}
        global_ts = parse_ts(doc.get("timestamp_utc"))
        rows = []
        assets = []

        for station_id in ("tomsk", "cumiana"):
            src = sources.get(station_id)
            if not isinstance(src, dict): 
                continue
            if src.get("status") != "ok":
                continue

            # Station meta
            station_meta = {
                "confidence": src.get("confidence"),
                "last_modified": src.get("last_modified"),
                "overlay_path": src.get("overlay_path") or doc.get("overlay_path"),
                "raw_note": (src.get("raw") or {}).get("note"),
                "source": src.get("source"),
            }

            # Upsert station (lat/lon unknown -> null)
            await conn.execute(UPSERT_STATION, station_id, station_id.title(), None, None, json.dumps(station_meta))

            # Overlay asset (raw GitHub URL)
            overlay_rel = (src.get("overlay_path") or "").strip().lstrip("./")
            if not overlay_rel:
                # fallback: station-specific default
                overlay_rel = f"{station_id}_overlay.png"
            overlay_url = RAW_IMG_BASE + overlay_rel
            assets.append((overlay_url, "image/png", f"{station_id} overlay", json.dumps({"repo":"gennwu/gaiaeyes-media"})))

            # Timestamp
            ts = parse_ts(src.get("timestamp_utc")) or global_ts
            if not ts:
                # If nothing to timestamp, skip station
                continue

            # Fundamental
            f0 = src.get("fundamental_hz")
            if f0 is not None:
                try:
                    rows.append((station_id, ts, "fundamental_hz", float(f0), "Hz", json.dumps(src)))
                except Exception:
                    pass

            # Harmonics
            harm = src.get("harmonics_hz") or {}
            if isinstance(harm, dict):
                for k, v in harm.items():
                    if not is_harmonic_key(k):
                        continue
                    if v is None:
                        continue
                    try:
                        rows.append((station_id, ts, k, float(v), "Hz", json.dumps(src)))
                    except Exception:
                        continue

        # Write rows
        if rows:
            await conn.executemany(UPSERT_ROW, rows)
            print(f"Upserted {len(rows)} schumann rows")

        # Upsert overlay assets
        if assets:
            await conn.executemany(UPSERT_ASSET, assets)
            print(f"Upserted {len(assets)} overlay assets")

    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
