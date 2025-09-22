#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Earthscope (Supabase-first)
- Reads daily aggregates from Supabase marts:
    marts.space_weather_daily  (kp_max, bz_min, sw_speed_avg, flares_count, cmes_count)
    marts.schumann_daily       (station_id in {tomsk,cumiana}, f0_avg_hz, f1_avg_hz, f2_avg_hz, h3_avg_hz, h4_avg_hz)
- Generates short caption + long 3-section forecast (OpenAI optional)
- Upserts one row per date into Supabase posts table (default: earthscope_posts)

Notes:
- Google Sheets writes are disabled in this version.
- If OpenAI key is missing, falls back to deterministic copy using numbers.
"""

import os, json, argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List

import requests
from dotenv import load_dotenv

# Supabase
from supabase import create_client

# Optional: OpenAI (LLM)
try:
    from openai import OpenAI
    HAVE_OPENAI = True
except Exception:
    HAVE_OPENAI = False

# ============================================================
# Env / Clients
# ============================================================
BASE_DIR = Path(__file__).parent
ENV_PATH = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")
POSTS_SCHEMA = os.getenv("SUPABASE_POSTS_SCHEMA", "content")
POSTS_TABLE  = os.getenv("SUPABASE_POSTS_TABLE", "daily_posts")
SPACE_SCHEMA = os.getenv("SUPABASE_MARTS_SCHEMA", "marts")
SW_TABLE     = os.getenv("SUPABASE_SW_TABLE", "space_weather_daily")
SR_TABLE     = os.getenv("SUPABASE_SR_TABLE", "schumann_daily")
DAY_COLUMN   = os.getenv("SUPABASE_DAY_COLUMN", "day")
PLATFORM     = os.getenv("EARTHSCOPE_PLATFORM", "default")
USER_ID      = os.getenv("EARTHSCOPE_USER_ID", None)

# --- Hook mode toggles ---
HOOK_MODE = os.getenv("EARTHSCOPE_HOOK_MODE", "guard").strip().lower()  # guard | blend | always
HOOK_BLEND_P = float(os.getenv("EARTHSCOPE_HOOK_BLEND_P", "0.35"))       # used when HOOK_MODE=blend

if not SUPABASE_URL or not SUPABASE_KEY:
    raise SystemExit("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in .env")

SB = create_client(SUPABASE_URL, SUPABASE_KEY)

# ============================================================
# Helpers
# ============================================================

def today_iso_local() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def to_float(x):
    try:
        if x is None:
            return None
        if isinstance(x, str) and x.strip() == "":
            return None
        return float(x)
    except Exception:
        return None

# --- text sanitizers ---
def _strip_intro_header(block: str) -> str:
    """Remove any leading top-level header line the model might add."""
    if not block:
        return block
    lines = [l for l in block.splitlines()]
    # drop leading empty lines
    while lines and not lines[0].strip():
        lines.pop(0)
    if lines:
        head = lines[0].strip()
        if head.startswith("###") or head.startswith("##") or (head.startswith("**") and "Gaia Eyes" in head):
            lines = lines[1:]
    return "\n".join(lines).strip()

# --- hook + tone system (no questions, no "Feeling...", no emojis) ---
import random, re

BAN_STARTS = ("feeling ", "are you ", "ever feel ", "ready to ", "it’s time", "its time", "let’s ", "lets ")
EMOJI_RE = re.compile(r"[\U00010000-\U0010ffff]", flags=re.UNICODE)

HOOKS = {
    "calm": [
        "Quieter field today—good for deep focus.",
        "Calm geomagnetics; lock in your rhythm.",
        "Steady skies, steady mind.",
        "Low Kp, longer runway for clarity.",
        "Baseline is smooth—use your late‑morning window.",
        "Stable backdrop—clean shots at focus blocks.",
        "Quiet day upstairs—keep it simple and sharp.",
        "Magnetic weather is tame—work the plan.",
    ],
    "unsettled": [
        "Small waves, not a storm—pace beats push.",
        "Pulse‑and‑dip kind of day.",
        "A few bumps on the line; keep cadence.",
        "Unsettled doesn’t mean unworkable—buffer your peaks.",
        "Short surges, brief dips—ride the middle.",
        "Minor fluctuation day—aim for steady cadence.",
        "Some texture in the field—stay rhythmic.",
        "Patchy flow—tighten your timing windows.",
    ],
    "stormy": [
        "Charged air today—keep your cadence tight.",
        "Storm‑leaning field—short bursts, longer recoveries.",
        "Expect a punchy arc today.",
        "Strong coupling window—step lightly.",
        "Spiky profile—protect the edges of your day.",
        "Lively magnetics—move with firm guardrails.",
        "High‑gain conditions—keep resets close.",
        "Aurora‑style volatility—work in clips, not sprints.",
    ],
    "neutral": [
        "Straightforward field—set your tempo.",
        "No big swings on the board.",
        "Good canvas—paint a clear day.",
        "Ordinary profile—make ordinary work count.",
        "Middle‑of‑the‑road day—consistency wins.",
        "Plain sailing—don’t overcomplicate it.",
    ],
}

def _tone_from_ctx(ctx: Dict[str, Any]) -> str:
    kp = ctx.get("kp_max_24h"); bz = ctx.get("bz_min"); wind = ctx.get("solar_wind_kms")
    try:
        kpf = float(kp) if kp is not None else None
        bzf = float(bz) if bz is not None else None
        wf  = float(wind) if wind is not None else None
    except Exception:
        kpf = bzf = wf = None
    if (kpf is not None and kpf >= 5) or (bzf is not None and bzf <= -6):
        return "stormy"
    if kpf is not None and kpf > 2.67:
        return "unsettled"
    if (kpf is not None and kpf <= 2.67) and (bzf is None or bzf >= 0):
        return "calm"
    return "neutral"

def _daily_seed() -> int:
    return int(datetime.utcnow().strftime("%Y%m%d"))


# --- Recent opener helpers for hook variation ---
SENT_SPLIT_RE = re.compile(r"(?<=\.)\s+|(?<=! )\s+|(?<=\?)\s+", re.X)

def _first_sentence(txt: str) -> str:
    if not txt: return ""
    parts = SENT_SPLIT_RE.split(txt.strip(), maxsplit=1)
    return parts[0].strip() if parts else txt.strip()

def _recent_openers(days_back: int = 7) -> set:
    try:
        since = (datetime.utcnow() - timedelta(days=days_back)).date().isoformat()
        res = (
            SB.schema(POSTS_SCHEMA)
              .table(POSTS_TABLE)
              .select("day,caption,platform")
              .gte("day", since)
              .order("day", desc=True)
              .limit(20)
              .execute()
        )
        rows = res.data or []
        opens = set()
        for r in rows:
            cap = r.get("caption") or ""
            if cap:
                opens.add(_first_sentence(cap).lower())
        return opens
    except Exception:
        return set()

def _pick_hook(tone: str, last_used: set | None = None) -> str:
    pool = HOOKS.get(tone) or HOOKS["neutral"]
    random.seed(_daily_seed() + hash(tone))
    candidates = pool.copy()
    random.shuffle(candidates)
    if last_used:
        filtered = [h for h in candidates if _first_sentence(h).lower() not in last_used]
        if filtered:
            candidates = filtered
    return candidates[0]

def _sanitize_caption(txt: str) -> str:
    if not txt:
        return ""
    s = txt.strip()
    # drop emojis
    s = EMOJI_RE.sub("", s)
    # collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _needs_rehook(s: str) -> bool:
    if not s: return True
    head = s.strip().lower()
    if any(head.startswith(b) for b in BAN_STARTS):
        return True
    if head.endswith("?"):
        return True
    return False

# --- deterministic snapshot builder ---
def _build_snapshot_md(ctx: Dict[str, Any]) -> str:
    bullets: List[str] = []
    kp_now = ctx.get("kp_now")
    kp_max = ctx.get("kp_max_24h")
    wind   = ctx.get("solar_wind_kms")
    flr    = ctx.get("flares_24h")
    cme    = ctx.get("cmes_24h")
    sr     = ctx.get("schumann_value_hz")

    if kp_now is not None:
        bullets.append(f"- Kp now: {round(float(kp_now), 2)}")
    if kp_max is not None:
        bullets.append(f"- Kp max (24h): {round(float(kp_max), 2)}")
    if wind is not None:
        bullets.append(f"- Solar wind: {round(float(wind), 1)} km/s")
    if flr is not None:
        bullets.append(f"- Flares (24h): {int(round(float(flr)))}")
    if cme is not None:
        bullets.append(f"- CMEs (24h): {int(round(float(cme)))}")
    if sr is not None:
        bullets.append(f"- Schumann f0: {round(float(sr), 2)} Hz")

    return "Space Weather Snapshot\n" + "\n".join(bullets)

# ============================================================
# Data fetch: Supabase marts
# ============================================================

def fetch_space_weather_from_marts(day: str) -> Dict[str, Any]:
    """Fetch one daily row from marts.space_weather_daily for the given date.
    Expected fields: kp_max, bz_min, sw_speed_avg, flares_count, cmes_count
    """
    try:
        res = (
            SB.schema(SPACE_SCHEMA)
              .table(SW_TABLE)
              .select("*")
              .eq(DAY_COLUMN, day)
              .limit(1)
              .execute()
        )
        row = (res.data or [None])[0]
        if not row:
            return {}
        return {
            "kp_max_24h": to_float(row.get("kp_max")),
            "bz_min": to_float(row.get("bz_min")),
            "solar_wind_kms": to_float(row.get("sw_speed_avg")),
            "flares_24h": to_float(row.get("flares_count")) or 0,
            "cmes_24h": to_float(row.get("cmes_count")) or 0,
        }
    except Exception as e:
        print(f"[WARN] space_weather_daily fetch failed: {e}")
        return {}


def _avg_non_null(values: List[Optional[float]]) -> Optional[float]:
    vals = [v for v in values if v is not None]
    return round(sum(vals)/len(vals), 2) if vals else None


def fetch_schumann_from_marts(day: str) -> Dict[str, Any]:
    """Fetch Schumann fundamentals/harmonics for the given day.
    Robust to station_id variants and to missing exact-day rows (falls back to latest <= day).
    Computes f0 and harmonics by averaging across Tomsk/Cumiana if present, else across all.
    """
    def _avg(xs: List[Optional[float]]) -> Optional[float]:
        vals = [v for v in xs if isinstance(v, (int, float)) and v is not None]
        return round(sum(vals) / len(vals), 2) if vals else None

    try:
        # 1) Try exact day first
        res = (
            SB.schema(SPACE_SCHEMA)
              .table(SR_TABLE)
              .select("*")
              .eq(DAY_COLUMN, day)
              .execute()
        )
        rows = res.data or []

        # 2) If no rows for that day, fall back to latest <= day
        if not rows:
            fb = (
                SB.schema(SPACE_SCHEMA)
                  .table(SR_TABLE)
                  .select("*")
                  .lte(DAY_COLUMN, day)
                  .order(DAY_COLUMN, desc=True)
                  .limit(4)
                  .execute()
            )
            rows = fb.data or []
            if not rows:
                print(f"[WARN] schumann_daily: no rows for {day} or earlier")
                return {}

        # Map by station substring (avoid brittle exact matches)
        tomsk_rows: List[Dict[str, Any]] = []
        cumiana_rows: List[Dict[str, Any]] = []
        other_rows: List[Dict[str, Any]] = []
        for r in rows:
            sid = (r.get("station_id") or "").lower()
            if "tomsk" in sid:
                tomsk_rows.append(r)
            elif "cumiana" in sid:
                cumiana_rows.append(r)
            else:
                other_rows.append(r)

        def _collect(key: str, coll: List[Dict[str, Any]]) -> List[Optional[float]]:
            vals: List[Optional[float]] = []
            for rr in coll:
                v = rr.get(key)
                try:
                    vals.append(float(v) if v is not None and str(v) != "" else None)
                except Exception:
                    vals.append(None)
            return vals

        # Compute averages per station group, then overall
        f0_t = _avg(_collect("f0_avg_hz", tomsk_rows))
        f0_c = _avg(_collect("f0_avg_hz", cumiana_rows))
        f1_t = _avg(_collect("f1_avg_hz", tomsk_rows))
        f1_c = _avg(_collect("f1_avg_hz", cumiana_rows))
        f2_t = _avg(_collect("f2_avg_hz", tomsk_rows))
        f2_c = _avg(_collect("f2_avg_hz", cumiana_rows))
        h3_t = _avg(_collect("h3_avg_hz", tomsk_rows))
        h3_c = _avg(_collect("h3_avg_hz", cumiana_rows))
        # Some datasets use h4_avg or h4_avg_hz
        def _h4_key(rr: Dict[str, Any]) -> Optional[float]:
            v = rr.get("h4_avg_hz", rr.get("h4_avg"))
            try:
                return float(v) if v is not None and str(v) != "" else None
            except Exception:
                return None
        h4_t = _avg([_h4_key(rr) for rr in tomsk_rows])
        h4_c = _avg([_h4_key(rr) for rr in cumiana_rows])

        # If we didn't get station-specific rows, average across *all* available rows
        def _avg_all(col: str) -> Optional[float]:
            vals: List[Optional[float]] = []
            for rr in rows:
                v = rr.get(col)
                try:
                    vals.append(float(v) if v is not None and str(v) != "" else None)
                except Exception:
                    vals.append(None)
            return _avg(vals)

        f0 = _avg([v for v in [f0_t, f0_c] if v is not None]) or _avg_all("f0_avg_hz")
        f1 = _avg([v for v in [f1_t, f1_c] if v is not None]) or _avg_all("f1_avg_hz")
        f2 = _avg([v for v in [f2_t, f2_c] if v is not None]) or _avg_all("f2_avg_hz")
        h3 = _avg([v for v in [h3_t, h3_c] if v is not None]) or _avg_all("h3_avg_hz")
        # Handle h4 key variants
        h4_all = []
        for rr in rows:
            h4v = rr.get("h4_avg_hz", rr.get("h4_avg"))
            try:
                h4_all.append(float(h4v) if h4v is not None and str(h4v) != "" else None)
            except Exception:
                h4_all.append(None)
        h4 = _avg([v for v in [h4_t, h4_c] if v is not None]) or _avg(h4_all)

        stations = []
        if tomsk_rows: stations.append("tomsk")
        if cumiana_rows: stations.append("cumiana")
        if other_rows: stations.append("other")
        used = ",".join(stations) if stations else "none"
        note = f"Schumann f0 from {used}; harmonics averaged across available stations."

        return {
            "schumann_value_hz": f0,
            "schumann_harmonics": {"f1": f1, "f2": f2, "h3": h3, "h4": h4},
            "schumann_note": note,
        }
    except Exception as e:
        print(f"[WARN] schumann_daily fetch failed: {e}")
        return {}

# ============================================================
# LLM (spreadsheet-style copy)
# ============================================================

def openai_client() -> Optional[OpenAI]:
    if not HAVE_OPENAI:
        return None
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        return OpenAI()
    except Exception:
        return None


def generate_short_caption(ctx: Dict[str, Any]) -> (str, str):
    client = openai_client()
    kp_now = ctx.get("kp_now")
    kp_max = ctx.get("kp_max_24h")
    wind   = ctx.get("solar_wind_kms")
    flr    = ctx.get("flares_24h")
    cme    = ctx.get("cmes_24h")
    sr     = ctx.get("schumann_value_hz")
    sr_note= ctx.get("schumann_note")

    if not client:
        # Deterministic fallback
        tone = _tone_from_ctx(ctx)
        last_used = _recent_openers(7)
        hook = _pick_hook(tone, last_used=last_used)
        cap = (f"{hook} Kp max {kp_max}, wind {wind} km/s, flares {int(flr)} CMEs {int(cme)}. "
               f"Schumann ~{sr} Hz." )
        tags = "#GaiaEyes #SpaceWeather #KpIndex #SolarWind #Aurora"
        return cap, tags

    model = os.getenv("GAIA_OPENAI_MODEL", "gpt-4o-mini")
    try:
        resp = client.chat.completions.create(
            model=model,
            temperature=0.9,
            presence_penalty=0.6,
            frequency_penalty=0.4,
            max_tokens=320,
            messages=[
                {"role":"system","content":(
                    "You are Gaia Eyes' space‑weather writer. Write an accurate, human, declarative caption. "
                    "Do not start with questions or phrases like 'Feeling', 'Are you', 'Ever feel', 'Ready to', 'Let’s'. "
                    "Never use emojis. Vary openings day‑to‑day."
                )},
                {"role":"user","content":(
                    "Using the data below, write one short, viral‑friendly caption for Gaia Eyes. "
                    "Start with a declarative, data‑aware hook (4–10 words). No questions. No emojis. "
                    "Relate concisely (one sentence max) to mood/energy/heart/nervous system—only if consistent with the data (calm vs stormy). "
                    "On the final line include 4–6 relevant hashtags. ≤600 chars. Render flare/CME counts as integers.\n\n"
                    f"Kp max (24h): {kp_max}\nSolar wind (km/s): {wind}\nFlares (24h): {flr}\nCMEs (24h): {cme}\nSchumann: {sr} Hz ({sr_note})"
                )},
            ],
        )
        text = resp.choices[0].message.content.strip()
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        hashtags = ""
        caption = text
        if lines and lines[-1].startswith("#"):
            hashtags = lines[-1]
            caption = "\n".join(lines[:-1]).strip()
        if not hashtags:
            hashtags = "#GaiaEyes #SpaceWeather #KpIndex #SolarWind #Aurora"
        # Post‑process: sanitize and fix repetitive/question intros
        caption = _sanitize_caption(caption)
        doit = False
        if HOOK_MODE == "always":
            doit = True
        elif HOOK_MODE == "blend":
            doit = _needs_rehook(caption) or (random.random() < HOOK_BLEND_P)
        else:  # guard
            doit = _needs_rehook(caption)
        if doit:
            tone = _tone_from_ctx(ctx)
            last_used = _recent_openers(7)
            hook = _pick_hook(tone, last_used=last_used)
            first_split = re.split(r"(?<=\.)\s+", caption, maxsplit=1)
            rest = first_split[1] if len(first_split) > 1 else caption
            caption = f"{hook} {rest}".strip()
        # ensure hashtags exist
        if not hashtags:
            hashtags = "#GaiaEyes #SpaceWeather #KpIndex #SolarWind #Aurora"
        return caption, hashtags
    except Exception:
        tone = _tone_from_ctx(ctx)
        last_used = _recent_openers(7)
        hook = _pick_hook(tone, last_used=last_used)
        cap = (f"{hook} Kp max {kp_max}, wind {wind} km/s, flares {int(flr)} CMEs {int(cme)}. "
               f"Schumann ~{sr} Hz." )
        tags = "#GaiaEyes #SpaceWeather #KpIndex #SolarWind #Aurora"
        return cap, tags


def generate_long_sections(ctx: Dict[str, Any]) -> (str, str, str, str):
    client = openai_client()
    kp_now = ctx.get("kp_now")
    kp_max = ctx.get("kp_max_24h")
    wind   = ctx.get("solar_wind_kms")
    flr    = ctx.get("flares_24h")
    cme    = ctx.get("cmes_24h")
    sr     = ctx.get("schumann_value_hz")
    sr_note= ctx.get("schumann_note")

    if not client:
        snapshot = _build_snapshot_md(ctx)
        affects = (
            "How This Affects You\n"
            "- Calm geomagnetics support steadier mood and coherence.\n"
            "- Adjust effort to energy; let wind/pressure shifts guide pacing.\n"
            "- Gentle breath and longer exhales settle the ANS.\n"
            "- Hydration + daylight help cognition when winds fluctuate."
        )
        playbook = (
            "Self-Care Playbook\n"
            "- 5–10 min breathwork or HRV biofeedback\n"
            "- Nature time / barefoot grounding\n"
            "- Extra water + electrolytes\n"
            "- Gentle mobility; reduce doomscrolling"
        )
        return snapshot, affects, playbook, "#GaiaEyes #SpaceWeather #Wellness #HeartBrain #Mindfulness"

    model = os.getenv("GAIA_OPENAI_MODEL", "gpt-4o-mini")
    prompt = f"""
