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
BASE_SUM = "https://services.swpc.noaa.gov/products/summary"
BASE_PROD = "https://services.swpc.noaa.gov/products"
URLS_LIST = {
    # Try summary first, then products fallbacks
    "kp": [
        f"{BASE_PROD}/noaa-planetary-k-index.json",      # primary
        f"{BASE_SUM}/planetary-k-index.json",           # legacy
    ],
    "speed": [
        f"{BASE_SUM}/solar-wind-speed.json",
    ],
    "mag": [
        f"{BASE_SUM}/solar-wind-mag.json",              # primary
        f"{BASE_SUM}/solar-wind-mag-field.json",        # legacy/alt
    ],
}
ALERTS_URL = "https://services.swpc.noaa.gov/products/alerts.json"
FORECAST_URL = "https://services.swpc.noaa.gov/text/3-day-forecast.txt"

UA = os.getenv("HTTP_USER_AGENT", "gaiaeyes.com contact: gaiaeyes7.83@gmail.com")

def parse_iso(ts: str) -> datetime:
    """Parse ISO8601-ish strings and ensure tz-aware (UTC)."""
    if not ts:
        return None  # type: ignore
    s = ts.strip()
    # normalize common variants
    if s.endswith("Z"):
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    else:
        # some feeds use "YYYY-MM-DD HH:MM:SS" without TZ
        # make sure it parses and becomes UTC-aware
        try:
            dt = datetime.fromisoformat(s)
        except Exception:
            # last resort: replace space with T
            try:
                dt = datetime.fromisoformat(s.replace(" ", "T"))
            except Exception:
                return None  # type: ignore
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt

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

async def fetch_any_json_array(client: httpx.AsyncClient, urls: list[str], label: str):
    last_err = None
    for u in urls:
        try:
            return await fetch_json_array(client, u)
        except Exception as e:
            last_err = e
            print(f"[warn] {label} fetch failed for {u}: {e}")
            continue
    print(f"[warn] {label} fetch failed for all URLs")
    return []

async def fetch_text(client: httpx.AsyncClient, url: str) -> str:
    r = await client.get(url)
    r.raise_for_status()
    return r.text

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
        ts = None
        try:
            ts_raw = r[ts_i] if ts_i is not None and ts_i < len(r) else None
            ts = parse_iso(ts_raw) if ts_raw else None
        except Exception:
            ts = None
        # keep rows even if ts is None; later filters will drop them
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
    out = {}
    for ts, v in d.items():
        if not ts:
            continue
        t = ts
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        else:
            t = t.astimezone(timezone.utc)
        if t >= cutoff:
            out[t] = v
    return out

def parse_alert_rows(arr):
    """Parse SWPC alerts feed into a list of rows.
    Accepts one of:
      - array-of-arrays with header row
      - array of dicts
      - dict with an 'alerts' key containing either of the above
    Returns list of dicts: {issued_at: datetime|None, message: str, meta: dict}
    """
    def _row_to_dict_list(header, rows):
        out = []
        for r in rows:
            # tolerate ragged rows
            meta = {header[i]: (r[i] if i < len(r) else None) for i in range(len(header))}
            ts_raw = None
            for k in ("issue_time", "issue_time_utc", "time_tag", "time"):
                if k in meta and meta[k]:
                    ts_raw = meta[k]
                    break
            issued = None
            try:
                issued = parse_iso(ts_raw) if ts_raw else None
            except Exception:
                issued = None
            message = meta.get("message") or meta.get("alert_message") or json.dumps(meta)
            out.append({"issued_at": issued, "message": message, "meta": meta})
        return out

    # Unwrap dict wrapper
    if isinstance(arr, dict):
        if "alerts" in arr and isinstance(arr["alerts"], list):
            arr = arr["alerts"]
        else:
            # Unknown dict shape
            return []

    if not isinstance(arr, list) or not arr:
        return []

    first = arr[0]
    # Case 1: array-of-arrays with header row
    if isinstance(first, list):
        header = first
        rows = arr[1:]
        # If header isn’t strings, bail safely
        if not all(isinstance(h, str) for h in header):
            return []
        return _row_to_dict_list(header, rows)

    # Case 2: array of dicts
    if isinstance(first, dict):
        out = []
        for meta in arr:
            if not isinstance(meta, dict):
                continue
            ts_raw = None
            for k in ("issue_time", "issue_time_utc", "time_tag", "time"):
                if k in meta and meta[k]:
                    ts_raw = meta[k]
                    break
            issued = None
            try:
                issued = parse_iso(ts_raw) if ts_raw else None
            except Exception:
                issued = None
            message = meta.get("message") or meta.get("alert_message") or json.dumps(meta)
            out.append({"issued_at": issued, "message": message, "meta": meta})
        return out

    # Unknown list shape → ignore
    return []

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

