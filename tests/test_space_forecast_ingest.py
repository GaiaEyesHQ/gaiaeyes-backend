import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

from scripts.ingest_space_forecasts_step1 import (
    _aurora_headline,
    _parse_dt,
    _parse_float,
    _radiation_risk,
    _region_from_station,
    _s_scale_from_flux,
    ingest_aurora,
    ingest_drap,
    ingest_magnetometer,
)


class RecordingWriter:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []  # type: ignore[name-defined]

    async def upsert_many(
        self,
        schema: str,
        table: str,
        rows,
        conflict_cols=None,
        *,
        constraint=None,
        skip_update_cols=None,
    ) -> int:
        self.calls.append(
            {
                "schema": schema,
                "table": table,
                "rows": rows,
            }
        )
        return len(rows)

    def rows_for(self, schema: str, table: str):
        for call in self.calls:
            if call["schema"] == schema and call["table"] == table:
                return call["rows"]
        return []


@pytest.mark.parametrize(
    "value,expected",
    [
        ("2024-11-05T12:00:00Z", datetime(2024, 11, 5, 12, 0, tzinfo=UTC)),
        ("2024-11-05 12:00:00", datetime(2024, 11, 5, 12, 0, tzinfo=UTC)),
        (None, None),
        ("", None),
    ],
)
def test_parse_dt(value, expected):
    assert _parse_dt(value) == expected


@pytest.mark.parametrize(
    "value,expected",
    [("3.5", 3.5), ("nan", None), (None, None), ("", None)]
)
def test_parse_float(value, expected):
    assert _parse_float(value) == expected


@pytest.mark.parametrize(
    "flux,expected",
    [
        (150_000, ("S5", 5)),
        (12_000, ("S4", 4)),
        (1200, ("S3", 3)),
        (150, ("S2", 2)),
        (20, ("S1", 1)),
        (5, ("S0", 0)),
        (None, (None, None)),
    ],
)
def test_s_scale_from_flux(flux, expected):
    assert _s_scale_from_flux(flux) == expected


@pytest.mark.parametrize(
    "flux,expected",
    [
        (2e7, "extreme"),
        (2e6, "severe"),
        (2e5, "high"),
        (2e4, "elevated"),
        (2e3, "moderate"),
        (200, "quiet"),
        (None, "unknown"),
    ],
)
def test_radiation_risk(flux, expected):
    assert _radiation_risk(flux) == expected


@pytest.mark.parametrize(
    "station,expected",
    [
        ("ALE", "auroral"),
        ("aae", "equatorial"),
        ("lyr", "polar"),
        ("foo", "global"),
        (None, "global"),
    ],
)
def test_region_from_station(station, expected):
    assert _region_from_station(station) == expected


@pytest.mark.parametrize(
    "power,kp,headline",
    [
        (90, 6.5, "Major aurora power – Wing Kp 6.5"),
        (65, None, "Active aurora"),
        (45, 4.1, "Elevated aurora – Wing Kp 4.1"),
        (20, None, "Quiet aurora"),
        (None, 3.5, "Wing Kp 3.5"),
        (None, None, "Auroral outlook unavailable"),
    ],
)
def test_aurora_headline(power, kp, headline):
    assert _aurora_headline(power, kp) == headline


def test_ingest_aurora_parses_summary(monkeypatch):
    from scripts import ingest_space_forecasts_step1 as module

    sample = {
        "Observation Time": "2024-11-05T12:00:00Z",
        "Hemisphere Power": {"North": 65.2, "South": 25.5},
    }

    async def fake_fetch_json(client, url, params=None):  # noqa: ARG001
        return sample

    async def runner():
        monkeypatch.setattr(module, "fetch_json", fake_fetch_json)
        writer = RecordingWriter()
        await ingest_aurora(None, writer)  # type: ignore[arg-type]
        return writer

    writer = asyncio.run(runner())
    ext_rows = writer.rows_for("ext", "aurora_power")
    assert len(ext_rows) == 2
    hemis = {row["hemisphere"] for row in ext_rows}
    assert hemis == {"north", "south"}
    mart_rows = writer.rows_for("marts", "aurora_outlook")
    assert len(mart_rows) == 2
    assert all(row["wing_kp"] is None for row in mart_rows)
    assert mart_rows[0]["valid_to"] - mart_rows[0]["valid_from"] == timedelta(hours=1)
    assert any("Elevated" in row["headline"] or "Active" in row["headline"] for row in mart_rows)


def test_ingest_drap_parses_text(monkeypatch):
    from scripts import ingest_space_forecasts_step1 as module

    text_payload = """
:Product: dummy
# Time Frequency Region Absorption
2024-11-05T12:00:00Z 5MHz global 2.5
2024-11-05T12:00:00Z 10MHz equatorial 1.2
"""

    async def fake_fetch_text(client, url, params=None):  # noqa: ARG001
        return text_payload

    async def runner():
        monkeypatch.setattr(module, "fetch_text", fake_fetch_text)
        writer = RecordingWriter()
        await ingest_drap(None, writer, days=1000)  # type: ignore[arg-type]
        return writer

    writer = asyncio.run(runner())
    ext_rows = writer.rows_for("ext", "drap_absorption")
    assert len(ext_rows) == 2
    freqs = sorted(row["frequency_mhz"] for row in ext_rows)
    assert freqs == [5.0, 10.0]
    mart_rows = writer.rows_for("marts", "drap_absorption_daily")
    assert len(mart_rows) == 2
    assert {row["region"] for row in mart_rows} == {"global", "equatorial"}


def test_ingest_magnetometer_supermag(monkeypatch):
    from scripts import ingest_space_forecasts_step1 as module

    sample = {
        "data": [
            {
                "timestamp": "2024-11-05T12:00:00Z",
                "station": "ALE",
                "sme": 480,
                "sml": -320,
                "smu": 160,
                "smr": 2.1,
            },
            {
                "timestamp": "2024-11-05T12:10:00Z",
                "station": "LYR",
                "sme": 500,
                "sml": -350,
                "smu": 180,
                "smr": 2.4,
            },
        ]
    }

    async def fake_fetch_json(client, url, params=None):  # noqa: ARG001
        assert url.startswith("https://supermag.jhuapl.edu/mag/indices/SuperMAG_AE.json")
        assert params and params.get("fmt") == "json"
        return sample

    async def runner():
        monkeypatch.setattr(module, "fetch_json", fake_fetch_json)
        writer = RecordingWriter()
        await ingest_magnetometer(None, writer, days=1)  # type: ignore[arg-type]
        return writer

    writer = asyncio.run(runner())
    ext_rows = writer.rows_for("ext", "magnetometer_chain")
    assert len(ext_rows) == 2
    mart_rows = writer.rows_for("marts", "magnetometer_regional")
    assert mart_rows, "expected aggregated regional rows"
    stations = json.loads(mart_rows[0]["stations"])
    assert stations
