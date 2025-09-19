#!/usr/bin/env python3
"""
Ingest NASA DONKI FLR (flares) and CME into ext.donki_event.

ENV:
  SUPABASE_DB_URL  (required)
  NASA_API_KEY     (required)
  START_DAYS_AGO   (default 7)  -- pulls events from now()-N days to today
"""

import os, sys, asyncio, json, random
from datetime import datetime, timedelta, timezone
import httpx, asyncpg

def env(k, default=None, required=False):
    v = os.getenv(k, default)
    if required and (v is None or v == ""):
        print(f"Missing env: {k}", file=sys.stderr); sys.exit(2)
    return v

DB   = env("SUPABASE_DB_URL", required=True)
KEY  = env("NASA_API_KEY", required=True)
DAYS = int(env("START_DAYS_AGO", "7"))
RETRIES = int(env("DONKI_MAX_RETRIES", "5"))
RETRY_BASE_MS = int(env("DONKI_RETRY_BASE_MS", "500"))  # base backoff in milliseconds

DAY_MODE = env("DONKI_DAY_MODE", "1").strip().lower() in ("1","true","yes","on")
DAY_SLEEP_MS = int(env("DONKI_DAY_SLEEP_MS", "600"))  # pause between day calls

BASE = "https://api.nasa.gov/DONKI"

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
    Fetch with retry/backoff. Retries on 5xx and 429. Returns [] on exhausted retries.
    """
    url = f"{BASE}/{path}"
    attempt = 0
    while True:
        try:
            r = await client.get(url, params=params, timeout=httpx.Timeout(45.0, connect=10.0))
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as e:
            status = e.response.status_code if e.response is not None else None
            retryable = (status == 429) or (status is not None and 500 <= status < 600)
            attempt += 1
            if retryable and attempt <= retries:
                # exponential backoff with jitter
                delay = (base_ms / 1000.0) * (2 ** (attempt - 1)) + (random.random() * 0.25)
                print(f"[DONKI] {path} got HTTP {status}; retry {attempt}/{retries} in {delay:.2f}s", file=sys.stderr)
                await asyncio.sleep(delay)
                continue
            if retryable:
                print(f"[DONKI] {path} failed after {retries} retries with HTTP {status}; skipping.", file=sys.stderr)
                return []
            # non-retryable
            raise
        except httpx.RequestError as e:
            attempt += 1
            if attempt <= retries:
                delay = (base_ms / 1000.0) * (2 ** (attempt - 1)) + (random.random() * 0.25)
                print(f"[DONKI] network error on {path}: {e!r}; retry {attempt}/{retries} in {delay:.2f}s", file=sys.stderr)
                await asyncio.sleep(delay)
                continue
            print(f"[DONKI] network error on {path}; exhausted retries; skipping.", file=sys.stderr)
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
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
