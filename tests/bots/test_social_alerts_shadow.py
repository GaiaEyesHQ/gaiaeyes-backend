from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bots.social_alerts.shadow_drafts as shadow_drafts
from bots.social_alerts.shadow_drafts import (
    CTA,
    CTA_BY_CATEGORY,
    CME_HOOKS,
    MAX_CONTEXT_CHIPS,
    SCHUMANN_ALERT_CHIPS,
    SCHUMANN_HOOKS,
    SIGNAL_FOOTERS,
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
                "cmes_count": 1,
                "cmes_max_speed_kms": 720,
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
    assert {"geomagnetic", "solar_flare", "cme", "schumann"} <= _categories(payload)
    assert "air_quality" not in _categories(payload)
    assert "pollen" not in _categories(payload)
    assert "earthquake" not in _categories(payload)
    assert "global_hazard" not in _categories(payload)

    for draft in payload["drafts"]:
        assert draft["mode"] == "shadow"
        assert draft["auto_publish"] is False
        assert draft["review_status"] == "needs_human_review"
        assert draft["overlay_spec"]["rendering_status"] == "spec_only"
        assert draft["overlay_spec"]["square_image"]["canvas"] == {"width": 1080, "height": 1080}
        assert draft["overlay_spec"]["feed_card"]["canvas"] == {"width": 1080, "height": 1350}
        assert draft["overlay_spec"]["story_reel"]["canvas"] == {"width": 1080, "height": 1920}


def test_shadow_copy_stays_conservative_and_contextual() -> None:
    payload = build_shadow_payload(
        {
            "space_weather": {
                "now": {"kp": 6.4, "bz_nt": -10.0, "solar_wind_kms": 660},
                "xray_max_class": "M5.6",
                "cmes_count": 1,
            },
            "local": {"air": {"aqi": 172}},
        }
    )

    joined = " ".join(draft["caption"].lower() for draft in payload["drafts"])
    assert "context only" not in joined
    assert "not giving medical advice" in joined
    assert "affect you" not in joined
    assert "windows like this" not in joined
    assert "pattern recognition app" in joined
    assert "forecast of symptoms" not in joined
    assert "cause" not in joined
    assert "cure" not in joined
    assert "treat" not in joined
    assert "guarantee" not in joined
    assert "guessing" not in joined


def test_space_alerts_keep_health_pattern_context() -> None:
    payload = build_shadow_payload(
        {
            "space_weather": {
                "now": {"kp": 4.2, "bz_nt": -4.0, "solar_wind_kms": 455},
                "cmes_count": 1,
            },
        }
    )

    drafts = {draft["category"]: draft for draft in payload["drafts"]}
    for category in ("geomagnetic", "cme"):
        draft = drafts[category]
        square = draft["overlay_spec"]["square_image"]
        assert CTA_BY_CATEGORY[category] in draft["overlay_spec"]["story_reel"]["frames"][-1]["text"]
        assert "full signal read" not in draft["caption"]
        assert "before posting" not in draft["subtitle"].lower()
        assert "review" not in draft["subtitle"].lower()
        assert "before posting" not in square["subtitle"].lower()
        assert "review" not in square["subtitle"].lower()
        assert {"Sleep", "HRV"} <= set(square["context_chips"])
        assert len(square["context_chips"]) <= MAX_CONTEXT_CHIPS

    cme_caption = drafts["cme"]["caption"]
    assert drafts["cme"]["title"] in {hook for hooks in CME_HOOKS.values() for hook in hooks}
    assert drafts["cme"]["title"] in {
        "Feeling drained today?",
        "Moving in slow motion today?",
        "Battery on empty today?",
        "Nerves on overdrive?",
        "Feeling restless today?",
        "Pain level worse today?",
    }
    assert "Feeling off today?" not in cme_caption
    assert "Recovery feeling off?" not in cme_caption
    assert "Body signals look noisier today." not in cme_caption
    assert "The sun influences more than we think." not in cme_caption
    assert "A CME is a huge cloud from the Sun." in cme_caption
    assert "kind of like wind shaking a tree" in cme_caption
    assert "Researchers have studied solar and geomagnetic activity alongside HRV" in cme_caption
    assert "The science is still developing, but the question is exactly why Gaia Eyes exists" in cme_caption
    assert "One day is a note. Repeated overlaps become a pattern." in cme_caption
    assert "Use Gaia Eyes as a recovery log:" in cme_caption
    assert "health conditions feel unusual" in cme_caption
    assert "Gaia Eyes is a pattern recognition app and is not giving medical advice." in cme_caption
    assert "alongside the CME signal" not in cme_caption
    assert CTA_BY_CATEGORY["cme"] in cme_caption
    assert "https://GaiaEyes.com/app" in cme_caption
    assert "Gaia Eyes compares symptoms, wearables, exposures, and environmental signals over time." not in cme_caption
    assert "CME activity is elevated" not in cme_caption
    assert "CME activity is present" not in cme_caption
    assert "instead of guessing" not in cme_caption
    assert "log it so patterns are easier to compare later" in drafts["cme"]["subtitle"]
    assert drafts["cme"]["overlay_spec"]["square_image"]["metric_chips"] == []
    assert "Recovery" not in drafts["cme"]["overlay_spec"]["square_image"]["context_chips"]

    geomagnetic_caption = drafts["geomagnetic"]["caption"]
    assert geomagnetic_caption.startswith(f"{drafts['geomagnetic']['title']}\n\nGeomagnetic activity is elevated right now")
    assert "The science is still developing, but the question is exactly why Gaia Eyes exists" in geomagnetic_caption
    assert "If your body feels louder than normal today" in geomagnetic_caption
    assert "health conditions are the kinds of patterns Gaia Eyes can help you compare" in geomagnetic_caption
    assert geomagnetic_caption.count("sleep") == 1


def test_schumann_caption_includes_brief_public_explainer_and_app_cta() -> None:
    payload = build_shadow_payload({"schumann": {"zscore_30d": 3.2, "combined": {"f1_hz": 7.91}}})
    schumann = next(draft for draft in payload["drafts"] if draft["category"] == "schumann")

    assert "Schumann resonance is part of Earth's natural electromagnetic background." in schumann["caption"]
    assert "HeartMath and other researchers have studied Schumann resonance" in schumann["caption"]
    assert "The science is still developing, but the question is exactly why Gaia Eyes exists" in schumann["caption"]
    assert "Use Gaia Eyes as a body-pattern log:" in schumann["caption"]
    assert "health conditions" in schumann["caption"]
    assert "Gaia Eyes is a pattern recognition app and is not giving medical advice." in schumann["caption"]
    assert CTA_BY_CATEGORY["schumann"] in schumann["caption"]


def test_space_alert_ctas_vary_by_category_without_changing_app_link() -> None:
    payload = build_shadow_payload(
        {
            "space_weather": {
                "now": {"kp": 6.4, "bz_nt": -10.0, "solar_wind_kms": 660},
                "xray_max_class": "M5.6",
                "cmes_count": 1,
            },
            "schumann": {"zscore_30d": 3.2, "combined": {"f1_hz": 7.91}},
        }
    )

    ctas = []
    for draft in payload["drafts"]:
        frames = draft["overlay_spec"]["story_reel"]["frames"]
        cta = next(frame["text"] for frame in frames if frame["role"] == "cta")
        ctas.append(cta)
        assert "https://GaiaEyes.com/app" in cta
        assert cta in draft["caption"]

    assert len(set(ctas)) >= 3


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

    assert draft["overlay_spec"]["square_image"]["background_candidates"][:4] == [
        "social/share/backgrounds/space_weather.jpg",
        "social/share/backgrounds/kp.jpg",
        "social/share/backgrounds/bz.jpg",
        "social/share/backgrounds/solar_wind.jpg",
    ]
    assert "media_repo:backgrounds/square/picked.jpg" in draft["overlay_spec"]["square_image"]["background_candidates"]
    assert "media_repo:backgrounds/tall/picked.jpg" in draft["overlay_spec"]["square_image"]["background_candidates"]
    assert "bootstrap:social_alerts/solar_aurora" in draft["overlay_spec"]["square_image"]["background_candidates"]
    assert draft["overlay_spec"]["square_image"]["background_keywords"] == [
        "space_weather",
        "kp",
        "bz",
        "solar_wind",
    ]
    assert draft["overlay_spec"]["square_image"]["visual_style"]["layout"] == "trust_first_alert_card"
    assert "bootstrap:social_alerts generated pack" in draft["overlay_spec"]["square_image"]["background_source"]
    assert draft["overlay_spec"]["square_image"]["background_prompts"]


def test_known_media_assets_are_attached_to_reel_specs() -> None:
    payload = build_shadow_payload(
        {
            "space_weather": {"xray_max_class": "X1.2", "cmes_count": 1, "cmes_max_speed_kms": 720},
            "schumann": {"zscore_30d": 3.2, "combined": {"f1_hz": 7.91}},
        }
    )

    drafts = {draft["category"]: draft for draft in payload["drafts"]}
    flare_reel = drafts["solar_flare"]["overlay_spec"]["story_reel"]
    flare_square = drafts["solar_flare"]["overlay_spec"]["square_image"]
    cme_reel = drafts["cme"]["overlay_spec"]["story_reel"]
    schumann_square = drafts["schumann"]["overlay_spec"]["square_image"]

    assert flare_reel["video_candidates"] == ["nasa/ccor1/latest.mp4", "nasa/enlil/latest.mp4"]
    assert "bootstrap:social_alerts/solar_heat" in flare_square["background_candidates"]
    assert cme_reel["video_candidates"] == ["nasa/ccor1/latest.mp4", "nasa/enlil/latest.mp4"]
    assert "nasa/ccor1/latest.jpg" in flare_reel["still_candidates"]
    assert "nasa/enlil/latest.jpg" in cme_reel["still_candidates"]
    assert schumann_square["still_candidates"] == [
        "schumann/latest/tomsk_share_latest.jpg",
        "social/earthscope/latest/tomsk_share_latest.jpg",
    ]
    assert schumann_square["background_candidates"][:2] == [
        "social/share/backgrounds/schumann.jpg",
        "social/share/backgrounds/earthscope.jpg",
    ]
    assert "bootstrap:social_alerts/resonance_field" in schumann_square["background_candidates"]


def test_schumann_alert_uses_human_first_trust_copy() -> None:
    payload = build_shadow_payload(
        {"schumann": {"zscore_30d": 3.2, "combined": {"f1_hz": 7.91}}},
        generated_at="2026-04-30T12:05:00Z",
    )

    draft = next(draft for draft in payload["drafts"] if draft["category"] == "schumann")
    square = draft["overlay_spec"]["square_image"]

    assert draft["title"] in SCHUMANN_HOOKS
    assert "compare" in draft["subtitle"].lower() or "worth comparing" in draft["subtitle"].lower()
    assert "Schumann resonance is part of Earth's natural electromagnetic background." in draft["caption"]
    assert square["label"] == "HEALTH WATCH"
    assert square["context_chips"] == SCHUMANN_ALERT_CHIPS
    assert square["footer"] == SIGNAL_FOOTERS["schumann"]
    assert len(square["context_chips"]) <= MAX_CONTEXT_CHIPS
    assert len(square["metric_chips"]) <= 2
    joined = json.dumps(draft).lower()
    assert "causing" not in joined
    assert "spike detected" not in joined
    assert "danger" not in joined
    assert "warning" not in joined
    assert "impacting you" not in joined


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
    assert any(hook in markdown for hooks in shadow_drafts.GEOMAGNETIC_HOOKS.values() for hook in hooks)
    assert "Post caption copy:" in markdown
    assert "```text" in markdown
    assert "Context only" not in markdown
    assert "not medical advice" not in markdown

    out_path = write_shadow_review_markdown(payload, tmp_path / "social-alerts.md")
    assert out_path.exists()
    written = out_path.read_text(encoding="utf-8")
    assert (tmp_path / "latest-review.md").read_text(encoding="utf-8") == written
    assert "Background candidates:" in written
    assert "bootstrap:social_alerts/solar_aurora" in written
    assert "Background keywords:" in written
    assert "Visual style:" in written
