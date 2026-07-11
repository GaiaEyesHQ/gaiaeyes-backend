#!/usr/bin/env python3
"""Run Gaia Eyes Render cron lanes in a bounded, sequential order.

Render guarantees a single active run per cron service. Keeping each lane
sequential prevents the quarter-hour ingestion burst that previously stressed
the database while still allowing independent steps to finish when one source
is temporarily unavailable.
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
LOG = logging.getLogger("gaiaeyes.render_cron")
_ASYNC_DRIVER_UNSUPPORTED_DSN_PARAMS = {"hostaddr", "pgbouncer"}


@dataclass(frozen=True)
class Step:
    name: str
    command: tuple[str, ...]
    timeout_seconds: int
    env: dict[str, str] = field(default_factory=dict)


def _python(*parts: str) -> tuple[str, ...]:
    return (PYTHON, *parts)


LANES: dict[str, tuple[Step, ...]] = {
    "critical": (
        Step(
            "space_current",
            _python("scripts/ingest_space_weather_swpc.py"),
            240,
            {"SINCE_HOURS": "24", "MAX_SOURCE_AGE_MINUTES": "90"},
        ),
        Step(
            "space_live_context",
            _python(
                "scripts/ingest_space_forecasts_step1.py",
                "--days",
                "1",
                "--only",
                "sep",
                "xray",
                "aurora",
                "drap",
                "alerts",
            ),
            360,
        ),
        Step("ulf", _python("bots/geomag_ulf/ingest_ulf.py"), 300),
        Step(
            "schumann_extract",
            _python(
                "bots/schumann/schumann_multi.py",
                "--prefer",
                "cumiana,tomsk",
                "--out",
                "/tmp/gaiaeyes-schumann/schumann_now.json",
                "--overlay",
                "/tmp/gaiaeyes-schumann/schumann_overlay.png",
                "--insecure",
            ),
            360,
        ),
        Step(
            "schumann_ingest",
            _python("scripts/ingest_schumann_github.py"),
            180,
            {"SCHUMANN_JSON_PATH": "/tmp/gaiaeyes-schumann/schumann_now.json"},
        ),
        Step(
            "local_current",
            _python("-m", "bots.local_health_poll", "--mode", "current"),
            600,
        ),
        Step(
            "space_daily_current_rollup",
            _python("scripts/rollup_space_weather_daily.py"),
            240,
            {"DAYS_BACK": "3"},
        ),
        Step("gauges", _python("bots/gauges/gauge_scoring_job.py"), 900),
    ),
    "events": (
        Step(
            "earthquakes",
            _python("scripts/ingest_usgs_quakes.py"),
            360,
            {"OUTPUT_JSON_PATH": "/tmp/gaiaeyes-events/quakes_latest.json"},
        ),
        Step(
            "global_hazards",
            _python("-m", "bots.hazards.hazards_bot"),
            420,
            {"HAZARDS_SKIP_WP": "1"},
        ),
        Step(
            "nasa_donki",
            _python("scripts/ingest_nasa_donki.py"),
            600,
            {
                "START_DAYS_AGO": "3",
                "DONKI_DAY_MODE": "0",
                "OUTPUT_JSON_PATH": "/tmp/gaiaeyes-events/flares_cmes.json",
            },
        ),
    ),
    "daily": (
        Step(
            "local_forecast",
            _python("-m", "bots.local_health_poll", "--mode", "forecast"),
            1200,
        ),
        Step(
            "space_forecasts",
            _python(
                "scripts/ingest_space_forecasts_step1.py",
                "--days",
                "3",
                "--only",
                "enlil",
                "radiation",
                "aurora",
                "coronal",
                "scoreboard",
                "solar",
                "bulletins",
            ),
            1200,
        ),
        Step(
            "health_reconciliation",
            _python("scripts/rollup_health_daily.py"),
            1200,
            {"DAYS_BACK": "3"},
        ),
        Step(
            "daily_features",
            _python("scripts/rollup_daily_features.py"),
            1200,
            {"DAYS_BACK": "3"},
        ),
        Step("location_context", _python("bots/gauges/location_context_job.py"), 300),
        Step("gauges", _python("bots/gauges/gauge_scoring_job.py"), 900),
        Step(
            "patterns",
            _python("bots/patterns/pattern_engine_job.py", "--days-back", "180"),
            1800,
        ),
    ),
}


def _prepare_runtime_paths(lane: str) -> None:
    if lane == "critical":
        target = Path("/tmp/gaiaeyes-schumann")
        target.mkdir(parents=True, exist_ok=True)
        for name in ("schumann_now.json", "schumann_overlay.png"):
            (target / name).unlink(missing_ok=True)
    elif lane == "events":
        Path("/tmp/gaiaeyes-events").mkdir(parents=True, exist_ok=True)


def _normalized_database_url(value: str) -> str:
    """Remove libpq-only URL options that asyncpg sends as server settings."""
    if not value or "://" not in value:
        return value
    parsed = urlsplit(value)
    query = [
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in _ASYNC_DRIVER_UNSUPPORTED_DSN_PARAMS
    ]
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))


def _base_environment() -> dict[str, str]:
    env = os.environ.copy()
    root_text = str(ROOT)
    existing_pythonpath = env.get("PYTHONPATH", "").strip()
    env["PYTHONPATH"] = (
        f"{root_text}{os.pathsep}{existing_pythonpath}" if existing_pythonpath else root_text
    )
    for key in ("SUPABASE_DB_URL", "DATABASE_URL", "DIRECT_URL"):
        if env.get(key):
            env[key] = _normalized_database_url(env[key])
    return env


def run_lane(
    lane: str,
    *,
    dry_run: bool = False,
    steps: Iterable[Step] | None = None,
) -> int:
    selected = tuple(steps if steps is not None else LANES[lane])
    _prepare_runtime_paths(lane)
    failures: list[str] = []
    lane_started = time.monotonic()

    for step in selected:
        rendered = " ".join(step.command)
        if dry_run:
            LOG.info("[cron] plan lane=%s step=%s command=%s", lane, step.name, rendered)
            continue

        env = _base_environment()
        env.update(step.env)
        started = time.monotonic()
        LOG.info("[cron] start lane=%s step=%s command=%s", lane, step.name, rendered)
        try:
            completed = subprocess.run(
                step.command,
                cwd=ROOT,
                env=env,
                check=False,
                timeout=step.timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            failures.append(f"{step.name}:timeout")
            LOG.error(
                "[cron] timeout lane=%s step=%s seconds=%s",
                lane,
                step.name,
                step.timeout_seconds,
            )
            continue

        elapsed = time.monotonic() - started
        if completed.returncode != 0:
            failures.append(f"{step.name}:exit_{completed.returncode}")
            LOG.error(
                "[cron] failed lane=%s step=%s exit=%s seconds=%.1f",
                lane,
                step.name,
                completed.returncode,
                elapsed,
            )
        else:
            LOG.info("[cron] done lane=%s step=%s seconds=%.1f", lane, step.name, elapsed)

    elapsed = time.monotonic() - lane_started
    if failures:
        LOG.error("[cron] lane=%s failed=%s seconds=%.1f", lane, ",".join(failures), elapsed)
        return 1
    LOG.info("[cron] lane=%s ok steps=%s seconds=%.1f", lane, len(selected), elapsed)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a Gaia Eyes Render cron lane.")
    parser.add_argument("lane", choices=sorted(LANES))
    parser.add_argument("--dry-run", action="store_true", help="Print the ordered plan without running it.")
    args = parser.parse_args()

    logging.basicConfig(
        level=os.getenv("GAIA_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    raise SystemExit(run_lane(args.lane, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
