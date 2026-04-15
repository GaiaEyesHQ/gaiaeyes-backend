#!/usr/bin/env python3
"""Create square social-share crops from Schumann overlay images.

The crop is anchored to the extractor's current-time pick. The right edge is
`now + margin`, then the square is resized for app/social usage.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Optional, Tuple

from PIL import Image

RESAMPLE_LANCZOS = getattr(getattr(Image, "Resampling", Image), "LANCZOS")


def _as_float(value: Any) -> Optional[float]:
    try:
        if value is None or isinstance(value, bool):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _load_payload(path: Optional[str]) -> dict[str, Any]:
    if not path:
        return {}
    payload_path = Path(path)
    if not payload_path.exists():
        return {}
    with payload_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def _anchor_x(payload: dict[str, Any], image_width: int) -> Tuple[float, str]:
    raw = payload.get("raw") if isinstance(payload.get("raw"), dict) else {}
    debug = raw.get("debug") if isinstance(raw.get("debug"), dict) else {}

    candidates: list[tuple[str, Any]] = [
        ("raw.debug.x_now", debug.get("x_now")),
        ("raw.x_now_pixel", raw.get("x_now_pixel")),
    ]

    if bool(debug.get("guard_applied")):
        candidates.append(("raw.debug.right_guard", debug.get("right_guard")))

    candidates.extend(
        [
            ("raw.debug.x_ideal", debug.get("x_ideal")),
            ("raw.debug.x_time", debug.get("x_time")),
            ("raw.debug.right_guard", debug.get("right_guard")),
        ]
    )

    frontier = _as_float(debug.get("x_frontier"))
    guard = _as_float(debug.get("guard_px"))
    if frontier is not None:
        candidates.append(
            (
                "raw.debug.x_frontier-minus-guard",
                frontier - (guard if guard is not None else 0.0),
            )
        )

    for source, value in candidates:
        number = _as_float(value)
        if number is not None:
            return max(0.0, min(float(image_width - 1), number)), source

    return float(image_width - 1), "image.right"


def _pixels_per_hour(payload: dict[str, Any]) -> Optional[float]:
    raw = payload.get("raw") if isinstance(payload.get("raw"), dict) else {}
    debug = raw.get("debug") if isinstance(raw.get("debug"), dict) else {}
    groups = raw.get("group_boundaries_px") if isinstance(raw.get("group_boundaries_px"), dict) else {}

    for value in (
        debug.get("pph"),
        _as_float(groups.get("day_w_time")) / 24.0 if _as_float(groups.get("day_w_time")) else None,
        _as_float(groups.get("day_w")) / 24.0 if _as_float(groups.get("day_w")) else None,
    ):
        number = _as_float(value)
        if number is not None and number > 0:
            return number
    return None


def build_share_crop(
    image_path: str,
    json_path: Optional[str],
    out_path: str,
    *,
    output_size: int,
    right_margin_minutes: float,
    right_margin_px: Optional[int],
    jpeg_quality: int,
) -> dict[str, Any]:
    payload = _load_payload(json_path)
    with Image.open(image_path) as source:
        image = source.convert("RGB")

    anchor, anchor_source = _anchor_x(payload, image.width)
    pph = _pixels_per_hour(payload)
    margin_px = float(right_margin_px) if right_margin_px is not None else (
        pph * (right_margin_minutes / 60.0) if pph is not None else 32.0
    )

    side = min(image.width, image.height)
    right = int(round(anchor + margin_px))
    right = max(side, min(image.width, right))
    left = right - side

    if image.height > side:
        top = max(0, (image.height - side) // 2)
    else:
        top = 0
    bottom = top + side

    crop = image.crop((left, top, right, bottom))
    if output_size != side:
        crop = crop.resize((output_size, output_size), RESAMPLE_LANCZOS)

    output = Path(out_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    crop.save(output, format="JPEG", quality=jpeg_quality, optimize=True)

    return {
        "ok": True,
        "image": image_path,
        "json": json_path,
        "out": out_path,
        "source_size": [image.width, image.height],
        "crop_box": [left, top, right, bottom],
        "anchor_x": anchor,
        "anchor_source": anchor_source,
        "right_margin_px": margin_px,
        "right_margin_minutes": right_margin_minutes if right_margin_px is None else None,
        "pph": pph,
        "output_size": output_size,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a square social crop for Schumann share cards.")
    parser.add_argument("--image", required=True, help="Input overlay image.")
    parser.add_argument("--json", default=None, help="Extractor JSON with current-time debug coordinates.")
    parser.add_argument("--out", required=True, help="Output JPG path.")
    parser.add_argument("--size", type=int, default=1080, help="Output square size in pixels.")
    parser.add_argument("--right-margin-minutes", type=float, default=90.0, help="Time margin to include right of now.")
    parser.add_argument("--right-margin-px", type=int, default=None, help="Pixel margin to include right of now.")
    parser.add_argument("--quality", type=int, default=86, help="JPEG quality.")
    args = parser.parse_args()

    result = build_share_crop(
        args.image,
        args.json,
        args.out,
        output_size=max(256, int(args.size)),
        right_margin_minutes=float(args.right_margin_minutes),
        right_margin_px=args.right_margin_px,
        jpeg_quality=max(1, min(95, int(args.quality))),
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
