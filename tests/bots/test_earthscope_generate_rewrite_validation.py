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

from bots.earthscope_post.earthscope_generate import (
    _platform_caption_profile,
    _polish_public_caption,
    _select_best_rewrite_candidate,
    _validate_rewrite,
)


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


def test_validate_rewrite_rejects_directional_cme_language_without_arrival_context():
    result = _validate_rewrite(
        _rewrite_with("The sun has sent a few CME blobs our way today."),
        {"cmes_24h": 3, "flares_24h": 0},
    )

    assert result is None


def test_validate_rewrite_allows_directional_cme_language_with_arrival_context():
    result = _validate_rewrite(
        _rewrite_with("A CME arrival is possible in the next window."),
        {"cmes_24h": 3, "flares_24h": 0, "earth_directed_cme_count_72h": 1},
    )

    assert result is not None


def test_polish_public_caption_replaces_repetitive_day_feels_opener():
    caption = _polish_public_caption(
        "The day feels steady and cooperative. Use focused work blocks.",
        {"kp_max_24h": 2.0},
    )

    assert "The day feels" not in caption
    assert caption != "Use focused work blocks."


def test_polish_public_caption_avoids_recent_context_lead():
    caption = _polish_public_caption(
        "The day feels steady and cooperative. Use focused work blocks.",
        {
            "day": "2026-06-14",
            "platform": "default",
            "kp_max_24h": 2.0,
            "banned_openers": ["Use the steadier window while it is here."],
        },
    )

    assert not caption.startswith("Use the steadier window while it is here.")
    assert "The day feels" not in caption


def test_select_best_rewrite_candidate_prefers_fresh_human_hook():
    obj = {
        "candidates": [
            {
                "caption": "Use the steadier window while it is here. Keep your work simple today.",
                "snapshot": "The field looks calmer today.",
                "affects": "Some people may notice steadier focus.",
                "playbook": "- Pick one task\n- Keep caffeine earlier\n- Protect wind-down",
                "hashtags": "#GaiaEyes #SpaceWeather #HRV #Sleep #Focus #Wellness",
            },
            {
                "caption": "Need a catch-up day? The background looks more cooperative, so use it for one thing that has been waiting.",
                "snapshot": "The field looks calmer today.",
                "affects": "Some people may notice steadier focus.",
                "playbook": "- Pick one task\n- Keep caffeine earlier\n- Protect wind-down",
                "hashtags": "#GaiaEyes #SpaceWeather #HRV #Sleep #Focus #Wellness",
            },
            {
                "caption": "Geomagnetic conditions are quiet today. Maintain structured productivity.",
                "snapshot": "The field looks calmer today.",
                "affects": "Some people may notice steadier focus.",
                "playbook": "- Pick one task\n- Keep caffeine earlier\n- Protect wind-down",
                "hashtags": "#GaiaEyes #SpaceWeather #HRV #Sleep #Focus #Wellness",
            },
        ]
    }

    selected = _select_best_rewrite_candidate(
        obj,
        {"cmes_24h": 0, "flares_24h": 0, "kp_max_24h": 2.0},
        {
            "banned_openers": ["Use the steadier window while it is here."],
            "recent_captions": [],
        },
    )

    assert selected is not None
    assert selected["caption"].startswith("Need a catch-up day?")


def test_facebook_caption_profile_is_longer_than_instagram():
    fb = _platform_caption_profile("fb")
    ig = _platform_caption_profile("ig")

    assert fb["caption_words"][1] > ig["caption_words"][1]
    assert "Facebook-style mini post" in fb["caption_instruction"]
    assert "compact for Instagram" in ig["caption_instruction"]
