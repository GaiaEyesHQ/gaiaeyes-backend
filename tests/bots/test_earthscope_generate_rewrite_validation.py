import sys
import types
import os
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

supabase_stub = types.ModuleType("supabase")
supabase_stub.create_client = lambda *_, **__: object()
sys.modules.setdefault("supabase", supabase_stub)
os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-key")

from bots.earthscope_post import earthscope_generate
from bots.earthscope_post.earthscope_generate import (
    _build_social_caption_variants,
    _build_reel_story,
    _build_reel_voiceover_text,
    _caption_context_lead,
    _canonical_public_platform,
    _clean_llm_title,
    _fallback_social_title,
    _finalize_rewrite_payload,
    _preferred_hook_lanes,
    _normalize_rewrite_payload,
    _platform_caption_profile,
    _polish_public_caption,
    _select_best_rewrite_candidate,
    _validate_rewrite,
    _voiceover_caption_from_variants,
    _rewrite_facebook_caption_from_spine,
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
    assert _clean_llm_title("High-Speed Solar Wind", set()) is None
    assert _clean_llm_title("Track The Overlap", set()) is None
    assert _clean_llm_title("Mood Sleep Pressure Check", set()) is None
    assert _clean_llm_title("Wearable Trends Need Context", set()) is None
    assert _clean_llm_title("Check The Body Pattern", set()) is None
    assert _clean_llm_title("Sensitive Systems Take Note", set()) is None
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


def test_title_cleaner_rejects_vague_running_loud_hook():
    assert _clean_llm_title("Is Your Body Running Loud?", set()) is None


def test_fallback_social_title_replaces_running_loud_default():
    title = _fallback_social_title(
        {"day": "2026-07-11", "platform": "default", "kp_max_24h": 4.3},
        "Is Your Body Running Loud?",
        {"is your body running loud"},
    )

    assert "running loud" not in title.lower()
    assert _clean_llm_title(title, {"is your body running loud"}) == title


def test_fallback_social_title_follows_caption_hook_lane():
    title = _fallback_social_title(
        {"day": "2026-07-12", "platform": "default", "kp_max_24h": 3.8},
        "Magnetic Calm",
        {"magnetic calm", "head pressure asking for space"},
        hook_text="Body buzzed and wired for no reason? Like an over-caffeinated squirrel.",
    )

    lowered = title.lower()
    assert any(term in lowered for term in ("buzz", "jittery", "squirrely", "wired"))
    assert "head pressure" not in lowered
    assert "asking for space" not in lowered


def test_fallback_social_title_uses_symptom_pattern_language():
    title = _fallback_social_title(
        {"day": "2026-07-04", "platform": "default", "kp_max_24h": 5.7},
        "Active Geomagnetics",
        {"active geomagnetics", "clear runway", "quiet skies"},
    )

    assert any(
        term in title.lower()
        for term in ("pain", "body", "energy", "migraine", "sleep")
    )


def test_fallback_social_title_uses_emotional_hooks_not_dashboard_labels():
    blocked = {
        "track the overlap",
        "mood sleep pressure check",
        "wearable trends need context",
        "check the body pattern",
    }

    for tone_ctx in (
        {"day": "2026-07-10", "platform": "default", "kp_max_24h": 2.0},
        {"day": "2026-07-11", "platform": "default", "kp_max_24h": 3.8},
        {"day": "2026-07-12", "platform": "default", "kp_max_24h": 5.8},
        {"day": "2026-07-13", "platform": "default"},
    ):
        title = _fallback_social_title(tone_ctx, "Track The Overlap", blocked)
        lowered = title.lower()

        assert lowered not in blocked
        assert _clean_llm_title(title, blocked) == title
        assert any(
            marker in lowered
            for marker in ("?", "body", "sleep", "energy", "pain", "brain fog", "mood")
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


def test_preferred_hook_lanes_do_not_overlearn_recent_sleep_hook():
    lanes = _preferred_hook_lanes(
        {
            "day": "2026-07-12",
            "platform": "fb",
            "kp_max_24h": 4.7,
            "bz_min": -7.2,
            "solar_wind_kms": 560,
            "flares_24h": 2,
            "cmes_24h": 3,
            "recent_captions": [
                "Can't sleep even when your bed is perfect? Keep the evening softer.",
                "Can't sleep but your mind is oddly jumpy? Try a slower night.",
            ],
        }
    )

    assert lanes[0] != "sleep"
    assert any(lane in lanes[:2] for lane in ("wired_tired", "brain_fog", "head_pressure", "energy"))


def test_hook_lanes_include_migraine_and_chronic_flare_days():
    migraine_lanes = _preferred_hook_lanes(
        {
            "day": "2026-07-12",
            "platform": "default",
            "kp_max_24h": 4.8,
            "bz_min": -8.0,
            "affects": "Migraine and headache thresholds may feel lower for some people.",
            "recent_captions": [],
        }
    )
    flare_lanes = _preferred_hook_lanes(
        {
            "day": "2026-07-12",
            "platform": "default",
            "kp_max_24h": 4.8,
            "bz_min": -7.0,
            "flares_24h": 3,
            "affects": "Chronic illness flare patterns and symptom flares may run louder.",
            "recent_captions": [],
        }
    )

    assert "migraine_headache" in migraine_lanes[:2]
    assert "chronic_flare" in flare_lanes[:2]


def test_select_best_rewrite_candidate_uses_non_sleep_lane_when_sleep_recent():
    obj = {
        "candidates": [
            {
                "caption": "Can't sleep even when your body is tired? Keep the night simple.",
                "snapshot": "The field feels a little unsettled today.",
                "affects": "Some people may notice jittery energy.",
                "playbook": "- Take slow breaths\n- Keep the day simple",
                "hashtags": "#GaiaEyes #SpaceWeather",
                "voiceover": "Can't sleep even when your body is tired? Take slow breaths.",
            },
            {
                "caption": "Body buzzing for no clear reason? The signal mix is a little restless, so keep your pace gentle.",
                "snapshot": "The field feels a little unsettled today.",
                "affects": "Some people may notice jittery energy.",
                "playbook": "- Take slow breaths\n- Keep the day simple",
                "hashtags": "#GaiaEyes #SpaceWeather",
                "voiceover": "Body buzzing for no clear reason? Take slow breaths.",
            },
        ]
    }

    selected = _select_best_rewrite_candidate(
        obj,
        {"cmes_24h": 1, "flares_24h": 1, "kp_max_24h": 4.5, "bz_min": -7},
        {
            "kp_max_24h": 4.5,
            "bz_min": -7,
            "flares_24h": 1,
            "cmes_24h": 1,
            "recent_captions": ["Can't sleep even when your bed is perfect? Keep the evening softer."],
            "banned_openers": [],
        },
    )

    assert selected is not None
    assert selected["caption"].startswith("Body buzzing")
    assert selected["voiceover"].startswith("Body buzzing")


def test_reel_voiceover_fallback_starts_with_emotional_title_not_action_caption():
    voiceover = _build_reel_voiceover_text(
        ctx={"kp_max_24h": 4.5, "bz_min": -7},
        title="Body Buzzing For No Reason?",
        caption="Take short movement breaks and sip water today. Keep the day simple when your body feels keyed up.",
        snapshot="Solar wind is elevated today. Magnetic conditions are shifting.",
        affects="Some people may notice restless energy or trouble settling.",
        playbook="- Do 3 minutes of easy movement\n- Sip water",
        rewrite=None,
    )

    assert voiceover.startswith("Body Buzzing For No Reason?")
    assert "Solar wind is elevated today." in voiceover
    assert "restless energy" in voiceover
    assert "Do 3 minutes" not in voiceover
    assert "Follow Gaia Eyes" not in voiceover
    assert "download the app" not in voiceover


def test_voiceover_caption_source_prefers_facebook_variant():
    caption = _voiceover_caption_from_variants(
        {
            "default": {"caption": "IG caption first paragraph."},
            "fb": {"caption": "Facebook caption first paragraph.\n\nMore Facebook context."},
        },
        "Default caption first paragraph.",
    )

    assert caption == "Facebook caption first paragraph.\n\nMore Facebook context."


def test_reel_voiceover_uses_long_explicit_script_when_available():
    voiceover = _build_reel_voiceover_text(
        ctx={"kp_max_24h": 4.5, "bz_min": -7},
        title="Body Buzzing For No Reason?",
        caption="Take short movement breaks and sip water today.",
        snapshot="Solar wind is elevated today.",
        affects="Some people may notice restless energy.",
        playbook="- Do 3 minutes of easy movement",
        rewrite={
            "voiceover": (
                "Body buzzing for no clear reason? Solar wind is elevated today, and magnetic conditions have been shifting. "
                "Some sensitive people notice days like this as restless energy, trouble settling, or energy that spikes and dips before easing again."
            )
        },
    )

    assert voiceover == (
        "Body buzzing for no clear reason? Solar wind is elevated today, and magnetic conditions have been shifting. "
        "Some sensitive people notice days like this as restless energy, trouble settling, or energy that spikes and dips before easing again."
    )


def test_facebook_caption_profile_is_longer_than_instagram():
    fb = _platform_caption_profile("fb")
    ig = _platform_caption_profile("ig")

    assert fb["caption_words"][1] > ig["caption_words"][1]
    assert "Facebook-style mini post" in fb["caption_instruction"]
    assert "compact for Instagram" in ig["caption_instruction"]
    assert fb["caption_words"] == [70, 120]
    assert "audience question" in fb["caption_instruction"]


def test_public_generation_uses_one_canonical_platform():
    assert _canonical_public_platform("default") == "default"
    assert _canonical_public_platform("ig") == "default"


def test_reel_story_uses_writer_fields_without_changing_web_sections():
    story = _build_reel_story(
        title="Body buzzing for no clear reason?",
        snapshot="Solar wind is elevated today.",
        affects="Some people may feel restless. Energy may spike and dip.",
        voiceover="Body buzzing for no clear reason? Solar wind is elevated today.",
        rewrite={
            "reel_signal": "Solar wind is elevated",
            "reel_effects": "Restless or jittery\nEnergy may spike, then dip",
            "reel_pattern": "An uneven-energy day",
        },
    )

    assert story["signal"] == "Solar wind is elevated"
    assert story["effects"].splitlines() == ["Restless or jittery", "Energy may spike, then dip"]
    assert story["pattern"] == "An uneven-energy day"


def test_reel_voiceover_keeps_hook_signal_and_effect_without_tip():
    voiceover = _build_reel_voiceover_text(
        ctx={"kp_max_24h": 2.0, "bz_min": -4.8},
        title="Body Buzzing For No Clear Reason?",
        caption=(
            "Body buzzing for no clear reason? That jittery wired-but-tired feeling can make small tasks feel draining. "
            "This extra sentence should not make the reel drag into a long Facebook-style read."
        ),
        snapshot="Solar wind is elevated today. Magnetic conditions are shifting.",
        affects="Some people may notice restless energy or energy that spikes and dips.",
        playbook="- Take three slow breaths before pushing through\n- Lower screen brightness",
        rewrite=None,
    )

    assert voiceover.startswith("Body buzzing for no clear reason?")
    assert "Solar wind is elevated today." in voiceover
    assert "slow breaths" not in voiceover
    assert len(voiceover.split()) <= 60


def test_facebook_caption_rewrite_receives_finished_content_spine(monkeypatch):
    captured = {}

    def fake_chat_create(_client, **kwargs):
        captured.update(kwargs)
        message = types.SimpleNamespace(
            content=json.dumps(
                {
                    "caption": (
                        "Body buzzing for no clear reason? Some people may feel jumpy and drained today. "
                        "The signal mix is quiet overall with a faint jitter underneath it. "
                        "That can make focus skate between sharp and foggy without turning the whole day into a wash. "
                        "Try three minutes of slow breathing when the squirrel energy shows up. "
                        "Gaia Eyes keeps watching how these signals overlap with your patterns."
                    ),
                    "hashtags": "#GaiaEyes #WiredTired",
                }
            )
        )
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])

    monkeypatch.setattr(earthscope_generate, "_chat_create_compat", fake_chat_create)
    monkeypatch.setattr(earthscope_generate, "_writer_model", lambda: "test-model")

    result = _rewrite_facebook_caption_from_spine(
        object(),
        ctx={"day": "2026-07-13", "platform": "fb"},
        title="Body Buzzing For No Clear Reason?",
        default_caption="Body buzzing for no clear reason? Keep your pace gentle when you feel squirrely.",
        default_hashtags="#GaiaEyes",
        sections={
            "snapshot": "The field is quiet overall with a faint jitter.",
            "affects": "You may feel jumpy and drained, with focus that skates between sharp and foggy.",
            "playbook": "- Pause for three minutes of slow breathing",
        },
    )

    prompt = json.loads(captured["messages"][1]["content"])
    assert prompt["content_spine"]["title"] == "Body Buzzing For No Clear Reason?"
    assert prompt["content_spine"]["felt_effects"].startswith("You may feel jumpy and drained")
    assert prompt["constraints"]["preserve_hook_lane"] is True
    assert prompt["constraints"]["new_symptoms_allowed"] is False
    assert result is not None
    assert result["caption"].startswith("Body buzzing for no clear reason?")


