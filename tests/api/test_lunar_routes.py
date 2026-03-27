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
from app.routers import lunar


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
    transport = ASGITransport(app=app, lifespan="off")
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_db, None)


@pytest.mark.anyio
async def test_lunar_current_returns_context(client: AsyncClient):
    response = await client.get(
        "/v1/lunar/current",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["utc_date"]
    assert payload["moon_phase_label"]
    assert "days_from_full_moon" in payload
    assert "days_from_new_moon" in payload


@pytest.mark.anyio
async def test_lunar_overlay_returns_window_markers(client: AsyncClient):
    response = await client.get(
        "/v1/series/lunar-overlay",
        headers={"Authorization": "Bearer test-token"},
        params={"start": "2026-03-01", "end": "2026-03-31"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert "windows" in payload
    assert any(item["type"] in {"full", "new"} for item in payload["windows"])


@pytest.mark.anyio
async def test_lunar_insights_returns_insufficient_data_payload(monkeypatch, client: AsyncClient):
    async def _fake_preferences(conn, user_id):  # noqa: ARG001
        return {"lunar_sensitivity_declared": True}

    async def _fake_fetch_patterns(conn, user_id):  # noqa: ARG001
        return None

    monkeypatch.setattr(lunar, "_fetch_profile_preferences", _fake_preferences)
    monkeypatch.setattr(lunar, "_fetch_user_lunar_pattern_row", _fake_fetch_patterns)

    response = await client.get(
        "/v1/insights/lunar",
        headers={"Authorization": "Bearer test-token", "X-Dev-UserId": "00000000-0000-0000-0000-000000000111"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["declared_lunar_sensitivity"] is True
    assert payload["insufficient_data"] is True
    assert payload["pattern_strength"] == "none"
    assert payload["message_scientific"]


@pytest.mark.anyio
async def test_lunar_insights_returns_highlighted_pattern(monkeypatch, client: AsyncClient):
    async def _fake_preferences(conn, user_id):  # noqa: ARG001
        return {"lunar_sensitivity_declared": False}

    async def _fake_fetch_patterns(conn, user_id):  # noqa: ARG001
        return {
            "observed_days": 42,
            "full_window_days": 6,
            "new_window_days": 5,
            "baseline_days": 31,
            "hrv_observed_days": 42,
            "hrv_full_days": 6,
            "hrv_new_days": 5,
            "hrv_baseline_days": 31,
            "hrv_full_avg": 31.2,
            "hrv_new_avg": 34.7,
            "hrv_baseline_avg": 36.1,
            "sleep_observed_days": 42,
            "sleep_full_days": 6,
            "sleep_new_days": 5,
            "sleep_baseline_days": 31,
            "sleep_full_avg": 82.4,
            "sleep_new_avg": 85.7,
            "sleep_baseline_avg": 87.3,
            "symptom_observed_days": 24,
            "symptom_full_days": 5,
            "symptom_new_days": 4,
            "symptom_baseline_days": 15,
            "symptom_events_full_avg": 2.1,
            "symptom_events_new_avg": 1.4,
            "symptom_events_baseline_avg": 0.9,
            "symptom_severity_full_avg": 2.7,
            "symptom_severity_new_avg": 2.1,
            "symptom_severity_baseline_avg": 1.8,
        }

    monkeypatch.setattr(lunar, "_fetch_profile_preferences", _fake_preferences)
    monkeypatch.setattr(lunar, "_fetch_user_lunar_pattern_row", _fake_fetch_patterns)

    response = await client.get(
        "/v1/insights/lunar",
        headers={"Authorization": "Bearer test-token", "X-Dev-UserId": "00000000-0000-0000-0000-000000000111"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["insufficient_data"] is False
    assert payload["pattern_strength"] in {"weak", "moderate"}
    assert payload["highlight_window"] in {"full", "new"}
    assert payload["highlight_metric"] in {"hrv", "sleep_efficiency", "symptom_events", "symptom_severity"}
    assert payload["full_window"]["hrv_avg"] == pytest.approx(31.2)
    assert payload["deltas"]["hrv_full_vs_baseline"] == pytest.approx(-4.9)
