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
