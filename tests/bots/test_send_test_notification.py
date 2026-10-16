from __future__ import annotations

import json
import os
import sqlite3
import stat
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from bots.notifications import apns
from bots.notifications import send_test_notification as diagnostic


TARGET = diagnostic.Target(
    UUID(int=1), UUID(int=2), "1.0.1 (9)", "dev",
    datetime(2026, 10, 15, 2, 42, 36, tzinfo=timezone.utc), UUID(int=3),
)
ENV = {name: "SECRET_CONFIG_SENTINEL" for name in diagnostic.APNS_ENV}
ENV["APNS_BUNDLE_ID"] = diagnostic.TOPIC


class FixtureDB:
    """Execute production SELECT predicates against several synthetic recipients."""
    def __init__(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript("""
          create table user_push_tokens (id text primary key, user_id text, platform text,
            enabled boolean, app_version text, environment text, updated_at text, device_token text);
          create table user_notification_preferences (user_id text primary key, enabled boolean);
        """)
        for registration, user, token in [(1, 2, "ONLY_TARGET_SECRET"),
                                           (4, 2, "OTHER_DEVICE_SECRET"),
                                           (5, 6, "OTHER_ACCOUNT_SECRET")]:
            self.conn.execute("insert into user_push_tokens values (?, ?, 'ios', 1, ?, ?, ?, ?)",
                              (str(UUID(int=registration)), str(UUID(int=user)), TARGET.app_version,
                               TARGET.environment, TARGET.updated_at.isoformat(), token))
        self.conn.executemany("insert into user_notification_preferences values (?, 1)",
                              [(str(UUID(int=2)),), (str(UUID(int=6)),)])
        self.reads = []
        self.before_private_read = None

    def fetchrow(self, query, *params):
        assert query.strip().lower().startswith("select ")
        assert "notification_events" not in query
        self.reads.append(query)
        if "device_token" in query and self.before_private_read:
            self.before_private_read()
        sql = query.replace("app.", "").replace("%s::uuid", "?").replace("%s::timestamptz", "?").replace("%s", "?")
        args = tuple(value.isoformat() if isinstance(value, datetime) else value for value in params)
        row = self.conn.execute(sql, args).fetchone()
        return dict(row) if row else None


@pytest.fixture
def setup(monkeypatch, tmp_path):
    db = FixtureDB()
    sent = []
    monkeypatch.setattr(diagnostic, "create_provider_token", lambda **kwargs: "SECRET_JWT")
    def send(**kwargs):
        sent.append(kwargs)
        # The latch must exist before transport is called.
        receipt = tmp_path / f"{TARGET.attempt_id}.jsonl"
        assert json.loads(receipt.read_text())["status"] == "reserved_do_not_retry"
        return {"ok": True, "status_code": 200}
    monkeypatch.setattr(diagnostic, "send_apns_notification", send)
    def run(**changes):
        args = dict(db=db, target=TARGET, receipt_dir=tmp_path, environ=ENV, execute=True)
        args.update(changes)
        return diagnostic.run_test(**args)
    return db, sent, run


def test_preflight_never_reads_token_signs_or_sends(setup, monkeypatch, tmp_path):
    db, sent, run = setup
    monkeypatch.setattr(diagnostic, "create_provider_token", lambda **kw: pytest.fail("preflight signed"))
    assert run(execute=False)["status"] == "preflight_ready"
    assert len(db.reads) == 1 and "device_token" not in db.reads[0]
    assert sent == [] and list(tmp_path.iterdir()) == []


def test_exact_recipient_one_call_fixed_payload_and_redacted_receipt(setup, tmp_path, capsys):
    db, sent, run = setup
    result = run()
    assert result["status"] == "accepted" and result["device_receipt"] == "unconfirmed"
    assert len(sent) == 1 and sent[0]["device_token"] == "ONLY_TARGET_SECRET"
    assert sent[0]["sandbox"] is True and sent[0]["topic"] == diagnostic.TOPIC
    assert sent[0]["timeout_seconds"] == 15
    assert sent[0]["body"] == {"aps": {"alert": {"title": "Gaia Eyes", "body": "Gaia Eyes notification test"}, "sound": "default"}}
    assert len(db.reads) == 2
    receipt = tmp_path / f"{TARGET.attempt_id}.jsonl"
    assert receipt.stat().st_mode & 0o777 == 0o600
    public = receipt.read_text() + json.dumps(result) + str(capsys.readouterr())
    assert "SECRET" not in public
    assert run()["reason"] == "attempt_already_reserved_do_not_retry"
    assert len(sent) == 1


@pytest.mark.parametrize("changes", [
    {"registration_id": UUID(int=99)}, {"user_id": UUID(int=6)},
    {"app_version": "1.0.1 (8)"}, {"environment": "prod"},
    {"updated_at": datetime(2026, 10, 14, tzinfo=timezone.utc)},
])
def test_target_mismatches_fail_closed_without_private_read(setup, changes):
    db, sent, run = setup
    assert run(target=replace(TARGET, **changes))["status"] == "blocked_no_send"
    assert sent == [] and all("device_token" not in q for q in db.reads)


@pytest.mark.parametrize("mutation", [
    "update user_push_tokens set enabled = 0 where id = ?",
    "update user_push_tokens set platform = 'android' where id = ?",
    "delete from user_push_tokens where id = ?",
    "update user_notification_preferences set enabled = 0 where user_id = ?",
    "delete from user_notification_preferences where user_id = ?",
])
def test_disabled_missing_or_wrong_platform_fail_closed(setup, mutation):
    db, sent, run = setup
    key = TARGET.user_id if "user_notification_preferences" in mutation else TARGET.registration_id
    db.conn.execute(mutation, (str(key),))
    assert run()["status"] == "blocked_no_send"
    assert sent == [] and all("device_token" not in q for q in db.reads)


@pytest.mark.parametrize("mutation", [
    "update user_push_tokens set enabled = 0 where id = ?",
    "update user_push_tokens set environment = 'prod' where id = ?",
    "update user_push_tokens set updated_at = 'changed' where id = ?",
    "update user_notification_preferences set enabled = 0 where user_id = ?",
])
def test_registration_is_revalidated_at_private_read(setup, mutation):
    db, sent, run = setup
    key = TARGET.user_id if "user_notification_preferences" in mutation else TARGET.registration_id
    db.before_private_read = lambda: db.conn.execute(mutation, (str(key),))
    assert run()["status"] == "blocked_no_send"
    assert sent == []


@pytest.mark.parametrize("config", [{}, dict(ENV, APNS_BUNDLE_ID="wrong.topic")])
def test_configuration_failures_do_not_read_or_send(setup, config):
    db, sent, run = setup
    assert run(environ=config)["status"] == "blocked_no_send"
    assert db.reads == [] and sent == []


def test_signing_exception_cannot_expose_secret(setup, monkeypatch):
    db, sent, run = setup
    def fail(**kwargs):
        raise RuntimeError("SECRET_SIGNING_EXCEPTION")
    monkeypatch.setattr(diagnostic, "create_provider_token", fail)
    result = run()
    assert result["reason"] == "provider_signing_failed" and "SECRET" not in json.dumps(result)
    assert sent == [] and all("device_token" not in q for q in db.reads)


def test_uncertain_transport_never_retries_or_exposes_exception(setup, monkeypatch, tmp_path):
    db, sent, run = setup
    calls = []
    def fail(**kwargs):
        calls.append(kwargs)
        raise RuntimeError("SECRET_TRANSPORT_EXCEPTION")
    monkeypatch.setattr(diagnostic, "send_apns_notification", fail)
    result = run()
    assert result["status"] == "uncertain_do_not_retry"
    assert run()["reason"] == "attempt_already_reserved_do_not_retry"
    assert len(calls) == 1
    assert "SECRET" not in json.dumps(result) + next(tmp_path.iterdir()).read_text()


@pytest.mark.parametrize("response, status, reason", [
    ({"ok": False, "status_code": 400, "body": {"reason": "BadDeviceToken"}}, "rejected", "BadDeviceToken"),
    ({"ok": False, "status_code": 400, "body": {"reason": "SECRET_PROVIDER_TEXT"}}, "rejected", "unrecognized_provider_reason"),
    ({"ok": False, "status_code": 0, "stderr": "SECRET_ERROR"}, "uncertain_do_not_retry", None),
])
def test_provider_outcomes_are_allowlisted_without_database_mutations(setup, monkeypatch, response, status, reason):
    db, sent, run = setup
    monkeypatch.setattr(diagnostic, "send_apns_notification", lambda **kwargs: response)
    before = list(db.conn.iterdump())
    result = run()
    assert result["status"] == status
    if reason:
        assert result["reason"] == reason
    assert "SECRET" not in json.dumps(result)
    assert list(db.conn.iterdump()) == before


def test_unavailable_or_existing_receipt_blocks_token_read(setup, tmp_path):
    db, sent, run = setup
    assert run(receipt_dir=tmp_path / "absent")["reason"] == "receipt_unavailable"
    assert sent == [] and all("device_token" not in q for q in db.reads)


def test_receipt_directory_is_durable_before_token_read(setup, monkeypatch):
    db, sent, run = setup
    synced = []
    original_fsync = os.fsync
    def fsync(fd):
        synced.append("directory" if stat.S_ISDIR(os.fstat(fd).st_mode) else "file")
        original_fsync(fd)
    monkeypatch.setattr(diagnostic.os, "fsync", fsync)
    def before_private():
        assert synced == ["file", "directory"]
    db.before_private_read = before_private
    assert run()["status"] == "accepted"
    assert synced == ["file", "directory", "file"]


def test_receipt_directory_sync_failure_blocks_token_read_and_send(setup, monkeypatch):
    db, sent, run = setup
    original_fsync = os.fsync
    def fsync(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError("SECRET_ERROR")
        original_fsync(fd)
    monkeypatch.setattr(diagnostic.os, "fsync", fsync)
    assert run()["status"] == "blocked_no_send"
    assert sent == [] and all("device_token" not in q for q in db.reads)


def test_bounded_apns_disables_curlrc_and_retries(monkeypatch):
    calls = []
    def subprocess_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return SimpleNamespace(returncode=0, stdout=b"\n200", stderr=b"")
    monkeypatch.setattr(apns.subprocess, "run", subprocess_run)
    result = apns.send_apns_notification(device_token="{SYNTHETIC_A,SYNTHETIC_B}", body={}, auth_token="SYNTHETIC",
                                          topic=diagnostic.TOPIC, sandbox=True, timeout_seconds=15)
    assert result["ok"] is True and len(calls) == 1
    cmd, options = calls[0]
    assert cmd[:7] == ["curl", "--disable", "--globoff", "--retry", "0", "--max-time", "15"]
    assert options["timeout"] == 20
    assert "https://api.sandbox.push.apple.com/3/device/{SYNTHETIC_A,SYNTHETIC_B}" in cmd


def test_existing_apns_callers_keep_default_options(monkeypatch):
    calls = []
    monkeypatch.setattr(apns.subprocess, "run", lambda cmd, **kwargs: calls.append((cmd, kwargs)) or
                        SimpleNamespace(returncode=0, stdout=b"\n200", stderr=b""))
    apns.send_apns_notification(device_token="SYNTHETIC", body={}, auth_token="SYNTHETIC", topic=diagnostic.TOPIC)
    assert "--disable" not in calls[0][0] and "timeout" not in calls[0][1]


def test_cli_requires_explicit_target_without_loading_database(capsys):
    with pytest.raises(SystemExit) as exc:
        diagnostic.main([])
    assert exc.value.code == 2
    assert "--registration-id" in capsys.readouterr().err
