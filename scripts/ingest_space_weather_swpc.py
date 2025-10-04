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

import os, sys, asyncio, math, json, gzip, pathlib, re
from datetime import datetime, timezone, timedelta
import asyncpg
import httpx

SINCE_HOURS = int(os.getenv("SINCE_HOURS", "72"))
DB = os.getenv("SUPABASE_DB_URL")
if not DB:
    print("Missing SUPABASE_DB_URL", file=sys.stderr)
    sys.exit(2)

OUTPUT_JSON_PATH = os.getenv("OUTPUT_JSON_PATH")  # e.g., ../gaiaeyes-media/data/space_weather.json
OUTPUT_JSON_GZIP = os.getenv("OUTPUT_JSON_GZIP", "false").lower() in ("1","true","yes")
NEXT72_DEFAULT = os.getenv("NEXT72_DEFAULT", "Quiet to unsettled")

SRC = "noaa-swpc"
BASE_SUM = "https://services.swpc.noaa.gov/products/summary"
BASE_PROD = "https://services.swpc.noaa.gov/products"
URLS_LIST = {
    # Prefer products/* 1-day, then 7-day; keep summary as last fallback
    "kp": [
        f"{BASE_PROD}/noaa-planetary-k-index.json",
        f"{BASE_SUM}/planetary-k-index.json",
    ],
    "speed": [
        f"{BASE_PROD}/solar-wind/plasma-1-day.json",
        f"{BASE_PROD}/solar-wind/plasma-7-day.json",
        f"{BASE_SUM}/solar-wind-speed.json",            # preferred (works, single-object)
    ],
    "mag": [
        f"{BASE_PROD}/solar-wind/mag-1-day.json",
        f"{BASE_PROD}/solar-wind/mag-7-day.json",
        f"{BASE_SUM}/solar-wind-mag-field.json",
        f"{BASE_SUM}/solar-wind-mag.json",
    ],
}
ALERTS_URL = "https://services.swpc.noaa.gov/products/alerts.json"
FORECAST_URL = "https://services.swpc.noaa.gov/text/3-day-forecast.txt"

UA = os.getenv("HTTP_USER_AGENT", "gaiaeyes.com contact: gaiaeyes7.83@gmail.com")

def _safe_mkdirs(path: str):
    p = pathlib.Path(path)
    if p.suffix:
        p.parent.mkdir(parents=True, exist_ok=True)
    else:
        p.mkdir(parents=True, exist_ok=True)


def latest_ts_and_vals(merged: dict):
    """Return (ts, vals) for the most recent merged entry."""
    if not merged:
        return None, {}
    ts = max(merged.keys())
    return ts, merged[ts]

def latest_field_value(merged: dict, field: str):
    """Return the most recent non-None value for a field from the merged map."""
    if not merged:
        return None
    latest_val = None
    for ts in sorted(merged.keys()):
        v = merged[ts].get(field)
        if v is not None:
            latest_val = v
    return latest_val

def _to_float_or_none(x):
    try:
        if x is None:
            return None
        f = float(x)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except Exception:
        return None

def parse_next72_headline(forecast_txt: str|None) -> tuple[str,str]:
    """
    Heuristic: scan SWPC 3-day text for strongest G-level keywords and adverbs.
    Returns (headline, confidence).
    """
    if not forecast_txt:
        return NEXT72_DEFAULT, "low"
    txt = forecast_txt.lower()
    # Find strongest G-level mentioned
    level = None
    for g in ["g5","g4","g3","g2","g1"]:
        if g in txt:
            level = g.upper()
            break
    # Confidence terms
    conf = "medium"
    if re.search(r"\blikely\b|\bexpected\b|\bprobable\b", txt):
        conf = "high"
    elif re.search(r"\bslight\b|\bchance\b|\bpossible\b", txt):
        conf = "medium"
    elif re.search(r"\bunlikely\b|\bminimal\b", txt):
        conf = "low"
    if level:
        # Try to infer timing phrases
        when = None
        m = re.search(r"(tonight|tomorrow|day\s+\d|day\s+two|day\s+three|day\s+1|day\s+2|day\s+3|weekend|overnight)", txt)
        if m:
            when = m.group(1).replace("day 1","today").replace("day 2","tomorrow").replace("day two","tomorrow").replace("day 3","day 3")
        headline = f"{level} possible{(' ' + when) if when else ''}".strip()
    else:
        headline = NEXT72_DEFAULT
    return headline, conf

