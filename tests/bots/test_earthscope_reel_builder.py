import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bots.earthscope_post import reel_builder


def test_reel_card_order_matches_public_carousel_flow():
    assert reel_builder.PREFERRED_CARD_NAMES == [
        "daily_affects.jpg",
        "daily_playbook.jpg",
        "daily_stats.jpg",
    ]


def test_reel_fallback_accepts_uppercase_image_extensions(tmp_path):
    image = tmp_path / "fallback-card.PNG"
    image.write_bytes(b"placeholder")

    assert reel_builder.pick_card_images(tmp_path, 1) == [image]
