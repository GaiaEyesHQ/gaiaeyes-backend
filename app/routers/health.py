from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter

from app.db.health import get_health_monitor


router = APIRouter()

_INGEST_QUEUE_HEALTH_TIMEOUT_SECONDS = 0.35


@router.get("/health/live", include_in_schema=False)
async def service_liveness() -> Dict[str, Any]:
    """Fast process liveness probe for platform health checks.

    This intentionally avoids DB, Redis, and upstream calls. Use /health for
    readiness/diagnostics; use /health/live to decide whether the process is
    listening and should stay alive.
    """

    return {
        "ok": True,
        "service": "gaiaeyes-backend",
        "time": datetime.now(timezone.utc).isoformat(),
        "live": True,
    }


@router.get("/health", include_in_schema=False)
async def service_health() -> Dict[str, Any]:
    monitor = get_health_monitor()
    snapshot: Optional[Dict[str, Any]] = monitor.snapshot() if monitor else None
    db_ok = bool(snapshot.get("db_ok")) if snapshot else True
    sticky_age = int(snapshot.get("sticky_age_ms", 0)) if snapshot else 0

    response: Dict[str, Any] = {
        "ok": True,
        "service": "gaiaeyes-backend",
        "time": datetime.now(timezone.utc).isoformat(),
        "db": db_ok,
        "db_sticky_age": sticky_age,
    }

    if snapshot is not None:
        response["monitor"] = snapshot

    try:
        from app.routers.ingest import ingest_queue_status

        response["ingest_queue"] = await asyncio.wait_for(
            ingest_queue_status(),
            timeout=_INGEST_QUEUE_HEALTH_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        response["ingest_queue"] = {
            "redis_depth": None,
            "redis_error": "queue_status_timeout",
        }
    except Exception:
        pass

    return response
