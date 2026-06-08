from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bots.social_alerts.shadow_drafts import build_shadow_payload
from bots.social_alerts.snapshot_sources import _clean_db_url, build_existing_signal_snapshot, write_snapshot


def test_build_existing_signal_snapshot_normalizes_db_rows() -> None:
    schumann_rows = []
    for index in range(16):
        schumann_rows.append(
            {
                "day": date(2026, 4, index + 1),
                "value_hz": 7.83 + (index * 0.01),
                "f1_hz": 7.83 + (index * 0.01),
                "station_id": "cumiana",
            }
        )
    schumann_rows[-1]["value_hz"] = 8.25
    schumann_rows[-1]["f1_hz"] = 8.25

    snapshot = build_existing_signal_snapshot(
        space_daily={
            "day": date(2026, 4, 16),
            "kp_now": 3.1,
            "kp_max": 5.4,
            "bz_now": -4.1,
            "bz_min": -7.2,
            "sw_speed_now_kms": 500,
            "sw_speed_avg": 520,
            "xray_max_class": "M5.2",
            "updated_at": datetime(2026, 4, 16, 12, 0, tzinfo=timezone.utc),
        },
        latest_space={
            "ts_utc": datetime(2026, 4, 16, 12, 10, tzinfo=timezone.utc),
            "kp_index": 3.6,
            "bz_nt": -5.5,
            "sw_speed_kms": 560,
        },
        schumann_rows=schumann_rows,
        quakes=[{"time_utc": datetime(2026, 4, 16, 10, 0, tzinfo=timezone.utc), "mag": 6.2, "place": "Test Ridge"}],
        hazards=[{"kind": "storm", "severity": "orange", "title": "Storm alert"}],
        generated_at="2026-04-16T12:15:00Z",
    )

    assert snapshot["source_mode"] == "db_snapshot"
    assert snapshot["space_weather"]["now"]["kp"] == 3.6
    assert snapshot["space_weather"]["last_24h"]["kp_max"] == 5.4
    assert snapshot["space_weather"]["xray_max_class"] == "M5.2"
    assert snapshot["schumann"]["sample_count"] >= 14
    assert snapshot["active_states"][0]["signal_key"] == "schumann.variability_24h"
    assert snapshot["quakes"]["events"][0]["time_utc"] == "2026-04-16T10:00:00Z"

    payload = build_shadow_payload(snapshot)
    categories = {draft["category"] for draft in payload["drafts"]}
    assert {"geomagnetic", "solar_flare", "schumann"} <= categories
    assert "earthquake" not in categories
    assert "global_hazard" not in categories
    assert "air_quality" not in categories
    assert "pollen" not in categories


def test_write_snapshot_writes_json(tmp_path: Path) -> None:
    snapshot = build_existing_signal_snapshot(
        space_daily={"kp_max": 3.5, "updated_at": "2026-04-16T12:00:00Z"},
        generated_at="2026-04-16T12:15:00Z",
    )
    out_path = write_snapshot(snapshot, tmp_path / "snapshot.json")

    assert out_path.exists()
    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert written["source_mode"] == "db_snapshot"
    assert written["space_weather"]["now"]["kp"] == 3.5


def test_clean_db_url_removes_psycopg_incompatible_query_params() -> None:
    cleaned = _clean_db_url("postgresql://user:pass@example.com/db?pgbouncer=true&prepare_threshold=0&foo=bar")

    assert "pgbouncer" not in cleaned
    assert "prepare_threshold" not in cleaned
    assert "foo=bar" in cleaned
    assert "sslmode=require" in cleaned
