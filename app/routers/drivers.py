from __future__ import annotations

import os
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.db import get_db
from app.security.auth import require_read_auth
from services.drivers.all_drivers import build_all_drivers_payload


router = APIRouter(prefix="/v1/users/me", tags=["drivers"])
DEFAULT_TIMEZONE = os.getenv("GAIA_TIMEZONE", "America/Chicago")


def _require_user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id missing from request context")
    return user_id


def _default_driver_day() -> date:
    try:
        return datetime.now(ZoneInfo(DEFAULT_TIMEZONE)).date()
    except Exception:
        return datetime.now(timezone.utc).date()


@router.get("/drivers", dependencies=[Depends(require_read_auth)])
async def user_drivers(
    request: Request,
    day: date | None = Query(None),
    conn=Depends(get_db),
):
    user_id = _require_user_id(request)
    target_day = day or _default_driver_day()
    try:
        payload = await build_all_drivers_payload(conn, user_id=user_id, day=target_day)
    except Exception as exc:
        return {"ok": False, "error": f"all drivers build failed: {exc}"}
    return {"ok": True, **payload}
