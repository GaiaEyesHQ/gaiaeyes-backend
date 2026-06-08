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
