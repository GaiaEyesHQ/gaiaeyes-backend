from __future__ import annotations

from datetime import date
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.routers.quakes import _merge_monthly_with_daily_rollups


def test_monthly_quakes_prefers_daily_rollup_when_monthly_row_is_zeroed():
    monthly_rows = [
        {
            "day": date(2026, 7, 1),
            "all_quakes": 0,
            "m4p": 0,
            "m5p": 0,
            "m6p": 0,
            "m7p": 0,
        },
        {
            "day": date(2026, 2, 1),
            "all_quakes": 1584,
            "m4p": 120,
            "m5p": 23,
            "m6p": 1,
            "m7p": 0,
        },
    ]
    daily_rollups = [
        {
            "month": date(2026, 7, 1),
            "all_quakes": 528,
            "m4p": 41,
            "m5p": 11,
            "m6p": 2,
            "m7p": 0,
        }
    ]

    items = _merge_monthly_with_daily_rollups(monthly_rows, daily_rollups)

    assert items[0] == {
        "month": "2026-07-01",
        "all_quakes": 528,
        "m4p": 41,
        "m5p": 11,
        "m6p": 2,
        "m7p": 0,
    }
    assert items[1]["month"] == "2026-02-01"
    assert items[1]["m5p"] == 23
