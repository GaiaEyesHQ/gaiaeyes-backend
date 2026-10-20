#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List
from email.utils import parsedate_to_datetime

from bots.notifications.apns import create_provider_token, send_apns_notification
from bots.notifications.fcm import FcmClient
from bots.notifications.push_logic import family_allowed, is_within_quiet_hours, normalize_preferences, utc_now
from services.db import pg


LOG_LEVEL = os.getenv("GAIA_LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)

_INVALID_TOKEN_REASONS = {
    "BadDeviceToken",
    "DeviceTokenNotForTopic",
    "Unregistered",
}
_INVALID_FCM_REASONS = {"UNREGISTERED", "registration-token-not-registered"}


def _fetch_queued_events(limit: int | None = None, user_id: str | None = None) -> List[Dict[str, Any]]:
    params: List[Any] = [utc_now().isoformat()]
    where = ["status = 'queued'", "coalesce(payload->'_push_delivery'->>'retry_after', '') <= %s"]
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
         order by coalesce(payload->'_push_delivery'->>'checked_at', '') asc, created_at asc
         {limit_sql}
    """
    return pg.fetch(sql, *params)


def _fetch_user_tokens(user_id: str) -> List[Dict[str, Any]]:
    return pg.fetch(
        """
        select id, platform, device_token, environment
          from app.user_push_tokens
         where user_id = %s
           and enabled = true
         order by updated_at desc, created_at desc
        """,
        user_id,
    )


def _fetch_preferences(user_id: str) -> Dict[str, Any]:
    row = pg.fetchrow(
        """
        select enabled, signal_alerts_enabled, local_condition_alerts_enabled,
               personalized_gauge_alerts_enabled, symptom_followups_enabled,
               symptom_followup_push_enabled, daily_checkins_enabled,
               daily_checkin_push_enabled, quiet_hours_enabled,
               to_char(quiet_start, 'HH24:MI') as quiet_start,
               to_char(quiet_end, 'HH24:MI') as quiet_end,
               time_zone, sensitivity, families
          from app.user_notification_preferences where user_id = %s
        """, user_id,
    )
    return normalize_preferences(row)


def _claim_event(event_id: str) -> Dict[str, Any] | None:
    # Commit before touching a provider. Concurrent workers cannot claim twice.
    # A crash/ambiguous outcome stays failed and is never automatically replayed.
    return pg.fetchrow(
        """update content.push_notification_events
              set status = 'failed', error_text = 'delivery_unconfirmed'
            where id = %s and status = 'queued'
              and coalesce(payload->'_push_delivery'->>'retry_after', '') <= %s
            returning *""", event_id, utc_now().isoformat(),
    )


def _event_policy(event: Dict[str, Any], preferences: Dict[str, Any], now: datetime) -> str | None:
    if not preferences.get("enabled"):
        return "notifications_disabled"
    payload = _normalized_payload(event.get("payload"))
    family = str(event.get("family") or "")
    severity = str(event.get("severity") or "")
    if family == "digest":
        children = payload.get("child_events")
        if not isinstance(children, list) or not children or not all(
            isinstance(child, dict) and family_allowed(
                preferences, str(child.get("family") or ""), str(child.get("severity") or "watch")
            ) for child in children
        ):
            return "category_disabled"
    elif not family_allowed(preferences, family, severity):
        return "category_disabled"
    max_age = None if family in {"symptom_followups", "daily_checkins"} else timedelta(hours=1)
    created = event.get("created_at")
    if not isinstance(created, datetime) or created > now or (max_age is not None and now - created > max_age):
        return "expired"
    if is_within_quiet_hours(
        now, enabled=bool(preferences.get("quiet_hours_enabled")),
        time_zone_name=str(preferences.get("time_zone") or "UTC"),
        quiet_start=str(preferences.get("quiet_start") or "22:00"),
        quiet_end=str(preferences.get("quiet_end") or "08:00"),
    ):
        return "quiet_hours"
    return None


def _prompt_policy(event: Dict[str, Any], now: datetime) -> str | None:
    if event.get("family") not in {"symptom_followups", "daily_checkins"}:
        return None
    prompt_id = _normalized_payload(event.get("payload")).get("prompt_id")
    if not prompt_id:
        return "prompt_no_longer_current"
    row = pg.fetchrow(
        """select status, delivered_at, push_delivery_enabled,
                  coalesce(snoozed_until, scheduled_for) as due_at
             from raw.user_feedback_prompts p where id = %s and user_id = %s
               and (p.prompt_type <> 'symptom_follow_up' or exists (
                 select 1 from raw.user_symptom_episodes ep
                  where ep.id = p.episode_id and ep.user_id = p.user_id and ep.current_state <> 'resolved'
                    and not (upper(ep.symptom_code) <> 'MIGRAINE' and ep.current_state = 'new')
                    and exists (select 1 from raw.user_symptom_episode_updates activity
                      where activity.episode_id = ep.id and activity.user_id = ep.user_id
                        and activity.metadata->>'activity_contract' = 'persistent_v1')
               ))""",
        prompt_id, event["user_id"],
    )
    due = (row or {}).get("due_at")
    delivered = (row or {}).get("delivered_at")
    explicitly_snoozed = bool(row and row.get("status") == "snoozed"
                              and isinstance(due, datetime)
                              and (delivered is None or due > delivered))
    if not (row and row.get("status") in {"pending", "snoozed"}
            and row.get("push_delivery_enabled") and (not delivered or explicitly_snoozed)
            and isinstance(due, datetime)):
        return "prompt_no_longer_current"
    if due > now:
        return "prompt_not_due"
    if due < now - timedelta(hours=24):
        return "expired"
    return None


def _send_once(send):
    try:
        return send()
    except Exception:
        # A transport exception is not proof of rejection.
        return {"ok": False, "status_code": 0}


def _retry_delay(result: Dict[str, Any], now: datetime) -> int:
    # APNs recommends waiting 15 minutes after 5xx. This also exceeds FCM's
    # one-minute minimum; honor a longer provider Retry-After when supplied.
    delay = 900
    raw = str(result.get("retry_after") or "")
    try:
        delay = max(delay, int(raw))
    except ValueError:
        try:
            delay = max(delay, int((parsedate_to_datetime(raw) - now).total_seconds()))
        except (ValueError, TypeError, OverflowError):
            pass
    return delay


def _defer_event(event: Dict[str, Any], now: datetime, reason: str, *, delay: int = 300, attempts: int | None = None) -> None:
    previous = _normalized_payload(_normalized_payload(event.get("payload")).get("_push_delivery"))
    metadata = {**previous, "checked_at": now.isoformat(),
                "retry_after": (now + timedelta(seconds=delay)).isoformat()}
    if attempts is not None:
        metadata["attempts"] = attempts
    pg.execute(
        """update content.push_notification_events
              set status='queued', sent_at=null, error_text=%s,
                  payload=jsonb_set(coalesce(payload, '{}'::jsonb), '{_push_delivery}', %s::jsonb)
            where id=%s and status='failed' and error_text='delivery_unconfirmed'""",
        reason, json.dumps(metadata), event["id"],
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
         where id = %s and status = 'failed' and error_text = 'delivery_unconfirmed'
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
    payload.pop("_push_delivery", None)
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


def _fcm_reason(result: Dict[str, Any]) -> str:
    body = _normalized_payload(result.get("body"))
    error = _normalized_payload(body.get("error"))
    details = error.get("details") if isinstance(error.get("details"), list) else []
    for detail in details:
        detail_map = _normalized_payload(detail)
        code = str(detail_map.get("errorCode") or "").strip()
        if code:
            return code
    return str(
        error.get("status")
        or f"http_{result.get('status_code') or 0}"
    )


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


def _missing_apns_env() -> List[str]:
    required = [
        "APNS_TEAM_ID",
        "APNS_KEY_ID",
        "APNS_BUNDLE_ID",
        "APNS_PRIVATE_KEY",
    ]
    return [name for name in required if not os.getenv(name, "").strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Send queued Gaia Eyes push notifications through APNs or FCM.")
    parser.add_argument("--limit", type=int, default=100, help="Limit number of queued events processed.")
    parser.add_argument("--user-id", default=None, help="Optional single user_id override.")
    args = parser.parse_args()
    if not 1 <= args.limit <= 100:
        parser.error("--limit must be between 1 and 100")

    queued_events = _fetch_queued_events(limit=args.limit, user_id=args.user_id)
    if not queued_events:
        logger.info("[push-send] no queued events")
        return

    apns_config: Dict[str, str] | None = None
    fcm_client: FcmClient | None = None
    fcm_config_error: str | None = None
    logger.info("[push-send] queued=%d", len(queued_events))

    sent = 0
    skipped = 0
    failed = 0
    unconfigured = 0

    for event in _iter_events(queued_events, args.limit):
        event_id = str(event.get("id") or "").strip()
        user_id = str(event.get("user_id") or "").strip()
        if not event_id or not user_id:
            continue

        claimed = _claim_event(event_id)
        if not claimed:
            continue
        # A concurrent worker may have deferred this row since our queue read.
        # Use the claim's current payload/attempt count, never the old snapshot.
        event = claimed
        now_utc = utc_now()
        preferences = _fetch_preferences(user_id)
        reason = _event_policy(event, preferences, now_utc)
        if reason:
            if reason == "quiet_hours":
                _defer_event(event, now_utc, reason)
            else:
                _mark_event_status(event_id, "skipped", now_utc, reason)
            skipped += 1
            continue
        prompt_reason = _prompt_policy(event, now_utc)
        if prompt_reason:
            if prompt_reason == "prompt_not_due":
                _defer_event(event, now_utc, prompt_reason)
            else:
                _mark_event_status(event_id, "skipped", now_utc, prompt_reason)
            skipped += 1
            continue

        tokens = _fetch_user_tokens(user_id)
        if not tokens:
            _mark_event_status(event_id, "skipped", now_utc, "no_enabled_tokens")
            logger.info(
                "[push-send] skipped event=%s user=%s family=%s reason=no_enabled_tokens",
                event_id,
                user_id,
                str(event.get("family") or "").strip() or "unknown",
            )
            skipped += 1
            continue

        body = _apns_body(event)
        collapse_id = hashlib.sha256(event_id.encode()).hexdigest()

        any_success = False
        any_attempt = False
        errors: List[str] = []
        retry_delays: List[int] = []
        retryable = True
        for token_row in tokens:
            token_id = str(token_row.get("id") or "").strip()
            device_token = str(token_row.get("device_token") or "").strip()
            environment = str(token_row.get("environment") or "prod").strip().lower() or "prod"
            platform = str(token_row.get("platform") or "ios").strip().lower() or "ios"
            if platform == "android":
                if fcm_client is None and fcm_config_error is None:
                    try:
                        fcm_client = FcmClient.from_environment()
                    except Exception:
                        fcm_config_error = "fcm_not_configured"
                if fcm_client is None:
                    retryable = False
                    errors.append(fcm_config_error or "fcm_not_configured")
                    continue
                any_attempt = True
                payload = _normalized_payload(event.get("payload"))
                payload.pop("_push_delivery", None)
                payload.setdefault("family", str(event.get("family") or ""))
                payload.setdefault("event_id", event_id)
                result = _send_once(lambda: fcm_client.send(
                    device_token=device_token,
                    title=str(event.get("title") or "").strip(),
                    body=str(event.get("body") or "").strip(),
                    data=payload,
                ))
                if result.get("ok"):
                    any_success = True
                    continue
                if result.get("status_code") in {429, 500, 503}:
                    retry_delays.append(_retry_delay(result, now_utc))
                else:
                    retryable = False
                reason = _fcm_reason(result) if result.get("status_code") else "delivery_unconfirmed"
                errors.append(reason)
                logger.warning(
                    "[push-send] fcm rejected event=%s user=%s family=%s token=%s status=%s reason=%s",
                    event_id,
                    user_id,
                    str(event.get("family") or "").strip() or "unknown",
                    token_id or "<missing>",
                    result.get("status_code") or 0,
                    reason,
                )
                if reason in _INVALID_FCM_REASONS and token_id:
                    _disable_token(token_id, reason, now_utc)
                continue

            if apns_config is None:
                missing_env = _missing_apns_env()
                if missing_env:
                    retryable = False
                    errors.append("missing_apns_env:" + ",".join(missing_env))
                    continue
                apns_config = {
                    "bundle_id": _required_env("APNS_BUNDLE_ID"),
                    "auth_token": create_provider_token(
                        team_id=_required_env("APNS_TEAM_ID"),
                        key_id=_required_env("APNS_KEY_ID"),
                        private_key_pem=_required_env("APNS_PRIVATE_KEY"),
                    ),
                }
            any_attempt = True
            result = _send_once(lambda: send_apns_notification(
                device_token=device_token,
                body=body,
                auth_token=apns_config["auth_token"],
                topic=apns_config["bundle_id"],
                sandbox=environment == "dev",
                collapse_id=collapse_id,
                timeout_seconds=15,
                expiration=int(now_utc.timestamp()) + 300,
            ))
            if result.get("ok"):
                any_success = True
                continue

            if result.get("status_code") in {429, 500, 503}:
                retry_delays.append(_retry_delay(result, now_utc))
            else:
                retryable = False
            reason = str(_normalized_payload(result.get("body")).get("reason") or
                         (f"http_{result.get('status_code')}" if result.get("status_code") else "delivery_unconfirmed"))
            errors.append(str(reason))
            logger.warning(
                "[push-send] apns rejected event=%s user=%s family=%s token=%s status=%s reason=%s",
                event_id,
                user_id,
                str(event.get("family") or "").strip() or "unknown",
                token_id or "<missing>",
                result.get("status_code") or 0,
                str(reason),
            )
            if str(reason) in _INVALID_TOKEN_REASONS and token_id:
                _disable_token(token_id, str(reason), now_utc)

        if any_success:
            _mark_event_status(event_id, "sent", now_utc, None)
            logger.info(
                "[push-send] provider_accepted event=%s user=%s family=%s device_receipt=unconfirmed",
                event_id,
                user_id,
                str(event.get("family") or "").strip() or "unknown",
            )
            sent += 1
        elif not any_attempt:
            _defer_event(event, now_utc, "provider_not_configured", delay=900)
            unconfigured += 1
            logger.warning(
                "[push-send] no provider configured event=%s user=%s; leaving queued error=%s",
                event_id,
                user_id,
                "; ".join(errors[:3]) or "provider_not_configured",
            )
        else:
            error_text = "; ".join(errors[:3]) or "push_send_failed"
            attempt = int(_normalized_payload(_normalized_payload(event.get("payload")).get("_push_delivery")).get("attempts") or 0) + 1
            if retryable and retry_delays and attempt < 3:
                _defer_event(event, now_utc, "provider_retry", delay=max(retry_delays) * attempt, attempts=attempt)
            else:
                _mark_event_status(event_id, "failed", now_utc, error_text)
            logger.warning(
                "[push-send] failed event=%s user=%s family=%s error=%s",
                event_id,
                user_id,
                str(event.get("family") or "").strip() or "unknown",
                error_text,
            )
            failed += 1

    logger.info("[push-send] done provider_accepted=%d skipped=%d failed=%d unconfigured=%d", sent, skipped, failed, unconfigured)
    if failed or unconfigured:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
