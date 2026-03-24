from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
import sys
import types
import unittest
from pathlib import Path

os.environ.setdefault("SUPABASE_DB_URL", "postgresql://user:pass@localhost:5432/testdb")

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if "psycopg" not in sys.modules:
    psycopg_stub = types.ModuleType("psycopg")

    class _FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, *args, **kwargs):
            return None

        def fetchone(self):
            return None

        def fetchall(self):
            return []

    class _FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return _FakeCursor()

        def commit(self):
            return None

    def _connect(*args, **kwargs):
        return _FakeConnection()

    psycopg_stub.connect = _connect
    rows_stub = types.ModuleType("psycopg.rows")
    rows_stub.dict_row = object()
    sys.modules["psycopg"] = psycopg_stub
    sys.modules["psycopg.rows"] = rows_stub

from bots.gauges.gauge_scorer import (  # noqa: E402
    _build_symptom_signal_summary,
    apply_symptom_gauge_adjustments,
    build_health_status_explainer,
    compute_health_status,
)


def _baseline_row(seed: int) -> dict[str, float]:
    return {
        "sleep_total_minutes": 420.0 + (seed % 3) * 10.0,
        "sleep_efficiency": 89.0 - (seed % 3),
        "sleep_deep_minutes": 74.0 + (seed % 4) * 3.0,
        "spo2_avg": 98.0 - (seed % 2),
        "hr_max": 110.0 + (seed % 4) * 2.0,
        "steps_total": 6200.0 + seed * 75.0,
        "bp_sys_avg": 118.0 + (seed % 2),
        "bp_dia_avg": 76.0 + (seed % 3),
        "hrv_avg": 41.0 + (seed % 4),
    }


