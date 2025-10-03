# app/routers/summary.py
from fastapi import APIRouter, Depends, Request
from datetime import timezone
from os import getenv
from psycopg.rows import dict_row
from app.db import get_db

router = APIRouter(prefix="/v1")

# -----------------------------
# /v1/features/today (full)
# -----------------------------
@router.get("/features/today")
async def features_today(request: Request, conn = Depends(get_db)):
    """
    Return today's (latest) features row including derived sleep, current Kp/Bz/SW,
    Schumann preference (tomsk > cumiana), and Earthscope default post. America/Chicago
    is used for daily bucketing of sleep.
    """
    media_base = getenv("MEDIA_BASE_URL", "").rstrip("/")

    sql = """
    with pick as (
      select * from marts.daily_features order by day desc limit 1
    ),
    sr as (
      select (start_time at time zone 'America/Chicago')::date as day,
             sum(case when lower(value_text)='rem'  then extract(epoch from (coalesce(end_time,start_time)-start_time))/60 end) as rem_m,
             sum(case when lower(value_text)='core' then extract(epoch from (coalesce(end_time,start_time)-start_time))/60 end) as core_m,
             sum(case when lower(value_text)='deep' then extract(epoch from (coalesce(end_time,start_time)-start_time))/60 end) as deep_m,
             sum(case when lower(value_text)='awake'then extract(epoch from (coalesce(end_time,start_time)-start_time))/60 end) as awake_m,
             sum(case when lower(value_text) in ('inbed','in_bed') then extract(epoch from (coalesce(end_time,start_time)-start_time))/60 end) as inbed_m
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

    -- latest Schumann row on or before picked day, prefer tomsk over cumiana
    left join LATERAL (
      select s.station_id,
             s.f0_avg_hz, s.f1_avg_hz, s.f2_avg_hz, s.f3_avg_hz, s.f4_avg_hz
      from marts.schumann_daily s
      where s.station_id in ('tomsk','cumiana') and s.day <= p.day
      order by s.day desc,
               case when s.station_id='tomsk' then 0 when s.station_id='cumiana' then 1 else 2 end
      limit 1
    ) sch on true

    -- latest Earthscope default post on or before picked day
    left join LATERAL (
      select p0.title as post_title,
             p0.caption as post_caption,
             p0.body_markdown as post_body,
             p0.hashtags as post_hashtags
      from content.daily_posts p0
      where p0.platform = 'default' and p0.day <= p.day
      order by p0.day desc, p0.updated_at desc
      limit 1
    ) dp on true

    cross join diag d
    """

    try:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(sql)
            row = await cur.fetchone()
    except Exception as e:
        return {"ok": True, "data": None, "error": f"features_today query failed: {e}"}

    if not row:
        return {"ok": True, "data": None}

    rec = dict(row)
    rec["day"] = str(rec.get("day"))

    # Diagnostics (optional; used by the app for visibility)
    diagnostics = {
        "max_day": str(rec.pop("max_day", None)),
        "total_rows": rec.pop("total_rows", None)
    }

    # Provide Earthscope image URLs if MEDIA_BASE_URL is set
    if media_base:
        rec["earthscope_images"] = {
            "caption": f"{media_base}/images/daily_caption.jpg",
            "stats": f"{media_base}/images/daily_stats.jpg",
            "affects": f"{media_base}/images/daily_affects.jpg",
            "playbook": f"{media_base}/images/daily_playbook.jpg",
        }

    return {"ok": True, "data": rec, "diagnostics": diagnostics}


