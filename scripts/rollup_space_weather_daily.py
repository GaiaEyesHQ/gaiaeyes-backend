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
    (array_agg(kp_index order by ts_utc desc) filter (where kp_index is not null))[1] as kp_now,
    (array_agg(bz_nt order by ts_utc desc) filter (where bz_nt is not null))[1] as bz_now,
    (array_agg(sw_speed_kms order by ts_utc desc) filter (where sw_speed_kms is not null))[1] as sw_speed_now_kms,
    max(ts_utc) filter (where kp_index is not null or bz_nt is not null or sw_speed_kms is not null) as now_ts,
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
),
ap_latest as (
  select d, hemisphere, hemispheric_power_gw
  from (
    select date(ts_utc) as d,
           hemisphere,
           hemispheric_power_gw,
           ts_utc,
           row_number() over (partition by date(ts_utc), hemisphere order by ts_utc desc) as rn
    from ext.aurora_power
    where ts_utc >= date_trunc('day', now() - interval '{DAYS_BACK} days')
  ) t
  where rn = 1
),
ap as (
  select d as day,
         max(hemispheric_power_gw) filter (where hemisphere = 'north') as aurora_hp_north_gw,
         max(hemispheric_power_gw) filter (where hemisphere = 'south') as aurora_hp_south_gw
  from ap_latest
  group by 1
)
insert into marts.space_weather_daily
  (day, kp_max, bz_min, sw_speed_avg, kp_now, bz_now, sw_speed_now, sw_speed_now_kms, now_ts,
   row_count, flares_count, cmes_count, aurora_hp_north_gw, aurora_hp_south_gw, updated_at)
select
  sw.day,
  sw.kp_max,
  sw.bz_min,
  sw.sw_speed_avg,
  sw.kp_now,
  sw.bz_now,
  sw.sw_speed_now_kms,
  sw.sw_speed_now_kms,
  sw.now_ts,
  sw.row_count,
  coalesce(dk.flares_count, 0),
  coalesce(dk.cmes_count, 0),
  ap.aurora_hp_north_gw,
  ap.aurora_hp_south_gw,
  now()
from sw
left join dk using (day)
left join ap using (day)
on conflict (day) do update
set kp_max       = excluded.kp_max,
    bz_min       = excluded.bz_min,
    sw_speed_avg = excluded.sw_speed_avg,
    kp_now       = excluded.kp_now,
    bz_now       = excluded.bz_now,
    sw_speed_now = excluded.sw_speed_now,
    sw_speed_now_kms = excluded.sw_speed_now_kms,
    now_ts       = excluded.now_ts,
    row_count    = excluded.row_count,
    flares_count = excluded.flares_count,
    cmes_count   = excluded.cmes_count,
    aurora_hp_north_gw = excluded.aurora_hp_north_gw,
    aurora_hp_south_gw = excluded.aurora_hp_south_gw,
    updated_at   = now();
"""

async def main():
    conn = await asyncpg.connect(dsn=DB, statement_cache_size=0)
    try:
        await conn.execute(UPSERT_SQL)
        print(f"Rolled up last {DAYS_BACK} days into marts.space_weather_daily (incl. DONKI counts + aurora power)")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
