"""Exercise the real emitter using only disposable, synthetic media files."""

import json
from pathlib import Path
import subprocess
import sys

import pytest


EMITTER = Path(__file__).resolve().parents[2] / "scripts/pulse_emit.py"
SOURCE_TIME = "2020-01-02T03:04:05Z"
SOURCES = {"cme_source": "https://example.invalid/synthetic-cme-source"}
NO_ARRIVAL = " Arrival timing is not provided by these observations."


def feed(rows, **overrides):
    return {
        "timestamp_utc": SOURCE_TIME,
        "sources": SOURCES,
        "cmes": {"last_72h": rows, "headline": "No Earth-directed CMEs detected"},
        **overrides,
    }


def emit(tmp_path, inputs):
    media = tmp_path / "media"
    data = media / "data"
    data.mkdir(parents=True)
    for name, payload in inputs.items():
        (data / name).write_text(json.dumps(payload), encoding="utf-8")
    before = {p.name: p.read_bytes() for p in data.iterdir()}
    output = tmp_path / "isolated-output/pulse.json"
    result = subprocess.run(
        [sys.executable, str(EMITTER)],
        cwd=tmp_path,
        env={
            "MEDIA_DIR": str(media),
            "OUTPUT_JSON_PATH": str(output),
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        capture_output=True, text=True, check=True, timeout=10,
    )
    assert result.stdout.strip() == f"[pulse] wrote -> {output}"
    assert not result.stderr
    assert {p.name: p.read_bytes() for p in data.iterdir()} == before
    payload = json.loads(output.read_text())
    assert set(payload) == {"timestamp_utc", "cards"}
    assert payload["timestamp_utc"].endswith("Z")
    return payload["cards"]


def cme_card(tmp_path, payload):
    return next(c for c in emit(tmp_path, {"flares_cmes.json": payload}) if c["type"] == "cme")


@pytest.mark.parametrize("speed", [None, 0, 347, 399, 400, 450, 599, 600, 999, 1000, 2400])
def test_speed_never_becomes_earth_impact_or_arrival_forecast(tmp_path, speed):
    # Three reports also exercise the formerly hard-coded count of two.
    card = cme_card(tmp_path, feed([
        {"earth_directed": False, "speed_kms": speed},
        {"earth_directed": False},
        {"earth_directed": False},
    ]))
    assert card == {
        "type": "cme",
        "title": "CME Observations",
        "summary": "Reported CMEs are marked non-Earth-directed." + NO_ARRIVAL,
        "severity": "info",
        "time_window": "Source snapshot: 2020-01-02 03:04 UTC",
        "data": {"max_speed_kms": speed, "source_timestamp_utc": SOURCE_TIME, "sources": SOURCES},
    }


@pytest.mark.parametrize(("rows", "summary"), [
    ([{"earth_directed": True}], "At least one reported CME is marked Earth-directed."),
    ([{"earth_directed": True}, {"earth_directed": False}], "At least one reported CME is marked Earth-directed."),
    ([{"earth_directed": True}, {"earth_directed": None}], "At least one reported CME is marked Earth-directed. Other reported CME directions are unconfirmed."),
    ([{"earth_directed": False}], "Reported CMEs are marked non-Earth-directed."),
    ([{"earth_directed": False}, {"speed_kms": 347}], "Earth-directed status is unconfirmed for some or all reported CMEs."),
    ([{"earth_directed": None}], "Earth-directed status is unconfirmed for some or all reported CMEs."),
    ([{"earth_directed": "false"}, {"earth_directed": "true"}], "Earth-directed status is unconfirmed for some or all reported CMEs."),
    ([{"earth_directed": 0}, {"earth_directed": 1}], "Earth-directed status is unconfirmed for some or all reported CMEs."),
])
def test_direction_uses_explicit_flags_and_does_not_repeat_misleading_headline(tmp_path, rows, summary):
    card = cme_card(tmp_path, feed(rows))
    assert card["summary"] == summary + NO_ARRIVAL
    assert card["severity"] == "info"
    assert card["title"] == "CME Observations"


@pytest.mark.parametrize("payload", [
    None, [], ["bad envelope"], {}, {"cmes": None}, {"cmes": []},
    {"cmes": {}}, {"cmes": {"last_72h": None}},
    {"cmes": {"last_72h": []}}, {"cmes": {"last_72h": "unavailable"}},
    {"cmes": {"last_72h": [None, "bad row", 0, {}]}},
])
def test_missing_or_empty_observations_omit_card_without_claiming_no_cmes(tmp_path, payload):
    cards = emit(tmp_path, {"flares_cmes.json": payload})
    assert [c["type"] for c in cards] == ["tips"]


def test_missing_file_omits_cme_card(tmp_path):
    assert [c["type"] for c in emit(tmp_path, {})] == ["tips"]


def test_invalid_json_omits_cme_card(tmp_path):
    # A malformed file remains a missing-data condition, not a zero-event claim.
    media = tmp_path / "media/data"
    media.mkdir(parents=True)
    (media / "flares_cmes.json").write_text("{truncated")
    output = tmp_path / "output/pulse.json"
    subprocess.run([sys.executable, str(EMITTER)], cwd=tmp_path, env={
        "MEDIA_DIR": str(media.parent), "OUTPUT_JSON_PATH": str(output),
    }, capture_output=True, check=True, timeout=10)
    assert [c["type"] for c in json.loads(output.read_text())["cards"]] == ["tips"]
    assert (media / "flares_cmes.json").read_text() == "{truncated"


@pytest.mark.parametrize("valid_speeds", [[], [0], [347, 1200, 599]])
def test_missing_or_invalid_speed_is_not_zero_and_max_uses_measurements(tmp_path, valid_speeds):
    speeds = [None, -1, "9999", True, False, float("nan"), float("inf"), {}] + valid_speeds
    card = cme_card(tmp_path, feed([{"speed_kms": speed} for speed in speeds]))
    assert card["data"]["max_speed_kms"] == (max(valid_speeds) if valid_speeds else None)


@pytest.mark.parametrize("source_time", [None, "not-a-date", 123, "2020-01-02T03:04:05"])
def test_invalid_or_unzoned_source_time_does_not_use_emission_time(tmp_path, source_time):
    card = cme_card(tmp_path, feed([{"earth_directed": None}], timestamp_utc=source_time))
    assert card["time_window"] == "Source snapshot time unavailable"
    assert "source_timestamp_utc" not in card["data"]


def test_offset_source_time_is_normalized_and_missing_provenance_not_invented(tmp_path):
    card = cme_card(tmp_path, feed([{"earth_directed": True}],
        timestamp_utc="2020-01-01T22:04:05-05:00", sources=None))
    assert card["data"]["source_timestamp_utc"] == SOURCE_TIME
    assert card["time_window"] == "Source snapshot: 2020-01-02 03:04 UTC"
    assert "sources" not in card["data"]


def test_unrelated_card_output_is_unchanged(tmp_path):
    cards = emit(tmp_path, {
        "flares_cmes.json": feed([{"earth_directed": False, "speed_kms": 347}], flares={"max_24h": "M1.2"}),
        "space_weather.json": {"now": {"kp": 5}, "next_72h": {"headline": "G1 watch"}},
        "quakes_latest.json": {"events": [{"mag": 5.1, "place": "Synthetic location", "depth_km": 10, "time_utc": SOURCE_TIME, "url": "https://example.invalid/quake"}]},
        "alerts_us_latest.json": {"alerts": [{"event": "Flood Warning"}]},
        "gdacs_latest.json": {"alerts": [{"code": "TC", "title": "Synthetic storm", "published": SOURCE_TIME, "url": "https://example.invalid/hazard"}]},
    })
    assert [c for c in cards if c["type"] != "cme"] == [
        {"type": "flare", "title": "M-class Solar Flare Risk Persists", "summary": "Recent peak M1.2. Radio/HF may see brief fades during bursts.", "severity": "medium", "time_window": "Next 24–48h", "data": {"max_24h": "M1.2"}},
        {"type": "aurora", "title": "Aurora Chances: High Latitudes", "summary": "G1 watch. Best bets after local midnight; dark skies help.", "severity": "low", "time_window": "Tonight–Next 72h", "data": {"kp_now": 5, "headline": "G1 watch"}},
        {"type": "tips", "title": "How to Capture Auroras", "summary": "Wide lens; ISO 1600–3200; 4–6s exposure; manual focus on bright star; shoot RAW.", "severity": "info"},
        {"type": "quake", "title": "M5.1 Earthquake — Synthetic location", "summary": "Shallow event.", "severity": "info", "time_window": "2020-01-02 03:04:05 UTC", "details_url": "https://example.invalid/quake", "data": {"mag": 5.1, "place": "Synthetic location", "time_utc": SOURCE_TIME}},
        {"type": "severe", "title": "Central U.S. — Storm & Flood Risk", "summary": "Clusters of severe t-storm / flood alerts active. Check local NWS.", "severity": "medium", "time_window": "Next 48h", "details_url": "https://www.weather.gov/alerts", "data": {"examples": ["Flood Warning"]}},
        {"type": "global", "title": "Global Hazard — Synthetic storm", "summary": "GDACS reports an active event; monitor local advisories.", "severity": "high", "time_window": SOURCE_TIME, "details_url": "https://example.invalid/hazard"},
    ]
