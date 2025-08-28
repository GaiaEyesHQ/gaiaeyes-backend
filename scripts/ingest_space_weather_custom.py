#!/usr/bin/env python3
"""
Ingest Kp (1-minute) + SWPC Solar Wind (plasma + mag) into ext.space_weather.

Sources (defaults):
- Kp 1m:   https://services.swpc.noaa.gov/json/planetary_k_index_1m.json  (list of dicts)
- Plasma:  https://services.swpc.noaa.gov/products/solar-wind/plasma-7-day.json  (array-of-arrays)
- Mag:     https://services.swpc.noaa.gov/products/solar-wind/mag-7-day.json     (array-of-arrays; includes Bz)

Upserts into ext.space_weather:
  ts_utc (PK), kp_index, bz_nt, sw_speed_kms, src='noaa-swpc', meta jsonb

ENV:
  SUPABASE_DB_URL  (required)   -- pooler DSN with ?pgbouncer=true&sslmode=require
  KP_URL           (optional)   -- override Kp JSON URL
  SW_URL           (optional)   -- override plasma JSON URL
  MAG_URL          (optional)   -- override mag JSON URL for Bz
  HTTP_USER_AGENT  (optional)   -- polite UA for api.weather.gov-style services
  SINCE_HOURS      (default 72) -- only keep rows newer than now()-N hours
"""

import os
import sys
import json
import math
import asyncio
from datetime import datetime, timezone, timedelta

import httpx
import asyncpg


# ---------------------- env helpers ----------------------

def env(name: str, default=None, required: bool = False):
    val = os.getenv(name, default)
    if required and (val is None or val == ""):
        print(f"Missing required env: {name}", file=sys.stderr)
        sys.exit(2)
    return val


DB  = env("SUPABASE_DB_URL", required=True)

# Recommended SWPC product endpoints:
KP  = env("KP_URL",  "https://services.swpc.noaa.gov/json/planetary_k_index_1m.json")
SW  = env("SW_URL",  "https://services.swpc.noaa.gov/products/solar-wind/plasma-7-day.json")
MAG = env("MAG_URL", "https://services.swpc.noaa.gov/products/solar-wind/mag-7-day.json")

UA  = env("HTTP_USER_AGENT", "(gaiaeyes.com, gaiaeyes7.83@gmail.com)")
SINCE_HOURS = int(env("SINCE_HOURS", "72"))

SRC = "noaa-swpc"


# ---------------------- parsing helpers ----------------------

def parse_ts(x):
    """Robust timestamp parser supporting ISO strings (with/without Z) and epoch seconds."""
    if x is None:
        return None
    if isinstance(x, (int, float)):
        try:
            return datetime.fromtimestamp(float(x), tz=timezone.utc)
        except Exception:
            return None
    if isinstance(x, str):
        s = x.strip()
        try:
            if s.endswith("Z"):
                return datetime.fromisoformat(s.replace("Z", "+00:00"))
            return datetime.fromisoformat(s)
        except Exception:
            # last resort: trim fractional
            try:
                base = s.split(".")[0]
                if not base.endswith("Z") and "+" not in base and "-" not in base[10:]:
                    base += "Z"
                return datetime.fromisoformat(base.replace("Z", "+00:00"))
            except Exception:
                return None
    return None


def f(x):
    """Coerce to float; filter NaN/inf/empties → None."""
    if x in (None, "", "null", "NaN"):
        return None
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except Exception:
        return None


def cutoff_dt():
    return datetime.now(timezone.utc) - timedelta(hours=SINCE_HOURS)


def normalize_array_of_arrays(data):
    """
    Convert SWPC 'products' JSON (array-of-arrays: [header, row1, ...])
    into list-of-dicts to match the rest of the pipeline.
    If data already looks like list-of-dicts, return as-is.
    """
    if not isinstance(data, list) or not data:
        return data
    header = data[0]
    if not (isinstance(header, list) and all(isinstance(h, str) for h in header)):
        return data  # not AoA; likely list of dicts already
    out = []
    keys = [h.strip() for h in header]
    for row in data[1:]:
        if not isinstance(row, list):
            continue
        d = {}
        for i, k in enumerate(keys):
            if i < len(row):
                d[k] = row[i]
        out.append(d)
    return out


