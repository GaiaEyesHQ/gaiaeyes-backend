from fastapi import APIRouter, HTTPException, Request
from datetime import date
from ..db import get_pool
from psycopg.rows import dict_row
from os import getenv

router = APIRouter(tags=["summary"])

@router.get("/me/daily-summary")
async def get_daily_summary(request: Request, date: date):
    user_id = getattr(request.state, "user_id", None)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    pool = await get_pool()
    sql = "select * from gaia.daily_summary where user_id=%s and date=%s"
    async with pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(sql, (user_id, date))
            row = await cur.fetchone()
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
    media_base = getenv("MEDIA_BASE_URL", "").rstrip("/")
    pool = await get_pool()
    sql = """
    with pick as (
      select *
      from marts.daily_features
      order by day desc
      limit 1
    ),
    sr as (
      select (start_time at time zone 'America/Chicago')::date as day,
             sum(case when lower(value_text)='rem'  then extract(epoch from (end_time-start_time))/60 end) as rem_m,
             sum(case when lower(value_text)='core' then extract(epoch from (end_time-start_time))/60 end) as core_m,
             sum(case when lower(value_text)='deep' then extract(epoch from (end_time-start_time))/60 end) as deep_m,
             sum(case when lower(value_text)='awake'then extract(epoch from (end_time-start_time))/60 end) as awake_m,
             sum(case when lower(value_text) in ('inbed','in_bed')
                      then extract(epoch from (end_time-start_time))/60 end) as inbed_m
      from gaia.samples
      group by 1
    ),
    schu as (
      select s.day,
             s.station_id,
             s.f0_avg_hz, s.f1_avg_hz, s.f2_avg_hz, s.h3_avg_hz, s.h4_avg_hz,
             row_number() over (
               order by s.day desc,
                        case when s.station_id='tomsk' then 0 when s.station_id='cumiana' then 1 else 2 end
             ) as rn
      from marts.schumann_daily s
    ),
    post as (
      select p.day,
             p.title as post_title,
             p.caption as post_caption,
             p.body_markdown as post_body,
             p.hashtags as post_hashtags,
             row_number() over (order by p.day desc, p.updated_at desc) as rn
      from content.dailyposts p
      where p.platform = 'default'
    ),
    diag as (
      select max(day) as max_day, count(*) as total_rows from marts.daily_features
    )
    select p.day,
           p.steps_total,
           p.hr_min,
           p.hrv_avg,
           p.spo2_avg,
           (coalesce(sr2.rem_m,0)+coalesce(sr2.core_m,0)+coalesce(sr2.deep_m,0))::int as sleep_total_minutes,
           round(coalesce(sr2.rem_m,0)::numeric,0)  as rem_m,
           round(coalesce(sr2.core_m,0)::numeric,0) as core_m,
           round(coalesce(sr2.deep_m,0)::numeric,0) as deep_m,
           round(coalesce(sr2.awake_m,0)::numeric,0) as awake_m,
           round(coalesce(sr2.inbed_m,0)::numeric,0) as inbed_m,
           case when coalesce(sr2.inbed_m,0) > 0
                then round(((coalesce(sr2.rem_m,0)+coalesce(sr2.core_m,0)+coalesce(sr2.deep_m,0)) / sr2.inbed_m)::numeric, 3)
                else null end as sleep_efficiency,
           p.kp_max,
           p.bz_min,
           p.sw_speed_avg,
           p.flares_count,
           p.cmes_count,
           p.updated_at,
           sch.station_id  as sch_station,
           sch.f0_avg_hz   as sch_f0_hz,
           sch.f1_avg_hz   as sch_f1_hz,
           sch.f2_avg_hz   as sch_f2_hz,
           sch.h3_avg_hz   as sch_h3_hz,
           sch.h4_avg_hz   as sch_h4_hz,
           dp.post_title,
           dp.post_caption,
           dp.post_body,
           dp.post_hashtags,
           d.max_day,
           d.total_rows
    from pick p
    left join sr   sr2 on sr2.day = p.day
    left join schu sch on sch.rn = 1 and sch.day <= p.day
    left join post dp  on dp.rn = 1  and dp.day  <= p.day
    cross join diag d
    """
    try:
        async with pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(sql)
                row = await cur.fetchone()
    except Exception as e:
        # Return structured response so clients don’t see a 500
        return {"ok": True, "data": None, "error": f"features_today query failed: {e}"}

    # Always return diagnostics; data is present only when a day was picked
    if not row:
        return {"ok": True, "data": None, "diagnostics": {}}

    rec = dict(row)
    diagnostics = {"max_day": str(rec.pop("max_day", None)), "total_rows": rec.pop("total_rows", None)}

    if rec.get("day") is None:
        return {"ok": True, "data": None, "diagnostics": diagnostics}

    rec["day"] = str(rec.get("day"))

    if media_base:
        rec["earthscope_images"] = {
            "caption": f"{media_base}/images/daily_caption.jpg",
            "stats": f"{media_base}/images/daily_stats.jpg",
            "affects": f"{media_base}/images/daily_affects.jpg",
            "playbook": f"{media_base}/images/daily_playbook.jpg",
        }

    return {"ok": True, "data": rec, "diagnostics": diagnostics}
