#!/usr/bin/env python3
"""
Ingest NASA DONKI FLR (flares) and CME into ext.donki_event.

ENV:
  SUPABASE_DB_URL  (required)
  NASA_API_KEY     (required)
  START_DAYS_AGO   (default 7)  -- pulls events from now()-N days to today
  OUTPUT_JSON_PATH  (optional) path to write flares_cmes.json (e.g., ../gaiaeyes-media/docs/data/flares_cmes.json)
  OUTPUT_JSON_GZIP  (optional) "true"/"false" to also write .gz
"""

import os, sys, asyncio, json, random, gzip, pathlib

# Helper to get environment variables with optional default and required flag
def env(k, default=None, required=False):
    v = os.getenv(k, default)
    if required and (v is None or v == ""):
        print(f"Missing env: {k}", file=sys.stderr)
        sys.exit(2)
    return v
from datetime import datetime, timedelta, timezone
import httpx, asyncpg

GOES_XRS_1DAY = os.getenv("GOES_XRS_1DAY_URL", "https://services.swpc.noaa.gov/json/goes/primary/xrays-1-day.json")

def flare_class_from_flux(flux_wm2: float) -> str | None:
    """
    Convert 1–8Å X-ray flux (W/m^2) to class string 'A0.0'..'X99.9'.
    """
    try:
        f = float(flux_wm2)
    except Exception:
        return None
    if f <= 0 or not (f < 1e2):
        return None
    # Determine band and magnitude
    if f >= 1e-4:
        band, base = "X", 1e-4
    elif f >= 1e-5:
        band, base = "M", 1e-5
    elif f >= 1e-6:
        band, base = "C", 1e-6
    elif f >= 1e-7:
        band, base = "B", 1e-7
    else:
        band, base = "A", 1e-8
    mag = f / base
    return f"{band}{mag:.1f}"

def parse_goes_long_flux(entry: dict) -> tuple[datetime | None, float | None]:
    """
    Try multiple common GOES XRS JSON shapes to extract time + long (1–8Å) flux.
    """
    if not isinstance(entry, dict):
        return None, None
    ts = entry.get("time_tag") or entry.get("time") or entry.get("timestamp") or entry.get("date_time")
    # common keys for long channel
    val = (
        entry.get("xrsb") or entry.get("long") or entry.get("flux") or
        entry.get("value") or entry.get("observed_flux") or entry.get("primary")
    )
    t = parse_iso(ts)
    try:
        v = float(val) if val is not None else None
    except Exception:
        v = None
    return t, v

async def fetch_goes_xrs(client: httpx.AsyncClient) -> list:
    """
    Fetch GOES XRS 1-day JSON. Returns list of entries (dicts) or [].
    """
    try:
        r = await client.get(GOES_XRS_1DAY, timeout=httpx.Timeout(45.0, connect=10.0))
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list):
            return data
    except Exception as e:
        print(f"[DONKI] GOES XRS fetch failed: {e}", file=sys.stderr)
    return []

def summarize_flares_from_goes(goes_list: list, now: datetime) -> dict:
    """
    Build flare summary using GOES long-channel flux.
    Picks max flux in last 24h and reports its class/time.
    """
    cutoff = now - timedelta(hours=24)
    max_flux = None
    max_time = None
    for e in goes_list or []:
        t, v = parse_goes_long_flux(e)
        if not t or t < cutoff or v is None:
            continue
        if (max_flux is None) or (v > max_flux):
            max_flux, max_time = v, t
    if max_flux is None:
        return {"max_24h": None, "recent": []}
    cls = flare_class_from_flux(max_flux)
    recent = [{"class": cls, "peak_utc": max_time.replace(microsecond=0).isoformat().replace("+00:00","Z")} ] if cls else []
    return {"max_24h": cls, "recent": recent}

OUTPUT_JSON_PATH = os.getenv("OUTPUT_JSON_PATH")
OUTPUT_JSON_GZIP = os.getenv("OUTPUT_JSON_GZIP", "false").strip().lower() in ("1","true","yes")

DB   = env("SUPABASE_DB_URL", required=True)
KEY  = env("NASA_API_KEY", required=True)
DAYS = int(env("START_DAYS_AGO", "7"))
RETRIES = int(env("DONKI_MAX_RETRIES", "5"))
RETRY_BASE_MS = int(env("DONKI_RETRY_BASE_MS", "500"))  # base backoff in milliseconds

