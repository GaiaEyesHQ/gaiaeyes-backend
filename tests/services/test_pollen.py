from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.external import pollen  # noqa: E402


class PollenNormalizationTests(unittest.TestCase):
    def test_normalize_daily_forecast_computes_overall_and_primary_type(self) -> None:
        payload = {
            "dailyInfo": [
                {
                    "date": {"year": 2026, "month": 3, "day": 19},
                    "pollenTypeInfo": [
                        {"code": "TREE", "displayName": "Tree", "indexInfo": {"value": 4, "category": "HIGH"}},
                        {"code": "GRASS", "displayName": "Grass", "indexInfo": {"value": 2, "category": "LOW"}},
                        {"code": "WEED", "displayName": "Weed", "indexInfo": {"value": 3, "category": "MODERATE"}},
                    ],
                }
            ]
        }

        rows = pollen.normalize_daily_forecast(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["day"], date(2026, 3, 19))
        self.assertEqual(rows[0]["pollen_overall_level"], "high")
        self.assertEqual(rows[0]["pollen_primary_type"], "tree")
        self.assertEqual(rows[0]["pollen_tree_level"], "high")
        self.assertEqual(rows[0]["pollen_weed_level"], "moderate")

    def test_current_snapshot_returns_user_facing_labels(self) -> None:
        payload = {
            "dailyInfo": [
                {
                    "date": {"year": 2026, "month": 3, "day": 19},
                    "pollenTypeInfo": [
                        {"code": "GRASS", "displayName": "Grass", "indexInfo": {"value": 5, "category": "VERY_HIGH"}},
                    ],
                }
            ]
        }

        snapshot = pollen.current_snapshot(payload)

        self.assertEqual(snapshot["overall_level"], "very_high")
        self.assertEqual(snapshot["overall_label"], "High")
        self.assertEqual(snapshot["primary_type"], "grass")
        self.assertEqual(snapshot["primary_label"], "Grass pollen")


if __name__ == "__main__":
    unittest.main()