def test_social_variants_expand_spine_instead_of_starting_second_interpretation(monkeypatch):
    captured = {}

    monkeypatch.setattr(earthscope_generate, "EARTHSCOPE_FORCE_RULES", False)
    monkeypatch.setattr(earthscope_generate, "_hybrid_rewrite_enabled", lambda: True)
    monkeypatch.setattr(earthscope_generate, "openai_client", lambda: object())

    def fake_spine_rewrite(_client, **kwargs):
        captured.update(kwargs)
        return {
            "caption": "Body buzzing for no clear reason? Facebook expansion stays in the wired-tired lane.",
            "hashtags": "#GaiaEyes #WiredTired",
        }

    def fail_full_rewrite(*_args, **_kwargs):
        raise AssertionError("Facebook variants must not start a second full interpretation")

    monkeypatch.setattr(earthscope_generate, "_rewrite_facebook_caption_from_spine", fake_spine_rewrite)
    monkeypatch.setattr(earthscope_generate, "_get_cached_rewrite", fail_full_rewrite)

    sections = {
        "snapshot": "Quiet overall with a faint jitter.",
        "affects": "Jumpy and drained, with focus moving between sharp and foggy.",
        "playbook": "- Pause for slow breathing",
    }
    variants = _build_social_caption_variants(
        {"day": "2026-07-13", "platform": "default"},
        title="Body Buzzing For No Clear Reason?",
        default_caption="Body buzzing for no clear reason? Keep your pace gentle.",
        default_hashtags="#GaiaEyes",
        sections=sections,
    )

    assert captured["title"] == "Body Buzzing For No Clear Reason?"
    assert captured["sections"] == sections
    assert variants["fb"]["caption"].startswith("Body buzzing for no clear reason?")
