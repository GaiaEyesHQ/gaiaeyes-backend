#!/usr/bin/env python3
"""
reel_builder.py — Build a vertical (1080x1920) Reel from daily Gaia Eyes cards,
speak a short VO via OpenAI TTS, add a loopable music bed from Supabase, and
write the final H.264/AAC MP4.

Intended to run in GitHub Actions in the "render" job after cards are generated.

ENV it uses (all optional, sane defaults applied when possible):
- MEDIA_REPO_PATH           : path to the gaiaeyes-media checkout (cards and JSON live here)
- EARTHSCOPE_OUTPUT_JSON_PATH: path to earthscope_daily.json (to pull short VO text)
- OPENAI_API_KEY            : your OpenAI API key (for TTS). If missing, VO is skipped.
- REEL_TTS_VOICE            : e.g., "marin" (default), any supported TTS voice
- REEL_TTS_MODEL            : OpenAI TTS model, default gpt-4o-mini-tts
- REEL_VO_LEAD_PAD_SEC      : optional leading silence before VO (default 0.15)
- REEL_MUSIC_VOLUME_DB      : music bed gain before ducking (default -9dB)
- REEL_DURATION_SEC         : total output duration target (if set, otherwise inferred)
- SUPABASE_URL              : e.g., https://<project>.supabase.co (for audio manifest default)
- SUPABASE_AUDIO_BASE       : Explicit prefix for audio assets (default:
                              f"{SUPABASE_URL}/storage/v1/object/public/space-visuals/social/audio")
- REEL_MOOD                 : optional mood selector (calm|bright|tense|…); picked best-effort
- REEL_OUT_PATH             : target output path; default: "{MEDIA_REPO_PATH}/images/reel.mp4"

Runtime deps:
- ffmpeg (installed via apt in the job)
- Python: requests, Pillow (pip install requests pillow)

Basic flow:
1) Build a large hook-only opener, then use the care-notes and stats cards.
2) Add immediate subtle motion and crossfade the short clips into one 1080x1920 video.
3) Build VO via OpenAI TTS (optional); pull a music bed WAV from Supabase (tracks.json -> wav).
4) Sidechain-compress bed under VO; export MP4 with AAC audio and H.264 video.
"""

import os
import json
import random
import re
import subprocess
import shlex
from pathlib import Path
from typing import List, Optional, Sequence
import requests
from requests.adapters import HTTPAdapter, Retry
import datetime as dt
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

# ------------ Utilities ------------

def log(msg: str):
    print(f"[reel] {msg}", flush=True)

def run(cmd: List[str]) -> None:
    log("RUN " + " ".join(shlex.quote(c) for c in cmd))
    subprocess.run(cmd, check=True)

def which_ffmpeg() -> str:
    ff = subprocess.run(["which", "ffmpeg"], capture_output=True, text=True)
    path = ff.stdout.strip()
    if not path:
        raise RuntimeError("ffmpeg not found in PATH. Install it in the job (apt-get install ffmpeg).")
    return path


# ------------ Media duration probe ------------
def probe_duration_seconds(media_path: Path) -> Optional[float]:
    """
    Use ffprobe to get duration in seconds (float). Returns None on failure.
    """
    try:
        res = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(media_path),
            ],
            capture_output=True, text=True, check=False
        )
        if res.returncode == 0:
            s = res.stdout.strip()
            if s:
                return float(s)
    except Exception as e:
        log(f"ffprobe duration failed for {media_path}: {e}")
    return None

def env_get(name: str, default: Optional[str] = None) -> Optional[str]:
    val = os.environ.get(name)
    if val is None or val == "":
        return default
    return val

