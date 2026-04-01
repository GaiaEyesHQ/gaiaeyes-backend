import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.mc_modals.modal_builder import build_earthscope_semantic_payload, render_earthscope_summary
from services.voice.profiles import VoiceProfile


def test_public_playful_voice_profile_defaults() -> None:
    profile = VoiceProfile.public_playful()

    assert profile.mode == "scientific"
    assert profile.tone == "humorous"
    assert profile.channel == "social_public"
    assert profile.humor_enabled is True
    assert profile.caution_line() == "Watch the pattern, not the panic."


def test_build_earthscope_semantic_payload_shapes_guardrails() -> None:
    payload = build_earthscope_semantic_payload(
        day=date(2026, 2, 27),
        gauges={"pain": 88, "sleep": 74},
        gauges_meta={
            "pain": {"zone": "high", "label": "Flare"},
            "sleep": {"zone": "elevated", "label": "Disrupted"},
        },
        gauge_labels={"pain": "Pain", "sleep": "Sleep"},
        drivers=[
            {"key": "pressure", "label": "Pressure Swing", "severity": "high", "state": "High"},
            {"key": "sw", "label": "Solar Wind", "severity": "elevated", "state": "Elevated"},
        ],
        user_tags=["fibromyalgia"],
        personal_relevance={
            "primary_driver": {
                "key": "pressure",
                "label": "Pressure Swing",
                "confidence": "Moderate",
                "personal_reason_short": "Pressure often matches your pain pattern.",
            }
        },
    )

    assert payload.schema_version == "1.0"
    assert payload.kind == "earthscope_summary"
    assert payload.guardrails.confidence_overall == "moderate"
    assert payload.guardrails.claim_strength == "may_notice"
    assert payload.guardrails.avoid_fear_language is True
    assert payload.guardrails.max_urgency in {"watch", "high"}
    assert payload.interpretation["primary_driver"]["key"] == "pressure"


def test_render_earthscope_summary_uses_voice_profile_caution_line() -> None:
    payload = build_earthscope_semantic_payload(
        day=date(2026, 2, 27),
        gauges={"pain": 88},
        gauges_meta={"pain": {"zone": "high", "label": "Flare"}},
        gauge_labels={"pain": "Pain"},
        drivers=[
            {"key": "pressure", "label": "Pressure Swing", "severity": "high", "state": "High"},
        ],
        personal_relevance=None,
    )

    rendered = render_earthscope_summary(
        payload,
        user_id="user-123",
        voice_profile=VoiceProfile.public_playful(),
    )

    assert "Watch the pattern, not the panic." in rendered