# Optional: tune retries per base so we fail over to fallback faster
PRIMARY_RETRIES = int(env("DONKI_PRIMARY_RETRIES", str(RETRIES)))
FALLBACK_RETRIES = int(env("DONKI_FALLBACK_RETRIES", str(RETRIES)))

DAY_MODE = env("DONKI_DAY_MODE", "1").strip().lower() in ("1","true","yes","on")
DAY_SLEEP_MS = int(env("DONKI_DAY_SLEEP_MS", "600"))  # pause between day calls

# Primary (NASA Open APIs) + Fallback (CCMC DONKI WS on kauai)
BASE_PRIMARY = os.getenv("DONKI_BASE_PRIMARY", "https://api.nasa.gov/DONKI").rstrip("/")
BASE_FALLBACK = os.getenv("DONKI_BASE_FALLBACK", "https://kauai.ccmc.gsfc.nasa.gov/DONKI/WS/get").rstrip("/")
BASES = [BASE_PRIMARY, BASE_FALLBACK]

UPSERT = """
insert into ext.donki_event (event_id, event_type, start_time, peak_time, end_time, class, source, meta)
values ($1, $2, $3, $4, $5, $6, 'nasa-donki', $7::jsonb)
on conflict (event_id) do update
set start_time = excluded.start_time,
    peak_time  = excluded.peak_time,
    end_time   = excluded.end_time,
    class      = excluded.class,
    meta       = excluded.meta;
"""

FLARE_ORDER = {"A":0,"B":1,"C":2,"M":3,"X":4}

def parse_iso_to_utc(ts):
    dt = parse_iso(ts)
    if not dt:
        return None
    return dt.astimezone(timezone.utc)

def flare_key(cls: str):
    """Return tuple for sorting flare classes like 'C3.2', 'M1.0'."""
    if not cls or not isinstance(cls, str):
        return (-1, 0.0)
    cls = cls.strip().upper()
    band = cls[:1]
    mag = 0.0
    try:
        mag = float(cls[1:])
    except Exception:
        mag = 0.0
    return (FLARE_ORDER.get(band, -1), mag)

def summarize_flares(flr_list: list, now: datetime):
    """Return summary dict with max_24h class and recent list of peaks."""
    max_cls = None
    recent = []
    cutoff = now - timedelta(hours=24)
    for e in flr_list or []:
        cls = e.get("classType")
        peak = parse_iso_to_utc(e.get("peakTime"))
        if peak:
            if peak >= cutoff:
                recent.append({"class": cls, "peak_utc": peak.replace(microsecond=0).isoformat().replace("+00:00","Z")})
            if (max_cls is None) or (flare_key(cls) > flare_key(max_cls)):
                # consider only last 24h for max_24h
                if peak >= cutoff:
                    max_cls = cls
    # sort recent by time desc
    recent.sort(key=lambda x: x.get("peak_utc",""), reverse=True)
    return {"max_24h": max_cls, "recent": recent}

def earth_directed_from_analyses(cme_event: dict) -> bool|None:
    """
    Try to infer earth-directed from DONKI fields.
    Prefer explicit 'cmeAnalyses' bools; otherwise return None.
    """
    analyses = cme_event.get("cmeAnalyses") or cme_event.get("analyses") or []
    if isinstance(analyses, dict):
        analyses = [analyses]
    for a in analyses:
        ed = a.get("isEarthDirected")
        if isinstance(ed, bool):
            return ed
    return None

