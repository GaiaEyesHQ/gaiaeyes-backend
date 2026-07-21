from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace

from bots.public_signal_report import collector, writer
from bots.public_signal_report.contract import SECTION_ORDER, validate_report_contract
from bots.public_signal_report.regions import PUBLIC_SIGNAL_ANCHORS, US_SIGNAL_ANCHORS
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


def _reel_summary(
    regional: str = "Regional heat leads today.",
    space: str = "Space weather remains low today.",
    earth: str = "Earth measurements remain available today.",
    major_event: str = "",
) -> dict:
    return {
        "regional": regional,
        "space": space,
        "earth": earth,
        "major_event": major_event,
    }


def test_region_registry_has_three_anchors_across_40_regions() -> None:
    counts: dict[str, int] = {}
    for anchor in PUBLIC_SIGNAL_ANCHORS:
        counts[anchor.region_key] = counts.get(anchor.region_key, 0) + 1

    assert len(PUBLIC_SIGNAL_ANCHORS) == 120
    assert len(counts) == 40
    assert set(counts.values()) == {3}
    assert len(US_SIGNAL_ANCHORS) == 42


def test_us_edition_filters_global_regions_and_requires_structured_us_hazard_scope() -> None:
    us_rows = [
        _observation("boston", region_key="us_new_england", region_label="New England", pressure_delta=-6),
        _observation("portland", region_key="us_new_england", region_label="New England", pressure_delta=-5),
    ]
    asia_rows = [
        _observation("tokyo", region_key="east_asia", region_label="East Asia", pressure_delta=-7),
        _observation("seoul", region_key="east_asia", region_label="East Asia", pressure_delta=-6),
    ]
    context = _context()
    context["hazards"] = [
        {
            "source": "gdacs",
            "kind": "fire",
            "title": "Orange U.S. fire",
            "severity": "orange",
            "payload": {"id": "us-fire", "affected_country_codes": ["US"]},
        },
        {
            "source": "gdacs",
            "kind": "earthquake",
            "title": "Orange Philippines earthquake",
            "severity": "orange",
            "payload": {"id": "ph-quake", "country_code": "PH"},
        },
    ]

    report = build_daily_signal_report(
        day="2026-07-19",
        observations=[*us_rows, *asia_rows],
        context=context,
        expected_anchor_count=len(US_SIGNAL_ANCHORS),
        edition="us",
    )

    assert report["public_name"] == "Gaia Eyes U.S. Health Snapshot"
    assert report["geographic_scope"] == "United States"
    assert [item["region_key"] for item in report["regional_watch"]["items"]] == ["us_new_england"]
    assert [item["title"] for item in report["major_events"]["items"]] == ["Orange U.S. fire"]
    assert report["coverage"]["observed_anchors"] == 2
    assert report["coverage"]["expected_anchors"] == 42
    assert report["coverage"]["public_global_claims_allowed"] is False


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


def test_schumann_context_falls_back_when_v2_harmonics_are_null(monkeypatch) -> None:
    rows = iter(
        [
            {"day": "2026-07-15", "f0": None, "f1": None, "f2": None},
            {
                "day": "2026-07-15",
                "f0": 7.37,
                "f1": 7.37,
                "f2": 14.38,
                "stations_used": ["cumiana", "tomsk"],
                "source": "marts.schumann_daily",
            },
        ]
    )
    monkeypatch.setattr(collector, "_fetch_one", lambda _conn, _queries: next(rows))

    result = collector._fetch_schumann_context(object())

    assert result["f0"] == 7.37
    assert result["stations_used"] == ["cumiana", "tomsk"]
    assert result["source"] == "marts.schumann_daily"


def test_writer_marks_normalized_schumann_facts_available() -> None:
    context = _context()
    context["schumann"] = {
        "day": "2026-07-15",
        "f0": 7.37,
        "f1": 7.37,
        "f2": 14.38,
        "stations_used": ["cumiana", "tomsk"],
        "source": "marts.schumann_daily",
    }
    report = build_daily_signal_report(day="2026-07-15", observations=[], context=context)

    earth_facts = writer.writer_payload(report)["facts"]["earth_signal"]

    assert earth_facts["schumann_available"] is True
    assert earth_facts["schumann_values"]["f0"] == 7.37


