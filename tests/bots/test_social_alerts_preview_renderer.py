from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bots.social_alerts.preview_renderer import render_shadow_previews, resolve_background_image
from bots.social_alerts.shadow_drafts import build_shadow_payload


def _write_image(path: Path, color: tuple[int, int, int]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (1280, 1280), color)
    image.save(path, "PNG")
    return path


def test_render_shadow_previews_for_schumann_flare_and_cme(tmp_path: Path) -> None:
    payload = build_shadow_payload(
        {
            "generated_at": "2026-04-30T12:00:00Z",
            "space_weather": {"xray_max_class": "X1.2", "cmes_count": 1, "cmes_max_speed_kms": 720},
            "schumann": {"zscore_30d": 3.2, "combined": {"f1_hz": 7.91}},
        },
        generated_at="2026-04-30T12:05:00Z",
    )
    out_dir = tmp_path / "previews"
    assets = {
        "schumann/latest/tomsk_share_latest.jpg": _write_image(tmp_path / "tomsk.png", (18, 90, 82)),
        "nasa/ccor1/latest.jpg": _write_image(tmp_path / "ccor.png", (180, 72, 22)),
        "nasa/enlil/latest.jpg": _write_image(tmp_path / "enlil.png", (20, 64, 126)),
    }

    manifest = render_shadow_previews(
        payload,
        out_dir,
        categories={"schumann", "solar_flare", "cme"},
        local_asset_overrides=assets,
    )

    assert manifest["schema_version"] == "social_alerts_preview_v1"
    assert manifest["mode"] == "shadow"
    assert manifest["auto_publish"] is False
    assert manifest["rendered_count"] == 3
    assert (out_dir / "preview-manifest.json").exists()

    written = json.loads((out_dir / "preview-manifest.json").read_text(encoding="utf-8"))
    assert written["rendered_count"] == 3
    formats = []
    for rendered in manifest["rendered"]:
        for output in rendered["outputs"]:
            path = Path(output["path"])
            assert path.exists()
            with Image.open(path) as image:
                assert image.size in {(1080, 1080), (1080, 1350), (1080, 1920)}
            formats.append(output["format"])
    assert formats.count("square_image") == 3
    assert formats.count("feed_card") == 3
    assert formats.count("story_reel_frame") == 3


def test_resolve_background_uses_local_override_before_remote(tmp_path: Path) -> None:
    local_image = _write_image(tmp_path / "local.png", (24, 80, 140))

    image, source, warnings = resolve_background_image(
        ["nasa/ccor1/latest.jpg"],
        category="solar_flare",
        size=(1080, 1080),
        media_base_url="https://example.invalid/space-visuals",
        local_asset_overrides={"nasa/ccor1/latest.jpg": local_image},
    )

    assert image.size == (1280, 1280)
    assert source == "nasa/ccor1/latest.jpg"
    assert warnings == []


def test_resolve_background_generates_fallback_when_candidates_fail() -> None:
    image, source, warnings = resolve_background_image(
        ["media_repo:missing/asset.jpg"],
        category="cme",
        size=(1080, 1080),
    )

    assert image.size == (1080, 1080)
    assert source == "generated:fallback_gradient"
    assert warnings
