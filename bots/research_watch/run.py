import os
from datetime import datetime, timezone
from typing import List
from .sources import fetch_all
from .scoring import score_item
from .rewrite import rewrite_dual
from .publish import upsert_post
from .models import Item

TOP_N = int(os.getenv("RESEARCH_TOP_N", "4"))
MIN_SCORE = float(os.getenv("RESEARCH_MIN_SCORE", "0.45"))  # gentler default
RECENT_HOURS = int(os.getenv("RESEARCH_RECENT_HOURS", "120"))
FORCE_ONE = os.getenv("RESEARCH_FORCE_ONE", "1") == "1"
RENDER_MEDIA = os.getenv("RESEARCH_RENDER_MEDIA", "1") == "1"

def _within_recent(it: Item) -> bool:
    age_h = max(1, (datetime.now(timezone.utc) - it.published_at).total_seconds() / 3600)
    # allow some slack beyond RECENT_HOURS; the scoring still favors fresh items
    return age_h <= (RECENT_HOURS * 2)

def pick_items(items: List[Item]) -> List[Item]:
    # must have at least one topic hit and be reasonably recent
    pool = [i for i in items if i.topics and _within_recent(i)]
    for it in pool:
        it.score = score_item(it, recent_hours=RECENT_HOURS)
    pool.sort(key=lambda x: x.score, reverse=True)

    # Debug table (top 10) so you can see why items were picked or skipped
    print("\n[research_watch] candidates:")
    for it in pool[:10]:
        age_h = int((datetime.now(timezone.utc) - it.published_at).total_seconds() / 3600)
        topics = ", ".join(it.topics) if it.topics else "-"
        print(f"- {it.score:0.3f} | {age_h:>3}h | {it.source:16s} | {topics} | {it.title[:90]}")

    picked = [i for i in pool if i.score >= MIN_SCORE][:TOP_N]
    if picked:
        return picked

    # Fallback: if nothing meets threshold but we have plausible items, take the top one
    if FORCE_ONE and pool:
        print("[research_watch] forcing 1 item (no one met threshold).")
        return [pool[0]]

    return []

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
                # crude energy heuristic for visual styling
                energy = "High" if any(k in (it.topics or []) for k in ("storm", "storm watch", "x-class", "cme", "geomagnetic", "aurora watch")) else "Calm"
                render_fb_square(draft, energy=energy)
                render_vertical_set(draft, energy=energy)
            except Exception as e:
                print(f"[research_watch] media render failed: {e}")
        print(f"[research_watch] published: {it.title}")

if __name__ == "__main__":
    main()