def test_writer_uses_structured_report_and_no_voiceover_cta(monkeypatch) -> None:
    captured: dict = {}
    output = {
        "headline": "A calmer sky, but regional shifts still matter",
        "quick_read": "A short read.",
        "facebook": " ".join(["Facebook"] * 225),
        "instagram": " ".join(["Instagram"] * 60),
        "voiceover": " ".join(["Voiceover"] * 55),
        "reel_story": {
            "hook": "Head pressure building today?",
            "where": "New England carries the strongest regional signal today.",
            "drivers": "Pressure swings are the leading supported environmental driver.",
            "effects": "Some people may notice headaches or migraine sensitivity.",
            "summary": _reel_summary(),
        },
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
    report = build_daily_signal_report(
        day="2026-07-14",
        observations=[_observation("alpha"), _observation("bravo")],
        context=_context(),
    )
    result = writer.generate_platform_copy(report, api_key="test-key", model="test-model")

    assert result["status"] == "generated"
    assert result["writer_attempts"] == 1
    assert "Voiceover must end on the factual rundown" in captured["messages"][0]["content"]
    assert "public_global_claims_allowed" in captured["messages"][0]["content"]
    assert "recovery_frame is true" in captured["messages"][0]["content"]
    assert "Do not say readings explain why" in captured["messages"][0]["content"]
    assert "Facebook must also open" in captured["messages"][0]["content"]
    assert "no CTA, advice, wellness tip, reflection prompt" in captured["messages"][0]["content"]
    assert "includes an explicit health_context" in captured["messages"][0]["content"]
    assert "not an activity or intensity score" in captured["messages"][0]["content"]
    assert captured["response_format"]["type"] == "json_schema"
    assert captured["response_format"]["json_schema"]["strict"] is True
    assert captured["response_format"]["json_schema"]["schema"]["properties"]["reel_story"]["required"] == [
        "hook",
        "where",
        "drivers",
        "effects",
        "summary",
    ]
    supplied_facts = json.loads(captured["messages"][1]["content"])["facts"]
    assert "source_row" not in supplied_facts["space_watch"]
    assert supplied_facts["space_watch"]["current_metrics"]["current_kp"] is None
    assert supplied_facts["earth_signal"]["ulf"] == {
        "context_class": "quiet",
        "confidence_score": 0.8,
        "regional_intensity": None,
        "regional_coherence": None,
        "regional_persistence": None,
        "stations_used": None,
    }


def test_writer_omits_low_confidence_ulf_measurements() -> None:
    context = _context()
    context["ulf"] = {
        "context_class": "Quiet",
        "confidence_score": 0.146,
        "regional_intensity": 26.34,
    }
    report = build_daily_signal_report(day="2026-07-15", observations=[], context=context)

    facts = writer.writer_payload(report)["facts"]

    assert facts["earth_signal"]["ulf_usable"] is False
    assert facts["earth_signal"]["ulf"] is None
    assert "Do not interpret" in facts["earth_signal"]["unavailable_reason"]


def test_writer_revises_copy_once_when_word_ranges_fail(monkeypatch) -> None:
    short = {
        "headline": "Feeling off?",
        "quick_read": "Short read.",
        "facebook": "Too short",
        "instagram": "Too short",
        "voiceover": "Too short",
        "reel_story": {
            "hook": "Feeling off?",
            "where": "Regions are active today.",
            "drivers": "Pressure is shifting today.",
            "effects": "Some people may notice headaches.",
            "summary": _reel_summary(),
        },
        "section_copy": {
            "regional_watch": "Regional",
            "space_watch": "Space",
            "earth_signal": "Earth",
            "major_events": "Events",
        },
    }
    valid = {
        **short,
        "facebook": " ".join(["Facebook"] * 225),
        "instagram": " ".join(["Instagram"] * 60),
        "voiceover": " ".join(["Voiceover"] * 55),
    }
    calls: list[dict] = []

    class FakeCompletions:
        def create(self, **kwargs):
            calls.append(kwargs)
            output = short if len(calls) == 1 else valid
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(output)))])

    class FakeOpenAI:
        def __init__(self, *, api_key):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(writer, "OpenAI", FakeOpenAI)
    result = writer.generate_platform_copy({}, api_key="test-key", model="test-model")

    assert result["status"] == "generated"
    assert result["writer_attempts"] == 2
    assert len(calls) == 2
    assert "instagram must be 60-110 words" in calls[1]["messages"][-1]["content"]


