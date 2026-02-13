#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging
import os
from datetime import datetime, timezone
from typing import Iterable, Set

from services.db import pg
from bots.gauges.gauge_scorer import score_user_day


LOG_LEVEL = os.getenv("GAIA_LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)


def _today_utc() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _fetch_user_ids() -> Set[str]:
    user_ids: Set[str] = set()
    try:
        rows = pg.fetch("select distinct user_id from app.user_locations")
        user_ids.update([r["user_id"] for r in rows if r.get("user_id")])
    except Exception as exc:
        logger.warning("[gauges] app.user_locations fetch failed: %s", exc)

    try:
        rows = pg.fetch(
            """
            select distinct user_id
              from public.app_user_entitlements_active
             where is_active = true
            """
        )
        user_ids.update([r["user_id"] for r in rows if r.get("user_id")])
    except Exception as exc:
        logger.warning("[gauges] entitlements fetch failed: %s", exc)

    return user_ids


def _iter_users(user_ids: Iterable[str], limit: int | None) -> Iterable[str]:
    count = 0
    for uid in user_ids:
        yield uid
        count += 1
        if limit and count >= limit:
            break


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute daily gauge scores for users.")
    parser.add_argument("--day", default=_today_utc(), help="Day in YYYY-MM-DD (UTC).")
    parser.add_argument("--user-id", default=None, help="Optional single user_id override.")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of users processed.")
    parser.add_argument("--force", action="store_true", help="Recompute even if inputs_hash matches.")
    args = parser.parse_args()

    if args.user_id:
        user_ids = {args.user_id}
    else:
        user_ids = _fetch_user_ids()

    logger.info("[gauges] scoring users=%d day=%s", len(user_ids), args.day)

    for uid in _iter_users(sorted(user_ids), args.limit):
        try:
            result = score_user_day(uid, args.day, force=args.force)
            logger.info("[gauges] user=%s day=%s ok=%s skipped=%s", uid, args.day, result.get("ok"), result.get("skipped"))
        except Exception as exc:
            logger.exception("[gauges] user=%s failed: %s", uid, exc)

    logger.info("[gauges] done")


if __name__ == "__main__":
    main()
