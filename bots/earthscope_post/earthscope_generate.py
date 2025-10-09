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
import math
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List

STYLE_GUIDE = (
    "Persona: holistic clinician‑researcher who studies space/earth frequencies and their effects on physiology. "
    "Voice: clinical, plain‑language, humane, lightly empathic; first‑person is OK in short asides. "
    "Audience: people who consider themselves sensitive (HRV, sleep, nerve/pain flares during storms). "
    "Rules: facts first; never contradict provided metrics; no emojis; no rhetorical questions. "
    "Prefer terms like 'geomagnetic activity', 'autonomic/HRV', 'sleep continuity', 'GNSS accuracy'. "
    "Never claim deterministic health effects; use 'some may', 'can', 'tends to', 'I often see'. "
    "Keep sections compact and scannable."
)
BAN_PHRASES = [
    "energy is calm", "calm vibes", "mindful living", "cosmic vibes",
    "mother earth recharge", "sound bath", "tap into", "manifest", "alchemy",
    "grounding energy", "soothe your soul"
]

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

# Output JSON for website/app card (optional)
EARTHSCOPE_OUTPUT_JSON = os.getenv("EARTHSCOPE_OUTPUT_JSON_PATH")  # e.g., ../gaiaeyes-media/data/earthscope_daily.json
EARTHSCOPE_FORCE_RULES = os.getenv("EARTHSCOPE_FORCE_RULES", "false").strip().lower() in ("1","true","yes","on")
# Toggle for first-person clinical asides in affects/playbook
EARTHSCOPE_FIRST_PERSON = os.getenv("EARTHSCOPE_FIRST_PERSON", "true").strip().lower() in ("1","true","yes","on")

# Debug flag for rewrite path tracing
EARTHSCOPE_DEBUG_REWRITE = os.getenv("EARTHSCOPE_DEBUG_REWRITE", "false").strip().lower() in ("1","true","yes","on")

def _dbg(msg: str) -> None:
    if EARTHSCOPE_DEBUG_REWRITE:
        print(f"[earthscope.debug] {msg}")