# -----------------------------
# /v1/space/forecast/summary
# -----------------------------
@router.get("/space/forecast/summary")
async def forecast_summary(conn = Depends(get_db)):
    """
    Latest SWPC 3-day forecast summary (cleaned for the card).
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("set statement_timeout = 60000")
        await cur.execute(
            """
            select fetched_at, body_text
            from ext.space_forecast
            order by fetched_at desc
            limit 1
            """
        )
        row = await cur.fetchone()

    if not row:
        return {"ok": True, "data": None}

    fetched_at = row.get("fetched_at")
    fetched_at = fetched_at.astimezone(timezone.utc).isoformat() if fetched_at else None
    body = (row.get("body_text") or "").strip()

    if not body:
        return {"ok": True, "data": {"fetched_at": fetched_at, "headline": None, "lines": None, "body": None}}

    raw_lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    lines = [ln for ln in raw_lines if not ln.startswith((':', '#'))]
    headline = lines[0] if lines else None

    bullets = []
    for ln in lines[1:]:
        if ln.startswith(('-', '*', '•')) or len(ln) <= 120:
            bullets.append(ln.lstrip('-*• ').strip())
        if len(bullets) >= 4:
            break

    return {"ok": True, "data": {"fetched_at": fetched_at, "headline": headline, "lines": bullets or None, "body": None}}


# -----------------------------
# /v1/space/series
# -----------------------------
@router.get("/space/series")
async def space_series(request: Request, days: int = 30, conn = Depends(get_db)):
    """
    Space weather (Kp/Bz/SW), Schumann daily (f0/f1/f2), HR daily (min/max),
    and 5-minute HR buckets. Returns the exact JSON the app expects.
    """
    days = max(1, min(days, 31))
    user_id = getattr(request.state, "user_id", None)

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("set statement_timeout = 60000")

        # A) Space weather: union per metric
        await cur.execute(
            """
            (
              select ts_utc, kp_index as kp, null::double precision as bz, null::double precision as sw
              from ext.space_weather
              where ts_utc >= now() - %s::interval and kp_index is not null
            )
            union all
            (
              select ts_utc, null::double precision as kp, bz_nt as bz, null::double precision as sw
              from ext.space_weather
              where ts_utc >= now() - %s::interval and bz_nt is not null
            )
            union all
            (
              select ts_utc, null::double precision as kp, null::double precision as bz, sw_speed_kms as sw
              from ext.space_weather
              where ts_utc >= now() - %s::interval and sw_speed_kms is not null
            )
            order by ts_utc asc
            """,
            (f"{days} days", f"{days} days", f"{days} days"),
        )
        sw_rows = await cur.fetchall()

        # B) Schumann daily (prefer tomsk > cumiana)
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
        )
        sch_rows = await cur.fetchall()

        # C) HR daily from daily_summary
        hr_daily_rows = []
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
            )
            hr_daily_rows = await cur.fetchall()

        # D) 5-minute HR buckets (epoch bin)
        hr_ts_rows = []
        if user_id is not None:
            await cur.execute(
                """
                with buckets as (
                  select generate_series(
                    now() - %s::interval,
                    now(),
                    interval '5 minutes'
                  ) as ts
                ),
                agg as (
                  select
                    to_timestamp(floor(extract(epoch from start_time)/300.0)*300.0) at time zone 'UTC' as bucket,
                    avg(value) as hr
                  from gaia.samples
                  where user_id = %s
                    and type in ('heart_rate','hr')
                    and start_time >= now() - %s::interval
                  group by 1
                )
                select b.ts as ts_utc, a.hr
                from buckets b
                left join agg a on a.bucket = b.ts
                order by ts_utc asc
                """,
                (f"{days} days", user_id, f"{days} days"),
            )
            hr_ts_rows = await cur.fetchall()

        # Diagnostics: counts by source in the same window
        await cur.execute("select count(*) as n from ext.space_weather where ts_utc >= now() - %s::interval", (f"{days} days",))
        sw_count_row = await cur.fetchone()
        sw_count = sw_count_row.get("n") if sw_count_row else None

        await cur.execute("select count(*) as n from marts.schumann_daily where day >= (current_date - %s::interval)::date", (f"{days} days",))
        sch_count_row = await cur.fetchone()
        sch_count = sch_count_row.get("n") if sch_count_row else None

        hr_daily_count = len(hr_daily_rows or [])
        hr_ts_count = len(hr_ts_rows or [])

    # Normalize
    def iso(ts): return ts.astimezone(timezone.utc).isoformat() if ts else None

    space_weather = [{
        "ts": iso(r.get("ts_utc")),
        "kp": r.get("kp"),
        "bz": r.get("bz"),
        "sw": r.get("sw"),
    } for r in (sw_rows or [])]

    schumann_daily = [{
        "day": str(r.get("day")) if r.get("day") is not None else None,
        "station_id": r.get("station_id"),
        "f0": r.get("f0_avg_hz"),
        "f1": r.get("f1_avg_hz"),
        "f2": r.get("f2_avg_hz"),
    } for r in (sch_rows or [])]

    hr_daily = [{
        "day": str(r.get("day")) if r.get("day") is not None else None,
        "hr_min": r.get("hr_min"),
        "hr_max": r.get("hr_max"),
    } for r in (hr_daily_rows or [])]

    hr_timeseries = [{
        "ts": iso(r.get("ts_utc")),
        "hr": r.get("hr"),
    } for r in (hr_ts_rows or [])]

    return {"ok": True, "data": {
        "space_weather": space_weather,
        "schumann_daily": schumann_daily,
        "hr_daily": hr_daily,
        "hr_timeseries": hr_timeseries,
    }, "diag": {
        "days": days,
        "sw_rows": len(space_weather),
        "sch_rows": len(schumann_daily),
        "hr_daily_rows": len(hr_daily),
        "hr_ts_rows": len(hr_timeseries),
        "sw_count_db": sw_count,
        "sch_count_db": sch_count
    }}