def summarize_cmes(cme_list: list, now: datetime):
    """Return last_72h simplified entries and headline."""
    cutoff = now - timedelta(hours=72)
    rows = []
    any_ed = False
    max_speed = 0
    for e in cme_list or []:
        st = parse_iso_to_utc(e.get("startTime"))
        if not st or st < cutoff:
            continue
        speed = None
        # speed may live in 'cmeAnalyses' entries
        analyses = e.get("cmeAnalyses") or []
        if isinstance(analyses, dict):
            analyses = [analyses]
        for a in analyses:
            sp = a.get("speed")
            if sp:
                try:
                    speed = int(round(float(sp)))
                    break
                except Exception:
                    pass
        ed = earth_directed_from_analyses(e)
        if ed is True:
            any_ed = True
        max_speed = max(max_speed, speed or 0)
        row = {
            "time_utc": st.replace(microsecond=0).isoformat().replace("+00:00","Z"),
            "speed_kms": speed,
            "earth_directed": ed
        }
        # Collapse by time_utc, prefer higher speed and any earth_directed=True
        # Use a dict keyed by time_utc
        if '___best_by_time' not in locals():
            ___best_by_time = {}
        k = row["time_utc"]
        prev = ___best_by_time.get(k)
        if prev is None:
            ___best_by_time[k] = row
        else:
            # prefer explicit True for earth_directed
            ed_prev = prev.get("earth_directed")
            take = False
            if (ed is True) and (ed_prev is not True):
                take = True
            elif (ed is ed_prev) or (ed is None and ed_prev is None):
                # tie on ED flag → prefer higher speed
                take = (row.get("speed_kms") or 0) > (prev.get("speed_kms") or 0)
            # else keep prev (e.g., prev True, new False/None)
            if take:
                ___best_by_time[k] = row
    # materialize collapsed rows
    rows = list((locals().get("___best_by_time") or {}).values())
    # sort desc
    rows.sort(key=lambda r: r["time_utc"], reverse=True)
    # Headline logic
    if not rows:
        headline = "No CMEs in last 72h"
    elif any_ed:
        headline = "Earth-directed CME possible"
    elif max_speed >= 1000:
        headline = "Fast CMEs observed"
    elif max_speed >= 600:
        headline = "Moderate CMEs in last 72h"
    else:
        headline = "No Earth-directed CMEs detected"
    return {"last_72h": rows, "headline": headline}

def emit_json_flares_cmes(now_ts: datetime, flr_summary: dict, cme_summary: dict, sources: dict):
    if not OUTPUT_JSON_PATH:
        print("[DONKI] OUTPUT_JSON_PATH not set; skipping JSON emission.")
        return
    payload = {
        "timestamp_utc": now_ts.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z"),
        "flares": flr_summary,
        "cmes": cme_summary,
        "sources": sources
    }
    p = pathlib.Path(OUTPUT_JSON_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, separators=(",",":"), ensure_ascii=False)
    if OUTPUT_JSON_GZIP:
        out = p if str(p).endswith(".gz") else pathlib.Path(str(p) + ".gz")
        with gzip.open(out, "wb") as f:
            f.write(raw.encode("utf-8"))
        print(f"[DONKI] wrote gz JSON -> {out}")
    else:
        with open(p, "w", encoding="utf-8") as f:
            f.write(raw)
        print(f"[DONKI] wrote JSON -> {p}")

def iso_day(d: datetime) -> str:
    return d.strftime("%Y-%m-%d")

def parse_iso(ts):
    if not ts: return None
    try:
        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(float(ts), tz=timezone.utc)
        s = str(ts)
        if s.endswith("Z"):
            return datetime.fromisoformat(s.replace("Z","+00:00"))
        return datetime.fromisoformat(s)
    except Exception:
        return None

def day_range(start_dt: datetime, end_dt: datetime):
    cur = datetime(year=start_dt.year, month=start_dt.month, day=start_dt.day, tzinfo=start_dt.tzinfo)
    end = datetime(year=end_dt.year, month=end_dt.month, day=end_dt.day, tzinfo=end_dt.tzinfo)
    while cur <= end:
        yield cur, min(end_dt, cur + timedelta(days=1))
        cur = cur + timedelta(days=1)

async def sleepy(ms: int):
    # add small jitter so parallel runners don't thump the API at once
    delay = (ms / 1000.0) + (random.random() * 0.35)
    await asyncio.sleep(delay)

