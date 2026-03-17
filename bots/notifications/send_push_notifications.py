#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List

from bots.notifications.apns import create_provider_token, send_apns_notification
from bots.notifications.push_logic import utc_now
from services.db import pg


LOG_LEVEL = os.getenv("GAIA_LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)

_INVALID_TOKEN_REASONS = {
    "BadDeviceToken",
    "DeviceTokenNotForTopic",
    "TopicDisallowed",
    "Unregistered",
}


def _fetch_queued_events(limit: int | None = None, user_id: str | None = None) -> List[Dict[str, Any]]:
    params: List[Any] = []
    where = ["status = 'queued'"]
    if user_id:
        where.append("user_id = %s")
        params.append(user_id)

    limit_sql = ""
    if limit and limit > 0:
        limit_sql = "limit %s"
        params.append(limit)

    sql = f"""
        select id,
               user_id,
               family,
               event_key,
               severity,
               title,
               body,
               payload,
               dedupe_key,
               created_at
          from content.push_notification_events
         where {' and '.join(where)}
         order by created_at asc
         {limit_sql}
    """
    return pg.fetch(sql, *params)


def _fetch_user_tokens(user_id: str) -> List[Dict[str, Any]]:
    return pg.fetch(
        """
        select id, device_token, environment
          from app.user_push_tokens
         where user_id = %s
           and enabled = true
         order by updated_at desc, created_at desc
        """,
        user_id,
    )


def _disable_token(token_id: str, reason: str, now_utc: datetime) -> None:
    pg.execute(
        """
        update app.user_push_tokens
           set enabled = false,
               updated_at = %s
         where id = %s
        """,
        now_utc,
        token_id,
    )
    logger.info("[push-send] disabled token=%s reason=%s", token_id, reason)


def _mark_event_status(event_id: str, status: str, now_utc: datetime, error_text: str | None = None) -> None:
    sent_at = now_utc if status == "sent" else None
    pg.execute(
        """
        update content.push_notification_events
           set status = %s,
               sent_at = %s,
               error_text = %s
         where id = %s
        """,
        status,
        sent_at,
        error_text,
        event_id,
    )


def _normalized_payload(raw: Any) -> Dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            return {}
    return dict(raw) if isinstance(raw, dict) else {}


def _apns_body(event: Dict[str, Any]) -> Dict[str, Any]:
    payload = _normalized_payload(event.get("payload"))
    return {
        "aps": {
            "alert": {
                "title": str(event.get("title") or "").strip(),
                "body": str(event.get("body") or "").strip(),
            },
            "sound": "default",
        },
        **payload,
    }


def _iter_events(rows: Iterable[Dict[str, Any]], limit: int | None) -> Iterable[Dict[str, Any]]:
    count = 0
    for row in rows:
        yield row
        count += 1
        if limit and count >= limit:
            break


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description="Send queued Gaia Eyes push notifications through APNs.")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of queued events processed.")
    parser.add_argument("--user-id", default=None, help="Optional single user_id override.")
    args = parser.parse_args()

    queued_events = _fetch_queued_events(limit=args.limit, user_id=args.user_id)
    if not queued_events:
        logger.info("[push-send] no queued events")
        return

    team_id = _required_env("APNS_TEAM_ID")
    key_id = _required_env("APNS_KEY_ID")
    bundle_id = _required_env("APNS_BUNDLE_ID")
    private_key = _required_env("APNS_PRIVATE_KEY")
    auth_token = create_provider_token(team_id=team_id, key_id=key_id, private_key_pem=private_key)
    logger.info("[push-send] queued=%d", len(queued_events))

    sent = 0
    skipped = 0
    failed = 0
    now_utc = utc_now()

    for event in _iter_events(queued_events, args.limit):
        event_id = str(event.get("id") or "").strip()
        user_id = str(event.get("user_id") or "").strip()
        if not event_id or not user_id:
            continue

        tokens = _fetch_user_tokens(user_id)
        if not tokens:
            _mark_event_status(event_id, "skipped", now_utc, "no_enabled_tokens")
            skipped += 1
            continue

        body = _apns_body(event)
        collapse_id = str(event.get("dedupe_key") or event_id)

        any_success = False
        errors: List[str] = []
        for token_row in tokens:
            token_id = str(token_row.get("id") or "").strip()
            device_token = str(token_row.get("device_token") or "").strip()
            environment = str(token_row.get("environment") or "prod").strip().lower() or "prod"
            sandbox = environment == "dev"
            result = send_apns_notification(
                device_token=device_token,
                body=body,
                auth_token=auth_token,
                topic=bundle_id,
                sandbox=sandbox,
                collapse_id=collapse_id,
            )
            if result.get("ok"):
                any_success = True
                continue

            reason = (
                (_normalized_payload(result.get("body")).get("reason"))
                or result.get("raw_body")
                or result.get("stderr")
                or f"http_{result.get('status_code') or 0}"
            )
            errors.append(str(reason))
            if str(reason) in _INVALID_TOKEN_REASONS and token_id:
                _disable_token(token_id, str(reason), now_utc)

        if any_success:
            _mark_event_status(event_id, "sent", now_utc, None)
            sent += 1
        else:
            _mark_event_status(event_id, "failed", now_utc, "; ".join(errors[:3]) or "apns_send_failed")
            failed += 1

    logger.info("[push-send] done sent=%d skipped=%d failed=%d", sent, skipped, failed)


if __name__ == "__main__":
    main()
