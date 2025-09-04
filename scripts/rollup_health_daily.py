#!/usr/bin/env python3
"""
Aggregate gaia.samples -> gaia.daily_summary for the last N days (all users).

ENV:
  SUPABASE_DB_URL  (required)
  DAYS_BACK        (default 7)                 # how many days to recompute
  USER_TZ          (default 'America/Chicago') # day bucketing timezone
"""

import os, sys, asyncio, asyncpg

def env(k, default=None, required=False):
    v = os.getenv(k, default)
    if required and (v is None or v == ""):
        print(f"Missing env: {k}", file=sys.stderr); sys.exit(2)
    return v

DB = env("SUPABASE_DB_URL", required=True)
DAYS_BACK = int(env("DAYS_BACK", "7"))
USER_TZ = env("USER_TZ", "America/Chicago")

SQL = f"""
with w as (
  select
    user_id,
    (start_time at time zone '{USER_TZ}')::date as day_local,
    type, value, value_text, start_time, end_time
  from gaia.samples
  where start_time >= date_trunc('day', (now() at time zone '{USER_TZ}')) - interval '{DAYS_BACK} days'
),

-- unify sleep minutes whether they come as 4 types or as 'sleep_stage' labels
sleep_rows as (
  select
    user_id, day_local,

    -- asleep minutes = rem + core + deep (via sleep_stage or dedicated types)
    sum(
      case
        when type in ('sleep_rem')
          or (type = 'sleep_stage' and lower(coalesce(value_text,'')) = 'rem')
        then extract(epoch from (end_time - start_time))/60.0
      end
    ) as rem_m,

    sum(
      case
        when type in ('sleep_core')
          or (type = 'sleep_stage' and lower(coalesce(value_text,'')) = 'core')
        then extract(epoch from (end_time - start_time))/60.0
      end
    ) as core_m,

    sum(
      case
        when type in ('sleep_deep')
          or (type = 'sleep_stage' and lower(coalesce(value_text,'')) = 'deep')
        then extract(epoch from (end_time - start_time))/60.0
      end
    ) as deep_m,

    -- out-of-sleep but in bed: inBed
    sum(
      case
        when type in ('sleep_in_bed','sleep_inbed')
          or (type = 'sleep_stage' and lower(coalesce(value_text,'')) in ('inbed','in_bed'))
        then extract(epoch from (end_time - start_time))/60.0
      end
    ) as inbed_m,

    -- awake while in bed
    sum(
      case
        when type in ('sleep_awake')
          or (type = 'sleep_stage' and lower(coalesce(value_text,'')) = 'awake')
        then extract(epoch from (end_time - start_time))/60.0
      end
    ) as awake_m

  from w
  where type in (
      'sleep_rem','sleep_core','sleep_deep','sleep_awake',
      'sleep_in_bed','sleep_inbed',    -- in case you add explicit types later
      'sleep_stage'
  )
  group by user_id, day_local
),

agg as (
  select
    user_id, day_local as day,

    -- HR min/max
    min(value) filter (where type = 'heart_rate') as hr_min,
    max(value) filter (where type = 'heart_rate') as hr_max,

    -- HRV (accept common aliases)
    avg(value) filter (where type in (
      'hrv','hrv_rmssd','hrv_sdnn','heart_rate_variability',
      'heart_rate_variability_rmssd','heart_rate_variability_sdnn',
      'rmssd','sdnn'
    )) as hrv_avg,

    -- Steps (aliases)
    sum(value) filter (where type in ('steps','step_count','apple_move_steps')) as steps_total,

    -- SpO2 average
    avg(value) filter (where type = 'spo2') as spo2_avg,

    -- Blood pressure
    avg(value) filter (where type in ('blood_pressure_systolic','bp_sys'))  as bp_sys_avg,
    avg(value) filter (where type in ('blood_pressure_diastolic','bp_dia')) as bp_dia_avg

  from w
  group by user_id, day_local
)

insert into gaia.daily_summary (
  user_id, date,
  hr_min, hr_max, hrv_avg, steps_total,
  sleep_total_minutes,               -- rem+core+deep
  sleep_rem_minutes, sleep_core_minutes, sleep_deep_minutes,
  sleep_awake_minutes,               -- awake in bed
  sleep_efficiency,                  -- asleep / (asleep + awake + inBed)
  spo2_avg, bp_sys_avg, bp_dia_avg,
  updated_at
)
select
  a.user_id, a.day,
  a.hr_min, a.hr_max, a.hrv_avg, a.steps_total,

  (coalesce(s.rem_m,0) + coalesce(s.core_m,0) + coalesce(s.deep_m,0))::numeric as sleep_total_minutes,
  s.rem_m, s.core_m, s.deep_m,
  s.awake_m,

  case
    when (coalesce(s.rem_m,0)+coalesce(s.core_m,0)+coalesce(s.deep_m,0)+coalesce(s.awake_m,0)+coalesce(s.inbed_m,0)) > 0
    then (coalesce(s.rem_m,0)+coalesce(s.core_m,0)+coalesce(s.deep_m,0))
         /
         (coalesce(s.rem_m,0)+coalesce(s.core_m,0)+coalesce(s.deep_m,0)+coalesce(s.awake_m,0)+coalesce(s.inbed_m,0))
    else null end as sleep_efficiency,

  a.spo2_avg, a.bp_sys_avg, a.bp_dia_avg,
  now()

from agg a
left join sleep_rows s
  on s.user_id = a.user_id and s.day_local = a.day

on conflict (user_id, date) do update
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
    updated_at          = now();
"""

async def main():
    conn = await asyncpg.connect(dsn=DB, statement_cache_size=0)
    try:
        await conn.execute(SQL)
        print(f"Rolled up last {DAYS_BACK} days into gaia.daily_summary (tz={USER_TZ})")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
