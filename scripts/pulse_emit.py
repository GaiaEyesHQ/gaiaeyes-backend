#!/usr/bin/env python3
import os, sys, json, pathlib
from datetime import datetime, timezone

MEDIA_DIR = os.getenv("MEDIA_DIR", "../gaiaeyes-media")
OUT = os.getenv("OUTPUT_JSON_PATH", f"{MEDIA_DIR}/data/pulse.json")

def load(name):
    p = pathlib.Path(MEDIA_DIR)/"data"/name
    if p.exists():
        try: return json.loads(p.read_text(encoding="utf-8"))
        except: return None
    return None

def card(type_, title, summary, severity="info", time_window=None, details_url=None, data=None):
    c = {"type":type_, "title":title, "summary":summary, "severity":severity}
    if time_window: c["time_window"]=time_window
    if details_url: c["details_url"]=details_url
    if data: c["data"]=data
    return c

def main():
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")
    wx  = load("space_weather.json") or {}
    fc  = load("flares_cmes.json") or {}
    es  = load("earthscope.json") or {}
    qk  = load("quakes_latest.json") or {}
    nws = load("alerts_us_latest.json") or {}

    cards = []

    # CME
    cmes = (fc.get("cmes") or {})
    cme_head = cmes.get("headline")
    speeds = [e.get("speed_kms") or 0 for e in (cmes.get("last_72h") or [])]
    max_spd = max(speeds) if speeds else 0
    if cmes.get("last_72h"):
        sev = "high" if max_spd>=1000 else ("medium" if max_spd>=600 else "low")
        tw  = "Next 2–3 days" if max_spd>=400 else "Next few days"
        cards.append(card("cme",
                          "Two Slow CMEs Expected Oct 7–8" if sev=="low" else "CME Activity Continues",
                          cme_head or "Recent CMEs observed; monitor for geomagnetic effects.",
                          severity=sev, time_window=tw,
                          data={"max_speed_kms":max_spd}))

    # Flare
    max24 = (fc.get("flares") or {}).get("max_24h")
    if max24:
        sev = "high" if max24.startswith("X") else ("medium" if max24.startswith("M") else "low")
        tw  = "Next 24–48h" if sev!="low" else "Next 24h"
        title = "M-class Solar Flare Risk Persists" if sev=="medium" else ("X-class Risk" if sev=="high" else "C-class Flares Ongoing")
        cards.append(card("flare", title,
                          f"Recent peak {max24}. Radio/HF may see brief fades during bursts.",
                          severity=sev, time_window=tw, data={"max_24h":max24}))

    # Aurora
    headline = (wx.get("next_72h") or {}).get("headline","")
    if any(k in (headline or "").upper() for k in ("G1","G2","G3","G4","G5")):
        kp = ((wx.get("now") or {}).get("kp"))
        sev = "low" if "G1" in headline else ("medium" if "G2" in headline else "high")
        cards.append(card("aurora", "Aurora Chances: High Latitudes" if sev=="low" else "Aurora Watch",
                          f"{headline}. Best bets after local midnight; dark skies help.",
                          severity=sev, time_window="Tonight–Next 72h", data={"kp_now":kp, "headline":headline}))

    # Tips (aurora photo)
    cards.append(card("tips", "How to Capture Auroras",
                      "Wide lens; ISO 1600–3200; 4–6s exposure; manual focus on bright star; shoot RAW.",
                      severity="info"))

    # Earthquakes (top one)
    evs = qk.get("events") or []
    if evs:
        top = evs[0]
        t = top.get("time_utc","")
        ti = t.replace("T"," ").replace("Z"," UTC")
        mag = top.get("mag")
        place = top.get("place","")
        depth = top.get("depth_km") or ""
        cards.append(card("quake", f"M{mag:.1f} Earthquake — {place}",
                          "Deep event; no tsunami expected." if (depth and depth>300) else "Shallow event.",
                          severity="info", time_window=ti, details_url=top.get("url"),
                          data={"mag":mag, "place":place, "time_utc":t}))

    # NWS Severe (compact)
    alerts = nws.get("alerts") or []
    if alerts:
        # Rough cluster by keywords
        kinds = [a["event"] for a in alerts[:10] if a.get("event")]
        if kinds:
            cards.append(card("severe", "Central U.S. — Storm & Flood Risk",
                              "Clusters of severe t-storm / flood alerts active. Check local NWS.",
                              severity="medium", time_window="Next 48h",
                              details_url="https://www.weather.gov/alerts",
                              data={"examples": kinds[:4]}))

    payload = {"timestamp_utc": now, "cards": cards}
    p = pathlib.Path(OUT); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, separators=(",",":"), ensure_ascii=False), encoding="utf-8")
    print(f"[pulse] wrote -> {p}")

if __name__ == "__main__":
    main()