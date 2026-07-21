from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps, ImageStat

from bots.social_alerts.preview_renderer import resolve_background_image


CANVAS = (1080, 1920)
SAFE_TEXT_BOX = (88, 520, 910, 1430)
SLIDE_DURATION_SECONDS = (2.8, 3.2, 3.2, 3.2, 3.6)
XFADE_SECONDS = 0.25
FPS = 30

SLIDE_SPECS = (
    ("hook", "U.S. HEALTH SNAPSHOT", "01-hook.png"),
    ("where", "WHERE IT'S STRONGEST", "02-where.png"),
    ("drivers", "WHAT'S DRIVING IT", "03-drivers.png"),
    ("effects", "WHAT SOME MAY NOTICE", "04-effects.png"),
    ("summary", "TODAY'S SIGNALS", "05-summary.png"),
)

BOOTSTRAP_BACKGROUNDS = (
    "bootstrap:social_alerts/migraine_pressure",
    "bootstrap:social_alerts/weather_pressure",
    "bootstrap:social_alerts/air_quality_haze",
    "bootstrap:social_alerts/nervous_system_static",
    "bootstrap:social_alerts/earthscope_cosmic",
)

FONT_DIR = Path(__file__).resolve().parents[1] / "earthscope_post" / "fonts"
DISPLAY_FONT = FONT_DIR / "BebasNeue.ttf"
BODY_FONT = FONT_DIR / "Poppins" / "Poppins-SemiBold.ttf"
BRAND_FONT = FONT_DIR / "Poppins" / "Poppins-Regular.ttf"


def _run(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(command), check=True, capture_output=True, text=True)


def _ffmpeg_executable() -> str | None:
    system = shutil.which("ffmpeg")
    if system:
        return system
    try:
        import imageio_ffmpeg

        bundled = imageio_ffmpeg.get_ffmpeg_exe()
        return bundled if Path(bundled).is_file() else None
    except (ImportError, RuntimeError):
        return None


def _read_bundle(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("shadow input must be a JSON object")
    return payload


def _validate_input(bundle: Mapping[str, Any]) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    report = bundle.get("report") if isinstance(bundle.get("report"), Mapping) else {}
    platform_copy = report.get("platform_copy") if isinstance(report.get("platform_copy"), Mapping) else {}
    story = platform_copy.get("reel_story") if isinstance(platform_copy.get("reel_story"), Mapping) else {}
    errors: list[str] = []
    if bundle.get("auto_publish") is not False or report.get("auto_publish") is not False:
        errors.append("renderer accepts shadow-only bundles with auto_publish=false")
    if report.get("edition") != "us":
        errors.append("renderer requires the U.S. Health Snapshot edition")
    if report.get("public_name") != "Gaia Eyes U.S. Health Snapshot":
        errors.append("unexpected report public_name")
    for key, _label, _filename in SLIDE_SPECS:
        if key == "summary":
            summary = story.get("summary") if isinstance(story.get("summary"), Mapping) else {}
            if not all(str(summary.get(row) or "").strip() for row in ("regional", "space", "earth")):
                errors.append("missing reel_story.summary Regional, Space, or Earth row")
        elif not str(story.get(key) or "").strip():
            errors.append(f"missing reel_story.{key}")
    if errors:
        raise ValueError("; ".join(errors))
    return report, dict(story)


def _local_background(background_dir: Path | None, index: int) -> Path | None:
    if not background_dir:
        return None
    stems = (f"health_snapshot_{index}", f"reel_bg_{index}")
    for stem in stems:
        for suffix in (".jpg", ".jpeg", ".png", ".webp"):
            candidate = background_dir / f"{stem}{suffix}"
            if candidate.is_file():
                return candidate
    return None


def _background(index: int, background_dir: Path | None) -> tuple[Image.Image, str, list[str]]:
    local = _local_background(background_dir, index)
    if local:
        with Image.open(local) as source:
            return ImageOps.exif_transpose(source).convert("RGB"), str(local), []
    candidate = BOOTSTRAP_BACKGROUNDS[index - 1]
    image, source, warnings = resolve_background_image(
        [candidate],
        category="health_snapshot",
        size=CANVAS,
    )
    return image, source, warnings


def _prepare_background(image: Image.Image) -> Image.Image:
    prepared = ImageOps.fit(image.convert("RGB"), CANVAS, method=Image.Resampling.LANCZOS)
    prepared = prepared.filter(ImageFilter.GaussianBlur(radius=5))
    prepared = ImageEnhance.Color(prepared).enhance(0.92)
    prepared = ImageEnhance.Brightness(prepared).enhance(0.72)
    canvas = prepared.convert("RGBA")
    return Image.alpha_composite(canvas, Image.new("RGBA", CANVAS, (0, 0, 0, 58)))


def _font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    if not path.exists():
        raise FileNotFoundError(f"required font is missing: {path}")
    return ImageFont.truetype(str(path), size=size)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        width = draw.textbbox((0, 0), candidate, font=font)[2]
        if current and width > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def _fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    *,
    max_width: int,
    max_height: int,
    max_lines: int,
    maximum_size: int,
    minimum_size: int = 52,
) -> tuple[ImageFont.FreeTypeFont, list[str], int]:
    for size in range(maximum_size, minimum_size - 1, -2):
        font = _font(BODY_FONT, size)
        lines = _wrap(draw, text, font, max_width)
        line_height = int(size * 1.22)
        if len(lines) <= max_lines and len(lines) * line_height <= max_height:
            return font, lines, line_height
    raise ValueError(f"slide text cannot fit safely without dropping words: {text}")


