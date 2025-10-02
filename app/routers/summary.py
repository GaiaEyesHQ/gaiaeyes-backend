# app/routers/summary.py
from fastapi import APIRouter, Depends, Request
from datetime import timezone
from app.db import get_db

router = APIRouter(prefix="/v1")

# -----------------------------
# /v1/features/today
# -----------------------------
@router.get("/features/today")
async def features_today(request: Request, conn=Depends(get_db)):
    """
    Compact features_today; if you have your original full version, you can
    swap it in here. This one returns the fields your app expects so the
    cards render while we finish series/forecast work.
    """
    async with conn.cursor() as cur:
        await cur.execute("set statement_timeout = 60000")

        # Pick most recent day from daily_features
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

    if not row:
        return {"ok": True, "data": None}

    def num(x): return float(x) if x is not None else None
    def iso(ts): return ts.astimezone(timezone.utc).isoformat() if ts else None

    data = {
        "day": str(row[0]),
        "steps_total": num(row[1]),
        "hr_min": num(row[2]),
        "hr_max": num(row[3]),
        "hrv_avg": num(row[4]),
        "spo2_avg": num(row[5]),
        # sleep_* omitted here (still shows cards; your rollup fills daily_features)
        "sleep_total_minutes": None,
        "rem_m": None, "core_m": None, "deep_m": None, "awake_m": None, "inbed_m": None,
        "sleep_efficiency": None,
        "kp_max": num(row[6]),
        "bz_min": num(row[7]),
        "sw_speed_avg": num(row[8]),
        "flares_count": int(row[9]) if row[9] is not None else None,
        "cmes_count": int(row[10]) if row[10] is not None else None,
        "updated_at": iso(row[11]),
        # optional: schumann / post can be added back later
    }
    return {"ok": True, "data": data}

# -----------------------------
# /v1/space/forecast/summary
# -----------------------------
@router.get("/space/forecast/summary")
async def forecast_summary(conn=Depends(get_db)):
    """
    Latest SWPC 3-day forecast summary, cleaned for the card.
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
@router.get("/space/series")
async def space_series(request: Request, days: int = 14, conn=Depends(get_db)):
    """
    Space weather (Kp/Bz/SW), Schumann daily (f0/f1/f2),
    HR daily (min/max), and 5-minute HR buckets.
    """
    days = max(1, min(days, 31))
    user_id = getattr(request.state, "user_id", None)

    async with conn.cursor() as cur:
        await cur.execute("set statement_timeout = 60000")

        # A) Space weather: union rows per metric so Kp/Bz/SW appear even if on different timestamps
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

        # B) Schumann daily: prefer tomsk over cumiana per day
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

        # D) 5-minute HR buckets (psql-safe epoch binning)
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

    # -------- normalize to app shape --------
    def iso(ts): return ts.astimezone(timezone.utc).isoformat() if ts else None

    space_weather = [{"ts": iso(r[0]), "kp": r[1], "bz": r[2], "sw": r[3]} for r in (sw_rows or [])]
    schumann_daily = [{"day": str(r[0]) if r[0] is not None else None,
                       "station_id": r[1], "f0": r[2], "f1": r[3], "f2": r[4]}
                      for r in (sch_rows or [])]
    hr_daily = [{"day": str(r[0]) if r[0] is not None else None,
                 "hr_min": r[1], "hr_max": r[2]}
                for r in (hr_daily_rows or [])]
    hr_timeseries = [{"ts": iso(r[0]), "hr": r[1]} for r in (hr_ts_rows or [])]

    return {"ok": True, "data": {
        "space_weather": space_weather,
        "schumann_daily": schumann_daily,
        "hr_daily": hr_daily,
        "hr_timeseries": hr_timeseries,
    }}