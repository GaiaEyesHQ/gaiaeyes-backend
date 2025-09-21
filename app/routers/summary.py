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
    ), pick as (
      select *
      from marts.daily_features df
      where df.day <= (current_timestamp at time zone 'America/Chicago')::date
      order by df.day desc
      limit 1
    ), diag as (
      select max(day) as max_day, count(*) as total_rows
      from marts.daily_features
    )
    select p.day,
           p.steps_total,
           p.hr_min,
           p.hrv_avg,
           p.spo2_avg,
           p.sleep_total_minutes,
           round(coalesce(sr.rem_m,   0)::numeric, 0) as rem_m,
           round(coalesce(sr.core_m,  0)::numeric, 0) as core_m,
           round(coalesce(sr.deep_m,  0)::numeric, 0) as deep_m,
           round(coalesce(sr.awake_m, 0)::numeric, 0) as awake_m,
           round(coalesce(sr.inbed_m, 0)::numeric, 0) as inbed_m,
           case when sr.inbed_m > 0
                then round((p.sleep_total_minutes::numeric / sr.inbed_m)::numeric, 3)
                else null end as sleep_efficiency,
           p.kp_max,
           p.bz_min,
           p.sw_speed_avg,
           p.flares_count,
           p.cmes_count,
           p.updated_at,
           d.max_day,
           d.total_rows
    from pick p
    left join sr on sr.day = p.day
    cross join diag d
    """
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(sql)
    except Exception as e:
        # Return structured response so clients don’t see a 500
        return {"ok": True, "data": None, "error": f"features_today query failed: {e}"}

    if not row:
        return {"ok": True, "data": None}

    rec = dict(row)
    rec["day"] = str(rec.get("day"))
    diagnostics = {"max_day": str(rec.pop("max_day", None)), "total_rows": rec.pop("total_rows", None)}
    return {"ok": True, "data": rec, "diagnostics": diagnostics}