# ------------ Helper: Strip trailing metric/stat readouts from captions ------------
def strip_metric_tail(text: str) -> str:
    """
    Remove metric/stat readouts and hashtag-only lines from a caption for VO use,
    then collapse remaining prose to a single paragraph.
    """
    if not text:
        return text
    lines = [ln.strip() for ln in str(text).splitlines() if ln.strip()]

    def is_metric_footer(ln: str) -> bool:
        low = ln.lower()
        if low.startswith("—"):
            return True
        # common footer pattern with multiple tokens
        if ("kp" in low and "bz" in low) or ("schumann" in low and "hz" in low):
            return True
        if any(tok in low for tok in ("pfu", "mev", "f10.7", "goes")):
            return True
        return False

    def is_hashtag_only(ln: str) -> bool:
        parts = ln.split()
        if not parts:
            return False
        return all(p.startswith("#") for p in parts)

    # Drop metric footer lines anywhere
    kept = [ln for ln in lines if not is_metric_footer(ln)]

    # Drop trailing hashtag-only lines (common in captions)
    while kept and is_hashtag_only(kept[-1]):
        kept.pop()

    # Collapse to one paragraph for VO
    out = " ".join(kept).strip()
    out = re.sub(r"\s*—\s*kp.*$", "", out, flags=re.I).strip()
    return out

# ------------ Inputs & Defaults ------------

MEDIA_REPO_PATH = Path(env_get("MEDIA_REPO_PATH", os.getcwd()))
IMAGES_DIR = MEDIA_REPO_PATH / "images"
DATA_DIR = MEDIA_REPO_PATH / "data"
EARTHSCOPE_JSON = Path(env_get("EARTHSCOPE_OUTPUT_JSON_PATH", str(DATA_DIR / "earthscope_daily.json")))
OPENAI_API_KEY = env_get("OPENAI_API_KEY")
REEL_TTS_VOICE = env_get("REEL_TTS_VOICE", "marin")
REEL_TTS_MODEL = env_get("REEL_TTS_MODEL", "gpt-4o-mini-tts")
REEL_TTS_FALLBACK_MODEL = env_get("REEL_TTS_FALLBACK_MODEL", "gpt-4o-mini-tts")
REEL_VO_LEAD_PAD_SEC = env_get("REEL_VO_LEAD_PAD_SEC", "0.15")
REEL_MUSIC_VOLUME_DB = env_get("REEL_MUSIC_VOLUME_DB", "-9")
REEL_REQUIRE_VO = env_get("REEL_REQUIRE_VO", "0") == "1"
REEL_MOOD = env_get("REEL_MOOD", None)
REEL_OUT_PATH = Path(env_get("REEL_OUT_PATH", env_get("REEL_OUT", str(IMAGES_DIR / "reel.mp4"))))

SUPABASE_URL = env_get("SUPABASE_URL")
SUPABASE_AUDIO_BASE = env_get(
    "SUPABASE_AUDIO_BASE",
    f"{SUPABASE_URL}/storage/v1/object/public/space-visuals/social/audio" if SUPABASE_URL else None
)

# Toggle: Strip trailing metric/stat lines from VO text
STRIP_METRICS = env_get("REEL_VO_STRIP_METRICS", "1") != "0"

# ------------ Caption from Supabase (content.daily_posts) ------------
# Optional envs; when present we'll try to fetch a caption VO from Supabase
SUPABASE_REST_URL = os.getenv("SUPABASE_REST_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = (os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_ANON_KEY") or "").strip()

def _sb_session():
    s = requests.Session()
    try:
        retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
        s.mount("https://", HTTPAdapter(max_retries=retries))
    except Exception:
        pass
    return s

def _sb_headers(schema: str = "content"):
    h = {
        "Accept": "application/json",
        "Accept-Profile": schema,
    }
    if SUPABASE_SERVICE_KEY:
        h["apikey"] = SUPABASE_SERVICE_KEY
        h["Authorization"] = f"Bearer {SUPABASE_SERVICE_KEY}"
    return h

def _sb_select(path: str, params: dict, schema: str = "content"):
    if not SUPABASE_REST_URL:
        return None
    url = f"{SUPABASE_REST_URL}/{path}"
    r = _sb_session().get(url, headers=_sb_headers(schema), params=params, timeout=30)
    if r.status_code != 200:
        log(f"[caption] Supabase {path} failed {r.status_code}: {r.text[:160]}")
        return None
    try:
        return r.json()
    except Exception as e:
        log(f"[caption] JSON parse error: {e}")
        return None

