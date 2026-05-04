#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple
from urllib.parse import urlparse
from urllib.request import urlopen

from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MEDIA_BASE_URL = "https://qadwzkwubfbfuslfxkzl.supabase.co/storage/v1/object/public/space-visuals"
DEFAULT_PREVIEW_DIR = Path("tmp") / "social_alerts_shadow" / "previews"
FALLBACK_GRADIENTS = {
    "solar_flare": ((36, 10, 5), (236, 138, 42), (5, 20, 34)),
    "cme": ((7, 18, 32), (68, 148, 214), (240, 144, 54)),
    "schumann": ((8, 18, 25), (64, 196, 155), (150, 108, 216)),
    "geomagnetic": ((6, 18, 34), (73, 131, 236), (125, 213, 154)),
}


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _slug(value: Any) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", _safe_text(value).lower()).strip("-")
    return text or "draft"


def _media_base_url() -> str:
    raw = (
        os.environ.get("VISUALS_MEDIA_BASE_URL", "").strip()
        or os.environ.get("MEDIA_BASE_URL", "").strip()
        or os.environ.get("GAIA_MEDIA_BASE", "").strip()
    )
    if raw:
        return raw.rstrip("/")
    supabase_url = os.environ.get("SUPABASE_URL", "").strip()
    if supabase_url:
        return f"{supabase_url.rstrip('/')}/storage/v1/object/public/space-visuals"
    return DEFAULT_MEDIA_BASE_URL


def _media_repo_path() -> Path:
    return Path(os.environ.get("MEDIA_REPO_PATH", str(REPO_ROOT / "gaiaeyes-media"))).expanduser()


def _is_url(candidate: str) -> bool:
    parsed = urlparse(candidate)
    return parsed.scheme in {"http", "https"}


def _remote_url(candidate: str, media_base_url: str) -> Optional[str]:
    candidate = candidate.strip()
    if not candidate or candidate.startswith("media_repo:"):
        return None
    if _is_url(candidate):
        return candidate
    return f"{media_base_url.rstrip('/')}/{candidate.lstrip('/')}"


def _latest_file(patterns: Sequence[str]) -> Optional[Path]:
    matches: List[Path] = []
    for pattern in patterns:
        matches.extend(REPO_ROOT.glob(pattern))
    existing = [path for path in matches if path.is_file()]
    if not existing:
        return None
    existing.sort(key=lambda path: (path.stat().st_mtime, path.name))
    return existing[-1]


def _local_candidates(candidate: str) -> List[Path]:
    candidate = candidate.strip()
    media_repo = _media_repo_path()
    paths: List[Path] = []

    if candidate.startswith("media_repo:"):
        relative = candidate.removeprefix("media_repo:").lstrip("/")
        paths.extend([media_repo / relative, REPO_ROOT / "gaiaeyes-media" / relative])
    elif candidate:
        paths.extend([REPO_ROOT / candidate, REPO_ROOT / "gaiaeyes-media" / candidate, media_repo / candidate])

    alias_patterns = {
        "nasa/ccor1/latest.jpg": ["gaiaeyes-media/images/space/ccor1_*.jpg"],
        "nasa/aia_304/latest.jpg": ["gaiaeyes-media/images/space/aia_primary_*.jpg"],
        "nasa/lasco_c2/latest.jpg": ["gaiaeyes-media/images/space/soho_c2_*.jpg"],
        "nasa/geospace_3h/latest.jpg": ["gaiaeyes-media/images/space/geospace_3h_*.png"],
        "schumann/latest/tomsk_share_latest.jpg": [
            "gaiaeyes-media/images/tomsk/*270x270*.png",
            "gaiaeyes-media/images/tomsk/*cropped*.png",
        ],
        "schumann/tomsk_share_latest.jpg": [
            "gaiaeyes-media/images/tomsk/*270x270*.png",
            "gaiaeyes-media/images/tomsk/*cropped*.png",
        ],
        "social/earthscope/latest/tomsk_share_latest.jpg": [
            "gaiaeyes-media/images/tomsk/*270x270*.png",
            "gaiaeyes-media/images/tomsk/*cropped*.png",
        ],
    }
    for pattern in alias_patterns.get(candidate, []):
        latest = _latest_file([pattern])
        if latest is not None:
            paths.append(latest)

    seen: Set[Path] = set()
    resolved: List[Path] = []
    for path in paths:
        expanded = path.expanduser()
        if expanded not in seen and expanded.is_file():
            resolved.append(expanded)
            seen.add(expanded)
    return resolved


