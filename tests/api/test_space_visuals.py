from __future__ import annotations

import asyncio
from pathlib import Path
import sys
from datetime import datetime, timezone
from typing import Any, List

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.db import get_db, settings

pytestmark = pytest.mark.anyio("asyncio")


@pytest.fixture(autouse=True)
def _set_dev_bearer():
    original = settings.DEV_BEARER
    settings.DEV_BEARER = "test-token"
    try:
        yield
    finally:
        settings.DEV_BEARER = original


@pytest.fixture
def anyio_backend():
    return "asyncio"


class _FakeCursor:
    def __init__(self, rows: List[dict[str, Any]], should_fail: bool = False):
        self._rows = rows
        self._fail = should_fail

    async def __aenter__(self):
        if self._fail:
            raise RuntimeError("boom")
        return self

    async def __aexit__(self, exc_type, exc, tb):  # noqa: ARG002
        return False

    async def execute(self, *args, **kwargs):  # noqa: ARG002
        if self._fail:
            raise RuntimeError("boom")
        return None

    async def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self, rows: List[dict[str, Any]], should_fail: bool = False):
        self._rows = rows
        self._fail = should_fail

    def cursor(self, *args, **kwargs):  # noqa: ARG002
        return _FakeCursor(self._rows, should_fail=self._fail)


@pytest.fixture
async def client(monkeypatch):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_db, None)


def _auth_headers():
    return {"Authorization": "Bearer test-token"}


@pytest.mark.anyio
async def test_space_visuals_happy_path(monkeypatch, client: AsyncClient):
    ts = datetime(2024, 5, 2, 12, tzinfo=timezone.utc)
    rows = [
        {
            "ts": ts,
            "key": "aia_primary",
            "asset_type": "image",
            "image_path": "images/space/aia.jpg",
            "meta": {"capture_stamp": "20240502T120000Z"},
            "series": None,
            "feature_flags": {"flare_markers": True},
            "instrument": "SDO",
            "credit": "NASA",
        },
        {
            "ts": ts,
            "key": "goes_xray",
            "asset_type": "series",
            "image_path": None,
            "meta": {"label": "X-ray", "color": "#7fc8ff"},
            "series": [{"ts": "2024-05-02T11:00:00Z", "value": 1e-6}],
            "feature_flags": {"flare_markers": True},
            "instrument": "GOES",
            "credit": "NOAA",
        },
    ]

    async def _fake_get_db():
        yield _FakeConn(rows)

    app.dependency_overrides[get_db] = _fake_get_db
    monkeypatch.setenv("MEDIA_BASE_URL", "https://media.test")

    resp = await client.get("/v1/space/visuals", headers=_auth_headers())
    body = resp.json()
    assert body["ok"] is True
    assert len(body["images"]) == 1
    assert body["images"][0]["url"] == "https://media.test/images/space/aia.jpg"
    assert body["series"][0]["key"] == "goes_xray"
    assert body["feature_flags"].get("flare_markers") is True


@pytest.mark.anyio
async def test_space_visuals_handles_db_error(monkeypatch, client: AsyncClient):
    async def _fake_get_db():
        yield _FakeConn([], should_fail=True)

    app.dependency_overrides[get_db] = _fake_get_db

    resp = await client.get("/v1/space/visuals", headers=_auth_headers())
    body = resp.json()
    assert body["ok"] is False
    assert "failed" in (body["error"] or "")
