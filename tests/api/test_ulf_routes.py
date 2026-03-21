import os
from pathlib import Path
import sys

import pytest
from httpx import ASGITransport, AsyncClient

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/postgres")

pytestmark = pytest.mark.anyio("asyncio")

from app.main import app
from app.db import get_db, settings
from app.routers import earth


class _DummyConn:
    pass


@pytest.fixture(autouse=True)
def _set_dev_bearer():
    original = settings.DEV_BEARER
    settings.DEV_BEARER = "test-token"
    try:
        yield
    finally:
        settings.DEV_BEARER = original


@pytest.fixture
async def client():
    async def _fake_get_db():
        yield _DummyConn()

    app.dependency_overrides[get_db] = _fake_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_db, None)


@pytest.mark.anyio
async def test_ulf_latest_returns_context_and_station_rows(monkeypatch, client: AsyncClient):
    async def _fake_latest_context(conn):  # noqa: ARG001
        return {
            "ts_utc": "2026-03-20T12:00:00+00:00",
            "stations_used": ["BOU", "CMO"],
            "regional_intensity": 71.2,
            "regional_coherence": 0.64,
            "regional_persistence": 55.4,
            "context_class": "Elevated (coherent)",
            "confidence_score": 0.73,
            "quality_flags": [],
        }

    async def _fake_latest_station(conn, *, ts_utc=None):  # noqa: ARG001
        assert ts_utc is not None
        return [
            {
                "station_id": "BOU",
                "ts_utc": "2026-03-20T12:00:00+00:00",
                "component_used": "H",
                "component_substituted": False,
                "dbdt_rms": 0.92,
                "ulf_rms_broad": 0.92,
                "ulf_band_proxy": 0.48,
                "ulf_index_station": 77.1,
                "ulf_index_localtime": None,
                "persistence_30m": 61.2,
                "persistence_90m": 49.8,
                "quality_flags": [],
            }
        ]

    monkeypatch.setattr(earth.ulf_db, "get_latest_ulf_context", _fake_latest_context)
    monkeypatch.setattr(earth.ulf_db, "get_latest_ulf_by_station", _fake_latest_station)

    response = await client.get("/v1/earth/ulf/latest")
    assert response.status_code == 200
    payload = response.json()
    assert payload["classification"] == "Elevated (coherent)"
    assert payload["confidence"] == 0.73
    assert payload["latest_context"]["regional_intensity"] == 71.2
    assert payload["latest_by_station"][0]["station_id"] == "BOU"
    assert response.headers["Cache-Control"] == "public, max-age=60"


@pytest.mark.anyio
async def test_ulf_series_defaults_to_context_mode(monkeypatch, client: AsyncClient):
    async def _fake_context_series(conn, hours):  # noqa: ARG001
        assert hours == 48
        return [
            {
                "ts_utc": "2026-03-20T10:00:00+00:00",
                "stations_used": ["BOU", "CMO"],
                "regional_intensity": 40.0,
                "regional_coherence": 0.55,
                "regional_persistence": 37.5,
                "context_class": "Active (diffuse)",
                "confidence_score": 0.52,
                "quality_flags": [],
            }
        ]

    async def _unexpected_station_series(conn, hours, station_id=None):  # noqa: ARG001
        raise AssertionError("station series should not be called in context mode")

    monkeypatch.setattr(earth.ulf_db, "get_ulf_context_series", _fake_context_series)
    monkeypatch.setattr(earth.ulf_db, "get_ulf_station_series", _unexpected_station_series)

    response = await client.get("/v1/earth/ulf/series")
    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "context"
    assert payload["hours"] == 48
    assert len(payload["series"]) == 1


@pytest.mark.anyio
async def test_ulf_series_station_mode_returns_station_rows(monkeypatch, client: AsyncClient):
    async def _fake_station_series(conn, hours, station_id=None):  # noqa: ARG001
        assert hours == 24
        assert station_id == "CMO"
        return [
            {
                "station_id": "CMO",
                "ts_utc": "2026-03-20T09:00:00+00:00",
                "component_used": "X",
                "component_substituted": True,
                "dbdt_rms": 0.72,
                "ulf_rms_broad": 0.72,
                "ulf_band_proxy": 0.33,
                "ulf_index_station": 58.4,
                "ulf_index_localtime": None,
                "persistence_30m": 51.1,
                "persistence_90m": 44.2,
                "quality_flags": ["fallback_component"],
            }
        ]

    async def _unexpected_context_series(conn, hours):  # noqa: ARG001
        raise AssertionError("context series should not be called in station mode")

    monkeypatch.setattr(earth.ulf_db, "get_ulf_station_series", _fake_station_series)
    monkeypatch.setattr(earth.ulf_db, "get_ulf_context_series", _unexpected_context_series)

    response = await client.get("/v1/earth/ulf/series", params={"mode": "station", "hours": 24, "station_id": "CMO"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "station"
    assert payload["hours"] == 24
    assert payload["series"][0]["station_id"] == "CMO"
