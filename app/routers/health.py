from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter

from app.db.health import get_health_monitor


router = APIRouter()


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

    return response
