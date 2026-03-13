from fastapi import APIRouter, Query

from services.local_signals.aggregator import assemble_for_zip, ensure_weather_fields
from services.local_signals.cache import latest_for_zip, upsert_zip_payload

router = APIRouter(prefix="/v1/local", tags=["local"])


@router.get("/check")
async def check(zip: str = Query(..., min_length=5, max_length=10)):
    cached = latest_for_zip(zip)
    if cached:
        weather = cached.get("weather") if isinstance(cached, dict) else {}
        had_missing = not isinstance(weather, dict) or any(
            weather.get(key) is None
            for key in ("temp_delta_24h_c", "baro_delta_24h_hpa", "baro_trend")
        )
        repaired = ensure_weather_fields(zip, cached)
        if had_missing:
            upsert_zip_payload(zip, repaired)
        return repaired
    payload = await assemble_for_zip(zip)
    payload = ensure_weather_fields(zip, payload)
    upsert_zip_payload(zip, payload)
    return payload
