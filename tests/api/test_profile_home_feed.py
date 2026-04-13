from __future__ import annotations

import sys
import os
import types
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import jwt
import pytest
from httpx import ASGITransport, AsyncClient

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# app.main imports the billing router, which imports stripe. These tests do not
# exercise billing, so provide the minimum import-time surface when the optional
# Stripe package is not installed in the local test venv.
sys.modules.setdefault(
    "stripe",
    types.SimpleNamespace(
        Customer=types.SimpleNamespace(create=lambda **_: types.SimpleNamespace(id="cus_test")),
        checkout=types.SimpleNamespace(Session=types.SimpleNamespace(create=lambda **_: None)),
        error=types.SimpleNamespace(StripeError=Exception),
        api_key="",
    ),
)
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost:5432/gaiaeyes_test")

from app.db import get_db
from app.main import app
from app.routers import profile as profile_router


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.last_query = ""

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, query, params=None, prepare=False):  # noqa: ARG002
        self.last_query = str(query)
        self.conn.queries.append((self.last_query, params))

    async def fetchone(self):
        if "seen_at::date = current_date" in self.last_query:
            return self.conn.seen_today_row
        if "from content.home_feed_items" in self.last_query:
            return self.conn.item_row
        if "returning seen_at, dismissed_at" in self.last_query:
            return self.conn.seen_response_row
        return None


class FakeConn:
    def __init__(self):
        self.queries = []
        self.committed = False
        self.seen_today_row = None
        self.item_row = None
        self.seen_response_row = {
            "seen_at": datetime(2026, 4, 13, 12, 0, tzinfo=timezone.utc),
            "dismissed_at": None,
        }

    def cursor(self, row_factory=None):  # noqa: ARG002
        return FakeCursor(self)

    async def commit(self):
        self.committed = True


