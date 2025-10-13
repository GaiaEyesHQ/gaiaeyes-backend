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
    "magnetosphere", "sym-h", "symh", "dst", "kp", "bz", "imf", "solar wind",
    "flare", "x-class", "m-class", "cme", "coronal mass ejection",
    "schumann", "resonance", "hrv", "heart rate variability", "blood pressure",
    "gnss", "gps", "hf radio", "geomagnetic", "aurora", "storm", "storm watch",
    "aurora watch", "solar risk", "radiation storm"
}

# Regex patterns to catch formatting variants and phrases
_PATTERNS = [
    re.compile(r"\bSYM[-\s]?H\b", re.I),
    re.compile(r"\bDST\b", re.I),
    re.compile(r"\bK[\s-]?p\b", re.I),
    re.compile(r"\bB[\s-]?z\b", re.I),
    re.compile(r"\bIMF\b", re.I),
    re.compile(r"\b(aurora|auroral)\s+(watch|alert|outlook)\b", re.I),
    re.compile(r"\b(geomagnetic|solar)\s+(storm|watch|alert)\b", re.I),
    re.compile(r"\bcoronal\s+mass\s+ejection\b", re.I),
    re.compile(r"\bX[- ]?class\b", re.I),
    re.compile(r"\bM[- ]?class\b", re.I),
    re.compile(r"\bSchumann\b", re.I),
    re.compile(r"\bheart[- ]?rate[- ]?variability\b", re.I),
    re.compile(r"\bHRV\b", re.I),
]

def _topic_hits(blob: str) -> list[str]:
    hits = set()
    low = blob.lower()
    # keyword hits
    for kw in KEYTERMS:
        if kw in low:
            hits.add(kw)
    # regex hits
    for pat in _PATTERNS:
        if pat.search(blob):
            hits.add(pat.pattern)
    return sorted(hits)

def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()

def _sha8(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:8]

def _tag_topics(title: str, summary: str):
    blob = f"{title} {summary}"
    return _topic_hits(blob)

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