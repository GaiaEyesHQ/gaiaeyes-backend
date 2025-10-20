import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bots.earthscope_post.gaia_eyes_viral_bot import build_stats_rows, StatRow


def _row_for_label(rows: list[StatRow], label: str) -> StatRow:
    for row in rows:
        if row.label == label:
            return row
    raise AssertionError(f"Missing row for {label}")


def test_bz_prefers_min_and_applies_severe_styling():
    feats = {
        "kp_max": 4.5,
        "bz_min": -8.0,
        "bz_current": -2.0,
        "sw_speed_avg": 505,
        "sch_any_fundamental_avg_hz": 7.83,
    }

    rows = build_stats_rows(feats, "avg")
    bz_row = _row_for_label(rows, "Bz (min)")

    assert bz_row.display == "-8.0 nT"
    assert bz_row.raw_value == pytest.approx(-8.0)
    assert bz_row.color == (239, 106, 106, 220)


def test_bz_falls_back_to_current_with_label():
    feats = {
        "kp_max": 3.2,
        "bz_min": None,
        "bz_current": -3.4,
        "sw_speed_avg": 455,
        "sch_any_fundamental_avg_hz": 7.7,
    }

    rows = build_stats_rows(feats, "avg")
    bz_row = _row_for_label(rows, "Bz (current)")

    assert bz_row.display == "-3.4 nT"
    assert bz_row.raw_value == pytest.approx(-3.4)
    assert bz_row.color == (100, 160, 220, 220)


@pytest.mark.parametrize(
    "feats",
    [
        {"kp_max": 2.1, "sw_speed_avg": 420, "sch_any_fundamental_avg_hz": 7.6},
        {
            "kp_max": 2.1,
            "bz_min": None,
            "bz_current": None,
            "bz_now": None,
            "sw_speed_avg": 420,
            "sch_any_fundamental_avg_hz": 7.6,
        },
    ],
)
def test_bz_missing_uses_placeholder(feats):
    rows = build_stats_rows(feats, "avg")
    bz_row = _row_for_label(rows, "Bz (current)")
    assert bz_row.display == "—"
    assert bz_row.raw_value is None
