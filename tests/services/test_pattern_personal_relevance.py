import os
import sys
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/postgres")

from services.mc_modals.modal_builder import build_earthscope_summary, build_modal_models
from app.routers.patterns import _build_explanation, _outcome_label, _signal_label
from services.patterns.personal_relevance import compute_personal_relevance, pattern_anchor_statement, _visible_pattern_row


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
        self.assertIn("pain flare", primary["personal_reason"].lower())
        self.assertEqual(primary["role_label"], "Leading now")
        daily_brief = relevance["today_relevance_explanations"]["daily_brief"]
        self.assertIn("matters more right now", daily_brief)
        self.assertEqual(daily_brief.count("for you"), 1)
        self.assertEqual(relevance["driver_summary_semantic"]["kind"], "driver_summary")
        self.assertEqual(relevance["driver_summary_semantic"]["schema_version"], "1.0")

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
        why_blob = " ".join(pain_gauge.get("why") or []) + " " + str(pain_gauge.get("causal_callout") or "")
        self.assertIn("pain flare history", why_blob.lower())
        self.assertIn("pain flare history", pressure_driver["why"][0].lower())

    def test_hrv_pattern_is_relevant_to_heart_energy_and_recovery(self) -> None:
        relevance = compute_personal_relevance(
            day=date(2026, 7, 12),
            drivers=[
                {
                    "key": "schumann",
                    "label": "Schumann",
                    "severity": "watch",
                    "state": "Watch",
                    "signal_strength": 0.72,
                    "show_driver": True,
                }
            ],
            pattern_rows=[
                {
                    "signal_key": "schumann_exposed",
                    "outcome_key": "hrv_dip_day",
                    "confidence": "Strong",
                    "lag_hours": 48,
                    "relative_lift": 2.8,
                }
            ],
            user_tags=[],
            recent_outcomes={},
        )

        gauge_keys = {item["gauge_key"] for item in relevance["pattern_relevant_gauges"]}
        self.assertTrue({"heart", "stamina", "energy", "health_status"}.issubset(gauge_keys))

    def test_high_signal_stays_visible_when_personal_relevance_is_low(self) -> None:
        relevance = compute_personal_relevance(
            day=date(2026, 3, 17),
            drivers=[
                {
                    "key": "sw",
                    "label": "Solar Wind",
                    "severity": "high",
                    "state": "High",
                    "value": 655.0,
                    "unit": "km/s",
                    "signal_strength": 0.96,
                    "force_visible": True,
                    "show_driver": True,
                },
                {
                    "key": "pressure",
                    "label": "Pressure Swing",
                    "severity": "mild",
                    "state": "Mild",
                    "value": -6.4,
                    "unit": "hPa",
                    "signal_strength": 0.60,
                    "show_driver": True,
                },
            ],
            pattern_rows=[
                {
                    "signal_key": "pressure_swing_exposed",
                    "outcome_key": "pain_flare_day",
                    "confidence": "Strong",
                    "lag_hours": 24,
                    "relative_lift": 2.3,
                }
            ],
            user_tags=[],
            recent_outcomes={},
        )

        keys = [row["key"] for row in relevance["ranked_drivers"]]
        self.assertIn("sw", keys)
        solar_wind = next(row for row in relevance["ranked_drivers"] if row["key"] == "sw")
        self.assertTrue(solar_wind["hard_visible"])
        self.assertGreaterEqual(solar_wind["display_score"], solar_wind["signal_strength"])

    def test_sensitivity_reason_uses_public_copy(self) -> None:
        relevance = compute_personal_relevance(
            day=date(2026, 3, 17),
            drivers=[
                {
                    "key": "kp",
                    "label": "Kp Index",
                    "severity": "watch",
                    "state": "Watch",
                    "value": 5.7,
                    "unit": "Kp",
                    "signal_strength": 0.72,
                    "show_driver": True,
                }
            ],
            pattern_rows=[],
            user_tags=["geomagnetic_sensitive"],
            recent_outcomes={},
        )

        primary = relevance["primary_driver"]
        self.assertIsNotNone(primary)
        assert primary is not None
        self.assertEqual(primary["role_label"], "Leading now")
        self.assertIn("what you asked Gaia Eyes to track", primary["personal_reason"])
        self.assertNotIn("sensitivity profile", primary["personal_reason"])

    def test_pattern_route_labels_release_safe_outcomes(self) -> None:
        self.assertEqual(_signal_label("ulf_exposed"), "ULF activity")
        self.assertEqual(_outcome_label("resting_hr_elevated_day"), "Resting HR elevated")
        self.assertEqual(
            _build_explanation(
                {
                    "signal_key": "ulf_exposed",
                    "outcome_key": "resting_hr_elevated_day",
                }
            ),
            "In your history, days with resting HR elevated have overlapped more when ULF activity was elevated.",
        )
        self.assertEqual(
            pattern_anchor_statement(
                {
                    "signal_key": "ulf_exposed",
                    "outcome_key": "hrv_dip_day",
                },
                variant="short",
            ),
            "ULF activity has lined up with more HRV dips for you.",
        )

    def test_allergen_driver_prefers_matching_specific_pollen_pattern(self) -> None:
        relevance = compute_personal_relevance(
            day=date(2026, 3, 17),
            drivers=[
                {
                    "key": "allergens",
                    "label": "Grass pollen",
                    "severity": "watch",
                    "state": "Watch",
                    "value": 4.1,
                    "unit": "index",
                    "signal_strength": 0.82,
                    "show_driver": True,
                }
            ],
            pattern_rows=[
                {
                    "signal_key": "pollen_grass_exposed",
                    "outcome_key": "fatigue_day",
                    "confidence": "Strong",
                    "lag_hours": 24,
                    "relative_lift": 2.2,
                },
                {
                    "signal_key": "pollen_overall_exposed",
                    "outcome_key": "headache_day",
                    "confidence": "Moderate",
                    "lag_hours": 24,
                    "relative_lift": 1.4,
                },
            ],
            user_tags=["allergies_sinus"],
            recent_outcomes={"counts": {"fatigue_day": 1}},
        )

        primary = relevance["primary_driver"]
        self.assertIsNotNone(primary)
        assert primary is not None
        self.assertEqual(primary["key"], "allergens")
        self.assertEqual(primary["active_pattern_refs"][0]["signal_key"], "pollen_grass_exposed")
        self.assertIn("grass pollen", primary["personal_reason"].lower())

    def test_humidity_driver_can_use_pattern_history(self) -> None:
        relevance = compute_personal_relevance(
            day=date(2026, 3, 17),
            drivers=[
                {
                    "key": "humidity",
                    "label": "Humidity",
                    "severity": "watch",
                    "state": "Watch",
                    "value": 78.0,
                    "unit": "%",
                    "signal_strength": 0.72,
                    "show_driver": True,
                }
            ],
            pattern_rows=[
                {
                    "signal_key": "humidity_extreme_exposed",
                    "outcome_key": "poor_sleep_day",
                    "confidence": "Moderate",
                    "lag_hours": 24,
                    "relative_lift": 1.9,
                }
            ],
            user_tags=["allergies_sinus"],
            recent_outcomes={"counts": {"poor_sleep_day": 1}},
        )

        primary = relevance["primary_driver"]
        self.assertIsNotNone(primary)
        assert primary is not None
        self.assertEqual(primary["key"], "humidity")
        self.assertEqual(primary["active_pattern_refs"][0]["signal_key"], "humidity_extreme_exposed")
        self.assertIn("humidity extremes", primary["personal_reason"].lower())

    def test_recent_pattern_row_stays_visible_as_emerging(self) -> None:
        row = _visible_pattern_row(
            {
                "signal_key": "schumann_exposed",
                "outcome_key": "anxiety_day",
                "confidence": None,
                "confidence_rank": 0,
                "last_seen_at": datetime(2026, 3, 10, tzinfo=timezone.utc),
                "relative_lift": 1.1,
                "rate_diff": 0.05,
                "lag_hours": 24,
            },
            day=date(2026, 3, 17),
        )

        self.assertIsNotNone(row)
        self.assertEqual(row["confidence"], "Emerging")
        self.assertEqual(row["confidence_rank"], 1)
        self.assertTrue(row["surfaceable"])

    def test_still_taking_shape_pattern_row_normalizes_to_emerging(self) -> None:
        row = _visible_pattern_row(
            {
                "signal_key": "humidity_extreme_exposed",
                "outcome_key": "headache_day",
                "confidence": "Still taking shape",
                "confidence_rank": 0,
                "last_seen_at": datetime(2026, 2, 1, tzinfo=timezone.utc),
                "relative_lift": 1.1,
                "rate_diff": 0.05,
                "lag_hours": 24,
            },
            day=date(2026, 3, 17),
        )

        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["confidence"], "Emerging")
        self.assertEqual(row["confidence_rank"], 1)
        self.assertTrue(row["surfaceable"])

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
                    "daily_brief": "Right now, pressure swing looks most relevant. Pressure swings are a known repeating pattern in your pain flare history. Air quality is also contributing."
                }
            },
        )

        self.assertTrue(summary.startswith("Right now, pressure swing looks most relevant."))
        self.assertIn("pain flare history", summary.lower())


if __name__ == "__main__":
    unittest.main()
