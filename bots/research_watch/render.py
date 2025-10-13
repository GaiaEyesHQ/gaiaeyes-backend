import os
from pathlib import Path
from typing import List
from .models import Draft

# Import your working overlay functions (no changes to your file)
from bots.earthscope_post.gaia_eyes_viral_bot import (
    render_card,             # square caption-style
    render_text_card,        # tall text card
    MEDIA_REPO_PATH,         # to keep the same folder targets
)

def _media_base() -> Path:
    """
    Choose a writable media base directory.
    Priority:
      1) RESEARCH_MEDIA_DIR env var (if set)
      2) MEDIA_REPO_PATH from EarthScope module (if writable)
      3) ./media under current working directory
    """
    env_dir = os.getenv("RESEARCH_MEDIA_DIR")
    if env_dir:
        p = Path(env_dir)
        try:
            p.mkdir(parents=True, exist_ok=True)
            return p
        except Exception:
            pass
    try:
        base = Path(MEDIA_REPO_PATH)
        base.mkdir(parents=True, exist_ok=True)
        return base
    except Exception:
        pass
    fallback = Path("media")
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback

def render_fb_square(draft: Draft, energy: str = "Calm") -> Path:
    # Use the scientific TL;DR for the square headline
    caption = draft.scientific.tldr or "Research highlight"
    im = render_card(energy, caption, sch=7.83, kp=3.0, kind="square")
    base = _media_base() / "images"
    base.mkdir(parents=True, exist_ok=True)
    out = base / "research_square.jpg"
    im.save(out, "JPEG", quality=90)
    return out

def render_vertical_set(draft: Draft, energy: str = "Calm") -> List[Path]:
    paths: List[Path] = []
    what = draft.scientific.what_happened or ""
    why  = draft.scientific.why_it_matters or ""
    im1 = render_text_card("What happened", what, energy, kind="tall")
    im2 = render_text_card("Why it matters",  why,  energy, kind="tall")
    base = _media_base() / "images"
    base.mkdir(parents=True, exist_ok=True)
    p1 = base / "research_what.jpg"
    p2 = base / "research_why.jpg"
    im1.save(p1, "JPEG", quality=90)
    im2.save(p2, "JPEG", quality=90)
    paths.extend([p1, p2])
    return paths