from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from bots.public_signal_report import reel_renderer


def _bundle() -> dict:
    return {
        "auto_publish": False,
        "report": {
            "day": "2026-07-19",
            "edition": "us",
            "public_name": "Gaia Eyes U.S. Health Snapshot",
            "auto_publish": False,
            "platform_copy": {
                "reel_story": {
                    "hook": "Feeling heavy and slow today?",
                    "where": "The strongest signals centered on the Desert Southwest, Mountain West, and Southern Plains.",
                    "drivers": "Heat and humidity were the primary sampled drivers across these regions.",
                    "effects": "Some people may notice fatigue or sleep disruption under these conditions.",
                    "summary": {
                        "regional": "Heat and humidity lead regionally today.",
                        "space": "Space weather remains low today.",
                        "earth": "Earth measurements show a Quiet ULF pattern.",
                        "major_event": "",
                    },
                }
            },
        },
    }


def _backgrounds(path: Path) -> Path:
    colors = (
        (36, 102, 145),
        (98, 52, 112),
        (35, 118, 78),
        (136, 72, 34),
        (42, 66, 122),
    )
    for index, color in enumerate(colors, start=1):
        image = Image.new("RGB", (1200, 2000), color)
        image.save(path / f"health_snapshot_{index}.jpg")
    return path


def test_renderer_rejects_global_or_publishable_input(tmp_path) -> None:
    bundle = _bundle()
    bundle["report"]["edition"] = "global"

    with pytest.raises(ValueError, match="U.S. Health Snapshot edition"):
        reel_renderer._validate_input(bundle)

    bundle = _bundle()
    bundle["auto_publish"] = True
    with pytest.raises(ValueError, match="shadow-only"):
        reel_renderer._validate_input(bundle)


def test_five_slides_use_distinct_blank_backgrounds_and_keep_text_safe(tmp_path) -> None:
    background_dir = tmp_path / "backgrounds"
    background_dir.mkdir()
    _backgrounds(background_dir)
    output_dir = tmp_path / "slides"
    story = _bundle()["report"]["platform_copy"]["reel_story"]
    rendered = []

    for index, (key, label, filename) in enumerate(reel_renderer.SLIDE_SPECS, start=1):
        if key == "summary":
            rendered.append(
                reel_renderer._render_summary_slide(
                    summary=story[key],
                    output_path=output_dir / filename,
                    index=index,
                    background_dir=background_dir,
                )
            )
        else:
            rendered.append(
                reel_renderer._render_slide(
                    text=story[key],
                    label=label,
                    output_path=output_dir / filename,
                    index=index,
                    background_dir=background_dir,
                )
            )

    assert len({slide["background_source"] for slide in rendered}) == 5
    assert len({slide["background_digest"] for slide in rendered}) == 5
    for slide in rendered:
        with Image.open(slide["path"]) as image:
            assert image.size == reel_renderer.CANVAS
        assert " ".join(slide["wrapped_lines"]) == slide["text"]
        left, top, right, bottom = slide["text_bbox"]
        safe_left, safe_top, safe_right, safe_bottom = reel_renderer.SAFE_TEXT_BOX
        assert safe_left <= left < right <= safe_right
        assert safe_top <= top < bottom <= safe_bottom


@pytest.mark.skipif(not reel_renderer._ffmpeg_executable(), reason="ffmpeg required")
def test_full_shadow_reel_passes_visual_preflight(tmp_path) -> None:
    input_path = tmp_path / "us-shadow.json"
    input_path.write_text(json.dumps(_bundle()), encoding="utf-8")
    background_dir = tmp_path / "backgrounds"
    background_dir.mkdir()
    _backgrounds(background_dir)

    manifest = reel_renderer.render_us_health_snapshot_reel(
        input_path,
        tmp_path / "rendered",
        background_dir=background_dir,
    )

    assert manifest["passed"] is True
    assert manifest["errors"] == []
    assert len(manifest["slides"]) == 5
    assert len(manifest["video"]["sampled_frames"]) == 5
    assert manifest["video"]["duration_seconds"] >= 12
    assert (tmp_path / "rendered/us-health-snapshot-preview.mp4").is_file()
    assert (tmp_path / "rendered/preflight-manifest.json").is_file()