async def fetch(client: httpx.AsyncClient, path: str, params: dict, retries: int = RETRIES, base_ms: int = RETRY_BASE_MS):
    """
    Fetch with retry/backoff across primary and fallback DONKI endpoints.
    - Tries NASA Open API first (requires api_key), then CCMC 'kauai' WS (no key).
    - Retries (per base) on 5xx/429; returns [] when both bases fail.
    """
    print(f"[DONKI] Bases in use: {BASES}", file=sys.stderr)
    for base in BASES:
        url = f"{base}/{path.lstrip('/')}"
        print(f"[DONKI] Trying {path} via {base} -> {url}", file=sys.stderr)
        attempt = 0
        max_retries = PRIMARY_RETRIES if base == BASES[0] else FALLBACK_RETRIES
        # Adjust params: CCMC WS does not accept api_key
        call_params = dict(params)
        if "kauai.ccmc.gsfc.nasa.gov" in base:
            call_params.pop("api_key", None)
        while True:
            try:
                r = await client.get(url, params=call_params, timeout=httpx.Timeout(45.0, connect=10.0))
                r.raise_for_status()
                data = r.json()
                # Some endpoints return dict on error; normalize to list-success
                if isinstance(data, dict):
                    # Unexpected payload (likely error) — treat as failure for this base
                    raise httpx.HTTPStatusError("Unexpected dict payload", request=r.request, response=r)
                return data
            except httpx.HTTPStatusError as e:
                status = e.response.status_code if e.response is not None else None
                retryable = (status == 429) or (status is not None and 500 <= status < 600)
                attempt += 1
                if retryable and attempt <= max_retries:
                    delay = (base_ms / 1000.0) * (2 ** (attempt - 1)) + (random.random() * 0.35)
                    print(f"[DONKI] {path} via {base} HTTP {status}; retry {attempt}/{max_retries} in {delay:.2f}s", file=sys.stderr)
                    await asyncio.sleep(delay)
                    continue
                # If this was not the last base, fall through to try next base
                print(f"[DONKI] {path} failed via {base} (HTTP {status}) after {attempt} attempts; {'trying next base' if base != BASES[-1] else 'no more bases'}.", file=sys.stderr)
                break
            except httpx.RequestError as e:
                attempt += 1
                if attempt <= max_retries:
                    delay = (base_ms / 1000.0) * (2 ** (attempt - 1)) + (random.random() * 0.35)
                    print(f"[DONKI] network error on {path} via {base}: {e!r}; retry {attempt}/{max_retries} in {delay:.2f}s", file=sys.stderr)
                    await asyncio.sleep(delay)
                    continue
                print(f"[DONKI] network error on {path} via {base} after {attempt} attempts; {'trying next base' if base != BASES[-1] else 'no more bases'}.", file=sys.stderr)
                break
    # Exhausted all bases
    return []

async def main():
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=DAYS)
    params = {"startDate": iso_day(start), "endDate": iso_day(now), "api_key": KEY}

    async with httpx.AsyncClient() as client:
        if DAY_MODE:
            flr_all, cme_all = [], []
            for d0, d1 in day_range(start, now):
                day_params = {"startDate": iso_day(d0), "endDate": iso_day(d1), "api_key": KEY}
                flr_day = await fetch(client, "FLR", day_params) or []
                await sleepy(int(DAY_SLEEP_MS/2))
                cme_day = await fetch(client, "CME", day_params) or []
                if flr_day:
                    flr_all.extend(flr_day)
                if cme_day:
                    cme_all.extend(cme_day)
                await sleepy(DAY_SLEEP_MS)
            flr, cme = flr_all, cme_all
        else:
            flr = await fetch(client, "FLR", params) or []
            cme = await fetch(client, "CME", params) or []

        # Also fetch GOES XRS for reliable flare max in last 24h
        goes = await fetch_goes_xrs(client)

    # Build JSON summaries
    now_ts = datetime.now(timezone.utc)
    flares_summary = summarize_flares(flr, now_ts)
    goes_summary = summarize_flares_from_goes(goes, now_ts)
    if goes_summary.get("max_24h"):
        flares_summary = goes_summary
    cmes_summary = summarize_cmes(cme, now_ts)
    sources_meta = {
        "flr_source": f"{BASE_PRIMARY}/FLR",
        "cme_source": f"{BASE_PRIMARY}/CME"
    }

    rows = []
    # FLR: fields: flrID, beginTime, peakTime, endTime, classType
    if isinstance(flr, list):
        for e in flr:
            eid = e.get("flrID") or e.get("eventID") or ("FLR-" + (e.get("beginTime") or e.get("activityID") or "unknown"))
            rows.append((
                eid, "FLR",
                parse_iso(e.get("beginTime")),
                parse_iso(e.get("peakTime")),
                parse_iso(e.get("endTime")),
                e.get("classType"),
                json.dumps(e),
            ))
    # CME: fields vary; often 'activityID', 'startTime'
    if isinstance(cme, list):
        for e in cme:
            eid = e.get("activityID") or e.get("eventID") or ("CME-" + (e.get("startTime") or "unknown"))
            rows.append((
                eid, "CME",
                parse_iso(e.get("startTime")),
                None, None,
                None,
                json.dumps(e),
            ))

    if not rows:
        print("No DONKI events in range.")
        return

    conn = await asyncpg.connect(dsn=DB, statement_cache_size=0)
    try:
        await conn.executemany(UPSERT, rows)
        print(f"Upserted {len(rows)} DONKI events")
        # Emit companion JSON for web/app dashboards
        try:
            emit_json_flares_cmes(now_ts, flares_summary, cmes_summary, sources_meta)
        except Exception as e:
            print(f"[DONKI] WARN: failed to emit flares_cmes.json: {e}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