Using the data below, create a Gaia Eyes–branded daily forecast with THREE sections and a hashtags line:
1) Space Weather Snapshot — bullet the numbers (Kp now/max, solar wind, flares/CMEs, Schumann). Omit any bullet whose value is missing/None.
2) How This Affects You — 4 concise bullets for mood, energy, heart, nervous system.
3) Self-Care Playbook — 3–5 practical tips tailored to today.
End with 4–6 hashtags on the last line. Tone: friendly, engaging, a bit viral. Avoid dates. Render flare/ CME counts as integers.

Data:
- Kp now: {kp_now}
- Kp max (24h): {kp_max}
- Solar wind speed (km/s): {wind}
- Flares past 24h: {flr}
- CMEs past 24h: {cme}
- Schumann: {sr} Hz ({sr_note})
""".strip()
    try:
        resp = client.chat.completions.create(
            model=model, temperature=0.75, max_tokens=900,
            messages=[{"role":"system","content":"You are Gaia Eyes' space weather writer. Be accurate, warm, and helpful. Balance science and mysticism."},
                     {"role":"user","content": prompt}],
        )
        text = resp.choices[0].message.content.strip()
        # Try to carve out the three sections + hashtags
        snapshot, affects, playbook, hashtags = "", "", "", ""
        blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
        cur = None
        for b in blocks:
            low = b.lower()
            if "space weather snapshot" in low:
                cur = "snap"; snapshot += b + "\n\n"; continue
            if "how this affects you" in low:
                cur = "aff"; affects += b + "\n\n"; continue
            if "self-care" in low:
                cur = "play"; playbook += b + "\n\n"; continue
            if b.startswith("#") and " " in b and not hashtags:
                hashtags = b; continue
            if cur == "snap": snapshot += b + "\n\n"
            elif cur == "aff": affects += b + "\n\n"
            elif cur == "play": playbook += b + "\n\n"
            else: snapshot += b + "\n\n"
        if not hashtags:
            hashtags = "#GaiaEyes #SpaceWeather #Wellness #Mindfulness #HeartBrain"
        # sanitize hashtags: ensure the final line is a real hashtag line
        if not hashtags or not hashtags.strip().startswith("#"):
            hashtags = "#GaiaEyes #SpaceWeather #Wellness #HeartBrain #Mindfulness"
        # Strip any duplicate self-added headers
        snapshot = _strip_intro_header(snapshot)
        affects  = _strip_intro_header(affects)
        playbook = _strip_intro_header(playbook)
        return snapshot.strip(), affects.strip(), playbook.strip(), hashtags
    except Exception:
        snapshot = (
            f"Space Weather Snapshot\n"
            f"- Kp now: {kp_now}\n- Kp max (24h): {kp_max}\n- Solar wind: {wind} km/s\n"
            f"- Flares (24h): {flr}\n- CMEs (24h): {cme}\n- Schumann: {sr} Hz\n"
        )
        affects = (
            "How This Affects You\n"
            "- Calm geomagnetics support steadier mood and coherence.\n"
            "- Adjust effort to energy; let wind/pressure shifts guide pacing.\n"
            "- Gentle breath and longer exhales settle the ANS.\n"
            "- Hydration + daylight help cognition when winds fluctuate."
        )
        playbook = (
            "Self-Care Playbook\n"
            "- 5–10 min breathwork or HRV biofeedback\n"
            "- Nature time / barefoot grounding\n"
            "- Extra water + electrolytes\n"
            "- Gentle mobility; reduce doomscrolling"
        )
        return snapshot, affects, playbook, "#GaiaEyes #SpaceWeather #Wellness #HeartBrain #Mindfulness"

# ============================================================
# Supabase write: posts upsert
# ============================================================

def upsert_supabase_post(values: Dict[str, Any]) -> None:
    """Upsert one row into posts table; uses schema and supports user_id."""
    payload = {
        "day": values["day"],
        "user_id": values.get("user_id"),
        "platform": values.get("platform", PLATFORM),
        "title": values.get("title"),
        "caption": values.get("caption"),
        "body_markdown": values.get("body_markdown"),
        "hashtags": values.get("hashtags"),
        "metrics_json": values.get("metrics_json"),
        "sources_json": values.get("sources_json"),
    }
    try:
        conflict = "day,platform"
        if payload.get("user_id"):
            conflict = "day,user_id,platform"
        (
            SB.schema(POSTS_SCHEMA)
              .table(POSTS_TABLE)
              .upsert(payload, on_conflict=conflict)
              .execute()
        )
    except Exception as e:
        print(f"[WARN] Supabase posts upsert failed: {e}")

# ============================================================
# Main
# ============================================================

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=today_iso_local(), help="YYYY-MM-DD (default: today)")
    ap.add_argument("--platform", default=PLATFORM)
    args = ap.parse_args()

    day = args.date

    # 1) Fetch from Supabase marts
    sw = fetch_space_weather_from_marts(day)
    sr = fetch_schumann_from_marts(day)

    # Compose the context used by LLM
    ctx = {
        "kp_now": None,  # not in daily mart; could be added later
        "kp_max_24h": sw.get("kp_max_24h"),
        "solar_wind_kms": sw.get("solar_wind_kms"),
        "flares_24h": sw.get("flares_24h"),
        "cmes_24h": sw.get("cmes_24h"),
        "schumann_value_hz": sr.get("schumann_value_hz"),
        "schumann_note": sr.get("schumann_note"),
        "harmonics": sr.get("schumann_harmonics"),
    }

    # 2) Generate copy
    short_caption, short_tags = generate_short_caption(ctx)
    snapshot, affects, playbook, long_tags = generate_long_sections(ctx)

    # Title heuristic (tiered)
    kpmax = ctx.get("kp_max_24h")
    wind  = ctx.get("solar_wind_kms")
    if kpmax is None and wind is None:
        title = "Space Weather Update"
    elif kpmax is not None and kpmax >= 6:
        title = "Geomagnetic Storm Watch"
    elif kpmax is not None and kpmax >= 4:
        title = "Active Geomagnetics"
    elif wind is not None and wind >= 600:
        title = "High-Speed Solar Wind"
    else:
        title = "Magnetic Calm"

    # 3) Prepare payloads
    metrics_json = {
        "kp_max_24h": ctx.get("kp_max_24h"),
        "solar_wind_kms": ctx.get("solar_wind_kms"),
        "flares_24h": ctx.get("flares_24h"),
        "cmes_24h": ctx.get("cmes_24h"),
        "schumann_value_hz": ctx.get("schumann_value_hz"),
        "harmonics": ctx.get("harmonics"),
    }
    sources_json = {
        "marts.space_weather_daily": True,
        "marts.schumann_daily": True,
    }

    # 4) Build final body markdown and upsert (single row per date/platform)
    body_md = (
        "### Gaia Eyes Daily Space Weather Forecast\n\n" +
        "\n\n".join([snapshot, affects, playbook]).strip()
    )

    upsert_supabase_post({
        "day": day,
        "user_id": USER_ID,
        "platform": args.platform,
        "title": title,
        "caption": short_caption,
        "body_markdown": body_md,
        "hashtags": (long_tags or short_tags),
        "metrics_json": metrics_json,
        "sources_json": sources_json,
    })

    print("Earthscope (Supabase) generation complete.")


if __name__ == "__main__":
    main()
