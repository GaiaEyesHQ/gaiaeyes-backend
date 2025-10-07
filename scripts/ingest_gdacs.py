#!/usr/bin/env python3
import os, sys, json, pathlib, re
from datetime import datetime, timezone
from urllib.request import urlopen, Request

MEDIA_DIR = os.getenv("MEDIA_DIR", "../gaiaeyes-media")
OUT = os.getenv("OUTPUT_JSON_PATH", f"{MEDIA_DIR}/data/gdacs_latest.json")
RSS = os.getenv("GDACS_RSS", "https://www.gdacs.org/xml/rss.xml")

# very small RSS parser (enough for GDACS)
def fetch(url):
    req = Request(url, headers={"User-Agent":"gaiaeyes.com"})
    with urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8","ignore")

def tag(text, name):
    # return list of <name>...</name> chunks
    return re.findall(rf"<{name}[^>]*>(.*?)</{name}>", text, flags=re.S|re.I)

def field(block, name):
    m = re.search(rf"<{name}[^>]*>(.*?)</{name}>", block, flags=re.S|re.I)
    return (m.group(1).strip() if m else None)

KEEP = ("FL","TC","VO","EQ")  # Flood, Tropical Cyclone, Volcano, Earthquake

def main():
    try:
        xml = fetch(RSS)
    except Exception as e:
        print(f"[gdacs] fetch failed: {e}", file=sys.stderr)
        xml = ""

    items = []
    for it in tag(xml, "item"):
        title = field(it, "title") or ""
        link  = field(it, "link") or ""
        pub   = field(it, "pubDate") or ""
        cat   = field(it, "category") or ""
        # GDACS puts codes like "FL", "TC" in category/title
        code = None
        for k in KEEP:
            if re.search(rf"\b{k}\b", title+cat):
                code = k; break
        if not code:
            continue
        items.append({
            "code": code,
            "title": re.sub(r"\s+", " ", title).strip(),
            "url": link,
            "published": pub
        })

    payload = {
        "timestamp_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z"),
        "alerts": items[:10],
        "sources": { "gdacs_rss": RSS }
    }
    p = pathlib.Path(OUT); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, separators=(",",":"), ensure_ascii=False), encoding="utf-8")
    print(f"[gdacs] wrote -> {p}")

if __name__ == "__main__":
    main()