from datetime import datetime, timezone
from .models import Item

TRUST = {
  "noaa_swpc": 1.0, "usgs_eq": 0.95, "esa": 0.9, "agu_eos": 0.85,
  "spaceweatherlive": 0.70, "general": 0.5
}
WEIGHTS = {"trust": 0.6, "keywords": 0.3, "recency": 0.1}

def score_item(item: Item) -> float:
    trust = TRUST.get(item.source, 0.4)
    kw = len(item.topics)
    age_h = max(1, (datetime.now(timezone.utc) - item.published_at).total_seconds()/3600)
    rec = 1.0 / (1.0 + (age_h/48.0))
    score = WEIGHTS["trust"]*trust + WEIGHTS["keywords"]*min(1, kw/2.0) + WEIGHTS["recency"]*rec
    return round(score, 3)