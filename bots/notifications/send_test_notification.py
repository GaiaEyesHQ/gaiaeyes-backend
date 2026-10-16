"""Opt-in, one-registration APNs diagnostic; never consumes the notification queue.

Run with --help. Without --execute this only checks metadata/configuration.
Keep the same attempt ID and receipt directory after ANY uncertain outcome.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import UUID

from bots.notifications.apns import create_provider_token, send_apns_notification

TOPIC = "com.gaiaeyes.GaiaExporter"
APNS_ENV = ("APNS_TEAM_ID", "APNS_KEY_ID", "APNS_BUNDLE_ID", "APNS_PRIVATE_KEY")
KNOWN_REASONS = frozenset({
    "BadDeviceToken", "DeviceTokenNotForTopic", "Unregistered", "BadTopic",
    "TopicDisallowed", "InvalidProviderToken", "ExpiredProviderToken",
    "MissingProviderToken", "Forbidden", "BadPayload", "PayloadTooLarge",
    "TooManyRequests", "InternalServerError", "ServiceUnavailable", "Shutdown",
})

# Both reads use the exact same predicates. No account-wide recipient fallback.
RECIPIENT_FROM = """
  from app.user_push_tokens t
  join app.user_notification_preferences p on p.user_id = t.user_id
 where t.id = %s::uuid and t.user_id = %s::uuid
   and t.platform = 'ios' and t.enabled = true and p.enabled = true
   and t.app_version = %s and t.environment = %s
   and t.updated_at = %s::timestamptz
"""


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("timestamp requires a timezone")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class Target:
    registration_id: UUID
    user_id: UUID
    app_version: str
    environment: str
    updated_at: datetime
    attempt_id: UUID

    def params(self) -> tuple[str, str, str, str, datetime]:
        return (str(self.registration_id), str(self.user_id), self.app_version,
                self.environment, self.updated_at)


def _result(target: Target, status: str, **fields: Any) -> dict[str, Any]:
    # Only caller-selected identifiers and allowlisted status fields leave this tool.
    return {"attempt_id": str(target.attempt_id),
            "registration_fingerprint": hashlib.sha256(str(target.registration_id).encode()).hexdigest(),
            "status": status, **fields}


def run_test(*, db: Any, target: Target, receipt_dir: Path, execute: bool = False,
             environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    env = os.environ if environ is None else environ
    if (target.environment not in {"dev", "prod"} or not target.app_version.strip()
            or target.updated_at.tzinfo is None):
        return _result(target, "blocked_no_send", reason="invalid_target")
    if any(not env.get(name, "").strip() for name in APNS_ENV):
        return _result(target, "blocked_no_send", reason="missing_existing_apns_configuration")
    if env["APNS_BUNDLE_ID"] != TOPIC:
        return _result(target, "blocked_no_send", reason="topic_mismatch")
    try:
        ready = db.fetchrow("select t.id" + RECIPIENT_FROM, *target.params())
    except Exception:
        return _result(target, "blocked_no_send", reason="metadata_read_failed")
    if not ready:
        return _result(target, "blocked_no_send", reason="registration_or_preferences_changed")
    if not execute:
        return _result(target, "preflight_ready", provider_attempted=False)
    try:
        auth = create_provider_token(team_id=env["APNS_TEAM_ID"], key_id=env["APNS_KEY_ID"],
                                     private_key_pem=env["APNS_PRIVATE_KEY"])
    except Exception:
        return _result(target, "blocked_no_send", reason="provider_signing_failed")

    # Exclusive, flushed receipt reserves this attempt before any token read/send.
    # The directory must already exist and be retained across retries/restarts.
    receipt = receipt_dir / f"{target.attempt_id}.jsonl"
    try:
        fd = os.open(receipt, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return _result(target, "blocked_no_send", reason="attempt_already_reserved_do_not_retry")
    except OSError:
        return _result(target, "blocked_no_send", reason="receipt_unavailable")

    provider_attempted = False
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(json.dumps(_result(target, "reserved_do_not_retry")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
            directory_fd = os.open(receipt_dir, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            # Revalidate immediately before use. Token stays internal to the backend
            # process and is never emitted, persisted in the receipt, or logged.
            row = db.fetchrow("select t.device_token" + RECIPIENT_FROM, *target.params())
            if not row or not isinstance(row.get("device_token"), str) or not row["device_token"]:
                result = _result(target, "blocked_no_send", reason="registration_or_preferences_changed")
            else:
                provider_attempted = True
                response = send_apns_notification(
                    device_token=row["device_token"],
                    body={"aps": {"alert": {"title": "Gaia Eyes", "body": "Gaia Eyes notification test"},
                                  "sound": "default"}},
                    auth_token=auth, topic=TOPIC, sandbox=target.environment == "dev",
                    collapse_id=str(target.attempt_id), timeout_seconds=15,
                )
                status = response.get("status_code")
                if response.get("ok") is True and status == 200:
                    result = _result(target, "accepted", provider_status=200, device_receipt="unconfirmed")
                elif isinstance(status, int) and 400 <= status <= 599:
                    body = response.get("body")
                    reason = body.get("reason") if isinstance(body, dict) else None
                    result = _result(target, "rejected", provider_status=status,
                                     reason=reason if reason in KNOWN_REASONS else "unrecognized_provider_reason")
                else:
                    result = _result(target, "uncertain_do_not_retry")
            handle.write(json.dumps(result) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
            return result
    except Exception:
        # Never expose exception strings, command arguments, provider bodies, or DSNs.
        return _result(target, "uncertain_do_not_retry" if provider_attempted else "blocked_no_send",
                       reason="attempt_reserved_do_not_retry")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registration-id", type=UUID, required=True)
    parser.add_argument("--user-id", type=UUID, required=True)
    parser.add_argument("--expected-app-version", required=True)
    parser.add_argument("--expected-environment", choices=("dev", "prod"), required=True)
    parser.add_argument("--expected-updated-at", type=_timestamp, required=True)
    parser.add_argument("--attempt-id", type=UUID, required=True)
    parser.add_argument("--receipt-dir", type=Path, required=True,
                        help="Existing private persistent directory; retain it and the same attempt ID")
    parser.add_argument("--execute", action="store_true", help="Send once; default is metadata-only preflight")
    args = parser.parse_args(argv)
    target = Target(args.registration_id, args.user_id, args.expected_app_version,
                    args.expected_environment, args.expected_updated_at, args.attempt_id)
    try:
        from services.db import pg
        with pg.operation_timeouts(connect_timeout=5, statement_timeout_ms=5000):
            result = run_test(db=pg, target=target, receipt_dir=args.receipt_dir, execute=args.execute)
    except Exception:
        result = _result(target, "blocked_no_send", reason="existing_database_connection_unavailable")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] in {"preflight_ready", "accepted"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
