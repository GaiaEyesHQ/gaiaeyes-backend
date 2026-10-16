from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import pytest
import yaml

from bots.notifications import github_notification_test as job
from bots.notifications import send_test_notification as diagnostic

NOW = datetime(2026, 10, 16, 3, tzinfo=timezone.utc)
UPDATED = "2026-10-16T01:28:43.535137+00:00"
REGISTRATION = str(UUID(int=11))
ACCOUNT = str(UUID(int=12))


class FixtureDB:
    def __init__(self):
        self.reads = []
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.create_function("convert_to", 2, lambda text, encoding: text.encode())
        self.conn.create_function("sha256", 1, lambda data: hashlib.sha256(data).digest())
        self.conn.create_function("encode", 2, lambda data, encoding: data.hex())
        self.conn.executescript("""
          create table user_push_tokens (id text primary key, user_id text, platform text,
            enabled boolean, app_version text, environment text, updated_at text, device_token text);
          create table user_notification_preferences (user_id text primary key, enabled boolean);
        """)
        for registration, account, token in [(11, 12, "SECRET_TARGET"),
                                              (13, 12, "SECRET_SECOND_DEVICE"),
                                              (14, 15, "SECRET_OTHER_ACCOUNT")]:
            self.conn.execute("insert into user_push_tokens values (?, ?, 'ios', 1, '1.0.1 (9)', 'dev', ?, ?)",
                              (str(UUID(int=registration)), str(UUID(int=account)), UPDATED, token))
        self.conn.executemany("insert into user_notification_preferences values (?, 1)",
                              [(ACCOUNT,), (str(UUID(int=15)),)])

    def fetchrow(self, query, *params):
        self.reads.append(query)
        assert query.strip().startswith("select ")
        sql = query.replace("app.", "").replace("::text", "").replace("%s::uuid", "?").replace("%s::timestamptz", "?").replace("%s", "?")
        row = self.conn.execute(sql, tuple(p.isoformat() if isinstance(p, datetime) else p for p in params)).fetchone()
        return dict(row) if row else None


@pytest.fixture
def setup(monkeypatch, tmp_path):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW
    monkeypatch.setattr(job, "datetime", Clock)
    monkeypatch.setattr(job, "REGISTRATION_SHA256", hashlib.sha256(REGISTRATION.encode()).hexdigest())
    monkeypatch.setattr(job, "ACCOUNT_SHA256", hashlib.sha256(ACCOUNT.encode()).hexdigest())
    env = dict(job.CONTEXT, GITHUB_RUN_ID="12345", EXPECTED_UPDATED_AT=UPDATED,
               RUNNER_TEMP=str(tmp_path), RESERVATION_ARTIFACT_ID="34567",
               RESERVATION_ARTIFACT_DIGEST="a" * 64)
    env.update({key: "SECRET_CONFIGURATION" for key in diagnostic.APNS_ENV})
    env["APNS_BUNDLE_ID"] = diagnostic.TOPIC
    receipt = tmp_path / job.CAMPAIGN
    job.reserve(env, receipt)
    calls = []
    monkeypatch.setattr(diagnostic, "create_provider_token", lambda **kw: "SECRET_AUTH")
    def send(**kwargs):
        calls.append(kwargs)
        return {"ok": True, "status_code": 200}
    monkeypatch.setattr(diagnostic, "send_apns_notification", send)
    return FixtureDB(), env, receipt, calls


def test_exact_hashed_target_sends_once_and_keeps_raw_ids_out_of_receipt(setup):
    db, env, receipt, calls = setup
    before = list(db.conn.iterdump())
    result = job.execute_once(db, env, receipt)
    assert result["status"] == "accepted" and len(calls) == 1
    assert calls[0]["device_token"] == "SECRET_TARGET" and calls[0]["sandbox"] is True
    assert calls[0]["body"]["aps"]["alert"] == {"title": "Gaia Eyes", "body": "Gaia Eyes notification test"}
    assert list(db.conn.iterdump()) == before
    public = json.dumps(result) + "".join(p.read_text() for p in receipt.iterdir())
    assert "SECRET" not in public and REGISTRATION not in public and ACCOUNT not in public
    assert job.execute_once(db, env, receipt)["reason"] == "attempt_already_reserved_do_not_retry"
    assert len(calls) == 1


