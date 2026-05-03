from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bots.social_alerts.shadow_drafts as shadow_drafts
from bots.social_alerts.shadow_drafts import (
    build_review_markdown,
    build_shadow_payload,
    write_shadow_payload,
    write_shadow_review_markdown,
)


def _categories(payload: dict) -> set[str]:
    return {draft["category"] for draft in payload["drafts"]}


def test_build_shadow_payload_generates_reviewable_drafts_without_publish() -> None:
    payload = build_shadow_payload(
        {
            "generated_at": "2026-04-27T15:00:00Z",
            "space_weather": {
                "now": {"kp": 5.6, "bz_nt": -8.4, "solar_wind_kms": 575},
                "xray_max_class": "M5.6",
            },
            "schumann": {"zscore_30d": 3.2, "combined": {"f1_hz": 7.91}},
            "local": {
                "air": {"aqi": 124},
                "allergens": {"overall_level": "high", "overall_index": 4.2, "primary_label": "Tree pollen"},
            },
            "quakes": {"events": [{"mag": 6.4, "place": "South Sandwich Islands", "time_utc": "2026-04-27T13:30:00Z"}]},
        },
        generated_at="2026-04-27T15:05:00Z",
    )

    assert payload["schema_version"] == "social_alerts_shadow_v1"
    assert payload["mode"] == "shadow"
    assert payload["auto_publish"] is False
    assert payload["draft_count"] >= 4
    assert {"geomagnetic", "solar_flare", "schumann", "earthquake"} <= _categories(payload)
    assert "air_quality" not in _categories(payload)
    assert "pollen" not in _categories(payload)

    for draft in payload["drafts"]:
        assert draft["mode"] == "shadow"
        assert draft["auto_publish"] is False
        assert draft["review_status"] == "needs_human_review"
        assert draft["overlay_spec"]["rendering_status"] == "spec_only"
        assert draft["overlay_spec"]["square_image"]["canvas"] == {"width": 1080, "height": 1080}
        assert draft["overlay_spec"]["story_reel"]["canvas"] == {"width": 1080, "height": 1920}


def test_shadow_copy_stays_conservative_and_contextual() -> None:
    payload = build_shadow_payload(
        {
            "space_weather": {"now": {"kp": 6.4, "bz_nt": -10.0, "solar_wind_kms": 660}},
            "local": {"air": {"aqi": 172}},
        }
    )

    joined = " ".join(draft["caption"].lower() for draft in payload["drafts"])
    assert "context only" not in joined
    assert "not medical advice" not in joined
    assert "forecast of symptoms" not in joined
    assert "cause" not in joined
    assert "cure" not in joined
    assert "treat" not in joined
    assert "guarantee" not in joined


def test_geomagnetic_kp_thresholds_use_watch_at_3_5_and_high_at_5() -> None:
    watch_payload = build_shadow_payload({"space_weather": {"now": {"kp": 3.5}}})
    high_payload = build_shadow_payload({"space_weather": {"now": {"kp": 5.0}}})

    watch = next(draft for draft in watch_payload["drafts"] if draft["category"] == "geomagnetic")
    high = next(draft for draft in high_payload["drafts"] if draft["category"] == "geomagnetic")

    assert watch["severity"] == "watch"
    assert high["severity"] == "high"


def test_background_candidates_reuse_viral_bot_picker(monkeypatch) -> None:
    def fake_candidate(kind: str) -> str:
        return f"media_repo:backgrounds/{kind}/picked.jpg"

    monkeypatch.setattr(shadow_drafts, "_viral_background_candidate", fake_candidate)

    payload = build_shadow_payload({"space_weather": {"now": {"kp": 3.5}}})
    draft = payload["drafts"][0]

    assert draft["overlay_spec"]["square_image"]["background_candidates"][:2] == [
        "media_repo:backgrounds/square/picked.jpg",
        "media_repo:backgrounds/tall/picked.jpg",
    ]
    assert (
        draft["overlay_spec"]["square_image"]["background_source"]
        == "bots.earthscope_post.gaia_eyes_viral_bot._choose_background"
    )


def test_write_shadow_payload_writes_json(tmp_path: Path) -> None:
    payload = build_shadow_payload({"space_weather": {"now": {"kp": 3.5}}})
    out_path = write_shadow_payload(payload, tmp_path / "social-alerts.json")

    assert out_path.exists()
    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert written["mode"] == "shadow"
    assert written["drafts"][0]["category"] == "geomagnetic"


def test_review_markdown_is_human_scannable(tmp_path: Path) -> None:
    payload = build_shadow_payload(
        {
            "generated_at": "2026-04-27T15:00:00Z",
            "space_weather": {"now": {"kp": 5.0, "bz_nt": -5.4, "solar_wind_kms": 560}},
        },
        generated_at="2026-04-27T15:05:00Z",
    )

    markdown = build_review_markdown(payload)
    assert "# Social Alerts Shadow Review" in markdown
    assert "Auto publish: `False`" in markdown
    assert "Geomagnetic storm watch" in markdown
    assert "```text" in markdown
    assert "Context only" not in markdown
    assert "not medical advice" not in markdown

    out_path = write_shadow_review_markdown(payload, tmp_path / "social-alerts.md")
    assert out_path.exists()
    assert "Background candidates:" in out_path.read_text(encoding="utf-8")
