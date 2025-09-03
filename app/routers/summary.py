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
