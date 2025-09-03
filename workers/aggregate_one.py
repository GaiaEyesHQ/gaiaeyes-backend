import os, sys, asyncio, asyncpg
from datetime import datetime, date, timedelta
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DIRECT_URL") or os.getenv("DATABASE_URL")

Q = """
with day as (
  select * from gaia.samples
  where user_id=$1 and start_time >= $3 and start_time < $4
),
hr as (select min(value_text::numeric) hr_min, max(value_text::numeric) hr_max from day where type='heart_rate'),
hrv as (select avg(value_text::numeric) hrv_avg from day where type='hrv'),
steps as (select sum(value_text::numeric) steps_total from day where type='steps'),
spo2 as (select avg(value_text::numeric) spo2_avg from day where type='spo2'),
sleep_intervals as (
  select start_time, end_time, lower(value_text) as stage
  from day
  where type in ('sleep','sleep_stage')
),
sleep_minutes as (
  select
    sum(case when stage='rem'  then greatest(0, extract(epoch from (least(end_time,$4)-greatest(start_time,$3)))) else 0 end)/60.0 as rem_min,
    sum(case when stage='core' then greatest(0, extract(epoch from (least(end_time,$4)-greatest(start_time,$3)))) else 0 end)/60.0 as core_min,
    sum(case when stage='deep' then greatest(0, extract(epoch from (least(end_time,$4)-greatest(start_time,$3)))) else 0 end)/60.0 as deep_min,
    sum(case when stage='awake'then greatest(0, extract(epoch from (least(end_time,$4)-greatest(start_time,$3)))) else 0 end)/60.0 as awake_min,
    sum(case when stage='inbed'then greatest(0, extract(epoch from (least(end_time,$4)-greatest(start_time,$3)))) else 0 end)/60.0 as inbed_min
  from sleep_intervals
),
sleep_rollup as (
  select
    coalesce(rem_min,0)  as rem_min,
    coalesce(core_min,0) as core_min,
    coalesce(deep_min,0) as deep_min,
    coalesce(awake_min,0) as awake_min,
    coalesce(inbed_min, null) as inbed_min,
    coalesce(rem_min,0)+coalesce(core_min,0)+coalesce(deep_min,0) as asleep_min
  from sleep_minutes
),
sleep_final as (
  select
    rem_min, core_min, deep_min, awake_min,
    case when inbed_min is not null then inbed_min else asleep_min + awake_min end as inbed_total,
    asleep_min
  from sleep_rollup
)
insert into gaia.daily_summary
  (user_id, date, hr_min, hr_max, hrv_avg, steps_total, spo2_avg,
   sleep_total_minutes, sleep_rem_minutes, sleep_core_minutes, sleep_deep_minutes, sleep_awake_minutes, sleep_efficiency, updated_at)
values
  ($1, $2,
   (select hr_min from hr),(select hr_max from hr),
   (select hrv_avg from hrv),(select steps_total from steps),(select spo2_avg from spo2),
   (select asleep_min from sleep_final),
   (select rem_min from sleep_final),
   (select core_min from sleep_final),
   (select deep_min from sleep_final),
   (select awake_min from sleep_final),
   (select case when inbed_total > 0 then asleep_min / inbed_total else null end from sleep_final),
   now())
on conflict (user_id, date) do update set
  hr_min=excluded.hr_min, hr_max=excluded.hr_max, hrv_avg=excluded.hrv_avg,
  steps_total=excluded.steps_total, spo2_avg=excluded.spo2_avg,
  sleep_total_minutes=excluded.sleep_total_minutes,
  sleep_rem_minutes=excluded.sleep_rem_minutes,
  sleep_core_minutes=excluded.sleep_core_minutes,
  sleep_deep_minutes=excluded.sleep_deep_minutes,
  sleep_awake_minutes=excluded.sleep_awake_minutes,
  sleep_efficiency=excluded.sleep_efficiency,
  updated_at=now();
"""

async def run(date_str: str, user_id: str):
    d = date.fromisoformat(date_str)
    start = datetime.combine(d, datetime.min.time())
    end = start + timedelta(days=1)
    pool = await asyncpg.create_pool(dsn=DATABASE_URL, min_size=1, max_size=5, statement_cache_size=0)
    async with pool.acquire() as conn:
        await conn.execute(Q, user_id, d, start, end)
    await pool.close()
    print("Aggregated", date_str, "for", user_id)

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python workers/aggregate_one.py YYYY-MM-DD USER_ID")
        sys.exit(1)
    asyncio.run(run(sys.argv[1], sys.argv[2]))
