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
    _caption_context_lead,
    _clean_llm_title,
    _fallback_social_title,
    _finalize_rewrite_payload,
    _normalize_rewrite_payload,
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
        "playbook": "- Keep the day simple\n- Protect evening routine",
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
        _rewrite_with("A CME arrival is possible in the next day."),
        {"cmes_24h": 3, "flares_24h": 0, "earth_directed_cme_count_72h": 1},
    )

    assert result is not None


def test_validate_rewrite_rejects_typo_and_report_phrasing():
    result = _validate_rewrite(
        {
            "caption": "Neutral energy. You set the pace. The near-Earth field is quiet today.",
            "snapshot": "The field looks quieter today.",
            "affects": "Attention may come in usable blocs with small dips.",
            "playbook": "- Keep the day simple\n- Protect evening routine",
            "hashtags": "#GaiaEyes #SpaceWeather",
        },
        {"cmes_24h": 0, "flares_24h": 0},
    )

    assert result is None


def test_normalize_rewrite_payload_accepts_list_playbook():
    normalized = _normalize_rewrite_payload(
        {
            "caption": "Quiet backdrop today.",
            "snapshot": "The field looks calmer today.",
            "affects": "Focus may feel steady for some sensitive systems.",
            "playbook": ["Pick one task", "Keep caffeine earlier", "Protect evening routine"],
            "hashtags": "#GaiaEyes #SpaceWeather",
        }
    )

    assert normalized["playbook"] == "Pick one task\nKeep caffeine earlier\nProtect evening routine"
    assert _validate_rewrite(normalized, {"cmes_24h": 0, "flares_24h": 0}) is not None


def test_finalize_rewrite_payload_normalizes_playbook_bullets():
    finalized = _finalize_rewrite_payload(
        {
            "caption": "Keep the day simple.",
            "snapshot": "The field looks calmer today.",
            "affects": "Focus may feel steady for some sensitive systems.",
            "playbook": "Pick one task\n2. Keep caffeine earlier\n• Protect evening routine",
            "hashtags": "#GaiaEyes #SpaceWeather",
        }
    )

    assert finalized["playbook"] == "- Pick one task\n- Keep caffeine earlier\n- Protect evening routine"


def test_validate_rewrite_rejects_awkward_event_synonyms_and_brand_signoff():
    result = _validate_rewrite(
        {
            "caption": "You may notice steadier attention and fewer abrupt shifts today.",
            "snapshot": "A slight southward tilt nudged a single small flare through the last day. No recent coronal expulsions have been reported.",
            "affects": "Focus may feel steady for some sensitive systems.",
            "playbook": "- Keep the day simple\n- Gaia Eyes: treat today like a steady gear.",
            "hashtags": "#GaiaEyes #SpaceWeather",
        },
        {"cmes_24h": 0, "flares_24h": 1},
    )

    assert result is None


def test_clean_llm_title_accepts_fresh_human_hook():
    title = _clean_llm_title("Brain Tabs Closing", {"quiet skies", "clear runway"})

    assert title == "Brain Tabs Closing"


def test_clean_llm_title_rejects_generic_or_recent_fallback_labels():
    assert _clean_llm_title("Clear Runway", set()) is None
    assert _clean_llm_title("Quiet Skies", set()) is None
    assert _clean_llm_title("Magnetic Calm", set()) is None
    assert _clean_llm_title("Geomagnetic Storm Watch", set()) is None
    assert _clean_llm_title("Brain Tabs Closing", {"brain tabs closing"}) is None


def test_clean_llm_title_does_not_hard_reject_style_guidance_terms():
    assert _clean_llm_title("Sleep Gets A Softer Window", set()) == "Sleep Gets A Softer Window"
    assert _clean_llm_title("Ready For Easier Wind-Down", set()) == "Ready For Easier Wind-Down"


def test_validate_rewrite_keeps_style_guidance_out_of_validator():
    result = _validate_rewrite(
        _rewrite_with("Sleep gets a softer window today."),
        {"cmes_24h": 0, "flares_24h": 0},
    )

    assert result is not None


def test_fallback_social_title_replaces_generic_report_label():
    title = _fallback_social_title(
        {"day": "2026-07-02", "platform": "default", "kp_max_24h": 2.0},
        "Magnetic Calm",
        {"clear runway", "magnetic calm", "quiet skies"},
    )

    assert title not in {"Clear Runway", "Magnetic Calm", "Quiet Skies"}
    assert _clean_llm_title(title, {"clear runway", "magnetic calm", "quiet skies"}) == title