def test_writer_rejects_fragmented_or_duplicate_reel_story(monkeypatch) -> None:
    invalid = {
        "headline": "Head pressure building?",
        "quick_read": "Short read.",
        "facebook": " ".join(["Facebook"] * 225),
        "instagram": " ".join(["Instagram"] * 60),
        "voiceover": " ".join(["Voiceover"] * 55),
        "reel_story": {
            "hook": "Head pressure building?",
            "where": "Pressure shifts across New England",
            "drivers": "Pressure shifts across New England.",
            "effects": "Some people may notice headaches.",
            "summary": _reel_summary(),
        },
        "section_copy": {
            "regional_watch": "Regional",
            "space_watch": "Space",
            "earth_signal": "Earth",
            "major_events": "Events",
        },
    }
    calls: list[dict] = []

    class FakeCompletions:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(invalid)))])

    class FakeOpenAI:
        def __init__(self, *, api_key):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(writer, "OpenAI", FakeOpenAI)
    result = writer.generate_platform_copy({}, api_key="test-key", model="test-model")

    assert result["status"] == "invalid"
    assert any("complete sentence" in error for error in result["validation_errors"])
    assert any("near-duplicates" in error for error in result["validation_errors"])
    assert len(calls) == 2


def test_writer_validation_rejects_unsupported_signal_comparisons() -> None:
    copy = {
        "headline": "Heat making everything harder?",
        "quick_read": "Schumann frequencies tracked near expected values.",
        "facebook": "Solar wind was modest and steady today.",
        "instagram": "ULF intensity was modest today.",
        "voiceover": "Measured signals are available today.",
        "reel_story": {
            "hook": "Heat making everything harder?",
            "where": "The strongest regional signal centers on the Desert Southwest.",
            "drivers": "Heat and humidity are the leading supported drivers.",
            "effects": "Some people may notice fatigue or lower exercise tolerance.",
            "summary": _reel_summary(),
        },
        "section_copy": {},
    }

    errors = writer._copy_validation_errors(copy, {"major_events": {"items": []}})

    assert "copy gives schumann an unsupported qualitative comparison" in errors
    assert "copy gives ulf an unsupported qualitative comparison" in errors
    assert "copy gives solar wind an unsupported qualitative comparison" in errors


def test_writer_validation_does_not_treat_gulf_as_ulf() -> None:
    copy = {
        "headline": "Heavy air slowing you down?",
        "quick_read": "Heat and humidity were strongest along the Gulf Coast.",
        "facebook": "Heat and humidity were sampled today.",
        "instagram": "Heat and humidity were sampled today.",
        "voiceover": "Heat and humidity were sampled today.",
        "reel_story": {
            "hook": "Heavy air slowing you down?",
            "where": "Heat and humidity were strongest along the Gulf Coast.",
            "drivers": "Heat and humidity were the leading sampled drivers.",
            "effects": "Some people may notice fatigue under these conditions.",
            "summary": _reel_summary(earth="Earth signals use ULF Active (diffuse)."),
        },
        "section_copy": {},
    }

    errors = writer._copy_validation_errors(copy, {"major_events": {"items": []}})

    assert "copy gives ulf an unsupported qualitative comparison" not in errors


def test_writer_validation_rejects_internal_summary_notation() -> None:
    copy = {
        "headline": "Heavy air slowing you down?",
        "quick_read": "Heat and humidity were sampled today.",
        "facebook": "Heat and humidity were sampled today.",
        "instagram": "Heat and humidity were sampled today.",
        "voiceover": "Heat and humidity were sampled today.",
        "reel_story": {
            "hook": "Heavy air slowing you down?",
            "where": "Heat was strongest along the Gulf Coast.",
            "drivers": "Heat and humidity were the leading sampled drivers.",
            "effects": "Some people may notice fatigue under these conditions.",
            "summary": _reel_summary(earth="ULF Active (diffuse) was measured."),
        },
        "section_copy": {},
    }

    errors = writer._copy_validation_errors(copy, {"major_events": {"items": []}})

    assert "reel_story.summary.earth must use plain prose without semicolons or parentheses" in errors


