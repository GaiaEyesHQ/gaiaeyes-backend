#!/usr/bin/env python3
"""
Join health daily summaries with space weather daily into marts.daily_features.

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
with src as (
  select
    s.user_id,
    s.date::date as day,

    -- health
    s.hr_min,
    s.hr_max,
    s.hrv_avg,
    s.steps_total,
    s.sleep_total_minutes,
    s.sleep_rem_minutes,
    s.sleep_core_minutes,
    s.sleep_deep_minutes,
    s.sleep_awake_minutes,
    s.sleep_efficiency,
    s.spo2_avg,
    s.bp_sys_avg,
    s.bp_dia_avg,

    -- space weather
    w.kp_max,
    w.bz_min,
    w.sw_speed_avg,
    w.flares_count,
    w.cmes_count

  from gaia.daily_summary s
  left join marts.space_weather_daily w
    on w.day = s.date::date
  where s.date >= date_trunc('day', now() - interval '{DAYS_BACK} days')
)
insert into marts.daily_features (
  user_id, day,
  hr_min, hr_max, hrv_avg, steps_total,
  sleep_total_minutes, sleep_rem_minutes, sleep_core_minutes, sleep_deep_minutes, sleep_awake_minutes, sleep_efficiency,
  spo2_avg, bp_sys_avg, bp_dia_avg,
  kp_max, bz_min, sw_speed_avg, flares_count, cmes_count,
  src, updated_at
)
select
  user_id, day,
  hr_min, hr_max, hrv_avg, steps_total,
  sleep_total_minutes, sleep_rem_minutes, sleep_core_minutes, sleep_deep_minutes, sleep_awake_minutes, sleep_efficiency,
  spo2_avg, bp_sys_avg, bp_dia_avg,
  kp_max, bz_min, sw_speed_avg, coalesce(flares_count,0), coalesce(cmes_count,0),
  'rollup-v1', now()
from src
on conflict (user_id, day) do update
set hr_min              = excluded.hr_min,
    hr_max              = excluded.hr_max,
    hrv_avg             = excluded.hrv_avg,
    steps_total         = excluded.steps_total,
    sleep_total_minutes = excluded.sleep_total_minutes,
    sleep_rem_minutes   = excluded.sleep_rem_minutes,
    sleep_core_minutes  = excluded.sleep_core_minutes,
    sleep_deep_minutes  = excluded.sleep_deep_minutes,
    sleep_awake_minutes = excluded.sleep_awake_minutes,
    sleep_efficiency    = excluded.sleep_efficiency,
    spo2_avg            = excluded.spo2_avg,
    bp_sys_avg          = excluded.bp_sys_avg,
    bp_dia_avg          = excluded.bp_dia_avg,
    kp_max              = excluded.kp_max,
    bz_min              = excluded.bz_min,
    sw_speed_avg        = excluded.sw_speed_avg,
    flares_count        = excluded.flares_count,
    cmes_count          = excluded.cmes_count,
    src                 = excluded.src,
    updated_at          = now();
"""

async def main():
    conn = await asyncpg.connect(dsn=DB, statement_cache_size=0)
    try:
        await conn.execute(UPSERT_SQL)
        print(f"Rolled up last {DAYS_BACK} days into marts.daily_features")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
