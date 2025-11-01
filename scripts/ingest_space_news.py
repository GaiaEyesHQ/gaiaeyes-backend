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
  ("NASA Breaking", "https://www.nasa.gov/rss/dyn/breaking_news.rss", "space_activity", "rss"),
  ("SWPC Alerts", "https://services.swpc.noaa.gov/products/alerts.json", "space_weather", "swpc_alerts_json"),
  ("NASA DONKI", "donki", "space_weather", "donki_api")
]


def fetch(url: str) -> str:
  try:
    req = urllib.request.Request(url, headers={"User-Agent":"GaiaEyes/1.0 (+https://gaiaeyes.com)"})
    with urllib.request.urlopen(req, timeout=20) as r:
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


def parse_swpc_alerts_json(obj, cutoff):
  """SWPC alerts.json is a list-of-lists; first row is header. We convert rows into news items if within LOOKBACK window."""
  items = []
  if not isinstance(obj, list) or not obj:
    return items
  header = obj[0] if isinstance(obj[0], list) else []
  # Expect keys like: "issue_datetime", "message", "product_id", "type", "begin_time", "source"
  def idx(k):
    try:
      return header.index(k)
    except ValueError:
      return -1
  i_issue = idx("issue_datetime")
  i_msg   = idx("message")
  i_type  = idx("product_id") if idx("product_id")!=-1 else idx("type")
  for row in obj[1:]:
    if not isinstance(row, list):
      continue
    pub_str = row[i_issue] if (i_issue!=-1 and i_issue < len(row)) else ""
    msg = row[i_msg] if (i_msg!=-1 and i_msg < len(row)) else "SWPC Alert"
    cat = row[i_type] if (i_type!=-1 and i_type < len(row)) else "SWPC"
    pub_dt = parse_pubdate(pub_str)
    if pub_dt and pub_dt < cutoff:
      continue
    publ = pub_dt.replace(microsecond=0).isoformat().replace("+00:00","Z") if pub_dt else ""
    items.append({
      "title": msg,
      "link": "https://www.swpc.noaa.gov/products/alerts-watches-and-warnings",
      "published_at": publ,
      "_dt": pub_dt or cutoff  # ensure sortability
    })
  return items


def donki_fetch(kind: str, start_iso: str, api_key: str):
  base = "https://api.nasa.gov/DONKI/" + kind
  qs = {"startDate": start_iso, "api_key": api_key}
  url = base + "?" + urllib.parse.urlencode(qs)
  try:
    req = urllib.request.Request(url, headers={"User-Agent":"GaiaEyes/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
      return json.loads(r.read().decode("utf-8"))
  except Exception as e:
    print("[news][donki]", kind, e)
    return []

def donki_items(cutoff: dt.datetime, api_key: str):
  items = []
  start_iso = (cutoff.date()).isoformat()
  # Flares
  flrs = donki_fetch("FLR", start_iso, api_key)
  for f in flrs or []:
    peak = f.get("peakTime") or f.get("beginTime") or ""
    pub_dt = parse_pubdate(peak)
    if pub_dt and pub_dt < cutoff: continue
    cls = f.get("classType") or "Flare"
    ar  = f.get("sourceLocation") or ""
    t   = f"Solar flare {cls} {('at '+ar) if ar else ''}"
    items.append({"title": t.strip(), "link": "https://www.swpc.noaa.gov/products/solar-and-geophysical-event-reports", "published_at": pub_dt.replace(microsecond=0).isoformat().replace("+00:00","Z") if pub_dt else "", "_dt": pub_dt or cutoff})
  # CMEs
  cmes = donki_fetch("CME", start_iso, api_key)
  for c in cmes or []:
    pub_dt = parse_pubdate(c.get("startTime") or c.get("time21_5") or "")
    if pub_dt and pub_dt < cutoff: continue
    spd = None
    try:
      if c.get("cmeAnalyses"): spd = c["cmeAnalyses"][0].get("speed")
    except Exception:
      pass
    t = f"CME detected{(' speed '+str(spd)+' km/s') if spd else ''}"
    items.append({"title": t, "link": "https://ccmc.gsfc.nasa.gov/donki/", "published_at": pub_dt.replace(microsecond=0).isoformat().replace("+00:00","Z") if pub_dt else "", "_dt": pub_dt or cutoff})
  return items


def main():
  now = dt.datetime.now(dt.timezone.utc)
  cutoff = now - dt.timedelta(days=max(0, LOOKBACK))
  items = []
  for entry in SOURCES:
    if len(entry) == 4:
      name, url, cat, kind = entry
    else:
      name, url, cat = entry; kind = "rss"
    if kind == "rss":
      data = fetch(url)
      if not data:
        continue
      for it in rss_items(data):
        it["source"] = name
        it["category"] = cat
        parsed = parse_pubdate(it.get("published_at"))
        if parsed and parsed < cutoff:
          continue
        it["published_at"] = parsed.replace(microsecond=0).isoformat().replace("+00:00", "Z") if parsed else ""
        it["_dt"] = parsed or now
        items.append(it)
    elif kind == "swpc_alerts_json":
      data = fetch(url)
      if not data:
        continue
      try:
        obj = json.loads(data)
      except Exception:
        obj = None
      items.extend(parse_swpc_alerts_json(obj, cutoff))
    elif kind == "donki_api":
      api_key = os.getenv("NASA_API_KEY", "DEMO_KEY")
      items.extend(donki_items(cutoff, api_key))

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
