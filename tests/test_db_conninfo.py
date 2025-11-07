from pathlib import Path
import sys
from urllib.parse import urlparse

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import db


def _reset_pool_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(db, "_pool_conninfo_primary", None)
    monkeypatch.setattr(db, "_pool_conninfo_fallback", None)
    monkeypatch.setattr(db, "_pool_primary_label", "unknown")
    monkeypatch.setattr(db, "_pool_fallback_label", None)
    monkeypatch.setattr(db, "_pool_active_label", "unknown")


def test_prepare_conninfo_no_explicit_pgbouncer(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_pool_state(monkeypatch)

    monkeypatch.setattr(
        db.settings,
        "DATABASE_URL",
        "postgresql://user:pass@db.example.com:6543/postgres?sslmode=require",
    )
    monkeypatch.setattr(db.settings, "DIRECT_URL", None)

    db._prepare_conninfo()

    assert db._pool_primary_label == "direct"
    assert db._pool_active_label == "direct"
    assert db._pool_conninfo_primary.endswith(":6543/postgres?sslmode=require")

    # Without an explicit DIRECT_URL we should not fabricate a fallback.
    assert db._pool_fallback_label is None
    assert db._pool_conninfo_fallback is None


def test_prepare_conninfo_pgbouncer_with_direct_url(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_pool_state(monkeypatch)

    monkeypatch.setattr(
        db.settings,
        "DATABASE_URL",
        "postgresql://user:pass@db.example.com:6543/postgres?sslmode=require&pgbouncer=true",
    )
    monkeypatch.setattr(
        db.settings,
        "DIRECT_URL",
        "postgresql://user:pass@db-primary.example.com:5432/postgres?sslmode=require",
    )

    db._prepare_conninfo()

    assert db._pool_primary_label == "pgbouncer"
    assert db._pool_active_label == "pgbouncer"
    assert db._pool_conninfo_primary.endswith(":6543/postgres?sslmode=require")

    assert db._pool_fallback_label == "direct"
    assert db._pool_conninfo_fallback is not None
    parsed = urlparse(db._pool_conninfo_fallback)
    assert parsed.port == 5432
    assert parsed.hostname == "db-primary.example.com"


def test_prepare_conninfo_pgbouncer_without_direct_url(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_pool_state(monkeypatch)

    monkeypatch.setattr(
        db.settings,
        "DATABASE_URL",
        "postgresql://user:pass@db.example.com/postgres?sslmode=require&pgbouncer=true",
    )
    monkeypatch.setattr(db.settings, "DIRECT_URL", None)

    db._prepare_conninfo()

    assert db._pool_primary_label == "pgbouncer"
    assert db._pool_active_label == "pgbouncer"
    assert db._pool_conninfo_primary.endswith(":6543/postgres?sslmode=require")

    # With pgBouncer enabled and no explicit direct DSN we must not fabricate a fallback.
    assert db._pool_fallback_label is None
    assert db._pool_conninfo_fallback is None
