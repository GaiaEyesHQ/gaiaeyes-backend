import unittest
from datetime import date, datetime, timezone

from bots.patterns.pattern_engine_job import (
    ASSOCIATION_PAIRS,
    build_user_daily_features,
    confidence_bucket,
    percentile_nearest_rank,
    select_best_lag,
    signal_exposure,
)


class PatternEngineJobTests(unittest.TestCase):
    def test_percentile_nearest_rank_uses_deterministic_nearest_rank(self) -> None:
        self.assertEqual(percentile_nearest_rank([1, 2, 3, 4, 5], 0.80), 4)

    def test_confidence_bucket_requires_recent_strong_pattern(self) -> None:
        self.assertEqual(
            confidence_bucket(
                exposed_n=12,
                relative_lift=2.3,
                rate_diff=0.22,
                observed_weeks=3,
                last_outcome_day=date(2026, 3, 10),
                as_of_day=date(2026, 3, 17),
            ),
            "Strong",
        )
        self.assertEqual(
            confidence_bucket(
                exposed_n=12,
                relative_lift=2.3,
                rate_diff=0.22,
                observed_weeks=3,
                last_outcome_day=date(2026, 1, 1),
                as_of_day=date(2026, 3, 17),
            ),
            "Moderate",
        )

    def test_select_best_lag_prefers_confidence_then_lift_then_shorter_lag(self) -> None:
        rows = [
            {"confidence": "Emerging", "relative_lift": 2.0, "rate_diff": 0.12, "lag_hours": 24},
            {"confidence": "Moderate", "relative_lift": 1.9, "rate_diff": 0.16, "lag_hours": 48},
            {"confidence": "Moderate", "relative_lift": 1.9, "rate_diff": 0.16, "lag_hours": 12},
        ]
        best = select_best_lag(rows)
        self.assertIsNotNone(best)
        self.assertEqual(best["lag_hours"], 12)

    def test_signal_exposure_handles_explicit_thresholds_and_dynamic_schumann(self) -> None:
        pressure_row = {"pressure_delta_24h": -6.5}
        exposed, threshold = signal_exposure(pressure_row, "pressure_swing_exposed")
        self.assertTrue(exposed)
        self.assertEqual(threshold, 6.0)

        schumann_row = {"schumann_variability_proxy": 0.35, "schumann_variability_p80": 0.30}
        exposed, threshold = signal_exposure(schumann_row, "schumann_exposed")
        self.assertTrue(exposed)
        self.assertEqual(threshold, 0.30)

    def test_build_user_daily_features_preserves_zero_flare_and_cme_counts(self) -> None:
        rows = build_user_daily_features(
            base_rows=[
                {
                    "user_id": "user-1",
                    "day": date(2026, 3, 17),
                    "flares_count": 0,
                    "cmes_count": 0,
                }
            ],
            gauges={},
            gauge_deltas={},
            symptom_stats={},
            camera_rows={},
            tag_flags={},
            day_zip_map={},
            current_zip_map={},
            local_signals_daily={},
            schumann_daily={},
            updated_at=datetime(2026, 3, 17, tzinfo=timezone.utc),
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["flares_count"], 0)
        self.assertEqual(rows[0]["cmes_count"], 0)

    def test_body_signal_pairs_include_sleep_and_heart_rate_outcomes(self) -> None:
        self.assertIn(("solar_wind_exposed", "high_hr_day"), ASSOCIATION_PAIRS)
        self.assertIn(("solar_wind_exposed", "short_sleep_day"), ASSOCIATION_PAIRS)
        self.assertIn(("kp_g1_plus_exposed", "short_sleep_day"), ASSOCIATION_PAIRS)


if __name__ == "__main__":
    unittest.main()
