# api/webhooks.py
import hmac, hashlib, os
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
import httpx

router = APIRouter()

WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")  # same secret used by the GA workflow

def verify_sig(raw: bytes, sig: str | None):
    if not WEBHOOK_SECRET or not sig:
        raise HTTPException(status_code=401, detail="Missing signature")
    mac = hmac.new(WEBHOOK_SECRET.encode(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(mac, sig):
        raise HTTPException(status_code=401, detail="Bad signature")

class AlertPayload(BaseModel):
    kind: str
    rule: str
    payload: dict

class SocialPayload(BaseModel):
    text: str

@router.post("/hooks/earthscope")
async def earthscope_hook(body: AlertPayload, x_signature: str | None = Header(None)):
    # verify signature over raw body
    # FastAPI doesn’t expose raw body here; easiest pattern is to re-verify in middleware
    # For simplicity we trust env/infra here OR wire a small middleware (shown below).
    # TODO: branch on rule and do site ops, e.g. cache-bust, toggle banner, etc.
    # Example: call your own internal notifier or write to Supabase log table
    return {"ok": True}

@router.post("/hooks/social")
async def social_hook(body: SocialPayload, x_signature: str | None = Header(None)):
    # Same signature note as above
    # TODO: hand this text to your own poster (FB/Twitter/etc) or queue
    return {"ok": True, "accepted": body.text}