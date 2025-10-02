from fastapi import APIRouter, Depends
from app.db import get_db

router = APIRouter()

@router.get("/space/series")
async def space_series(days: int = 14, conn: Depends(get_db)):
    # ... other code ...

    await conn.execute("set statement_timeout = 60000")
    async with conn.transaction():
        cur = await conn.cursor()
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
            prepare=False,
        )
        sw_rows = await cur.fetchall()

    # ... rest of the function unchanged ...
