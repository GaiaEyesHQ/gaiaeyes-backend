from fastapi import APIRouter, HTTPException, Request
from datetime import date
from ..db import get_pool

router = APIRouter(tags=["summary"])

@router.get("/me/daily-summary")
async def get_daily_summary(request: Request, date: date):
    user_id = getattr(request.state, "user_id", None)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    pool = await get_pool()
    sql = "select * from gaia.daily_summary where user_id=$1 and date=$2"
    async with pool.acquire() as conn:
        row = await conn.fetchrow(sql, user_id, date)
        if not row:
            return {"date": str(date), "summary": None}
        rec = dict(row)
        rec["user_id"] = str(rec["user_id"])
        return {"date": str(date), "summary": rec}


# New endpoint: features_today
@router.get("/features/today")
async def features_today(request: Request):
    """
    Return today's features row with sleep_efficiency included.
    Uses America/Chicago for day bucketing and computes in-bed minutes on the fly
    from gaia.samples (type='sleep_stage', value_text in ['inbed','in_bed']).
    """
    # Optional auth check (consistent with other handlers):
    user_id = getattr(request.state, "user_id", None)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    pool = await get_pool()
    sql = """
    with sr as (
      select (start_time at time zone 'America/Chicago')::date as day,
             sum(case when lower(value_text) = 'rem'
                      then extract(epoch from (end_time - start_time))/60 end) as rem_m,
             sum(case when lower(value_text) = 'core'
                      then extract(epoch from (end_time - start_time))/60 end) as core_m,
             sum(case when lower(value_text) = 'deep'
                      then extract(epoch from (end_time - start_time))/60 end) as deep_m,
             sum(case when lower(value_text) = 'awake'
                      then extract(epoch from (end_time - start_time))/60 end) as awake_m,
             sum(case when lower(value_text) in ('inbed','in_bed')
                      then extract(epoch from (end_time - start_time))/60 end) as inbed_m
      from gaia.samples
      where type = 'sleep_stage'
      group by 1
    )
    select df.day,
           df.steps_total,
           df.hr_min,
           df.hrv_avg,
           df.spo2_avg,
           df.sleep_total_minutes,
           -- expose stage minutes (rounded) alongside total
           round(coalesce(sr.rem_m,   0)::numeric, 0) as rem_m,
           round(coalesce(sr.core_m,  0)::numeric, 0) as core_m,
           round(coalesce(sr.deep_m,  0)::numeric, 0) as deep_m,
           round(coalesce(sr.awake_m, 0)::numeric, 0) as awake_m,
           round(coalesce(sr.inbed_m, 0)::numeric, 0) as inbed_m,
           case when sr.inbed_m > 0
                then round((df.sleep_total_minutes::numeric / sr.inbed_m)::numeric, 3)
                else null end as sleep_efficiency,
           df.kp_max,
           df.bz_min,
           df.sw_speed_avg,
           df.flares_count,
           df.cmes_count,
           df.updated_at
    from marts.daily_features df
    left join sr on sr.day = df.day
    where df.day = (current_timestamp at time zone 'America/Chicago')::date
    limit 1
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(sql)
        if not row:
            return {"ok": True, "data": None}
        rec = dict(row)
        # Ensure JSON serializable types
        rec["day"] = str(rec["day"])
        return {"ok": True, "data": rec}
