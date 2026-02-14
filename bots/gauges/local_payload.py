from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any, Dict, Optional

from services.db import pg
from services.local_signals.cache import latest_for_zip
from bots.gauges.db_utils import pick_column, table_columns


def _coerce_day(value: str | date | None) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    return datetime.now(timezone.utc).date()


def _try_rpc(user_id: str, day: date) -> Optional[Dict[str, Any]]:
    sqls = [
        ("select app.get_local_signals_for_user(%s::uuid, %s::date) as payload", (user_id, day)),
        ("select app.get_local_signals_for_user(%s::date, %s::uuid) as payload", (day, user_id)),
        ("select app.get_local_signals_for_user(%s::date) as payload", (day,)),
        ("select app.get_local_signals_for_user(%s::uuid) as payload", (user_id,)),
    ]
    for sql, params in sqls:
        try:
            row = pg.fetchrow(sql, *params)
        except Exception:
            continue
        if not row:
            continue
        payload = row.get("payload")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                return None
        if isinstance(payload, dict):
            return payload
    return None


def _fetch_zip_from_location_context(user_id: str, day: date) -> Optional[str]:
    cols = table_columns("marts", "user_location_context_day")
    if not cols:
        return None
    if "zip" not in cols:
        return None
    row = pg.fetchrow(
        """
        select zip
          from marts.user_location_context_day
         where user_id = %s
           and day = %s
         limit 1
        """,
        user_id,
        day,
    )
    if row and row.get("zip"):
        return row.get("zip")
    row = pg.fetchrow(
        """
        select zip
          from marts.user_location_context_day
         where user_id = %s
           and zip is not null
         order by day desc
         limit 1
        """,
        user_id,
    )
    return row.get("zip") if row else None


def _fetch_zip_from_user_locations(user_id: str) -> Optional[str]:
    cols = table_columns("app", "user_locations")
    if not cols:
        return None
    zip_col = pick_column(cols, ["zip", "postal_code"])
    if not zip_col:
        return None
    primary_col = pick_column(cols, ["is_primary", "primary", "is_default"])
    order_col = pick_column(cols, ["updated_at", "created_at"])
    where_primary = f"and {primary_col} = true" if primary_col else ""
    order_by = f"order by {order_col} desc" if order_col else ""
    sql = f"""
        select {zip_col} as zip
          from app.user_locations
         where user_id = %s
         {where_primary}
         {order_by}
         limit 1
    """
    row = pg.fetchrow(sql, user_id)
    return row.get("zip") if row else None


def get_local_payload(user_id: str, day: str | date | None = None) -> Optional[Dict[str, Any]]:
    day = _coerce_day(day)

    payload = _try_rpc(user_id, day)
    if isinstance(payload, dict):
        return payload

    zip_code = _fetch_zip_from_location_context(user_id, day) or _fetch_zip_from_user_locations(user_id)
    if not zip_code:
        return None

    cached = latest_for_zip(zip_code)
    return cached if isinstance(cached, dict) else None
