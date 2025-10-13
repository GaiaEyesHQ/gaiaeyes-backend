import os
from typing import List
from .sources import fetch_all
from .scoring import score_item
from .rewrite import rewrite_dual
from .publish import upsert_post
from .models import Item

TOP_N = int(os.getenv("RESEARCH_TOP_N", "4"))
MIN_SCORE = float(os.getenv("RESEARCH_MIN_SCORE", "0.55"))
RENDER_MEDIA = os.getenv("RESEARCH_RENDER_MEDIA", "1") == "1"

def pick_items(items: List[Item]) -> List[Item]:
    pool = [i for i in items if i.topics]
    for it in pool:
        it.score = score_item(it)
    pool.sort(key=lambda x: x.score, reverse=True)
    return [i for i in pool if i.score >= MIN_SCORE][:TOP_N]

def main():
    items = fetch_all()
    picked = pick_items(items)
    if not picked:
        print("[research_watch] nothing credible today.")
        return
    for it in picked:
        draft = rewrite_dual(it)
        upsert_post(it, draft)
        if RENDER_MEDIA:
            try:
                from .render import render_fb_square, render_vertical_set
                render_fb_square(draft)
                render_vertical_set(draft)
            except Exception as e:
                print(f"[research_watch] media render failed: {e}")
        print(f"[research_watch] published: {it.title}")

if __name__ == "__main__":
    main()