def _latest_day_from_content(platform: str = "default") -> str:
    # Try direct query: most recent day for platform, then fall back to 'default'
    params = {"platform": f"eq.{platform}", "select": "day", "order": "day.desc", "limit": "1"}
    res = _sb_select("daily_posts", params, schema="content")
    if isinstance(res, list) and res and "day" in res[0]:
        return res[0]["day"]
    if platform != "default":
        params["platform"] = "eq.default"
        res = _sb_select("daily_posts", params, schema="content")
        if isinstance(res, list) and res and "day" in res[0]:
            return res[0]["day"]
    # fallback to UTC today
    return dt.datetime.utcnow().date().isoformat()

def fetch_post_for_day(day: str, platform: str = "default") -> Optional[dict]:
    params = {
        "day": f"eq.{day}",
        "platform": f"eq.{platform}",
        "select": "*"
    }
    rows = _sb_select("daily_posts", params, schema="content")
    if isinstance(rows, list) and rows:
        return rows[0]
    # fallback to default platform for the same day
    if platform != "default":
        params["platform"] = "eq.default"
        rows = _sb_select("daily_posts", params, schema="content")
        if isinstance(rows, list) and rows:
            return rows[0]
    return None


def _metrics_sections(row: dict) -> dict:
    metrics = row.get("metrics_json")
    if isinstance(metrics, str):
        try:
            metrics = json.loads(metrics)
        except Exception:
            metrics = {}
    if not isinstance(metrics, dict):
        return {}
    sections = metrics.get("sections")
    return sections if isinstance(sections, dict) else {}


def _clean_vo_sentence(text: object) -> str:
    cleaned = " ".join(str(text or "").replace("•", " ").split())
    return cleaned.strip(" -")


def _first_action(text: object) -> str:
    for raw in str(text or "").splitlines():
        line = _clean_vo_sentence(raw)
        if line:
            return line
    return ""


def _first_sentences(text: object, *, max_sentences: int = 2, max_chars: int = 360) -> str:
    cleaned = _clean_vo_sentence(text)
    if not cleaned:
        return ""
    parts = [item.strip() for item in re.split(r"(?<=[.!?])\s+", cleaned) if item.strip()]
    out = " ".join(parts[:max_sentences]).strip() if parts else cleaned
    if len(out) <= max_chars:
        return out
    return out[:max_chars].rsplit(" ", 1)[0].rstrip(" ,;:-") + "."


def _explicit_vo_text(row: dict, sections: dict) -> str:
    candidates = [
        row.get("voiceover"),
        row.get("vo_text"),
        row.get("short_caption"),
        row.get("reel_caption"),
        sections.get("voiceover"),
        sections.get("vo_text"),
        sections.get("reel_voiceover"),
    ]
    cards = row.get("cards")
    if isinstance(cards, dict):
        for key in ("voiceover", "reel", "caption"):
            node = cards.get(key)
            if isinstance(node, dict):
                candidates.extend([node.get("voiceover"), node.get("vo_text"), node.get("short"), node.get("text")])
    for value in candidates:
        cleaned = _clean_vo_sentence(value)
        if cleaned:
            return cleaned
    return ""


def _audio_db(value: object, default: float = -9.0) -> str:
    raw = str(value or "").strip().lower()
    try:
        amount = float(raw[:-2] if raw.endswith("db") else raw)
    except Exception:
        amount = default
    return f"{amount:g}dB"


def _vo_lead_filter() -> str:
    try:
        lead = max(0.0, float(str(REEL_VO_LEAD_PAD_SEC or "").strip()))
    except Exception:
        lead = 0.15
    delay_ms = int(round(lead * 1000))
    if delay_ms <= 0:
        return ""
    return f"adelay={delay_ms}|{delay_ms},afade=t=in:st=0:d=0.08,"


