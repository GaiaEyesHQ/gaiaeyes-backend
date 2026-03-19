from __future__ import annotations

import sys
import unittest
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    outlook_router = import_module("app.routers.outlook")
    _IMPORT_ERROR = None
except ModuleNotFoundError as exc:  # pragma: no cover - environment-specific
    outlook_router = None
    _IMPORT_ERROR = exc


@unittest.skipIf(outlook_router is None, f"router import unavailable: {_IMPORT_ERROR}")
class OutlookRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_user_outlook_route_returns_structured_payload(self) -> None:
        async def _fake_builder(conn, user_id):  # noqa: ARG001
            return {
                "generated_at": "2026-03-18T12:00:00+00:00",
                "available_windows": ["next_24h", "next_72h"],
                "forecast_data_ready": {
                    "location_found": True,
                    "local_forecast_daily": True,
                    "local_forecast_days": 3,
                    "space_forecast_daily": True,
                    "space_forecast_days": 3,
                    "next_24h": True,
                    "next_72h": True,
                    "next_7d": False,
                },
                "next_24h": {
                    "window_hours": 24,
                    "likely_elevated_domains": [{"key": "pain", "label": "Pain", "likelihood": "watch"}],
                    "top_drivers": [{"key": "pressure", "label": "Pressure swing", "severity": "watch"}],
                    "summary": "Pressure may swing more over the next 24 hours.",
                    "support_line": "Worth keeping pacing steady.",
                },
                "next_72h": {
                    "window_hours": 72,
                    "likely_elevated_domains": [{"key": "sleep", "label": "Sleep", "likelihood": "mild"}],
                    "top_drivers": [{"key": "kp", "label": "Geomagnetic outlook", "severity": "watch"}],
                    "summary": "Geomagnetic activity may stay a bit more active over the next 72 hours.",
                    "support_line": "Worth keeping evenings lighter.",
                },
            }

        request = SimpleNamespace(state=SimpleNamespace(user_id="00000000-0000-0000-0000-000000000321"))
        with patch("app.routers.outlook.build_user_outlook_payload", _fake_builder):
            payload = await outlook_router.user_outlook(request, conn=object())

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["available_windows"], ["next_24h", "next_72h"])
        self.assertEqual(payload["next_24h"]["top_drivers"][0]["key"], "pressure")
        self.assertEqual(payload["next_72h"]["likely_elevated_domains"][0]["key"], "sleep")


if __name__ == "__main__":
    unittest.main()
