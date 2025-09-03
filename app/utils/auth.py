from fastapi import Request, HTTPException
from .. import db

async def require_auth(request: Request):
    auth = request.headers.get("Authorization", "")
    token = auth.replace("Bearer ", "").strip() if auth else ""
    settings = db.settings
    # Dev bearer: attach user id from header for testing
    if settings.DEV_BEARER and token == settings.DEV_BEARER:
        request.state.user_id = request.headers.get(
            "X-Dev-UserId", "00000000-0000-0000-0000-000000000000"
        )
        return
    raise HTTPException(status_code=401, detail="Unauthorized")
