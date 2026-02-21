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

import os, json, argparse, re
import math
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys
from typing import Optional, Dict, Any, List
import hashlib

STYLE_GUIDE = (
    "Persona: Humorous researcher who studies space/earth frequencies and their effects on physiology. "
    "Voice: Viral, plain‑language, humane, lightly empathic; first‑person is OK in short asides. "
    "Audience: Chronic pain sufferers and people who consider themselves sensitive (HRV, sleep, nerve/pain flares during storms). "
    "Rules: Never contradict provided metrics; no emojis; no rhetorical questions. "
    "Prefer terms like 'active geomagnetics', 'autonomic/HRV', 'sleep quality', 'nerve sensitivity'. "
    "Never claim deterministic health effects; use 'some may', 'can', 'tends to', 'I often see'. "
    "Keep sections compact and scannable."
)
BAN_PHRASES = [
    "energy is calm", "calm vibes", "mindful living", "cosmic vibes",
    "mother earth recharge", "sound bath", "tap into", "manifest", "alchemy",
    "grounding energy", "soothe your soul", "textured",
    "a small metaphor",
    "small metaphor",
    "satellite-dependent",
    "gnss",
]

import requests
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.openai_models import resolve_openai_model

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
# Kp obs mart table
KPOBS_TABLE  = os.getenv("SUPABASE_KPOBS_TABLE", "kp_obs")
DAY_COLUMN   = os.getenv("SUPABASE_DAY_COLUMN", "day")
PLATFORM     = os.getenv("EARTHSCOPE_PLATFORM", "default")
USER_ID      = os.getenv("EARTHSCOPE_USER_ID", None)

# Output JSON for website/app card (optional)
EARTHSCOPE_OUTPUT_JSON = os.getenv("EARTHSCOPE_OUTPUT_JSON_PATH")  # e.g., ../gaiaeyes-media/data/earthscope_daily.json
EARTHSCOPE_PULSE_JSON = os.getenv("EARTHSCOPE_PULSE_JSON", str((BASE_DIR / ".." / ".." / "gaiaeyes-media" / "data" / "pulse.json").resolve()))
# Optional: external space weather JSON (now/next_72h/impacts) — preferred fallback for missing KP/Bz/SW
EARTHSCOPE_SPACE_JSON = os.getenv("EARTHSCOPE_SPACE_JSON", str((BASE_DIR / ".." / ".." / "gaiaeyes-media" / "data" / "space_weather.json").resolve()))
# Optional: consolidated earthscope card JSON (sections + metrics) to merge and pass through
EARTHSCOPE_CARD_JSON = os.getenv("EARTHSCOPE_CARD_JSON", str((BASE_DIR / ".." / ".." / "gaiaeyes-media" / "data" / "earthscope.json").resolve()))
EARTHSCOPE_API_BASE = (os.getenv("GAIAEYES_API_BASE") or "https://gaiaeyes-backend.onrender.com").rstrip("/")
EARTHSCOPE_OUTLOOK_PATH = os.getenv("EARTHSCOPE_OUTLOOK_PATH", "/v1/space/forecast/outlook")
EARTHSCOPE_API_BEARER = (os.getenv("EARTHSCOPE_API_BEARER") or os.getenv("READ_TOKEN") or "").strip()
EARTHSCOPE_FORCE_RULES = os.getenv("EARTHSCOPE_FORCE_RULES", "false").strip().lower() in ("1","true","yes","on")
# Toggle for first-person clinical asides in affects/playbook
EARTHSCOPE_FIRST_PERSON = os.getenv("EARTHSCOPE_FIRST_PERSON", "true").strip().lower() in ("1","true","yes","on")

# Debug flag for rewrite path tracing
EARTHSCOPE_DEBUG_REWRITE = os.getenv("EARTHSCOPE_DEBUG_REWRITE", "false").strip().lower() in ("1","true","yes","on")

def _dbg(msg: str) -> None:
    if EARTHSCOPE_DEBUG_REWRITE:
        print(f"[earthscope.debug] {msg}")


def _writer_model() -> Optional[str]:
    return resolve_openai_model("public_writer")


INTRO_LINES = [
    "Gaia Eyes check-in: the sky has opinions today.",
    "Gaia Eyes forecast: subtle field, real effects.",
    "Gaia Eyes update: magnetic weather with personality.",
    "Gaia Eyes report: nervous systems may notice today.",
    "Gaia Eyes says: keep pacing and stay curious.",
    "Gaia Eyes field note: calm outside, sensitive inside.",
    "Gaia Eyes alert: today's signal is a mixed bag.",
    "Gaia Eyes briefing: your body may read the room.",
    "Gaia Eyes pulse: geomagnetics are setting the tone.",
    "Gaia Eyes watch: the atmosphere feels a little spicy.",
    "Gaia Eyes check: steady skies, better rhythm windows.",
    "Gaia Eyes note: cosmic weather, human consequences.",
    "Gaia Eyes lens: today favors pacing over force.",
    "Gaia Eyes tracker: field shifts, mood shifts, plan shifts.",
    "Gaia Eyes monitor: today asks for cleaner boundaries.",
    "Gaia Eyes signal: active currents, gentle strategy.",
    "Gaia Eyes status: quiet magnetics, useful focus.",
    "Gaia Eyes forecast: friction pockets, keep it simple.",
    "Gaia Eyes bulletin: your nervous system gets a vote.",
    "Gaia Eyes readout: build slack into the schedule.",
    "Gaia Eyes daily: steady effort beats heroic effort.",
    "Gaia Eyes observation: subtle changes still count.",
    "Gaia Eyes brief: field conditions can shape recovery.",
    "Gaia Eyes outlook: protect sleep like it is medicine.",
    "Gaia Eyes note: today rewards shorter work bursts.",
    "Gaia Eyes update: magnetic texture is not perfectly flat.",
    "Gaia Eyes check-in: calm-ish day, still pace wisely.",
    "Gaia Eyes radar: expect waves, not catastrophe.",
    "Gaia Eyes ping: it is a regulation-first day.",
    "Gaia Eyes signal check: keep your load intentional.",
    "Gaia Eyes weather desk: today has edge and nuance.",
    "Gaia Eyes pulse report: optimize for consistency.",
    "Gaia Eyes tracker says: reduce noise, protect bandwidth.",
    "Gaia Eyes guide: nervous systems like predictability today.",
    "Gaia Eyes update: charged backdrop, softer pacing.",
    "Gaia Eyes check: light structure will help today.",
]

METAPHOR_HINTS = [
    "roller coaster",
    "over-caffeinated squirrel",
    "too many browser tabs",
    "cosmic espresso shot",
    "weather with jazz hands",
    "nervous system pinging like a notification",
    "a bumpy road with good suspension",
    "a treadmill set to 'interesting'",
    "a sea with small chop",
    "a radio slightly off-station",
    "Wi-Fi cutting in and out",
    "low battery mode",
    "pop-up notifications all day",
    "background app refresh",
    "jazz improvisation",
    "a car idling high",
    "static on a signal",
    "3am zoomies energy",
    "a browser spinning wheel",
    "a slightly misaligned compass",
    "micro-bursts of caffeine",
    "a choppy but manageable flight",
    "a light crosswind",
    "a dashboard blinking softly",
    "a playlist on shuffle",
    "a mild headwind",
    "a humming transformer",
    "a tightrope with balance",
    "small waves, not a tsunami",
    "a flickering streetlight"
]

def _select_metaphor_hint(day_iso: str, platform: str) -> str:
    seed = int(hashlib.sha256(f"{day_iso}|{platform}|metaphor".encode("utf-8")).hexdigest(), 16)
    return METAPHOR_HINTS[seed % len(METAPHOR_HINTS)]
PHRASE_VARIANTS = {
    "feel_stable": [
        "Steady field—good window for getting things done.",
        "Quieter field—use the mental clarity to your advantage today.",
        "Stable profile—set a simple plan and move steadily towards goals."
    ],
    "feel_unsettled": [
        "Ups and Downs—work in short blocks, pace yourself.",
        "Easily Distracted—add extra time for tasks and be patient with yourself.",
        "Disruptions—aim for rhythm over intensity."
    ],
    "sleep_guard": [
        "Dim lights earlier; protect your sleep routine.",
        "Wind down on schedule; keep evenings warm‑lit.",
        "Say no to the extra caffeine and sugar today; keep screens softer."
    ],
    "nerve_note": [
        "If you run sensitive, brief tingles or nerve flares can show—plan micro‑breaks.",
        "Sensitives can feel more wired; keep shoulders relaxed, jaw unclenched. Try grounding",
        "If pain flares on active days, apply heat, take it easy and ground."
    ],
}
def _pick_variant(key: str, seed_extra: int = 0) -> str:
    arr = PHRASE_VARIANTS.get(key) or []
    if not arr: return ""
    random.seed(_daily_seed() + hash(key) + seed_extra)
    return random.choice(arr)

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

