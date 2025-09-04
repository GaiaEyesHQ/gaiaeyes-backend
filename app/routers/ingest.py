# app/routers/ingest.py
from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Union, Annotated

from fastapi import APIRouter, Body, Depends, Request, Header, HTTPException, status
from pydantic import BaseModel

from ..db import get_pool, settings  # settings.DEV_BEARER, async pg pool

router = APIRouter(tags=["ingest"])


# ---------- Models ----------
class SampleIn(BaseModel):
    user_id: str
    device_os: str
    source: str
    type: str
    start_time: datetime
    end_time: datetime
    value: Optional[float] = None
    unit: Optional[str] = None
    value_text: Optional[str] = None


class SamplesWrapper(BaseModel):
    samples: List[SampleIn]


# ---------- Auth ----------
async def require_bearer(authorization: str = Header(..., alias="Authorization")) -> None:
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )
    token = authorization.split(" ", 1)[1].strip()
    if not settings.DEV_BEARER or token != settings.DEV_BEARER:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token",
        )


# ---------- Endpoint ----------
# Accept EITHER {"samples":[...]} OR a raw array [...]
Payload = Annotated[Union[SamplesWrapper, List[SampleIn]], Body(..., media_type="application/json")]

# --- keep your models & auth as-is above this ---

# psycopg-style insert with %s placeholders
sql = """
insert into gaia.samples (
  user_id, device_os, source, type,
  start_time, end_time, value, unit, value_text
) values (%s,%s,%s,%s,%s,%s,%s,%s,%s)
on conflict (user_id, type, start_time, end_time) do nothing
"""

@router.post("/samples/batch")
async def samples_batch(
    payload: Payload,           # your Union[SamplesWrapper, List[SampleIn]]
    request: Request,           # so we can read headers if you added UUID override
    _auth: None = Depends(require_bearer),
):
    # Normalize payload to list
    items = payload.samples if isinstance(payload, SamplesWrapper) else (payload or [])
    if not items:
        return {"ok": True, "received": 0}

    # If you added header-based UUID override earlier, keep it; otherwise remove this block.
    x_uid = request.headers.get("X-Dev-UserId", "").strip() or None
    dev_uid = x_uid  # assume already a proper UUID string; your earlier code validated

        pool = await get_pool()
    values = [
        (
            dev_uid or s.user_id,
            s.device_os,
            s.source,
            s.type,
            s.start_time,    # datetime is fine
            s.end_time,
            s.value,
            s.unit,
            s.value_text,
        )
        for s in items
    ]

    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            for v in values:
                await cur.execute(sql, v)   # no prepare kw in async psycopg
        await conn.commit()

    return {"ok": True, "received": len(items)}
