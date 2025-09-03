# workers/aggregate.py
import os
import asyncio
import asyncpg
from datetime import date, datetime, timedelta, timezone

DSN = os.environ.get("DATABASE_URL")
if not DSN:
    raise SystemExit("Set DATABASE_URL in environment/.env")

def day_bounds_utc(d: date):
    start = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    return start, end

async def run_for_user_day(conn: asyncpg.Connection, user_id: str, d: date):
    start, end = day_bounds_utc(d)

    q = r"""
    insert into gaia.daily_summary as d (
      user_id, date,

      -- heart rate
      hr_min, hr_max,

      -- hrv + spo2
      hrv_avg, spo2_avg,

      -- blood pressure
      bp_sys_avg, bp_dia_avg,

      -- sleep aggregates (minutes)
      sleep_total_minutes,
      sleep_rem_minutes,
      sleep_core_minutes,
      sleep_deep_minutes,
      sleep_awake_minutes,
      sleep_efficiency,

      updated_at
    )
    select
      $1::uuid as user_id,
      $2::date  as date,

      -- HR min/max (bpm)
      (select min(value)::float8
         from gaia.samples
        where user_id = $1 and type = 'heart_rate'
          and start_time >= $3 and start_time < $4),
      (select max(value)::float8
         from gaia.samples
        where user_id = $1 and type = 'heart_rate'
          and start_time >= $3 and start_time < $4),

      -- HRV avg (ms)
      (select avg(value)::float8
         from gaia.samples
        where user_id = $1 and type = 'hrv_sdnn'
          and start_time >= $3 and start_time < $4),

      -- SpO2 avg (% 0–100)
      (select avg(value)::float8
         from gaia.samples
        where user_id = $1 and type = 'spo2'
          and start_time >= $3 and start_time < $4),

      -- Blood pressure (mmHg)
      (select avg(value)::float8
         from gaia.samples
        where user_id = $1 and type = 'blood_pressure_systolic'
          and start_time >= $3 and start_time < $4),
      (select avg(value)::float8
         from gaia.samples
        where user_id = $1 and type = 'blood_pressure_diastolic'
          and start_time >= $3 and start_time < $4),

      -- Sleep totals by stage (minutes)
      (
        select sum(extract(epoch from (least(end_time, $4) - greatest(start_time, $3))) / 60.0)
        from gaia.samples
        where user_id = $1 and type = 'sleep_stage'
          and start_time < $4 and end_time > $3
          and value_text in ('rem','core','deep','asleep') -- "asleep" as fallback
      )::float8,

      (
        select sum(extract(epoch from (least(end_time, $4) - greatest(start_time, $3))) / 60.0)
        from gaia.samples
        where user_id = $1 and type = 'sleep_stage'
          and start_time < $4 and end_time > $3
          and value_text = 'rem'
      )::float8,

      (
        select sum(extract(epoch from (least(end_time, $4) - greatest(start_time, $3))) / 60.0)
        from gaia.samples
        where user_id = $1 and type = 'sleep_stage'
          and start_time < $4 and end_time > $3
          and value_text = 'core'
      )::float8,

      (
        select sum(extract(epoch from (least(end_time, $4) - greatest(start_time, $3))) / 60.0)
        from gaia.samples
        where user_id = $1 and type = 'sleep_stage'
          and start_time < $4 and end_time > $3
          and value_text = 'deep'
      )::float8,

      (
        select sum(extract(epoch from (least(end_time, $4) - greatest(start_time, $3))) / 60.0)
        from gaia.samples
        where user_id = $1 and type = 'sleep_stage'
          and start_time < $4 and end_time > $3
          and value_text = 'awake'
      )::float8,

      -- sleep efficiency = asleep minutes / (asleep + awake minutes)
      (
        with mins as (
          select
            coalesce((
              select sum(extract(epoch from (least(end_time, $4) - greatest(start_time, $3))) / 60.0)
              from gaia.samples
              where user_id = $1 and type = 'sleep_stage'
                and start_time < $4 and end_time > $3
                and value_text in ('rem','core','deep','asleep')
            ), 0) as asleep_min,
            coalesce((
              select sum(extract(epoch from (least(end_time, $4) - greatest(start_time, $3))) / 60.0)
              from gaia.samples
              where user_id = $1 and type = 'sleep_stage'
                and start_time < $4 and end_time > $3
                and value_text = 'awake'
            ), 0) as awake_min
        )
        select case when (asleep_min + awake_min) > 0
                    then asleep_min / (asleep_min + awake_min)
                    else null end
        from mins
      )::float8,

      now()
    on conflict (user_id, date) do update set
      hr_min = excluded.hr_min,
      hr_max = excluded.hr_max,
      hrv_avg = excluded.hrv_avg,
      spo2_avg = excluded.spo2_avg,
      bp_sys_avg = excluded.bp_sys_avg,
      bp_dia_avg = excluded.bp_dia_avg,
      sleep_total_minutes = excluded.sleep_total_minutes,
      sleep_rem_minutes   = excluded.sleep_rem_minutes,
      sleep_core_minutes  = excluded.sleep_core_minutes,
      sleep_deep_minutes  = excluded.sleep_deep_minutes,
      sleep_awake_minutes = excluded.sleep_awake_minutes,
      sleep_efficiency    = excluded.sleep_efficiency,
      updated_at = now();
    """

    await conn.execute(q, user_id, d, start, end)

async def main():
    conn = await asyncpg.connect(dsn=DSN, statement_cache_size=0)
    try:
        users = await conn.fetch("select id from gaia.users")
        days = 14  # aggregate last 14 days for all users
        for u in users:
            uid = str(u["id"])
            for i in range(days):
                d = (datetime.now(timezone.utc).date() - timedelta(days=i))
                await run_for_user_day(conn, uid, d)
                print(f"Aggregated {d} for {uid}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