# --- simple banding/labels ---
def _band_kp(kp: float|None) -> str:
    if kp is None: return "unknown"
    if kp >= 7: return "severe"
    if kp >= 5: return "storm"
    if kp >= 4: return "active"
    if kp >= 3: return "unsettled"
    return "quiet"

def _band_sw(speed: float|None) -> str:
    if speed is None: return "unknown"
    if speed >= 700: return "very-high"
    if speed >= 600: return "high"
    if speed >= 500: return "elevated"
    return "normal"

def _bz_desc(bz: float|None) -> str:
    if bz is None: return "undetermined"
    if bz <= -10: return "strong southward"
    if bz <= -6: return "southward"
    if bz < 0: return "slightly southward"
    if bz >= 8: return "strong northward"
    if bz >= 3: return "northward"
    return "near neutral"

# --- Aurora headline from Kp helper ---
def _derive_aurora_from_kp(kp: Optional[float]) -> tuple[str, str]:
    """
    Return (headline, severity) from a Kp-like value.
    Severity is a coarse label: G0/G1/G2/G3+ used only for narrative hints.
    """
    if kp is None:
        return ("Aurora mostly confined to polar regions", "G0")
    try:
        k = float(kp)
    except Exception:
        return ("Aurora mostly confined to polar regions", "G0")
    if k >= 7:
        return ("G3+ aurora possible", "G3+")
    if k >= 6:
        return ("G2 aurora possible", "G2")
    if k >= 5:
        return ("G1 aurora possible", "G1")
    if k >= 4:
        return ("High‑latitude aurora possible", "G0")
    return ("Aurora mostly confined to polar regions", "G0")

def _fmt_num(x, nd=1):
    try:
        return f"{float(x):.{nd}f}"
    except Exception:
        return "—"

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

# --- section header label stripper ---
HEADER_LABEL_RE = re.compile(
    r"^(space situation:|space weather snapshot:?|how people may feel:|how this affects you:|self-?care playbook:?|care notes:?|playbook:?|snapshot:)\s*",
    re.I
)

def _strip_section_labels(text: str) -> str:
    if not text:
        return text
    lines = [ln.rstrip() for ln in str(text).splitlines()]
    out = []
    for ln in lines:
        out.append(HEADER_LABEL_RE.sub("", ln).strip())
    return "\n".join([x for x in out if x != ""]).strip()

# --- hook + tone system (no questions, no "Feeling...", no emojis) ---
import random

BAN_STARTS = ("feeling ", "are you ", "ever feel ", "ready to ", "it’s time", "its time", "let’s ", "lets ")
BAN_CAPTION_OPENERS = (
    "active geomagnetic",
    "geomagnetic conditions",
    "geomagnetic activity is",
    "solar wind is",
    "elevated solar wind",
    "southward magnetic tilt",
)
EMOJI_RE = re.compile(r"[\U00010000-\U0010ffff]", flags=re.UNICODE)