def build_vo_text_from_post(row: dict) -> str:
    sections = _metrics_sections(row)
    explicit = _explicit_vo_text(row, sections)
    if explicit:
        return strip_metric_tail(explicit)

    caption = _first_sentences(row.get("caption") or sections.get("caption") or row.get("overview") or row.get("lead"))
    action = _first_action(sections.get("playbook"))

    parts: List[str] = []
    if caption:
        parts.append(caption)
    if action:
        parts.append(f"Try this today: {action}.")

    text = " ".join(parts).strip()
    if text:
        return strip_metric_tail(text)
    affects = _first_sentences(sections.get("affects"), max_sentences=1, max_chars=220)
    return strip_metric_tail(affects) if affects else ""


def resolve_caption(platform: str = "default", target_day: Optional[str] = None) -> Optional[str]:
    if not SUPABASE_REST_URL:
        return None
    day = target_day or _latest_day_from_content(platform)
    row = fetch_post_for_day(day, platform)
    if not row:
        return None
    # Prefer explicit caption, then overview/lead/short, then cards.caption.text
    for key in ("caption", "overview", "lead", "short"):
        val = row.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    cards = row.get("cards")
    if isinstance(cards, dict):
        cap = cards.get("caption") or {}
        if isinstance(cap, dict):
            txt = cap.get("text") or cap.get("short")
            if isinstance(txt, str) and txt.strip():
                return txt.strip()
    return None


def resolve_vo_text(platform: str = "default", target_day: Optional[str] = None) -> Optional[str]:
    if not SUPABASE_REST_URL:
        return None
    day = target_day or _latest_day_from_content(platform)
    row = fetch_post_for_day(day, platform)
    if not row:
        return None
    vo_text = build_vo_text_from_post(row)
    if vo_text:
        return vo_text
    return resolve_caption(platform=platform, target_day=day)

# Visual timing
HOOK_CLIP_DUR = 2.2
DETAIL_CLIP_DUR = 5.4
XFADE = 0.25
FPS = 30


def hook_text_from_post(row: Optional[dict]) -> str:
    if not isinstance(row, dict):
        return "Today, in your body"
    title = _clean_vo_sentence(row.get("title"))
    if title:
        return title
    sections = _metrics_sections(row)
    caption = row.get("caption") or sections.get("caption") or ""
    first = _first_sentences(caption, max_sentences=1, max_chars=90)
    return first or "Today, in your body"


def _fit_hook_font(draw: ImageDraw.ImageDraw, text: str, font_path: Path, max_width: int) -> ImageFont.FreeTypeFont:
    for size in range(132, 71, -4):
        font = ImageFont.truetype(str(font_path), size=size)
        if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
            return font
    return ImageFont.truetype(str(font_path), size=72)


