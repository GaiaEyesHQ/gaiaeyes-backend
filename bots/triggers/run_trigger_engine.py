#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging
import os
from datetime import datetime, timezone
from typing import List

from services.db import pg
from bots.triggers.trigger_engine import evaluate_user_triggers
from bots.earthscope_post.member_earthscope_generate import run_for_user


LOG_LEVEL = os.getenv("GAIA_LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)


def _today_utc() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _fetch_paid_users() -> List[str]:
    keys = [k.strip() for k in os.getenv("ENTITLEMENT_KEYS", "plus,pro").split(",") if k.strip()]
    try:
        rows = pg.fetch(
            """
            select distinct user_id
              from public.app_user_entitlements_active
             where is_active = true
               and entitlement_key = any(%s)
            """,
            keys,
        )
        return [r["user_id"] for r in rows if r.get("user_id")]
    except Exception as exc:
        logger.warning("[triggers] entitlements fetch failed: %s", exc)
        return []


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate triggers and update member EarthScope posts.")
    parser.add_argument("--day", default=_today_utc(), help="Day in YYYY-MM-DD (UTC).")
    parser.add_argument("--user-id", default=None, help="Optional single user_id override.")
    parser.add_argument("--limit", type=int, default=None, help="Limit users processed.")
    args = parser.parse_args()

    if args.user_id:
        users = [args.user_id]
    else:
        users = _fetch_paid_users()

    if args.limit:
        users = users[: args.limit]

    logger.info("[triggers] users=%d day=%s", len(users), args.day)
    for uid in users:
        try:
            _alerts, events = evaluate_user_triggers(uid, args.day)
            if events:
                logger.info("[triggers] user=%s events=%d", uid, len(events))
                run_for_user(uid, args.day, trigger_events=events, force=False)
        except Exception as exc:
            logger.exception("[triggers] user=%s failed: %s", uid, exc)


if __name__ == "__main__":
    main()