@pytest.mark.parametrize("key", list(job.CONTEXT))
def test_all_native_context_constraints_fail_closed_before_database(setup, key):
    db, env, receipt, calls = setup
    env[key] = "unexpected"
    assert job.execute_once(db, env, receipt)["reason"] == "github_context_or_repeat_guard"
    assert db.reads == [] and calls == []


@pytest.mark.parametrize("key,value", [
    ("GITHUB_RUN_ID", ""), ("GITHUB_RUN_ID", "0"), ("RUNNER_DEBUG", "1"),
    ("GITHUB_RUN_NUMBER", "1"), ("GITHUB_RUN_NUMBER", "3"),
    ("GITHUB_RUN_NUMBER", "999"), ("GITHUB_RUN_ATTEMPT", "2"),
    ("GITHUB_RUN_ATTEMPT", "3"),
])
def test_duplicate_dispatch_and_rerun_on_fresh_runner_never_sends(setup, tmp_path, key, value):
    db, env, receipt, calls = setup
    assert job.execute_once(db, env, receipt)["status"] == "accepted"
    env[key] = value
    # A replacement runner has no copy of the old local receipt.
    result = job.execute_once(db, env, tmp_path / "fresh-runner")
    assert result["reason"] == "github_context_or_repeat_guard" and len(calls) == 1


def test_expired_authorization_stops_without_reading_database(setup, monkeypatch):
    db, env, receipt, calls = setup
    monkeypatch.setattr(job, "DEADLINE", NOW)
    assert job.execute_once(db, env, receipt)["reason"] == "github_context_or_repeat_guard"
    assert db.reads == [] and calls == []


@pytest.mark.parametrize("key,value", [
    ("RESERVATION_ARTIFACT_ID", ""), ("RESERVATION_ARTIFACT_ID", "0"),
    ("RESERVATION_ARTIFACT_DIGEST", ""), ("RESERVATION_ARTIFACT_DIGEST", "z" * 64),
])
def test_unconfirmed_remote_reservation_blocks_send(setup, key, value):
    db, env, receipt, calls = setup
    env[key] = value
    assert job.execute_once(db, env, receipt)["reason"] == "durable_reservation_unconfirmed"
    assert db.reads == [] and calls == []


@pytest.mark.parametrize("content", ["{}", "bad json", None])
def test_missing_or_altered_reservation_fails_closed(setup, content):
    db, env, receipt, calls = setup
    path = receipt / "reservation.json"
    if content is None:
        path.unlink()
    else:
        path.write_text(content)
    assert job.execute_once(db, env, receipt)["reason"] == "durable_reservation_unconfirmed"
    assert db.reads == [] and calls == []


def test_reserving_again_never_overwrites_existing_reservation(setup):
    db, env, receipt, calls = setup
    before = (receipt / "reservation.json").read_text()
    with pytest.raises(FileExistsError):
        job.reserve(env, receipt)
    assert (receipt / "reservation.json").read_text() == before
    assert calls == []


@pytest.mark.parametrize("mutation", [
    "update user_push_tokens set enabled = 0 where id = ?",
    "update user_push_tokens set app_version = '1.0.1 (8)' where id = ?",
    "update user_push_tokens set environment = 'prod' where id = ?",
    "update user_push_tokens set platform = 'android' where id = ?",
    "update user_push_tokens set updated_at = 'changed' where id = ?",
    "delete from user_push_tokens where id = ?",
    "update user_notification_preferences set enabled = 0 where user_id = ?",
])
def test_target_mismatch_does_not_fall_back_to_second_device(setup, mutation):
    db, env, receipt, calls = setup
    db.conn.execute(mutation, (ACCOUNT if "preferences" in mutation else REGISTRATION,))
    assert job.execute_once(db, env, receipt)["reason"] == "target_metadata_or_preferences_changed"
    assert calls == [] and all("device_token" not in q for q in db.reads)