def test_fallback_social_title_uses_symptom_pattern_language():
    title = _fallback_social_title(
        {"day": "2026-07-04", "platform": "default", "kp_max_24h": 5.7},
        "Active Geomagnetics",
        {"active geomagnetics", "clear runway", "quiet skies"},
    )

    assert any(
        term in title.lower()
        for term in ("pain", "body", "recovery", "migraine", "sleep")
    )


def test_caption_context_lead_stays_symptom_based_for_calm_days():
    lead = _caption_context_lead(
        {
            "day": "2026-07-04",
            "platform": "default",
            "kp_max_24h": 1.7,
            "bz_min": 0.3,
        }
    )

    assert any(
        term in lead.lower()
        for term in ("recovery", "sleep", "body", "symptoms", "wearable", "pain", "pressure", "mood")
    )
    assert "catch up" not in lead.lower()
    assert "focus" not in lead.lower()


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
                "playbook": "- Pick one task\n- Keep caffeine earlier\n- Protect evening routine",
                "hashtags": "#GaiaEyes #SpaceWeather #HRV #Sleep #Focus #Wellness",
            },
            {
                "caption": "Need a catch-up day? The background looks more cooperative, so use it for one thing that has been waiting.",
                "snapshot": "The field looks calmer today.",
                "affects": "Some people may notice steadier focus.",
                "playbook": "- Pick one task\n- Keep caffeine earlier\n- Protect evening routine",
                "hashtags": "#GaiaEyes #SpaceWeather #HRV #Sleep #Focus #Wellness",
            },
            {
                "caption": "Geomagnetic conditions are quiet today. Maintain structured productivity.",
                "snapshot": "The field looks calmer today.",
                "affects": "Some people may notice steadier focus.",
                "playbook": "- Pick one task\n- Keep caffeine earlier\n- Protect evening routine",
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


def test_select_best_rewrite_candidate_prefers_body_hook_over_productivity_hook():
    obj = {
        "candidates": [
            {
                "caption": "Good day for focused work blocks. Keep your plan simple and take breaks.",
                "snapshot": "The field looks calmer today.",
                "affects": "Some people may notice steadier focus.",
                "playbook": "- Pick one task\n- Keep caffeine earlier\n- Protect evening routine",
                "hashtags": "#GaiaEyes #SpaceWeather #HRV #Sleep #Focus #Wellness",
            },
            {
                "caption": "Head feel a little clearer today? The quieter signal mix may support steadier pacing without pushing.",
                "snapshot": "The field looks calmer today.",
                "affects": "Some people may notice steadier focus.",
                "playbook": "- Pick one task\n- Keep caffeine earlier\n- Protect evening routine",
                "hashtags": "#GaiaEyes #SpaceWeather #HRV #Sleep #Focus #Wellness",
            },
        ]
    }

    selected = _select_best_rewrite_candidate(
        obj,
        {"cmes_24h": 0, "flares_24h": 0, "kp_max_24h": 2.0},
        {"banned_openers": [], "recent_captions": []},
    )

    assert selected is not None
    assert selected["caption"].startswith("Head feel a little clearer today?")


def test_select_best_rewrite_candidate_prefers_wearable_symptom_hook_over_catchup():
    obj = {
        "candidates": [
            {
                "caption": "Good day to catch up gently. Keep your plan simple and take breaks.",
                "snapshot": "The field looks calmer today.",
                "affects": "Some people may notice steadier recovery.",
                "playbook": "- Pick one task\n- Keep caffeine earlier\n- Protect evening routine",
                "hashtags": "#GaiaEyes #SpaceWeather #HRV #Sleep #Focus #Wellness",
            },
            {
                "caption": "Wearable trends may be easier to read today. The quieter backdrop gives sleep, pressure, and recovery patterns a cleaner comparison point.",
                "snapshot": "The field looks calmer today.",
                "affects": "Some people may notice steadier recovery.",
                "playbook": "- Pick one task\n- Keep caffeine earlier\n- Protect evening routine",
                "hashtags": "#GaiaEyes #SpaceWeather #HRV #Sleep #Focus #Wellness",
            },
        ]
    }

    selected = _select_best_rewrite_candidate(
        obj,
        {"cmes_24h": 0, "flares_24h": 0, "kp_max_24h": 2.0},
        {"banned_openers": [], "recent_captions": []},
    )

    assert selected is not None
    assert selected["caption"].startswith("Wearable trends")


def test_facebook_caption_profile_is_longer_than_instagram():
    fb = _platform_caption_profile("fb")
    ig = _platform_caption_profile("ig")

    assert fb["caption_words"][1] > ig["caption_words"][1]
    assert "Facebook-style mini post" in fb["caption_instruction"]
    assert "compact for Instagram" in ig["caption_instruction"]
