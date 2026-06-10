import sys
import types
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

supabase_stub = types.ModuleType("supabase")
supabase_stub.create_client = lambda *_, **__: object()
sys.modules.setdefault("supabase", supabase_stub)
os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-key")

from bots.earthscope_post.earthscope_generate import _polish_public_caption, _validate_rewrite


def _rewrite_with(text: str) -> dict[str, str]:
    return {
        "caption": "Quiet backdrop today.",
        "snapshot": text,
        "affects": "Focus and sleep may feel steadier for some sensitive systems.",
        "playbook": "- Keep the day simple\n- Protect wind-down",
        "hashtags": "#GaiaEyes #SpaceWeather",
    }


def test_validate_rewrite_allows_no_cme_absence_language():
    result = _validate_rewrite(
        _rewrite_with("No CME activity is adding extra noise today."),
        {"cmes_24h": 0, "flares_24h": 0},
    )

    assert result is not None


def test_validate_rewrite_rejects_unsupported_positive_cme_language():
    result = _validate_rewrite(
        _rewrite_with("Recent CME activity is adding extra noise today."),
        {"cmes_24h": 0, "flares_24h": 0},
    )

    assert result is None


def test_polish_public_caption_replaces_repetitive_day_feels_opener():
    caption = _polish_public_caption(
        "The day feels steady and cooperative. Use focused work blocks.",
        {"kp_max_24h": 2.0},
    )

    assert caption.startswith("Use the steadier window while it is here.")
    assert "The day feels" not in caption