def extract_recent_alert_tags(alert_rows: list[dict], hours:int=24) -> list[str]:
    """
    Pull compact tags like G1..G5, R1..R5, S1..S5 from recent SWPC alerts.
    """
    if not alert_rows:
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    tags = []
    for a in alert_rows:
        t = a.get("issued_at")
        if t and t >= cutoff:
            msg = (a.get("message") or "").upper()
            for tag in ("G1","G2","G3","G4","G5","R1","R2","R3","R4","R5","S1","S2","S3","S4","S5"):
                if tag in msg and tag not in tags:
                    tags.append(tag)
    return tags

def humanize_impacts(kp: float|None, bz: float|None) -> dict:
    """
    Simple rules to turn current Kp and Bz orientation into human-readable impacts.
    """
    gps = "Normal"
    comms = "Normal"
    grids = "Normal"
    aurora = "Unlikely except high latitudes"

    if kp is not None:
        if kp >= 7:
            gps = "Significant errors & dropouts possible; favor multi-constellation + dual-frequency"
            comms = "HF blackouts and GNSS scintillation likely at high/mid latitudes"
            grids = "Geomagnetically induced currents possible; operators may see alarms"
            aurora = "Likely far south from usual; widespread visibility"
        elif kp >= 6:
            gps = "Elevated errors at high/mid latitudes; brief loss of lock possible"
            comms = "HF degradation likely at high latitudes; some mid-latitude impacts"
            grids = "Minor voltage fluctuations possible"
            aurora = "Likely at high latitudes; possible into mid-latitudes"
        elif kp >= 5:
            gps = "Minor positioning errors at high latitudes"
            comms = "Occasional HF fades near poles"
            grids = "Low risk; minor fluctuations"
            aurora = "Possible at high latitudes"
        elif kp >= 4:
            gps = "Mostly normal; slight high-lat jitter"
            comms = "Mostly normal"
            grids = "Normal"
            aurora = "More frequent high-lat aurora"
        else:
            gps = "Normal"
            comms = "Normal"
            grids = "Normal"
            aurora = "Mostly confined to polar regions"

    # Bz southward increases coupling → nudge risk upward
    if bz is not None and bz < -5:
        gps = ("Slightly elevated risk due to southward Bz — " + gps).strip()
        comms = ("Polar HF more variable — " + comms).strip()
        aurora = ("Enhanced if sustained — " + aurora).strip()

    return {"gps": gps, "comms": comms, "grids": grids, "aurora": aurora}

def emit_space_weather_json(now_ts: datetime, now_vals: dict, next_headline: str, confidence: str, alerts: list[str], sources_meta: dict):
    payload = {
        "timestamp_utc": now_ts.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z"),
        "now": {
            "kp": now_vals.get("kp_index"),
            "solar_wind_kms": now_vals.get("sw_speed_kms"),
            "bz_nt": now_vals.get("bz_nt"),
        },
        "next_72h": {
            "headline": next_headline,
            "confidence": confidence,
        },
        "alerts": alerts,
        "impacts": humanize_impacts(now_vals.get("kp_index"), now_vals.get("bz_nt")),
        "sources": sources_meta,
    }
    if not OUTPUT_JSON_PATH:
        print("[info] OUTPUT_JSON_PATH not set; skipping JSON file emission.")
        return
    _safe_mkdirs(OUTPUT_JSON_PATH)
    raw = json.dumps(payload, separators=(",",":"), ensure_ascii=False)
    if OUTPUT_JSON_GZIP:
        out_path = OUTPUT_JSON_PATH + ("" if OUTPUT_JSON_PATH.endswith(".gz") else ".gz")
        with gzip.open(out_path, "wb") as f:
            f.write(raw.encode("utf-8"))
        print(f"[info] Wrote gzipped space-weather JSON -> {out_path}")
    else:
        with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
            f.write(raw)
        print(f"[info] Wrote space-weather JSON -> {OUTPUT_JSON_PATH}")

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
    # Some products return { "data": [header, ...] }
    try:
        table = normalize_to_table(data)
    except Exception:
        raise ValueError(f"Unexpected JSON shape from {url}")
    if not isinstance(table, list) or not table:
        raise ValueError(f"Unexpected JSON shape from {url}")
    return table  # array-of-arrays: [ header_row, row1, row2, ... ]

async def fetch_any_json_array(client: httpx.AsyncClient, urls: list[str], label: str):
    last_err = None
    for u in urls:
        try:
            arr = await fetch_json_array(client, u)
            print(f"[info] {label} fetched from {u}")
            return arr
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