def build_hook_card(source: Path, out_path: Path, hook_text: str) -> Path:
    with Image.open(source) as raw:
        background = raw.convert("RGB")
    background = background.resize((1080, 1920), Image.Resampling.LANCZOS)
    background = background.filter(ImageFilter.GaussianBlur(radius=14))
    background = ImageEnhance.Brightness(background).enhance(0.46)

    canvas = background.convert("RGBA")
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 70))
    canvas = Image.alpha_composite(canvas, overlay)
    draw = ImageDraw.Draw(canvas)

    font_path = Path(__file__).resolve().parent / "fonts" / "BebasNeue.ttf"
    label_font = ImageFont.truetype(str(font_path), size=42)
    measure_font = ImageFont.truetype(str(font_path), size=112)
    words = str(hook_text or "Today, in your body").strip().upper().split()
    lines: List[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and draw.textbbox((0, 0), candidate, font=measure_font)[2] > 880:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    if len(lines) > 3:
        lines = [" ".join(lines[:-1]), lines[-1]]

    longest = max(lines, key=len) if lines else "TODAY, IN YOUR BODY"
    hook_font = _fit_hook_font(draw, longest, font_path, 880)
    line_height = hook_font.size + 18
    block_height = line_height * len(lines)
    top = max(520, (1920 - block_height) // 2 - 70)

    draw.text((100, top - 92), "EARTHSCOPE  •  TODAY", font=label_font, fill=(84, 224, 225, 255))
    for index, line in enumerate(lines):
        draw.text((100, top + index * line_height), line, font=hook_font, fill=(255, 255, 255, 255))
    draw.text((100, 1690), "GAIA EYES", font=label_font, fill=(255, 255, 255, 225))
    draw.text((100, 1744), "Decode the unseen.", font=label_font, fill=(210, 220, 224, 225))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(out_path, "JPEG", quality=92)
    return out_path

# ------------ Image selection ------------

PREFERRED_CARD_NAMES = [
    "daily_affects.jpg",
    "daily_playbook.jpg",
    "daily_stats.jpg",
]

def pick_card_images(images_dir: Path, max_count: int = 3) -> List[Path]:
    # Try preferred names first (if present)
    chosen: List[Path] = []
    for name in PREFERRED_CARD_NAMES:
        p = images_dir / name
        if p.exists():
            chosen.append(p)
    # If fewer than needed, fill with any jpg/jpeg/png not already chosen.
    if len(chosen) < max_count:
        pool = [
            p for p in images_dir.iterdir()
            if p.is_file()
            and p.suffix.lower() in {".jpg", ".jpeg", ".png"}
            and p not in chosen
        ]
        # Prefer stable ordering by name.
        pool.sort()
        for p in pool:
            if len(chosen) >= max_count:
                break
            chosen.append(p)
    return chosen[:max_count]

# ------------ Build video from stills ------------

def build_still_clip(
    image: Path,
    out_mp4: Path,
    duration: float,
    fps: int = FPS,
    *,
    motion: bool = False,
) -> None:
    """
    Create a simple 1080x1920 clip from a still image with minimal letterbox/pad.
    """
    if motion:
        vf = (
            "scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,"
            f"zoompan=z='min(zoom+0.0007,1.055)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d=1:s=1080x1920:fps={fps},format=yuv420p"
        )
    else:
        vf = (
            "scale=1080:1920:force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2,"
            "format=yuv420p"
        )
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(fps),
        "-loop", "1",
        "-i", str(image),
        "-t", f"{duration:.3f}",
        "-vf", vf,
        "-an",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(out_mp4)
    ]
    run(cmd)

def xfade_concat(
    clips: List[Path],
    out_mp4: Path,
    clip_durations: Sequence[float],
    xfade: float,
    fps: int = FPS,
) -> None:
    """Crossfade clips with per-clip durations."""
    if len(clips) != len(clip_durations):
        raise ValueError("clips and clip_durations must have the same length")
    if len(clips) < 2:
        # Single clip case: just copy it
        run(["cp", str(clips[0]), str(out_mp4)])
        return
    filters: List[str] = []
    cumulative = float(clip_durations[0])
    previous = "0:v"
    for index in range(1, len(clips)):
        offset = cumulative - xfade
        output = "vout" if index == len(clips) - 1 else f"v{index:02d}"
        filters.append(
            f"[{previous}][{index}:v]xfade=transition=fade:duration={xfade}:offset={offset:.3f}[{output}]"
        )
        previous = output
        cumulative += float(clip_durations[index]) - xfade

    cmd = [
        "ffmpeg", "-y",
        *[part for clip in clips for part in ("-i", str(clip))],
        "-filter_complex", ";".join(filters),
        "-map", "[vout]",
        "-an",
        "-r", str(fps),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(out_mp4)
    ]
    run(cmd)

# ------------ TTS (OpenAI) ------------

def guess_vo_text(json_path: Path) -> str:
    """
    Extract a short VO blurb from earthscope_daily.json with best-effort fallback.
    """
    if json_path.exists():
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            # Heuristics: try common spots
            for key in ("overview", "caption", "short", "summary", "lead"):
                if key in data and isinstance(data[key], str) and data[key].strip():
                    return data[key].strip()
            # Nested cards/caption
            cards = data.get("cards") or {}
            if isinstance(cards, dict):
                for k in ("caption", "overview", "summary"):
                    node = cards.get(k)
                    if isinstance(node, dict):
                        for tkey in ("text", "short", "blurb"):
                            if tkey in node and isinstance(node[tkey], str) and node[tkey].strip():
                                return node[tkey].strip()
        except Exception as e:
            log(f"Could not parse JSON for VO text: {e}")

    # Fallback generic
    return "Gaia Eyes daily highlights. Check the latest cosmic weather and tips to feel your best today."

def tts_to_wav(text: str, out_wav: Path, api_key: str, voice: str = "marin", model: str = "gpt-4o-mini-tts") -> bool:
    """
    Request TTS audio from OpenAI and write WAV. Returns True on success.
    """
    url = "https://api.openai.com/v1/audio/speech"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "voice": voice,
        "input": text,
        "format": "wav"
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        if resp.status_code == 200:
            out_wav.write_bytes(resp.content)
            log(f"VO wav saved: {out_wav}")
            return True
        else:
            log(f"TTS failed {resp.status_code}: {resp.text[:400]}")
            return False
    except Exception as e:
        log(f"TTS exception: {e}")
        return False

# ------------ Music bed from Supabase ------------

def pick_track(tracks: list, mood: Optional[str]) -> Optional[dict]:
    if not tracks:
        return None
    if mood:
        filtered = [t for t in tracks if t.get("mood") == mood]
        if filtered:
            return random.choice(filtered)
    return random.choice(tracks)

def fetch_audio_manifest(base: Optional[str]) -> Optional[list]:
    if not base:
        return None
    url = base.rstrip("/") + "/tracks.json"
    try:
        r = requests.get(url, timeout=30)
        if r.status_code == 200:
            return r.json()
        log(f"tracks.json fetch failed {r.status_code}: {r.text[:200]}")
    except Exception as e:
        log(f"tracks.json exception: {e}")
    return None

def download_audio(base: Optional[str], rel_url: str, out_wav: Path) -> bool:
    if not base:
        return False
    url = base.rstrip("/") + "/" + rel_url.lstrip("/")
    try:
        r = requests.get(url, timeout=60)
        if r.status_code == 200:
            out_wav.write_bytes(r.content)
            log(f"Music bed saved: {out_wav.name}")
            return True
        log(f"Audio fetch failed {r.status_code}: {r.text[:120]}")
    except Exception as e:
        log(f"Audio fetch exception: {e}")
    return False

# ------------ Audio mix with ffmpeg ------------

def mix_audio_with_video(video_in: Path, video_out: Path, vo_wav: Optional[Path], bed_wav: Optional[Path], total_duration: float) -> None:
    """
    Compose final audio mix and mux with video.
    - If VO + bed: sidechain-compress bed under VO, limiter on master.
    - If VO only: limiter.
    - If bed only: set bed to configured gain, fade out 200 ms at tail.
    - Else: copy video with no audio.
    """
    # Always re-encode video to be safe for social (yuv420p, H.264 high)
    common_video = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.1", "-r", str(FPS), "-movflags", "+faststart"]
    duration_str = f"{total_duration:.3f}"
    music_volume = _audio_db(REEL_MUSIC_VOLUME_DB, -9.0)
    vo_prefix = _vo_lead_filter()

    if vo_wav and bed_wav and vo_wav.exists() and bed_wav.exists():
        # Loop/trim bed to exactly duration; then sidechain duck it under VO, resample/mix to stereo/44.1k, and limit peaks
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_in),
            "-i", str(vo_wav),
            "-stream_loop", "-1", "-i", str(bed_wav),
            "-filter_complex",
            (
                f"[1:a]{vo_prefix}aformat=sample_fmts=fltp:channel_layouts=stereo,aresample=44100,asplit=2[vo_sc][vo_mix];"
                f"[2:a]atrim=0:{duration_str},asetpts=N/SR/TB,volume={music_volume},"
                f"aformat=sample_fmts=fltp:channel_layouts=stereo,aresample=44100[bed];"
                f"[bed][vo_sc]sidechaincompress=threshold=0.05:ratio=8:attack=5:release=220:makeup=3[duck];"
                f"[duck][vo_mix]amix=inputs=2:duration=longest:dropout_transition=250,alimiter=limit=0.98[aout]"
            ),
            "-map", "0:v",
            "-map", "[aout]",
            *common_video,
            "-c:a", "aac", "-b:a", "192k",
            "-t", duration_str,
            str(video_out)
        ]
        run(cmd)
        return

    if vo_wav and vo_wav.exists():
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_in),
            "-i", str(vo_wav),
            "-filter_complex", f"[1:a]{vo_prefix}aformat=sample_fmts=fltp:channel_layouts=stereo,aresample=44100,alimiter=limit=0.98[aout]",
            "-map", "0:v",
            "-map", "[aout]",
            *common_video,
            "-c:a", "aac", "-b:a", "192k",
            "-t", duration_str,
            str(video_out)
        ]
        run(cmd)
        return

    if bed_wav and bed_wav.exists():
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_in),
            "-stream_loop", "-1", "-i", str(bed_wav),
            "-filter_complex", f"[1:a]atrim=0:{duration_str},asetpts=N/SR/TB,volume={music_volume},afade=t=out:st={max(0.0, total_duration-0.2):.3f}:d=0.2[aout]",
            "-map", "0:v",
            "-map", "[aout]",
            *common_video,
            "-c:a", "aac", "-b:a", "192k",
            "-t", duration_str,
            str(video_out)
        ]
        run(cmd)
        return

    # No audio case
    run([
        "ffmpeg", "-y",
        "-i", str(video_in),
        "-an",
        *common_video,
        str(video_out)
    ])