PHRASE_VARIANTS = {
    "feel_stable": [
        "Steady backdrop—good window for structured work.",
        "Quieter field—use the clarity for deep tasks.",
        "Stable profile—set a simple plan and move steadily."
    ],
    "feel_unsettled": [
        "Pulses and dips—short blocks, gentle pacing.",
        "Variable flow—add margins around focus.",
        "Bit of texture—aim for rhythm over intensity."
    ],
    "sleep_guard": [
        "Dim light earlier; protect sleep continuity.",
        "Wind down on schedule; keep evenings warm‑lit.",
        "Guard bedtime routine; keep screens softer."
    ],
    "nerve_note": [
        "If you run sensitive, brief tingles or nerve heaviness can show—plan micro‑breaks.",
        "Sensitives can feel more wired; keep shoulders relaxed, jaw unclenched.",
        "If pain flares on stormy days, keep heat/contrast and pacing nearby."
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
        trailing = "Expect geomagnetic sensitivity windows; protect focus blocks."
    elif tone == "unsettled":
        trailing = "Some variability—schedule breaks and buffer critical tasks."
    elif tone == "calm":
        trailing = "Stable backdrop—good day for deep work and recovery."
    else:
        trailing = "Moderate profile—steady cadence tends to work best."
    caption = f"{cap_lead}. {trailing}"

    # Snapshot bullets (only present values)
    snap = []
    if kp is not None: snap.append(f"- Kp max (24h): { _fmt_num(kp,1) }")
    if sw is not None: snap.append(f"- Solar wind: { int(round(float(sw))) } km/s")
    if bz is not None: snap.append(f"- Bz: { _fmt_num(bz,1) } nT ({bz_txt})")
    if flr is not None: snap.append(f"- Flares (24h): {int(round(float(flr)))}")
    if cme is not None: snap.append(f"- CMEs (24h): {int(round(float(cme)))}")
    if sr is not None: snap.append(f"- Schumann f0: { _fmt_num(sr,2) } Hz")
    snapshot = "Space weather snapshot\n" + "\n".join(snap)

    # How it may feel (human clinical tone)
    feel = []
    if tone in ("stormy","unsettled"):
        feel.append(f"- Focus/energy: {_pick_variant('feel_unsettled') or 'Expect ebbs/spikes; keep sprints short.'}")
        feel.append("- Autonomic/HRV: Southward Bz or higher Kp can nudge HRV down in some; paced breathing helps.")
        feel.append(f"- Sleep: {_pick_variant('sleep_guard')}")
        if EARTHSCOPE_FIRST_PERSON:
            feel.append(f"- Clinician note: {_pick_variant('nerve_note', seed_extra=1)}")
        else:
            feel.append(f"- Sensitivity note: {_pick_variant('nerve_note', seed_extra=1)}")
        feel.append("- Comms/GNSS: Minor accuracy or HF variability is possible at higher latitudes.")
    else:
        feel.append(f"- Focus/energy: {_pick_variant('feel_stable') or 'Stable; good window for structured work.'}")
        feel.append("- Autonomic/HRV: Conditions generally support recovery and coherence practices.")
        feel.append("- Sleep: Keep evening light warm and low; usual hygiene works.")
        if EARTHSCOPE_FIRST_PERSON:
            feel.append("- Clinician note: I see steadier HRV and less reactivity for many on days like this.")
    affects = "How it may feel\n" + "\n".join(feel)

    # Care notes (practical, small set)
    care_lines = []
    if tone in ("stormy","unsettled"):
        care_lines.append("- 5–10 min paced breathing (e.g., 4:6) or brief HRV biofeedback")
        care_lines.append("- Hydration + electrolytes; short daylight exposure; gentle mobility")
        care_lines.append("- Protect sleep: blue‑light filters and a consistent wind‑down")
        care_lines.append("- If sensitive, quick grounding/outdoor walk; warm pack for nerve flare windows")
    else:
        care_lines.append("- Block 1–2 focus sessions (60–90 min) while the field is steady")
        care_lines.append("- Natural light and movement breaks to reinforce circadian tone")
        care_lines.append("- Hydrate; keep caffeine earlier in the day")
    playbook = "Care notes\n" + "\n".join(care_lines)

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
    return s.strip()

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


def _validate_rewrite(obj: Any) -> Optional[Dict[str, str]]:
    """Ensure JSON has required keys and no numerals in text fields."""
    if not isinstance(obj, dict):
        return None
    required = ["caption", "snapshot", "affects", "playbook", "hashtags"]
    for k in required:
        if k not in obj or not isinstance(obj[k], str):
            return None
    # Enforce number-free narrative in main fields (hashtags may include numbers, allow there)
    for k in ["caption", "snapshot", "affects", "playbook"]:
        if _contains_digits(obj[k]):
            return None
    return obj  # looks valid


def _rewrite_json_interpretive(client: Optional["OpenAI"], draft: Dict[str, str], facts: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """Call the LLM to rewrite into interpretive, number-free JSON. Returns dict or None."""
    if not client:
        return None

    system_msg = (
        "You are Gaia Eyes’ daily author. Interpret today’s space/earth conditions for humans. "
        "Do NOT cite numeric measurements or units (e.g., 'Kp 4.7', '386 km/s'). "
        "Explain significance and likely felt effects in calm, clinical-warm language. "
        "Offer practical self-care suggestions. Never catastrophize. No emojis. No questions. "
        "Return ONLY a compact JSON object with EXACTLY these string keys: caption, snapshot, affects, playbook, hashtags. "
        "No markdown, no extra keys, no code fences."
    )

    payload = {
        "metrics": facts,
        "context": _summarize_context(facts),
        "draft": draft,
        "style": {
            "persona": "researcher-coach",
            "audience": "people tracking HRV, sleep, nervous-system sensitivity",
            "opener_palette": HOOKS.get(facts.get("tone") or "neutral", HOOKS["neutral"]),
            "ban_phrases": BAN_PHRASES,
            "bullet_style": "short"
        },
        "constraints": {
            "omit_numbers": True,
            "no_questions": True,
            "no_emojis": True,
            "max_caption_chars": 600
        }
    }

    model = os.getenv("GAIA_OPENAI_MODEL", "gpt-4o-mini")
    try:
        _dbg("rewrite: request -> OpenAI (interpretive JSON)")
        resp = client.chat.completions.create(
            model=model,
            temperature=0.7,
            top_p=0.9,
            presence_penalty=0.3,
            frequency_penalty=0.2,
            max_tokens=700,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}
            ],
        )
        text = (resp.choices[0].message.content or "").strip()
        # Expect raw JSON object only
        try:
            _dbg("rewrite: response received; attempting JSON parse")
            obj = json.loads(text)
        except Exception as e:
            _dbg(f"rewrite: JSON parse failed: {e}")
            return None
        valid = _validate_rewrite(obj)
        _dbg("rewrite: JSON valid") if valid else _dbg("rewrite: JSON invalid by validator")
        if valid:
            # final scrubs
            valid["caption"] = _scrub_banned_phrases(_sanitize_caption(valid["caption"]))
            valid["snapshot"] = _scrub_banned_phrases(valid["snapshot"]) 
            valid["affects"] = _scrub_banned_phrases(valid["affects"]) 
            valid["playbook"] = _scrub_banned_phrases(valid["playbook"]) 
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
        "stormy":   "Charged geomagnetics—short bursts, longer recoveries.",
        "unsettled": "A few bumps in the field—pace beats push today.",
        "calm":     "Steady magnetic backdrop—set a simple plan and move steadily.",
        "neutral":  "Straightforward field—consistency wins today.",
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
        lines.append("Magnetics lean punchy today—expect short surges and brief dips.")
    elif tone == "unsettled":
        lines.append("Some texture in the field—small waves rather than a full storm.")
    elif tone == "calm":
        lines.append("Steady magnetic backdrop—a good canvas for focused work and recovery.")
    else:
        lines.append("Straightforward profile—ordinary variance without big swings.")

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

    # Close with guidance intent
    lines.append("Plan a steady rhythm; if you run sensitive, keep a quick breath reset and short movement breaks.")

    return "Space Weather Snapshot\n" + " ".join(lines)

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

# --- Single-call rewrite cache (avoid double API calls in one run) ---
_REWRITE_CACHE: Optional[Dict[str, str]] = None

def _get_cached_rewrite(client: Optional["OpenAI"], ctx: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """Compute interpretive JSON rewrite once per run and cache it. Returns dict or None."""
    global _REWRITE_CACHE
    _dbg("rewrite-cache: check")
    if _REWRITE_CACHE:
        _dbg("rewrite-cache: hit")
        return _REWRITE_CACHE
    if not client:
        _dbg("rewrite-cache: no client; skipping")
        return None
    rc_local = _rule_copy(ctx)
    _dbg("rewrite-cache: miss; computing via LLM")
    out = _llm_rewrite_from_rules(
        client,
        rc_local["caption"], rc_local["snapshot"], rc_local["affects"], rc_local["playbook"], ctx
    )
    if out:
        _REWRITE_CACHE = out
    _dbg("rewrite-cache: stored" if _REWRITE_CACHE else "rewrite-cache: compute failed; using None")
    return _REWRITE_CACHE


def generate_short_caption(ctx: Dict[str, Any]) -> (str, str):
    client = openai_client()
    if EARTHSCOPE_FORCE_RULES or not client:
        rc = _rule_copy(ctx)
        return rc["caption"], rc["hashtags"]

    # Hybrid: generate rule copy and ask LLM to tighten it (no change of facts)
    rc = _rule_copy(ctx)
    try_rewrite = os.getenv("EARTHSCOPE_HYBRID_REWRITE", "true").strip().lower() in ("1","true","yes","on")
    if try_rewrite:
        # New: interpretive, number-free JSON rewrite (cached single-call reuse)
        out = _get_cached_rewrite(client, ctx)
        if out and out.get("caption"):
            return out["caption"], out.get("hashtags", rc.get("hashtags", "#GaiaEyes #SpaceWeather"))

    kp_now = ctx.get("kp_now")
    kp_max = ctx.get("kp_max_24h")
    wind   = ctx.get("solar_wind_kms")
    flr    = ctx.get("flares_24h")
    cme    = ctx.get("cmes_24h")
    sr     = ctx.get("schumann_value_hz")
    sr_note= ctx.get("schumann_note")

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
        caption = _scrub_banned_phrases(caption)
        return caption, hashtags
    except Exception:
        rc = _rule_copy(ctx)
        return rc["caption"], rc["hashtags"]


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
    }

    # 2) Generate copy
    short_caption, short_tags = generate_short_caption(ctx)
    snapshot, affects, playbook, long_tags = generate_long_sections(ctx)

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
        "tone": tone,
        "bands": bands,
        "sections": sections_struct,
    }
    sources_json = {
        "marts.space_weather_daily": True,
        "marts.schumann_daily": True,
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