def test_writer_validation_rejects_unsupplied_ulf_classification_and_low_strength() -> None:
    copy = {
        "headline": "Feeling weighed down by heat?",
        "quick_read": "Space weather is low-strength and ULF was classified today.",
        "facebook": "Heat and humidity were sampled today.",
        "instagram": "Heat and humidity were sampled today.",
        "voiceover": "Heat and humidity were sampled today.",
        "reel_story": {
            "hook": "Feeling weighed down by heat?",
            "where": "Heat was strongest along the Gulf Coast.",
            "drivers": "Heat and humidity were the leading sampled drivers.",
            "effects": "Some people may notice fatigue under these conditions.",
            "summary": _reel_summary(earth="ULF was classified today."),
        },
        "section_copy": {},
    }

    errors = writer._copy_validation_errors(
        copy,
        {"major_events": {"items": []}, "earth_signal": {"ulf_usable": False}},
    )

    assert "copy must not call ULF classified when no usable ULF class is supplied" in errors
    assert "copy must describe supplied low space activity in plain language" in errors


def test_writer_validation_rejects_bare_ulf_classifier_stack() -> None:
    copy = {
        "headline": "Is the air feeling heavy?",
        "quick_read": "Earth signals include Active diffuse ULF.",
        "facebook": "Heat and humidity were sampled today.",
        "instagram": "Heat and humidity were sampled today.",
        "voiceover": "Heat and humidity were sampled today.",
        "reel_story": {
            "hook": "Is the air feeling heavy?",
            "where": "Heat was strongest along the Gulf Coast.",
            "drivers": "Heat and humidity were the leading sampled drivers.",
            "effects": "Some people may notice fatigue under these conditions.",
            "summary": _reel_summary(earth="Earth signals include Active diffuse ULF."),
        },
        "section_copy": {},
    }

    errors = writer._copy_validation_errors(
        copy,
        {"major_events": {"items": []}, "earth_signal": {"ulf_usable": True}},
    )

    assert "copy must translate ULF classifiers into grammatical public prose" in errors


def test_writer_validation_rejects_schumann_as_single_summary_score() -> None:
    copy = {
        "headline": "Is the air feeling heavy?",
        "quick_read": "Heat and humidity were sampled today.",
        "facebook": "Heat and humidity were sampled today.",
        "instagram": "Heat and humidity were sampled today.",
        "voiceover": "Heat and humidity were sampled today.",
        "reel_story": {
            "hook": "Is the air feeling heavy?",
            "where": "Heat was strongest along the Gulf Coast.",
            "drivers": "Heat and humidity were the leading sampled drivers.",
            "effects": "Some people may notice fatigue under these conditions.",
            "summary": _reel_summary(earth="Schumann is near 7.67 hertz today."),
        },
        "section_copy": {},
    }

    errors = writer._copy_validation_errors(
        copy,
        {"major_events": {"items": []}, "earth_signal": {"ulf_usable": True}},
    )

    assert "reel_story.summary.earth must describe measured Schumann frequencies, not Schumann as a score" in errors


def test_shadow_fixture_writes_review_only_bundle(tmp_path) -> None:
    observations_path = tmp_path / "observations.json"
    context_path = tmp_path / "context.json"
    output_path = tmp_path / "report.json"
    observations_path.write_text(json.dumps([_observation("alpha"), _observation("bravo")]))
    context_path.write_text(json.dumps(_context()))
    args = argparse.Namespace(
        date="2026-07-14",
        edition="global",
        output=str(output_path),
        observations_fixture=str(observations_path),
        context_fixture=str(context_path),
        previous=None,
        anchor_limit=0,
        concurrency=2,
        model=None,
        no_writer=True,
    )

    asyncio.run(run(args))
    bundle = json.loads(output_path.read_text())

    assert bundle["auto_publish"] is False
    assert bundle["report"]["auto_publish"] is False
    assert bundle["copy_runtime"] == {"status": "not_generated", "reason": "--no-writer"}
    assert bundle["review_inputs"]["observation_count"] == 2


def test_us_shadow_uses_edition_specific_default_filename(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    observations_path = tmp_path / "observations.json"
    context_path = tmp_path / "context.json"
    observations_path.write_text(json.dumps([]))
    context_path.write_text(json.dumps(_context()))
    args = argparse.Namespace(
        date="2026-07-19",
        edition="us",
        output=None,
        observations_fixture=str(observations_path),
        context_fixture=str(context_path),
        previous=None,
        anchor_limit=0,
        concurrency=2,
        model=None,
        no_writer=True,
    )

    output = asyncio.run(run(args))

    assert output.resolve() == tmp_path / "tmp/public_signal_report/2026-07-19-us.json"
    bundle = json.loads(output.read_text())
    assert bundle["review_inputs"]["edition"] == "us"
    assert bundle["report"]["public_name"] == "Gaia Eyes U.S. Health Snapshot"
