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

def _entry_text(e) -> str:
    """
    Build a richer summary blob from multiple possible feed fields.
    Handles RSS/Atom variations: summary, content[], description.
    """
    parts = []
    # summary/description
    summary = e.get("summary") or e.get("description") or ""
    if summary:
        parts.append(str(summary))
    # content array (common in Atom/WordPress feeds)
    try:
        content_list = e.get("content") or []
        for c in content_list:
            val = c.get("value")
            if val:
                parts.append(str(val))
    except Exception:
        pass
    # title as last resort context (already used elsewhere)
    title = e.get("title") or ""
    if title:
        parts.append(str(title))
    blob = " ".join(parts)
    # strip HTML tags crudely if present
    blob = re.sub(r"&lt;/?[^&]*&gt;|<[^>]+>", " ", blob)
    return _clean(blob)

def _topics_from_tags(e) -> list[str]:
    """
    Extract topics/keywords from feed 'tags' if present.
    feedparser normalizes tags as a list of dicts with 'term'.
    """
    hits = []
    try:
        tags = e.get("tags") or []
        for t in tags:
            term = (t.get("term") or "").strip()
            if term:
                term_low = term.lower()
                # direct keyword matches
                if term_low in KEYTERMS:
                    hits.append(term_low)
                # regex phrase matches via topic_hits
                if term_low and _topic_hits(term):
                    hits.extend(_topic_hits(term))
    except Exception:
        pass
    # dedupe & sort
    return sorted(set(hits))

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
            # richer text aggregation from entry fields
            summ = _entry_text(e)
            if not link or not title:
                continue
            pub = e.get("published") or e.get("updated") or None
            try:
                published_at = dtp.parse(pub).astimezone(timezone.utc) if pub else datetime.now(timezone.utc)
            except Exception:
                published_at = datetime.now(timezone.utc)
            id_hash = _sha8(f"{source}|{link}")
            topics_from_text = _tag_topics(title, summ)
            topics_from_feed_tags = _topics_from_tags(e)
            topics = sorted(set(topics_from_text + topics_from_feed_tags))
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