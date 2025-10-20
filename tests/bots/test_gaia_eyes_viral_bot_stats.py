import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bots.earthscope_post.gaia_eyes_viral_bot import build_stats_rows


def _value_for_label(rows, label):
    for row in rows:
        if row[0] == label:
            return row[1]
    raise AssertionError(f"Missing row for {label}")


def test_bz_negative_includes_value():
    feats = {
        "kp_max": 4.5,
        "bz_current": -7.34,
        "sw_speed_avg": 505,
        "sch_any_fundamental_avg_hz": 7.83,
    }

    rows = build_stats_rows(feats, "avg")
    assert _value_for_label(rows, "Bz (min)") == "-7.3 nT"


@pytest.mark.parametrize(
    "feats",
    [
        {"kp_max": 2.1, "sw_speed_avg": 420, "sch_any_fundamental_avg_hz": 7.6},
        {"kp_max": 2.1, "bz_min": None, "sw_speed_avg": 420, "sch_any_fundamental_avg_hz": 7.6},
    ],
)
def test_bz_missing_uses_placeholder(feats):
    rows = build_stats_rows(feats, "avg")
    assert _value_for_label(rows, "Bz (min)") == "—"
