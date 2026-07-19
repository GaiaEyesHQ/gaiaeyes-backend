from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "post_launch_monitor.py"


def _load_module() -> object:
    spec = importlib.util.spec_from_file_location("test_post_launch_monitor_module", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.pop(spec.name, None)


def test_loads_local_dotenv_without_shell_parsing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GAIA_MONITOR_AUTH_BEARER", raising=False)
    monkeypatch.delenv("WRITE_TOKENS", raising=False)
    monkeypatch.delenv("DEV_BEARER", raising=False)
    monkeypatch.delenv("GAIA_MONITOR_DEV_USER_ID", raising=False)
    monkeypatch.delenv("GAIA_MONITOR_ADMIN_BEARER", raising=False)
    monkeypatch.delenv("GAIAEYES_API_ADMIN_BEARER", raising=False)
    monkeypatch.delenv("GAIAEYES_ADMIN_BEARER", raising=False)
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "DEV_BEARER=https://example.com/callback?x=1&y=2",
                "GAIA_MONITOR_DEV_USER_ID=user-123",
                "GAIA_MONITOR_ADMIN_BEARER=admin-token # inline comment",
            ]
        ),
        encoding="utf-8",
    )

    module = _load_module()

    assert module.AUTH_BEARER == "https://example.com/callback?x=1&y=2"
    assert module.DEV_USER_ID == "user-123"
    assert module.ADMIN_BEARER == "admin-token"


def test_does_not_override_existing_environment(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GAIA_MONITOR_AUTH_BEARER", raising=False)
    monkeypatch.delenv("WRITE_TOKENS", raising=False)
    monkeypatch.setenv("DEV_BEARER", "already-set")
    monkeypatch.delenv("GAIA_MONITOR_ADMIN_BEARER", raising=False)
    monkeypatch.delenv("GAIAEYES_API_ADMIN_BEARER", raising=False)
    monkeypatch.delenv("GAIAEYES_ADMIN_BEARER", raising=False)
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    (tmp_path / ".env").write_text("DEV_BEARER=from-dotenv\n", encoding="utf-8")

    module = _load_module()

    assert module.AUTH_BEARER == "already-set"


def test_prefers_write_tokens_and_requires_explicit_admin_token(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GAIA_MONITOR_AUTH_BEARER", raising=False)
    monkeypatch.delenv("WRITE_TOKENS", raising=False)
    monkeypatch.delenv("DEV_BEARER", raising=False)
    monkeypatch.delenv("GAIA_MONITOR_ADMIN_BEARER", raising=False)
    monkeypatch.delenv("GAIAEYES_API_ADMIN_BEARER", raising=False)
    monkeypatch.delenv("GAIAEYES_ADMIN_BEARER", raising=False)
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "WRITE_TOKENS=write-token-1,write-token-2",
                "DEV_BEARER=dev-bearer",
            ]
        ),
        encoding="utf-8",
    )

    module = _load_module()

    assert module.AUTH_BEARER == "write-token-1"
    assert module.ADMIN_BEARER == ""
