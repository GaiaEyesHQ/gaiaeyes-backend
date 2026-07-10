import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.drivers.driver_normalize import (
    merge_signal_bar_driver_candidates,
    normalize_environmental_drivers,
    signal_bar_driver_candidates,
)


class DriverNormalizeV2Tests(unittest.TestCase):
    def test_signal_bar_candidate_keeps_state_and_numeric_value_separate(self) -> None:
        rows = signal_bar_driver_candidates(
            {
                "items": [
                    {
                        "key": "solar_wind",
                        "value": "577 km/s",
                        "numeric_value": 577.0,
                        "state": "elevated",
                    }
                ]
            }
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["state"], "Elevated")
        self.assertEqual(rows[0]["value"], 577.0)
        self.assertEqual(rows[0]["display"], "Solar Wind: Elevated (577 km/s)")

    def test_signal_bar_current_wind_replaces_stale_driver_value(self) -> None:
        rows = merge_signal_bar_driver_candidates(
            [
                {
                    "key": "sw",
                    "label": "Solar Wind",
                    "severity": "high",
                    "state": "High",
                    "value": 619.0,
                    "unit": "km/s",
                    "display": "Solar Wind: High (619 km/s)",
                }
            ],
            {
                "items": [
                    {
                        "key": "solar_wind",
                        "value": "577 km/s",
                        "numeric_value": 577.0,
                        "state": "elevated",
                    }
                ]
            },
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["state"], "Elevated")
        self.assertEqual(rows[0]["value"], 577.0)

    def test_signal_bar_current_quiet_kp_removes_stale_active_driver(self) -> None:
        rows = merge_signal_bar_driver_candidates(
            [
                {
                    "key": "kp",
                    "label": "Kp Index",
                    "severity": "watch",
                    "state": "Elevated",
                    "value": 5.0,
                },
                {
                    "key": "schumann",
                    "label": "Schumann",
                    "severity": "watch",
                    "state": "Active",
                },
            ],
            {
                "items": [
                    {
                        "key": "kp",
                        "value": "3.0",
                        "numeric_value": 3.0,
                        "state": "quiet",
                    }
                ]
            },
        )

        self.assertEqual([row["key"] for row in rows], ["schumann"])

    def test_normalize_environmental_drivers_dedupes_family_and_prefers_stronger(self) -> None:
        active_states = [
            {"signal_key": "earthweather.pressure_swing_12h", "state": "moderate", "value": -6.4},
            {"signal_key": "earthweather.pressure_drop_3h", "state": "high", "value": -5.2},
            {"signal_key": "spaceweather.sw_speed", "state": "high", "value": 655.0},
            {"signal_key": "spaceweather.kp", "state": "elevated", "value": 5.0},
        ]
        alerts = [{"key": "alert.air_quality", "severity": "watch"}]
        local_payload = {"weather": {"baro_delta_12h_hpa": -6.0}, "air": {"aqi": 119}}

        rows = normalize_environmental_drivers(
            active_states=active_states,
            local_payload=local_payload,
            alerts_json=alerts,
        )

        keys = [row["key"] for row in rows]
        self.assertEqual(keys.count("pressure"), 1)
        pressure = next(row for row in rows if row["key"] == "pressure")
        self.assertEqual(pressure["severity"], "high")
        self.assertEqual(pressure["state"], "High")
        self.assertTrue(pressure["show_driver"])

        aqi = next(row for row in rows if row["key"] == "aqi")
        self.assertEqual(aqi["severity"], "watch")
        self.assertEqual(aqi["value"], 119.0)

        solar_wind = next(row for row in rows if row["key"] == "sw")
        self.assertEqual(solar_wind["severity"], "high")
        self.assertTrue(solar_wind["force_visible"])
        self.assertGreaterEqual(solar_wind["signal_strength"], 0.9)

    def test_normalize_environmental_drivers_uses_local_payload_when_no_active_signals(self) -> None:
        local_payload = {
            "weather": {
                "baro_delta_12h_hpa": -9.1,
                "temp_delta_24h_c": 6.2,
                "humidity_pct": 82,
            },
            "air": {"aqi": 58},
        }

        rows = normalize_environmental_drivers(
            active_states=[],
            local_payload=local_payload,
            alerts_json=[],
        )

        keys = [row["key"] for row in rows]
        self.assertEqual(keys[0], "pressure")
        self.assertEqual(set(keys), {"pressure", "temp", "humidity", "aqi"})

        pressure = rows[0]
        self.assertEqual(pressure["severity"], "watch")
        self.assertIn("Pressure Swing", pressure["display"])

        humidity = next(row for row in rows if row["key"] == "humidity")
        self.assertEqual(humidity["severity"], "watch")
        self.assertEqual(humidity["display"], "Humidity: Watch (82%)")

    def test_stale_space_alerts_do_not_create_current_drivers(self) -> None:
        rows = normalize_environmental_drivers(
            active_states=[],
            local_payload={},
            alerts_json=[
                {"key": "alert.geomagnetic_active", "severity": "watch"},
                {"key": "alert.solar_wind_speed", "severity": "watch"},
            ],
        )

        self.assertFalse(any(row["key"] in {"kp", "sw"} for row in rows))

    def test_normalize_environmental_drivers_preserves_force_visible_high_signal(self) -> None:
        rows = normalize_environmental_drivers(
            active_states=[
                {
                    "signal_key": "spaceweather.sw_speed",
                    "state": "high",
                    "severity": "high",
                    "value": 655.0,
                    "force_visibility": True,
                },
                {
                    "signal_key": "earthweather.pressure_swing_12h",
                    "state": "moderate",
                    "value": -6.2,
                },
            ],
            local_payload={},
            alerts_json=[],
        )

        self.assertEqual(rows[0]["key"], "sw")
        self.assertTrue(rows[0]["force_visible"])
        self.assertTrue(rows[0]["show_driver"])

    def test_normalize_environmental_drivers_uses_primary_pollen_label_when_available(self) -> None:
        rows = normalize_environmental_drivers(
            active_states=[
                {
                    "signal_key": "earthweather.allergens",
                    "state": "high",
                    "value": 4.2,
                }
            ],
            local_payload={
                "allergens": {
                    "overall_level": "high",
                    "overall_index": 4.2,
                    "primary_type": "grass",
                }
            },
            alerts_json=[],
        )

        allergen = next(row for row in rows if row["key"] == "allergens")
        self.assertEqual(allergen["label"], "Grass pollen")
        self.assertIn("Grass pollen", allergen["display"])


if __name__ == "__main__":
    unittest.main()
