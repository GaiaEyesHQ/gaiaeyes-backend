from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.routers.space import _cme_arrival_stats, space_history


class _FakeCursor:
    def __init__(self, fetchall_batches: list[list[dict[str, Any]]]):
        self._fetchall_batches = list(fetchall_batches)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):  # noqa: ARG002
        return False

    async def execute(self, *args, **kwargs):  # noqa: ARG002
        return None

    async def fetchall(self):
        return self._fetchall_batches.pop(0)


class _FakeConn:
    def __init__(self, fetchall_batches: list[list[dict[str, Any]]]):
        self._fetchall_batches = fetchall_batches

    def cursor(self, *args, **kwargs):  # noqa: ARG002
        return _FakeCursor(self._fetchall_batches)


@pytest.mark.anyio
async def test_space_history_fills_sw_and_bz_from_magnetosphere_pulse():
    ts = datetime(2026, 7, 2, 3, 30, tzinfo=timezone.utc)
    conn = _FakeConn(
        [
            [{"ts_utc": ts, "kp_index": 2.0, "bz_nt": None, "sw_speed_kms": None}],
            [{"ts": ts, "kp_latest": 2.0, "bz_nt": -6.2, "v_kms": 485.5}],
        ]
    )

    body = await space_history(conn=conn, hours=24)

    assert body["ok"] is True
    assert body["data"]["series24"]["kp"] == [["2026-07-02T03:30:00+00:00", 2.0]]
    assert body["data"]["series24"]["sw"] == [["2026-07-02T03:30:00+00:00", 485.5]]
    assert body["data"]["series24"]["bz"] == [["2026-07-02T03:30:00+00:00", -6.2]]


def test_cme_arrival_stats_counts_unique_simulations_not_targets():
    ts = datetime(2026, 7, 2, 3, 30, tzinfo=timezone.utc)
    rows = [
        {"arrival_time": ts, "simulation_id": "sim-1", "location": "Mars", "cme_speed_kms": 500},
        {"arrival_time": ts, "simulation_id": "sim-1", "location": "Psyche", "cme_speed_kms": 650},
        {"arrival_time": ts, "simulation_id": "sim-2", "location": "Earth", "cme_speed_kms": 600},
    ]

    assert _cme_arrival_stats(rows) == {
        "total_72h": 2,
        "earth_directed_count": 1,
        "max_speed_kms": 650.0,
    }
