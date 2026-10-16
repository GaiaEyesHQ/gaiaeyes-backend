"""One authorized, generic phone test; this workflow identity must never be reset."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import UUID

from bots.notifications.send_test_notification import APNS_ENV, TOPIC, Target, _timestamp, run_test

CAMPAIGN = "phone-notification-test-20261016"
ATTEMPT_ID = UUID("bce5e846-1942-4d98-a077-5ea17110f542")
REGISTRATION_SHA256 = "78d618c110b38c58b00ebc9ae02889384c62a5405d5bb91a04b4fdf3f8256d86"
ACCOUNT_SHA256 = "85493336464a41c3ddd9eee51518f4480574d901f7a0837174f9218d629f3583"
WORKFLOW_REF = "GaiaEyesHQ/gaiaeyes-backend/.github/workflows/phone-notification-test-20261016.yml@refs/heads/main"
CONTEXT = {
    "GITHUB_ACTIONS": "true",
    "GITHUB_REPOSITORY": "GaiaEyesHQ/gaiaeyes-backend",
    "GITHUB_REPOSITORY_ID": "1031061846",
    "GITHUB_ACTOR_ID": "224334203",
    "GITHUB_EVENT_NAME": "workflow_dispatch",
    "GITHUB_REF": "refs/heads/main",
    "GITHUB_WORKFLOW_REF": WORKFLOW_REF,
    "GITHUB_RUN_NUMBER": "1",
    "GITHUB_RUN_ATTEMPT": "1",
    "RUNNER_ENVIRONMENT": "github-hosted",
    "CONFIRM_SINGLE_SEND": "true",
}
DEADLINE = datetime(2026, 10, 17, tzinfo=timezone.utc)


def context_ready(env: Mapping[str, str], now: datetime | None = None) -> bool:
    """GitHub's persisted counters, not runner storage, consume the sole opportunity."""
    return (
        all(env.get(key) == value for key, value in CONTEXT.items())
        and env.get("GITHUB_RUN_ID", "").isdigit()
        and int(env["GITHUB_RUN_ID"]) > 0
        and not env.get("RUNNER_DEBUG")
        and (now or datetime.now(timezone.utc)) < DEADLINE
    )


def resolve_target(db: Any, updated_at: datetime) -> Target | None:
    # Only this registration/account pair can match. Raw identifiers stay inside
    # the runner; the public repository, logs, and receipts contain fingerprints.
    row = db.fetchrow(
        """
        select t.id, t.user_id
          from app.user_push_tokens t
          join app.user_notification_preferences p on p.user_id = t.user_id
         where encode(sha256(convert_to(t.id::text, 'UTF8')), 'hex') = %s
           and encode(sha256(convert_to(t.user_id::text, 'UTF8')), 'hex') = %s
           and t.platform = 'ios' and t.enabled = true and p.enabled = true
           and t.app_version = '1.0.1 (9)' and t.environment = 'dev'
           and t.updated_at = %s::timestamptz
        """,
        REGISTRATION_SHA256, ACCOUNT_SHA256, updated_at,
    )
    if not row:
        return None
    registration, account = UUID(str(row["id"])), UUID(str(row["user_id"]))
    if (hashlib.sha256(str(registration).encode()).hexdigest() != REGISTRATION_SHA256
            or hashlib.sha256(str(account).encode()).hexdigest() != ACCOUNT_SHA256):
        return None
    return Target(registration, account, "1.0.1 (9)", "dev", updated_at, ATTEMPT_ID)


def reservation(env: Mapping[str, str]) -> dict[str, str]:
    return {"campaign": CAMPAIGN, "run_id": env["GITHUB_RUN_ID"],
            "run_number": "1", "run_attempt": "1", "status": "reserved_do_not_retry"}


