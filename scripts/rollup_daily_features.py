#!/usr/bin/env python3
"""
Join health daily summaries with space weather + Schumann (Tomsk & Cumiana)
into marts.daily_features.

Sources:
  - gaia.daily_summary              (health)
  - marts.space_weather_daily       (space weather + DONKI counts)
  - marts.schumann_daily            (daily Schumann by station_id)

Writes:
  - marts.daily_features            (Tomsk columns retained; Cumiana & fallback added)

ENV:
  SUPABASE_DB_URL  (required)  -- use Pooler DSN (sslmode=require)
  DAYS_BACK        (default 7) -- recompute last N days (idempotent)
"""

import os, sys, asyncio, asyncpg


def env(k: str, default: str | None = None, required: bool = False) -> str:
    v = os.getenv(k, default)
    if required and (v is None or v == ""):
        print(f"Missing env: {k}", file=sys.stderr)
        sys.exit(2)
    return v  # type: ignore[return-value]


DB = env("SUPABASE_DB_URL", required=True)
DAYS_BACK = int(env("DAYS_BACK", "7"))

SQL = f"""
with s as (
  select
    user_id,
    date::date as day,
    hr_min, hr_max, hrv_avg, steps_total,
    sleep_total_minutes, sleep_rem_minutes, sleep_core_minutes, sleep_deep_minutes, sleep_awake_minutes, sleep_efficiency,
    spo2_avg, bp_sys_avg, bp_dia_avg
  from gaia.daily_summary
  where date >= current_date - interval '{DAYS_BACK} days'
),
wx as (
  select
    day,
    kp_max, bz_min, sw_speed_avg,
    flares_count, cmes_count
  from marts.space_weather_daily
  where day >= current_date - interval '{DAYS_BACK} days'
),
sch_t as (  -- Tomsk
  select
    day,
    f0_avg_hz as t_f0,
    f1_avg_hz as t_f1,
    f2_avg_hz as t_f2,
    f3_avg_hz as t_f3,
    f4_avg_hz as t_f4,
    f5_avg_hz as t_f5
  from marts.schumann_daily
  where station_id = 'tomsk'
    and day >= current_date - interval '{DAYS_BACK} days'
),
sch_c as (  -- Cumiana
  select
    day,
    f0_avg_hz as c_f0,
    f1_avg_hz as c_f1,
    f2_avg_hz as c_f2,
    f3_avg_hz as c_f3,
    f4_avg_hz as c_f4,
    f5_avg_hz as c_f5
  from marts.schumann_daily
  where station_id = 'cumiana'
    and day >= current_date - interval '{DAYS_BACK} days'
)
insert into marts.daily_features (
  user_id, day,

  -- Health
  hr_min, hr_max, hrv_avg, steps_total,
  sleep_total_minutes, sleep_rem_minutes, sleep_core_minutes, sleep_deep_minutes, sleep_awake_minutes, sleep_efficiency,
  spo2_avg, bp_sys_avg, bp_dia_avg,

  -- Space weather (+ DONKI)
  kp_max, bz_min, sw_speed_avg, flares_count, cmes_count,

  -- Schumann (Tomsk, existing columns)
  schumann_station, sch_fundamental_avg_hz, sch_f1_avg_hz, sch_f2_avg_hz, sch_f3_avg_hz, sch_f4_avg_hz, sch_f5_avg_hz,

  -- Schumann (Cumiana, new columns)
  sch_cumiana_station, sch_cumiana_fundamental_avg_hz, sch_cumiana_f1_avg_hz, sch_cumiana_f2_avg_hz,
  sch_cumiana_f3_avg_hz, sch_cumiana_f4_avg_hz, sch_cumiana_f5_avg_hz,

  -- Schumann (fallback: prefer Tomsk, else Cumiana)
  sch_any_fundamental_avg_hz, sch_any_f1_avg_hz, sch_any_f2_avg_hz, sch_any_f3_avg_hz, sch_any_f4_avg_hz, sch_any_f5_avg_hz,

  src, updated_at
)
select
  s.user_id, s.day,

  -- Health
  s.hr_min, s.hr_max, s.hrv_avg, s.steps_total,
  s.sleep_total_minutes, s.sleep_rem_minutes, s.sleep_core_minutes, s.sleep_deep_minutes, s.sleep_awake_minutes, s.sleep_efficiency,
  s.spo2_avg, s.bp_sys_avg, s.bp_dia_avg,

  -- Space weather
  w.kp_max, w.bz_min, w.sw_speed_avg, w.flares_count, w.cmes_count,

  -- Tomsk
  case when t.t_f0 is not null then 'tomsk' else null end as schumann_station,
  t.t_f0, t.t_f1, t.t_f2, t.t_f3, t.t_f4, t.t_f5,

  -- Cumiana
  case when c.c_f0 is not null then 'cumiana' else null end as sch_cumiana_station,
  c.c_f0, c.c_f1, c.c_f2, c.c_f3, c.c_f4, c.c_f5,

  -- Fallback
  coalesce(t.t_f0, c.c_f0) as sch_any_fundamental_avg_hz,
  coalesce(t.t_f1, c.c_f1) as sch_any_f1_avg_hz,
  coalesce(t.t_f2, c.c_f2) as sch_any_f2_avg_hz,
  coalesce(t.t_f3, c.c_f3) as sch_any_f3_avg_hz,
  coalesce(t.t_f4, c.c_f4) as sch_any_f4_avg_hz,
  coalesce(t.t_f5, c.c_f5) as sch_any_f5_avg_hz,

  'rollup-v3', now()

from s
left join wx   w  on w.day  = s.day
left join sch_t t on t.day  = s.day
left join sch_c c on c.day  = s.day

on conflict (user_id, day) do update
set
  -- Health
  hr_min              = excluded.hr_min,
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

  -- Space weather
  kp_max              = excluded.kp_max,
  bz_min              = excluded.bz_min,
  sw_speed_avg        = excluded.sw_speed_avg,
  flares_count        = excluded.flares_count,
  cmes_count          = excluded.cmes_count,

  -- Tomsk
  schumann_station          = excluded.schumann_station,
  sch_fundamental_avg_hz    = excluded.sch_fundamental_avg_hz,
  sch_f1_avg_hz             = excluded.sch_f1_avg_hz,
  sch_f2_avg_hz             = excluded.sch_f2_avg_hz,
  sch_f3_avg_hz             = excluded.sch_f3_avg_hz,
  sch_f4_avg_hz             = excluded.sch_f4_avg_hz,
  sch_f5_avg_hz             = excluded.sch_f5_avg_hz,

  -- Cumiana
  sch_cumiana_station                  = excluded.sch_cumiana_station,
  sch_cumiana_fundamental_avg_hz       = excluded.sch_cumiana_fundamental_avg_hz,
  sch_cumiana_f1_avg_hz                = excluded.sch_cumiana_f1_avg_hz,
  sch_cumiana_f2_avg_hz                = excluded.sch_cumiana_f2_avg_hz,
  sch_cumiana_f3_avg_hz                = excluded.sch_cumiana_f3_avg_hz,
  sch_cumiana_f4_avg_hz                = excluded.sch_cumiana_f4_avg_hz,
  sch_cumiana_f5_avg_hz                = excluded.sch_cumiana_f5_avg_hz,

  -- Fallback
  sch_any_fundamental_avg_hz = excluded.sch_any_fundamental_avg_hz,
  sch_any_f1_avg_hz          = excluded.sch_any_f1_avg_hz,
  sch_any_f2_avg_hz          = excluded.sch_any_f2_avg_hz,
  sch_any_f3_avg_hz          = excluded.sch_any_f3_avg_hz,
  sch_any_f4_avg_hz          = excluded.sch_any_f4_avg_hz,
  sch_any_f5_avg_hz          = excluded.sch_any_f5_avg_hz,

  src                 = excluded.src,
  updated_at          = now();
"""


async def main():
    conn = await asyncpg.connect(dsn=DB, statement_cache_size=0)
    try:
        await conn.execute(SQL)
        print(f"✅ Rolled up last {DAYS_BACK} days into marts.daily_features (Tomsk+Cumiana)")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
