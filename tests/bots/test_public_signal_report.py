from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace

from bots.public_signal_report import collector, writer
from bots.public_signal_report.contract import SECTION_ORDER, validate_report_contract
from bots.public_signal_report.regions import PUBLIC_SIGNAL_ANCHORS
from bots.public_signal_report.report import build_daily_signal_report
from bots.public_signal_report.shadow import run


def _observation(
    anchor_id: str,
    *,
    region_key: str = "test_region",
    region_label: str = "Test Region",
    condition_code: int = 800,
    pressure_delta: float | None = None,
    weather_ok: bool = True,
) -> dict:
    return {
        "anchor_id": anchor_id,
        "region_key": region_key,
        "region_label": region_label,
        "macro_region": "Test Macro",
        "location_label": anchor_id.title(),
        "weather": {
            "condition_code": condition_code,
            "pressure_delta_24h_hpa": pressure_delta,
            "temp_c": 22,
        },
        "air": {"openweather_aqi": 1},
        "pollen": {},
        "provider_status": {"weather": weather_ok, "air": True, "pollen": False},
    }


def _context() -> dict:
    return {
        "space": {"kp_max": 2.0, "bz_min": -2.0, "sw_speed_avg": 360},
        "schumann": {"day": "2026-07-14", "quality": "ok"},
        "ulf": {"context_class": "quiet", "confidence_score": 0.8},
        "hazards": [],
    }


def test_region_registry_has_three_anchors_across_40_regions() -> None:
    counts: dict[str, int] = {}
    for anchor in PUBLIC_SIGNAL_ANCHORS:
        counts[anchor.region_key] = counts.get(anchor.region_key, 0) + 1

    assert len(PUBLIC_SIGNAL_ANCHORS) == 120
    assert len(counts) == 40
    assert set(counts.values()) == {3}


def test_report_requires_correlated_regional_driver_and_preserves_flow() -> None:
    observations = [
        _observation("alpha", pressure_delta=-6),
        _observation("bravo", pressure_delta=-5),
        _observation("charlie"),
        _observation("lone", region_key="single", region_label="Single Region", condition_code=211),
    ]

    report = build_daily_signal_report(
        day="2026-07-14",
        observations=observations,
        context=_context(),
        expected_anchor_count=120,
        generated_at=datetime(2026, 7, 14, tzinfo=timezone.utc),
    )

    assert report["section_order"] == list(SECTION_ORDER)
    assert report["auto_publish"] is False
    assert validate_report_contract(report) == []
    assert [item["region_key"] for item in report["regional_watch"]["items"]] == ["test_region"]
    assert report["regional_watch"]["items"][0]["drivers"][0]["key"] == "pressure_swings"
    assert report["space_watch"]["signal_strength"] == "low"
    assert report["space_watch"]["recovery_frame"] is True
    assert report["coverage"]["public_global_claims_allowed"] is False


def test_global_claim_gate_requires_75_percent_weather_coverage() -> None:
    observations = [_observation(f"anchor-{index}") for index in range(90)]
    report = build_daily_signal_report(
        day="2026-07-14",
        observations=observations,
        context=_context(),
        expected_anchor_count=120,
    )

    assert report["coverage"]["weather_ratio"] == 0.75
    assert report["coverage"]["public_global_claims_allowed"] is True


def test_major_events_filters_info_deduplicates_and_keeps_newest_tie_order() -> None:
    context = _context()
    context["hazards"] = [
        {"source": "gdacs", "kind": "cyclone", "title": "Orange newer event", "severity": "orange", "started_at": "2026-07-14T10:00:00Z", "payload": {"id": "event-1"}},
        {"source": "gdacs", "kind": "cyclone", "title": "Orange older event", "severity": "orange", "started_at": "2026-07-14T08:00:00Z", "payload": {"id": "event-2"}},
        {"source": "gdacs", "kind": "cyclone", "title": "Orange duplicate impact band", "severity": "orange", "started_at": "2026-07-14T10:00:00Z", "payload": {"id": "event-1"}},
        {"source": "gdacs", "kind": "quake", "title": "Green earthquake", "severity": "red", "payload": {"id": "event-3"}},
        {"source": "usgs", "kind": "earthquake", "title": "Informational", "severity": "info"},
    ]

    report = build_daily_signal_report(day="2026-07-14", observations=[], context=context)

    assert [item["title"] for item in report["major_events"]["items"]] == [
        "Orange newer event",
        "Orange older event",
    ]


def test_collector_parses_provider_rows_and_previous_day_deltas(monkeypatch) -> None:
    async def fake_get_json(_client, url, params):
        if "air_pollution" in url:
            return {"list": [{"main": {"aqi": 3}, "components": {"pm2_5": 41.2}}]}
        return {
            "dt": 1784030400,
            "main": {"temp": 30, "feels_like": 33, "pressure": 1002, "humidity": 72},
            "wind": {"speed": 4, "gust": 7},
            "weather": [{"id": 211, "main": "Thunderstorm", "description": "thunderstorm"}],
            "rain": {"1h": 8},
        }

    monkeypatch.setattr(collector, "_get_json", fake_get_json)
    row = asyncio.run(
        collector.collect_anchor_observation(
            object(),
            PUBLIC_SIGNAL_ANCHORS[0],
            openweather_key="test",
            previous={"weather": {"temp_c": 23, "pressure_hpa": 1009}},
        )
    )

    assert row["weather"]["temp_delta_24h_c"] == 7.0
    assert row["weather"]["pressure_delta_24h_hpa"] == -7.0
    assert row["air"]["openweather_aqi"] == 3
    assert row["provider_status"] == {"weather": True, "air": True, "pollen": None}


def test_writer_uses_structured_report_and_no_voiceover_cta(monkeypatch) -> None:
    captured: dict = {}
    output = {
        "headline": "A calmer sky, but regional shifts still matter",
        "quick_read": "A short read.",
        "facebook": "Facebook copy",
        "instagram": "Instagram copy",
        "voiceover": "Voiceover copy",
        "section_copy": {
            "regional_watch": "Regional",
            "space_watch": "Space",
            "earth_signal": "Earth",
            "major_events": [],
        },
    }

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(output)))])

    class FakeOpenAI:
        def __init__(self, *, api_key):
            assert api_key == "test-key"
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(writer, "OpenAI", FakeOpenAI)
    result = writer.generate_platform_copy(_context(), api_key="test-key", model="test-model")

    assert result["status"] == "generated"
    assert "Voiceover must not include a CTA" in captured["messages"][0]["content"]
    assert "public_global_claims_allowed" in captured["messages"][0]["content"]
    assert captured["response_format"] == {"type": "json_object"}


def test_shadow_fixture_writes_review_only_bundle(tmp_path) -> None:
    observations_path = tmp_path / "observations.json"
    context_path = tmp_path / "context.json"
    output_path = tmp_path / "report.json"
    observations_path.write_text(json.dumps([_observation("alpha"), _observation("bravo")]))
    context_path.write_text(json.dumps(_context()))
    args = argparse.Namespace(
        date="2026-07-14",
        output=str(output_path),
        observations_fixture=str(observations_path),
        context_fixture=str(context_path),
        previous=None,
        anchor_limit=0,
        concurrency=2,
        no_writer=True,
    )

    asyncio.run(run(args))
    bundle = json.loads(output_path.read_text())

    assert bundle["auto_publish"] is False
    assert bundle["report"]["auto_publish"] is False
    assert bundle["copy_runtime"] == {"status": "not_generated", "reason": "--no-writer"}
    assert bundle["review_inputs"]["observation_count"] == 2
