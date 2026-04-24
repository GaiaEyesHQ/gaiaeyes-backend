from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import get_db, settings
from app.routers import profile


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


class _FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.last_query = ""

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, query, params=None, prepare=False):  # noqa: ARG002
        self.last_query = str(query)
        self.conn.queries.append((self.last_query, tuple(params or ())))

    async def fetchone(self):
        if "returning id, created_at" in self.last_query.lower():
            return self.conn.insert_row
        return None


class _FakeConn:
    def __init__(self):
        self.queries: list[tuple[str, tuple]] = []
        self.insert_row = {
            "id": str(uuid4()),
            "created_at": datetime(2026, 4, 24, 5, 25, tzinfo=timezone.utc),
        }
        self.commit_count = 0

    def cursor(self, *args, **kwargs):  # noqa: ARG002
        return _FakeCursor(self)

    async def commit(self):
        self.commit_count += 1


@pytest.fixture
def fake_conn():
    return _FakeConn()


@pytest.fixture
async def client(fake_conn: _FakeConn, monkeypatch):
    app = FastAPI()
    app.include_router(profile.router)

    async def _override_get_db():
        yield fake_conn

    async def _fake_table_columns(conn, schema, table):  # noqa: ARG001
        return [
            "user_id",
            "source",
            "description",
            "diagnostics_bundle",
            "created_at",
            "alert_sent",
            "alert_error",
            "alert_email_to",
            "alert_response",
        ]

    async def _fake_send_bug_report_alert(payload):  # noqa: ARG001
        return True, None, {"email_to": "help@gaiaeyes.com"}

    monkeypatch.setattr(profile, "_table_columns", _fake_table_columns)
    monkeypatch.setattr(profile, "_send_bug_report_alert", _fake_send_bug_report_alert)
    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.anyio
async def test_profile_bug_report_allows_unauthenticated_submit(
    client: AsyncClient,
    fake_conn: _FakeConn,
):
    response = await client.post(
        "/v1/profile/bug-report",
        json={
            "description": "Switched to logged-out state while using Outlook",
            "diagnostics_bundle": "bundle",
            "source": "ios_app",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True

    insert_query, insert_params = fake_conn.queries[0]
    assert "insert into app.user_bug_reports" in insert_query.lower()
    assert insert_params[0] is None
    assert insert_params[1] == "ios_app"
    assert fake_conn.commit_count == 2


@pytest.mark.anyio
async def test_profile_bug_report_uses_authenticated_user_when_present(
    client: AsyncClient,
    fake_conn: _FakeConn,
    monkeypatch,
):
    original = settings.DEV_BEARER
    settings.DEV_BEARER = "test-token"
    user_id = str(uuid4())
    try:
        response = await client.post(
            "/v1/profile/bug-report",
            headers={
                "Authorization": "Bearer test-token",
                "X-Dev-UserId": user_id,
            },
            json={
                "description": "Signed-in report",
                "diagnostics_bundle": "bundle",
                "source": "ios_app",
            },
        )
    finally:
        settings.DEV_BEARER = original

    assert response.status_code == 200
    insert_query, insert_params = fake_conn.queries[0]
    assert "insert into app.user_bug_reports" in insert_query.lower()
    assert insert_params[0] == user_id
