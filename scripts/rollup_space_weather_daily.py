#!/usr/bin/env python3
"""
Daily rollup from ext.space_weather (+ DONKI counts) into marts.space_weather_daily.

ENV:
  SUPABASE_DB_URL (required)
  DAYS_BACK       (default 30)   -- recompute last N days (idempotent)
"""

import os, sys, asyncio, asyncpg

def env(k, default=None, required=False):
    v = os.getenv(k, default)
    if required and (v is None or v == ""):
        print(f"Missing env: {k}", file=sys.stderr); sys.exit(2)
    return v

DB = env("SUPABASE_DB_URL", required=True)
DAYS_BACK = int(env("DAYS_BACK", "30"))

UPSERT_SQL = f"""
with sw as (
  select
    date(ts_utc) as day,
    max(kp_index)              as kp_max,
    min(bz_nt)                 as bz_min,
    avg(sw_speed_kms)          as sw_speed_avg,
    count(*)                   as row_count
  from ext.space_weather
  where ts_utc >= date_trunc('day', now() - interval '{DAYS_BACK} days')
  group by 1
),
dk as (
  select
    date(start_time) as day,
    count(*) filter (where event_type = 'FLR') as flares_count,
    count(*) filter (where event_type = 'CME') as cmes_count
  from ext.donki_event
  where start_time >= date_trunc('day', now() - interval '{DAYS_BACK} days')
  group by 1
)
insert into marts.space_weather_daily
  (day, kp_max, bz_min, sw_speed_avg, row_count, flares_count, cmes_count, updated_at)
select
  sw.day,
  sw.kp_max,
  sw.bz_min,
  sw.sw_speed_avg,
  sw.row_count,
  coalesce(dk.flares_count, 0),
  coalesce(dk.cmes_count, 0),
  now()
from sw
left join dk using (day)
on conflict (day) do update
set kp_max       = excluded.kp_max,
    bz_min       = excluded.bz_min,
    sw_speed_avg = excluded.sw_speed_avg,
    row_count    = excluded.row_count,
    flares_count = excluded.flares_count,
    cmes_count   = excluded.cmes_count,
    updated_at   = now();
"""

async def main():
    conn = await asyncpg.connect(dsn=DB, statement_cache_size=0)
    try:
        await conn.execute(UPSERT_SQL)
        print(f"Rolled up last {DAYS_BACK} days into marts.space_weather_daily (incl. DONKI counts)")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
