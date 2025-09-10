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
    """Fetch Schumann fundamentals/harmonics for both stations and combine.
    Returns f0..h4 averages across available stations and a note.
    """
    try:
        res = (
            SB.schema(SPACE_SCHEMA)
              .table(SR_TABLE)
              .select("*")
              .eq(DAY_COLUMN, day)
              .in_("station_id", ["tomsk", "cumiana"])
              .execute()
        )
        rows = res.data or []
        # Map by station
        by_station = {r.get("station_id"): r for r in rows}
        f0_t = to_float(by_station.get("tomsk", {}).get("f0_avg_hz"))
        f0_c = to_float(by_station.get("cumiana", {}).get("f0_avg_hz"))
        f0 = _avg_non_null([f0_t, f0_c])
        f1 = _avg_non_null([to_float(by_station.get("tomsk", {}).get("f1_avg_hz")),
                            to_float(by_station.get("cumiana", {}).get("f1_avg_hz"))])
        f2 = _avg_non_null([to_float(by_station.get("tomsk", {}).get("f2_avg_hz")),
                            to_float(by_station.get("cumiana", {}).get("f2_avg_hz"))])
        h3 = _avg_non_null([to_float(by_station.get("tomsk", {}).get("h3_avg_hz")),
                            to_float(by_station.get("cumiana", {}).get("h3_avg_hz"))])
        # Some datasets use h4_avg_hz; handle typos gracefully
        h4_t = by_station.get("tomsk", {})
        h4_c = by_station.get("cumiana", {})
        h4 = _avg_non_null([
            to_float(h4_t.get("h4_avg_hz") or h4_t.get("h4_avg")),
            to_float(h4_c.get("h4_avg_hz") or h4_c.get("h4_avg")),
        ])
        stations_used = ",".join([s for s in ("tomsk" if f0_t is not None else None, "cumiana" if f0_c is not None else None) if s]) or "none"
        note = f"Schumann f0 from {stations_used}; harmonics averaged across available stations."
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
        hook = "Magnetic calm" if (kp_max is not None and kp_max < 3) else "Magnetic storm watch"
        cap = (f"{hook} — Kp max {kp_max}, wind {wind} km/s, flares {flr}, CMEs {cme}. "
               f"Schumann ~{sr} Hz. Breathe, ground, hydrate. 💫")
        tags = "#GaiaEyes #SpaceWeather #KpIndex #SolarWind #Mindfulness #Wellness"
        return cap, tags

    model = os.getenv("GAIA_OPENAI_MODEL", "gpt-4o-mini")
    prompt = f"""
Using the data below, write a short, viral-friendly caption for Gaia Eyes.
Start with an attention-grabbing line appropriate to the conditions (if Kp_max≥5 or wind≥600 km/s, lean urgent; else calm & curious). Relate to mood, energy, heart, and nervous system. Include 4–6 relevant hashtags on the last line. ≤700 chars. Render flare/ CME counts as integers.

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
            model=model,
            temperature=0.75,
            max_tokens=320,
            messages=[{"role":"system","content":"You are Gaia Eyes' space weather writer. Be accurate, warm, and helpful."},
                     {"role":"user","content": prompt}],
        )
        text = resp.choices[0].message.content.strip()
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        hashtags = ""
        caption = text
        if lines and lines[-1].startswith("#"):
            hashtags = lines[-1]
            caption = "\n".join(lines[:-1]).strip()
        if not hashtags:
            hashtags = "#GaiaEyes #SpaceWeather #Wellness #Mindfulness #HeartBrain"
        return caption, hashtags
    except Exception:
        cap = (f"Space weather check — Kp max {kp_max}, wind {wind} km/s; flares {flr}, CMEs {cme}. "
               f"Schumann ~{sr} Hz. Stay regulated. ✨")
        return cap, "#GaiaEyes #SpaceWeather #Wellness #Mindfulness #HeartBrain"


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
        "### 🌌 Gaia Eyes Daily Space Weather Forecast\n\n" +
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