@pytest.fixture(autouse=True)
def override_dev_bearer():
    from app import db

    original = db.settings.DEV_BEARER
    db.settings.DEV_BEARER = "test-token"
    try:
        yield
    finally:
        db.settings.DEV_BEARER = original


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def fake_conn(monkeypatch):
    conn = FakeConn()

    async def _fake_db():
        yield conn

    async def _ready(_conn):  # noqa: ARG001
        return True

    app.dependency_overrides[get_db] = _fake_db
    monkeypatch.setattr(profile_router, "_home_feed_tables_ready", _ready)
    try:
        yield conn
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.anyio
async def test_profile_home_feed_returns_unseen_mode_item(client: AsyncClient, fake_conn: FakeConn):
    item_id = uuid4()
    fake_conn.item_row = {
        "id": str(item_id),
        "slug": "mystical-test",
        "mode": "mystical",
        "kind": "message",
        "title": "Listen softly",
        "body": "A short test message.",
        "link_label": None,
        "link_url": None,
        "updated_at": datetime(2026, 4, 13, 11, 0, tzinfo=timezone.utc),
    }
    headers = {"Authorization": "Bearer test-token", "X-Dev-UserId": str(uuid4())}

    response = await client.get("/v1/profile/home-feed?mode=mystical", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["item"]["id"] == str(item_id)
    assert payload["item"]["title"] == "Listen softly"
    item_query = next(query for query in fake_conn.queries if "from content.home_feed_items" in query[0])
    assert item_query[1][0] == "mystical"


@pytest.mark.anyio
async def test_profile_home_feed_returns_seen_today_when_not_dismissed(client: AsyncClient, fake_conn: FakeConn):
    item_id = uuid4()
    fake_conn.seen_today_row = {
        "id": str(item_id),
        "slug": "scientific-seen-test",
        "mode": "scientific",
        "kind": "fact",
        "title": "Already seen",
        "body": "Keep showing this until it is dismissed.",
        "link_label": None,
        "link_url": None,
        "updated_at": datetime(2026, 4, 13, 11, 0, tzinfo=timezone.utc),
        "dismissed_at": None,
    }
    headers = {"Authorization": "Bearer test-token", "X-Dev-UserId": str(uuid4())}

    response = await client.get("/v1/profile/home-feed?mode=scientific", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["item"]["id"] == str(item_id)
    assert payload["item"]["title"] == "Already seen"
    assert payload["reason"] == "seen_today"
    assert not any(
        "from content.home_feed_items item" in query and "not exists" in query
        for query, _ in fake_conn.queries
    )


@pytest.mark.anyio
async def test_profile_home_feed_hides_after_dismissed_today(client: AsyncClient, fake_conn: FakeConn):
    fake_conn.seen_today_row = {
        "id": str(uuid4()),
        "slug": "scientific-dismissed-test",
        "mode": "scientific",
        "kind": "fact",
        "title": "Dismissed",
        "body": "This should stay hidden for today.",
        "link_label": None,
        "link_url": None,
        "updated_at": datetime(2026, 4, 13, 11, 0, tzinfo=timezone.utc),
        "dismissed_at": datetime(2026, 4, 13, 12, 0, tzinfo=timezone.utc),
    }
    headers = {"Authorization": "Bearer test-token", "X-Dev-UserId": str(uuid4())}

    response = await client.get("/v1/profile/home-feed?mode=scientific", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["item"] is None
    assert payload["reason"] == "dismissed_today"
    assert not any(
        "from content.home_feed_items item" in query and "not exists" in query
        for query, _ in fake_conn.queries
    )


@pytest.mark.anyio
async def test_profile_home_feed_public_read_keeps_authenticated_user(
    client: AsyncClient,
    fake_conn: FakeConn,
    monkeypatch,
):
    from app import db
    from app.security import auth as security_auth

    user_id = uuid4()
    item_id = uuid4()
    fake_conn.item_row = {
        "id": str(item_id),
        "slug": "scientific-test",
        "mode": "scientific",
        "kind": "fact",
        "title": "Context first",
        "body": "A short test fact.",
        "link_label": None,
        "link_url": None,
        "updated_at": datetime(2026, 4, 13, 11, 0, tzinfo=timezone.utc),
    }
    monkeypatch.setattr(security_auth, "PUBLIC_READ_ENABLED", True)
    monkeypatch.setattr(security_auth, "PUBLIC_READ_PATHS", ["/v1/profile"])
    monkeypatch.setattr(db.settings, "SUPABASE_JWT_SECRET", "test-secret")
    token = jwt.encode({"sub": str(user_id)}, "test-secret", algorithm="HS256")

    response = await client.get(
        "/v1/profile/home-feed?mode=scientific",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["item"]["id"] == str(item_id)
    seen_query = next(query for query in fake_conn.queries if "seen_at::date = current_date" in query[0])
    item_query = next(query for query in fake_conn.queries if "from content.home_feed_items" in query[0])
    assert seen_query[1][0] == str(user_id)
    assert item_query[1][1] == str(user_id)


@pytest.mark.anyio
async def test_profile_home_feed_public_read_without_user_is_unauthorized(
    client: AsyncClient,
    fake_conn: FakeConn,
    monkeypatch,
):
    from app.security import auth as security_auth

    monkeypatch.setattr(security_auth, "PUBLIC_READ_ENABLED", True)
    monkeypatch.setattr(security_auth, "PUBLIC_READ_PATHS", ["/v1/profile"])

    response = await client.get("/v1/profile/home-feed?mode=scientific")

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing or invalid Authorization header"
    assert fake_conn.queries == []


@pytest.mark.anyio
async def test_profile_home_feed_seen_records_item(client: AsyncClient, fake_conn: FakeConn):
    item_id = uuid4()
    headers = {"Authorization": "Bearer test-token", "X-Dev-UserId": str(uuid4())}

    response = await client.post(
        "/v1/profile/home-feed/seen",
        json={"item_id": str(item_id), "dismissed": True},
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["seen"] is True
    assert payload["item_id"] == str(item_id)
    assert fake_conn.committed is True
    insert_query = next(query for query in fake_conn.queries if "insert into content.user_home_feed_seen" in query[0])
    assert insert_query[1][1] == str(item_id)
    assert insert_query[1][2] is True