def reserve(env: Mapping[str, str], receipt_dir: Path) -> None:
    """Upload this file as an immutable artifact before the secret-bearing step."""
    receipt_dir.mkdir(mode=0o700, parents=False, exist_ok=True)
    with (receipt_dir / "reservation.json").open("x") as handle:
        handle.write(json.dumps(reservation(env), sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    directory_fd = os.open(receipt_dir, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def reservation_ready(env: Mapping[str, str], receipt_dir: Path) -> bool:
    artifact_id = env.get("RESERVATION_ARTIFACT_ID", "")
    digest = env.get("RESERVATION_ARTIFACT_DIGEST", "")
    if not artifact_id.isdigit() or int(artifact_id) <= 0:
        return False
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        return False
    try:
        return json.loads((receipt_dir / "reservation.json").read_text()) == reservation(env)
    except (OSError, ValueError):
        return False


def execute_once(db: Any, env: Mapping[str, str], receipt_dir: Path) -> dict[str, Any]:
    if not context_ready(env):
        return {"status": "blocked_no_send", "reason": "github_context_or_repeat_guard"}
    if not reservation_ready(env, receipt_dir):
        return {"status": "blocked_no_send", "reason": "durable_reservation_unconfirmed"}
    if any(not env.get(name, "").strip() for name in APNS_ENV) or env.get("APNS_BUNDLE_ID") != TOPIC:
        return {"status": "blocked_no_send", "reason": "existing_apns_configuration_unavailable"}
    may_have_sent = False
    try:
        target = resolve_target(db, _timestamp(env.get("EXPECTED_UPDATED_AT", "")))
        if target is None:
            return {"status": "blocked_no_send", "reason": "target_metadata_or_preferences_changed"}
        if not context_ready(env):
            return {"status": "blocked_no_send", "reason": "github_context_or_repeat_guard"}
        receipt_dir.mkdir(mode=0o700, parents=False, exist_ok=True)
        may_have_sent = True
        return run_test(db=db, target=target, receipt_dir=receipt_dir, execute=True, environ=env)
    except Exception:
        return {"status": "uncertain_do_not_retry" if may_have_sent else "blocked_no_send",
                "reason": "diagnostic_failed_do_not_retry"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-context", action="store_true")
    parser.add_argument("--reserve", action="store_true")
    args = parser.parse_args(argv)
    if not context_ready(os.environ):
        print(json.dumps({"status": "blocked_no_send", "reason": "github_context_or_repeat_guard"}))
        return 1
    if args.check_context:
        print(json.dumps({"status": "context_ready", "run_id": os.environ["GITHUB_RUN_ID"]}))
        return 0
    receipt_dir = Path(os.environ["RUNNER_TEMP"]) / CAMPAIGN
    if args.reserve:
        try:
            reserve(os.environ, receipt_dir)
        except Exception:
            print(json.dumps({"status": "blocked_no_send", "reason": "reservation_failed"}))
            return 1
        print(json.dumps(reservation(os.environ), sort_keys=True))
        return 0
    try:
        from services.db import pg
        with pg.operation_timeouts(connect_timeout=5, statement_timeout_ms=5000):
            result = execute_once(pg, os.environ, receipt_dir)
    except Exception:
        result = {"status": "blocked_no_send", "reason": "existing_database_configuration_unavailable"}
    result.update({"run_id": os.environ["GITHUB_RUN_ID"], "run_number": 1, "run_attempt": 1,
                   "campaign": CAMPAIGN, "device_receipt": "unconfirmed",
                   "reservation_artifact_id": os.environ.get("RESERVATION_ARTIFACT_ID", "")})
    print(json.dumps(result, sort_keys=True))
    # Best-effort supplemental evidence. Absence never permits another execution.
    try:
        receipt_dir.mkdir(mode=0o700, parents=False, exist_ok=True)
        (receipt_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    except OSError:
        print(json.dumps({"status": "receipt_export_unavailable_do_not_retry"}))
        return 1
    return 0 if result["status"] == "accepted" else 1


if __name__ == "__main__":
    raise SystemExit(main())