class GaugeScorerTests(unittest.TestCase):
    def test_apply_symptom_gauge_adjustments_raises_pain_for_severe_headache(self) -> None:
        gauges = {
            "pain": 25.0,
            "focus": 25.0,
            "heart": 25.0,
            "stamina": 25.0,
            "energy": 25.0,
            "sleep": 25.0,
            "mood": 25.0,
        }
        symptoms = {
            "top_symptoms": [
                {"symptom_code": "HEADACHE", "events": 1, "max_severity": 9},
            ]
        }

        adjusted, meta = apply_symptom_gauge_adjustments(gauges, symptoms)

        self.assertGreater(adjusted["pain"], 40.0)
        self.assertGreater(adjusted["focus"], 30.0)
        self.assertGreater(meta["adjustments"]["pain"], 10.0)

    def test_compute_health_status_includes_recovery_penalties(self) -> None:
        baseline_rows = [_baseline_row(idx) for idx in range(14)]
        today_row = {
            **_baseline_row(0),
            "sleep_debt_proxy": 120.0,
            "sleep_vs_14d_baseline_delta": -90.0,
            "resting_hr_baseline_delta": 6.0,
            "respiratory_rate_baseline_delta": 2.2,
            "temperature_deviation_baseline_delta": 0.45,
            "bedtime_consistency_score": 55.0,
            "waketime_consistency_score": 60.0,
        }

        health_status, meta = compute_health_status(
            today_row,
            baseline_rows,
            {"total_24h": 0, "max_severity": None, "top_symptoms": []},
        )

        self.assertIsNotNone(health_status)
        self.assertGreater(health_status or 0.0, 10.0)
        self.assertGreater(meta["recovery_penalty_total"], 10.0)
        self.assertIn("sleep_debt_proxy", meta["recovery_penalties"])
        self.assertIn("resting_hr_baseline_delta", meta["recovery_penalties"])

    def test_compute_health_status_can_use_recovery_penalties_without_metric_zscores(self) -> None:
        baseline_rows = [
            {
                "sleep_total_minutes": 420.0,
                "sleep_efficiency": 90.0,
                "sleep_deep_minutes": 75.0,
                "spo2_avg": 98.0,
                "hr_max": 110.0,
                "steps_total": 6500.0,
                "bp_sys_avg": 118.0,
                "bp_dia_avg": 76.0,
                "hrv_avg": 42.0,
            }
            for _ in range(14)
        ]
        today_row = {
            **baseline_rows[0],
            "sleep_debt_proxy": 95.0,
            "resting_hr_baseline_delta": 5.5,
            "respiratory_rate_baseline_delta": 2.0,
        }

        health_status, meta = compute_health_status(
            today_row,
            baseline_rows,
            {"total_24h": 0, "max_severity": None, "top_symptoms": []},
        )

        self.assertIsNotNone(health_status)
        self.assertEqual(meta["metrics_used"], [])
        self.assertGreater(meta["recovery_penalty_total"], 0.0)

    def test_build_health_status_explainer_surfaces_recovery_and_cycle_context(self) -> None:
        today_row = {
            "cycle_tracking_enabled": True,
            "cycle_phase": "luteal",
            "cycle_day": 22,
            "menstrual_active": False,
        }
        symptoms = {
            "max_severity": 9,
            "top_symptoms": [
                {"symptom_code": "HEADACHE", "events": 1, "max_severity": 9},
            ],
        }
        health_meta = {
            "calibrating": False,
            "baseline_days": 21,
            "recovery_penalties": {
                "sleep_debt_proxy": {
                    "label": "Sleep debt",
                    "value": 120.0,
                    "points": 8.5,
                },
                "resting_hr_baseline_delta": {
                    "label": "Resting HR above usual",
                    "value": 6.0,
                    "points": 6.0,
                },
            },
            "stress_penalty": 0.0,
        }

        payload = build_health_status_explainer(today_row, symptoms, 42.0, health_meta)

        self.assertEqual(payload["health_status"], 42.0)
        self.assertFalse(payload["calibrating"])
        self.assertEqual(payload["baseline_days"], 21)
        self.assertIn("sleep debt", payload["summary"].lower())
        self.assertEqual(payload["drivers"][0]["label"], "Symptoms logged")
        self.assertEqual(payload["drivers"][1]["label"], "Sleep debt")
        self.assertEqual(payload["context"][0]["label"], "Cycle context")
        self.assertIn("luteal", payload["context"][0]["display"])

    def test_symptom_signal_summary_uses_severity_tiers_and_recency_decay(self) -> None:
        now = datetime.now(timezone.utc)
        summary = _build_symptom_signal_summary(
            [
                {"symptom_code": "HEADACHE", "severity": 9, "ts_utc": now - timedelta(hours=1)},
                {"symptom_code": "FATIGUE", "severity": 6, "ts_utc": now - timedelta(hours=10)},
            ]
        )

        self.assertEqual(summary["gauge_boosts"]["pain"], 18.0)
        self.assertAlmostEqual(summary["gauge_boosts"]["energy"], 3.6, places=2)
        self.assertEqual(summary["recent_gauge_boosts"]["pain"], 18.0)
        self.assertNotIn("energy", summary["recent_gauge_boosts"])
        self.assertIn("pain", summary["recent_matching_gauges"])
        self.assertGreater(summary["health_status_symptom_boost"], 12.0)

    def test_symptom_signal_summary_respects_current_state_multipliers(self) -> None:
        now = datetime.now(timezone.utc)
        summary = _build_symptom_signal_summary(
            [
                {"symptom_code": "HEADACHE", "severity": 8, "last_interaction_at": now - timedelta(hours=1), "current_state": "ongoing"},
                {"symptom_code": "FATIGUE", "severity": 8, "last_interaction_at": now - timedelta(hours=1), "current_state": "improving"},
                {"symptom_code": "PAIN", "severity": 9, "last_interaction_at": now - timedelta(hours=1), "current_state": "resolved"},
            ]
        )

        self.assertIn("pain", summary["gauge_boosts"])
        self.assertIn("energy", summary["gauge_boosts"])
        self.assertLess(summary["gauge_boosts"]["energy"], 18.0)
        self.assertGreater(summary["gauge_boosts"].get("stamina", 0.0), 0.0)
        self.assertLess(summary["gauge_boosts"]["stamina"], 9.8)


if __name__ == "__main__":
    unittest.main()
