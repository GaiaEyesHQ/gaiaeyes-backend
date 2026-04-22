from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "postgresql://localhost/test")

from app.routers import profile


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.rowcount = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, query, params=None, prepare=False):  # noqa: ARG002
        self.conn.queries.append((str(query), params))
        index = len(self.conn.queries) - 1
        if index < len(self.conn.rowcounts):
            self.rowcount = self.conn.rowcounts[index]
        else:
            self.rowcount = 0


class FakeConn:
    def __init__(self, rowcounts: list[int]):
        self.rowcounts = rowcounts
        self.queries: list[tuple[str, list[object] | tuple[object, ...] | None]] = []

    def cursor(self, row_factory=None):  # noqa: ARG002
        return FakeCursor(self)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_profile_location_upsert_preserves_existing_coordinates_for_same_zip(monkeypatch):
    existing_row = {
        "zip": "76541",
        "lat": 31.1164,
        "lon": -97.7278,
        "use_gps": False,
        "local_insights_enabled": True,
    }
    conn = FakeConn(rowcounts=[1])
    request = SimpleNamespace(state=SimpleNamespace(user_id="967d5ecf-17c1-4901-8bbd-5bfb3621e9d0"))

    async def _fake_columns(_conn, schema: str, table: str):  # noqa: ARG001
        if (schema, table) == ("app", "user_locations"):
            return [
                "user_id",
                "zip",
                "lat",
                "lon",
                "is_primary",
                "use_gps",
                "local_insights_enabled",
                "updated_at",
                "created_at",
            ]
        return []

    fetch_calls = 0

    async def _fake_fetch_location_row(_conn, user_id: str):  # noqa: ARG001
        nonlocal fetch_calls
        fetch_calls += 1
        return existing_row

    monkeypatch.setattr(profile, "_table_columns", _fake_columns)
    monkeypatch.setattr(profile, "_fetch_location_row", _fake_fetch_location_row)

    result = await profile.profile_location_upsert(
        profile.ProfileLocationIn(zip="76541", use_gps=False, local_insights_enabled=True),
        request,
        conn=conn,
    )

    assert result["ok"] is True
    assert fetch_calls == 2
    assert conn.queries
    update_query, update_params = conn.queries[0]
    assert "update" in update_query.lower()
    assert 31.1164 in update_params
    assert -97.7278 in update_params
    assert result["location"]["lat"] == 31.1164
    assert result["location"]["lon"] == -97.7278


@pytest.mark.anyio
async def test_profile_location_upsert_geocodes_zip_when_inserting_without_coordinates(monkeypatch):
    inserted_row = {
        "zip": "76541",
        "lat": 31.1164,
        "lon": -97.7278,
        "use_gps": False,
        "local_insights_enabled": True,
    }
    conn = FakeConn(rowcounts=[0, 1])
    request = SimpleNamespace(state=SimpleNamespace(user_id="967d5ecf-17c1-4901-8bbd-5bfb3621e9d0"))

    async def _fake_columns(_conn, schema: str, table: str):  # noqa: ARG001
        if (schema, table) == ("app", "user_locations"):
            return [
                "user_id",
                "zip",
                "lat",
                "lon",
                "is_primary",
                "use_gps",
                "local_insights_enabled",
                "updated_at",
                "created_at",
                "label",
            ]
        return []

    fetch_responses = [None, inserted_row]

    async def _fake_fetch_location_row(_conn, user_id: str):  # noqa: ARG001
        return fetch_responses.pop(0)

    async def _fake_to_thread(fn, *args, **kwargs):  # noqa: ARG001
        assert args == ("76541",)
        return (31.1164, -97.7278)

    monkeypatch.setattr(profile, "_table_columns", _fake_columns)
    monkeypatch.setattr(profile, "_fetch_location_row", _fake_fetch_location_row)
    monkeypatch.setattr(profile.asyncio, "to_thread", _fake_to_thread)

    result = await profile.profile_location_upsert(
        profile.ProfileLocationIn(zip="76541", use_gps=False, local_insights_enabled=True),
        request,
        conn=conn,
    )

    assert result["ok"] is True
    assert len(conn.queries) == 2
    insert_query, insert_params = conn.queries[1]
    assert "insert into" in insert_query.lower()
    assert 31.1164 in insert_params
    assert -97.7278 in insert_params
    assert result["location"]["lat"] == 31.1164
    assert result["location"]["lon"] == -97.7278
