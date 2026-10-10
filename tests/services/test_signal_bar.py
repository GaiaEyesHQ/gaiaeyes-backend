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
    def test_explicit_missing_snapshots_never_fetch_or_imply_quiet(self) -> None:
        for snapshot in (None, {}):
            with self.subTest(snapshot=snapshot), patch.object(
                signal_bar.signal_resolver,
                "_fetch_space_snapshot",
                side_effect=AssertionError("unexpected space fetch"),
            ), patch.object(
                signal_bar,
                "_fetch_schumann_snapshot",
                side_effect=AssertionError("unexpected Schumann fetch"),
            ):
                payload = signal_bar.build_signal_bar(
                    day=date(2026, 3, 26),
                    active_states=[],
                    local_payload={},
                    space_snapshot=snapshot,
                    schumann_snapshot=snapshot,
                )

            self.assertEqual(payload["items"], [])
            self.assertEqual(payload["unavailable_items"], ["kp", "solar_wind", "schumann", "pressure"])
            self.assertEqual(payload["availability"], "unavailable")
            self.assertIsNone(payload["updated_at"])

    def test_partial_snapshot_omits_only_missing_pills_and_keeps_legacy_states(self) -> None:
        payload = signal_bar.build_signal_bar(
            day=date(2026, 3, 26),
            active_states=[{"signal_key": "schumann.variability_24h", "state": "elevated"}],
            local_payload={},
            space_snapshot={"kp_now": 0.0},
            schumann_snapshot=None,
        )

        self.assertEqual([item["key"] for item in payload["items"]], ["kp", "schumann"])
        self.assertEqual(payload["unavailable_items"], ["solar_wind", "pressure"])
        self.assertEqual(payload["availability"], "partial")
        self.assertEqual([item["state"] for item in payload["items"]], ["quiet", "elevated"])
        self.assertTrue(all(item["state"] in {"quiet", "watch", "elevated", "strong"} for item in payload["items"]))

    def test_supplied_snapshots_compose_without_fetching_and_keep_source_times(self) -> None:
        space = {
            "kp_now": 0.0,
            "kp_max": 6.0,
            "sw_speed_now_kms": 420.0,
            "sw_speed_avg": 750.0,
            "space_now_ts": datetime(2026, 3, 20, 12, 0, tzinfo=timezone.utc),
        }
        schumann = {"state": "quiet", "label": "Calm", "updated_at": "2026-03-20T11:00:00Z"}
        with patch.object(
            signal_bar.signal_resolver,
            "_fetch_space_snapshot",
            side_effect=AssertionError("unexpected space fetch"),
        ), patch.object(
            signal_bar,
            "_fetch_schumann_snapshot",
            side_effect=AssertionError("unexpected Schumann fetch"),
        ):
            payload = signal_bar.build_signal_bar(
                day=date(2026, 3, 26),
                active_states=[],
                local_payload={"weather": {"baro_delta_12h_hpa": 0.0}},
                space_snapshot=space,
                schumann_snapshot=schumann,
            )

        items = {item["key"]: item for item in payload["items"]}
        self.assertEqual(items["kp"]["value"], "0.0")
        self.assertEqual(items["solar_wind"]["value"], "420 km/s")
        self.assertEqual(items["pressure"]["value"], "+0.0")
        self.assertEqual(items["schumann"]["value"], "Calm")
        self.assertEqual(items["kp"]["updated_at"], "2026-03-20T12:00:00+00:00")
        self.assertEqual(items["schumann"]["updated_at"], "2026-03-20T11:00:00Z")
        self.assertTrue(all(item["state"] == "quiet" for item in payload["items"]))
        self.assertTrue(all(item["availability"] == "available" for item in payload["items"]))
        self.assertEqual(payload["availability"], "available")
        self.assertEqual(payload["unavailable_items"], [])
        self.assertIsInstance(space["space_now_ts"], datetime)
        self.assertEqual(schumann, {"state": "quiet", "label": "Calm", "updated_at": "2026-03-20T11:00:00Z"})

    def test_omitted_snapshots_retain_fetch_behavior(self) -> None:
        day = date(2026, 3, 26)
        with patch.object(signal_bar.signal_resolver, "_fetch_space_snapshot", return_value={}) as space_fetch, patch.object(
            signal_bar, "_fetch_schumann_snapshot", return_value=None,
        ) as schumann_fetch:
            signal_bar.build_signal_bar(day=day, active_states=[], local_payload={})

        space_fetch.assert_called_once_with(day)
        schumann_fetch.assert_called_once_with()

    def test_space_composition_is_pure_and_uses_measured_daily_fallbacks(self) -> None:
        with patch.object(
            signal_bar.signal_resolver, "_fetch_space_snapshot", side_effect=AssertionError("unexpected fetch"),
        ):
            payload = signal_bar._compose_space_signal_snapshot({"kp_max": 4.5, "sw_speed_avg": 720.0})

        items = {item["key"]: item for item in payload["items"]}
        self.assertEqual(items["kp"]["value"], "4.5")
        self.assertEqual(items["kp"]["state"], "elevated")
        self.assertEqual(items["solar_wind"]["value"], "720 km/s")
        self.assertEqual(items["solar_wind"]["state"], "strong")
        self.assertEqual(payload["availability"], "available")
        self.assertEqual(payload["unavailable_items"], [])

    def test_nonfinite_space_measurements_are_unavailable(self) -> None:
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value):
                payload = signal_bar._compose_space_signal_snapshot({"kp_now": value, "sw_speed_now_kms": value})
                self.assertEqual(payload["items"], [])
                self.assertEqual(payload["unavailable_items"], ["kp", "solar_wind"])
                self.assertEqual(payload["availability"], "unavailable")

    def test_inactive_schumann_trigger_and_pressure_trend_are_not_measurements(self) -> None:
        payload = signal_bar.build_signal_bar(
            day=date(2026, 3, 26),
            active_states=[{"signal_key": "schumann.variability_24h", "state": "quiet"}],
            local_payload={"weather": {"pressure_trend": "steady"}},
            space_snapshot=None,
            schumann_snapshot=None,
        )
        self.assertEqual(payload["items"], [])
        self.assertEqual(payload["unavailable_items"], ["kp", "solar_wind", "schumann", "pressure"])
        self.assertEqual(payload["availability"], "unavailable")

    def test_pressure_zero_delta_is_not_replaced_by_fallback(self) -> None:
        payload = signal_bar.build_signal_bar(
            day=date(2026, 3, 26),
            active_states=[],
            local_payload={"weather": {"baro_delta_12h_hpa": 0.0, "pressure_delta_12h": -12.0}},
            space_snapshot=None,
            schumann_snapshot=None,
        )
        pressure = next(item for item in payload["items"] if item["key"] == "pressure")
        self.assertEqual(pressure["state"], "quiet")
        self.assertEqual(pressure["value"], "+0.0")

    def test_active_pressure_trigger_survives_missing_local_metrics(self) -> None:
        payload = signal_bar.build_signal_bar(
            day=date(2026, 3, 26),
            active_states=[{"signal_key": "earthweather.pressure_drop_3h", "state": "high"}],
            local_payload={},
            space_snapshot=None,
            schumann_snapshot=None,
        )
        pressure = next(item for item in payload["items"] if item["key"] == "pressure")
        self.assertEqual(pressure["state"], "strong")
        self.assertEqual(pressure["value"], "—")
        self.assertEqual(payload["unavailable_items"], ["kp", "solar_wind", "schumann"])
        self.assertEqual(payload["availability"], "partial")

    def test_refresh_signal_bar_space_updates_availability_when_metrics_return(self) -> None:
        missing = signal_bar.build_signal_bar(
            day=date(2026, 3, 26), active_states=[], local_payload={},
            space_snapshot=None, schumann_snapshot=None,
        )
        with patch.object(signal_bar.signal_resolver, "_fetch_space_snapshot", return_value={"kp_now": 1.0}):
            refreshed = signal_bar.refresh_signal_bar_space(missing, day=date(2026, 3, 26))

        self.assertEqual([item["key"] for item in refreshed["items"]], ["kp"])
        self.assertEqual(refreshed["unavailable_items"], ["solar_wind", "schumann", "pressure"])
        self.assertEqual(refreshed["availability"], "partial")
        self.assertEqual(missing["availability"], "unavailable")
        self.assertEqual(missing["unavailable_items"], ["kp", "solar_wind", "schumann", "pressure"])

    def test_refresh_signal_bar_space_restores_order_and_missing_metadata(self) -> None:
        partial = signal_bar.build_signal_bar(
            day=date(2026, 3, 26), active_states=[],
            local_payload={"weather": {"baro_delta_12h_hpa": 0.0}},
            space_snapshot=None,
            schumann_snapshot={"state": "quiet", "label": "Calm"},
        )
        for snapshot, expected_keys, expected_missing in (
            ({"kp_now": 1.0}, ["kp", "schumann", "pressure"], ["solar_wind"]),
            ({"kp_now": 1.0, "sw_speed_now_kms": 400.0}, ["kp", "solar_wind", "schumann", "pressure"], []),
        ):
            with self.subTest(snapshot=snapshot), patch.object(
                signal_bar.signal_resolver, "_fetch_space_snapshot", return_value=snapshot,
            ):
                refreshed = signal_bar.refresh_signal_bar_space(partial, day=date(2026, 3, 26))

            self.assertEqual([item["key"] for item in refreshed["items"]], expected_keys)
            self.assertEqual(refreshed["unavailable_items"], expected_missing)
            self.assertEqual(refreshed["availability"], "partial" if expected_missing else "available")
            self.assertEqual(refreshed["items"][-2:], partial["items"])

        self.assertEqual(partial["unavailable_items"], ["kp", "solar_wind"])
        self.assertEqual([item["key"] for item in partial["items"]], ["schumann", "pressure"])

    def test_refresh_signal_bar_space_replaces_only_volatile_space_values(self) -> None:
        stale = {
            "updated_at": "2026-08-04T01:00:00Z",
            "space": {
                "kp_now": 0.0,
                "sw_speed_now_kms": 390.0,
                "updated_at": "2026-08-04T01:00:00Z",
            },
            "items": [
                {"key": "kp", "label": "KP", "value": "0.0", "state": "quiet"},
                {"key": "solar_wind", "label": "SW", "value": "390 km/s", "state": "quiet"},
                {"key": "schumann", "label": "SR", "value": "Active", "state": "watch"},
                {"key": "pressure", "label": "hPa", "value": "1014 →", "state": "quiet"},
            ],
        }

        with patch.object(
            signal_bar.signal_resolver,
            "_fetch_space_snapshot",
            return_value={
                "kp_now": 2.7,
                "kp_max": 3.0,
                "bz_now": -2.2,
                "sw_speed_now_kms": 448.4,
                "sw_density_now_cm3": 6.1,
                "space_now_ts": datetime(2026, 8, 4, 2, 5, tzinfo=timezone.utc),
            },
        ):
            refreshed = signal_bar.refresh_signal_bar_space(stale, day=date(2026, 8, 4))

        items = {item["key"]: item for item in refreshed["items"]}
        self.assertEqual(stale["space"]["kp_now"], 0.0)
        self.assertEqual(refreshed["space"]["kp_now"], 2.7)
        self.assertEqual(refreshed["space"]["bz_now"], -2.2)
        self.assertEqual(refreshed["space"]["sw_density_now_cm3"], 6.1)
        self.assertEqual(items["kp"]["value"], "2.7")
        self.assertEqual(items["solar_wind"]["value"], "448 km/s")
        self.assertEqual(items["schumann"], stale["items"][2])
        self.assertEqual(items["pressure"], stale["items"][3])
        self.assertEqual(refreshed["updated_at"], "2026-08-04T02:05:00+00:00")

    def test_refresh_signal_bar_space_preserves_cache_when_current_source_is_empty(self) -> None:
        stale = {
            "updated_at": "2026-08-04T01:00:00Z",
            "space": {"kp_now": 0.3},
            "items": [{"key": "kp", "value": "0.3"}],
        }

        with patch.object(signal_bar.signal_resolver, "_fetch_space_snapshot", return_value={}):
            refreshed = signal_bar.refresh_signal_bar_space(stale, day=date(2026, 8, 4))

        self.assertEqual(refreshed, stale)
        self.assertIsNot(refreshed, stale)

    def test_refresh_signal_bar_space_preserves_missing_live_metrics(self) -> None:
        stale = {
            "updated_at": "2026-08-04T01:00:00Z",
            "space": {
                "kp_now": 0.0,
                "bz_now": -1.7,
                "sw_speed_now_kms": 421.0,
                "sw_density_now_cm3": 5.4,
                "updated_at": "2026-08-04T01:00:00Z",
            },
            "items": [
                {"key": "kp", "label": "KP", "value": "0.0", "state": "quiet"},
                {"key": "solar_wind", "label": "SW", "value": "421 km/s", "state": "quiet"},
            ],
        }

        with patch.object(
            signal_bar.signal_resolver,
            "_fetch_space_snapshot",
            return_value={
                "kp_now": 2.0,
                "space_now_ts": datetime(2026, 8, 4, 2, 5, tzinfo=timezone.utc),
            },
        ):
            refreshed = signal_bar.refresh_signal_bar_space(stale, day=date(2026, 8, 4))

        items = {item["key"]: item for item in refreshed["items"]}
        self.assertEqual(refreshed["space"]["kp_now"], 2.0)
        self.assertEqual(refreshed["space"]["bz_now"], -1.7)
        self.assertEqual(refreshed["space"]["sw_speed_now_kms"], 421.0)
        self.assertEqual(refreshed["space"]["sw_density_now_cm3"], 5.4)
        self.assertEqual(items["kp"]["value"], "2.0")
        self.assertEqual(items["solar_wind"], stale["items"][1])

    def test_build_signal_bar_prefers_current_solar_wind_over_higher_daily_average(self) -> None:
        with patch.object(
            signal_bar.signal_resolver,
            "_fetch_space_snapshot",
            return_value={"kp_now": 3.7, "sw_speed_now_kms": 464.0, "sw_speed_avg": 566.0},
        ), patch.object(signal_bar, "_fetch_schumann_snapshot", return_value=None):
            payload = signal_bar.build_signal_bar(
                day=date(2026, 7, 9),
                active_states=[],
                local_payload={},
            )

        items = {item["key"]: item for item in payload["items"]}
        self.assertEqual(items["solar_wind"]["value"], "464 km/s")
        self.assertEqual(items["solar_wind"]["numeric_value"], 464.0)
        self.assertEqual(items["solar_wind"]["state"], "quiet")
        self.assertEqual(payload["space"]["kp_now"], 3.7)
        self.assertEqual(payload["space"]["sw_speed_now_kms"], 464.0)

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
                "kp_max": 6.7,
                "bz_now": -4.8,
                "sw_speed_now_kms": 689.0,
                "sw_density_now_cm3": 7.3,
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
        self.assertEqual(items["kp"]["numeric_value"], 6.2)
        self.assertEqual(items["solar_wind"]["state"], "elevated")
        self.assertEqual(items["solar_wind"]["value"], "689 km/s")
        self.assertEqual(items["solar_wind"]["numeric_value"], 689.0)
        self.assertEqual(items["schumann"]["state"], "elevated")
        self.assertEqual(items["schumann"]["value"], "Elevated")
        self.assertEqual(items["pressure"]["state"], "watch")
        self.assertEqual(items["pressure"]["value"], "1009 ↓")
        self.assertEqual(items["pressure"]["detail_target"], "local_conditions")
        self.assertEqual(
            payload["space"],
            {
                "kp_now": 6.2,
                "kp_max_24h": 6.7,
                "bz_now": -4.8,
                "sw_speed_now_kms": 689.0,
                "sw_density_now_cm3": 7.3,
                "updated_at": "2026-03-26T11:55:00+00:00",
            },
        )

    def test_build_signal_bar_keeps_measured_quiet_but_missing_schumann_is_unavailable(self) -> None:
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
        self.assertNotIn("schumann", items)
        self.assertEqual(payload["unavailable_items"], ["schumann"])
        self.assertEqual(payload["availability"], "partial")
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
