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

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MEDIA_BASE_URL = "https://qadwzkwubfbfuslfxkzl.supabase.co/storage/v1/object/public/space-visuals"
DEFAULT_PREVIEW_DIR = Path("tmp") / "social_alerts_shadow" / "previews"
FALLBACK_GRADIENTS = {
    "solar_flare": ((36, 10, 5), (236, 138, 42), (5, 20, 34)),
    "cme": ((7, 18, 32), (68, 148, 214), (240, 144, 54)),
    "schumann": ((8, 18, 25), (64, 196, 155), (150, 108, 216)),
    "geomagnetic": ((6, 18, 34), (73, 131, 236), (125, 213, 154)),
}
ACCENTS = {
    "cyan": (71, 225, 255),
    "green": (121, 247, 172),
    "amber": (244, 194, 95),
    "violet": (198, 130, 255),
}
DEFAULT_CONTEXT_CHIPS = {
    "schumann": ["Restless", "Wired", "Harder to settle"],
    "solar_flare": ["Solar activity", "Bright signal", "Worth watching"],
    "cme": ["Solar motion", "Review first", "In the mix"],
    "geomagnetic": ["Kp/Bz active", "Solar wind", "Worth watching"],
    "earthquake": ["Official feeds", "Location context", "Review first"],
    "global_hazard": ["Verified feeds", "Location context", "Review first"],
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


def _poster_background(base: Image.Image, size: Tuple[int, int], category: str) -> Image.Image:
    image = _cover(base, size)
    image = ImageEnhance.Color(image).enhance(1.18)
    image = ImageEnhance.Contrast(image).enhance(1.04)
    image = image.filter(ImageFilter.GaussianBlur(radius=1.2)).convert("RGBA")

    width, height = size
    overlay = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for y in range(height):
        t = y / max(height - 1, 1)
        alpha = int(168 + 64 * t)
        blue = int(18 + 12 * (1 - t))
        draw.line((0, y, width, y), fill=(1, 5, blue, alpha))
    draw.rectangle((0, 0, width, height), fill=(0, 0, 0, 42))

    glow = Image.new("RGBA", size, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    cyan = ACCENTS["cyan"]
    green = ACCENTS["green"] if category == "schumann" else ACCENTS["amber"]
    glow_draw.ellipse((-width * 0.25, height * 0.05, width * 0.42, height * 0.55), fill=(*cyan, 40))
    glow_draw.ellipse((width * 0.55, height * 0.28, width * 1.18, height * 0.92), fill=(*green, 34))
    glow = glow.filter(ImageFilter.GaussianBlur(radius=86))
    return Image.alpha_composite(Image.alpha_composite(image, overlay), glow)


def _draw_glass_panel(
    draw: ImageDraw.ImageDraw,
    box: Tuple[int, int, int, int],
    *,
    radius: int,
    accent: Tuple[int, int, int],
) -> None:
    x1, y1, x2, y2 = box
    for step, alpha in enumerate((26, 18, 12), start=1):
        inset = step * 8
        draw.rounded_rectangle(
            (x1 - inset, y1 - inset, x2 + inset, y2 + inset),
            radius=radius + inset,
            outline=(*accent, alpha),
            width=2,
        )
    draw.rounded_rectangle(box, radius=radius, fill=(3, 12, 24, 205), outline=(*accent, 118), width=2)
    draw.rounded_rectangle((x1 + 2, y1 + 2, x2 - 2, y2 - 2), radius=radius - 2, outline=(255, 255, 255, 24), width=1)


def _fit_font(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_width: int,
    *,
    max_size: int,
    min_size: int,
    bold: bool = False,
    max_lines: int = 3,
) -> ImageFont.ImageFont:
    for size in range(max_size, min_size - 1, -2):
        font = _font(size, bold=bold)
        lines = _wrap_text(draw, text, font, max_width)
        if len(lines) <= max_lines and all(_text_size(draw, line, font)[0] <= max_width for line in lines):
            return font
    return _font(min_size, bold=bold)


def _metrics_line(chips: Sequence[Mapping[str, Any]]) -> str:
    parts: List[str] = []
    for chip in chips[:2]:
        label = _safe_text(chip.get("label") if isinstance(chip, Mapping) else "")
        value = _safe_text(chip.get("value") if isinstance(chip, Mapping) else "")
        if label and value and value != "--":
            parts.append(f"{label} {value}")
    return " | ".join(parts)


def _context_chips(spec: Mapping[str, Any], category: str) -> List[str]:
    values = spec.get("context_chips")
    if isinstance(values, list):
        chips = [_safe_text(item) for item in values if _safe_text(item)]
        if chips:
            return chips[:3]
    return DEFAULT_CONTEXT_CHIPS.get(category, ["Worth watching"])[:3]


def _draw_context_chips(
    draw: ImageDraw.ImageDraw,
    chips: Sequence[str],
    *,
    x: int,
    y: int,
    max_width: int,
    font: ImageFont.ImageFont,
) -> int:
    cur_x = x
    cur_y = y
    gap = 14
    row_height = 56
    accents = [ACCENTS["cyan"], ACCENTS["green"], ACCENTS["amber"], ACCENTS["violet"]]
    for index, chip in enumerate(chips[:3]):
        label = _safe_text(chip)
        if not label:
            continue
        text_width, text_height = _text_size(draw, label, font)
        pill_width = text_width + 42
        if cur_x > x and cur_x + pill_width > x + max_width:
            cur_x = x
            cur_y += row_height + gap
        accent = accents[index % len(accents)]
        box = (cur_x, cur_y, cur_x + pill_width, cur_y + row_height)
        draw.rounded_rectangle(box, radius=28, fill=(*accent, 24), outline=(*accent, 128), width=1)
        draw.text((cur_x + 21, cur_y + (row_height - text_height) // 2 - 1), label, font=font, fill=(235, 245, 250, 236))
        cur_x += pill_width + gap
    return cur_y + row_height


def _draw_label(draw: ImageDraw.ImageDraw, box: Tuple[int, int, int, int], text: str, accent: Tuple[int, int, int]) -> None:
    font = _font(24, bold=True)
    x1, y1, x2, y2 = box
    draw.rounded_rectangle(box, radius=(y2 - y1) // 2, fill=(*accent, 20), outline=(*accent, 125), width=1)
    width, height = _text_size(draw, text, font)
    draw.text((x1 + (x2 - x1 - width) // 2, y1 + (y2 - y1 - height) // 2 - 1), text, font=font, fill=(222, 252, 255, 235))


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


def _render_alert_card(
    draft: Mapping[str, Any],
    *,
    output_path: Path,
    spec_name: str,
    default_size: Tuple[int, int],
    format_name: str,
    media_base_url: Optional[str],
    local_asset_overrides: Optional[Mapping[str, Path | str]],
) -> Dict[str, Any]:
    overlay = draft.get("overlay_spec") if isinstance(draft.get("overlay_spec"), Mapping) else {}
    spec = overlay.get(spec_name) if isinstance(overlay.get(spec_name), Mapping) else {}
    if not spec and spec_name == "feed_card":
        spec = overlay.get("square_image") if isinstance(overlay.get("square_image"), Mapping) else {}
    canvas = spec.get("canvas") if isinstance(spec.get("canvas"), Mapping) else {}
    size = (int(canvas.get("width") or default_size[0]), int(canvas.get("height") or default_size[1]))
    if spec_name == "feed_card" and size == (1080, 1080):
        size = default_size
    candidates = _candidate_images(spec)
    category = _safe_text(draft.get("category")) or "social_alert"
    background, used_source, warnings = resolve_background_image(
        candidates,
        category=category,
        size=size,
        media_base_url=media_base_url,
        local_asset_overrides=local_asset_overrides,
    )
    image = _poster_background(background, size, category)
    draw = ImageDraw.Draw(image)

    width, height = size
    accent = ACCENTS["green"] if category == "schumann" else ACCENTS["cyan"]
    margin = 74 if height <= 1100 else 86
    if height <= 1100:
        panel = (margin, 150, width - margin, height - 112)
        title_max = 70
        subtitle_size = 33
        body_gap = 22
    elif height <= 1500:
        panel = (margin, 230, width - margin, height - 170)
        title_max = 80
        subtitle_size = 36
        body_gap = 26
    else:
        panel = (margin, 420, width - margin, height - 310)
        title_max = 92
        subtitle_size = 42
        body_gap = 34

    _draw_glass_panel(draw, panel, radius=44, accent=accent)

    brand_font = _font(25, bold=True)
    brand = "Gaia Eyes"
    brand_width, brand_height = _text_size(draw, brand, brand_font)
    draw.text((width - margin - brand_width, max(52, panel[1] - 78)), brand, font=brand_font, fill=(230, 241, 249, 178))

    x1, y1, x2, y2 = panel
    inner_x = x1 + 58
    inner_w = x2 - x1 - 116
    y = y1 + 54
    label = _safe_text(spec.get("label")) or "SIGNAL WATCH"
    _draw_label(draw, (inner_x, y, inner_x + 218, y + 48), label.upper(), ACCENTS["cyan"])
    y += 82

    title = _safe_text(draft.get("title") or spec.get("title"))
    subtitle = _safe_text(draft.get("subtitle") or spec.get("subtitle"))
    title_font = _fit_font(draw, title, inner_w, max_size=title_max, min_size=52, bold=True, max_lines=3)
    y = _draw_wrapped_text(draw, (inner_x, y), title, title_font, inner_w, fill=(238, 255, 244, 255), line_gap=10)
    y += body_gap

    subtitle_font = _font(subtitle_size)
    y = _draw_wrapped_text(draw, (inner_x, y), subtitle, subtitle_font, inner_w, fill=(226, 235, 244, 232), line_gap=10)
    y += body_gap + 4

    context_font = _font(28 if height <= 1100 else 31, bold=True)
    y = _draw_context_chips(draw, _context_chips(spec, category), x=inner_x, y=y, max_width=inner_w, font=context_font)
    y += body_gap + 6

    draw.line((inner_x, y, inner_x + inner_w, y), fill=(*accent, 104), width=2)
    y += body_gap

    metrics = spec.get("metric_chips") if isinstance(spec.get("metric_chips"), list) else []
    metric_text = _metrics_line(metrics)
    if metric_text:
        metric_font = _font(30 if height <= 1100 else 34, bold=True)
        draw.text((inner_x, y), metric_text, font=metric_font, fill=(255, 220, 148, 245))
        y += _text_size(draw, metric_text, metric_font)[1] + body_gap

    cta_title = _safe_text(spec.get("footer")) or "Facts, not fear."
    cta_font = _font(34 if height <= 1100 else 38, bold=True)
    cta_body_font = _font(29 if height <= 1100 else 32)
    cta_y = min(max(y, y2 - 168), y2 - 134)
    draw.text((inner_x, cta_y), cta_title, font=cta_font, fill=(215, 255, 232, 250))
    draw.text((inner_x, cta_y + 52), "Open Gaia Eyes for the full signal read.", font=cta_body_font, fill=(232, 239, 248, 226))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(output_path, "PNG")
    return {
        "format": format_name,
        "path": str(output_path),
        "canvas": {"width": size[0], "height": size[1]},
        "asset_source": used_source,
        "video_candidates": spec.get("video_candidates") if isinstance(spec.get("video_candidates"), list) else [],
        "warnings": warnings,
    }


def _render_square(
    draft: Mapping[str, Any],
    *,
    output_path: Path,
    media_base_url: Optional[str],
    local_asset_overrides: Optional[Mapping[str, Path | str]],
) -> Dict[str, Any]:
    return _render_alert_card(
        draft,
        output_path=output_path,
        spec_name="square_image",
        default_size=(1080, 1080),
        format_name="square_image",
        media_base_url=media_base_url,
        local_asset_overrides=local_asset_overrides,
    )


def _render_feed_card(
    draft: Mapping[str, Any],
    *,
    output_path: Path,
    media_base_url: Optional[str],
    local_asset_overrides: Optional[Mapping[str, Path | str]],
) -> Dict[str, Any]:
    return _render_alert_card(
        draft,
        output_path=output_path,
        spec_name="feed_card",
        default_size=(1080, 1350),
        format_name="feed_card",
        media_base_url=media_base_url,
        local_asset_overrides=local_asset_overrides,
    )


def _render_story(
    draft: Mapping[str, Any],
    *,
    output_path: Path,
    media_base_url: Optional[str],
    local_asset_overrides: Optional[Mapping[str, Path | str]],
) -> Dict[str, Any]:
    return _render_alert_card(
        draft,
        output_path=output_path,
        spec_name="story_reel",
        default_size=(1080, 1920),
        format_name="story_reel_frame",
        media_base_url=media_base_url,
        local_asset_overrides=local_asset_overrides,
    )


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
        feed = _render_feed_card(
            draft,
            output_path=out_dir / f"{stem}-feed.png",
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
                "outputs": [square, feed, story],
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
