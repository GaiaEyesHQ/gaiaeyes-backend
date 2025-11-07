import asyncio

import pytest
from psycopg_pool.errors import PoolTimeout


@pytest.fixture
def anyio_backend():
    return "asyncio"


class _FailContext:
    async def __aenter__(self):
        raise PoolTimeout("timeout")

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _SuccessConn:
    async def execute(self, query):  # noqa: ARG002 - interface shim
        return None


class _SuccessContext:
    async def __aenter__(self):
        return _SuccessConn()

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FailPool:
    def connection(self):
        return _FailContext()

    def get_stats(self):
        return {"pool_size": 0, "pool_available": 0, "requests_waiting": 0}


class _SuccessPool:
    def connection(self):
        return _SuccessContext()

    def get_stats(self):
        return {"pool_size": 1, "pool_available": 1, "requests_waiting": 0}


@pytest.mark.anyio
async def test_get_db_pool_timeout_triggers_failover(monkeypatch):
    from app import db

    # Reset globals to a known state for the fake pools
    db._pool = _FailPool()  # type: ignore[assignment]
    db._pool_open = True
    db._pool_conninfo_fallback = "postgresql://fallback"
    db._pool_fallback_label = "direct"
    db._pool_primary_label = "pgbouncer"
    db._pool_active_label = "pgbouncer"
    db._pool_lock = asyncio.Lock()

    failover_calls: list[str] = []

    async def _fake_activate(reason: str) -> bool:
        failover_calls.append(reason)
        db._pool = _SuccessPool()  # type: ignore[assignment]
        db._pool_open = True
        db._pool_active_label = "direct"
        return True

    monkeypatch.setattr(db, "_activate_fallback_pool", _fake_activate)

    try:
        agen = db.get_db()
        conn = await agen.__anext__()
        assert isinstance(conn, _SuccessConn)
        await agen.aclose()
    finally:
        db._pool = None
        db._pool_open = False
        db._pool_conninfo_fallback = None
        db._pool_fallback_label = None
        db._pool_active_label = "unknown"

    assert failover_calls == ["pool timeout acquiring connection"]
