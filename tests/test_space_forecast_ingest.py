from datetime import UTC, datetime

import pytest

from scripts.ingest_space_forecasts_step1 import (
    _aurora_headline,
    _parse_dt,
    _parse_float,
    _radiation_risk,
    _region_from_station,
    _s_scale_from_flux,
)


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
