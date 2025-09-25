from fastapi import APIRouter, HTTPException, Request
from datetime import date, timezone
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
             sum(case when lower(value_text) in ('inbed','in_bed') then extract(epoch from (end_time-start_time))/60 end) as inbed_m
      from gaia.samples
      group by 1
    ),
    diag as (
      select max(day) as max_day, count(*) as total_rows from marts.daily_features
    )
    select p.day,
           p.steps_total,
           p.hr_min,
           p.hr_max,
           p.hrv_avg,
           p.spo2_avg,
           p.bp_sys_avg,
           p.bp_dia_avg,
           (coalesce(sr2.rem_m,0)+coalesce(sr2.core_m,0)+coalesce(sr2.deep_m,0))::int as sleep_total_minutes,
           round(coalesce(sr2.rem_m,0)::numeric,0)  as rem_m,
           round(coalesce(sr2.core_m,0)::numeric,0) as core_m,
           round(coalesce(sr2.deep_m,0)::numeric,0) as deep_m,
           round(coalesce(sr2.awake_m,0)::numeric,0) as awake_m,
           round(coalesce(sr2.inbed_m,0)::numeric,0) as inbed_m,
           case when coalesce(sr2.inbed_m,0) > 0
                then round(((coalesce(sr2.rem_m,0)+coalesce(sr2.core_m,0)+coalesce(sr2.deep_m,0)) / sr2.inbed_m)::numeric, 3)
                else null end as sleep_efficiency,
           cur_kp.kp_current,
           cur_bz.bz_current,
           cur_sw.sw_speed_current,
           (case when p.kp_max >= 5 then true else false end) as kp_alert,
           (case when p.flares_count > 0 then true else false end) as flare_alert,
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
           sch.f3_avg_hz   as sch_h3_hz,
           sch.f4_avg_hz   as sch_h4_hz,
           dp.post_title,
           dp.post_caption,
           dp.post_body,
           dp.post_hashtags,
           d.max_day,
           d.total_rows
    from pick p
    left join sr   sr2 on sr2.day = p.day
    -- latest Kp row (independent)
    left join LATERAL (
      select kp_index as kp_current
      from ext.space_weather
      where ts_utc <= now() and kp_index is not null
      order by ts_utc desc
      limit 1
    ) cur_kp on true

    -- latest Bz row (independent)
    left join LATERAL (
      select bz_nt as bz_current
      from ext.space_weather
      where ts_utc <= now() and bz_nt is not null
      order by ts_utc desc
      limit 1
    ) cur_bz on true

    -- latest Solar Wind speed row (independent)
    left join LATERAL (
      select sw_speed_kms as sw_speed_current
      from ext.space_weather
      where ts_utc <= now() and sw_speed_kms is not null
      order by ts_utc desc
      limit 1
    ) cur_sw on true
    -- pick latest Schumann row on or before the picked day, preferring tomsk over cumiana
    left join LATERAL (
      select s.station_id,
             s.f0_avg_hz, s.f1_avg_hz, s.f2_avg_hz, s.f3_avg_hz, s.f4_avg_hz
      from marts.schumann_daily s
      where s.station_id in ('tomsk','cumiana')
        and s.day <= p.day
      order by s.day desc,
               case when s.station_id='tomsk' then 0 when s.station_id='cumiana' then 1 else 2 end
      limit 1
    ) sch on true
    -- pick latest Earthscope default post on or before the picked day
    left join LATERAL (
      select p0.title as post_title,
             p0.caption as post_caption,
             p0.body_markdown as post_body,
             p0.hashtags as post_hashtags
      from content.daily_posts p0
      where p0.platform = 'default'
        and p0.day <= p.day
      order by p0.day desc, p0.updated_at desc
      limit 1
    ) dp on true
    cross join diag d
    """
    try:
        async with pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(sql, prepare=False)
                row = await cur.fetchone()
    except Exception as e:
        return {"ok": True, "data": None, "error": f"features_today query failed: {e}"}

    if not row:
        return {"ok": True, "data": None}

    rec = dict(row)
    rec["day"] = str(rec.get("day"))
    diagnostics = {"max_day": str(rec.pop("max_day", None)), "total_rows": rec.pop("total_rows", None)}
    if media_base:
        rec["earthscope_images"] = {
            "caption": f"{media_base}/images/daily_caption.jpg",
            "stats": f"{media_base}/images/daily_stats.jpg",
            "affects": f"{media_base}/images/daily_affects.jpg",
            "playbook": f"{media_base}/images/daily_playbook.jpg",
        }
    return {"ok": True, "data": rec, "diagnostics": diagnostics}

@router.get("/space/forecast/summary")
async def forecast_summary():
    """
    Return a compact summary of the latest SWPC 3-day geomagnetic forecast.
    Assumes the ingester stores raw text in ext.space_forecast (fetched_at, body_text).
    """
    pool = await get_pool()
    sql = """
      select fetched_at, body_text
      from ext.space_forecast
      order by fetched_at desc
      limit 1
    """
    try:
        async with pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(sql)
                row = await cur.fetchone()
    except Exception as e:
        return {"ok": True, "data": None, "error": f"forecast_summary query failed: {e}"}

    if not row:
        return {"ok": True, "data": None}

    fetched_at = None
    try:
        # ensure ISO-8601 UTC string
        fetched_at = row["fetched_at"].astimezone(timezone.utc).isoformat() if row.get("fetched_at") else None
    except Exception:
        fetched_at = None

    body = (row.get("body_text") or "").strip()
    if not body:
        return {"ok": True, "data": {"fetched_at": fetched_at, "headline": None, "lines": None, "body": None}}

    # Heuristic: filter boilerplate (lines starting with ':' or '#'),
    # pick first remaining as headline, then collect up to 4 concise points
    raw_lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    # drop NOAA headers like ':Product:', ':Issued:', '# Prepared by', etc.
    lines = [ln for ln in raw_lines if not ln.startswith((':', '#'))]

    headline = lines[0] if lines else None

    bullets = []
    for ln in lines[1:]:
        if ln.startswith(("-", "*", "•")) or len(ln) <= 120:
            cleaned = ln.lstrip("-*• ")
            bullets.append(cleaned)
        if len(bullets) >= 4:
            break

    return {
        "ok": True,
        "data": {
            "fetched_at": fetched_at,
            "headline": headline,
            "lines": bullets if bullets else None,
            "body": None
        }
    }

@router.get("/space/series")
async def space_series(request: Request, days: int = 7):
    """
    Return timeseries for space weather (kp, bz, sw) and daily Schumann (f0/f1/f2)
    for the last N days. Intended for lightweight charting in the app.
    """
    days = max(1, min(days, 31))
    user_id = getattr(request.state, "user_id", None)
    pool = await get_pool()
    try:
        async with pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                # Space weather raw (latest values over window)
                await cur.execute(
                    """
                    select ts_utc, kp_index as kp, bz_nt as bz, sw_speed_kms as sw
                    from ext.space_weather
                    where ts_utc >= now() - %s::interval
                    order by ts_utc asc
                    """,
                    (f"{days} days",),
                    prepare=False,
                )
                sw_rows = await cur.fetchall()

                # Schumann daily (prefer tomsk over cumiana per day)
                await cur.execute(
                    """
                    with d as (
                      select day, station_id, f0_avg_hz, f1_avg_hz, f2_avg_hz,
                             row_number() over (partition by day
                               order by case when station_id='tomsk' then 0
                                             when station_id='cumiana' then 1
                                        else 2 end) as rn
                      from marts.schumann_daily
                      where day >= (current_date - %s::interval)::date
                    )
                    select day, station_id, f0_avg_hz, f1_avg_hz, f2_avg_hz
                    from d where rn=1
                    order by day asc
                    """,
                    (f"{days} days",),
                    prepare=False,
                )
                sch_rows = await cur.fetchall()

                # Daily HR min/max for the current user
                hr_rows = []
                if user_id is not None:
                    await cur.execute(
                        """
                        select date as day, hr_min, hr_max
                        from gaia.daily_summary
                        where user_id = %s
                          and date >= (current_date - %s::interval)::date
                        order by day asc
                        """,
                        (user_id, f"{days} days"),
                        prepare=False,
                    )
                    hr_rows = await cur.fetchall()
    except Exception as e:
        return {"ok": True, "data": None, "error": f"space_series query failed: {e}"}

    # Normalize to simple lists of dicts the app can chart easily
    sw_list = []
    for r in sw_rows or []:
        sw_list.append({
            "ts": r.get("ts_utc").astimezone(timezone.utc).isoformat() if r.get("ts_utc") else None,
            "kp": r.get("kp"),
            "bz": r.get("bz"),
            "sw": r.get("sw"),
        })

    sch_list = []
    for r in sch_rows or []:
        sch_list.append({
            "day": str(r.get("day")) if r.get("day") is not None else None,
            "station_id": r.get("station_id"),
            "f0": r.get("f0_avg_hz"),
            "f1": r.get("f1_avg_hz"),
            "f2": r.get("f2_avg_hz"),
        })

    hr_list = []
    for r in (hr_rows or []):
        hr_list.append({
            "day": str(r.get("day")) if r.get("day") is not None else None,
            "hr_min": r.get("hr_min"),
            "hr_max": r.get("hr_max"),
        })

    return {"ok": True, "data": {"space_weather": sw_list, "schumann_daily": sch_list, "hr_daily": hr_list}}
