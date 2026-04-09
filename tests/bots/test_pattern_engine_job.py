import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch

import bots.patterns.pattern_engine_job as pattern_engine_job
from bots.patterns.pattern_engine_job import (
    ASSOCIATION_PAIRS,
    build_user_daily_features,
    build_user_daily_outcomes,
    confidence_bucket,
    _collect_relevant_zip_codes,
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

        humidity_row = {"humidity": 74.0}
        exposed, threshold = signal_exposure(humidity_row, "humidity_extreme_exposed")
        self.assertTrue(exposed)
        self.assertEqual(threshold, 35.0)

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

    def test_build_user_daily_features_carries_phase2_health_context(self) -> None:
        rows = build_user_daily_features(
            base_rows=[
                {
                    "user_id": "user-1",
                    "day": date(2026, 3, 17),
                    "respiratory_rate_avg": 15.1,
                    "resting_hr_baseline_delta": 6.2,
                    "temperature_deviation": 0.4,
                    "cycle_tracking_enabled": True,
                    "menstrual_active": True,
                    "cycle_phase": "menstrual",
                    "cycle_day": 2,
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
        self.assertEqual(rows[0]["respiratory_rate_avg"], 15.1)
        self.assertEqual(rows[0]["resting_hr_baseline_delta"], 6.2)
        self.assertEqual(rows[0]["cycle_phase"], "menstrual")
        self.assertTrue(rows[0]["cycle_tracking_enabled"])
        self.assertTrue(rows[0]["menstrual_active"])

    def test_build_user_daily_features_sets_humidity_extreme_signal(self) -> None:
        rows = build_user_daily_features(
            base_rows=[
                {
                    "user_id": "user-1",
                    "day": date(2026, 3, 17),
                }
            ],
            gauges={},
            gauge_deltas={},
            symptom_stats={},
            camera_rows={},
            tag_flags={},
            day_zip_map={("user-1", date(2026, 3, 17)): "78754"},
            current_zip_map={},
            local_signals_daily={("78754", date(2026, 3, 17)): {"humidity": 74.0}},
            schumann_daily={},
            updated_at=datetime(2026, 3, 17, tzinfo=timezone.utc),
        )

        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["humidity_extreme_exposed"])

    def test_build_user_daily_outcomes_derives_recovery_signal_flags(self) -> None:
        outcome_rows = build_user_daily_outcomes(
            [
                {
                    "user_id": "user-1",
                    "day": date(2026, 3, 17),
                    "symptom_total_events": 0,
                    "headache_symptom_events": 0,
                    "pain_symptom_events": 0,
                    "fatigue_symptom_events": 0,
                    "anxiety_symptom_events": 0,
                    "poor_sleep_symptom_events": 0,
                    "focus_fog_symptom_events": 0,
                    "respiratory_rate_baseline_delta": 2.4,
                    "resting_hr_baseline_delta": 5.5,
                    "temperature_deviation_baseline_delta": 0.35,
                }
            ],
            updated_at=datetime(2026, 3, 17, tzinfo=timezone.utc),
        )

        self.assertEqual(len(outcome_rows), 1)
        self.assertTrue(outcome_rows[0]["respiratory_rate_elevated_day"])
        self.assertTrue(outcome_rows[0]["resting_hr_elevated_day"])
        self.assertTrue(outcome_rows[0]["temperature_deviation_day"])

    def test_body_signal_pairs_include_sleep_and_heart_rate_outcomes(self) -> None:
        self.assertIn(("solar_wind_exposed", "high_hr_day"), ASSOCIATION_PAIRS)
        self.assertIn(("solar_wind_exposed", "short_sleep_day"), ASSOCIATION_PAIRS)
        self.assertIn(("kp_g1_plus_exposed", "short_sleep_day"), ASSOCIATION_PAIRS)

    def test_collect_relevant_zip_codes_dedupes_and_sorts(self) -> None:
        self.assertEqual(
            _collect_relevant_zip_codes(
                {
                    ("user-1", date(2026, 3, 29)): "60610",
                    ("user-2", date(2026, 3, 29)): "02139",
                },
                {
                    "user-1": "60610",
                    "user-3": "98109",
                },
            ),
            ["02139", "60610", "98109"],
        )

    def test_run_pattern_engine_retries_transient_ssl_eof_errors(self) -> None:
        expected = {"features": 1, "outcomes": 1, "associations": 1, "surfaced": 1}
        with (
            patch.object(pattern_engine_job, "_require_psycopg") as require_psycopg,
            patch.object(
                pattern_engine_job,
                "_run_pattern_engine_once",
                side_effect=[
                    RuntimeError("consuming input failed: SSL SYSCALL error: EOF detected"),
                    expected,
                ],
            ) as run_once,
            patch.object(pattern_engine_job.time_module, "sleep") as sleep_mock,
        ):
            result = pattern_engine_job.run_pattern_engine(
                as_of_day=date(2026, 3, 29),
                days_back=180,
                user_id=None,
                dsn="postgresql://localhost/test",
            )

        self.assertEqual(result, expected)
        require_psycopg.assert_called_once_with()
        self.assertEqual(run_once.call_count, 2)
        sleep_mock.assert_called_once_with(pattern_engine_job.DB_RETRY_BASE_SLEEP_SECONDS)

    def test_run_pattern_engine_does_not_retry_non_transient_errors(self) -> None:
        with (
            patch.object(pattern_engine_job, "_require_psycopg") as require_psycopg,
            patch.object(
                pattern_engine_job,
                "_run_pattern_engine_once",
                side_effect=ValueError("column does not exist"),
            ) as run_once,
            patch.object(pattern_engine_job.time_module, "sleep") as sleep_mock,
        ):
            with self.assertRaisesRegex(ValueError, "column does not exist"):
                pattern_engine_job.run_pattern_engine(
                    as_of_day=date(2026, 3, 29),
                    days_back=180,
                    user_id=None,
                    dsn="postgresql://localhost/test",
                )

        require_psycopg.assert_called_once_with()
        self.assertEqual(run_once.call_count, 1)
        sleep_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
