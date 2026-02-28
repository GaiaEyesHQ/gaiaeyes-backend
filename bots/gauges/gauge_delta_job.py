#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List

from services.db import pg
from bots.gauges.db_utils import upsert_row


LOG_LEVEL = os.getenv("GAIA_LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)

_GAUGE_KEYS = [
    "pain",
    "focus",
    "heart",
    "stamina",
    "energy",
    "sleep",
    "mood",
    "health_status",
]


def _today_utc() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _coerce_day(value: str | date | None) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    return datetime.now(timezone.utc).date()


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return float(value)
    except Exception:
        return None


def _as_int_delta(today_val: Any, yesterday_val: Any) -> int:
    today_num = _safe_float(today_val)
    yday_num = _safe_float(yesterday_val)
    if today_num is None or yday_num is None:
        return 0
    return int(round(today_num - yday_num, 0))


def _fetch_rows_for_day(day: date, user_id: str | None, limit: int | None) -> List[Dict[str, Any]]:
    params: List[Any] = [day]
    where = ["day = %s"]
    if user_id:
        where.append("user_id = %s")
        params.append(user_id)

    limit_sql = ""
    if limit and limit > 0:
        limit_sql = "limit %s"
        params.append(limit)

    sql = f"""
        select user_id, day, {", ".join(_GAUGE_KEYS)}
          from marts.user_gauges_day
         where {" and ".join(where)}
         order by user_id
         {limit_sql}
    """
    return pg.fetch(sql, *params)


def _fetch_yesterday_row(user_id: str, day: date) -> Dict[str, Any] | None:
    yesterday = day - timedelta(days=1)
    return pg.fetchrow(
        f"""
        select {", ".join(_GAUGE_KEYS)}
          from marts.user_gauges_day
         where user_id = %s
           and day = %s
         limit 1
        """,
        user_id,
        yesterday,
    )


def _build_deltas(today_row: Dict[str, Any], yesterday_row: Dict[str, Any] | None) -> Dict[str, int]:
    yday = yesterday_row or {}
    out: Dict[str, int] = {}
    for key in _GAUGE_KEYS:
        out[key] = _as_int_delta(today_row.get(key), yday.get(key))
    return out


def _iter_rows(rows: Iterable[Dict[str, Any]], limit: int | None) -> Iterable[Dict[str, Any]]:
    count = 0
    for row in rows:
        yield row
        count += 1
        if limit and count >= limit:
            break


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute daily gauge deltas for users.")
    parser.add_argument("--day", default=_today_utc(), help="Day in YYYY-MM-DD (UTC).")
    parser.add_argument("--user-id", default=None, help="Optional single user_id override.")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of users processed.")
    args = parser.parse_args()

    day = _coerce_day(args.day)
    rows = _fetch_rows_for_day(day, args.user_id, args.limit)
    logger.info("[gauge_delta] rows=%d day=%s", len(rows), day.isoformat())

    ok = 0
    failed = 0
    for row in _iter_rows(rows, args.limit):
        uid = str(row.get("user_id") or "").strip()
        if not uid:
            continue
        try:
            yday = _fetch_yesterday_row(uid, day)
            deltas = _build_deltas(row, yday)
            upsert_row(
                "marts",
                "user_gauges_delta_day",
                {
                    "user_id": uid,
                    "day": day,
                    "deltas_json": json.dumps(deltas, default=str),
                    "updated_at": datetime.now(timezone.utc),
                },
                ["user_id", "day"],
            )
            ok += 1
            logger.info("[gauge_delta] user=%s day=%s ok=true", uid, day.isoformat())
        except Exception as exc:
            failed += 1
            logger.exception("[gauge_delta] user=%s day=%s failed: %s", uid, day.isoformat(), exc)

    logger.info("[gauge_delta] done ok=%d failed=%d day=%s", ok, failed, day.isoformat())


if __name__ == "__main__":
    main()
