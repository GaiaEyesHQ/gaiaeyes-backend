#!/usr/bin/env python3
import asyncio, asyncpg, sys, pathlib, re
from datetime import date, datetime, timedelta

ROOT = pathlib.Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"

def load_database_url() -> str:
    if not ENV_PATH.exists():
        print(f".env not found at {ENV_PATH}"); sys.exit(2)
    m = re.search(r'^DATABASE_URL\s*=\s*(.+)$', ENV_PATH.read_text(), flags=re.MULTILINE)
    if not m:
        print("DATABASE_URL not found in .env"); sys.exit(2)
    url = m.group(1).strip().strip('"').strip("'")
    return url

DATABASE_URL = load_database_url()

HR_ALIASES    = ("heart_rate","hr","bpm")
HRV_ALIASES   = ("hrv","hrv_rmssd","heart_rate_variability","heart_rate_variability_rmssd","rmssd",
                 "hrv_sdnn","heart_rate_variability_sdnn","sdnn")
STEPS_ALIASES = ("steps","step_count","apple_move_steps")
SPO2_ALIASES  = ("spo2","oxygen_saturation")

SLEEP_REM     = ("sleep_rem",)
SLEEP_CORE    = ("sleep_core",)
SLEEP_DEEP    = ("sleep_deep",)
SLEEP_AWAKE   = ("sleep_awake",)

def sql_tuple(items):
    return "(" + ",".join("'" + x.replace("'", "''") + "'" for x in items) + ")"

HR_IN, HRV_IN, STEPS_IN, SPO2_IN = map(sql_tuple, (HR_ALIASES, HRV_ALIASES, STEPS_ALIASES, SPO2_ALIASES))
REM_IN, CORE_IN, DEEP_IN, AWAKE_IN = map(sql_tuple, (SLEEP_REM, SLEEP_CORE, SLEEP_DEEP, SLEEP_AWAKE))

AGG_SQL = f"""
with bounds as (
  select $2::date as d,
         ($2::date)::timestamptz at time zone 'utc' as start_ts,
         ($2::date + 1)::timestamptz at time zone 'utc' as end_ts
),
slice as (
  select s.*
  from gaia.samples s
  join bounds b
    on s.start_time >= b.start_ts
   and s.start_time <  b.end_ts
  where s.user_id = $1::uuid
),
hr as (
  select min(value) as hr_min, max(value) as hr_max
  from slice where type in {HR_IN}
),
hrv as (
  select avg(value) as hrv_avg
  from slice where type in {HRV_IN}
),
steps as (
  select sum(value) as steps_total
  from slice where type in {STEPS_IN}
),
spo2 as (
  select avg(value) as spo2_avg
  from slice where type in {SPO2_IN}
),
sleep as (
  select
    sum(case when type in {REM_IN}   then extract(epoch from (end_time - start_time))/60.0 end) as sleep_rem_minutes,
    sum(case when type in {CORE_IN}  then extract(epoch from (end_time - start_time))/60.0 end) as sleep_core_minutes,
    sum(case when type in {DEEP_IN}  then extract(epoch from (end_time - start_time))/60.0 end) as sleep_deep_minutes,
    sum(case when type in {AWAKE_IN} then extract(epoch from (end_time - start_time))/60.0 end) as sleep_awake_minutes
  from slice
),
sleep_tot as (
  select
    (coalesce(sleep_rem_minutes,0) + coalesce(sleep_core_minutes,0) + coalesce(sleep_deep_minutes,0))::numeric as sleep_total_minutes,
    sleep_rem_minutes, sleep_core_minutes, sleep_deep_minutes, sleep_awake_minutes,
    case when (coalesce(sleep_rem_minutes,0)+coalesce(sleep_core_minutes,0)+coalesce(sleep_deep_minutes,0)+coalesce(sleep_awake_minutes,0)) > 0
         then (coalesce(sleep_rem_minutes,0)+coalesce(sleep_core_minutes,0)+coalesce(sleep_deep_minutes,0))
              / (coalesce(sleep_rem_minutes,0)+coalesce(sleep_core_minutes,0)+coalesce(sleep_deep_minutes,0)+coalesce(sleep_awake_minutes,0))
         else null end as sleep_efficiency
  from sleep
)
insert into gaia.daily_summary as ds (
  user_id, date,
  hr_min, hr_max, hrv_avg, steps_total,
  sleep_total_minutes, sleep_rem_minutes, sleep_core_minutes, sleep_deep_minutes, sleep_awake_minutes, sleep_efficiency,
  spo2_avg, bp_sys_avg, bp_dia_avg, updated_at
)
select
  $1::uuid as user_id,
  b.d as date,
  (select hr_min  from hr),
  (select hr_max  from hr),
  (select hrv_avg from hrv),
  (select steps_total from steps),
  st.sleep_total_minutes, st.sleep_rem_minutes, st.sleep_core_minutes, st.sleep_deep_minutes, st.sleep_awake_minutes, st.sleep_efficiency,
  (select spo2_avg from spo2),
  (select avg(value) from slice where type in ('blood_pressure_systolic','bp_sys')) as bp_sys_avg,
  (select avg(value) from slice where type in ('blood_pressure_diastolic','bp_dia')) as bp_dia_avg,
  now()
from bounds b
cross join sleep_tot st
on conflict (user_id, date) do update
set hr_min = excluded.hr_min, hr_max = excluded.hr_max, hrv_avg = excluded.hrv_avg, steps_total = excluded.steps_total,
    sleep_total_minutes = excluded.sleep_total_minutes, sleep_rem_minutes = excluded.sleep_rem_minutes,
    sleep_core_minutes = excluded.sleep_core_minutes, sleep_deep_minutes = excluded.sleep_deep_minutes,
    sleep_awake_minutes = excluded.sleep_awake_minutes, sleep_efficiency = excluded.sleep_efficiency,
    spo2_avg = excluded.spo2_avg, bp_sys_avg = excluded.bp_sys_avg, bp_dia_avg = excluded.bp_dia_avg, updated_at = now();
"""

def parse_date(s: str) -> date:
    return datetime.fromisoformat(s).date()

async def run(user_id: str, start: date, end: date):
    conn = await asyncpg.connect(dsn=DATABASE_URL, statement_cache_size=0)
    try:
        cur = start
        while cur <= end:
            await conn.execute(AGG_SQL, user_id, cur)
            print(f"✔ Aggregated {cur.isoformat()} for {user_id}")
            cur += timedelta(days=1)
    finally:
        await conn.close()

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python workers/aggregate_range_standalone.py <USER_ID> <YYYY-MM-DD> <YYYY-MM-DD>")
        sys.exit(2)
    uid = sys.argv[1]; s = parse_date(sys.argv[2]); e = parse_date(sys.argv[3])
    if e < s: print("End date must be >= start date"); sys.exit(2)
    asyncio.run(run(uid, s, e))
