from fastapi import APIRouter, Query

from services.local_signals.aggregator import assemble_for_zip
from services.local_signals.cache import latest_for_zip, upsert_zip_payload

router = APIRouter(prefix="/v1/local", tags=["local"])


@router.get("/check")
async def check(zip: str = Query(..., min_length=5, max_length=10)):
    cached = latest_for_zip(zip)
    if cached:
        return cached
    payload = await assemble_for_zip(zip)
    upsert_zip_payload(zip, payload)
    return payload
