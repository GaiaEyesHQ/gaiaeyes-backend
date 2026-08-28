import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bots.earthscope_post.cta import APP_URL, CTA_VARIANTS, append_caption_cta, select_earthscope_cta


def test_select_earthscope_cta_is_deterministic():
    first = select_earthscope_cta("2026-06-09")
    second = select_earthscope_cta("2026-06-09")

    assert first == second
    assert first in CTA_VARIANTS


def test_append_caption_cta_rotates_from_seed():
    caption = append_caption_cta("Today may feel a little scattered.", seed="2026-06-09")

    assert caption.startswith("Today may feel a little scattered.")
    assert "Gaia Eyes" in caption
    assert APP_URL in caption


def test_append_caption_cta_adds_app_link_to_existing_cta():
    caption = append_caption_cta(
        "Sensitive to background signals? Gaia Eyes compares them with sleep and symptoms.",
        seed="2026-06-09",
    )

    assert caption.count(APP_URL) == 1
    assert caption.endswith(APP_URL)


def test_append_caption_cta_does_not_duplicate_app_link():
    caption = append_caption_cta(f"Download Gaia Eyes: {APP_URL}", seed="2026-06-09")

    assert caption == f"Download Gaia Eyes: {APP_URL}"


def test_select_earthscope_cta_uses_schumann_context():
    cta = select_earthscope_cta("2026-06-09", context={"schumann_value_hz": 7.8})

    assert cta["key"] == "frequency-sensitive"


def test_select_earthscope_cta_uses_pain_context_before_active_weather():
    cta = select_earthscope_cta(
        "2026-08-19",
        context={
            "kp_max": 5,
            "title": "Pain feeling extra loud?",
            "affects": "Joints may ache louder and muscle tension can stack faster.",
        },
    )

    assert cta["key"] == "pain-patterns"
    assert "Headaches" not in cta["card"]


def test_select_earthscope_cta_uses_nervous_system_context_before_solar_activity():
    cta = select_earthscope_cta(
        "2026-08-20",
        context={
            "cmes_24h": 1,
            "flares_24h": 2,
            "title": "Body buzzing for no clear reason?",
            "caption": "Body buzzing for no clear reason? The sky is steady and quiet.",
            "affects": "Wired/tired can pop up for some, where the body feels revved.",
        },
    )

    assert cta["key"] == "nervous-system-patterns"
    assert "heart" not in cta["card"].lower()


def test_select_earthscope_cta_uses_sleep_context_before_solar_activity():
    cta = select_earthscope_cta(
        "2026-08-24",
        context={
            "cmes_24h": 2,
            "title": "Can't settle even when you're tired?",
            "caption": "Keep lights warm and dim after sunset and ease off caffeine earlier.",
            "affects": "Sleep may come a bit easier if nights have felt jumpy lately.",
            "voiceover": "The body's wind-down cues have a cleaner lane to line up.",
            "reel_hook": "Can't settle even when you're tired?",
        },
    )

    assert cta["key"] == "sleep-wind-down-patterns"
    assert "heart" not in cta["card"].lower()


def test_select_earthscope_cta_uses_fatigue_context_before_solar_activity():
    cta = select_earthscope_cta(
        "2026-08-21",
        context={
            "cmes_24h": 1,
            "flares_24h": 1,
            "title": "Finally, a little breathing room?",
            "caption": "Heavy-limb drag can ease and energy comes back in small steps.",
            "affects": "If you still feel drained, recent stress or local factors could be prolonging the dip.",
            "reel_hook": "Finally, a little breathing room?",
        },
    )

    assert cta["key"] == "fatigue-recovery-patterns"
    assert "heart" not in cta["card"].lower()


def test_frequency_cta_uses_plain_language():
    cta = select_earthscope_cta("2026-06-09", context={"schumann_value_hz": 7.8})

    combined = f"{cta['card']} {cta['caption']}"
    assert "HRV" not in combined
    assert "Schumann" not in combined
    assert "ULF" not in combined
    assert "background signals" in combined


def test_caption_ctas_stay_compact():
    for cta in CTA_VARIANTS:
        assert len(cta["caption"]) <= 140
