import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "postgresql://localhost/test")

from services.local_signals import aggregator


pytestmark = pytest.mark.anyio("asyncio")


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def test_fetch_air_quality_prefers_latlon_results(monkeypatch):
    calls: list[tuple[str, int]] = []
    monkeypatch.setattr(aggregator.airnow, "DEFAULT_RADIUS_MI", 25)

    async def _fake_latlon(lat: float, lon: float, distance_miles: int | None = None):
        calls.append(("latlon", int(distance_miles or 0)))
        return [{"AQI": 42, "ParameterName": "PM2.5"}]

    async def _fake_zip(zip_code: str, distance_miles: int | None = None):
        calls.append(("zip", int(distance_miles or 0)))
        return [{"AQI": 99, "ParameterName": "O3"}]

    monkeypatch.setattr(aggregator.airnow, "current_by_latlon", _fake_latlon)
    monkeypatch.setattr(aggregator.airnow, "current_by_zip", _fake_zip)

    rows = await aggregator._fetch_air_quality("76541", 31.1171, -97.7278)

    assert rows == [{"AQI": 42, "ParameterName": "PM2.5"}]
    assert calls == [("latlon", aggregator.airnow.DEFAULT_RADIUS_MI)]


async def test_fetch_air_quality_expands_search_before_zip_fallback(monkeypatch):
    calls: list[tuple[str, int]] = []
    monkeypatch.setattr(aggregator.airnow, "DEFAULT_RADIUS_MI", 25)

    async def _fake_latlon(lat: float, lon: float, distance_miles: int | None = None):
        calls.append(("latlon", int(distance_miles or 0)))
        return []

    async def _fake_zip(zip_code: str, distance_miles: int | None = None):
        radius = int(distance_miles or 0)
        calls.append(("zip", radius))
        if radius == 100:
            return [{"AQI": 61, "ParameterName": "PM2.5"}]
        return []

    monkeypatch.setattr(aggregator.airnow, "current_by_latlon", _fake_latlon)
    monkeypatch.setattr(aggregator.airnow, "current_by_zip", _fake_zip)

    rows = await aggregator._fetch_air_quality("76541", 31.1171, -97.7278)

    assert rows == [{"AQI": 61, "ParameterName": "PM2.5"}]
    assert calls == [
        ("latlon", 25),
        ("latlon", 50),
        ("latlon", 100),
        ("zip", 25),
        ("zip", 50),
        ("zip", 100),
    ]


async def test_fetch_pollen_forecast_tries_nearby_coordinates_when_exact_centroid_is_empty(monkeypatch):
    calls: list[tuple[float, float]] = []
    pollen_payload = {
        "dailyInfo": [
            {
                "date": {"year": 2026, "month": 4, "day": 23},
                "pollenTypeInfo": [
                    {
                        "code": "TREE",
                        "indexInfo": {"value": 4, "category": "High"},
                    }
                ],
            }
        ]
    }

    async def _fake_forecast_by_latlon(lat: float, lon: float, *, days: int = 3):  # noqa: ARG001
        calls.append((lat, lon))
        return {} if len(calls) == 1 else pollen_payload

    monkeypatch.setattr(aggregator.pollen, "forecast_by_latlon", _fake_forecast_by_latlon)

    payload = await aggregator._fetch_pollen_forecast("78752", 30.3316, -97.7004, days=3)

    assert payload == pollen_payload
    assert calls[0] == (30.3316, -97.7004)
    assert len(calls) == 2
