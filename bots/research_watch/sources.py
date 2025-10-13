import hashlib, re
from datetime import datetime, timezone
from dateutil import parser as dtp
from typing import List, Tuple
import feedparser
from .models import Item

FEEDS: List[Tuple[str, str]] = [
    ("noaa_swpc", "https://services.swpc.noaa.gov/news/index.rss"),
    ("spaceweatherlive", "https://www.spaceweatherlive.com/community/rss/1-news.xml"),
    ("usgs_eq", "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/5.0_day.atom"),
    ("agu_eos", "https://eos.org/feed"),
    ("esa", "https://www.esa.int/rssfeed/Our_Activities/Space_Safety"),
]

KEYTERMS = {
  "magnetosphere", "sym-h", "kp", "bz", "solar wind", "flare", "cme",
  "schumann", "hrv", "blood pressure", "gnss", "hf radio",
  "geomagnetic", "aurora", "storm"
}

def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()

def _sha8(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:8]

def _tag_topics(title: str, summary: str):
    blob = f"{title} {summary}".lower()
    hits = [k for k in KEYTERMS if k in blob]
    return sorted(set(hits))

def fetch_all() -> List[Item]:
    items: List[Item] = []
    for source, url in FEEDS:
        feed = feedparser.parse(url)
        for e in feed.entries:
            link = e.get("link") or e.get("id")
            title = _clean(e.get("title", ""))
            summ = _clean(e.get("summary", ""))
            if not link or not title:
                continue
            pub = e.get("published") or e.get("updated") or None
            try:
                published_at = dtp.parse(pub).astimezone(timezone.utc) if pub else datetime.now(timezone.utc)
            except Exception:
                published_at = datetime.now(timezone.utc)
            id_hash = _sha8(f"{source}|{link}")
            topics = _tag_topics(title, summ)
            items.append(Item(
                id_hash=id_hash, url=link, title=title, summary=summ,
                source=source, published_at=published_at, topics=topics
            ))
    # Dedup newest per id
    latest = {}
    for it in items:
        if it.id_hash not in latest or it.published_at > latest[it.id_hash].published_at:
            latest[it.id_hash] = it
    return list(latest.values())