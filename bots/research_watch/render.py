from pathlib import Path
from typing import List
from .models import Draft

# Import your working overlay functions (no changes to your file)
from bots.earthscope_post.gaia_eyes_viral_bot import (
    render_card,             # square caption-style
    render_text_card,        # tall text card
    MEDIA_REPO_PATH,         # to keep the same folder targets
)

def render_fb_square(draft: Draft, energy: str = "Calm") -> Path:
    # Use the scientific TL;DR for the square headline
    caption = draft.scientific.tldr or "Research highlight"
    im = render_card(energy, caption, sch=7.83, kp=3.0, kind="square")
    out = MEDIA_REPO_PATH / "images" / f"research_square.jpg"
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out, "JPEG", quality=90)
    return out

def render_vertical_set(draft: Draft, energy: str = "Calm") -> List[Path]:
    paths: List[Path] = []
    what = draft.scientific.what_happened or ""
    why  = draft.scientific.why_it_matters or ""
    im1 = render_text_card("What happened", what, energy, kind="tall")
    im2 = render_text_card("Why it matters",  why,  energy, kind="tall")
    p1 = MEDIA_REPO_PATH / "images" / "research_what.jpg"
    p2 = MEDIA_REPO_PATH / "images" / "research_why.jpg"
    p1.parent.mkdir(parents=True, exist_ok=True)
    im1.save(p1, "JPEG", quality=90)
    im2.save(p2, "JPEG", quality=90)
    paths.extend([p1, p2])
    return paths