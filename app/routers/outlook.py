from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.security.auth import require_read_auth
from services.forecast_outlook import build_user_outlook_payload_via_pool


router = APIRouter(prefix="/v1/users/me", tags=["outlook"])


def _require_user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id missing from request context")
    return user_id


@router.get("/outlook", dependencies=[Depends(require_read_auth)])
async def user_outlook(request: Request):
    user_id = _require_user_id(request)
    try:
        payload = await build_user_outlook_payload_via_pool(user_id)
    except Exception as exc:
        return {"ok": False, "error": f"outlook build failed: {exc}"}
    return {"ok": True, **payload}
