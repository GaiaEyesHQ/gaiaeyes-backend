#!/usr/bin/env python3

from __future__ import annotations

import sys
from pathlib import Path

# Ensure repo root is on sys.path when executed as a script (e.g., in GitHub Actions)
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from services.db import pg
from bots.gauges.db_utils import pick_column, table_columns, upsert_row


LOG_LEVEL = os.getenv("GAIA_LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)


def _today_utc() -> datetime:
    return datetime.now(timezone.utc)


def _select_primary_location(user_id: str, cols: list[str]) -> Optional[Dict[str, Any]]:
    primary_col = pick_column(cols, ["is_primary", "primary", "is_default"])
    if not primary_col:
        return None

    updated_col = pick_column(cols, ["updated_at", "created_at"])
    order_by = f"order by {updated_col} desc" if updated_col else ""
    sql = f"""
        select *
          from app.user_locations
         where user_id = %s
           and {primary_col} = true
         {order_by}
         limit 1
    """
    return pg.fetchrow(sql, user_id)


def main() -> None:
    today = _today_utc().date()
    cols = table_columns("app", "user_locations")
    if not cols:
        raise RuntimeError("app.user_locations not found or has no columns")

    zip_col = pick_column(cols, ["zip", "postal_code"])
    lat_col = pick_column(cols, ["lat", "latitude"])
    lon_col = pick_column(cols, ["lon", "lng", "longitude"])

    users = pg.fetch("select distinct user_id from app.user_locations")
    logger.info("[location_context] users=%d day=%s", len(users), today)

    for row in users:
        user_id = row.get("user_id")
        if not user_id:
            continue
        primary = _select_primary_location(user_id, cols)
        source = "primary" if primary else "none"
        payload = {
            "user_id": user_id,
            "day": today,
            "zip": primary.get(zip_col) if (primary and zip_col) else None,
            "lat": primary.get(lat_col) if (primary and lat_col) else None,
            "lon": primary.get(lon_col) if (primary and lon_col) else None,
            "source": source,
            "updated_at": _today_utc(),
        }
        upsert_row("marts", "user_location_context_day", payload, ["user_id", "day"])

    logger.info("[location_context] done day=%s", today)


if __name__ == "__main__":
    main()