def _text_bbox(
    draw: ImageDraw.ImageDraw,
    lines: Sequence[str],
    font: ImageFont.FreeTypeFont,
    *,
    x: int,
    y: int,
    line_height: int,
) -> tuple[int, int, int, int]:
    widths = [draw.textbbox((0, 0), line, font=font)[2] for line in lines]
    return (x, y, x + max(widths, default=0), y + line_height * len(lines))


def _render_slide(
    *,
    text: str,
    label: str,
    output_path: Path,
    index: int,
    background_dir: Path | None,
) -> dict[str, Any]:
    background, background_source, warnings = _background(index, background_dir)
    canvas = _prepare_background(background)
    background_digest = hashlib.sha256(canvas.convert("RGB").resize((64, 64)).tobytes()).hexdigest()
    draw = ImageDraw.Draw(canvas)

    brand_font = _font(BRAND_FONT, 30)
    label_font = _font(DISPLAY_FONT, 54)
    draw.text((88, 312), "GAIA EYES", font=brand_font, fill=(224, 240, 248, 205))
    draw.text((88, 414), label, font=label_font, fill=(78, 224, 230, 255))

    left, top, right, bottom = SAFE_TEXT_BOX
    maximum_size = 128 if index == 1 else (92 if index < 5 else 76)
    max_lines = 3 if index == 1 else (5 if index < 5 else 7)
    body_font, lines, line_height = _fit_text(
        draw,
        text,
        max_width=right - left,
        max_height=bottom - top,
        max_lines=max_lines,
        maximum_size=maximum_size,
    )
    block_height = line_height * len(lines)
    y = max(top, min(690 if index == 1 else 640, bottom - block_height))
    bbox = _text_bbox(draw, lines, body_font, x=left, y=y, line_height=line_height)
    if bbox[2] > right or bbox[3] > bottom:
        raise ValueError(f"slide {index} text exceeds the safe area: {bbox}")
    for line in lines:
        draw.text((left, y), line, font=body_font, fill=(255, 255, 255, 255))
        y += line_height

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(output_path, "PNG", optimize=True)
    return {
        "index": index,
        "key": SLIDE_SPECS[index - 1][0],
        "label": label,
        "text": text,
        "path": str(output_path),
        "background_source": background_source,
        "background_digest": background_digest,
        "background_warnings": warnings,
        "font_size": body_font.size,
        "wrapped_lines": lines,
        "text_bbox": list(bbox),
        "safe_text_box": list(SAFE_TEXT_BOX),
    }


