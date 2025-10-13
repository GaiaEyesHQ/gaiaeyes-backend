from datetime import datetime, timezone
from .models import Item

# Source trust weights (adjust per your preferences)
TRUST = {
    "noaa_swpc": 1.0,
    "usgs_eq": 0.95,
    "esa": 0.90,
    "agu_eos": 0.85,
    "spaceweatherlive": 0.70,
    "general": 0.50,
}

def score_item(item: Item, recent_hours: int = 96) -> float:
    """
    Compute a credibility/relevance score in [0,1].

    Components:
      - trust (55%): per-source prior
      - keywords (35%): up to 3 distinct topic hits saturate the term
      - recency (10%): full credit inside `recent_hours`, then soft decay
    """
    # trust
    trust = TRUST.get(item.source, 0.40)

    # keywords: count DISTINCT topic tokens (already widened in sources.py)
    kw_term = min(1.0, len(set(item.topics)) / 3.0)

    # recency
    age_h = max(1, (datetime.now(timezone.utc) - item.published_at).total_seconds() / 3600)
    if age_h <= recent_hours:
        rec_term = 1.0
    else:
        over = age_h - recent_hours
        rec_term = 1.0 / (1.0 + (over / 48.0))

    score = 0.55 * trust + 0.35 * kw_term + 0.10 * rec_term
    return round(score, 3)