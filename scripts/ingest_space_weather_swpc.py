#!/usr/bin/env python3
"""
Ingest Kp(1m) + DSCOVR Solar Wind (+ optional MAG for Bz) into ext.space_weather.

Sources (defaults point to your picks):
- Kp 1m:        https://services.swpc.noaa.gov/json/planetary_k_index_1m.json
- Solar wind:   https://services.swpc.noaa.gov/json/dscovr/solar_wind.json
- Mag (Bz):     https://services.swpc.noaa.gov/json/dscovr/mag.json   (optional but recommended)

ENV:
  SUPABASE_DB_URL  (required)   -- pooler DSN with ?pgbouncer=true&sslmode=require
  KP_URL           (optional)   -- override Kp JSON URL
  SW_URL           (optional)   -- override solar wind JSON URL
  MAG_URL          (optional)   -- override mag JSON URL for Bz
  HTTP_USER_AGENT  (optional)
  SINCE_HOURS      (default 72)
"""

import os, sys, asyncio, math, json
from datetime import datetime, timezone, timedelta
import httpx, asyncpg

def env(k, default=None, required=False):
    v = os.getenv(k, default)
    if required and (v is None or v == ""):
        print(f"Missing env: {k}", file=sys.stderr); sys.exit(2)
    return v

DB  = env("SUPABASE_DB_URL", required=True)
KP  = env("KP_URL",  "https://services.swpc.noaa.gov/json/planetary_k_index_1m.json")
SW  = env("SW_URL",  "https://services.swpc.noaa.gov/json/dscovr/solar_wind.json")
MAG = env("MAG_URL", "https://services.swpc.noaa.gov/json/dscovr/mag.json")  # set to "" to disable
UA  = env("HTTP_USER_AGENT", "(gaiaeyes.com, gaiaeyes7.83@gmail.com)")
SINCE_HOURS = int(env("SINCE_HOURS", "72"))

SRC = "noaa-swpc"

def parse_ts(x):
    if x is None: return None
    if isinstance(x, (int, float)):
        return datetime.fromtimestamp(float(x), tz=timezone.utc)
    if isinstance(x, str):
        s = x.strip()
        if s.endswith("Z"):
            return datetime.fromisoformat(s.replace("Z","+00:00"))
        try:
            return datetime.fromisoformat(s)
        except Exception:
            # trim fractional
            try:
                base = s.split(".")[0]
                if not base.endswith("Z") and "+" not in base and "-" not in base[10:]:
                    base += "Z"
                return datetime.fromisoformat(base.replace("Z","+00:00"))
            except Exception:
                return None
    return None

def f(x):
    if x in (None, "", "null", "NaN"): return None
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v): return None
        return v
    except Exception:
        return None

async def get_json(client, url):
    r = await client.get(url)
    r.raise_for_status()
    return r.json()

def cutoff():
    return datetime.now(timezone.utc) - timedelta(hours=SINCE_HOURS)

def idx_by_ts(objs, ts_keys=("time_tag","time","timestamp","date","datetime","TimeTag")):
    out = {}
    co = cutoff()
    for d in objs:
        # try a few timestamp keys
        ts_raw = None
        for k in ts_keys:
            if k in d and d[k] not in ("", None):
                ts_raw = d[k]; break
        if ts_raw is None: 
            # some DSCOVR arrays use 'time_tag' nested name 'time_tag': 'YYYY...'
            # already handled, else skip
            continue
        ts = parse_ts(ts_raw)
        if not ts or ts < co: 
            continue
        out[ts] = d
    return out

UPSERT = """
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
    async with httpx.AsyncClient(timeout=timeout, headers=headers) as c:
        kp_json  = await get_json(c, KP)
        sw_json  = await get_json(c, SW)
        mag_json = None
        if MAG:
            try:
                mag_json = await get_json(c, MAG)
            except Exception:
                mag_json = None

    # Expect lists of dicts from these endpoints.
    if not isinstance(kp_json, list):  kp_json = []
    if not isinstance(sw_json, list):  sw_json = []
    if mag_json is not None and not isinstance(mag_json, list):
        mag_json = []

    kp_by_ts  = idx_by_ts(kp_json, ts_keys=("time_tag","time","timestamp","date","datetime"))
    sw_by_ts  = idx_by_ts(sw_json, ts_keys=("time_tag","time","timestamp"))
    mag_by_ts = idx_by_ts(mag_json or [], ts_keys=("time_tag","time","timestamp"))

    ts_all = sorted(set(kp_by_ts.keys()) | set(sw_by_ts.keys()) | set(mag_by_ts.keys()))
    if not ts_all:
        print("No recent records in the last hours window.")
        return

    rows = []
    for ts in ts_all:
        kpd = kp_by_ts.get(ts, {})
        swd = sw_by_ts.get(ts, {})
        mgd = mag_by_ts.get(ts, {})

        # Field name guesses:
        # Kp(1m): "kp_index" or "kp"
        kp_val = f(kpd.get("kp_index") or kpd.get("kp") or kpd.get("Kp"))

        # Solar wind speed: "speed" or "solar_wind_speed"
        sw_speed = f(swd.get("speed") or swd.get("solar_wind_speed") or swd.get("velocity"))

        # Bz from MAG: "bz" or "bz_gsm" or "Bz"
        bz_val = f(mgd.get("bz") or mgd.get("bz_gsm") or mgd.get("Bz"))

        meta = {
            "sources": {
                "kp": KP, "solar_wind": SW, "mag": (MAG or None)
            }
        }
        rows.append((ts, kp_val, bz_val, sw_speed, SRC, json.dumps(meta)))

    conn = await asyncpg.connect(dsn=DB, statement_cache_size=0)
    try:
        await conn.executemany(UPSERT, rows)
        print(f"Upserted {len(rows)} rows into ext.space_weather from {SRC}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
