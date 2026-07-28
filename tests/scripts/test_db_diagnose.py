from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "db_diagnose.py"


def _load_module() -> object:
    spec = importlib.util.spec_from_file_location("test_db_diagnose_module", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.pop(spec.name, None)


def test_loads_from_arbitrary_cwd_when_database_url_is_set(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/postgres?sslmode=require")

    module = _load_module()

    assert callable(module.main)
