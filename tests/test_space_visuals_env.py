import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.routers.space_visuals import _media_base


def test_prefers_visuals_media_base(monkeypatch):
    monkeypatch.setenv(
        "VISUALS_MEDIA_BASE_URL",
        "https://x.supabase.co/storage/v1/object/public/space-visuals/",
    )
    monkeypatch.delenv("MEDIA_BASE_URL", raising=False)
    monkeypatch.delenv("GAIA_MEDIA_BASE", raising=False)
    assert _media_base() == "https://x.supabase.co/storage/v1/object/public/space-visuals"


def test_falls_back_to_media_base(monkeypatch):
    monkeypatch.delenv("VISUALS_MEDIA_BASE_URL", raising=False)
    monkeypatch.setenv("MEDIA_BASE_URL", "https://y.supabase.co/space-visuals/")
    assert _media_base() == "https://y.supabase.co/space-visuals"


def test_falls_back_to_gaia_media_base(monkeypatch):
    monkeypatch.delenv("VISUALS_MEDIA_BASE_URL", raising=False)
    monkeypatch.delenv("MEDIA_BASE_URL", raising=False)
    monkeypatch.setenv("GAIA_MEDIA_BASE", "https://z.supabase.co/space-visuals")
    assert _media_base() == "https://z.supabase.co/space-visuals"


def test_empty_when_none(monkeypatch):
    monkeypatch.delenv("VISUALS_MEDIA_BASE_URL", raising=False)
    monkeypatch.delenv("MEDIA_BASE_URL", raising=False)
    monkeypatch.delenv("GAIA_MEDIA_BASE", raising=False)
    assert _media_base() == ""