HOOKS = {
    "calm": [
        "Quieter field today—good for deep focus.",
        "Calm geomagnetics; lock in your rhythm.",
        "Steady skies, steady mind.",
        "Low Kp, longer runway for clarity.",
        "Baseline is smooth—use your late‑morning window.",
        "Stable backdrop—great for prolonged focus.",
        "Quiet day upstairs—take advantage and get things done.",
        "Magnetic weather is tame—work your plan.",
    ],
    "unsettled": [
        "Ride the waves, not stormy, but active.",
        "Spikes‑and‑dips kind of day.",
        "A few bumps in the road; keep a steady pace and push on.",
        "Unsettled doesn’t mean unworkable—buffer your tasks with breaks.",
        "Short surges, brief dips—ride the middle line.",
        "Minor fluctuation day—aim for a steady pace.",
        "Today has a little attitude—be mindful of your energy.",
        "Patchy energy—reduce your workload if possible today.",
    ],
    "stormy": [
        "Charged air today—channel the energy.",
        "Storm‑leaning field—work in bursts, expect longer recoveries.",
        "Today might pack a punch.",
        "Strong coupling window—guard your spoons today.",
        "Prickly atmosphere—don't let it make you one.",
        "The vibes are jivin;—proceed like your walking on eggshells.",
        "Amplified everything—rest and reset.",
        "Volatile day—work steady, not in sprints.",
    ],
    "neutral": [
        "Neutral energy. You set the pace",
        "Bland vibes—nothing too exciting.",
        "Little influence—enjoy a clear day.",
        "Ordinary—enjoy a normal day.",
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
    # Stormy if KP>=5 or strong southward Bz with elevated wind
    if (kpf is not None and kpf >= 5) or ((bzf is not None and bzf <= -8) and (wf is not None and wf >= 550)):
        return "stormy"
    # Unsettled if KP>=3.5 or wind>=550 or Bz <= -6
    if (kpf is not None and kpf >= 3.5) or (wf is not None and wf >= 550) or (bzf is not None and bzf <= -6):
        return "unsettled"
    # Calm if KP<=2.5 and Bz >= -2
    if (kpf is not None and kpf <= 2.5) and (bzf is None or bzf > -2):
        return "calm"
    return "neutral"

def _daily_seed() -> int:
    return int(datetime.utcnow().strftime("%Y%m%d"))


def _ctx_day_iso(ctx: Dict[str, Any]) -> str:
    day = str(ctx.get("day") or "").strip()
    return day or today_iso_local()


def _ctx_platform(ctx: Dict[str, Any]) -> str:
    return str(ctx.get("platform") or PLATFORM or "default").strip() or "default"


def _stable_ctx_hash(ctx: Dict[str, Any]) -> str:
    omit = {"day", "platform", "intro_hint", "banned_openers"}
    normalized = {k: ctx[k] for k in sorted(ctx.keys()) if k not in omit}
    blob = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _select_intro_line(day_iso: str, platform: str, banned_openers: Optional[List[str]] = None) -> str:
    banned = {(x or "").strip().lower() for x in (banned_openers or []) if (x or "").strip()}
    seed = int(hashlib.sha256(f"{day_iso}|{platform}".encode("utf-8")).hexdigest(), 16)
    for offset in range(len(INTRO_LINES)):
        idx = (seed + offset) % len(INTRO_LINES)
        intro = INTRO_LINES[idx]
        if intro.strip().lower() not in banned:
            return intro
    return INTRO_LINES[seed % len(INTRO_LINES)]


# --- Recent opener helpers for hook variation ---
SENT_SPLIT_RE = re.compile(r"(?<=\.)\s+|(?<=! )\s+|(?<=\?)\s+", re.X)

def _first_sentence(txt: str) -> str:
    if not txt: return ""
    parts = SENT_SPLIT_RE.split(txt.strip(), maxsplit=1)
    return parts[0].strip() if parts else txt.strip()


def _first_nonempty_line(txt: str) -> str:
    if not txt:
        return ""
    for ln in str(txt).splitlines():
        s = ln.strip()
        if s:
            return s
    return ""

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


def _recent_platform_openers(platform: str, limit: int = 3) -> List[str]:
    plat = (platform or "default").strip() or "default"
    try:
        res = (
            SB.schema(POSTS_SCHEMA)
              .table(POSTS_TABLE)
              .select("day,lead,caption")
              .eq("platform", plat)
              .order("day", desc=True)
              .limit(limit)
              .execute()
        )
        rows = res.data or []
    except Exception:
        try:
            res = (
                SB.schema(POSTS_SCHEMA)
                  .table(POSTS_TABLE)
                  .select("day,caption")
                  .eq("platform", plat)
                  .order("day", desc=True)
                  .limit(limit)
                  .execute()
            )
            rows = res.data or []
        except Exception:
            rows = []
    out: List[str] = []
    for row in rows:
        opener = _first_nonempty_line(row.get("lead") or row.get("caption") or "")
        if opener:
            out.append(opener)
    return out[:limit]

# --- Recent titles helper to reduce repetition ---
def _recent_titles(days_back: int = 14) -> set:
    try:
        since = (datetime.utcnow() - timedelta(days=days_back)).date().isoformat()
        res = (
            SB.schema(POSTS_SCHEMA)
              .table(POSTS_TABLE)
              .select("day,title,platform")
              .gte("day", since)
              .order("day", desc=True)
              .limit(30)
              .execute()
        )
        rows = res.data or []
        return { (r.get("title") or "").strip().lower() for r in rows if r and r.get("title") }
    except Exception:
        return set()
# --- LLM-based title generator using cached rewrite ---
def _llm_title_from_context(client: Optional["OpenAI"], ctx: Dict[str, Any], rewrite: Optional[Dict[str,str]]) -> Optional[str]:
    """Ask the LLM for a short 2–4 word title based on tone + pulse + sections. No numbers, no emojis.
    Returns a plain string or None on failure.
    """
    if not client:
        return None
    tone = _tone_from_ctx(ctx)
    recent = sorted(list(_recent_titles(21)))
    # Compose compact context
    facts = {
        "tone": tone,
        "bands": {"kp": _band_kp(ctx.get("kp_max_24h")), "sw": _band_sw(ctx.get("solar_wind_kms")), "bz": _bz_desc(ctx.get("bz_min"))},
        "pulse": {
            "aurora": bool(ctx.get("aurora_headline")),
            "quakes": int(ctx.get("quakes_count") or 0) > 0,
            "severe": bool(ctx.get("severe_summary")),
        }
    }
    sections = rewrite or {}
    sys = (
        "You title Gaia Eyes daily cards. Write a **concise and sometimes comical 2–4 word title** that fits the day’s tone and context. "
        "Do not include numbers, dates, emojis, or hashtags. Avoid generic phrases. Keep it evocative but calm. "
        "Output ONLY the title text with no quotes."
    )
    usr = {
        "facts": facts,
        "samples": {"recent_titles": recent[:12]},
        "sections_excerpt": {k: (v[:160] if isinstance(v,str) else v) for k,v in sections.items() if k in ("caption","snapshot")}
    }
    try:
        model = _writer_model()
        if not model:
            return None
        resp = _chat_create_compat(
            client,
            model=model,
            temperature=0.65,
            top_p=0.9,
            presence_penalty=0.2,
            max_completion_tokens=16,
            messages=[{"role":"system","content":sys},{"role":"user","content":json.dumps(usr, ensure_ascii=False)}],
        )
        title = (resp.choices[0].message.content or "").strip()
        # Guardrails: strip quotes and trim length
        title = re.sub(r'^["\']|["\']$', "", title).strip()
        if 0 < len(title) <= 40:
            return title
        return None
    except Exception:
        return None

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

# --- deterministic rule-based copy ---
def _rule_copy(ctx: Dict[str, Any]) -> Dict[str, str]:
    kp = ctx.get("kp_max_24h")
    bz = ctx.get("bz_min")
    sw = ctx.get("solar_wind_kms")
    flr = ctx.get("flares_24h")
    cme = ctx.get("cmes_24h")
    sr = ctx.get("schumann_value_hz")

    tone = _tone_from_ctx(ctx)
    # Caption: concise, clinical, social-friendly
    kp_band = _band_kp(kp); sw_band = _band_sw(sw); bz_txt = _bz_desc(bz)
    parts = []
    if kp is not None: parts.append(f"Kp { _fmt_num(kp,1) } ({kp_band})")
    if sw is not None: parts.append(f"SW { int(round(float(sw))) } km/s ({sw_band})")
    if bz is not None: parts.append(f"Bz { _fmt_num(bz,1) } nT ({bz_txt})")
    cap_lead = " • ".join(parts) if parts else "Space weather update"
    if tone == "stormy":
        trailing = "Expect sensitivity and flares; readjust plans as necessary."
    elif tone == "unsettled":
        trailing = "Some variability—schedule breaks in your day and pace yourself with critical tasks."
    elif tone == "calm":
        trailing = "Ideal day—great day for playing catch up and recovery."
    else:
        trailing = "Moderate conditions—steady and consistent tends to work best."
    caption = f"{cap_lead}. {trailing}"

    # Snapshot bullets (only present values)
    snap = []
    if kp is not None: snap.append(f"- Kp max (24h): { _fmt_num(kp,1) }")
    if sw is not None: snap.append(f"- Solar wind: { int(round(float(sw))) } km/s")
    if bz is not None: snap.append(f"- Bz: { _fmt_num(bz,1) } nT ({bz_txt})")
    if flr is not None: snap.append(f"- Flares (24h): {int(round(float(flr)))}")
    if cme is not None: snap.append(f"- CMEs (24h): {int(round(float(cme)))}")
    if sr is not None: snap.append(f"- Schumann f0: { _fmt_num(sr,2) } Hz")
    snapshot = "\n".join(snap)

    # How it may feel (human clinical tone)
    feel = []
    if tone in ("stormy","unsettled"):
        feel.append(f"- Focus/energy: {_pick_variant('feel_unsettled') or 'Expect ebbs/spikes; keep tasks short.'}")
        feel.append("- Autonomic/HRV: Southward Bz or higher Kp can nudge HRV down in some; paced breathing helps.")
        feel.append(f"- Sleep: {_pick_variant('sleep_guard')}")
        if EARTHSCOPE_FIRST_PERSON:
            feel.append(f"- Clinician note: {_pick_variant('nerve_note', seed_extra=1)}")
        else:
            feel.append(f"- Sensitivity note: {_pick_variant('nerve_note', seed_extra=1)}")
        feel.append("- Comms/GPS: Tech may be glitchy today. Satellite based services, especially. Nervous System sensitivities may increase.")
    else:
        feel.append(f"- Focus/energy: {_pick_variant('feel_stable') or 'Stable; good window to get things done.'}")
        feel.append("- Autonomic/HRV: Great for recovery and healing practices.")
        feel.append("- Sleep: Keep evening light warm and low.")
        if EARTHSCOPE_FIRST_PERSON:
            feel.append("- Clinician note: I see steadier HRV and less reactivity for many on days like this.")
    affects = "\n".join(feel)

    # Care notes (practical, small set)
    care_lines = []
    if tone in ("stormy","unsettled"):
        care_lines.append("- 5–10 min paced breathing (e.g., 4:6) or brief HRV biofeedback")
        care_lines.append("- Hydration + electrolytes; short daylight exposure; move easy")
        care_lines.append("- Protect sleep: blue‑light filters and a consistent wind‑down")
        care_lines.append("- If sensitive, quick grounding/outdoor walk; warm pack for nerve flare windows")
    else:
        care_lines.append("- Block 1–2 focus sessions (60–90 min) while the field is steady")
        care_lines.append("- Natural light and movement breaks to reinforce circadian tone")
        care_lines.append("- Hydrate; keep caffeine earlier in the day")
    playbook = "\n".join(care_lines)

    tags = "#GaiaEyes #SpaceWeather #KpIndex #HRV #Sleep #Focus"
    return {"caption": caption, "snapshot": snapshot, "affects": affects, "playbook": playbook, "hashtags": tags}

# --- banned phrase and repetition scrubber ---

def _scrub_banned_phrases(text: str) -> str:
    s = text or ""
    low = s.lower()
    for bp in BAN_PHRASES:
        if bp in low:
            # Replace banned phrase with neutral wording
            s = re.sub(re.escape(bp), "stable conditions", s, flags=re.I)
            low = s.lower()
    # light n-gram de-dupe: collapse repeated bigrams
    s = re.sub(r"\b(\w+\s+\w+)\s+\1\b", r"\1", s, flags=re.I)
    s2 = s.strip()
    if s2:
        first = _first_sentence(s2)
        rest = s2[len(first):].lstrip()
        if rest.startswith(first):
            s2 = (first + " " + rest[len(first):].lstrip()).strip()
    return s2

# --- Context summarizer & JSON rewrite utilities (interpretive, number-free) ---

def _build_facts(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the subset of facts we pass to the LLM. These are context, not for citation."""
    return {
        "kp_max_24h": ctx.get("kp_max_24h"),
        "bz_min": ctx.get("bz_min"),
        "solar_wind_kms": ctx.get("solar_wind_kms"),
        "flares_24h": ctx.get("flares_24h"),
        "cmes_24h": ctx.get("cmes_24h"),
        "schumann_value_hz": ctx.get("schumann_value_hz"),
        # Earthquakes can be integrated later if present in ctx
        "earthquakes_72h": ctx.get("earthquakes_72h"),
        "tone": _tone_from_ctx(ctx),
        "bands": {
            "kp": _band_kp(ctx.get("kp_max_24h")),
            "sw": _band_sw(ctx.get("solar_wind_kms")),
            "bz": _bz_desc(ctx.get("bz_min")),
        },
        "aurora_headline": ctx.get("aurora_headline"),
        "aurora_window": ctx.get("aurora_window"),
        "aurora_severity": ctx.get("aurora_severity"),
        "quakes_count": ctx.get("quakes_count"),
        "severe_summary": ctx.get("severe_summary"),
        # Removed intro_hint and banned_openers from facts passed to LLM
        "metaphor_hint": ctx.get("metaphor_hint"),
    }


def _summarize_context(facts: Dict[str, Any]) -> str:
    """Deterministic short hint that guides narrative without numbers."""
    kp = facts.get("kp_max_24h")
    cmes = facts.get("cmes_24h")
    flr = facts.get("flares_24h")
    sr = facts.get("schumann_value_hz")
    tone = facts.get("tone") or "neutral"

    parts: List[str] = []
    if cmes and (cmes or 0) > 0:
        parts.append("recent CME activity")
    if flr and (flr or 0) > 0:
        parts.append("fresh solar flare effects")
    if isinstance(kp, (int, float)) and kp >= 5:
        parts.append("geomagnetic storm window")
    elif isinstance(kp, (int, float)) and kp >= 4:
        parts.append("active geomagnetics")
    if isinstance(sr, (int, float)) and sr:
        parts.append("lively Schumann resonance")

    if not parts:
        parts.append("steady background field")
    return ", ".join(parts) + f"; tone {tone}."



def _contains_digits(s: str) -> bool:
    return bool(re.search(r"\d", s or ""))

# --- Robust JSON extractor ---
from typing import Optional
def _extract_first_json_object(text: str) -> Optional[str]:
    """Return the first balanced {...} JSON object substring from text.
    Handles code fences and ignores braces inside strings.
    """
    if not text:
        return None
    s = text.replace("```json", "").replace("```", "").strip()
    # Find first '{'
    start = s.find('{')
    if start == -1:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if esc:
                esc = False
            elif ch == '\\':
                esc = True
            elif ch == '"':
                in_str = False
            continue
        else:
            if ch == '"':
                in_str = True
                continue
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return s[start:i+1]
    return None


def _validate_rewrite(obj: Any) -> Optional[Dict[str, str]]:
    """Ensure JSON has required keys. For number policy: forbid digits in caption/snapshot, but allow in affects/playbook (e.g., "5–10 min")."""
    if not isinstance(obj, dict):
        _dbg("validate: not a dict")
        return None
    required = ["caption", "snapshot", "affects", "playbook", "hashtags"]
    for k in required:
        if k not in obj or not isinstance(obj[k], str):
            _dbg(f"validate: missing or non-str key: {k}")
            return None
    # Enforce number-free narrative in top fields only
    for k in ["caption", "snapshot"]:
        if _contains_digits(obj[k]):
            _dbg(f"validate: digits found in {k}")
            return None
    return obj


def _rewrite_json_interpretive(client: Optional["OpenAI"], draft: Dict[str, str], facts: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """Call the LLM to rewrite into interpretive, number-free JSON. Returns dict or None."""
    if not client:
        return None

    system_msg = (
        "You are Gaia Eyes’ daily weather desk: grounded, practical, and lightly funny. "
        "Interpret today’s space/earth conditions for humans. "
        "Do NOT cite numeric measurements or units for space-weather values (e.g., 'Kp 4.7', '386 km/s', 'nT', 'Hz'). "
        "It is OK to include small time ranges in practices (e.g., '5–10 min'). "
        "Write in crisp, human language (not a bulletin or press release). Avoid sterile phrasing. "
        "Include one playful metaphor max in the caption only. Do not add additional metaphors or 'metaphor:' labels elsewhere. Use metaphor_hint as a theme; you may paraphrase it. "
        "Do not start with a label like 'Gaia Eyes signal:' or 'Gaia Eyes forecast:'. Start directly with the summary. "
        "Keep humor warm and grounded (no doom, no sarcasm). "
        "No emojis. No questions. "
        "Never claim deterministic health effects; use 'some may', 'can', 'for some'. "
        "Return ONLY a compact JSON object with EXACTLY these string keys: caption, snapshot, affects, playbook, hashtags. "
        "No markdown, no extra keys, no code fences. "
        "If aurora_headline exists, include one sentence about aurora chances (no numbers). "
        "If quakes_count exists, include one sentence noting recent notable earthquakes (no numbers). "
        "If severe_summary exists, include one calm safety sentence (no numbers). "
        "Do not repeat any sentence verbatim. "
        "Aim for: caption 3–5 sentences; snapshot 3–5 sentences; affects 3–4 sentences; playbook 3–5 bullets. "
        "Do not include section headers or labels such as 'Space situation:', 'Space Weather Snapshot:', 'How people may feel:', or 'Care notes:'. Write each field as plain paragraphs or bullets only. "
    )

    payload = {
        "metrics": facts,
        "context": _summarize_context(facts),
        "draft": draft,
        "style": {
            "persona": "researcher-coach-comedian",
            "audience": "people tracking pain, HRV, sleep, nervous-system sensitivity",
            "opener_palette": HOOKS.get(facts.get("tone") or "neutral", HOOKS["neutral"]),
            "ban_phrases": BAN_PHRASES,
            "bullet_style": "short",
            "tone": facts.get("tone"),
            "length_targets": {"caption": [3,5], "snapshot": [3,5], "affects": [3,4], "playbook": [3,5]},
            "extra_ban_phrases": [
                "structured approach to tasks",
                "personal recovery efforts",
                "remains effective",
                "optimize your day"
            ],
            # Removed intro_hint and banned_openers from style
            "metaphor_hint": facts.get("metaphor_hint"),
        },
        "constraints": {
            "omit_numbers": True,
            "no_questions": True,
            "no_emojis": True,
            "max_caption_chars": 600
        }
    }

    model = _writer_model()
    if not model:
        _dbg("rewrite: no model configured (OPENAI_MODEL_PUBLIC_WRITER/OPENAI_MODEL_DEFAULT/OPENAI_MODEL/GAIA_OPENAI_MODEL)")
        return None
    try:
        _dbg("rewrite: request -> OpenAI (interpretive JSON)")
        resp = _chat_create_compat(
            client,
            model=model,
            temperature=0.8,
            top_p=0.9,
            presence_penalty=0.3,
            frequency_penalty=0.2,
            reasoning_effort="low",
            max_completion_tokens=1800,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}
            ],
        )
        text = _chat_text(resp).strip()
        finish_reason = None
        try:
            finish_reason = getattr(resp.choices[0], "finish_reason", None)
        except Exception:
            pass
        _dbg(f"rewrite: finish_reason={finish_reason} text_len={len(text)}")
        if not text:
            _dbg("rewrite: empty content; issuing compact retry")
            compact_draft = {
                "caption": str(draft.get("caption") or "")[:220],
                "snapshot": str(draft.get("snapshot") or "")[:320],
                "affects": str(draft.get("affects") or "")[:320],
                "playbook": str(draft.get("playbook") or "")[:320],
            }
            compact_user = {
                "facts": _summarize_context(facts),
                "draft_hint": compact_draft,
                "required_keys": ["caption", "snapshot", "affects", "playbook", "hashtags"],
                "instructions": "Return only one JSON object.",
            }
            resp = _chat_create_compat(
                client,
                model=model,
                reasoning_effort="low",
                max_completion_tokens=2400,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": "Return only valid JSON with keys caption,snapshot,affects,playbook,hashtags."},
                    {"role": "user", "content": json.dumps(compact_user, ensure_ascii=False)},
                ],
            )
            text = _chat_text(resp).strip()
            try:
                finish_reason = getattr(resp.choices[0], "finish_reason", None)
            except Exception:
                finish_reason = None
            _dbg(f"rewrite: compact finish_reason={finish_reason} text_len={len(text)}")
            if not text:
                _dbg("rewrite: compact empty; issuing plain-json final retry")
                final_user = {
                    "context": _summarize_context(facts),
                    "required_keys": ["caption", "snapshot", "affects", "playbook", "hashtags"],
                    "constraints": "Return a compact JSON object only; no markdown; no prose outside JSON.",
                }
                resp = _chat_create_compat(
                    client,
                    model=model,
                    reasoning_effort="low",
                    max_completion_tokens=3000,
                    messages=[
                        {"role": "system", "content": "Output strict JSON with exactly keys caption,snapshot,affects,playbook,hashtags."},
                        {"role": "user", "content": json.dumps(final_user, ensure_ascii=False)},
                    ],
                )
                text = _chat_text(resp).strip()
                try:
                    finish_reason = getattr(resp.choices[0], "finish_reason", None)
                except Exception:
                    finish_reason = None
                _dbg(f"rewrite: final finish_reason={finish_reason} text_len={len(text)}")
        _dbg("rewrite: response received; attempting JSON parse")
        try:
            raw = _extract_first_json_object(text)
            if not raw:
                raise ValueError("no-json-object-found")
            obj = json.loads(raw)
        except Exception as e:
            _dbg(f"rewrite: JSON parse failed: {e}")
            _dbg(f"rewrite: raw snippet => {text[:200]}")
            return None
        # Make response robust: if hashtags missing, inject a sane default before validation
        if isinstance(obj, dict) and ("hashtags" not in obj or not isinstance(obj.get("hashtags"), str) or not obj.get("hashtags").strip()):
            obj["hashtags"] = "#GaiaEyes #SpaceWeather #ChronicPain #Schumann #HRV #Sleep #Wellness"
        valid = _validate_rewrite(obj)
        _dbg("rewrite: JSON valid") if valid else _dbg("rewrite: JSON invalid by validator")
        if not valid:
            _dbg(f"rewrite: raw response snippet => {text[:180]}")
        if valid:
            # final scrubs
            valid["caption"] = _scrub_banned_phrases(_sanitize_caption(valid["caption"]))
            valid["snapshot"] = _strip_section_labels(_scrub_banned_phrases(valid["snapshot"]))
            valid["affects"] = _strip_section_labels(_scrub_banned_phrases(valid["affects"]))
            valid["playbook"] = _strip_section_labels(_scrub_banned_phrases(valid["playbook"]))
            # Soft length diagnostics (debug only)
            def _sent_count(x: str) -> int:
                parts = re.split(r"(?<=[\.!?])\s+", x.strip()) if x and isinstance(x, str) else []
                return len([p for p in parts if p])
            sc_cap = _sent_count(valid["caption"])
            sc_snap = _sent_count(valid["snapshot"])
            sc_aff = _sent_count(valid["affects"])
            sc_play = _sent_count(valid["playbook"])
            _dbg(f"len: caption={sc_cap}, snapshot={sc_snap}, affects={sc_aff}, playbook={sc_play}")
            return valid
        return None
    except Exception as e:
        _dbg(f"rewrite: OpenAI call failed: {e}")
        return None


# --- LLM rewrite from rules ---
def _llm_rewrite_from_rules(client: Optional["OpenAI"], caption: str, snapshot: str, affects: str, playbook: str, ctx: Dict[str, Any]) -> Dict[str, str]:
    """Number-free interpretive rewrite. Falls back to rule copy if JSON invalid or client missing."""
    _dbg("rewrite: begin")
    # If no client, return the rule copy unchanged (but scrub)
    if not client:
        _dbg("rewrite: no client; returning scrubbed rule copy")
        return {
            "caption": _scrub_banned_phrases(_sanitize_caption(caption)),
            "snapshot": _scrub_banned_phrases(snapshot),
            "affects": _scrub_banned_phrases(affects),
            "playbook": _scrub_banned_phrases(playbook),
            "hashtags": "#GaiaEyes #SpaceWeather #KpIndex #HRV #Sleep #Focus",
        }

    draft = {
        "caption": caption,
        "snapshot": snapshot,
        "affects": affects,
        "playbook": playbook,
        "hashtags": "#GaiaEyes #SpaceWeather #KpIndex #HRV #Sleep #Focus",
    }
    facts = _build_facts(ctx)

    # Try once
    out = _rewrite_json_interpretive(client, draft, facts)
    _dbg("rewrite: primary succeeded") if out else _dbg("rewrite: primary failed; retrying")
    if out:
        return out
    # Try a second time with a slightly different temperature
    client_tweak = client
    try:
        # Some SDKs allow per-call overrides only; we just reissue with different params inside helper if needed.
        out = _rewrite_json_interpretive(client_tweak, draft, facts)
    except Exception:
        out = None

    _dbg("rewrite: retry succeeded") if out else _dbg("rewrite: retry failed; falling back to qualitative")
    if out:
        return out

    # Final fallback: qualitative narrative (no metric numbers), preserve useful timings in affects/playbook
    _dbg("rewrite: using qualitative fallback")
    rc_fallback = _rule_copy(ctx)
    qual_snap = _qualitative_snapshot(ctx)
    tone = _tone_from_ctx(ctx)
    cap_map = {
        "stormy":   "Charged atmosphere—work in bursts, expect longer recoveries.",
        "unsettled": "A few bumps in the road—keep a slow and steady pace today.",
        "calm":     "Steady magnetic backdrop—set your goals and enjoy the flow.",
        "neutral":  "Standard energy field—consistency wins today.",
    }
    cap_out = cap_map.get(tone, cap_map["neutral"])

    return {
        "caption": _scrub_banned_phrases(_sanitize_caption(cap_out)),
        "snapshot": _scrub_banned_phrases(qual_snap),
        "affects": _scrub_banned_phrases(rc_fallback["affects"]),
        "playbook": _scrub_banned_phrases(rc_fallback["playbook"]),
        "hashtags": rc_fallback.get("hashtags", "#GaiaEyes #SpaceWeather #Wellness #HRV #Sleep"),
    }

# --- deterministic snapshot builder ---
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

# --- qualitative, number-free snapshot builder ---

def _qualitative_snapshot(ctx: Dict[str, Any]) -> str:
    """Compose a brief, human overview (no numbers) for the snapshot section.
    Keeps the same key ('snapshot') so downstream remains compatible.
    """
    tone = _tone_from_ctx(ctx)
    kp_band = _band_kp(ctx.get("kp_max_24h"))
    sw_band = _band_sw(ctx.get("solar_wind_kms"))
    bz_txt  = _bz_desc(ctx.get("bz_min"))
    flr  = ctx.get("flares_24h")
    cmes = ctx.get("cmes_24h")
    sr   = ctx.get("schumann_value_hz")

    lines: List[str] = []

    # Lead sentence based on tone/bands
    if tone == "stormy":
        lines.append("Charged field day—expect short surges and dips in energy.")
    elif tone == "unsettled":
        lines.append("Lively field day—more waves than a full storm.")
    elif tone == "calm":
        lines.append("Steady magnetic backdrop—a good day for focused work and recovery.")
    else:
        lines.append("Middle-of-the-road field day—consistency wins.")

    # Optional humor/metaphor line (fallback only)
    mh = (ctx.get("metaphor_hint") or "").strip()
    if mh:
        lines.append(f"Translation: it can feel like {mh} for some—pace the big stuff.")

    # Solar drivers without citing numbers
    driver_bits: List[str] = []
    if (cmes or 0) > 0:
        driver_bits.append("recent CME after-effects")
    if (flr or 0) > 0:
        driver_bits.append("fresh flare activity")
    if bz_txt in ("southward", "strong southward", "slightly southward"):
        driver_bits.append("southward IMF windows")
    if sw_band in ("elevated", "high", "very-high"):
        driver_bits.append("faster solar wind")
    if driver_bits:
        lines.append("Drivers: " + ", ".join(driver_bits) + ".")

    # Schumann / resonance context
    if isinstance(sr, (int, float)) and sr:
        lines.append("Schumann resonance reads on the lively side at times, matching reports of vivid dreams or restlessness for some.")
    else:
        lines.append("Resonance bed looks ordinary overall.")

    # Aurora chances
    if ctx.get("aurora_headline"):
        lines.append("Aurora chances look favorable at higher latitudes—dark skies after local midnight tend to help.")

    # Recent notable quakes
    if ctx.get("quakes_count"):
        lines.append("Recent notable earthquakes were logged; keep news checks brief if you’re prone to stress.")

    # Severe weather
    if ctx.get("severe_summary"):
        lines.append("Regional storm/flood alerts are active—check local guidance if you’re in the affected area.")

    # Close with guidance intent
    lines.append("Keep a steady rhythm; if you run sensitive, utilize quick breath resets and short movement breaks.")

    return "Space Weather Snapshot\n" + " ".join(lines)
# ============================================================
# Optional pulse file: aurora, quakes, severe
# ============================================================

def _load_pulse_cards(pulse_path: str) -> Dict[str, Any]:
    """Read a pulse.json-like file and extract compact signals for context.
    Expected structure: {"timestamp_utc": ..., "cards": [{"type": ..., ...}]}
    Returns keys safe to merge into ctx and metrics.
    """
    try:
        p = Path(pulse_path)
        if not p.exists():
            _dbg(f"pulse: not found at {pulse_path}")
            return {}
        data = json.loads(p.read_text(encoding="utf-8"))
        cards = data.get("cards", []) or []
        out: Dict[str, Any] = {}
        # Aurora forecast
        aur = next((c for c in cards if c.get("type") == "aurora"), None)
        if aur:
            ad = aur.get("data", {}) or {}
            out["aurora_headline"] = ad.get("headline") or aur.get("title")
            out["aurora_window"] = aur.get("time_window")
            out["aurora_severity"] = aur.get("severity")
        # Quake: count and last title
        quakes = [c for c in cards if c.get("type") == "quake"]
        if quakes:
            out["quakes_count"] = len(quakes)
            # take the most recent item
            q0 = sorted(quakes, key=lambda c: c.get("data", {}).get("time_utc") or c.get("time_window") or "", reverse=True)[0]
            out["quake_top_title"] = q0.get("title")
            out["quake_top_summary"] = q0.get("summary")
        # Severe weather summary (if any)
        sev = next((c for c in cards if c.get("type") == "severe"), None)
        if sev:
            out["severe_summary"] = sev.get("summary")
            out["severe_window"] = sev.get("time_window")
        return out
    except Exception as e:
        _dbg(f"pulse: failed to load -> {e}")
        return {}

# ============================================================
# Optional space_weather.json loader (now/next_72h/impacts)
# ============================================================

def _load_space_weather(space_path: str) -> Dict[str, Any]:
    """Read a space_weather.json-like file and extract compact signals for context.
    Expected structure:
    {
      "timestamp_utc": "...",
      "now": {"kp": 2.0, "solar_wind_kms": 302, "bz_nt": -4.0},
      "next_72h": {"headline": "G1 possible", "confidence": "high"},
      "impacts": {"aurora": "Mostly confined to polar regions"}
    }
    Returns dict safe to merge into ctx.
    """
    try:
        p = Path(space_path)
        if not p.exists():
            _dbg(f"space_json: not found at {space_path}")
            return {}
        data = json.loads(p.read_text(encoding="utf-8"))
        out: Dict[str, Any] = {}
        now = data.get("now") or {}
        if isinstance(now, dict):
            if now.get("kp") is not None:
                out["kp_now"] = to_float(now.get("kp"))
            if now.get("solar_wind_kms") is not None:
                out["solar_wind_kms_now"] = to_float(now.get("solar_wind_kms"))
            if now.get("bz_nt") is not None:
                out["bz_now"] = to_float(now.get("bz_nt"))
        nx = data.get("next_72h") or {}
        if isinstance(nx, dict) and nx.get("headline"):
            out["aurora_headline"] = str(nx.get("headline")).strip()
            out["aurora_window"] = "Next 72h"
        imp = data.get("impacts") or {}
        if isinstance(imp, dict) and imp.get("aurora"):
            # If headline missing, use impacts.aurora as a softer headline
            out.setdefault("aurora_headline", str(imp.get("aurora")).strip())
        return out
    except Exception as e:
        _dbg(f"space_json: failed to load -> {e}")
        return {}

def _fetch_space_outlook_context() -> Dict[str, Any]:
    """
    Pull compact context from backend outlook endpoint:
      /v1/space/forecast/outlook
    """
    if not EARTHSCOPE_API_BASE:
        return {}

    def _dig(obj: Any, *path: str) -> Any:
        cur = obj
        for key in path:
            if not isinstance(cur, dict):
                return None
            cur = cur.get(key)
            if cur is None:
                return None
        return cur

    suffix = EARTHSCOPE_OUTLOOK_PATH if EARTHSCOPE_OUTLOOK_PATH.startswith("/") else f"/{EARTHSCOPE_OUTLOOK_PATH}"
    url = f"{EARTHSCOPE_API_BASE}{suffix}"
    headers = {"Accept": "application/json"}
    if EARTHSCOPE_API_BEARER:
        headers["Authorization"] = f"Bearer {EARTHSCOPE_API_BEARER}"

    try:
        r = requests.get(url, headers=headers, timeout=20)
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, dict):
            return {}

        out: Dict[str, Any] = {}
        kp_now = _dig(data, "kp", "now")
        kp_max = _dig(data, "kp", "last_24h_max")
        if kp_now is not None:
            out["kp_now"] = to_float(kp_now)
        if kp_max is not None:
            out["kp_max_24h"] = to_float(kp_max)

        bz_now = data.get("bz_now")
        sw_now = data.get("sw_speed_now_kms")
        if bz_now is not None:
            out["bz_now"] = to_float(bz_now)
        if sw_now is not None:
            out["solar_wind_kms_now"] = to_float(sw_now)

        # Optional enrichers for narrative context if present
        impacts_aurora = _dig(data, "impacts", "aurora")
        if isinstance(impacts_aurora, str) and impacts_aurora.strip():
            out["aurora_headline"] = impacts_aurora.strip()
            out["aurora_window"] = "Next 72h"

        # cme count fallback if endpoint includes it
        cme_count = data.get("earth_directed_cme_count_24h")
        if cme_count is None:
            cme_count = _dig(data, "cme", "earth_directed_count_24h")
        if cme_count is not None:
            out["cmes_24h"] = to_float(cme_count)

        return out
    except Exception as e:
        _dbg(f"outlook_api: fetch failed -> {e}")
        return {}

# ============================================================
# Optional earthscope.json loader (consolidated card)
# ============================================================

def _load_earthscope_card(card_path: str) -> Dict[str, Any]:
    """Read earthscope.json (consolidated card) and return compact dict for merging.
    Expected structure (varies): title, caption, affects, playbook, metrics{ ... }, sections{...}, quakes{...}
    Returns dict keys safe to merge into ctx and to pass-through in metrics_json.
    """
    out: Dict[str, Any] = {}
    try:
        p = Path(card_path)
        if not p.exists():
            _dbg(f"earth_card: not found at {card_path}")
            return out
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return out
        # pass-through pieces
        out["title"] = data.get("title")
        out["caption"] = data.get("caption")
        out["affects"] = data.get("affects")
        out["playbook"] = data.get("playbook")
        if isinstance(data.get("sections"), dict):
            out["sections"] = data["sections"]
        # metrics subset
        m = data.get("metrics") or {}
        if isinstance(m, dict):
            out["metrics"] = m
            # mergeables for ctx
            if m.get("schumann_value_hz") is not None:
                out["schumann_value_hz"] = to_float(m.get("schumann_value_hz"))
            # aurora hints
            sx = m.get("space_json") or {}
            if isinstance(sx, dict):
                if sx.get("aurora_headline"):
                    out["aurora_headline"] = str(sx.get("aurora_headline")).strip()
                if sx.get("aurora_window"):
                    out["aurora_window"] = str(sx.get("aurora_window")).strip()
        # quakes (if present)
        qk = data.get("quakes") or {}
        if isinstance(qk, dict):
            out["quakes"] = qk
            # e.g., set a count hint for narrative
            if qk.get("total_24h") is not None:
                out["quakes_count"] = int(qk.get("total_24h"))
        return out
    except Exception as e:
        _dbg(f"earth_card: failed to load -> {e}")
        return out

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


# --- Fetch most-recent Kp value from marts.kp_obs ---
def fetch_kp_now_from_marts(day: str) -> Optional[float]:
    """
    Get a 'now-ish' Kp value from marts.kp_obs.
    Strategy:
      1) Try the latest row within the last 12h.
      2) Fallback to the latest row overall.
    """
    # Prefer last 12h
    try:
        since_iso = (datetime.utcnow() - timedelta(hours=12)).replace(microsecond=0, tzinfo=None).isoformat() + "Z"
        res = (
            SB.schema(SPACE_SCHEMA)
              .table(KPOBS_TABLE)
              .select("kp_time,kp")
              .gte("kp_time", since_iso)
              .order("kp_time", desc=True)
              .limit(1)
              .execute()
        )
        row = (res.data or [None])[0]
        if row and row.get("kp") is not None:
            return to_float(row["kp"])
    except Exception as e:
        print(f"[WARN] kp_obs recent fetch failed: {e}")
    # Latest overall
    try:
        res2 = (
            SB.schema(SPACE_SCHEMA)
              .table(KPOBS_TABLE)
              .select("kp_time,kp")
              .order("kp_time", desc=True)
              .limit(1)
              .execute()
        )
        row2 = (res2.data or [None])[0]
        if row2 and row2.get("kp") is not None:
            return to_float(row2["kp"])
    except Exception as e:
        print(f"[WARN] kp_obs latest fetch failed: {e}")
    return None


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

def _chat_create_compat(client: "OpenAI", **kwargs):
    """
    Compatibility wrapper for model families that require either
    max_completion_tokens or max_tokens, and may not allow custom
    sampling/penalty parameters.
    """
    attempt_kwargs = dict(kwargs)
    for _ in range(5):
        try:
            return client.chat.completions.create(**attempt_kwargs)
        except Exception as e:
            msg = str(e)
            changed = False

            if (
                "Unsupported parameter: 'max_completion_tokens'" in msg
                or "unexpected keyword argument 'max_completion_tokens'" in msg
            ) and "max_completion_tokens" in attempt_kwargs:
                attempt_kwargs["max_tokens"] = attempt_kwargs.pop("max_completion_tokens")
                changed = True

            if (
                "Unsupported parameter: 'max_tokens'" in msg
                or "unexpected keyword argument 'max_tokens'" in msg
            ) and "max_tokens" in attempt_kwargs:
                attempt_kwargs["max_completion_tokens"] = attempt_kwargs.pop("max_tokens")
                changed = True

            for param in ("temperature", "top_p", "presence_penalty", "frequency_penalty", "reasoning_effort"):
                if (
                    f"Unsupported parameter: '{param}'" in msg
                    or f"unexpected keyword argument '{param}'" in msg
                    or f"Unsupported value: '{param}'" in msg
                ) and param in attempt_kwargs:
                    attempt_kwargs.pop(param, None)
                    changed = True

            if (
                "Unsupported parameter: 'response_format'" in msg
                or "unexpected keyword argument 'response_format'" in msg
                or "Unsupported value: 'response_format'" in msg
            ) and "response_format" in attempt_kwargs:
                attempt_kwargs.pop("response_format", None)
                changed = True

            if changed:
                continue
            raise
    raise RuntimeError("openai chat completion compatibility retries exhausted")

def _chat_text(resp: Any) -> str:
    """Extract text safely from a chat completion response across SDK shapes."""
    try:
        choice0 = resp.choices[0]
    except Exception:
        return ""
    msg = getattr(choice0, "message", None)
    if msg is None:
        return ""

    content = getattr(msg, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            txt = None
            if isinstance(item, dict):
                txt = item.get("text") or item.get("content")
            else:
                txt = getattr(item, "text", None) or getattr(item, "content", None)
            if isinstance(txt, str) and txt.strip():
                parts.append(txt.strip())
        if parts:
            return "\n".join(parts)

    # Rare fallback: function/tool argument payloads
    fc = getattr(msg, "function_call", None)
    if fc is not None:
        args = getattr(fc, "arguments", None)
        if isinstance(args, str):
            return args
    tool_calls = getattr(msg, "tool_calls", None)
    if tool_calls:
        try:
            first = tool_calls[0]
            fn = first.get("function") if isinstance(first, dict) else getattr(first, "function", None)
            args = fn.get("arguments") if isinstance(fn, dict) else getattr(fn, "arguments", None)
            if isinstance(args, str):
                return args
        except Exception:
            pass
    return ""

# --- Single-call rewrite cache (avoid double API calls in one run) ---
_REWRITE_CACHE: Dict[str, Dict[str, str]] = {}


def _rewrite_cache_key(ctx: Dict[str, Any]) -> tuple[str, str]:
    day_iso = _ctx_day_iso(ctx)
    platform = _ctx_platform(ctx)
    model = _writer_model() or ""
    ctx_hash = _stable_ctx_hash(ctx)
    raw = f"{day_iso}|{platform}|{model}|{ctx_hash}"
    key = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    _dbg(f"rewrite-cache: day={day_iso} platform={platform} model={model or 'none'} ctx={ctx_hash[:10]} key={key[:12]}")
    return key, key[:12]

def _get_cached_rewrite(client: Optional["OpenAI"], ctx: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """Compute interpretive JSON rewrite once per run and cache it. Returns dict or None."""
    key, key_short = _rewrite_cache_key(ctx)
    _dbg("rewrite-cache: check")
    if key in _REWRITE_CACHE:
        _dbg(f"rewrite-cache: hit key={key_short}")
        return _REWRITE_CACHE.get(key)
    if not client:
        _dbg("rewrite-cache: no client; skipping")
        return None
    rc_local = _rule_copy(ctx)
    _dbg(f"rewrite-cache: miss key={key_short}; computing via LLM")
    out = _llm_rewrite_from_rules(
        client,
        rc_local["caption"], rc_local["snapshot"], rc_local["affects"], rc_local["playbook"], ctx
    )
    if out:
        _REWRITE_CACHE[key] = out
    _dbg(f"rewrite-cache: {'stored' if key in _REWRITE_CACHE else 'compute failed; using None'} key={key_short}")
    return _REWRITE_CACHE.get(key)




def _apply_intro_guard(caption: str, ctx: Dict[str, Any]) -> str:
    day_iso = _ctx_day_iso(ctx)
    platform = _ctx_platform(ctx)
    banned = [x for x in (ctx.get("banned_openers") or []) if isinstance(x, str)]
    intro = str(ctx.get("intro_hint") or "").strip() or _select_intro_line(day_iso, platform, banned)
    if not caption:
        return intro

    cap = caption.strip()
    intro_l = intro.strip().lower()
    cap_l = cap.lower()

    # If the model already started with the intro (often followed by more text on the same line),
    # do not prepend it again.
    if cap_l.startswith(intro_l):
        return cap

    first = _first_nonempty_line(cap)
    if first.strip().lower() == intro_l:
        return cap
    if first.strip().lower() in {b.strip().lower() for b in banned if b.strip()}:
        body = cap.splitlines()
        body = "\n".join(body[1:]).strip() if len(body) > 1 else ""
        return f"{intro} {body}".strip()
    return f"{intro} {cap}".strip()

def generate_short_caption(ctx: Dict[str, Any]) -> (str, str):
    client = openai_client()
    if EARTHSCOPE_FORCE_RULES or not client:
        rc = _rule_copy(ctx)
        return rc["caption"].strip(), rc["hashtags"]

    # Hybrid: generate rule copy and ask LLM to tighten it (no change of facts)
    rc = _rule_copy(ctx)
    try_rewrite = os.getenv("EARTHSCOPE_HYBRID_REWRITE", "true").strip().lower() in ("1","true","yes","on")
    if try_rewrite:
        # New: interpretive, number-free JSON rewrite (cached single-call reuse)
        out = _get_cached_rewrite(client, ctx)
        if out and out.get("caption"):
            cap = out["caption"]

            # Encourage fuller paragraph; ensure period on calm day
            if _tone_from_ctx(ctx) == "calm" and not cap.endswith("."):
                cap += "."

            # Sanitize and avoid sterile bulletin-style openers
            cap = _sanitize_caption(cap)
            first_line = _first_nonempty_line(cap).lower()
            if any(first_line.startswith(p) for p in BAN_CAPTION_OPENERS):
                tone = _tone_from_ctx(ctx)
                hook = _pick_hook(tone, last_used=_recent_openers(7))
                first_split = re.split(r"(?<=\.)\s+", cap, maxsplit=1)
                rest = first_split[1] if len(first_split) > 1 else cap
                cap = f"{hook} {rest}".strip()

            cap = _scrub_banned_phrases(cap)

            # Append daily field summary footer
            kp = ctx.get("kp_max_24h"); bz = ctx.get("bz_min"); sr = ctx.get("schumann_value_hz")
            footer = []
            if kp is not None:
                footer.append(f"Kp {_fmt_num(kp,1)}")
            if bz is not None:
                footer.append(f"Bz {_fmt_num(bz,1)} nT")
            if sr is not None:
                footer.append(f"Schumann {_fmt_num(sr,2)} Hz")
            if footer:
                cap += f"\n\n— {'  •  '.join(footer)} (snapshot at write time)"
            return cap.strip(), out.get("hashtags", rc.get("hashtags", "#GaiaEyes #SpaceWeather"))

    kp_now = ctx.get("kp_now")
    kp_max = ctx.get("kp_max_24h")
    wind   = ctx.get("solar_wind_kms")
    flr    = ctx.get("flares_24h")
    cme    = ctx.get("cmes_24h")
    sr     = ctx.get("schumann_value_hz")
    sr_note= ctx.get("schumann_note")

    model = _writer_model()
    if not model:
        rc = _rule_copy(ctx)
        return rc["caption"].strip(), rc.get("hashtags", "#GaiaEyes #SpaceWeather")
    try:
        resp = _chat_create_compat(
            client,
            model=model,
            temperature=0.7,
            presence_penalty=0.3,
            frequency_penalty=0.2,
            max_completion_tokens=320,
            messages=[
                {"role":"system","content":(
                    "You are Gaia Eyes' space‑weather writer. Write an accurate, human, relatable and slightly humorous caption. "
                    "Do not start with questions or phrases like 'Feeling', 'Are you', 'Ever feel', 'Ready to', 'Let’s'. "
                    "Never use emojis. Vary openings day‑to‑day."
                )},
                {"role":"user","content":(
                    "Using the data below, write one short, viral‑friendly humorous caption for Gaia Eyes. "
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
        # Prevent sterile bulletin-style openers (check first non-empty line only)
        first_line = _first_nonempty_line(caption).lower()
        if any(first_line.startswith(p) for p in BAN_CAPTION_OPENERS):
            tone = _tone_from_ctx(ctx)
            hook = _pick_hook(tone, last_used=_recent_openers(7))
            first_split = re.split(r"(?<=\.)\s+", caption, maxsplit=1)
            rest = first_split[1] if len(first_split) > 1 else caption
            caption = f"{hook} {rest}".strip()
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
            hashtags = "#GaiaEyes #SpaceWeather #Schumann #ChronicPain #Health #localtriggers"
        caption = _scrub_banned_phrases(caption)
        return caption.strip(), hashtags
    except Exception:
        rc = _rule_copy(ctx)
        return rc["caption"].strip(), rc["hashtags"]


def generate_long_sections(ctx: Dict[str, Any]) -> (str, str, str, str):
    client = openai_client()
    if EARTHSCOPE_FORCE_RULES or not client:
        rc = _rule_copy(ctx)
        return rc["snapshot"], rc["affects"], rc["playbook"], rc["hashtags"]
    # Hybrid paraphrase path
    try_rewrite = os.getenv("EARTHSCOPE_HYBRID_REWRITE", "true").strip().lower() in ("1","true","yes","on")
    if try_rewrite:
        # New: interpretive, number-free JSON rewrite (cached single-call reuse)
        out = _get_cached_rewrite(client, ctx)
        if out:
            return out["snapshot"], out["affects"], out["playbook"], out.get("hashtags", "#GaiaEyes #SpaceWeather #Wellness #HeartBrain")

    # Fallback: legacy LLM block splitting
    kp_now = ctx.get("kp_now")
    kp_max = ctx.get("kp_max_24h")
    wind   = ctx.get("solar_wind_kms")
    flr    = ctx.get("flares_24h")
    cme    = ctx.get("cmes_24h")
    sr     = ctx.get("schumann_value_hz")
    sr_note= ctx.get("schumann_note")

    model = _writer_model()
    if not model:
        rc = _rule_copy(ctx)
        return rc["snapshot"], rc["affects"], rc["playbook"], rc["hashtags"]
    prompt = f"""
Using the data below, create a Gaia Eyes–branded daily forecast with THREE sections and a hashtags line:
1) Space Weather Snapshot — bullet the numbers (Kp now/max, solar wind, flares/CMEs, Schumann). Omit any bullet whose value is missing/None.
2) How This Affects You — 4 concise bullets for mood, energy, heart, nervous system.
3) Self-Care Playbook — 3–5 practical tips tailored to today.
End with 4–6 hashtags on the last line. Tone: friendly, funny, engaging, a bit viral. Avoid dates. Render flare/ CME counts as integers.

