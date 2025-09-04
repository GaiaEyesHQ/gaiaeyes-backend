#!/usr/bin/env python3
"""
Join health daily summaries with space weather daily + Schumann daily
into marts.daily_features.

ENV:
  SUPABASE_DB_URL   (required)
  DAYS_BACK         (default 30)  -- recompute last N days (idempotent)
  SCHUMANN_STATION  (default 'tomsk')  -- station_id from ext.schumann (e.g., 'tomsk' or 'cumiana')
"""

import os, sys, asyncio, asyncpg

def env(k, default=None, required=False):
    v = os.getenv(k, default)
    if required and (v is None or v == ""):
        print(f"Missing env: {k}", file=sys.stderr); sys.exit(2)
    return v

DB = env("SUPABASE_DB_URL", required=True)
DAYS_BACK = int(env("DAYS_BACK", "30"))
SCH_STATION = env("SCHUMANN_STATION", "tomsk")  # 'tomsk' or 'cumiana'

UPSERT_SQL = f"""
with s as (
  select
    user_id,
    date::date as day,
    hr_min, hr_max, hrv_avg, steps_total,
    sleep_total_minutes, sleep_rem_minutes, sleep_core_minutes, sleep_deep_minutes,
    sleep_awake_minutes, sleep_efficiency,
    spo2_avg, bp_sys_avg, bp_dia_avg
  from gaia.daily_summary
  where date >= date_trunc('day', now() - interval '{DAYS_BACK} days')
),
wx as (
  select
    day,
    kp_max, bz_min, sw_speed_avg,
    flares_count, cmes_count
  from marts.space_weather_daily
  where day >= date_trunc('day', now() - interval '{DAYS_BACK} days')
),
sch as (
  -- aggregate Schumann by chosen station_id
  select
    station_id,
    date(ts_utc) as day,
    avg(value_num) filter (where channel = 'fundamental_hz') as sch_fundamental_avg_hz,
    avg(value_num) filter (where channel = 'F1')            as sch_f1_avg_hz,
    avg(value_num) filter (where channel = 'F2')            as sch_f2_avg_hz,
    avg(value_num) filter (where channel = 'F3')            as sch_f3_avg_hz,
    avg(value_num) filter (where channel = 'F4')            as sch_f4_avg_hz,
    avg(value_num) filter (where channel = 'F5')            as sch_f5_avg_hz
  from ext.schumann
  where station_id = $1
    and ts_utc >= date_trunc('day', now() - interval '{DAYS_BACK} days')
  group by station_id, date(ts_utc)
)
insert into marts.daily_features (
  user_id, day,
  hr_min, hr_max, hrv_avg, steps_total,
  sleep_total_minutes, sleep_rem_minutes, sleep_core_minutes, sleep_deep_minutes, sleep_awake_minutes, sleep_efficiency,
  spo2_avg, bp_sys_avg, bp_dia_avg,
  kp_max, bz_min, sw_speed_avg, flares_count, cmes_count,
  schumann_station, sch_fundamental_avg_hz, sch_f1_avg_hz, sch_f2_avg_hz, sch_f3_avg_hz, sch_f4_avg_hz, sch_f5_avg_hz,
  src, updated_at
)
select
  s.user_id, s.day,
  s.hr_min, s.hr_max, s.hrv_avg, s.steps_total,
  s.sleep_total_minutes, s.sleep_rem_minutes, s.sleep_core_minutes, s.sleep_deep_minutes, s.sleep_awake_minutes, s.sleep_efficiency,
  s.spo2_avg, s.bp_sys_avg, s.bp_dia_avg,
  w.kp_max, w.bz_min, w.sw_speed_avg, w.flares_count, w.cmes_count,
  coalesce(sc.station_id, $1) as schumann_station,
  sc.sch_fundamental_avg_hz, sc.sch_f1_avg_hz, sc.sch_f2_avg_hz, sc.sch_f3_avg_hz, sc.sch_f4_avg_hz, sc.sch_f5_avg_hz,
  'rollup-v2', now()
from s
left join wx  w  on w.day  = s.day
left join sch sc on sc.day = s.day
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
    schumann_station          = excluded.schumann_station,
    sch_fundamental_avg_hz    = excluded.sch_fundamental_avg_hz,
    sch_f1_avg_hz             = excluded.sch_f1_avg_hz,
    sch_f2_avg_hz             = excluded.sch_f2_avg_hz,
    sch_f3_avg_hz             = excluded.sch_f3_avg_hz,
    sch_f4_avg_hz             = excluded.sch_f4_avg_hz,
    sch_f5_avg_hz             = excluded.sch_f5_avg_hz,
    src                 = excluded.src,
    updated_at          = now();
"""

async def main():
    conn = await asyncpg.connect(dsn=DB, statement_cache_size=0)
    try:
        await conn.execute(UPSERT_SQL, SCH_STATION)
        print(f"Rolled up last {DAYS_BACK} days into marts.daily_features with Schumann ({SCH_STATION})")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
