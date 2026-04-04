import sys
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from services import signal_bar
    _IMPORT_ERROR = None
except ModuleNotFoundError as exc:  # pragma: no cover - optional DB deps are absent in some local envs.
    signal_bar = None
    _IMPORT_ERROR = exc


@unittest.skipIf(_IMPORT_ERROR is not None, f"Signal bar tests require optional dependencies: {_IMPORT_ERROR}")
class SignalBarTests(unittest.TestCase):
    def test_build_signal_bar_maps_live_states_to_core_pills(self) -> None:
        local_payload = {
            "asof": "2026-03-26T12:00:00Z",
            "weather": {
                "pressure_hpa": 1009.4,
                "baro_delta_12h_hpa": -7.2,
                "baro_trend": "falling",
            },
        }
        active_states = [
            {
                "signal_key": "earthweather.pressure_swing_12h",
                "state": "moderate",
                "value": -7.2,
            },
            {
                "signal_key": "schumann.variability_24h",
                "state": "elevated",
                "evidence": {"ts": "2026-03-26T11:50:00Z"},
            },
        ]

        with patch.object(
            signal_bar.signal_resolver,
            "_fetch_space_snapshot",
            return_value={
                "kp_now": 6.2,
                "sw_speed_now_kms": 689.0,
                "updated_at": datetime(2026, 3, 26, 11, 55, tzinfo=timezone.utc),
            },
        ), patch.object(signal_bar, "_fetch_schumann_snapshot", return_value=None):
            payload = signal_bar.build_signal_bar(
                day=date(2026, 3, 26),
                active_states=active_states,
                local_payload=local_payload,
            )

        items = {item["key"]: item for item in payload["items"]}
        self.assertEqual(items["kp"]["state"], "strong")
        self.assertEqual(items["kp"]["value"], "6.2")
        self.assertEqual(items["solar_wind"]["state"], "elevated")
        self.assertEqual(items["solar_wind"]["value"], "689 km/s")
        self.assertEqual(items["schumann"]["state"], "elevated")
        self.assertEqual(items["schumann"]["value"], "Elevated")
        self.assertEqual(items["pressure"]["state"], "watch")
        self.assertEqual(items["pressure"]["value"], "1009 ↓")
        self.assertEqual(items["pressure"]["detail_target"], "local_conditions")

    def test_build_signal_bar_keeps_quiet_defaults_when_no_trigger_is_active(self) -> None:
        local_payload = {
            "asof": "2026-03-26T12:00:00Z",
            "weather": {
                "pressure_hpa": 1016.2,
                "baro_delta_24h_hpa": 1.1,
                "pressure_trend": "steady",
            },
        }

        with patch.object(
            signal_bar.signal_resolver,
            "_fetch_space_snapshot",
            return_value={
                "kp_now": 2.7,
                "sw_speed_now_kms": 420.0,
                "updated_at": datetime(2026, 3, 26, 12, 2, tzinfo=timezone.utc),
            },
        ), patch.object(signal_bar, "_fetch_schumann_snapshot", return_value=None):
            payload = signal_bar.build_signal_bar(
                day=date(2026, 3, 26),
                active_states=[],
                local_payload=local_payload,
            )

        items = {item["key"]: item for item in payload["items"]}
        self.assertEqual(items["kp"]["state"], "quiet")
        self.assertEqual(items["solar_wind"]["state"], "quiet")
        self.assertEqual(items["schumann"]["state"], "quiet")
        self.assertEqual(items["schumann"]["value"], "Quiet")
        self.assertEqual(items["pressure"]["state"], "quiet")
        self.assertEqual(items["pressure"]["value"], "1016 →")

    def test_build_signal_bar_uses_live_schumann_snapshot_for_watch_label(self) -> None:
        with patch.object(
            signal_bar.signal_resolver,
            "_fetch_space_snapshot",
            return_value={
                "kp_now": 2.1,
                "sw_speed_now_kms": 430.0,
                "updated_at": datetime(2026, 3, 26, 12, 2, tzinfo=timezone.utc),
            },
        ), patch.object(
            signal_bar,
            "_fetch_schumann_snapshot",
            return_value={
                "label": "Active",
                "state": "watch",
                "updated_at": "2026-03-26T12:04:00Z",
            },
        ):
            payload = signal_bar.build_signal_bar(
                day=date(2026, 3, 26),
                active_states=[],
                local_payload={},
            )

        items = {item["key"]: item for item in payload["items"]}
        self.assertEqual(items["schumann"]["state"], "watch")
        self.assertEqual(items["schumann"]["value"], "Active")
        self.assertEqual(items["schumann"]["updated_at"], "2026-03-26T12:04:00Z")

    def test_build_signal_bar_keeps_stronger_schumann_trigger_when_live_snapshot_is_quiet(self) -> None:
        with patch.object(
            signal_bar.signal_resolver,
            "_fetch_space_snapshot",
            return_value={
                "kp_now": 2.1,
                "sw_speed_now_kms": 430.0,
                "updated_at": datetime(2026, 3, 26, 12, 2, tzinfo=timezone.utc),
            },
        ), patch.object(
            signal_bar,
            "_fetch_schumann_snapshot",
            return_value={
                "label": "Calm",
                "state": "quiet",
                "updated_at": "2026-03-26T12:04:00Z",
            },
        ):
            payload = signal_bar.build_signal_bar(
                day=date(2026, 3, 26),
                active_states=[
                    {
                        "signal_key": "schumann.variability_24h",
                        "state": "elevated",
                        "evidence": {"ts": "2026-03-26T12:01:00Z"},
                    }
                ],
                local_payload={},
            )

        items = {item["key"]: item for item in payload["items"]}
        self.assertEqual(items["schumann"]["state"], "elevated")
        self.assertEqual(items["schumann"]["value"], "Elevated")
        self.assertEqual(items["schumann"]["updated_at"], "2026-03-26T12:04:00Z")


if __name__ == "__main__":
    unittest.main()