def normalize_to_table(data):
    """Accept SWPC JSON in one of:
       - [ [header...], [row...], ... ] (pass through)
       - { "data": [ [header...], [row...], ... ] } (unwrap data)
       - [ {k:v}, {k:v}, ... ] (array of dicts) -> [header, row...]
       - { k:v, ... } (single dict) -> [header, row]
       Returns a list. Raises ValueError if cannot normalize.
    """
    # Unwrap {"data": [...]}
    if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
        data = data["data"]
    # Already table
    if isinstance(data, list) and data and isinstance(data[0], list):
        return data
    # Array of dicts -> table
    if isinstance(data, list) and data and isinstance(data[0], dict):
        header = list(data[0].keys())
        rows = [[row.get(k) for k in header] for row in data]
        return [header] + rows
    # Single dict -> single-row table
    if isinstance(data, dict):
        header = list(data.keys())
        row = [data.get(k) for k in header]
        return [header, row]
    raise ValueError("Unexpected JSON shape")

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
    # Speed (km/s) appears as: 'windspeed', 'speed', 'V', 'proton_speed', 'solar_wind_speed', 'sw_speed'
    merge_metric(spd_recs, ["windspeed","speed","V","proton_speed","solar_wind_speed","sw_speed"], "sw_speed_kms", merged)
    # Bz (nT) appears as: 'bz_gsm', 'Bz', 'bz', 'bz_nt'
    merge_metric(mag_recs, ["bz_gsm","Bz","bz","bz_nt"], "bz_nt", merged)

    # Keep recent
    merged = filter_since(merged, SINCE_HOURS)

    # Compute latest snapshot for JSON emission with robust fallbacks
    latest_ts, latest_vals = latest_ts_and_vals(merged)
    if latest_vals is None:
        latest_vals = {}
    # Fallbacks: if any key missing in the latest entry, use the latest non-None value across the window
    if latest_vals.get("kp_index") is None:
        latest_vals["kp_index"] = latest_field_value(merged, "kp_index")
    if latest_vals.get("sw_speed_kms") is None:
        latest_vals["sw_speed_kms"] = latest_field_value(merged, "sw_speed_kms")
    if latest_vals.get("bz_nt") is None:
        latest_vals["bz_nt"] = latest_field_value(merged, "bz_nt")
    # Coerce types / rounding for clean JSON
    if latest_vals.get("kp_index") is not None:
        latest_vals["kp_index"] = round(_to_float_or_none(latest_vals["kp_index"]) or 0.0, 1)
    if latest_vals.get("sw_speed_kms") is not None:
        latest_vals["sw_speed_kms"] = int(round(_to_float_or_none(latest_vals["sw_speed_kms"]) or 0.0))
    if latest_vals.get("bz_nt") is not None:
        latest_vals["bz_nt"] = round(_to_float_or_none(latest_vals["bz_nt"]) or 0.0, 1)

    # alerts parsing for JSON (if any)
    alert_rows = [a for a in parse_alert_rows(alerts_arr) if a.get("issued_at")] if alerts_arr else []
    recent_alert_tags = extract_recent_alert_tags(alert_rows, hours=24)
    # headline/confidence from forecast
    next_headline, next_conf = parse_next72_headline(forecast_txt)
    sources_meta = {
        "kp_source": URLS_LIST["kp"][0] if URLS_LIST.get("kp") else None,
        "speed_source": URLS_LIST["speed"][0] if URLS_LIST.get("speed") else None,
        "mag_source": URLS_LIST["mag"][0] if URLS_LIST.get("mag") else None,
        "alerts_source": ALERTS_URL,
        "forecast_source": FORECAST_URL,
    }

    # Prepare rows for upsert
    rows = []
    for ts, v in sorted(merged.items()):
        meta = {
            "kp_source": URLS_LIST["kp"][0] if URLS_LIST.get("kp") else None,
            "speed_source": URLS_LIST["speed"][0] if URLS_LIST.get("speed") else None,
            "mag_source": URLS_LIST["mag"][0] if URLS_LIST.get("mag") else None,
        }
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

        # Emit dashboard JSON (best-effort)
        try:
            if latest_ts and latest_vals:
                emit_space_weather_json(latest_ts, latest_vals, next_headline, next_conf, recent_alert_tags, sources_meta)
            else:
                print("[warn] No latest space-weather values to emit JSON.")
        except Exception as e:
            print(f"[warn] Failed to emit space-weather JSON: {e}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
