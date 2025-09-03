import os, asyncio, asyncpg
from datetime import date, timedelta, datetime
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
sleep as (
  select sum(greatest(0, extract(epoch from (least(end_time, $4) - greatest(start_time, $3))))) / 60.0 as sleep_total_minutes
  from day where type='sleep'
)
insert into gaia.daily_summary
  (user_id, date, hr_min, hr_max, hrv_avg, steps_total, spo2_avg, sleep_total_minutes, updated_at)
values
  ($1, $2,
   (select hr_min from hr),(select hr_max from hr),
   (select hrv_avg from hrv),(select steps_total from steps),
   (select spo2_avg from spo2),(select sleep_total_minutes from sleep), now())
on conflict (user_id, date) do update set
  hr_min=excluded.hr_min, hr_max=excluded.hr_max, hrv_avg=excluded.hrv_avg,
  steps_total=excluded.steps_total, spo2_avg=excluded.spo2_avg,
  sleep_total_minutes=excluded.sleep_total_minutes, updated_at=now();
"""

async def run_for_user_day(conn, user_id, d):
    start = datetime.combine(d, datetime.min.time())
    end = start + timedelta(days=1)
    await conn.execute(Q, user_id, d, start, end)

async def main():
    pool = await asyncpg.create_pool(dsn=DATABASE_URL, min_size=1, max_size=5, statement_cache_size=0)
    async with pool.acquire() as conn:
        users = await conn.fetch("select id from gaia.users")
        days = [date.today() - timedelta(days=i) for i in range(0, 7)]
        for u in users:
            for d in days:
                await run_for_user_day(conn, u["id"], d)
    await pool.close()

if __name__ == "__main__":
    asyncio.run(main())
