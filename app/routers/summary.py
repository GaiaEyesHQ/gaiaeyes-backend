# app/routers/summary.py
from fastapi import APIRouter, Depends, Request
from datetime import timezone
from app.db import get_db

router = APIRouter()

# -----------------------------
# /v1/features/today  (compact, keep your original if you have it)
# -----------------------------
@router.get("/v1/features/today")
async def features_today(request: Request, conn=Depends(get_db)):
    """
    Compact features_today; replace with your original full query if needed.
    """
    user_id = getattr(request.state, "user_id", None)

    async with conn.cursor() as cur:
        await cur.execute("set statement_timeout = 60000")

        # Daily features row: pick the most recent day
        await cur.execute(
            """
            with pick as (
              select *
              from marts.daily_features
              order by day desc
              limit 1
            )
            select day,
                   steps_total, hr_min, hr_max, hrv_avg, spo2_avg,
                   kp_max, bz_min, sw_speed_avg,
                   flares_count, cmes_count,
                   updated_at
            from pick
            """
        )
        row = await cur.fetchone()

        # Sleep by day (derived from samples) for the picked day
        day = row[0] if row else None
        sr = None
        if day is not None:
            await cur.execute(
                """
                select
                  sum(case when lower(value_text)='rem'
                           then extract(epoch from (coalesce(end_time,start_time)-start_time))/60 end) as rem_m,
                  sum(case when lower(value_text)='core'
                           then extract(epoch from (coalesce(end_time,start_time)-start_time))/60 end) as core_m,
                  sum(case when lower(value_text)='deep'
                           then extract(epoch from (coalesce(end_time,start_time)-start_time))/60 end) as deep_m,
                  sum(case when lower(value_text)='awake'
                           then extract(epoch from (coalesce(end_time,start_time)-start_time))/60 end) as awake_m,
                  sum(case when lower(value_text) in ('inbed','in_bed')
                           then extract(epoch from (coalesce(end_time,start_time)-start_time))/60 end) as inbed_m
                from gaia.samples
                where type='sleep_stage'
                  and (start_time at time zone 'America/Chicago')::date = %s::date
                """,
                (day,),
            )
            sr = await cur.fetchone()

    if not row:
        return {"ok": True, "data": None}

    def num(x):  # safe cast helper
        return float(x) if x is not None else None

    data = {
        "day": str(row[0]),
        "steps_total": num(row[1]),
        "hr_min": num(row[2]),
        "hr_max": num(row[3]),
        "hrv_avg": num(row[4]),
        "spo2_avg": num(row[5]),
        "sleep_total_minutes": None,
        "rem_m": num(sr[0]) if sr else None,
        "core_m": num(sr[1]) if sr else None,
        "deep_m": num(sr[2]) if sr else None,
        "awake_m": num(sr[3]) if sr else None,
        "inbed_m": num(sr[4]) if sr else None,
        "sleep_efficiency": (
            round(((sr[0] or 0) + (sr[1] or 0) + (sr[2] or 0)) / sr[4], 3)
            if sr and sr[4] and sr[4] > 0 else None
        ),
        "kp_max": num(row[6]),
        "bz_min": num(row[7]),
        "sw_speed_avg": num(row[8]),
        "flares_count": int(row[9]) if row[9] is not None else None,
        "cmes_count": int(row[10]) if row[10] is not None else None,
        "updated_at": row[11].astimezone(timezone.utc).isoformat() if row[11] else None,
        # schumann + earthscope post omitted in this compact version; add back if desired
    }
    return {"ok": True, "data": data}

# -----------------------------
# /v1/space/forecast/summary
# -----------------------------
@router.get("/v1/space/forecast/summary")
async def forecast_summary(conn=Depends(get_db)):
    """
    Latest SWPC 3-day forecast summary (cleaned for card).
    """
    async with conn.cursor() as cur:
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

    fetched_at = row[0].astimezone(timezone.utc).isoformat() if row[0] else None
    body = (row[1] or "").strip()
    if not body:
        return {"ok": True, "data": {"fetched_at": fetched_at, "headline": None, "lines": None, "body": None}}

    # Filter NOAA boilerplate
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
@router.get("/v1/space/series")
async def space_series(request: Request, days: int = 14, conn=Depends(get_db)):
    """
    Space weather timeseries + Schumann daily + HR daily + 5-min HR buckets.
    """
    days = max(1, min(days, 31))
    user_id = getattr(request.state, "user_id", None)

    async with conn.cursor() as cur:
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

        # D) 5-minute HR buckets
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

    # Normalize to exact JSON your app expects
    def iso(ts):
        return ts.astimezone(timezone.utc).isoformat() if ts else None

    sw_list = [
        {"ts": iso(r[0]), "kp": r[1], "bz": r[2], "sw": r[3]}
        for r in (sw_rows or [])
    ]
    sch_list = [
        {"day": str(r[0]) if r[0] is not None else None,
         "station_id": r[1],
         "f0": r[2], "f1": r[3], "f2": r[4]}
        for r in (sch_rows or [])
    ]
    hr_list = [
        {"day": str(r[0]) if r[0] is not None else None,
         "hr_min": r[1], "hr_max": r[2]}
        for r in (hr_daily_rows or [])
    ]
    hr_ts_list = [
        {"ts": iso(r[0]), "hr": r[1]}
        for r in (hr_ts_rows or [])
    ]

    return {"ok": True, "data": {
        "space_weather": sw_list,
        "schumann_daily": sch_list,
        "hr_daily": hr_list,
        "hr_timeseries": hr_ts_list
    }}