def _open_local_image(path: Path) -> Image.Image:
    with Image.open(path) as image:
        return ImageOps.exif_transpose(image).convert("RGB")


def _open_remote_image(url: str, *, timeout: float) -> Image.Image:
    with urlopen(url, timeout=timeout) as response:
        content = response.read()
    with Image.open(BytesIO(content)) as image:
        return ImageOps.exif_transpose(image).convert("RGB")


def _fallback_background(category: str, size: Tuple[int, int]) -> Image.Image:
    width, height = size
    colors = FALLBACK_GRADIENTS.get(category, ((5, 12, 25), (73, 131, 236), (125, 213, 154)))
    image = Image.new("RGB", size, colors[0])
    draw = ImageDraw.Draw(image)
    for y in range(height):
        t = y / max(height - 1, 1)
        if t < 0.55:
            local = t / 0.55
            start, end = colors[0], colors[1]
        else:
            local = (t - 0.55) / 0.45
            start, end = colors[1], colors[2]
        rgb = tuple(int(start[i] + (end[i] - start[i]) * local) for i in range(3))
        draw.line([(0, y), (width, y)], fill=rgb)
    return image


def resolve_background_image(
    candidates: Sequence[str],
    *,
    category: str,
    size: Tuple[int, int],
    media_base_url: Optional[str] = None,
    local_asset_overrides: Optional[Mapping[str, Path | str]] = None,
    timeout: float = 8.0,
) -> Tuple[Image.Image, str, List[str]]:
    """Resolve the first usable preview background image from local or public media assets."""
    warnings: List[str] = []
    base_url = media_base_url or _media_base_url()
    overrides = dict(local_asset_overrides or {})

    for candidate in candidates:
        if candidate in overrides:
            try:
                return _open_local_image(Path(overrides[candidate])), candidate, warnings
            except Exception as exc:
                warnings.append(f"{candidate}: local override failed: {exc}")

    for candidate in candidates:
        url = _remote_url(candidate, base_url)
        if url:
            try:
                return _open_remote_image(url, timeout=timeout), url, warnings
            except Exception as exc:
                warnings.append(f"{candidate}: remote image failed at {url}: {exc}")

    for candidate in candidates:
        for path in _local_candidates(candidate):
            try:
                return _open_local_image(path), str(path), warnings
            except Exception as exc:
                warnings.append(f"{candidate}: local image failed at {path}: {exc}")

    warnings.append("No candidate image resolved; generated fallback background.")
    return _fallback_background(category, size), "generated:fallback_gradient", warnings


