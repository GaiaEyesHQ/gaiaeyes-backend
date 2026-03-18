import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.mc_modals.modal_builder import build_earthscope_summary, build_modal_models
from services.patterns.personal_relevance import compute_personal_relevance


class PatternPersonalRelevanceTests(unittest.TestCase):
    def test_pattern_relevance_can_outrank_raw_severity(self) -> None:
        relevance = compute_personal_relevance(
            day=date(2026, 3, 17),
            drivers=[
                {
                    "key": "aqi",
                    "label": "Air Quality",
                    "severity": "watch",
                    "state": "Watch",
                    "value": 108.0,
                    "unit": "AQI",
                },
                {
                    "key": "pressure",
                    "label": "Pressure Swing",
                    "severity": "mild",
                    "state": "Mild",
                    "value": -6.8,
                    "unit": "hPa",
                },
            ],
            pattern_rows=[
                {
                    "signal_key": "pressure_swing_exposed",
                    "outcome_key": "pain_flare_day",
                    "confidence": "Strong",
                    "lag_hours": 24,
                    "relative_lift": 2.7,
                }
            ],
            user_tags=["migraine_history", "pressure_sensitive", "fibromyalgia"],
            recent_outcomes={"counts": {"pain_flare_day": 2}},
        )

        primary = relevance["primary_driver"]
        self.assertIsNotNone(primary)
        self.assertEqual(primary["key"], "pressure")
        self.assertIn("pain flare history", primary["personal_reason"].lower())
        self.assertEqual(primary["role_label"], "Leading now")
        self.assertIn("matters more for you right now", relevance["today_relevance_explanations"]["daily_brief"])

    def test_modal_builder_uses_pattern_summary_when_present(self) -> None:
        payload = build_modal_models(
            day=date(2026, 3, 17),
            gauges={"pain": 78},
            gauges_meta={"pain": {"zone": "elevated", "label": "Active"}},
            gauge_labels={"pain": "Pain"},
            drivers=[
                {
                    "key": "pressure",
                    "label": "Pressure Swing",
                    "severity": "mild",
                    "state": "Mild",
                    "value": -6.8,
                    "unit": "hPa",
                    "personal_reason": "Pressure swings are a known repeating pattern in your pain flare history.",
                    "active_pattern_refs": [
                        {
                            "id": "pressure_swing_exposed|pain_flare_day|24",
                            "outcome_key": "pain_flare_day",
                        }
                    ],
                    "role": "primary",
                }
            ],
            personal_relevance={
                "pattern_relevant_gauges": [
                    {
                        "gauge_key": "pain",
                        "summary": "Pressure swings are a known repeating pattern in your pain flare history.",
                    }
                ]
            },
        )

        pain_gauge = payload["gauges"]["pain"]
        pressure_driver = payload["drivers"]["pressure"]
        self.assertIn("pain flare history", pain_gauge["why"][0].lower())
        self.assertIn("pain flare history", pressure_driver["why"][0].lower())

    def test_earthscope_summary_leads_with_personal_daily_brief(self) -> None:
        summary = build_earthscope_summary(
            user_id="user-123",
            day=date(2026, 3, 17),
            gauges={"pain": 84, "sleep": 66},
            gauges_meta={
                "pain": {"zone": "high", "label": "Flare"},
                "sleep": {"zone": "elevated", "label": "Disrupted"},
            },
            gauge_labels={"pain": "Pain", "sleep": "Sleep"},
            drivers=[
                {
                    "key": "pressure",
                    "label": "Pressure Swing",
                    "severity": "mild",
                    "state": "Mild",
                },
                {
                    "key": "aqi",
                    "label": "Air Quality",
                    "severity": "watch",
                    "state": "Watch",
                },
            ],
            user_tags=["fibromyalgia"],
            personal_relevance={
                "today_relevance_explanations": {
                    "daily_brief": "Right now, pressure swing looks most relevant for you. Pressure swings are a known repeating pattern in your pain flare history. Air quality is also in the mix."
                }
            },
        )

        self.assertTrue(summary.startswith("Right now, pressure swing looks most relevant for you."))
        self.assertIn("pain flare history", summary.lower())


if __name__ == "__main__":
    unittest.main()