UPSERT_ALERT_SQL = """
insert into ext.space_alerts (issued_at, src, message, meta)
values ($1, $2, $3, $4::jsonb)
on conflict (issued_at, src, message) do update
set meta = excluded.meta;
"""

UPSERT_FORECAST_SQL = """
insert into ext.space_forecast (fetched_at, src, body_text)
values ($1, $2, $3)
on conflict (fetched_at, src) do nothing;
"""

async def main():
    headers = {"User-Agent": UA, "Accept": "application/json"}
    timeout = httpx.Timeout(45.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
        kp_arr   = await fetch_any_json_array(client, URLS_LIST["kp"],   "kp")
        spd_arr  = await fetch_any_json_array(client, URLS_LIST["speed"],"speed")
        mag_arr  = await fetch_any_json_array(client, URLS_LIST["mag"],  "mag")
        # Optional feeds
        try:
            alerts_arr = await fetch_json_array(client, ALERTS_URL)
        except Exception as e:
            print(f"[warn] alerts fetch failed: {e}")
            alerts_arr = []
        try:
            forecast_txt = await fetch_text(client, FORECAST_URL)
        except Exception as e:
            print(f"[warn] forecast fetch failed: {e}")
            forecast_txt = None

    # Parse arrays → records (with timestamps)
    kp_recs  = rows_to_records(kp_arr,  {"ts": ["time_tag","time","datetime","timestamp"]}) if kp_arr else []
    spd_recs = rows_to_records(spd_arr, {"ts": ["time_tag","time","datetime","timestamp"]}) if spd_arr else []
    mag_recs = rows_to_records(mag_arr, {"ts": ["time_tag","time","datetime","timestamp"]}) if mag_arr else []

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

    # Prepare rows for upsert
    rows = []
    for ts, v in sorted(merged.items()):
        meta = {"kp_source": URLS_LIST["kp"][0] if URLS_LIST["kp"] else None, "speed_source": URLS_LIST["speed"][0] if URLS_LIST["speed"] else None, "mag_source": URLS_LIST["mag"][0] if URLS_LIST["mag"] else None}
        rows.append((
            ts,
            v.get("kp_index"),
            v.get("bz_nt"),
            v.get("sw_speed_kms"),
            SRC,
            json.dumps(meta),
        ))

    conn = await asyncpg.connect(dsn=DB, statement_cache_size=0)
    try:
        # Upsert space weather time series
        if rows:
            await conn.executemany(UPSERT_SQL, rows)
            print(f"Upserted {len(rows)} ext.space_weather rows from {SRC}")
        else:
            print("No recent space-weather records to upsert.")

        # Ingest alerts (best-effort)
        if alerts_arr:
            alert_rows = [a for a in parse_alert_rows(alerts_arr) if a.get("issued_at")]
            if alert_rows:
                ups = [(
                    a["issued_at"],
                    SRC,
                    a["message"],
                    json.dumps(a["meta"]),
                ) for a in alert_rows]
                await conn.executemany(UPSERT_ALERT_SQL, ups)
                print(f"Upserted {len(ups)} ext.space_alerts rows from {SRC}")

        # Store raw 3-day forecast text (best-effort, retains history by fetched_at)
        if forecast_txt:
            await conn.execute(UPSERT_FORECAST_SQL, datetime.now(timezone.utc), SRC, forecast_txt)
            print("Stored 3-day forecast text in ext.space_forecast")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
