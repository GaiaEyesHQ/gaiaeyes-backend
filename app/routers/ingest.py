# app/routers/ingest.py
from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Union, Annotated

import math
from psycopg import errors as pg_errors

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


# ---------- Validation ----------
def _validate_sample(s: SampleIn) -> tuple[bool, str | None]:
    # basic time sanity
    if s.end_time and s.end_time < s.start_time:
        return False, "end_time < start_time"
    # numeric checks
    if s.value is not None:
        if not math.isfinite(s.value):
            return False, "non-finite value"
    # type-specific ranges (keep permissive; mirror client-side sanitizers)
    t = s.type.lower()
    v = s.value
    if t == "heart_rate" and v is not None:
        if v < 20 or v > 250:
            return False, "heart_rate out of range"
    if t == "spo2" and v is not None:
        if v < 50 or v > 100:
            return False, "spo2 out of range"
    if t == "step_count" and v is not None:
        if v < 0:
            return False, "step_count negative"
    if t == "hrv_sdnn" and v is not None:
        if v < 0 or v > 600:
            return False, "hrv_sdnn out of range"
    return True, None


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
    payload: Payload,
    request: Request,
    _auth: None = Depends(require_bearer),
):
    # Normalize payload to list
    items = payload.samples if isinstance(payload, SamplesWrapper) else (payload or [])
    if not items:
        return {"ok": True, "received": 0, "inserted": 0, "skipped": 0}

    # Optional header override of user_id (useful for dev/testing)
    x_uid = request.headers.get("X-Dev-UserId", "").strip() or None
    dev_uid = x_uid

    pool = await get_pool()
    inserted = 0
    skipped = 0
    errors: list[dict] = []

    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            for s in items:
                # validate before touching the DB
                ok, reason = _validate_sample(s)
                if not ok:
                    skipped += 1
                    if len(errors) < 10:
                        errors.append({
                            "index": skipped + inserted,
                            "type": s.type,
                            "reason": reason,
                            "start_time": s.start_time.isoformat(),
                        })
                    continue
                # prepare values tuple
                v = (
                    dev_uid or s.user_id,
                    s.device_os,
                    s.source,
                    s.type,
                    s.start_time,
                    s.end_time,
                    s.value,
                    s.unit,
                    s.value_text,
                )
                try:
                    await cur.execute(sql, v, prepare=False)
                    inserted += 1
                except pg_errors.UniqueViolation:
                    # on-conflict do nothing should already prevent this, but be safe
                    continue
                except Exception as e:  # capture and keep inserting
                    skipped += 1
                    if len(errors) < 10:
                        errors.append({
                            "index": skipped + inserted,
                            "type": s.type,
                            "reason": f"db_error: {type(e).__name__}",
                            "message": str(e)[:200],
                        })
            await conn.commit()

    resp = {"ok": True, "received": len(items), "inserted": inserted, "skipped": skipped}
    if errors:
        resp["errors"] = errors  # include a small sample of what was skipped
    return resp