def _cover(image: Image.Image, size: Tuple[int, int]) -> Image.Image:
    return ImageOps.fit(image, size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Avenir Next.ttc",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except Exception:
            continue
    return ImageFont.load_default()


def _text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> Tuple[int, int]:
    if not text:
        return 0, 0
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    return right - left, bottom - top


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> List[str]:
    words = _safe_text(text).split()
    if not words:
        return []
    lines: List[str] = []
    current = words[0]
    for word in words[1:]:
        proposed = f"{current} {word}"
        if _text_size(draw, proposed, font)[0] <= max_width:
            current = proposed
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _draw_wrapped_text(
    draw: ImageDraw.ImageDraw,
    xy: Tuple[int, int],
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
    *,
    fill: Tuple[int, int, int, int] | Tuple[int, int, int],
    line_gap: int = 10,
    align: str = "left",
) -> int:
    x, y = xy
    for line in _wrap_text(draw, text, font, max_width):
        width, height = _text_size(draw, line, font)
        line_x = x
        if align == "center":
            line_x = x + max((max_width - width) // 2, 0)
        draw.text((line_x, y), line, font=font, fill=fill)
        y += height + line_gap
    return y


def _add_shadow_layer(base: Image.Image, intensity: int = 138) -> Image.Image:
    image = ImageEnhance.Color(base).enhance(1.12).convert("RGBA")
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    width, height = image.size
    draw.rectangle((0, 0, width, height), fill=(3, 8, 16, intensity))
    for y in range(height):
        alpha = int(70 * (1 - abs((y / max(height - 1, 1)) - 0.42)))
        draw.line((0, y, width, y), fill=(0, 0, 0, max(alpha, 0)))
    return Image.alpha_composite(image, overlay)


def _chip_palette(index: int) -> Tuple[Tuple[int, int, int, int], Tuple[int, int, int, int], Tuple[int, int, int, int]]:
    palettes = [
        ((36, 82, 155, 130), (101, 157, 255, 220), (214, 229, 255, 255)),
        ((123, 89, 24, 130), (242, 197, 88, 220), (255, 239, 183, 255)),
        ((29, 107, 82, 130), (126, 219, 165, 220), (221, 255, 232, 255)),
        ((82, 45, 113, 130), (197, 132, 243, 220), (246, 227, 255, 255)),
    ]
    return palettes[index % len(palettes)]


def _draw_chip(draw: ImageDraw.ImageDraw, box: Tuple[int, int, int, int], label: str, value: str, index: int) -> None:
    fill, outline, text_fill = _chip_palette(index)
    label_font = _font(29, bold=True)
    value_font = _font(34, bold=True)
    draw.rounded_rectangle(box, radius=30, fill=fill, outline=outline, width=2)
    x1, y1, x2, y2 = box
    draw.text((x1 + 32, y1 + 22), _safe_text(label).upper(), font=label_font, fill=outline)
    value_text = _safe_text(value) or "--"
    value_width, value_height = _text_size(draw, value_text, value_font)
    draw.text((x2 - value_width - 32, y1 + ((y2 - y1 - value_height) // 2) + 3), value_text, font=value_font, fill=text_fill)


def _chip_rows(chips: Sequence[Mapping[str, Any]], *, width: int, x: int, y: int, gap: int = 18) -> List[Tuple[int, int, int, int, Mapping[str, Any]]]:
    if not chips:
        return []
    rows: List[Tuple[int, int, int, int, Mapping[str, Any]]] = []
    chip_width = int((width - gap * (min(len(chips), 3) - 1)) / min(len(chips), 3))
    for index, chip in enumerate(chips):
        row = index // 3
        col = index % 3
        left = x + col * (chip_width + gap)
        top = y + row * 88
        rows.append((left, top, left + chip_width, top + 70, chip))
    return rows


def _candidate_images(spec: Mapping[str, Any]) -> List[str]:
    candidates: List[str] = []
    for key in ("still_candidates", "background_candidates"):
        values = spec.get(key)
        if not isinstance(values, list):
            continue
        for value in values:
            text = _safe_text(value)
            if text and text not in candidates and not text.lower().endswith(".mp4"):
                candidates.append(text)
    return candidates


def _render_square(
    draft: Mapping[str, Any],
    *,
    output_path: Path,
    media_base_url: Optional[str],
    local_asset_overrides: Optional[Mapping[str, Path | str]],
) -> Dict[str, Any]:
    overlay = draft.get("overlay_spec") if isinstance(draft.get("overlay_spec"), Mapping) else {}
    spec = overlay.get("square_image") if isinstance(overlay.get("square_image"), Mapping) else {}
    canvas = spec.get("canvas") if isinstance(spec.get("canvas"), Mapping) else {}
    size = (int(canvas.get("width") or 1080), int(canvas.get("height") or 1080))
    candidates = _candidate_images(spec)
    category = _safe_text(draft.get("category")) or "social_alert"
    background, used_source, warnings = resolve_background_image(
        candidates,
        category=category,
        size=size,
        media_base_url=media_base_url,
        local_asset_overrides=local_asset_overrides,
    )
    image = _add_shadow_layer(_cover(background, size), intensity=128)
    draw = ImageDraw.Draw(image)

    margin = 76
    draw.rounded_rectangle((margin, 54, size[0] - margin, 118), radius=30, fill=(6, 17, 30, 138), outline=(142, 180, 211, 96), width=1)
    eyebrow = "GAIA EYES - SOCIAL ALERT"
    eyebrow_font = _font(25, bold=True)
    eyebrow_width, _ = _text_size(draw, eyebrow, eyebrow_font)
    draw.text(((size[0] - eyebrow_width) // 2, 73), eyebrow, font=eyebrow_font, fill=(223, 232, 244, 230))

    title_font = _font(82, bold=True)
    subtitle_font = _font(37)
    title = _safe_text(draft.get("title") or spec.get("title")).upper()
    subtitle = _safe_text(draft.get("subtitle") or spec.get("subtitle"))
    y = 170
    y = _draw_wrapped_text(draw, (margin + 12, y), title, title_font, size[0] - margin * 2 - 24, fill=(211, 248, 224, 255), line_gap=8, align="center")
    y += 18
    y = _draw_wrapped_text(draw, (margin + 72, y), subtitle, subtitle_font, size[0] - margin * 2 - 144, fill=(236, 240, 246, 230), line_gap=8, align="center")

    chips = spec.get("metric_chips") if isinstance(spec.get("metric_chips"), list) else []
    chip_y = max(y + 52, 600)
    for index, (x1, y1, x2, y2, chip) in enumerate(_chip_rows(chips, width=size[0] - margin * 2, x=margin, y=chip_y)):
        if isinstance(chip, Mapping):
            _draw_chip(draw, (x1, y1, x2, y2), _safe_text(chip.get("label")), _safe_text(chip.get("value")), index)

    note_box = (margin, size[1] - 246, size[0] - margin, size[1] - 116)
    draw.rounded_rectangle(note_box, radius=30, fill=(4, 14, 25, 154), outline=(126, 219, 165, 115), width=2)
    footer_font = _font(32)
    cta_font = _font(36, bold=True)
    draw.text((note_box[0] + 42, note_box[1] + 28), "Open Gaia Eyes for the full signal read.", font=cta_font, fill=(222, 255, 235, 245))
    draw.text((note_box[0] + 42, note_box[1] + 78), _safe_text(spec.get("footer")) or "Gaia Eyes", font=footer_font, fill=(229, 234, 242, 210))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(output_path, "PNG")
    return {
        "format": "square_image",
        "path": str(output_path),
        "canvas": {"width": size[0], "height": size[1]},
        "asset_source": used_source,
        "warnings": warnings,
    }


def _render_story(
    draft: Mapping[str, Any],
    *,
    output_path: Path,
    media_base_url: Optional[str],
    local_asset_overrides: Optional[Mapping[str, Path | str]],
) -> Dict[str, Any]:
    overlay = draft.get("overlay_spec") if isinstance(draft.get("overlay_spec"), Mapping) else {}
    spec = overlay.get("story_reel") if isinstance(overlay.get("story_reel"), Mapping) else {}
    canvas = spec.get("canvas") if isinstance(spec.get("canvas"), Mapping) else {}
    size = (int(canvas.get("width") or 1080), int(canvas.get("height") or 1920))
    candidates = _candidate_images(spec)
    category = _safe_text(draft.get("category")) or "social_alert"
    background, used_source, warnings = resolve_background_image(
        candidates,
        category=category,
        size=size,
        media_base_url=media_base_url,
        local_asset_overrides=local_asset_overrides,
    )
    image = _add_shadow_layer(_cover(background, size), intensity=146)
    draw = ImageDraw.Draw(image)

    margin = 86
    draw.rounded_rectangle((margin, 100, size[0] - margin, 170), radius=34, fill=(5, 17, 31, 152), outline=(142, 180, 211, 100), width=1)
    label = "GAIA EYES - REVIEW DRAFT"
    label_font = _font(27, bold=True)
    label_width, _ = _text_size(draw, label, label_font)
    draw.text(((size[0] - label_width) // 2, 122), label, font=label_font, fill=(226, 234, 244, 230))

    title = _safe_text(draft.get("title")).upper()
    subtitle = _safe_text(draft.get("subtitle"))
    title_font = _font(92, bold=True)
    subtitle_font = _font(42)
    y = 250
    y = _draw_wrapped_text(draw, (margin, y), title, title_font, size[0] - margin * 2, fill=(211, 248, 224, 255), line_gap=12, align="center")
    y += 34
    y = _draw_wrapped_text(draw, (margin + 30, y), subtitle, subtitle_font, size[0] - margin * 2 - 60, fill=(238, 241, 247, 232), line_gap=12, align="center")

    chips = spec.get("frames", [{}])[1].get("metric_chips") if isinstance(spec.get("frames"), list) and len(spec.get("frames")) > 1 and isinstance(spec.get("frames")[1], Mapping) else []
    if not isinstance(chips, list):
        chips = []
    panel_top = max(y + 82, 900)
    panel = (margin, panel_top, size[0] - margin, panel_top + 410)
    draw.rounded_rectangle(panel, radius=42, fill=(3, 13, 23, 158), outline=(128, 199, 224, 115), width=2)
    panel_title = "Current Signal"
    panel_font = _font(36, bold=True)
    draw.text((panel[0] + 44, panel[1] + 36), panel_title, font=panel_font, fill=(126, 219, 165, 240))
    chip_width = panel[2] - panel[0] - 88
    for index, chip in enumerate(chips[:4]):
        if not isinstance(chip, Mapping):
            continue
        top = panel[1] + 98 + index * 76
        _draw_chip(draw, (panel[0] + 44, top, panel[0] + 44 + chip_width, top + 60), _safe_text(chip.get("label")), _safe_text(chip.get("value")), index)

    cta_box = (margin, size[1] - 360, size[0] - margin, size[1] - 190)
    draw.rounded_rectangle(cta_box, radius=42, fill=(5, 16, 29, 165), outline=(197, 132, 243, 125), width=2)
    cta_font = _font(43, bold=True)
    body_font = _font(31)
    draw.text((cta_box[0] + 44, cta_box[1] + 42), "Open Gaia Eyes", font=cta_font, fill=(236, 218, 255, 246))
    draw.text((cta_box[0] + 44, cta_box[1] + 100), "Review the full signal context before sharing.", font=body_font, fill=(234, 238, 246, 220))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(output_path, "PNG")
    return {
        "format": "story_reel_frame",
        "path": str(output_path),
        "canvas": {"width": size[0], "height": size[1]},
        "asset_source": used_source,
        "video_candidates": spec.get("video_candidates") if isinstance(spec.get("video_candidates"), list) else [],
        "warnings": warnings,
    }


def render_shadow_previews(
    payload: Mapping[str, Any],
    output_dir: Path | str = DEFAULT_PREVIEW_DIR,
    *,
    categories: Optional[Set[str]] = None,
    media_base_url: Optional[str] = None,
    local_asset_overrides: Optional[Mapping[str, Path | str]] = None,
) -> Dict[str, Any]:
    drafts = payload.get("drafts") if isinstance(payload.get("drafts"), list) else []
    out_dir = Path(output_dir)
    rendered: List[Dict[str, Any]] = []
    for draft in drafts:
        if not isinstance(draft, Mapping):
            continue
        category = _safe_text(draft.get("category")) or "social_alert"
        if categories and category not in categories:
            continue
        stem = f"{_slug(category)}-{_slug(draft.get('severity'))}-{_slug(draft.get('id'))[-12:]}"
        square = _render_square(
            draft,
            output_path=out_dir / f"{stem}-square.png",
            media_base_url=media_base_url,
            local_asset_overrides=local_asset_overrides,
        )
        story = _render_story(
            draft,
            output_path=out_dir / f"{stem}-story.png",
            media_base_url=media_base_url,
            local_asset_overrides=local_asset_overrides,
        )
        rendered.append(
            {
                "draft_id": draft.get("id"),
                "category": category,
                "severity": draft.get("severity"),
                "title": draft.get("title"),
                "outputs": [square, story],
            }
        )

    manifest = {
        "schema_version": "social_alerts_preview_v1",
        "mode": "shadow",
        "auto_publish": False,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source_payload_generated_at": payload.get("generated_at"),
        "rendered_count": len(rendered),
        "rendered": rendered,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "preview-manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest


def _category_filter(value: str) -> Optional[Set[str]]:
    if not value.strip():
        return None
    return {_slug(item).replace("-", "_") for item in value.split(",") if item.strip()}


def main() -> None:
    parser = argparse.ArgumentParser(description="Render local PNG previews for Social Alerts shadow drafts.")
    parser.add_argument("--input", required=True, help="Social Alerts shadow payload JSON.")
    parser.add_argument("--output-dir", default=str(DEFAULT_PREVIEW_DIR), help="Directory for PNG previews and manifest.")
    parser.add_argument("--categories", default="", help="Optional comma-separated category filter, e.g. schumann,solar_flare,cme.")
    parser.add_argument("--media-base-url", default="", help="Override public media base URL.")
    args = parser.parse_args()

    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise SystemExit("Input JSON must be an object.")
    manifest = render_shadow_previews(
        payload,
        args.output_dir,
        categories=_category_filter(args.categories),
        media_base_url=args.media_base_url or None,
    )
    print(f"[social_alerts.preview] rendered {manifest['rendered_count']} draft preview(s) -> {args.output_dir}")


if __name__ == "__main__":
    main()