def _render_summary_slide(
    *,
    summary: Mapping[str, Any],
    output_path: Path,
    index: int,
    background_dir: Path | None,
) -> dict[str, Any]:
    background, background_source, warnings = _background(index, background_dir)
    canvas = _prepare_background(background)
    background_digest = hashlib.sha256(canvas.convert("RGB").resize((64, 64)).tobytes()).hexdigest()
    draw = ImageDraw.Draw(canvas)
    draw.text((88, 312), "GAIA EYES", font=_font(BRAND_FONT, 30), fill=(224, 240, 248, 205))
    draw.text((88, 414), "TODAY'S SIGNALS", font=_font(DISPLAY_FONT, 54), fill=(78, 224, 230, 255))

    rows = [("REGIONAL", "regional"), ("SPACE", "space"), ("EARTH", "earth")]
    if str(summary.get("major_event") or "").strip():
        rows.append(("MAJOR EVENT", "major_event"))
    left, top, right, bottom = SAFE_TEXT_BOX
    row_gap = 34
    row_height = (bottom - top - row_gap * (len(rows) - 1)) // len(rows)
    y = top
    all_lines: list[str] = []
    rendered_rows: list[dict[str, Any]] = []
    right_edge = left
    bottom_edge = top
    for label, key in rows:
        text = str(summary.get(key) or "").strip()
        draw.text((left, y), label, font=_font(DISPLAY_FONT, 36), fill=(78, 224, 230, 255))
        text_y = y + 54
        font, lines, line_height = _fit_text(
            draw,
            text,
            max_width=right - left,
            max_height=row_height - 54,
            max_lines=3,
            maximum_size=58,
            minimum_size=40,
        )
        bbox = _text_bbox(draw, lines, font, x=left, y=text_y, line_height=line_height)
        for line in lines:
            draw.text((left, text_y), line, font=font, fill=(255, 255, 255, 255))
            text_y += line_height
        all_lines.extend(lines)
        right_edge = max(right_edge, bbox[2])
        bottom_edge = max(bottom_edge, bbox[3])
        rendered_rows.append({"label": label, "key": key, "text": text, "font_size": font.size, "bbox": list(bbox)})
        y += row_height + row_gap

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(output_path, "PNG", optimize=True)
    source_text = " ".join(str(summary.get(key) or "").strip() for _label, key in rows)
    return {
        "index": index,
        "key": "summary",
        "label": "TODAY'S SIGNALS",
        "text": source_text,
        "path": str(output_path),
        "background_source": background_source,
        "background_digest": background_digest,
        "background_warnings": warnings,
        "font_size": min(row["font_size"] for row in rendered_rows),
        "wrapped_lines": all_lines,
        "text_bbox": [left, top, right_edge, bottom_edge],
        "safe_text_box": list(SAFE_TEXT_BOX),
        "summary_rows": rendered_rows,
    }


def _render_video(slides: Sequence[Path], output_path: Path, work_dir: Path) -> None:
    ffmpeg = _ffmpeg_executable()
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required for reel rendering and preflight")
    work_dir.mkdir(parents=True, exist_ok=True)
    clips: list[Path] = []
    for index, (slide, duration) in enumerate(zip(slides, SLIDE_DURATION_SECONDS), start=1):
        clip = work_dir / f"clip-{index}.mp4"
        zoom = "min(zoom+0.00045,1.035)" if index % 2 else "min(zoom+0.00035,1.028)"
        _run(
            [
                ffmpeg,
                "-y",
                "-loop",
                "1",
                "-i",
                str(slide),
                "-t",
                f"{duration:.3f}",
                "-vf",
                (
                    "scale=1080:1920,"
                    f"zoompan=z='{zoom}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                    f"d=1:s=1080x1920:fps={FPS},format=yuv420p"
                ),
                "-an",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(clip),
            ]
        )
        clips.append(clip)

    filter_parts: list[str] = []
    previous = "0:v"
    cumulative = SLIDE_DURATION_SECONDS[0]
    for index in range(1, len(clips)):
        output = "vout" if index == len(clips) - 1 else f"v{index}"
        offset = cumulative - XFADE_SECONDS
        filter_parts.append(
            f"[{previous}][{index}:v]xfade=transition=fade:duration={XFADE_SECONDS}:offset={offset:.3f}[{output}]"
        )
        previous = output
        cumulative += SLIDE_DURATION_SECONDS[index] - XFADE_SECONDS

    video_only = work_dir / "video-only.mp4"
    _run(
        [
            ffmpeg,
            "-y",
            *[part for clip in clips for part in ("-i", str(clip))],
            "-filter_complex",
            ";".join(filter_parts),
            "-map",
            "[vout]",
            "-an",
            "-r",
            str(FPS),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(video_only),
        ]
    )
    total_duration = sum(SLIDE_DURATION_SECONDS) - XFADE_SECONDS * (len(slides) - 1)
    _run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(video_only),
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=48000:cl=stereo",
            "-t",
            f"{total_duration:.3f}",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    )