Data:
- Kp now: {kp_now}
- Kp max (24h): {kp_max}
- Solar wind speed (km/s): {wind}
- Flares past 24h: {flr}
- CMEs past 24h: {cme}
- Schumann: {sr} Hz ({sr_note})
""".strip()
    try:
        resp = _chat_create_compat(
            client,
            model=model, temperature=0.75, max_completion_tokens=900,
            messages=[{"role":"system","content":"You are Gaia Eyes' space weather writer. Be accurate, warm, and helpful. Balance science, humor and mysticism."},
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
            hashtags = "#GaiaEyes #SpaceWeather #Wellness #Mindfulness #Frequency"
        # sanitize hashtags: ensure the final line is a real hashtag line
        if not hashtags or not hashtags.strip().startswith("#"):
            hashtags = "#GaiaEyes #SpaceWeather #Wellness #Frequency #ChronicPain"
        # Strip any duplicate self-added headers
        snapshot = _strip_intro_header(snapshot)
        affects  = _strip_intro_header(affects)
        playbook = _strip_intro_header(playbook)
        snapshot = _scrub_banned_phrases(snapshot)
        affects = _scrub_banned_phrases(affects)
        playbook = _scrub_banned_phrases(playbook)
        return snapshot.strip(), affects.strip(), playbook.strip(), hashtags
    except Exception:
        rc = _rule_copy(ctx)
        return rc["snapshot"], rc["affects"], rc["playbook"], rc["hashtags"]
# ============================================================
# Web/app JSON emit (optional)
# ============================================================
def emit_earthscope_json(day: str, title: str, caption: str, snapshot: str, affects: str, playbook: str, metrics: Dict[str, Any]):
    if not EARTHSCOPE_OUTPUT_JSON:
        return
    payload = {
        "day": day,
        "title": title,
        "caption": caption,
        "snapshot": snapshot,
        "affects": affects,
        "playbook": playbook,
        "metrics": metrics,
        "timestamp_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")
    }
    try:
        out = Path(EARTHSCOPE_OUTPUT_JSON)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, separators=(",",":"), ensure_ascii=False), encoding="utf-8")
        print(f"[earthscope] wrote card JSON -> {out}")
    except Exception as e:
        print(f"[WARN] failed to write earthscope card JSON: {e}")

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
        "bz_min": sw.get("bz_min"),
        "solar_wind_kms": sw.get("solar_wind_kms"),
        "flares_24h": sw.get("flares_24h"),
        "cmes_24h": sw.get("cmes_24h"),
        "schumann_value_hz": sr.get("schumann_value_hz"),
        "schumann_note": sr.get("schumann_note"),
        "harmonics": sr.get("schumann_harmonics"),
        "day": day,
        "platform": args.platform,
    }
    ctx["banned_openers"] = _recent_platform_openers(args.platform, limit=3)
    ctx["intro_hint"] = _select_intro_line(day, args.platform, ctx.get("banned_openers"))
    ctx["metaphor_hint"] = _select_metaphor_hint(day, args.platform)

    # Fill Kp 'now' from the marts if available
    try:
        kp_now_db = fetch_kp_now_from_marts(day)
        if kp_now_db is not None:
            ctx["kp_now"] = kp_now_db
    except Exception as e:
        print(f"[WARN] kp_now fetch failed: {e}")

    # Merge /v1/space/forecast/outlook signals (now KP/Bz/SW + impacts)
    outlook_ctx = {}
    try:
        outlook_ctx = _fetch_space_outlook_context()
        if outlook_ctx:
            # Prefer mart-derived daily values; use outlook as fallback/now-context
            if ctx.get("kp_now") is None and outlook_ctx.get("kp_now") is not None:
                ctx["kp_now"] = outlook_ctx.get("kp_now")
            if ctx.get("kp_max_24h") is None and outlook_ctx.get("kp_max_24h") is not None:
                ctx["kp_max_24h"] = outlook_ctx.get("kp_max_24h")
            if ctx.get("solar_wind_kms") is None and outlook_ctx.get("solar_wind_kms_now") is not None:
                ctx["solar_wind_kms"] = outlook_ctx.get("solar_wind_kms_now")
            if ctx.get("bz_min") is None and outlook_ctx.get("bz_now") is not None:
                ctx["bz_min"] = outlook_ctx.get("bz_now")
            if outlook_ctx.get("solar_wind_kms_now") is not None:
                ctx["sw_now"] = outlook_ctx.get("solar_wind_kms_now")
            if outlook_ctx.get("bz_now") is not None:
                ctx["bz_now"] = outlook_ctx.get("bz_now")
            if ctx.get("cmes_24h") is None and outlook_ctx.get("cmes_24h") is not None:
                ctx["cmes_24h"] = outlook_ctx.get("cmes_24h")
            if outlook_ctx.get("aurora_headline"):
                ctx["aurora_headline"] = outlook_ctx.get("aurora_headline")
                ctx["aurora_window"] = outlook_ctx.get("aurora_window")
            _dbg("outlook_api: merged into ctx")
    except Exception as e:
        _dbg(f"outlook_api: merge failed -> {e}")

    # Aurora: only mention when notable (Kp >= 5). Otherwise omit aurora entirely.
    src_kp = ctx.get("kp_max_24h") if ctx.get("kp_max_24h") is not None else ctx.get("kp_now")
    kp_f = None
    try:
        kp_f = float(src_kp) if src_kp is not None else None
    except Exception:
        kp_f = None

    if kp_f is not None and kp_f >= 5.0:
        hed, sev = _derive_aurora_from_kp(kp_f)
        ctx["aurora_headline"] = hed
        ctx.setdefault("aurora_window", "Next 24h")
        ctx["aurora_severity"] = sev
    else:
        ctx["aurora_headline"] = None
        ctx["aurora_severity"] = "G0"

    # 2) Generate copy
    short_caption, short_tags = generate_short_caption(ctx)
    snapshot, affects, playbook, long_tags = generate_long_sections(ctx)
    _, dbg_key_short = _rewrite_cache_key(ctx)
    opener = _first_nonempty_line(short_caption)
    _dbg(f"opener={opener[:120]} day={day} platform={args.platform} cache_key={dbg_key_short}")

    # === Structured sections payload for renderers (back-compat) ===
    tone = _tone_from_ctx(ctx)
    bands = {
        "kp": _band_kp(ctx.get("kp_max_24h")),
        "sw": _band_sw(ctx.get("solar_wind_kms")),
        "bz": _bz_desc(ctx.get("bz_min")),
    }
    sections_struct = {
        "caption": short_caption,
        "snapshot": snapshot,
        "affects": affects,
        "playbook": playbook,
    }

    # Title via LLM (uses cached rewrite), with safe heuristic fallback
    client = openai_client()
    llm_title = None
    if client:
        try:
            llm_title = _llm_title_from_context(client, ctx, _REWRITE_CACHE.get(_rewrite_cache_key(ctx)[0]))
        except Exception:
            llm_title = None
    if llm_title:
        title = llm_title
    else:
        # Fallback heuristic (previous behavior)
        kpmax = ctx.get("kp_max_24h"); wind  = ctx.get("solar_wind_kms")
        if kpmax is None and wind is None:
            title = "Space Weather Update"
        elif kpmax is not None and kpmax >= 6:
            title = "Geomagnetic Storm Watch"
        elif kpmax is not None and kpmax >= 4:
            title = "Active Geomagnetics"
        elif wind is not None and wind >= 600:
            title = "High-Speed Solar Wind"
        else:
            # nudge small variety on calm days
            calm_titles = ["Magnetic Calm","Steady Field","Quiet Skies","Clear Runway"]
            random.seed(_daily_seed()); title = random.choice(calm_titles)

    # 3) Prepare payloads
    metrics_json = {
        "kp_max_24h": ctx.get("kp_max_24h"),
        "solar_wind_kms": ctx.get("solar_wind_kms"),
        "flares_24h": ctx.get("flares_24h"),
        "cmes_24h": ctx.get("cmes_24h"),
        "schumann_value_hz": ctx.get("schumann_value_hz"),
        "harmonics": ctx.get("harmonics"),
        "space_json": {
            "kp_now": ctx.get("kp_now"),
            "bz_now": ctx.get("bz_now"),
            "sw_now": ctx.get("sw_now"),
            "aurora_headline": ctx.get("aurora_headline"),
            "aurora_window": ctx.get("aurora_window"),
        },
        "space_outlook": outlook_ctx or None,
        "tone": tone,
        "bands": bands,
        "sections": sections_struct,
    }
    sources_json = {
        "marts.space_weather_daily": True,
        "marts.schumann_daily": True,
        "api.v1.space.forecast.outlook": bool(outlook_ctx),
    }

    # 4) Emit optional JSON for web/app card
    emit_earthscope_json(
        day=day,
        title=title,
        caption=short_caption,
        snapshot=snapshot,
        affects=affects,
        playbook=playbook,
        metrics=metrics_json
    )

    # Build final body markdown and upsert (single row per date/platform)
    body_md = (
        "Gaia Eyes — Daily EarthScope\n\n" +
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
