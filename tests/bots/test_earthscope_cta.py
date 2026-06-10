import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bots.earthscope_post.cta import CTA_VARIANTS, append_caption_cta, select_earthscope_cta


def test_select_earthscope_cta_is_deterministic():
    first = select_earthscope_cta("2026-06-09")
    second = select_earthscope_cta("2026-06-09")

    assert first == second
    assert first in CTA_VARIANTS


def test_append_caption_cta_rotates_from_seed():
    caption = append_caption_cta("Today may feel a little scattered.", seed="2026-06-09")

    assert caption.startswith("Today may feel a little scattered.")
    assert "Gaia Eyes" in caption


def test_select_earthscope_cta_uses_schumann_context():
    cta = select_earthscope_cta("2026-06-09", context={"schumann_value_hz": 7.8})

    assert cta["key"] == "frequency-sensitive"
