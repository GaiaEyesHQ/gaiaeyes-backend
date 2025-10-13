# api/middleware.py
import hmac, hashlib, os
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")

class WebhookSigMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/hooks/"):
            sig = request.headers.get("x-signature")
            raw = await request.body()
            if not WEBHOOK_SECRET or not sig:
                return Response("Missing signature", status_code=401)
            mac = hmac.new(WEBHOOK_SECRET.encode(), raw, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(mac, sig):
                return Response("Bad signature", status_code=401)
        return await call_next(request)