def _image_health(path: Path) -> dict[str, Any]:
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        gray = rgb.convert("L")
        stats = ImageStat.Stat(gray)
        digest = hashlib.sha256(gray.resize((64, 64)).tobytes()).hexdigest()
        return {
            "width": rgb.width,
            "height": rgb.height,
            "mean_luma": round(float(stats.mean[0]), 2),
            "variance": round(float(stats.var[0]), 2),
            "pixel_digest": digest,
        }


def _probe_video(path: Path) -> dict[str, Any]:
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        result = _run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                str(path),
            ]
        )
        return json.loads(result.stdout)

    ffmpeg = _ffmpeg_executable()
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required for reel preflight")
    inspection = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(path)],
        check=False,
        capture_output=True,
        text=True,
    )
    details = inspection.stderr
    duration_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", details)
    duration = 0.0
    if duration_match:
        duration = int(duration_match.group(1)) * 3600 + int(duration_match.group(2)) * 60 + float(duration_match.group(3))
    video_match = re.search(r"Stream[^\n]*Video:[^\n]*?\b(\d{2,5})x(\d{2,5})\b", details)
    video_codec_match = re.search(r"Stream[^\n]*Video:\s*([^,\s]+)", details)
    audio_match = re.search(r"Stream[^\n]*Audio:\s*([^,\s]+)", details)
    streams: list[dict[str, Any]] = []
    if video_match:
        streams.append(
            {
                "codec_type": "video",
                "codec_name": video_codec_match.group(1) if video_codec_match else None,
                "width": int(video_match.group(1)),
                "height": int(video_match.group(2)),
            }
        )
    if audio_match:
        streams.append({"codec_type": "audio", "codec_name": audio_match.group(1)})
    return {"streams": streams, "format": {"duration": duration}}


def _video_frame_health(video_path: Path, output_dir: Path) -> list[dict[str, Any]]:
    ffmpeg = _ffmpeg_executable()
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required for reel frame preflight")
    frames_dir = output_dir / "preflight-frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    times: list[float] = []
    cursor = 0.0
    for duration in SLIDE_DURATION_SECONDS:
        times.append(cursor + min(1.0, duration / 2))
        cursor += duration - XFADE_SECONDS
    health: list[dict[str, Any]] = []
    for index, timestamp in enumerate(times, start=1):
        frame_path = frames_dir / f"frame-{index}.png"
        _run(
            [
                ffmpeg,
                "-y",
                "-ss",
                f"{timestamp:.3f}",
                "-i",
                str(video_path),
                "-frames:v",
                "1",
                str(frame_path),
            ]
        )
        health.append({"timestamp": timestamp, "path": str(frame_path), **_image_health(frame_path)})
    return health