# ------------ Main orchestration ------------

def main():
    which_ffmpeg()
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    REEL_OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    platform = env_get("REEL_PLATFORM", "default")
    target_day = env_get("TARGET_DAY")
    resolved_day = target_day or _latest_day_from_content(platform)
    post_row = fetch_post_for_day(resolved_day, platform)

    # 1) Build a hook-only opener, then keep the detailed cards for later beats.
    detail_cards = pick_card_images(IMAGES_DIR, 3)
    if not detail_cards:
        raise SystemExit("No images found to build reel. Expected JPG/PNG cards in MEDIA_REPO_PATH/images")
    tmp_dir = Path("tmp_reel")
    tmp_dir.mkdir(exist_ok=True, parents=True)
    hook_card = build_hook_card(
        detail_cards[0],
        tmp_dir / "hook.jpg",
        hook_text_from_post(post_row),
    )
    later_cards = [card for card in detail_cards if card.name != "daily_affects.jpg"]
    if not later_cards:
        later_cards = detail_cards
    cards = [hook_card, *later_cards[:2]]
    clip_durations = [HOOK_CLIP_DUR, *([DETAIL_CLIP_DUR] * (len(cards) - 1))]
    log(f"Using cards: {', '.join(p.name for p in cards)}")

    # 2) Build short clips. Motion starts on frame one.
    clips = []
    for i, (img, duration) in enumerate(zip(cards, clip_durations)):
        outc = tmp_dir / f"clip_{i}.mp4"
        build_still_clip(img, outc, duration, FPS, motion=(i == 0))
        clips.append(outc)

    # 3) Crossfade chain
    vid_no_audio = tmp_dir / "video_no_audio.mp4"
    xfade_concat(clips, vid_no_audio, clip_durations, XFADE, FPS)

    total_duration = max(0.0, sum(clip_durations) - XFADE * (len(clips) - 1))
    log(f"Total visual duration: {total_duration:.3f}s")

    # 4) VO (best-effort) and bed
    caption_text = resolve_caption(platform=platform, target_day=target_day)
    post_caption = " ".join((caption_text or "").split())
    vo_text_raw = resolve_vo_text(platform=platform, target_day=target_day) or caption_text or ""
    if not vo_text_raw.strip():
        vo_text_raw = guess_vo_text(EARTHSCOPE_JSON)
    vo_text = strip_metric_tail(vo_text_raw) if STRIP_METRICS else vo_text_raw
    if len((vo_text or "").strip()) < 40:
        log("VO text too short after sanitize; using fallback blurb.")
        vo_text = "Gaia Eyes daily highlights. Check today’s EarthScope and pacing tips."
    if vo_text != vo_text_raw:
        log("Sanitized VO: removed trailing metric lines.")
    log(f"VO: api_key_present={bool(OPENAI_API_KEY)} voice={REEL_TTS_VOICE} model={REEL_TTS_MODEL}")
    log(f"VO text length={len((vo_text or '').strip())} sanitized={STRIP_METRICS}")
    vo_wav = tmp_dir / "vo.wav"
    vo_ok = False
    if OPENAI_API_KEY:
        log(f"VO using caption chars={len((vo_text or '').strip())}")
        vo_ok = tts_to_wav(
            vo_text,
            vo_wav,
            api_key=OPENAI_API_KEY,
            voice=REEL_TTS_VOICE,
            model=REEL_TTS_MODEL,
        )
        if (not vo_ok) and REEL_TTS_FALLBACK_MODEL != REEL_TTS_MODEL:
            log(f"Retrying TTS with fallback model={REEL_TTS_FALLBACK_MODEL}")
            vo_ok = tts_to_wav(
                vo_text,
                vo_wav,
                api_key=OPENAI_API_KEY,
                voice=REEL_TTS_VOICE,
                model=REEL_TTS_FALLBACK_MODEL,
            )
    else:
        log("OPENAI_API_KEY not set; skipping VO.")
    if REEL_REQUIRE_VO and not vo_ok:
        raise SystemExit("VO required but TTS failed")

    bed_wav = tmp_dir / "bed.wav"
    bed_ok = False
    manifest = fetch_audio_manifest(SUPABASE_AUDIO_BASE)
    if manifest:
        tr = pick_track(manifest, REEL_MOOD)
        if tr:
            rel = tr.get("url") or tr.get("file") or ""
            if rel:
                bed_ok = download_audio(SUPABASE_AUDIO_BASE, rel, bed_wav)
            else:
                log("Selected track has no 'url'/'file' key; skipping bed.")
        else:
            log("No track selected; skipping bed.")
    else:
        log("No tracks.json manifest available; skipping bed.")

    # --- If the VO is longer than the visual chain, extend detail beats but keep the hook fast. ---
    # Optional padding after VO to avoid abrupt cut
    vo_tail_pad = float(env_get("REEL_VO_TAIL_PAD_SEC", "0.8") or "0.8")

    # Optional hard target duration override (seconds). If provided and larger than current, prefer it.
    target_total_env = env_get("REEL_DURATION_SEC")
    target_total = None
    try:
        if target_total_env:
            target_total = float(target_total_env)
    except Exception:
        target_total = None

    vo_secs = None
    if vo_ok and vo_wav.exists():
        vo_secs = probe_duration_seconds(vo_wav)

    # Decide the required total duration
    required_total = total_duration
    if vo_secs:
        required_total = max(required_total, vo_secs + vo_tail_pad)
    if target_total:
        required_total = max(required_total, target_total)

    if required_total > total_duration + 0.05:
        detail_count = max(1, len(clip_durations) - 1)
        extra_per_detail = (required_total - total_duration) / detail_count
        clip_durations = [
            duration if index == 0 else duration + extra_per_detail
            for index, duration in enumerate(clip_durations)
        ]
        log(
            f"VO ~{(vo_secs or 0.0):.2f}s, keeping hook at {clip_durations[0]:.2f}s "
            f"and extending detail beats for total ~{required_total:.2f}s"
        )

        # Rebuild clips with the new per-clip duration
        clips = []
        for i, (img, duration) in enumerate(zip(cards, clip_durations)):
            outc = tmp_dir / f"clip_{i}.mp4"
            build_still_clip(img, outc, duration, FPS, motion=(i == 0))
            clips.append(outc)

        # Rebuild crossfade chain and recalc total
        xfade_concat(clips, vid_no_audio, clip_durations, XFADE, FPS)
        total_duration = max(0.0, sum(clip_durations) - XFADE * (len(clips) - 1))
        log(f"Adjusted visual duration: {total_duration:.3f}s")

    # 5) Mix and mux
    mix_audio_with_video(vid_no_audio, REEL_OUT_PATH, vo_wav if vo_ok else None, bed_wav if bed_ok else None, total_duration)

    log(f"Reel written to: {REEL_OUT_PATH}")
    return

if __name__ == "__main__":
    main()