def idx_by_ts(objs, ts_keys=("time_tag", "time", "timestamp", "date", "datetime", "TimeTag")):
    """
    Build dict keyed by parsed ts for rows newer than cutoff.
    Accepts list-of-dicts; caller should normalize AoA → dicts first.
    """
    out = {}
    co = cutoff_dt()
    for d in objs if isinstance(objs, list) else []:
        ts_raw = None
        for k in ts_keys:
            if k in d and d[k] not in ("", None):
                ts_raw = d[k]
                break
        if ts_raw is None:
            continue
        ts = parse_ts(ts_raw)
        if not ts:
            continue
        # >>> FIX: ensure timezone-aware (UTC) before comparing <<<
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if ts < co:
            continue
        out[ts] = d
    return out


# ---------------------- HTTP + DB ----------------------

async def get_json(client: httpx.AsyncClient, url: str):
    r = await client.get(url)
    r.raise_for_status()
    return r.json()


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


# ---------------------- main ----------------------

async def main():
    headers = {"User-Agent": UA, "Accept": "application/json"}
    timeout = httpx.Timeout(45.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout, headers=headers) as c:
        kp_json  = await get_json(c, KP)     # list-of-dicts
        sw_json  = await get_json(c, SW)     # array-of-arrays → normalize
        mag_json = await get_json(c, MAG)    # array-of-arrays → normalize

    # Normalize product feeds (AoA → list-of-dicts)
    kp_json  = normalize_array_of_arrays(kp_json)   # no-op if already dicts
    sw_json  = normalize_array_of_arrays(sw_json)
    mag_json = normalize_array_of_arrays(mag_json)

    # Index by timestamp within SINCE_HOURS window
    kp_by_ts  = idx_by_ts(kp_json, ts_keys=("time_tag", "time", "timestamp", "date", "datetime"))
    sw_by_ts  = idx_by_ts(sw_json, ts_keys=("time_tag", "time", "timestamp"))
    mag_by_ts = idx_by_ts(mag_json, ts_keys=("time_tag", "time", "timestamp"))

    ts_all = sorted(set(kp_by_ts.keys()) | set(sw_by_ts.keys()) | set(mag_by_ts.keys()))
    if not ts_all:
        print("No recent records in the selected time window.")
        return

    rows = []
    for ts in ts_all:
        kpd = kp_by_ts.get(ts, {})
        swd = sw_by_ts.get(ts, {})
        mgd = mag_by_ts.get(ts, {})

        # Kp (1m) candidate keys
        kp_val = f(
            kpd.get("kp_index") or kpd.get("kp") or kpd.get("Kp")
            or kpd.get("estimated_kp") or kpd.get("kp_value")
        )

        # Solar wind speed (km/s) candidate keys seen in plasma products
        # Common columns include: 'speed', 'plasma_speed', 'proton_speed', 'flow_speed', 'velocity'
        sw_speed = f(
            swd.get("speed") or swd.get("plasma_speed") or swd.get("proton_speed")
            or swd.get("flow_speed") or swd.get("velocity")
        )

        # Bz (nT) from MAG products (prefer GSM if available)
        bz_val = f(
            mgd.get("bz_gsm") or mgd.get("bz_gse") or mgd.get("bz") or mgd.get("Bz")
        )

        meta = {
            "sources": {
                "kp": KP,
                "plasma": SW,
                "mag": MAG
            }
        }

        rows.append((ts, kp_val, bz_val, sw_speed, SRC, json.dumps(meta)))

    conn = await asyncpg.connect(dsn=DB, statement_cache_size=0)  # PgBouncer-friendly
    try:
        await conn.executemany(UPSERT_SQL, rows)
        print(f"Upserted {len(rows)} rows into ext.space_weather from {SRC}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
