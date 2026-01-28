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
- REEL_TTS_VOICE            : e.g., "alloy" (default), any supported TTS voice
- REEL_DURATION_SEC         : total output duration target (if set, otherwise inferred)
- SUPABASE_URL              : e.g., https://<project>.supabase.co (for audio manifest default)
- SUPABASE_AUDIO_BASE       : Explicit prefix for audio assets (default:
                              f"{SUPABASE_URL}/storage/v1/object/public/space-visuals/social/audio")
- REEL_MOOD                 : optional mood selector (calm|bright|tense|…); picked best-effort
- REEL_OUT_PATH             : target output path; default: "{MEDIA_REPO_PATH}/images/reel.mp4"

Runtime deps:
- ffmpeg (installed via apt in the job)
- Python: requests (pip install requests)

Basic flow:
1) Pick three IG cards: daily_stats.jpg, daily_playbook.jpg, daily_affects.jpg (fallback: any 3 images).
2) Build still clips (6.5s each) and crossfade (0.3s) into one 1080x1920 video.
3) Build VO via OpenAI TTS (optional); pull a music bed WAV from Supabase (tracks.json -> wav).
4) Sidechain-compress bed under VO; export MP4 with AAC audio and H.264 video.
"""

import os
import json
import random
import subprocess
import shlex
from pathlib import Path
from typing import List, Optional
import requests
from requests.adapters import HTTPAdapter, Retry
import datetime as dt

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

# ------------ Inputs & Defaults ------------

MEDIA_REPO_PATH = Path(env_get("MEDIA_REPO_PATH", os.getcwd()))
IMAGES_DIR = MEDIA_REPO_PATH / "images"
DATA_DIR = MEDIA_REPO_PATH / "data"
EARTHSCOPE_JSON = Path(env_get("EARTHSCOPE_OUTPUT_JSON_PATH", str(DATA_DIR / "earthscope_daily.json")))
OPENAI_API_KEY = env_get("OPENAI_API_KEY")
REEL_TTS_VOICE = env_get("REEL_TTS_VOICE", "marin")
REEL_MOOD = env_get("REEL_MOOD", None)
REEL_OUT_PATH = Path(env_get("REEL_OUT_PATH", env_get("REEL_OUT", str(IMAGES_DIR / "reel.mp4"))))

SUPABASE_URL = env_get("SUPABASE_URL")
SUPABASE_AUDIO_BASE = env_get(
    "SUPABASE_AUDIO_BASE",
    f"{SUPABASE_URL}/storage/v1/object/public/space-visuals/social/audio" if SUPABASE_URL else None
)

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

# Visual timing
CLIP_DUR = 6.5   # seconds per still
XFADE = 0.3      # seconds
FPS = 30

# ------------ Image selection ------------

PREFERRED_CARD_NAMES = [
    "daily_stats.jpg",
    "daily_playbook.jpg",
    "daily_affects.jpg",
]

def pick_card_images(images_dir: Path, max_count: int = 3) -> List[Path]:
    # Try preferred names first (if present)
    chosen: List[Path] = []
    for name in PREFERRED_CARD_NAMES:
        p = images_dir / name
        if p.exists():
            chosen.append(p)
    # If fewer than needed, fill with any jpg/jpeg/png not already chosen
    if len(chosen) < max_count:
        pool = []
        for ext in ("*.jpg", "*.jpeg", "*.png"):
            pool.extend(images_dir.glob(ext))
        # Remove duplicates
        pool = [p for p in pool if p not in chosen]
        # Prefer stable ordering by name
        pool.sort()
        for p in pool:
            if len(chosen) >= max_count:
                break
            chosen.append(p)
    return chosen[:max_count]

# ------------ Build video from stills ------------

def build_still_clip(image: Path, out_mp4: Path, duration: float, fps: int = FPS) -> None:
    """
    Create a simple 1080x1920 clip from a still image with minimal letterbox/pad.
    """
    vf = (
        f"scale=1080:-2,"  # scale width to 1080, keep aspect
        f"pad=1080:1920:(ow-iw)/2:(oh-ih)/2,"
        f"format=yuv420p"
    )
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-t", f"{duration:.3f}",
        "-i", str(image),
        "-vsync", "cfr",
        "-r", str(fps),
        "-vf", vf,
        "-an",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(out_mp4)
    ]
    run(cmd)

def xfade_concat(clips: List[Path], out_mp4: Path, clip_dur: float, xfade: float, fps: int = FPS) -> None:
    """
    Crossfade 3 clips with xfade. Assumes exactly 3 inputs for now.
    """
    if len(clips) < 2:
        # Single clip case: just copy it
        run(["cp", str(clips[0]), str(out_mp4)])
        return
    if len(clips) == 2:
        # Two-clip chain
        off1 = clip_dur - xfade
        fc = (
            f"[0:v][1:v]xfade=transition=fade:duration={xfade}:offset={off1}[vout]"
        )
        cmd = [
            "ffmpeg", "-y",
            "-i", str(clips[0]),
            "-i", str(clips[1]),
            "-filter_complex", fc,
            "-map", "[vout]",
            "-an",
            "-r", str(fps),
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(out_mp4)
        ]
        run(cmd)
        return

    # Three-clip chain
    off1 = clip_dur - xfade                             # ~6.2
    length_after_1 = 2 * clip_dur - xfade               # ~12.7
    off2 = length_after_1 - xfade                       # ~12.4

    fc = (
        f"[0:v][1:v]xfade=transition=fade:duration={xfade}:offset={off1}[v01];"
        f"[v01][2:v]xfade=transition=fade:duration={xfade}:offset={off2}[vout]"
    )
    cmd = [
        "ffmpeg", "-y",
        "-i", str(clips[0]),
        "-i", str(clips[1]),
        "-i", str(clips[2]),
        "-filter_complex", fc,
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
            log(f"TTS failed {resp.status_code}: {resp.text[:200]}")
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
    - If bed only: set bed to -12 dB, fade out 200 ms at tail.
    - Else: copy video with no audio.
    """
    # Always re-encode video to be safe for social (yuv420p, H.264 high)
    common_video = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.1", "-r", str(FPS), "-movflags", "+faststart"]
    duration_str = f"{total_duration:.3f}"

    if vo_wav and bed_wav and vo_wav.exists() and bed_wav.exists():
        # Loop/trim bed to exactly duration; then sidechain duck it under VO, resample/mix to stereo/44.1k, and limit peaks
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_in),
            "-i", str(vo_wav),
            "-stream_loop", "-1", "-i", str(bed_wav),
            "-filter_complex",
            (
                f"[1:a]aformat=sample_fmts=fltp:channel_layouts=stereo,aresample=44100,asplit=2[vo_sc][vo_mix];"
                f"[2:a]atrim=0:{duration_str},asetpts=N/SR/TB,volume=-12dB,"
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
            "-filter_complex", "[1:a]aformat=sample_fmts=fltp:channel_layouts=stereo,aresample=44100,alimiter=limit=0.98[aout]",
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
            "-filter_complex", f"[1:a]atrim=0:{duration_str},asetpts=N/SR/TB,volume=-12dB,afade=t=out:st={max(0.0, total_duration-0.2):.3f}:d=0.2[aout]",
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

    # 1) Pick images
    cards = pick_card_images(IMAGES_DIR, 3)
    if not cards:
        raise SystemExit("No images found to build reel. Expected JPG/PNG cards in MEDIA_REPO_PATH/images")
    log(f"Using cards: {', '.join(p.name for p in cards)}")

    # 2) Build still clips
    tmp_dir = Path("tmp_reel")
    tmp_dir.mkdir(exist_ok=True, parents=True)
    clips = []
    for i, img in enumerate(cards):
        outc = tmp_dir / f"clip_{i}.mp4"
        build_still_clip(img, outc, CLIP_DUR, FPS)
        clips.append(outc)

    # 3) Crossfade chain
    vid_no_audio = tmp_dir / "video_no_audio.mp4"
    xfade_concat(clips, vid_no_audio, CLIP_DUR, XFADE, FPS)

    total_duration = max(0.0, CLIP_DUR * len(clips) - XFADE * (len(clips) - 1))
    log(f"Total visual duration: {total_duration:.3f}s")

    # 4) VO (best-effort) and bed
    platform = env_get("REEL_PLATFORM", "default")
    target_day = env_get("TARGET_DAY")
    caption_text = resolve_caption(platform=platform, target_day=target_day)
    vo_text = caption_text or guess_vo_text(EARTHSCOPE_JSON)
    vo_wav = tmp_dir / "vo.wav"
    vo_ok = False
    if OPENAI_API_KEY:
        vo_ok = tts_to_wav(vo_text, vo_wav, api_key=OPENAI_API_KEY, voice=REEL_TTS_VOICE)
    else:
        log("OPENAI_API_KEY not set; skipping VO.")

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

    # --- If the VO is longer than the visual chain, rebuild clips proportionally ---
    # Optional padding after VO to avoid abrupt cut
    vo_tail_pad = float(env_get("REEL_VO_TAIL_PAD_SEC", "1.2") or "1.2")

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
        n = len(clips)
        # Solve for per-clip duration so that: n * d - (n-1) * XFADE = required_total
        new_clip_dur = (required_total + XFADE * (n - 1)) / n
        log(f"VO ~{(vo_secs or 0.0):.2f}s, extending per-clip duration to {new_clip_dur:.2f}s for total ~{required_total:.2f}s")

        # Rebuild clips with the new per-clip duration
        clips = []
        for i, img in enumerate(cards):
            outc = tmp_dir / f"clip_{i}.mp4"
            build_still_clip(img, outc, new_clip_dur, FPS)
            clips.append(outc)

        # Rebuild crossfade chain and recalc total
        xfade_concat(clips, vid_no_audio, new_clip_dur, XFADE, FPS)
        total_duration = max(0.0, new_clip_dur * n - XFADE * (n - 1))
        log(f"Adjusted visual duration: {total_duration:.3f}s")

    # 5) Mix and mux
    mix_audio_with_video(vid_no_audio, REEL_OUT_PATH, vo_wav if vo_ok else None, bed_wav if bed_ok else None, total_duration)

    log(f"Reel written to: {REEL_OUT_PATH}")
    return

if __name__ == "__main__":
    main()
