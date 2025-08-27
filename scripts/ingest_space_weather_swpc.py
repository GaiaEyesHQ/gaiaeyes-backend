#!/usr/bin/env python3
"""
NOAA SWPC ingester → ext.space_weather

Fetches from these SWPC endpoints (JSON):
- Planetary K-index (3h bins): 
  https://services.swpc.noaa.gov/products/summary/planetary-k-index.json
- Solar wind speed (km/s):
  https://services.swpc.noaa.gov/products/summary/solar-wind-speed.json
- Solar wind magnetic field (includes Bz in nT):
  https://services.swpc.noaa.gov/products/summary/solar-wind-mag-field.json

Merges by timestamp (UTC), then upserts into ext.space_weather:
  ts_utc (PK), kp_index, bz_nt, sw_speed_kms, src='noaa-swpc', meta jsonb

ENV:
  SUPABASE_DB_URL  (required)  -- use the pooler url with ?pgbouncer=true
  SINCE_HOURS      (optional)  -- default: 72

Notes:
- SWPC “summary/*.json” endpoints return an array-of-arrays:
  first row is headers; subsequent rows are values with the same column order.
- We pick rows newer than now()-SINCE_HOURS.
"""

import os, sys, asyncio, math, json
from datetime import datetime, timezone, timedelta
import asyncpg
import httpx

SINCE_HOURS = int(os.getenv("SINCE_HOURS", "72"))
DB = os.getenv("SUPABASE_DB_URL")
if not DB:
    print("Missing SUPABASE_DB_URL", file=sys.stderr)
    sys.exit(2)

SRC = "noaa-swpc"
BASE = "https://services.swpc.noaa.gov/products/summary"
URLS = {
    "kp": f"{BASE}/planetary-k-index.json",
    "speed": f"{BASE}/solar-wind-speed.json",
    "mag": f"{BASE}/solar-wind-mag-field.json",
}

UA = os.getenv("HTTP_USER_AGENT", "gaiaeyes.com contact: gaiaeyes7.83@gmail.com")

def parse_iso(ts: str) -> datetime:
    # SWPC timestamps are usually ISO8601 with 'Z'
    if ts.endswith("Z"):
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return datetime.fromisoformat(ts)

def coerce_float(x):
    if x in (None, "", "null"):
        return None
    try:
        f = float(x)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except Exception:
        return None

async def fetch_json_array(client: httpx.AsyncClient, url: str):
    r = await client.get(url)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, list) or not data:
        raise ValueError(f"Unexpected JSON shape from {url}")
    return data  # array-of-arrays: [ header_row, row1, row2, ... ]

def rows_to_records(arr, wanted_cols):
    """
    arr: [header, r1, r2,...] (each r is array matching header columns)
    wanted_cols: dict of {logical_name: [candidate_column_names...]}

    Returns list of dicts with:
      ts (datetime), maybe kp_index / bz_nt / sw_speed_kms (floats)
    """
    header = arr[0]
    rows = arr[1:]
    # map header names (case-insensitive) to index
    idx = {h.lower(): i for i, h in enumerate(header)}

    def col_index(candidates):
        for name in candidates:
            key = name.lower()
            if key in idx:
                return idx[key]
        return None

    ts_i = col_index(wanted_cols["ts"])
    out = []
    for r in rows:
        try:
            ts_raw = r[ts_i] if ts_i is not None and ts_i < len(r) else None
            ts = parse_iso(ts_raw) if ts_raw else None
        except Exception:
            ts = None
        out.append({"ts": ts, "row": r, "idx": idx})
    return out

def merge_metric(records, candidates, field_name, out_map):
    """
    For each record with a ts, extract the metric from candidate columns (first that exists)
    and store in out_map[ts][field_name].
    """
    # Determine column index once per dataset (they all share .idx)
    if not records:
        return
    idx = records[0]["idx"]
    col_i = None
    for cand in candidates:
        lc = cand.lower()
        if lc in idx:
            col_i = idx[lc]
            break
    if col_i is None:
        return
    for rec in records:
        ts = rec["ts"]
        if not ts:
            continue
        row = rec["row"]
        val = None
        if col_i < len(row):
            val = coerce_float(row[col_i])
        if ts not in out_map:
            out_map[ts] = {}
        if val is not None:
            out_map[ts][field_name] = val

def filter_since(d: dict, hours: int):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    return {ts: v for ts, v in d.items() if ts and ts >= cutoff}

UPSERT_SQL = """
insert into ext.space_weather (ts_utc, kp_index, bz_nt, sw_speed_kms, src, meta)
values ($1, $2, $3, $4, $5, $6::jsonb)
on conflict (ts_utc) do update
set kp_index     = excluded.kp_index,
    bz_nt        = excluded.bz_nt,
    sw_speed_kms = excluded.sw_speed_kms,
    src          = excluded.src,
    meta         = excluded.meta;
"""

async def main():
    headers = {"User-Agent": UA, "Accept": "application/json"}
    timeout = httpx.Timeout(45.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
        kp_arr   = await fetch_json_array(client, URLS["kp"])
        spd_arr  = await fetch_json_array(client, URLS["speed"])
        mag_arr  = await fetch_json_array(client, URLS["mag"])

    # Parse arrays → records (with timestamps)
    kp_recs  = rows_to_records(kp_arr,  {"ts": ["time_tag","time","datetime","timestamp"]})
    spd_recs = rows_to_records(spd_arr, {"ts": ["time_tag","time","datetime","timestamp"]})
    mag_recs = rows_to_records(mag_arr, {"ts": ["time_tag","time","datetime","timestamp"]})

    # Merge values into a dict keyed by timestamp
    merged = {}

    # Kp can be under different header names; common ones in these feeds:
    # 'kp_index', 'kp_est', 'kp'
    merge_metric(kp_recs,  ["kp_index","kp_est","kp"],               "kp_index",     merged)
    # Solar wind speed columns often: 'speed', 'solar_wind_speed'
    merge_metric(spd_recs, ["speed","solar_wind_speed","sw_speed"],  "sw_speed_kms", merged)
    # Magnetic field Bz: 'bz', 'bz_gsm', 'bz_nt'
    merge_metric(mag_recs, ["bz","bz_gsm","bz_nt"],                  "bz_nt",        merged)

    # Keep recent
    merged = filter_since(merged, SINCE_HOURS)

    if not merged:
        print("No recent space-weather records to upsert.")
        return

    # Prepare rows for upsert
    rows = []
    for ts, v in sorted(merged.items()):
        meta = {"kp_source": URLS["kp"], "speed_source": URLS["speed"], "mag_source": URLS["mag"]}
        rows.append((
            ts,
            v.get("kp_index"),
            v.get("bz_nt"),
            v.get("sw_speed_kms"),
            SRC,
            json.dumps(meta),
        ))

    conn = await asyncpg.connect(dsn=DB, statement_cache_size=0)  # PgBouncer-friendly
    try:
        await conn.executemany(UPSERT_SQL, rows)
        print(f"Upserted {len(rows)} ext.space_weather rows from {SRC}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
