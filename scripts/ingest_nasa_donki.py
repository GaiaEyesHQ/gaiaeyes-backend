#!/usr/bin/env python3
"""
Ingest NASA DONKI FLR (flares) and CME into ext.donki_event.

ENV:
  SUPABASE_DB_URL  (required)
  NASA_API_KEY     (required)
  START_DAYS_AGO   (default 7)  -- pulls events from now()-N days to today
"""

import os, sys, asyncio, json
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

async def fetch(client: httpx.AsyncClient, path: str, params: dict):
    r = await client.get(f"{BASE}/{path}", params=params, timeout=httpx.Timeout(45.0, connect=10.0))
    r.raise_for_status()
    return r.json()

async def main():
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=DAYS)
    params = {"startDate": iso_day(start), "endDate": iso_day(now), "api_key": KEY}

    async with httpx.AsyncClient() as client:
        flr = await fetch(client, "FLR", params)
        cme = await fetch(client, "CME", params)

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
