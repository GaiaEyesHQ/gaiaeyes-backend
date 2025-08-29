#!/usr/bin/env python3
"""
Daily rollup from ext.space_weather into marts.space_weather_daily.

ENV:
  SUPABASE_DB_URL (required)
  DAYS_BACK       (default 7)    -- recompute last N days (idempotent)
"""

import os, sys, asyncio, asyncpg
from datetime import datetime, timezone, timedelta

def env(k, default=None, required=False):
    v = os.getenv(k, default)
    if required and (v is None or v == ""):
        print(f"Missing env: {k}", file=sys.stderr); sys.exit(2)
    return v

DB = env("SUPABASE_DB_URL", required=True)
DAYS_BACK = int(env("DAYS_BACK", "7"))

UPSERT_SQL = """
insert into marts.space_weather_daily (day, kp_max, bz_min, sw_speed_avg, row_count, updated_at)
select
  date(ts_utc) as day,
  max(kp_index) as kp_max,
  min(bz_nt) as bz_min,
  avg(sw_speed_kms) as sw_speed_avg,
  count(*) as row_count,
  now() as updated_at
from ext.space_weather
where ts_utc >= date_trunc('day', now() - interval '%s days')
group by 1
on conflict (day) do update
set kp_max       = excluded.kp_max,
    bz_min       = excluded.bz_min,
    sw_speed_avg = excluded.sw_speed_avg,
    row_count    = excluded.row_count,
    updated_at   = now();
"""

async def main():
    conn = await asyncpg.connect(dsn=DB, statement_cache_size=0)
    try:
        await conn.execute(UPSERT_SQL % DAYS_BACK)
        print(f"Rolled up last {DAYS_BACK} days into marts.space_weather_daily")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
