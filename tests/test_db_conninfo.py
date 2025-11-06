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


def test_prepare_conninfo_infers_pgbouncer_port(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_pool_state(monkeypatch)

    monkeypatch.setattr(
        db.settings,
        "DATABASE_URL",
        "postgresql://user:pass@db.example.com:6543/postgres?sslmode=require",
    )
    monkeypatch.setattr(db.settings, "DIRECT_URL", None)

    db._prepare_conninfo()

    assert db._pool_primary_label == "pgbouncer"
    assert db._pool_active_label == "pgbouncer"
    assert db._pool_conninfo_primary.endswith(":6543/postgres?sslmode=require")

    # The fallback should automatically target the direct Postgres port.
    assert db._pool_fallback_label == "direct"
    assert db._pool_conninfo_fallback is not None
    parsed = urlparse(db._pool_conninfo_fallback)
    assert parsed.port == 5432
    assert parsed.hostname == "db.example.com"