def test_failed_transport_consumes_opportunity_even_without_result_artifact(setup, monkeypatch, tmp_path):
    db, env, receipt, calls = setup
    def crash(**kwargs):
        calls.append(kwargs)
        raise RuntimeError("SECRET_TRANSPORT_ERROR")
    monkeypatch.setattr(diagnostic, "send_apns_notification", crash)
    result = job.execute_once(db, env, receipt)
    assert result["status"] == "uncertain_do_not_retry" and len(calls) == 1
    assert "SECRET" not in json.dumps(result)
    env["GITHUB_RUN_ATTEMPT"] = "2"
    assert job.execute_once(db, env, tmp_path / "new-runner")["status"] == "blocked_no_send"
    assert len(calls) == 1


def test_wrong_returned_identifiers_are_rejected(setup, monkeypatch):
    db, env, receipt, calls = setup
    monkeypatch.setattr(db, "fetchrow", lambda *args: {"id": str(UUID(int=13)), "user_id": ACCOUNT})
    assert job.execute_once(db, env, receipt)["reason"] == "target_metadata_or_preferences_changed"
    assert calls == []


def test_workflow_has_one_guarded_secret_step_after_immutable_reservation():
    root = Path(__file__).resolve().parents[2]
    path = root / ".github/workflows/phone-notification-test-20261016.yml"
    data = yaml.safe_load(path.read_text())
    assert set(data["on"]) == {"workflow_dispatch"}
    assert data["permissions"] == {"contents": "read"}
    assert data["concurrency"] == {"group": job.CAMPAIGN, "cancel-in-progress": False}
    assert list(data["jobs"]) == ["send-once"]
    spec = data["jobs"]["send-once"]
    assert "strategy" not in spec and spec["timeout-minutes"] == 5
    for condition in ("github.run_number == 2", "github.run_attempt == 1", "github.workflow_ref", "github.repository_id", "github.actor_id"):
        assert condition in spec["if"]
    steps = spec["steps"]
    secret_steps = [i for i, step in enumerate(steps) if "secrets." in json.dumps(step)]
    assert len(secret_steps) == 1
    send_index = secret_steps[0]
    upload = steps[send_index - 1]
    assert upload["id"] == "reserve" and upload["with"]["overwrite"] is False
    assert upload["with"]["if-no-files-found"] == "error"
    assert "if" not in steps[send_index] and "continue-on-error" not in upload
    assert steps[send_index]["env"]["RESERVATION_ARTIFACT_ID"] == "${{ steps.reserve.outputs.artifact-id }}"
    assert steps[send_index]["run"] == "python -m bots.notifications.github_notification_test"
    assert "send_push_notifications" not in path.read_text()
    assert "env" not in data and "env" not in spec
    for step in steps:
        if "uses" in step:
            sha = step["uses"].split("@", 1)[1]
            assert len(sha) == 40 and all(c in "0123456789abcdef" for c in sha)


@pytest.mark.parametrize("run_number,attempt", [("1", "1"), ("1", "2"), ("2", "2"), ("2", "3"), ("3", "1"), ("999", "1")])
def test_only_replacement_slot_can_read_database_or_attempt_send(setup, run_number, attempt):
    db, env, receipt, calls = setup
    env.update(GITHUB_RUN_NUMBER=run_number, GITHUB_RUN_ATTEMPT=attempt)
    assert job.execute_once(db, env, receipt)["reason"] == "github_context_or_repeat_guard"
    assert db.reads == [] and calls == []


def test_replacement_reservation_records_exact_slot_and_predecessor(setup):
    db, env, receipt, calls = setup
    record = json.loads((receipt / "reservation.json").read_text())
    assert record["run_number"] == "2" and record["run_attempt"] == "1"
    assert record["previous_blocked_run_id"] == "38844659979"
    assert job.ATTEMPT_ID != UUID("bce5e846-1942-4d98-a077-5ea17110f542")
    assert job.context_ready(env)
