#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gaia Eyes – Daily Image + Data Mirror (Supabase + Media repo)
-------------------------------------------------------------------
- Reads post & feature data from Supabase REST
- Renders four branded 1080×1080 JPGs:
  1) Stats / snapshot (EarthScope • Today’s Metrics)
  2) Caption card (short)
  3) How This Affects You
  4) Self-Care Playbook
- Avoids background reuse across days (bg_history.json)
- Writes data/latest.json + data/latest.csv
- Git add/commit/push with auto-stash on conflicts

Requirements:
  pip install requests python-dotenv pillow

Environment (.env) on desktop:
  MEDIA_REPO_PATH=/Users/jenniferobrien/Documents/gaiaeyes-media
  LOGO_PATH=/Users/jenniferobrien/Desktop/GaiaEyes/GaiaEyesLogo.png
  SUPABASE_REST_URL=https://<project>.supabase.co/rest/v1
  SUPABASE_ANON_KEY=<anon-or-empty>
  SUPABASE_SERVICE_KEY=<service-role-key>   # recommended for server-side
  SUPABASE_USER_ID=e20a3e9e-1fc2-41ad-b6f7-656668310d13
  TARGET_DAY=YYYY-MM-DD (optional; defaults to today UTC)
"""

import os
import sys
import csv
import json
import math
import time
import random
import logging
import argparse
import re
import subprocess
import datetime as dt
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Union

from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter

HERE = Path(__file__).resolve().parent
FONTS_DIR = HERE / "fonts"

def _load_font(primary: Union[str, List[str]], size: int, fallback: Optional[ImageFont.ImageFont] = None) -> ImageFont.ImageFont:
    candidates: List[str] = []
    candidates.extend(primary if isinstance(primary, list) else [primary])
    candidates += ["Arial Bold.ttf", "Arial.ttf", "Helvetica.ttf"]
    expanded: List[Path] = []
    for name in candidates:
        p = Path(name)
        if p.suffix.lower() in {".ttf", ".otf"}:
            expanded.append(p)
            if not p.is_absolute():
                expanded.append(FONTS_DIR / p.name)
        else:
            expanded.append(FONTS_DIR / name)
            expanded.append(Path(name))
    for path in expanded:
        try:
            return ImageFont.truetype(str(path), size)
        except Exception:
            continue
    return fallback or ImageFont.load_default()

def _overlay_logo_and_tagline(im: Image.Image, tagline: str = "Decode the unseen.") -> None:
    W, H = im.size
    draw = ImageDraw.Draw(im)
    try:
        font_small = _load_font(["Satisfy-Regular.ttf", "Oswald-Regular.ttf", "Poppins-Regular.ttf", "Arial.ttf"], 32)
    except Exception:
        font_small = ImageFont.load_default()
    dim = (190, 205, 230, 255)
    if LOGO_PATH.exists():
        try:
            logo = Image.open(LOGO_PATH)
            if logo.mode != "RGBA":
                logo = logo.convert("RGBA")
            lw = 200
            ratio = lw / float(logo.width)
            logo = logo.resize((lw, int(logo.height * ratio)))
            im.alpha_composite(logo, (W - lw - 50, H - logo.height - 70))
        except Exception as e:
            logging.warning(f"Logo overlay failed: {e}")
    x0, y0 = 60, H - 90
    draw.text((x0+2, y0+2), tagline, fill=(0,0,0,160), font=font_small)
    draw.text((x0, y0), tagline, fill=dim, font=font_small)

import requests
from requests.adapters import HTTPAdapter, Retry
from dotenv import load_dotenv

# -------------------------
# CONFIG / PATHS
# -------------------------
OUTPUT_DIR = HERE / "Output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

load_dotenv(HERE / ".env")
MEDIA_REPO_PATH = Path(os.getenv("MEDIA_REPO_PATH", "/Users/jenniferobrien/Documents/gaiaeyes-media")).expanduser()
LOGO_PATH = Path(os.getenv("LOGO_PATH", "/Users/jenniferobrien/Desktop/GaiaEyes/GaiaEyesLogo.png")).expanduser()

IMG_PATH_REPO = MEDIA_REPO_PATH / "images" / "dailypost.jpg"
JSON_PATH_REPO = MEDIA_REPO_PATH / "data" / "latest.json"
CSV_PATH_REPO  = MEDIA_REPO_PATH / "data" / "latest.csv"
SCHUMANN_CSV_REPO = MEDIA_REPO_PATH / "data" / "schumann.csv"

# Prefer media EarthScope card JSON if present (new pipeline)
EARTHSCOPE_MEDIA_DIR = Path(os.getenv("EARTHSCOPE_MEDIA_DIR", str(MEDIA_REPO_PATH))).expanduser()
EARTHSCOPE_CARD_CANDIDATES = [
    EARTHSCOPE_MEDIA_DIR / "data" / "earthscope_daily.json",   # new daily card
    EARTHSCOPE_MEDIA_DIR / "data" / "earthscope.json",         # consolidated earthscope
    EARTHSCOPE_MEDIA_DIR / "data" / "earthscope_latest.json",  # legacy name
]
# Optional pulse file (aurora/quakes/severe) living in media repo
PULSE_JSON_PATH = MEDIA_REPO_PATH / "data" / "pulse.json"

def load_pulse_ctx(p: Path = PULSE_JSON_PATH) -> dict:
    """Load compact context from pulse.json (if present)."""
    try:
        if not p.exists():
            return {}
        data = json.loads(p.read_text(encoding="utf-8"))
        cards = data.get("cards", []) or []
        out = {}
        aur = next((c for c in cards if c.get("type") == "aurora"), None)
        if aur:
            ad = aur.get("data", {}) or {}
            out["aurora_headline"] = ad.get("headline") or aur.get("title")
            out["aurora_window"] = aur.get("time_window")
            out["aurora_severity"] = aur.get("severity")
        quakes = [c for c in cards if c.get("type") == "quake"]
        if quakes:
            out["quakes_count"] = len(quakes)
            q0 = sorted(quakes, key=lambda c: c.get("data", {}).get("time_utc") or c.get("time_window") or "", reverse=True)[0]
            out["quake_top_title"] = q0.get("title")
        return out
    except Exception:
        return {}

# New: Load detailed stats from pulse.json
def load_pulse_stats(p: Path = PULSE_JSON_PATH) -> dict:
    """Extract numeric and textual stats (Kp, Bz, CMEs, flares, aurora, etc.) from pulse.json cards."""
    try:
        if not p.exists():
            return {}
        data = json.loads(p.read_text(encoding="utf-8"))
        cards = data.get("cards", []) or []
        out = {}

        # CME section
        cme = next((c for c in cards if c.get("type") == "cme"), None)
        if cme:
            d = cme.get("data", {}) or {}
            if d.get("max_speed_kms"): out["cmes_speed_kms"] = float(d["max_speed_kms"])
            out["cmes_text"] = cme.get("summary")

        # Flare section
        flare = next((c for c in cards if c.get("type") == "flare"), None)
        if flare:
            d = flare.get("data", {}) or {}
            out["flares_text"] = f"max {d.get('max_24h')}" if d.get("max_24h") else flare.get("summary")

        # Aurora section
        aur = next((c for c in cards if c.get("type") == "aurora"), None)
        if aur:
            d = aur.get("data", {}) or {}
            if d.get("kp_now"): out["kp_now"] = float(d["kp_now"])
            out["aurora_headline"] = d.get("headline") or aur.get("title")
            out["aurora_window"] = aur.get("time_window")

        # Quake (optional display)
        quakes = [c for c in cards if c.get("type") == "quake"]
        if quakes:
            out["quake_count"] = len(quakes)
            out["quake_top_title"] = quakes[0].get("title")

        # Severe weather (optional)
        sev = next((c for c in cards if c.get("type") == "severe"), None)
        if sev:
            out["severe_summary"] = sev.get("summary")

        return out
    except Exception as e:
        logging.warning(f"pulse.json stats parse failed: {e}")
        return {}
    
# Backgrounds (square posts)
BG_DIR_SQUARE = MEDIA_REPO_PATH / "backgrounds" / "square"
BG_DIR_TALL   = MEDIA_REPO_PATH / "backgrounds" / "tall"
RUN_BG_USED: set = set()

# Background history (avoid reuse across days)
BG_HISTORY_PATH = MEDIA_REPO_PATH / "data" / "bg_history.json"
BG_HISTORY_SIZE = 30
def _load_bg_history() -> list[str]:
    try:
        with open(BG_HISTORY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return [str(x) for x in data]
    except Exception:
        pass
    return []
def _save_bg_history(name: str) -> None:
    (MEDIA_REPO_PATH / "data").mkdir(parents=True, exist_ok=True)
    hist = _load_bg_history()
    hist = [h for h in hist if h != name]
    hist.append(name)
    if len(hist) > BG_HISTORY_SIZE:
        hist = hist[-BG_HISTORY_SIZE:]
    try:
        with open(BG_HISTORY_PATH, "w", encoding="utf-8") as f:
            json.dump(hist, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.warning(f"bg_history write failed: {e}")

AFFIRM_HISTORY_PATH = MEDIA_REPO_PATH / "data" / "affirm_history.json"
AFFIRM_HISTORY_SIZE = 28  # keep ~1 month of history

def _load_affirm_history() -> list[str]:
    try:
        with open(AFFIRM_HISTORY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return [str(x) for x in data]
    except Exception:
        pass
    return []

def _save_affirm_history(val: str) -> None:
    (MEDIA_REPO_PATH / "data").mkdir(parents=True, exist_ok=True)
    hist = _load_affirm_history()
    hist = [h for h in hist if h != val]
    hist.append(val)
    if len(hist) > AFFIRM_HISTORY_SIZE:
        hist = hist[-AFFIRM_HISTORY_SIZE:]
    try:
        with open(AFFIRM_HISTORY_PATH, "w", encoding="utf-8") as f:
            json.dump(hist, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.warning(f"affirm_history write failed: {e}")
      
# NOAA 1-minute planetary K index JSON
K_INDEX_URL = "https://services.swpc.noaa.gov/json/planetary_k_index_1m.json"

# Supabase REST
SUPABASE_REST_URL = os.getenv("SUPABASE_REST_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
SUPABASE_USER_ID  = os.getenv("SUPABASE_USER_ID", "e20a3e9e-1fc2-41ad-b6f7-656668310d13")

# Which day to render (UTC). Default: today.
TARGET_DAY = os.getenv("TARGET_DAY")  # YYYY-MM-DD; if None → today

# -------------------------
# LOGGING
# -------------------------
LOG_PATH = OUTPUT_DIR / "gaia_eyes.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(LOG_PATH), logging.StreamHandler(sys.stdout)],
)

# HTTP session with retries
session = requests.Session()
retries = Retry(total=3, backoff_factor=0.8, status_forcelist=[429, 500, 502, 503, 504])
session.mount("https://", HTTPAdapter(max_retries=retries))
session.mount("http://", HTTPAdapter(max_retries=retries))

# -------------------------
# UTIL
# -------------------------
def utcnow_iso() -> str:
    return dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

def ensure_repo_paths():
    (MEDIA_REPO_PATH / "images").mkdir(parents=True, exist_ok=True)
    (MEDIA_REPO_PATH / "data").mkdir(parents=True, exist_ok=True)

# -------------------------
# EARTHSCOPE MEDIA CARD LOADER
# -------------------------
def load_earthscope_card() -> Optional[dict]:
    """Load the newest EarthScope card from media repo, preferring the new daily JSON."""
    for p in EARTHSCOPE_CARD_CANDIDATES:
        try:
            if p.exists():
                with open(p, "r", encoding="utf-8") as f:
                    j = json.load(f)
                    if isinstance(j, dict):
                        logging.info(f"Loaded EarthScope card: {p.name}")
                        return j
        except Exception as e:
            logging.warning(f"EarthScope card read failed {p}: {e}")
    return None

# -------------------------
# TARGET DAY
# -------------------------
def target_day_utc() -> dt.date:
    if TARGET_DAY:
        try:
            return dt.date.fromisoformat(TARGET_DAY)
        except Exception:
            logging.warning(f"Invalid TARGET_DAY={TARGET_DAY}, falling back to today")
    return dt.datetime.utcnow().date()

# -------------------------
# DATA FETCHERS
# -------------------------
def fetch_schumann_from_repo_csv(repo_root: Path) -> Optional[float]:
    path = repo_root / "data" / "schumann.csv"
    if not path.exists():
        return None
    try:
        last = None
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("timestamp"):
                    continue
                last = line
        if last:
            parts = last.split(",")
            if len(parts) >= 2:
                val = float(parts[1])
                return val
    except Exception as e:
        logging.warning(f"Failed reading schumann.csv: {e}")
    return None

def fetch_kp_index() -> float:
    try:
        r = session.get(K_INDEX_URL, timeout=15)
        r.raise_for_status()
        arr = r.json()
        if not isinstance(arr, list) or not arr:
            raise RuntimeError("No Kp data array")
        latest = arr[-1]
        raw = latest.get("estimated_kp", latest.get("kp_index"))
        kp = float(raw)
        return kp
    except Exception as e:
        logging.warning(f"Kp fetch failed, using fallback 3.0: {e}")
        return 3.0

# -------------------------
# SUPABASE REST HELPERS
# -------------------------
def _sb_headers(schema: str = "public") -> dict:
    key = SUPABASE_SERVICE_KEY or SUPABASE_ANON_KEY
    h = {"apikey": key, "Authorization": f"Bearer {key}", "Accept": "application/json"}
    if schema and schema != "public":
        h["Accept-Profile"] = schema
    return h

def supabase_select(table: str, params: dict, schema: Optional[str] = None) -> List[Dict]:
    if not SUPABASE_REST_URL or not (SUPABASE_SERVICE_KEY or SUPABASE_ANON_KEY):
        logging.warning("Supabase REST not configured; skipping %s", table)
        return []
    tbl = table
    sch = schema or "public"
    if "." in table and schema is None:
        parts = table.split(".", 1)
        sch, tbl = parts[0], parts[1]
    url = f"{SUPABASE_REST_URL}/{tbl}"
    r = session.get(url, headers=_sb_headers(sch), params=params, timeout=20)
    if r.status_code != 200:
        logging.warning(f"Supabase select {sch}.{tbl} failed {r.status_code}: {r.text[:200]}")
        return []
    try:
        return r.json()
    except Exception as e:
        logging.warning(f"Supabase parse error for {sch}.{tbl}: {e}")
        return []


# Fallback: read space weather marts directly
def _fetch_space_weather_mart(day: dt.date) -> dict:
    params = {
        "day": f"eq.{day.isoformat()}",
        "select": "kp_max,bz_min,sw_speed_avg,flares_count,cmes_count"
    }
    rows = supabase_select("space_weather_daily", params, schema="marts")
    return rows[0] if rows else {}

# Fallback: read schumann marts directly and average Tomsk + Cumiana f0
def _fetch_schumann_mart(day: dt.date) -> dict:
    params = {"day": f"eq.{day.isoformat()}", "select": "station_id,f0_avg_hz"}
    rows = supabase_select("schumann_daily", params, schema="marts")
    tomsk = None; cumiana = None
    for r in (rows or []):
        sid = (r.get("station_id") or "").lower()
        v = r.get("f0_avg_hz")
        try:
            v = float(v) if v is not None else None
        except Exception:
            v = None
        if sid == "tomsk": tomsk = v
        if sid == "cumiana": cumiana = v
    avg = None
    vals = [v for v in [tomsk, cumiana] if v is not None]
    if vals:
        avg = sum(vals)/len(vals)
    out = {}
    if tomsk is not None: out["sch_fundamental_avg_hz"] = tomsk
    if cumiana is not None: out["sch_cumiana_fundamental_avg_hz"] = cumiana
    if avg is not None: out["sch_any_fundamental_avg_hz"] = avg
    return out

def fetch_latest_day_from_supabase() -> Optional[dt.date]:
    if not SUPABASE_REST_URL or not (SUPABASE_SERVICE_KEY or SUPABASE_ANON_KEY):
        return None
    rows = supabase_select("daily_posts", {"select":"day","order":"day.desc","limit":"1"}, schema="content")
    if rows and isinstance(rows, list) and rows[0].get("day"):
        try: return dt.date.fromisoformat(rows[0]["day"])
        except Exception: pass
    params = {"select":"day","order":"day.desc","limit":"1"}
    if SUPABASE_USER_ID:
        params["user_id"] = f"eq.{SUPABASE_USER_ID}"
    rows2 = supabase_select("daily_features", params, schema="marts")
    if rows2 and isinstance(rows2, list) and rows2[0].get("day"):
        try: return dt.date.fromisoformat(rows2[0]["day"])
        except Exception: pass
    return None

def fetch_daily_features_for(day: dt.date) -> Optional[dict]:
    if not SUPABASE_REST_URL:
        return None
    # First try daily_features with user filter (if provided)
    params = {
        "day": f"eq.{day.isoformat()}",
        "select": ",".join([
            "day","kp_max","bz_min","sw_speed_avg","flares_count","cmes_count",
            "sch_fundamental_avg_hz","sch_cumiana_fundamental_avg_hz","sch_any_fundamental_avg_hz"
        ])
    }
    if SUPABASE_USER_ID:
        params["user_id"] = f"eq.{SUPABASE_USER_ID}"
    rows = supabase_select("daily_features", params, schema="marts")
    if rows:
        return rows[0]

    # Retry without user_id filter (some marts don't include user_id)
    if SUPABASE_USER_ID:
        params.pop("user_id", None)
        rows = supabase_select("daily_features", params, schema="marts")
        if rows:
            return rows[0]

    # Build fallback from component marts
    sw = _fetch_space_weather_mart(day)
    sr = _fetch_schumann_mart(day)
    combo = {}
    combo.update(sw)
    combo.update(sr)
    if combo:
        logging.warning("Supabase: built features from marts fallback for day=%s (missing daily_features)", day.isoformat())
        return combo

    logging.warning("Supabase: no marts daily data found for day=%s", day.isoformat())
    return None

def fetch_post_for(day: dt.date, platform: str="default") -> Optional[dict]:
    if not SUPABASE_REST_URL:
        return None
    params = {
        "day": f"eq.{day.isoformat()}",
        "platform": f"eq.{platform}",
        "select": "day,platform,title,caption,body_markdown,hashtags,metrics_json,sources_json",
        "limit": "1"
    }
    rows = supabase_select("daily_posts", params, schema="content")
    if not rows:
        logging.warning("Supabase: no content.daily_posts found for day=%s platform=%s", day.isoformat(), platform)
        return None
    return rows[0]

# -------------------------
# COPY
# -------------------------
def generate_daily_forecast(sch: float, kp_current: float) -> Tuple[str, str, str]:
    # Energy label primarily from Kp (geomagnetic activity)
    if kp_current >= 5.0:
        energy = "High"
    elif kp_current >= 3.0:
        energy = "Elevated"
    elif kp_current >= 2.0:
        energy = "Calm"
    else:
        energy = "Calm"

    if kp_current >= 6.0:
        mood = "Wired, anxious, or extra sensitive? Earth’s energy is intense today. Be mindful of your heart and nervous system."
        tip  = "Ground outside, hydrate, and reduce caffeine and screen time."
    elif kp_current >= 3.0:
        mood = "Restlessness or mood swings possible—Earth is moderately active. Spurts of creativity mixed with bouts of exhaustion or anxiety."
        tip  = "Move gently, breathe deeper, drink water."
    else:
        mood = "The ideal energy day! Balanced energy—great for clarity and steady focus."
        tip  = "Plan, create, and enjoy steady vibes."
    return energy, mood, tip

def get_daily_affirmation() -> str:
    affirmations = [
        # existing 10
        "You're deeply connected to Earth's energy. Trust your intuition today.",
        "Let Earth's rhythms guide your actions—go slow and steady.",
        "Today, embrace calmness and clarity. Earth's energy supports you.",
        "Stay open to change and trust the flow of the Universe today.",
        "Remember to breathe and ground yourself—you are exactly where you're meant to be.",
        "You are aligned, you are supported, and you are enough.",
        "Every breath you take grounds you deeper into your true self.",
        "Your body knows the rhythm of the Earth. Trust it.",
        "There is peace in slowing down. Let go and receive.",
        "You are safe, you are centered, and you are in tune with Gaia.",
        # +12 new
        "The Earth holds you steady—breathe and let her rhythm restore your balance.",
        "Each moment is an invitation to reconnect with your heart and the cosmos.",
        "As the Schumann hums, so too does your soul find harmony.",
        "Today, trust the quiet—within stillness, your energy realigns.",
        "Like solar winds, let inspiration flow through you with ease.",
        "Ground yourself, root deep, and feel the calm strength of Gaia within.",
        "Your energy is part of Earth’s song; every heartbeat is in tune with her.",
        "Release the static of the day—clarity comes when you attune to Earth’s frequency.",
        "Let the cosmos remind you: you are vast, resilient, and connected.",
        "With each breath, you align more fully to the universal flow of energy.",
        "There is peace in slowing down. Let go and receive.",
        "You are safe, you are centered, and you are in tune with Gaia."
    ]

    # rotation: avoid recent repeats
    recent = set(_load_affirm_history()[-14:])   # last 14 used
    candidates = [a for a in affirmations if a not in recent] or affirmations[:]

    # deterministic choice per day (but not repeating recent)
    try:
        seed = int(dt.datetime.utcnow().strftime("%Y%m%d"))
        random.seed(seed)
    except Exception:
        pass

    choice = random.choice(candidates)
    _save_affirm_history(choice)
    return choice


# Robust section extractor (supports **Bold** or ## Markdown headings)
import re as _re

def extract_section(md: str, header: str) -> Optional[str]:
    """
    Extract the text under a header until the next header. Recognizes headings written as:
      - Markdown ATX headers:  #, ##, ### (any level)
      - Bold headings:         **Header** or __Header__ (optional trailing colon)
    Matching is case-insensitive and ignores surrounding asterisks/# and a trailing colon.
    """
    if not md:
        return None
    text = md.replace('\r', '')
    # Build a regex that matches a heading line for the target header
    hdr = _re.escape(header)
    heading_pat = rf"(?im)^\s*(?:#{1,6}\s*|\*\*\s*|__\s*)?(?:[^\w]*\s*)?{hdr}\s*:?\s*(?:\*\*|__)?.*$"
    m = _re.search(heading_pat, text)
    if not m:
        return None
    start_idx = m.end()
    # Next heading start (any bold or ATX header)
    next_heading_pat = r"(?im)^\s*(?:#{1,6}\s*|\*\*\s*|__\s*)(?:[^\w]*\s*)?([A-Za-z].+?)\s*(?:\*\*|__)?\s*:?.*$"
    n = _re.search(next_heading_pat, text[start_idx:])
    body = text[start_idx: start_idx + n.start()] if n else text[start_idx:]
    # Trim extra blank lines
    lines = [ln.rstrip() for ln in body.split('\n')]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    out = "\n".join(lines).strip()
    return out or None

def extract_any_section(md: str, headers: List[str]) -> Optional[str]:
    # Normalize common hyphen/dash variants to ASCII hyphen for matching
    if md:
        md_norm = (md.replace("\u2010", "-")  # hyphen
                     .replace("\u2011", "-")  # non-breaking hyphen
                     .replace("\u2012", "-")
                     .replace("\u2013", "-")  # en dash
                     .replace("\u2014", "-")) # em dash
    else:
        md_norm = md
    for h in headers:
        h_norm = (h.replace("\u2010", "-")
                    .replace("\u2011", "-")
                    .replace("\u2012", "-")
                    .replace("\u2013", "-")
                    .replace("\u2014", "-"))
        out = extract_section(md_norm, h_norm)
        if out:
            return out
    return None
# -------------------------
# IMAGE RENDER UTIL
# -------------------------
def _draw_gradient(w: int, h: int) -> Image.Image:
    img = Image.new("RGB", (w, h), (6, 10, 20))
    draw = ImageDraw.Draw(img)
    for y in range(h):
        r = 10 + int(10 * (y / h))
        g = 60 + int(120 * (y / h))
        b = 90 + int(120 * (y / h))
        draw.line([(0, y), (w, y)], fill=(r, g, b))
    return img

def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_w: int):
    words = text.split()
    lines = []
    line = ""
    for w in words:
        test = (line + " " + w).strip()
        if draw.textlength(test, font=font) <= max_w:
            line = test
        else:
            if line:
                lines.append(line)
            line = w
    if line:
        lines.append(line)
    return lines

from random import choice
def _list_backgrounds(kind: str = "square") -> List[Path]:
    if kind == "square":
        base = BG_DIR_SQUARE
    elif kind == "tall":
        base = BG_DIR_TALL
    else:
        base = (MEDIA_REPO_PATH / "backgrounds" / "wide")
    if not base.exists():
        return []
    return [p for p in base.glob("*.*") if p.suffix.lower() in {".jpg", ".jpeg", ".png"}]

_TAGS_HIGH = ("solar", "flare", "cme", "storm")
_TAGS_CALM = ("aurora", "nebula", "earth", "lake", "forest")

def _choose_background(energy: Optional[str], kind: str = "square") -> Optional[Path]:
    files = _list_backgrounds(kind)
    if not files:
        return None
    available = [p for p in files if p not in RUN_BG_USED]
    pool = available or files
    # Exclude recently used backgrounds across runs
    recent = set(_load_bg_history())
    pool = [p for p in pool if p.name not in recent] or pool
    if not energy:
        return choice(pool)
    e = energy.lower()
    tags: Tuple[str, ...] = _TAGS_CALM
    if e == "high":
        tags = _TAGS_HIGH
    elif e == "calm":
        tags = _TAGS_CALM
    tagged = [p for p in pool if any(t in p.name.lower() for t in tags)]
    return choice(tagged or pool)

def _compose_bg(W: int, H: int, energy: Optional[str], kind: str = "square") -> Image.Image:
    bgp = _choose_background(energy, kind)
    if bgp:
        RUN_BG_USED.add(bgp)
        try:
            _save_bg_history(bgp.name)
        except Exception:
            pass
    if bgp and bgp.exists():
        try:
            base = Image.open(bgp).convert("RGBA")
            base = ImageOps.fit(base, (W, H), method=Image.LANCZOS, centering=(0.5, 0.5))
        except Exception as e:
            logging.warning(f"Background load failed {bgp}: {e}")
            base = _draw_gradient(W, H).convert("RGBA")
    else:
        base = _draw_gradient(W, H).convert("RGBA")

    e = (energy or "").lower()
    alpha = 90
    if e == "high": alpha = 130
    elif e == "elevated": alpha = 110
    elif e == "calm": alpha = 80
    # small day-based variation to avoid sameness
    try:
        seed = int(dt.datetime.utcnow().strftime('%Y%m%d')) + (hash(kind) % 7)
        random.seed(seed)
        alpha = max(60, min(140, alpha + random.randint(-8, 8)))
    except Exception:
        pass
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, alpha))
    base.alpha_composite(overlay)

    vignette = Image.new("L", (W, H), 0)
    vg = ImageDraw.Draw(vignette)
    margin = int(min(W, H) * 0.08)
    vg.ellipse([margin, margin, W - margin, H - margin], fill=255)
    vignette = vignette.filter(ImageFilter.GaussianBlur(radius=80))
    inv = ImageOps.invert(vignette)
    dark = Image.new("RGBA", (W, H), (0, 0, 0, 60))
    base = Image.composite(dark, base, inv)
    return base

def _safe_text(s: str) -> str:
    if not s:
        return s
    repl = {
        "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-", "\u2014": "-", "\u2015": "-",
        "\u2018": "'", "\u2019": "'", "\u201A": ",",
        "\u201C": '"', "\u201D": '"', "\u201E": '"',
    }
    for k, v in repl.items():
        s = s.replace(k, v)
    return s

_EMOJI_PATTERN = re.compile(r"[\U0001F300-\U0001FAFF\U00002700-\U000027BF\U0001F1E6-\U0001F1FF]", flags=re.UNICODE)
def strip_hashtags_and_emojis(text: str) -> str:
    if not text:
        return text
    text = re.sub(r"#[\w_]+", "", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    try:
        text = _EMOJI_PATTERN.sub("", text)
    except re.error:
        pass
    return text

def _draw_wrapped_multilines(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont,
                             x0: int, y: int, max_w: int, line_gap: int = 60) -> int:
    for para in (text or "").splitlines():
        if not para.strip():
            y += line_gap
            continue
        for ln in _wrap(draw, para, font, max_w):
            draw.text((x0+2, y+2), ln, fill=(0,0,0,180), font=font)
            draw.text((x0, y), ln, fill=(235,245,255,255), font=font)
            y += line_gap
    return y

# Helper: draw text with wrapping, but stop before bottom. If truncated, add ellipsis.
def _draw_wrapped_to_bottom(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont,
                            x0: int, y: int, max_w: int, bottom: int, line_gap: int = 54) -> int:
    """Wrap and draw text but stop before `bottom`. If truncated, add ellipsis."""
    lines_drawn = 0
    for para in (text or "").splitlines():
        if not para.strip():
            if y + line_gap >= bottom: return y
            y += line_gap; continue
        for ln in _wrap(draw, para, font, max_w):
            if y + line_gap >= bottom:
                # add ellipsis to previous line if possible
                if lines_drawn > 0:
                    draw.text((x0, y - line_gap), ("…"), fill=(235,245,255,255), font=font)
                return y
            draw.text((x0+2, y+2), ln, fill=(0,0,0,180), font=font)
            draw.text((x0, y), ln, fill=(235,245,255,255), font=font)
            y += line_gap
            lines_drawn += 1
    return y

def _shadowed_text(draw: ImageDraw.ImageDraw, xy: tuple[int,int], text: str, font: ImageFont.ImageFont, fill=(235,245,255,255), shadow=(0,0,0,160), offset=(2,2)):
    x, y = xy
    draw.text((x+offset[0], y+offset[1]), text, font=font, fill=shadow)
    draw.text((x, y), text, font=font, fill=fill)

def _draw_badge(im: Image.Image, draw: ImageDraw.ImageDraw, text: str, xy: tuple[int,int], pad: tuple[int,int]=(24,12),
                fill=(60,180,120,190), stroke=(0,0,0,140), font: Optional[ImageFont.ImageFont]=None) -> tuple[int,int,int,int]:
    x, y = xy
    f = font or ImageFont.load_default()
    tw = int(draw.textlength(text, font=f))
    w = tw + pad[0]*2
    h = f.size + pad[1]*2
    r = h//2
    box = (x, y, x+w, y+h)
    badge = Image.new("RGBA", (w, h), (0,0,0,0))
    bd = ImageDraw.Draw(badge)
    bd.rounded_rectangle([0,0,w-1,h-1], radius=r, fill=fill, outline=stroke, width=2)
    sh = Image.new("RGBA", (w, h), (0,0,0,0))
    sd = ImageDraw.Draw(sh)
    sd.rounded_rectangle([2,2,w-1,h-1], radius=r, fill=(0,0,0,90))
    im.alpha_composite(sh, (x, y))
    im.alpha_composite(badge, (x, y))
    tx = x + (w - tw)//2
    ty = y + (h - f.size)//2 - 4
    draw.text((tx+1,ty+1), text, font=f, fill=(0,0,0,160))
    draw.text((tx,ty), text, font=f, fill=(255,255,255,230))
    return box

def _blur_panel(im: Image.Image, box: tuple[int,int,int,int], blur_radius: int = 6, panel_alpha: int = 80) -> None:
    x0, y0, x1, y1 = box
    crop = im.crop((x0, y0, x1, y1)).filter(ImageFilter.GaussianBlur(blur_radius))
    im.paste(crop, (x0, y0))
    panel = Image.new("RGBA", (x1 - x0, y1 - y0), (0, 0, 0, panel_alpha))
    im.alpha_composite(panel, (x0, y0))

def render_card(energy_label: str, mood: str, sch: float, kp: float, kind: str = "square") -> Image.Image:
    if kind == "tall":
        W, H = 1080, 1350
    else:
        W, H = 1080, 1080
    im = _compose_bg(W, H, energy_label, kind)
    draw = ImageDraw.Draw(im)
    font_h1   = _load_font(["BebasNeue.ttf", "BebasNeue-Regular.ttf", "ChangeOne-Regular.ttf", "AbrilFatface-Regular.ttf", "Oswald-Bold.ttf"], 68)
    font_h2   = _load_font(["Oswald-Bold.ttf", "AbrilFatface-Regular.ttf", "BebasNeue.ttf"], 46)
    font_body = _load_font(["Oswald-Regular.ttf", "Poppins-Regular.ttf", "AbrilFatface-Regular.ttf"], 36)
    font_small= _load_font(["Oswald-Regular.ttf", "Poppins-Regular.ttf"], 30)
    panel = Image.new("RGBA", (W - 80, H - 80), (0, 0, 0, 60))
    im.alpha_composite(panel, (40, 40))
    outline = Image.new("RGBA", (W - 60, H - 60), (255, 255, 255, 30))
    im.alpha_composite(outline, (30, 30))
    fg = (235, 245, 255, 255); sub = (210, 225, 255, 255); dim = (190, 205, 230, 255)
    x0, y = 90, 100
    draw.text((x0, y), "Gaia Eyes • Daily EarthScope", fill=fg, font=font_h1); y += 90
    el = (energy_label or "").lower()
    col = (59,201,168,190) if el=="calm" else ((243,193,75,190) if el=="elevated" else ((239,106,106,190) if el=="high" else (104,162,224,190)))
    _draw_badge(im, draw, f"Energy: {energy_label}", (x0, y), fill=col, font=font_h2); y += 70
    y += 36  # extra spacing under badge (no inline stats here)

    def section(head: str, body: str) -> None:
        nonlocal y
        draw.text((x0, y), head, fill=sub, font=font_h2); y += 50
        lines = _wrap(draw, body, font_body, W - x0 - 120)
        for ln in lines:
            draw.text((x0, y), ln, fill=fg, font=font_body); y += 46
        y += 16

    mood = strip_hashtags_and_emojis(mood)
    section("How it may feel", mood)
    _overlay_logo_and_tagline(im, "Decode the unseen.")
    return im.convert("RGB")

# ---------------------------------------
# Stats card renderer
# ---------------------------------------
def render_stats_card_from_features(
    day: dt.date,
    feats: dict,
    energy: Optional[str] = None,
    kind: str = "square",
    pulse: Optional[dict] = None,
) -> Image.Image:
    if kind == "tall":
        W, H = 1080, 1350
    else:
        W, H = 1080, 1080
    im = _compose_bg(W, H, energy, kind)
    draw = ImageDraw.Draw(im)
    font_h1   = _load_font(["BebasNeue.ttf", "ChangeOne-Regular.ttf", "AbrilFatface-Regular.ttf", "Oswald-Bold.ttf"], 68)
    font_h2   = _load_font(["Oswald-Bold.ttf", "AbrilFatface-Regular.ttf"], 40)
    font_body = _load_font(["Oswald-Regular.ttf", "Poppins-Regular.ttf"], 36)
    fg = (235,245,255,255); dim=(190,205,230,255)

    label = "avg"
    has_t = feats.get("sch_fundamental_avg_hz") is not None
    has_c = feats.get("sch_cumiana_fundamental_avg_hz") is not None
    if has_t and not has_c: label = "Tomsk"
    elif has_c and not has_t: label = "Cumiana"

    x0, y0 = 80, 96
    header_txt = "EarthScope • Today’s Metrics"
    date_txt   = day.strftime('%b %d, %Y')
    header_w = draw.textlength(header_txt, font=font_h1)
    date_w   = draw.textlength(date_txt,   font=font_h1)
    gap = 40; max_w = W - 2*x0
    if header_w + gap + date_w <= max_w:
        _shadowed_text(draw, (x0, y0), header_txt, font=font_h1, fill=fg)
        _shadowed_text(draw, (x0 + int(header_w + gap), y0), f" —  {date_txt}", font=font_h1, fill=fg)
        y = y0 + 94
    else:
        _shadowed_text(draw, (x0, y0), header_txt, font=font_h1, fill=fg)
        date_x = x0 + max(0, int(min(header_w, max_w) - date_w))
        _shadowed_text(draw, (date_x, y0 + 74), date_txt, font=font_h1, fill=fg)
        y = y0 + 148

    el = (energy or "").lower()
    col = (59,201,168,190) if el=="calm" else ((243,193,75,190) if el=="elevated" else ((239,106,106,190) if el=="high" else (104,162,224,190)))
    _draw_badge(im, draw, f"Energy: {energy}", (x0, y-10), fill=col, font=font_h2)
    y += 70

    panel_top = max(180, y + 10)
    panel_box = (80, panel_top, W - 80, H - 140)
    _blur_panel(im, panel_box, blur_radius=6, panel_alpha=70)

    # Format helpers: show em dash when missing
    def _fmt_float(val: Optional[float], nd: int = 2, unit: str = "") -> str:
        if val is None:
            return "—" if not unit else f"— {unit}".strip()
        try:
            s = f"{float(val):.{nd}f}"
        except Exception:
            return "—" if not unit else f"— {unit}".strip()
        return f"{s} {unit}".strip()

    def _fmt_int(val: Optional[float]) -> str:
        if val is None:
            return "—"
        try:
            return str(int(val))
        except Exception:
            return "—"

    sch_val = (
        feats.get("sch_any_fundamental_avg_hz")
        if feats.get("sch_any_fundamental_avg_hz") is not None
        else (feats.get("sch_fundamental_avg_hz") if feats.get("sch_fundamental_avg_hz") is not None
              else (feats.get("sch_cumiana_fundamental_avg_hz") if feats.get("sch_cumiana_fundamental_avg_hz") is not None else None))
    )

    rows = [
        ("Kp (max)", _fmt_float(feats.get("kp_max"), 2), (255,180,60,220), "KP"),
        ("Bz (min)", _fmt_float(feats.get("bz_min"), 2, "nT"), (100,160,220,220), "Bz"),
        ("SW speed", _fmt_float(feats.get("sw_speed_avg"), 0, "km/s"), (80,200,140,220), "SW"),
        (f"Schumann ({label})", _fmt_float(sch_val, 2, "Hz"), (160,120,240,220), "Sch"),
        ("Flares", _fmt_int(feats.get("flares_count")), (240,120,120,220), "Fl"),
        ("CMEs", _fmt_int(feats.get("cmes_count")), (240,160,120,220), "CM"),
    ]

    # Inject pulse rows up with the stats (not under Did you know)
    if isinstance(pulse, dict):
        aur_head = pulse.get("aurora_headline")
        aur_win  = pulse.get("aurora_window")
        if aur_head:
            aur_txt = str(aur_head)
            if aur_win:
                aur_txt += f" — {aur_win}"
            rows.append(("Aurora", aur_txt, (120,200,255,220), "Au"))
        if pulse.get("quakes_count"):
            rows.append(("Earthquakes", "recent notable events logged", (255,190,120,220), "Eq"))
    font_val = _load_font(["Oswald-Bold.ttf", "Oswald-Regular.ttf", "Poppins-Regular.ttf", "Menlo.ttf", "Courier New.ttf"], 48)
    chip_font = _load_font(["Oswald-Bold.ttf", "Poppins-Regular.ttf", "Arial.ttf"], 26)

    def _chip(draw: ImageDraw.ImageDraw, x:int, y:int, color:tuple, txt:str):
        r = 22
        draw.ellipse([x, y, x+2*r, y+2*r], fill=color, outline=(0,0,0,140), width=2)
        tw = int(draw.textlength(txt, font=chip_font))
        tx = x + r - tw//2
        ty = y + r - chip_font.size//2 - 2
        draw.text((tx+1,ty+1), txt, font=chip_font, fill=(0,0,0,160))
        draw.text((tx,ty), txt, font=chip_font, fill=(255,255,255,235))

    x_label, x_val = 160, W//2 + 80
    draw.text((x_label+2, y+2), "Metric", fill=(0,0,0,160), font=font_h2)
    draw.text((x_val+2, y+2), "Value",  fill=(0,0,0,160), font=font_h2)
    draw.text((x_label, y), "Metric", fill=dim, font=font_h2)
    draw.text((x_val, y), "Value",  fill=dim, font=font_h2)
    y += 56
    draw.line([(110, y), (W-110, y)], fill=(255,255,255,30), width=2)
    y += 24

    for lab, val, colr, abbr in rows:
        _chip(draw, x_label-56, y+2, colr, abbr)
        draw.text((x_label+2, y+2), lab, fill=(0,0,0,160), font=font_body)
        draw.text((x_label, y), lab, fill=fg, font=font_body)
        draw.text((x_val+2, y+2), val, fill=(0,0,0,160), font=font_val)
        draw.text((x_val, y), val, fill=fg, font=font_val)
        y += 56

    # Stats card Did you know:
    y += 40
    did_font = _load_font(["Oswald-Bold.ttf", "Poppins-Regular.ttf"], 36)
    facts = [
        "Did you know? Solar storms can affect human heart-rate variability.",
        "Did you know? Schumann resonance is linked to brainwave frequencies.",
        "Did you know? Geomagnetic activity may influence sleep quality.",
    ]
    fact = random.choice(facts)
    y = _draw_wrapped_multilines(draw, fact, did_font, x_label, y, W - x_label - 120, line_gap=56)
    y = min(y, H - 160)
    _overlay_logo_and_tagline(im, "Decode the unseen.")
    return im.convert("RGB")

def render_text_card(title: str, body: str, energy: Optional[str] = None, kind: str = "square") -> Image.Image:
    if kind == "tall":
        W, H = 1080, 1350
    else:
        W, H = 1080, 1080
    im = _compose_bg(W, H, energy, kind)
    draw = ImageDraw.Draw(im)
    font_h1   = _load_font(["BebasNeue.ttf", "ChangeOne-Regular.ttf", "AbrilFatface-Regular.ttf", "Oswald-Bold.ttf"], 66)
    font_body = _load_font(["Oswald-Regular.ttf", "Poppins-Regular.ttf"], 36)
    fg = (235,245,255,255)
    x0, y = 80, 120
    title = _safe_text(title); body = _safe_text(body)

    # Split out special sub-sections if present
    tip_head = None; tip_body = None
    aff_head = None; aff_body = None
    if "QUICK TIP:" in body:
        parts = body.split("QUICK TIP:", 1)
        body = parts[0].rstrip()
        tip_head, tip_body = "QUICK TIP:", parts[1].strip()
    if "DAILY COSMIC AFFIRMATION:" in body:
        parts = body.split("DAILY COSMIC AFFIRMATION:", 1)
        body = parts[0].rstrip()
        aff_head, aff_body = "DAILY COSMIC AFFIRMATION:", parts[1].strip()
    # If both were present originally (due to ordering), ensure we didn't drop one
    # by checking original text again
    if tip_head is None and "QUICK TIP:" in (aff_body or ""):
        sub = aff_body.split("QUICK TIP:", 1)
        aff_body = sub[0].rstrip()
        tip_head, tip_body = "QUICK TIP:", sub[1].strip()
    if aff_head is None and "DAILY COSMIC AFFIRMATION:" in (tip_body or ""):
        sub = tip_body.split("DAILY COSMIC AFFIRMATION:", 1)
        tip_body = sub[0].rstrip()
        aff_head, aff_body = "DAILY COSMIC AFFIRMATION:", sub[1].strip()

    # Daily headers for affects/care cards
    title_norm = (title or "").strip().lower()
    if title_norm in ("how this affects you", "how it may feel"):
        header = f"Daily EarthScope • {dt.datetime.utcnow().strftime('%b %d, %Y')}"
        _shadowed_text(draw, (x0, y), header, font=font_h1, fill=fg)
        y += 70
    if title_norm in ("self-care playbook", "care notes"):
        header = f"Daily EarthScope • {dt.datetime.utcnow().strftime('%b %d, %Y')}"
        _shadowed_text(draw, (x0, y), header, font=font_h1, fill=fg)
        y += 70

    _shadowed_text(draw, (x0, y), title, font=font_h1, fill=fg); y += 80

    # Normalize lists: bullets or numbered -> bullet list (applies to body only)
    if " - " in body or body.strip().startswith("-") or re.match(r"^\d+\.\s", body.strip()):
        cleaned = body.replace("\r", "").strip()
        lines = [ln.strip() for ln in cleaned.split("\n") if ln.strip()]
        parts = []
        for ln in lines:
            ln = re.sub(r"^(?:[-•]\s*|\d+\.)\s*", "", ln).strip()
            if not ln:
                continue
            # Skip if the line is just dashes or punctuation (e.g. "--", "--.", "—")
            if re.match(r"^[\-\.\u2013\u2014]+$", ln):
                continue
            if not ln.endswith((".", "!", "?")):
                ln += "."
            parts.append(ln)
        # Normalize bullets: strip emojis, normalize headings, and keyword casing
        processed = []
        for p in parts:
            # Strip emojis
            try:
                p = _EMOJI_PATTERN.sub("", p)
            except Exception:
                pass
            # Normalize "**Label:** text" → "LABEL: text"
            m = re.match(r"^\**\s*([^:*]+?)\s*\**\s*:\s*(.*)", p)
            if m:
                head = m.group(1).strip().upper()
                rest = m.group(2).strip()
                p = f"{head}: {rest}" if rest else f"{head}:"
            else:
                # Also normalize common keywords if they appear
                for kw in ("Mood", "Energy", "Heart", "Nervous System"):
                    if p.lower().startswith(kw.lower()):
                        p = kw.upper() + p[len(kw):]
                        break
            p = p.replace("**", "").strip()
            processed.append(p)
        body = "\n".join([f"• {p}" for p in processed])

    y = _draw_wrapped_multilines(draw, body, font_body, x0, y, W - x0 - 120, line_gap=54)
    # reserve footer space before special sections
    safe_bottom = H - 170

    # Render special sub-sections without bullets
    if tip_head and tip_body:
        y += 24
        _shadowed_text(draw, (x0, y), tip_head, font=font_h1, fill=fg); y += 60
        y = _draw_wrapped_to_bottom(draw, tip_body, font_body, x0, y, W - x0 - 120, bottom=safe_bottom, line_gap=54)
    if aff_head and aff_body:
        y += 24
        _shadowed_text(draw, (x0, y), aff_head, font=font_h1, fill=fg); y += 60
        y = _draw_wrapped_to_bottom(draw, aff_body, font_body, x0, y, W - x0 - 120, bottom=safe_bottom, line_gap=54)

    _overlay_logo_and_tagline(im, "Decode the unseen.")
    return im.convert("RGB")

# -------------------------
# FILE WRITERS
# -------------------------
def save_images(sch: float, kp: float, energy: str, mood: str, tip: str) -> Tuple[Path, Path]:
    ensure_repo_paths()
    im = render_card(energy, mood, sch, kp)
    ts = dt.datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")
    local_path = OUTPUT_DIR / f"earthscope_{ts}.jpg"
    im.save(local_path, format="JPEG", quality=90)
    logging.info(f"Saved image (local): {local_path}")
    im.save(IMG_PATH_REPO, format="JPEG", quality=90)
    logging.info(f"Saved image (repo):  {IMG_PATH_REPO}")
    return local_path, IMG_PATH_REPO

def write_json_csv(payload: dict) -> None:
    ensure_repo_paths()
    with open(JSON_PATH_REPO, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    header = [
        "timestamp_utc","kp_index","kp_time_utc","kp_band","storm_warning","storm_level",
        "schumann_hz","schumann_amp","aqi","aqi_city","image_path","image_url_hint","commit_sha"
    ]
    with open(CSV_PATH_REPO, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(header); w.writerow([payload.get(k) for k in header])

def save_all_cards(stats_im: Image.Image, caption_im: Image.Image, affects_im: Image.Image, play_im: Image.Image) -> list:
    ensure_repo_paths()
    out = []
    stats_p = MEDIA_REPO_PATH / "images" / "daily_stats.jpg"; stats_im.save(stats_p, "JPEG", quality=90); out.append(stats_p)
    cap_p   = MEDIA_REPO_PATH / "images" / "daily_caption.jpg"; caption_im.save(cap_p, "JPEG", quality=90); out.append(cap_p)
    aff_p   = MEDIA_REPO_PATH / "images" / "daily_affects.jpg"; affects_im.save(aff_p, "JPEG", quality=90); out.append(aff_p)
    play_p  = MEDIA_REPO_PATH / "images" / "daily_playbook.jpg"; play_im.save(play_p, "JPEG", quality=90); out.append(play_p)
    logging.info("Saved 4 images into repo/images/")
    return out

# -------------------------
# GIT HELPERS
# -------------------------
def git_run(args: list) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True)

def git_commit_push(paths: list) -> str:
    add = git_run(["git", "-C", str(MEDIA_REPO_PATH), "add"] + [str(p) for p in paths])
    if add.returncode != 0: raise RuntimeError(add.stderr.strip())
    cm = git_run(["git", "-C", str(MEDIA_REPO_PATH), "commit", "-m", f"daily: update image and data ({utcnow_iso()})"])
    if cm.returncode != 0 and "nothing to commit" not in (cm.stderr or "").lower():
        raise RuntimeError(f"git commit failed: {cm.stderr.strip()}")
    pr = git_run(["git", "-C", str(MEDIA_REPO_PATH), "pull", "--rebase", "origin", "main"])
    if pr.returncode != 0:
        git_run(["git", "-C", str(MEDIA_REPO_PATH), "stash", "push", "-u", "-m", "auto-stash"])
        pr2 = git_run(["git", "-C", str(MEDIA_REPO_PATH), "pull", "--rebase", "origin", "main"])
        if pr2.returncode == 0: git_run(["git", "-C", str(MEDIA_REPO_PATH), "stash", "pop"])
        else: raise RuntimeError(pr.stderr.strip())
    ps = git_run(["git", "-C", str(MEDIA_REPO_PATH), "push"])
    if ps.returncode != 0: raise RuntimeError(f"git push failed: {ps.stderr.strip()}")
    sha = git_run(["git", "-C", str(MEDIA_REPO_PATH), "rev-parse", "--short", "HEAD"])
    return (sha.stdout or "").strip()

# -------------------------
# BAND / PAYLOAD
# -------------------------
def kp_band_for(kp: float) -> str:
    if kp < 2.0: return "calm"
    if kp < 4.0: return "mild"
    if kp < 5.0: return "active"
    return "storm"

def build_payload(ts_iso_utc: str, kp: float, kp_time: Optional[str], sch: float, commit_sha: str) -> dict:
    return {
        "timestamp_utc": ts_iso_utc,
        "kp_index": round(kp, 2),
        "kp_time_utc": kp_time or ts_iso_utc,
        "kp_band": kp_band_for(kp),
        "storm_warning": kp >= 5.0,
        "storm_level": None,
        "schumann_hz": round(sch, 2),
        "schumann_amp": None,
        "aqi": None,
        "aqi_city": None,
        "image_path": "images/dailypost.jpg",
        "image_url_hint": "https://cdn.jsdelivr.net/gh/gennwu/gaiaeyes-media/images/dailypost.jpg",
        "commit_sha": commit_sha
    }

# -------------------------
# MAIN
# -------------------------
def main():
    RUN_BG_USED.clear()
    key_prefix = (SUPABASE_SERVICE_KEY or SUPABASE_ANON_KEY)[:8] if (SUPABASE_SERVICE_KEY or SUPABASE_ANON_KEY) else "(none)"
    logging.info("Supabase REST: url=%s key[0:8]=%s", SUPABASE_REST_URL or "(unset)", key_prefix)

    day = target_day_utc()
    feats_probe = fetch_daily_features_for(day) if SUPABASE_REST_URL else None
    post_probe  = fetch_post_for(day, "default") if SUPABASE_REST_URL else None
    if not TARGET_DAY and not feats_probe and not post_probe:
        latest = fetch_latest_day_from_supabase()
        if latest:
            logging.info("No data for today; rendering latest available day from Supabase: %s", latest.isoformat())
            day = latest

    feats = fetch_daily_features_for(day) if SUPABASE_REST_URL else None
    if feats:
        kp = float(feats.get("kp_max") or 0.0)
        sch_any = feats.get("sch_any_fundamental_avg_hz") or feats.get("sch_fundamental_avg_hz")
        sch = float(sch_any or 7.83)
    else:
        logging.info("No marts.daily_features for target day; using mirror sources")
        sch = fetch_schumann_from_repo_csv(MEDIA_REPO_PATH) or 7.83
        kp = fetch_kp_index()

    # Compute energy/mood/tip early so `tip` is available
    energy, mood, tip = generate_daily_forecast(sch, kp)

    post = fetch_post_for(day, "default") if SUPABASE_REST_URL else None
    if not post and SUPABASE_REST_URL:
        latest = fetch_latest_day_from_supabase()
        if latest and latest != day:
            logging.warning("No post for %s; falling back to latest %s", day.isoformat(), latest.isoformat())
            post = fetch_post_for(latest, "default")
    # Align day with the post we actually used (for header date on tall cards)
    if post and isinstance(post.get("day"), str):
        try:
            day = dt.date.fromisoformat(post["day"])  # adjust header date to post's day
        except Exception:
            pass

    # Try loading media EarthScope card JSON for sections/metrics if Supabase post is missing or outdated
    media_card = load_earthscope_card()
    # Prefer EarthScope media metrics when available (more reliable for flares/CMEs)
    media_metrics = (media_card or {}).get("metrics") if isinstance(media_card, dict) else None
    # Prefer metrics from content.daily_posts.metrics_json when available
    metrics = {}
    if post and post.get("metrics_json"):
        try:
            metrics = json.loads(post["metrics_json"]) if isinstance(post["metrics_json"], str) else (post["metrics_json"] or {})
        except Exception as e:
            logging.warning(f"metrics_json parse failed: {e}")
    if metrics:
        # Map Earthscope metrics_json → feats dict used by stats renderer
        m = metrics
        feats = feats or {}
        # Kp (max 24h)
        if m.get("kp_max_24h") is not None:
            try: feats["kp_max"] = float(m["kp_max_24h"]) 
            except Exception: pass
        # Bz min (optional)
        if m.get("bz_min") is not None:
            try: feats["bz_min"] = float(m["bz_min"]) 
            except Exception: pass
        # Solar wind km/s
        if m.get("solar_wind_kms") is not None:
            try: feats["sw_speed_avg"] = float(m["solar_wind_kms"]) 
            except Exception: pass
        # Flares / CMEs (counts)
        if m.get("flares_24h") is not None:
            try: feats["flares_count"] = int(m["flares_24h"]) 
            except Exception: pass
        if m.get("cmes_24h") is not None:
            try: feats["cmes_count"] = int(m["cmes_24h"]) 
            except Exception: pass
        # Schumann f0
        if m.get("schumann_value_hz") is not None:
            try:
                f0 = float(m["schumann_value_hz"]) 
                feats["sch_any_fundamental_avg_hz"] = f0
            except Exception: pass
                    # Prefer media metrics overrides if present
        if isinstance(media_metrics, dict):
            if media_metrics.get("flares_24h") is not None:
                try: feats["flares_count"] = int(media_metrics["flares_24h"])
                except Exception: pass
            if media_metrics.get("cmes_24h") is not None:
                try: feats["cmes_count"] = int(media_metrics["cmes_24h"])
                except Exception: pass
            if media_metrics.get("kp_max_24h") is not None and feats.get("kp_max") is None:
                try: feats["kp_max"] = float(media_metrics["kp_max_24h"])
                except Exception: pass
            if media_metrics.get("bz_min") is not None and feats.get("bz_min") is None:
                try: feats["bz_min"] = float(media_metrics["bz_min"])
                except Exception: pass
            if media_metrics.get("solar_wind_kms") is not None and feats.get("sw_speed_avg") is None:
                try: feats["sw_speed_avg"] = float(media_metrics["solar_wind_kms"])
                except Exception: pass
            if media_metrics.get("schumann_value_hz") is not None and feats.get("sch_any_fundamental_avg_hz") is None:
                try: feats["sch_any_fundamental_avg_hz"] = float(media_metrics["schumann_value_hz"])
                except Exception: pass
        # Optional harmonics structure (not drawn currently)
        # metrics.get("harmonics") can be kept if needed later

    # If metrics/sections are still empty, prefer media_card contents (new pipeline)
    if (not metrics or not isinstance(metrics, dict) or not metrics.get("sections")) and isinstance(media_card, dict):
        # Seed metrics from media_card if empty
        if media_card.get("metrics") and not metrics:
            metrics = dict(media_card["metrics"])  # seed directly from media card

        # Map a minimal metrics view from media card if available
        m2 = media_card.get("metrics") or {}
        if isinstance(m2, dict):
            metrics = metrics or {}
            # Copy over numeric fields if present
            for k_old, k_new in [
                ("kp_max_24h","kp_max_24h"),
                ("solar_wind_kms","solar_wind_kms"),
                ("flares_24h","flares_24h"),
                ("cmes_24h","cmes_24h"),
                ("schumann_value_hz","schumann_value_hz"),
            ]:
                if m2.get(k_old) is not None and metrics.get(k_new) is None:
                    metrics[k_new] = m2.get(k_old)
            # Deltas/bands/tone may also be present
            if m2.get("deltas"): metrics["deltas"] = m2["deltas"]
            if m2.get("g_headline"): metrics["g_headline"] = m2["g_headline"]
            if m2.get("sections"): metrics["sections"] = m2["sections"]  # pass-through if exists
            if m2.get("bands"): metrics["bands"] = m2["bands"]
            if m2.get("tone"): metrics["tone"] = m2["tone"]

    # Prefer structured sections from metrics_json (caption/affects/playbook) when available
    sections = None
    tone_band_energy = None
    try:
        sections = metrics.get("sections") if isinstance(metrics, dict) else None
    except Exception:
        sections = None
    tone_val = (metrics.get("tone") if isinstance(metrics, dict) else None) or ""
    bands = (metrics.get("bands") if isinstance(metrics, dict) else {}) or {}
    kp_band = (bands.get("kp") or "").lower()
    # Map bands/tone → energy badge
    def _energy_from_tone_and_bands(tone: str, kp_band_str: str) -> str:
        t = (tone or "").lower()
        if t in ("stormy","high"):
            return "High"
        kb = kp_band_str
        if kb in ("storm","severe"):
            return "High"
        if kb in ("active","unsettled","mild"):
            return "Elevated"
        return "Calm"
    if tone_val or kp_band:
        tone_band_energy = _energy_from_tone_and_bands(tone_val, kp_band)

    caption_text = (post or {}).get("caption") or "Daily Earthscope"
    body_md = (post or {}).get("body_markdown") or ""

    # If body_markdown accidentally contains a JSON blob, try to parse and use fields
    if body_md.strip().startswith("{") and '"sections"' in body_md:
        try:
            bdj = json.loads(body_md)
            if isinstance(bdj, dict):
                sec2 = bdj.get("sections") or {}
                if not sections and sec2:
                    sections = sec2
                if not tone_val and bdj.get("tone"):
                    tone_val = bdj.get("tone")
                if not kp_band and isinstance(bdj.get("bands"), dict):
                    kp_band = (bdj["bands"].get("kp") or "").lower()
                if (tone_val or kp_band) and not tone_band_energy:
                    tone_band_energy = _energy_from_tone_and_bands(tone_val, kp_band)
        except Exception:
            pass
    # Override text from structured sections if present
    if isinstance(sections, dict):
        caption_text = sections.get("caption") or caption_text
    elif isinstance(media_card, dict):
        # media_card may use top-level keys (caption/affects/playbook) or a sections{} block
        sec_mc = media_card.get("sections")
        if not isinstance(sec_mc, dict):
            sec_mc = {
                "caption": media_card.get("caption"),
                "snapshot": media_card.get("snapshot"),
                "affects": media_card.get("affects"),
                "playbook": media_card.get("playbook"),
            }
        if isinstance(sec_mc, dict):
            caption_text = sec_mc.get("caption") or caption_text

    # Extract sections (tolerant to Unicode hyphens/dashes and case)
    affects_txt  = extract_any_section(body_md, [
        "How This Affects You",
        "How this affects you",
        "How This Affects You –",
        "How This Affects You —",
        "How This Might Affect You",
        "How this might affect you",
        "How it may feel"
    ]) or ""

    playbook_txt = extract_any_section(body_md, [
        "Self-Care Playbook",      # ASCII hyphen
        "Self‑Care Playbook",      # U+2011 non-breaking hyphen
        "Self–Care Playbook",      # U+2013 en dash
        "Self—Care Playbook",      # U+2014 em dash
        "Self – Care Playbook",    # spaced en dash
        "Self — Care Playbook",    # spaced em dash
        "Self Care Playbook",      # no hyphen
        "Care notes"
    ]) or ""
    # If structured sections exist, prefer them over markdown extraction
    if isinstance(sections, dict):
        affects_txt  = sections.get("affects")  or affects_txt
        playbook_txt = sections.get("playbook") or playbook_txt
    elif isinstance(media_card, dict):
        # media_card may have sections{} or top-level keys
        sec_mc = media_card.get("sections")
        if not isinstance(sec_mc, dict):
            sec_mc = {
                "caption": media_card.get("caption"),
                "snapshot": media_card.get("snapshot"),
                "affects": media_card.get("affects"),
                "playbook": media_card.get("playbook"),
            }
        if isinstance(sec_mc, dict):
            affects_txt  = sec_mc.get("affects")  or affects_txt
            playbook_txt = sec_mc.get("playbook") or playbook_txt
    if not affects_txt or not playbook_txt:
        fa, fp = generate_daily_forecast(sch, kp)[1], " - " + generate_daily_forecast(sch, kp)[2]
        affects_txt = affects_txt or fa
        playbook_txt = playbook_txt or fp
    # Quick Tip placement
    if tip:
        if affects_txt:
            affects_txt = affects_txt.strip() + "\n\nQUICK TIP:\n" + tip.strip()
        else:
            affects_txt = "QUICK TIP:\n" + tip.strip()
    aff_line = get_daily_affirmation()
    # Affirmation placement
    if aff_line:
        if playbook_txt:
            playbook_txt = playbook_txt.strip() + "\n\nDAILY COSMIC AFFIRMATION:\n" + aff_line
        else:
            playbook_txt = "DAILY COSMIC AFFIRMATION:\n" + aff_line

    caption_text = strip_hashtags_and_emojis(_safe_text(caption_text))
    body_md = _safe_text(body_md)
    # Build stats rows from consolidated EarthScope card (daily) if available
    stats_feats = {}
    pulse_like  = {}
    if isinstance(media_card, dict):
        mm = media_card.get("metrics") or {}
        if isinstance(mm, dict):
            # Map to stats renderer keys
            if mm.get("kp_max_24h") is not None:
                try: stats_feats["kp_max"] = float(mm["kp_max_24h"])
                except Exception: pass
            if mm.get("bz_min") is not None:
                try: stats_feats["bz_min"] = float(mm["bz_min"])
                except Exception: pass
            if mm.get("solar_wind_kms") is not None:
                try: stats_feats["sw_speed_avg"] = float(mm["solar_wind_kms"])
                except Exception: pass
            if mm.get("schumann_value_hz") is not None:
                try: stats_feats["sch_any_fundamental_avg_hz"] = float(mm["schumann_value_hz"])
                except Exception: pass
            if mm.get("flares_24h") is not None:
                try: stats_feats["flares_count"] = int(mm["flares_24h"])
                except Exception: pass
            if mm.get("cmes_24h") is not None:
                try: stats_feats["cmes_count"] = int(mm["cmes_24h"])
                except Exception: pass
            # Aurora hints (for a chip row)
            sx = mm.get("space_json") or {}
            if isinstance(sx, dict):
                if sx.get("aurora_headline"):
                    pulse_like["aurora_headline"] = str(sx.get("aurora_headline"))
                if sx.get("aurora_window"):
                    pulse_like["aurora_window"]   = str(sx.get("aurora_window"))
        # Quakes count (optional indicator)
        qk = media_card.get("quakes") or {}
        if isinstance(qk, dict) and qk.get("total_24h"):
            pulse_like["quakes_count"] = int(qk.get("total_24h"))
    # Fallback: if we didn’t assemble anything from media, reuse feats mapped from Supabase above
    base_feats = stats_feats or (feats or {})
    stats_im   = render_stats_card_from_features(day, base_feats, energy, kind="tall", pulse=pulse_like)
    if isinstance(caption_text, (dict, list)):
        caption_text = json.dumps(caption_text, ensure_ascii=False)
    if hasattr(caption_text, "strip"):
        caption_text = caption_text.strip()

    # Override energy label from tone/bands if provided by metrics_json
    if tone_band_energy:
        energy = tone_band_energy
    elif isinstance(media_card, dict):
        m2 = media_card.get("metrics") or {}
        bands2 = m2.get("bands") or {}
        tone2  = (m2.get("tone") or "").lower()
        kb2    = (bands2.get("kp") or "").lower()
        if tone2 or kb2:
            def _energy_from_tb(t, kb):
                if t in ("stormy","high"): return "High"
                if kb in ("storm","severe"): return "High"
                if kb in ("active","unsettled","mild"): return "Elevated"
                return "Calm"
            energy = _energy_from_tb(tone2, kb2)

    # Strip hashtags/emojis from affects/playbook text for layout robustness
    affects_txt  = strip_hashtags_and_emojis(_safe_text(affects_txt))
    playbook_txt = strip_hashtags_and_emojis(_safe_text(playbook_txt))

    caption_im = render_card(energy, caption_text, sch, kp, kind="square")
    affects_im = render_text_card("How it may feel", affects_txt, energy, kind="tall")
    play_im    = render_text_card("Care notes", playbook_txt, energy, kind="tall")

    repo_paths = save_all_cards(stats_im, caption_im, affects_im, play_im)

    try:
        sha1 = git_commit_push(repo_paths)
    except Exception as e:
        logging.error(f"git push (images) failed: {e}")

    ts_iso = utcnow_iso()
    payload = build_payload(ts_iso, kp, None, sch, "")
    write_json_csv(payload)
    try:
        sha2 = git_commit_push([JSON_PATH_REPO, CSV_PATH_REPO])
    except Exception as e:
        logging.error(f"git push (data) failed: {e}")

    logging.info("✅ Done. Generated 4 images + data artifacts.")

if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.exception("Run failed")
        sys.exit(1)
