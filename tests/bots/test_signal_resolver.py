import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from bots.gauges import signal_resolver
    _IMPORT_ERROR = None
except ModuleNotFoundError as exc:  # pragma: no cover - optional DB deps are absent in some local envs.
    signal_resolver = None
    _IMPORT_ERROR = exc


@unittest.skipIf(_IMPORT_ERROR is not None, f"Signal resolver tests require optional dependencies: {_IMPORT_ERROR}")
class SignalResolverTests(unittest.TestCase):
    def test_resolve_signals_uses_solar_wind_average_fallback(self) -> None:
        with patch.object(
            signal_resolver,
            "_fetch_space_snapshot",
            return_value={
                "sw_speed_now_kms": None,
                "sw_speed_avg": 655.0,
                "updated_at": None,
            },
        ), patch.object(signal_resolver, "_fetch_schumann_stddev_24h", return_value=None), patch.object(
            signal_resolver,
            "_full_moon_days_to",
            return_value=99.0,
        ):
            signals = signal_resolver.resolve_signals(
                "user-1",
                date(2026, 3, 17),
                local_payload={},
                definition={"signal_definitions": []},
            )

        solar_wind = next(item for item in signals if item["signal_key"] == "spaceweather.sw_speed")
        self.assertEqual(solar_wind["state"], "high")
        self.assertEqual(solar_wind["severity"], "high")
        self.assertTrue(solar_wind["force_visibility"])
        self.assertTrue(solar_wind["force_signal"])
        self.assertEqual(solar_wind["evidence"]["sw_speed_avg"], 655.0)


if __name__ == "__main__":
    unittest.main()
