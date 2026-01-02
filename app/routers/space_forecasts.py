from fastapi import APIRouter, Depends, Query
from typing import Optional, List, Dict, Any
from app.db import get_db  # your existing helper

router = APIRouter(prefix="/v1/space", tags=["space"])

@router.get("/aurora/now")
async def aurora_now(
    hemisphere: str = Query("north", pattern="^(north|south|both)$"),
    conn = Depends(get_db),
):
    async with conn.cursor() as cur:
        if hemisphere == "both":
            await cur.execute("""
              select distinct on (hemisphere)
                     ts_utc, hemisphere, hemispheric_power_gw, wing_kp
              from ext.aurora_power
              where ts_utc > now() - interval '6 hours'
              order by hemisphere, ts_utc desc
            """)
        else:
            await cur.execute("""
              select ts_utc, hemisphere, hemispheric_power_gw, wing_kp
              from ext.aurora_power
              where hemisphere = %s
              order by ts_utc desc
              limit 1
            """, (hemisphere,))
        rows = await cur.fetchall()
    return {"as_of": max(r["ts_utc"] for r in rows) if rows else None,
            "samples": rows}

@router.get("/aurora/outlook")
async def aurora_outlook(
    hours: int = 24,
    hemisphere: str = Query("north", pattern="^(north|south)$"),
    conn = Depends(get_db),
):
    hours = max(1, min(hours, 72))
    async with conn.cursor() as cur:
        await cur.execute("""
          select valid_from, coalesce(valid_to, valid_from + interval '1 hour') as valid_to,
                 hemisphere, headline, power_gw, wing_kp, confidence
          from marts.aurora_outlook
          where hemisphere = %s
            and valid_from <= now() + (%s || ' hours')::interval
            and coalesce(valid_to, valid_from + interval '1 hour') >= now()
          order by valid_from
        """, (hemisphere, hours))
        bins = await cur.fetchall()
    return {"hemisphere": hemisphere, "bins": bins}

@router.get("/sep/latest")
async def sep_latest(conn = Depends(get_db), energy_band: str = ">=10"):
    async with conn.cursor() as cur:
        await cur.execute("""
          select ts_utc, satellite, energy_band, flux, s_scale, s_scale_index
          from ext.sep_flux
          where energy_band ilike %s
          order by ts_utc desc
          limit 1
        """, (f"%{energy_band}%",))
        row = await cur.fetchone()
    return row or {}

@router.get("/solarwind/state")
async def solarwind_state(conn = Depends(get_db)):
    async with conn.cursor() as cur:
        await cur.execute("""
          with w as (
            select ts_utc, sw_speed_kms, bz_nt
            from ext.space_weather
            where ts_utc > now() - interval '3 hours'
            order by ts_utc desc
          )
          select max(sw_speed_kms) as sw_max,
                 min(bz_nt)       as bz_min,
                 max(ts_utc)      as as_of
          from w
        """)
        row = await cur.fetchone()
    if not row or row["as_of"] is None:
        return {}
    state = ("high_speed_stream" if row["sw_max"] >= 600
             else "elevated" if row["sw_max"] >= 500
             else "normal")
    return {"as_of": row["as_of"], "speed_kms_max": row["sw_max"], "bz_nt_min": row["bz_min"], "state": state}

@router.get("/radiation-belts/latest")
async def belts_latest(conn = Depends(get_db)):
    async with conn.cursor() as cur:
        await cur.execute("""
          select distinct on (day) day, satellite, max_flux, avg_flux, risk_level, computed_at
          from marts.radiation_belts_daily
          order by day desc, satellite, computed_at desc
        """)
        rows = await cur.fetchall()
    return {"day": rows[0]["day"] if rows else None, "satellites": rows}

@router.get("/drap/latest")
async def drap_latest(conn = Depends(get_db), region: Optional[str] = None):
    async with conn.cursor() as cur:
        if region:
            await cur.execute("""
              select day, region, max_absorption_db, avg_absorption_db, created_at
              from marts.drap_absorption_daily
              where region ilike %s
              order by day desc
              limit 1
            """, (region,))
            row = await cur.fetchone()
            return row or {}
        else:
            await cur.execute("""
              select distinct on (region)
                     day, region, max_absorption_db, avg_absorption_db, created_at
              from marts.drap_absorption_daily
              order by region, day desc
            """)
            rows = await cur.fetchall()
            return {"regions": rows}

@router.get("/cme/arrivals")
async def cme_arrivals(conn = Depends(get_db),
                       hours_ahead: int = 72,
                       include_past_hours: int = 6,
                       target: str = "earth"):
    hours_ahead = max(1, min(hours_ahead, 168))
    include_past_hours = max(0, min(include_past_hours, 72))
    async with conn.cursor() as cur:
        await cur.execute("""
          select arrival_time, simulation_id, location, cme_speed_kms, kp_estimate, confidence
          from marts.cme_arrivals
          where lower(location_key) like lower(%s) || '%%'
            and arrival_time between now() - (%s || ' hours')::interval
                                and now() + (%s || ' hours')::interval
          order by arrival_time
        """, (target, include_past_hours, hours_ahead))
        rows = await cur.fetchall()
    return {"target": target, "arrivals": rows}

@router.get("/overview")
async def overview(conn = Depends(get_db)):
    # simple aggregator to power the app’s dashboard
    async with conn.cursor() as cur:
        await cur.execute("""select * from marts.space_weather_daily order by day desc limit 1""")
        swd = await cur.fetchone()
        await cur.execute("""select distinct on (hemisphere) ts_utc, hemisphere, hemispheric_power_gw
                             from ext.aurora_power
                             order by hemisphere, ts_utc desc""")
        aur = await cur.fetchall()
        await cur.execute("""select day, satellite, risk_level, max_flux
                             from marts.radiation_belts_daily
                             order by day desc, satellite limit 4""")
        belts = await cur.fetchall()
        await cur.execute("""select * from marts.drap_absorption_daily
                             where day = current_date order by region""")
        drap = await cur.fetchall()
    return {
        "as_of": swd["day"] if swd else None,
        "solar": {
            "xray": {"max_class": swd["xray_max_class"] if swd else None},
            "sep":  {"s_index": swd["sep_s_max"] if swd else None},
        },
        "magnetosphere": {"kp_max": swd["kp_max"] if swd else None,
                          "bz_min": swd["bz_min"] if swd else None,
                          "sw_speed_avg": swd["sw_speed_avg"] if swd else None},
        "aurora": { r["hemisphere"]: {"power_gw": r["hemispheric_power_gw"], "as_of": r["ts_utc"]} for r in aur },
        "radio_absorption": { r["region"]: {"day": r["day"], "max_db": r["max_absorption_db"]} for r in drap },
        "radiation": {"belts": belts},
    }