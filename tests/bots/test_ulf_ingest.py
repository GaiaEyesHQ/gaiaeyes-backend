from datetime import UTC, datetime

import pytest

from bots.geomag_ulf.ingest_ulf import (
    StationWindow,
    choose_component,
    classify_context,
    compute_coherence,
    compute_dbdt_rms,
    compute_percentile_index,
)


def test_compute_dbdt_rms_uses_minute_derivative() -> None:
    assert compute_dbdt_rms([0.0, 60.0, 120.0, 180.0, 240.0]) == pytest.approx(1.0)


def test_choose_component_falls_back_to_x() -> None:
    rows = [
        {"ts_utc": datetime(2026, 3, 20, 0, 0, tzinfo=UTC), "H": None, "X": 10.0},
        {"ts_utc": datetime(2026, 3, 20, 0, 1, tzinfo=UTC), "H": None, "X": 10.5},
        {"ts_utc": datetime(2026, 3, 20, 0, 2, tzinfo=UTC), "H": None, "X": 11.0},
    ]
    assert choose_component(rows) == ("X", True)


def test_compute_percentile_index_returns_none_with_sparse_history() -> None:
    assert compute_percentile_index(1.2, [0.4, 0.8, 1.0]) is None


def test_compute_coherence_is_none_for_single_station() -> None:
    window = StationWindow(
        station_id="BOU",
        ts_utc=datetime(2026, 3, 20, 0, 0, tzinfo=UTC),
        component_used="H",
        component_substituted=False,
        dbdt_rms=0.8,
        ulf_rms_broad=0.8,
        ulf_band_proxy=0.3,
        ulf_index_station=65.0,
        ulf_index_localtime=None,
        persistence_30m=60.0,
        persistence_90m=55.0,
        quality_flags=[],
        dbdt_trace=(0.1, 0.2, 0.3),
    )
    assert compute_coherence([window]) is None


@pytest.mark.parametrize(
    ("intensity", "coherence", "expected"),
    [
        (25.0, None, "Quiet"),
        (45.0, 0.2, "Active (diffuse)"),
        (65.0, 0.6, "Elevated (coherent)"),
        (85.0, 0.8, "Strong (coherent)"),
    ],
)
def test_classify_context_mapping(intensity: float, coherence: float | None, expected: str) -> None:
    assert classify_context(intensity, coherence) == expected
