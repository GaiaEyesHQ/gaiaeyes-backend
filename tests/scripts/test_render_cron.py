from __future__ import annotations

import subprocess

from scripts import run_render_cron


def test_critical_lane_orders_gauges_after_current_inputs() -> None:
    names = [step.name for step in run_render_cron.LANES["critical"]]

    assert names[-1] == "gauges"
    assert names.index("local_current") < names.index("gauges")
    assert names.index("schumann_ingest") < names.index("gauges")
    assert names.index("space_daily_current_rollup") < names.index("gauges")


def test_lane_continues_after_failure_and_returns_nonzero(monkeypatch) -> None:
    calls: list[tuple[str, ...]] = []
    steps = (
        run_render_cron.Step("first", ("first",), 10),
        run_render_cron.Step("second", ("second",), 10),
    )

    def fake_run(command, **kwargs):  # noqa: ANN001, ARG001
        calls.append(tuple(command))
        return subprocess.CompletedProcess(command, 1 if command[0] == "first" else 0)

    monkeypatch.setattr(run_render_cron.subprocess, "run", fake_run)

    assert run_render_cron.run_lane("critical", steps=steps) == 1
    assert calls == [("first",), ("second",)]


def test_dry_run_does_not_spawn_processes(monkeypatch) -> None:
    def fail_run(*args, **kwargs):  # noqa: ANN002, ANN003, ARG001
        raise AssertionError("subprocess should not run")

    monkeypatch.setattr(run_render_cron.subprocess, "run", fail_run)
    assert run_render_cron.run_lane("events", dry_run=True) == 0


def test_normalized_database_url_removes_asyncpg_incompatible_options() -> None:
    value = (
        "postgresql://user:pass@example.com:6543/postgres"
        "?sslmode=require&hostaddr=127.0.0.1&pgbouncer=true"
    )

    assert run_render_cron._normalized_database_url(value) == (
        "postgresql://user:pass@example.com:6543/postgres?sslmode=require"
    )


def test_base_environment_aliases_supabase_url_for_shared_settings(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv(
        "SUPABASE_DB_URL",
        "postgresql://user:pass@example.com:6543/postgres"
        "?sslmode=require&hostaddr=127.0.0.1&pgbouncer=true",
    )

    env = run_render_cron._base_environment()

    expected = "postgresql://user:pass@example.com:6543/postgres?sslmode=require"
    assert env["SUPABASE_DB_URL"] == expected
    assert env["DATABASE_URL"] == expected
