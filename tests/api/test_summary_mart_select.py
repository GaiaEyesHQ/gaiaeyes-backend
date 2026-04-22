from pathlib import Path
import sys
from datetime import date
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.routers import summary


def test_summary_mart_select_uses_daily_summary_cycle_updated_at():
    assert "ds.cycle_updated_at as cycle_updated_at" in summary._MART_SELECT
    assert "df.cycle_updated_at" not in summary._MART_SELECT


def test_zero_only_body_defaults_are_not_marked_present_in_payload_summary():
    payload = summary._normalize_features_payload(
        {
            "day": "2026-04-21",
            "source": "today",
            "steps_total": 0,
            "sleep_total_minutes": 0,
            "rem_m": 0,
            "core_m": 0,
            "deep_m": 0,
            "awake_m": 0,
            "inbed_m": 0,
        },
        {"day": date(2026, 4, 21)},
        str(uuid4()),
    )

    payload_summary = summary._summarize_feature_payload(payload)

    assert payload_summary["sections"]["health"] is False
    assert payload_summary["sections"]["sleep"] is False


def test_zero_only_same_day_cached_body_is_not_richer():
    cached_payload = {
        "day": "2026-04-21",
        "updated_at": "2026-04-22T01:45:00+00:00",
        "steps_total": 0,
        "sleep_total_minutes": 0,
        "rem_m": 0,
        "core_m": 0,
        "deep_m": 0,
        "awake_m": 0,
        "inbed_m": 0,
    }
    current_payload = {
        "day": "2026-04-21",
        "updated_at": "2026-04-22T01:44:00+00:00",
    }

    assert summary._same_day_cached_body_is_richer(cached_payload, current_payload) is False


def test_merge_payload_preserving_body_skips_zero_only_donor_values():
    base_payload = {
        "day": "2026-04-21",
        "steps_total": 4321,
        "sleep_total_minutes": 410,
    }
    donor_payload = {
        "day": "2026-04-21",
        "steps_total": 0,
        "sleep_total_minutes": 0,
        "rem_m": 0,
        "core_m": 0,
    }

    merged = summary._merge_payload_preserving_body(base_payload, donor_payload)

    assert merged["steps_total"] == 4321
    assert merged["sleep_total_minutes"] == 410
    assert "rem_m" not in merged
    assert "core_m" not in merged