def _preflight(
    *,
    bundle: Mapping[str, Any],
    slide_metadata: Sequence[Mapping[str, Any]],
    video_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    slide_health: list[dict[str, Any]] = []
    background_sources: list[str] = []
    background_digests: list[str] = []
    for slide in slide_metadata:
        path = Path(str(slide["path"]))
        health = _image_health(path)
        slide_health.append({"path": str(path), **health})
        if (health["width"], health["height"]) != CANVAS:
            errors.append(f"{path.name} is not 1080x1920")
        if health["variance"] < 80:
            errors.append(f"{path.name} appears blank or nearly blank")
        bbox = tuple(int(value) for value in slide["text_bbox"])
        safe = tuple(int(value) for value in slide["safe_text_box"])
        if bbox[0] < safe[0] or bbox[1] < safe[1] or bbox[2] > safe[2] or bbox[3] > safe[3]:
            errors.append(f"{path.name} text falls outside the safe area")
        if " ".join(slide["wrapped_lines"]).strip() != " ".join(str(slide["text"]).split()):
            errors.append(f"{path.name} dropped or changed text while wrapping")
        background_sources.append(str(slide["background_source"]))
        background_digests.append(str(slide["background_digest"]))
        warnings.extend(str(item) for item in slide.get("background_warnings") or [])
    if len(set(background_sources)) != len(SLIDE_SPECS):
        errors.append("each slide must use a different blank background source")
    if len(set(background_digests)) != len(SLIDE_SPECS):
        errors.append("each slide must use visually distinct blank background pixels")

    probe = _probe_video(video_path)
    streams = probe.get("streams") if isinstance(probe.get("streams"), list) else []
    video_streams = [stream for stream in streams if stream.get("codec_type") == "video"]
    audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]
    if len(video_streams) != 1:
        errors.append("reel must contain exactly one video stream")
    if len(audio_streams) != 1:
        errors.append("reel must contain exactly one audio stream")
    if video_streams:
        stream = video_streams[0]
        if (int(stream.get("width") or 0), int(stream.get("height") or 0)) != CANVAS:
            errors.append("reel video stream is not 1080x1920")
        if stream.get("codec_name") != "h264":
            errors.append("reel video stream must use H.264")
    if audio_streams and audio_streams[0].get("codec_name") != "aac":
        errors.append("reel audio stream must use AAC")
    duration = float((probe.get("format") or {}).get("duration") or 0)
    if duration < 12:
        errors.append("reel duration is unexpectedly short")

    frame_health = _video_frame_health(video_path, output_dir)
    if any(frame["variance"] < 80 for frame in frame_health):
        errors.append("one or more sampled reel frames appear blank")
    if len({frame["pixel_digest"] for frame in frame_health}) != len(frame_health):
        errors.append("sampled reel frames are not visually distinct")

    report = bundle.get("report") if isinstance(bundle.get("report"), Mapping) else {}
    return {
        "schema_version": "us-health-snapshot-reel-preflight.v1",
        "mode": "shadow",
        "auto_publish": False,
        "passed": not errors,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source_day": report.get("day"),
        "source_public_name": report.get("public_name"),
        "errors": errors,
        "warnings": warnings,
        "slides": list(slide_metadata),
        "slide_health": slide_health,
        "video": {
            "path": str(video_path),
            "duration_seconds": round(duration, 3),
            "stream_count": len(streams),
            "sampled_frames": frame_health,
        },
    }


def render_us_health_snapshot_reel(
    input_path: Path | str,
    output_dir: Path | str,
    *,
    background_dir: Path | str | None = None,
) -> dict[str, Any]:
    input_file = Path(input_path)
    destination = Path(output_dir)
    bundle = _read_bundle(input_file)
    _report, story = _validate_input(bundle)
    background_path = Path(background_dir) if background_dir else None
    slides_dir = destination / "slides"
    slide_metadata: list[dict[str, Any]] = []
    for index, (key, label, filename) in enumerate(SLIDE_SPECS, start=1):
        if key == "summary":
            slide_metadata.append(
                _render_summary_slide(
                    summary=story[key],
                    output_path=slides_dir / filename,
                    index=index,
                    background_dir=background_path,
                )
            )
        else:
            slide_metadata.append(
                _render_slide(
                    text=str(story[key]),
                    label=label,
                    output_path=slides_dir / filename,
                    index=index,
                    background_dir=background_path,
                )
            )

    video_path = destination / "us-health-snapshot-preview.mp4"
    work_dir = destination / ".render-work"
    _render_video([Path(slide["path"]) for slide in slide_metadata], video_path, work_dir)
    shutil.rmtree(work_dir, ignore_errors=True)
    manifest = _preflight(
        bundle=bundle,
        slide_metadata=slide_metadata,
        video_path=video_path,
        output_dir=destination,
    )
    destination.mkdir(parents=True, exist_ok=True)
    manifest_path = destination / "preflight-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Render and preflight a shadow-only Gaia Eyes U.S. Health Snapshot reel.")
    parser.add_argument("--input", required=True, help="U.S. Health Snapshot shadow JSON bundle.")
    parser.add_argument("--output-dir", required=True, help="Directory for slides, MP4, frames, and manifest.")
    parser.add_argument("--background-dir", default=None, help="Optional directory containing blank health_snapshot_1..5 assets.")
    args = parser.parse_args()
    manifest = render_us_health_snapshot_reel(
        args.input,
        args.output_dir,
        background_dir=args.background_dir,
    )
    print(json.dumps({"passed": manifest["passed"], "manifest": str(Path(args.output_dir) / "preflight-manifest.json")}))
    if not manifest["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
