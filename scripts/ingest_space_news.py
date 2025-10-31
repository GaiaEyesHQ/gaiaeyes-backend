#!/usr/bin/env python3
import datetime as dt
import json
import os
import urllib.request
from email.utils import parsedate_to_datetime

OUT_JSON = os.getenv("OUTPUT_JSON_PATH", "news_latest.json")
MEDIA_DIR = os.getenv("MEDIA_DIR", "gaiaeyes-media")
LOOKBACK = int(os.getenv("LOOKBACK_DAYS", "30"))

SOURCES = [
  ("NOAA SWPC News", "https://services.swpc.noaa.gov/news/notifications.rss", "space_weather"),
  ("NASA Heliophysics", "https://www.nasa.gov/rss/dyn/solar_system.rss", "solar_activity"),
]


def fetch(url: str) -> str:
  try:
    with urllib.request.urlopen(url, timeout=20) as r:
      return r.read().decode("utf-8", "ignore")
  except Exception as e:  # pragma: no cover - network resiliency
    print("[news]", url, e)
    return ""


def rss_items(raw: str):
  if not raw:
    return []
  out = []
  chunks = raw.split("<item>")
  for frag in chunks[1:]:
    title = frag.split("</title>")[0].split("<title>")[-1].strip()
    link = frag.split("</link>")[0].split("<link>")[-1].strip()
    pub = ""
    if "</pubDate>" in frag:
      pub = frag.split("</pubDate>")[0].split("<pubDate>")[-1].strip()
    out.append({"title": title, "link": link, "published_at": pub})
  return out


def parse_pubdate(value: str):
  if not value:
    return None
  try:
    parsed = parsedate_to_datetime(value)
  except (TypeError, ValueError):
    return None
  if parsed is None:
    return None
  if parsed.tzinfo is None:
    parsed = parsed.replace(tzinfo=dt.timezone.utc)
  return parsed.astimezone(dt.timezone.utc)


def output_path() -> str:
  if os.path.isabs(OUT_JSON):
    return OUT_JSON
  return os.path.join(MEDIA_DIR, "data", OUT_JSON)


def main():
  now = dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc)
  cutoff = now - dt.timedelta(days=max(0, LOOKBACK))
  items = []
  for name, url, cat in SOURCES:
    raw = fetch(url)
    for it in rss_items(raw):
      it["source"] = name
      it["category"] = cat
      parsed = parse_pubdate(it.get("published_at"))
      if parsed:
        if parsed < cutoff:
          continue
        it["published_at"] = parsed.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        it["_dt"] = parsed
      else:
        it["published_at"] = ""
        it["_dt"] = now
      items.append(it)

  seen = set()
  deduped = []
  for it in items:
    link = it.get("link")
    if not link or link in seen:
      continue
    seen.add(link)
    deduped.append(it)

  deduped.sort(key=lambda x: x.get("_dt") or dt.datetime.min.replace(tzinfo=dt.timezone.utc), reverse=True)
  for it in deduped:
    it.pop("_dt", None)

  dest = output_path()
  os.makedirs(os.path.dirname(dest), exist_ok=True)
  payload = {
    "timestamp_utc": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    "items": deduped,
  }
  with open(dest, "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
  print("[news] wrote", dest, "with", len(deduped), "items")


if __name__ == "__main__":
  main()
