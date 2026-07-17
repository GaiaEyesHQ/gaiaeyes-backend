import os
from pathlib import Path
import sys

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "postgresql://localhost/test")

from app.db import get_db, settings
from app.routers import local

local_test_app = FastAPI()
local_test_app.include_router(local.router)

pytestmark = pytest.mark.anyio("asyncio")


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def _set_dev_bearer():
    original = settings.DEV_BEARER
    settings.DEV_BEARER = "test-token"
    try:
        yield
    finally:
        settings.DEV_BEARER = original


@pytest.fixture(autouse=True)
def _override_db_dependency():
    local_test_app.dependency_overrides[get_db] = lambda: None
    try:
        yield
    finally:
        local_test_app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def client():
    transport = ASGITransport(app=local_test_app)
    return AsyncClient(transport=transport, base_url="http://test")


def test_merge_payload_preserves_cached_air_details_when_refresh_is_partial():
    merged = local._merge_payload(
        {"air": {"aqi": None, "category": None, "pollutant": "O3"}},
        {"air": {"aqi": 42, "category": "Good", "pollutant": "PM2.5"}},
    )

    assert merged["air"]["aqi"] == 42
    assert merged["air"]["category"] == "Good"
    assert merged["air"]["pollutant"] == "O3"


@pytest.mark.anyio
async def test_local_check_returns_cached_payload_without_live_aqi_refresh(monkeypatch, client: AsyncClient):
    cached_payload = {
        "ok": True,
        "where": {"zip": "78754", "lat": 30.3, "lon": -97.6},
        "weather": {
            "temp_c": 20.0,
            "temp_delta_24h_c": 1.1,
            "humidity_pct": 55.0,
            "precip_prob_pct": 10.0,
            "pressure_hpa": 1015.0,
            "baro_delta_24h_hpa": -1.2,
            "baro_trend": "steady",
        },
        "air": {"aqi": None, "category": None, "pollutant": None},
        "asof": "2026-04-22T01:00:00+00:00",
    }
    persisted: list[dict] = []
    attach_options: list[bool] = []

    async def _fake_attach_forecast_daily_best_effort(
        zip_code: str,  # noqa: ARG001
        payload: dict,
        *,
        refresh_if_stale: bool = True,
    ):
        attach_options.append(refresh_if_stale)
        return payload

    async def _fake_assemble_for_zip(zip_code: str):  # noqa: ARG001
        raise AssertionError("cached reads must not call live providers")

    monkeypatch.setattr(local, "latest_for_zip", lambda zip_code: cached_payload)  # noqa: ARG005
    monkeypatch.setattr(local, "assemble_for_zip", _fake_assemble_for_zip)
    monkeypatch.setattr(local, "_attach_forecast_daily_best_effort", _fake_attach_forecast_daily_best_effort)
    monkeypatch.setattr(local, "upsert_zip_payload", lambda zip_code, payload: persisted.append(payload))  # noqa: ARG005

    response = await client.get(
        "/v1/local/check",
        headers={"Authorization": "Bearer test-token"},
        params={"zip": "78754"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["air"]["aqi"] is None
    assert persisted == []
    assert attach_options == [False]


@pytest.mark.anyio
async def test_local_check_returns_cached_payload_without_live_allergen_refresh(monkeypatch, client: AsyncClient):
    cached_payload = {
        "ok": True,
        "where": {"zip": "76710", "lat": 31.54, "lon": -97.18},
        "weather": {
            "temp_c": 24.0,
            "temp_delta_24h_c": 0.8,
            "humidity_pct": 70.0,
            "precip_prob_pct": 15.0,
            "pressure_hpa": 1012.0,
            "baro_delta_24h_hpa": -0.7,
            "baro_trend": "steady",
        },
        "air": {"aqi": 54, "category": "Moderate", "pollutant": "PM2.5"},
        "allergens": {},
        "asof": "2026-04-22T22:35:00+00:00",
    }
    persisted: list[dict] = []
    attach_options: list[bool] = []

    async def _fake_attach_forecast_daily_best_effort(
        zip_code: str,  # noqa: ARG001
        payload: dict,
        *,
        refresh_if_stale: bool = True,
    ):
        attach_options.append(refresh_if_stale)
        return payload

    async def _fake_assemble_for_zip(zip_code: str):  # noqa: ARG001
        raise AssertionError("cached reads must not call live providers")

    monkeypatch.setattr(local, "latest_for_zip", lambda zip_code: cached_payload)  # noqa: ARG005
    monkeypatch.setattr(local, "assemble_for_zip", _fake_assemble_for_zip)
    monkeypatch.setattr(local, "_attach_forecast_daily_best_effort", _fake_attach_forecast_daily_best_effort)
    monkeypatch.setattr(local, "upsert_zip_payload", lambda zip_code, payload: persisted.append(payload))  # noqa: ARG005

    response = await client.get(
        "/v1/local/check",
        headers={"Authorization": "Bearer test-token"},
        params={"zip": "76710"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["air"]["aqi"] == 54
    assert data["allergens"] == {}
    assert persisted == []
    assert attach_options == [False]


@pytest.mark.anyio
async def test_local_check_returns_cached_allergen_source_without_live_refresh(monkeypatch, client: AsyncClient):
    cached_payload = {
        "ok": True,
        "where": {"zip": "78754", "lat": 30.3, "lon": -97.6},
        "weather": {
            "temp_c": 25.0,
            "temp_delta_24h_c": 1.0,
            "humidity_pct": 66.0,
            "precip_prob_pct": 20.0,
            "pressure_hpa": 1011.0,
            "baro_delta_24h_hpa": -0.4,
            "baro_trend": "steady",
        },
        "air": {"aqi": 60, "category": "Moderate", "pollutant": "PM2.5"},
        "allergens": {"source": "google-pollen:forecast"},
        "asof": "2026-04-22T22:35:00+00:00",
    }
    persisted: list[dict] = []
    attach_options: list[bool] = []

    async def _fake_attach_forecast_daily_best_effort(
        zip_code: str,  # noqa: ARG001
        payload: dict,
        *,
        refresh_if_stale: bool = True,
    ):
        attach_options.append(refresh_if_stale)
        return payload

    async def _fake_assemble_for_zip(zip_code: str):  # noqa: ARG001
        raise AssertionError("cached reads must not call live providers")

    monkeypatch.setattr(local, "latest_for_zip", lambda zip_code: cached_payload)  # noqa: ARG005
    monkeypatch.setattr(local, "assemble_for_zip", _fake_assemble_for_zip)
    monkeypatch.setattr(local, "_attach_forecast_daily_best_effort", _fake_attach_forecast_daily_best_effort)
    monkeypatch.setattr(local, "upsert_zip_payload", lambda zip_code, payload: persisted.append(payload))  # noqa: ARG005

    response = await client.get(
        "/v1/local/check",
        headers={"Authorization": "Bearer test-token"},
        params={"zip": "78754"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["allergens"] == {"source": "google-pollen:forecast"}
    assert persisted == []
    assert attach_options == [False]


@pytest.mark.anyio
async def test_local_check_returns_current_payload_when_forecast_attachment_fails(monkeypatch, client: AsyncClient):
    payload = {
        "ok": True,
        "where": {"zip": "78750", "lat": 30.42, "lon": -97.79},
        "weather": {
            "temp_c": 27.8,
            "temp_delta_24h_c": None,
            "humidity_pct": 60.0,
            "precip_prob_pct": 28.0,
            "pressure_hpa": 1012.2,
            "baro_delta_24h_hpa": None,
            "baro_trend": None,
        },
        "air": {"aqi": 57, "category": "Moderate", "pollutant": "PM2.5"},
        "allergens": {
            "source": "google-pollen:forecast",
            "state": "high",
            "primary_type": "tree",
            "primary_label": "Tree pollen",
        },
        "asof": "2026-04-22T23:51:00+00:00",
    }

    async def _fake_assemble_for_zip(zip_code: str):  # noqa: ARG001
        return payload

    async def _fake_ensure_local_forecast_daily_via_pool(**kwargs):  # noqa: ARG001
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(local, "latest_for_zip", lambda zip_code: None)  # noqa: ARG005
    monkeypatch.setattr(local, "assemble_for_zip", _fake_assemble_for_zip)
    monkeypatch.setattr(local, "ensure_local_forecast_daily_via_pool", _fake_ensure_local_forecast_daily_via_pool)
    monkeypatch.setattr(local, "ensure_weather_fields", lambda zip_code, incoming: dict(incoming))  # noqa: ARG005
    monkeypatch.setattr(local, "upsert_zip_payload", lambda zip_code, stored: None)  # noqa: ARG005,ARG001

    response = await client.get(
        "/v1/local/check",
        headers={"Authorization": "Bearer test-token"},
        params={"zip": "78750"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["where"]["zip"] == "78750"
    assert data["air"]["aqi"] == 57
    assert data["allergens"]["source"] == "google-pollen:forecast"
