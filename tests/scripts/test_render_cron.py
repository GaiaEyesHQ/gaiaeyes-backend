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


def test_migraine_worker_flag_is_runtime_managed() -> None:
    from pathlib import Path
    import yaml

    blueprint = yaml.safe_load(Path("render-crons.yaml").read_text())
    worker = next(service for service in blueprint["services"]
                  if service["name"] == "gaiaeyes-migraine-time-refresh")
    assert worker["type"] == "cron"
    assert worker["plan"] == "starter"
    assert worker["schedule"] == "*/5 * * * *"
    assert worker["startCommand"] == "python scripts/run_render_cron.py migraine_refresh"
    flag = next(item for item in worker["envVars"]
                if item.get("key") == "GAIA_MIGRAINE_TIME_REFRESH_WORKER_ENABLED")
    assert flag == {"key": "GAIA_MIGRAINE_TIME_REFRESH_WORKER_ENABLED", "sync": False}


def test_migraine_worker_defaults_off(monkeypatch, capsys) -> None:
    import ast
    from pathlib import Path

    # Execute the real CLI main without importing database clients or credentials.
    source = ast.parse(Path("scripts/run_migraine_time_refresh.py").read_text())
    main = next(node for node in source.body if isinstance(node, ast.FunctionDef) and node.name == "main")
    import argparse
    import json
    import os
    import sys
    import time

    def unexpected_work(*args, **kwargs):
        raise AssertionError("disabled worker must not access the queue")

    namespace = dict(argparse=argparse, json=json, os=os, time=time,
                     claim=unexpected_work, process=unexpected_work, health=unexpected_work)
    exec(compile(ast.Module(body=[main], type_ignores=[]), "worker-main", "exec"), namespace)
    monkeypatch.setattr(sys, "argv", ["worker"])
    for value in (None, "0", "false", ""):
        if value is None:
            monkeypatch.delenv("GAIA_MIGRAINE_TIME_REFRESH_WORKER_ENABLED", raising=False)
        else:
            monkeypatch.setenv("GAIA_MIGRAINE_TIME_REFRESH_WORKER_ENABLED", value)
        namespace["main"]()
        assert json.loads(capsys.readouterr().out) == {"status": "disabled"}
