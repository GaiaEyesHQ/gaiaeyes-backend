from __future__ import annotations

import asyncio

from bots import local_health_poll


def test_dedupe_locations_fetches_each_zip_once() -> None:
    rows = [
        {"zip": "78754", "lat": 30.34, "lon": -97.66},
        {"zip": "78754", "lat": 30.35, "lon": -97.67},
        {"zip": "49001", "lat": 42.27, "lon": -85.55},
    ]

    deduped = local_health_poll._dedupe_locations(rows)

    assert [row["zip"] for row in deduped] == ["78754", "49001"]


def test_current_mode_skips_multiday_forecast(monkeypatch) -> None:
    monkeypatch.setattr(
        local_health_poll.pg,
        "fetch",
        lambda *args, **kwargs: [{"zip": "78754", "lat": 30.3, "lon": -97.6}],
    )
    current_calls: list[str] = []

    async def fake_assemble(zip_code: str):
        current_calls.append(zip_code)
        return {"asof": "2026-07-11T20:00:00Z"}

    async def fail_forecast(*args, **kwargs):  # noqa: ANN002, ANN003, ARG001
        raise AssertionError("forecast should not run in current mode")

    monkeypatch.setattr(local_health_poll, "assemble_for_zip", fake_assemble)
    monkeypatch.setattr(local_health_poll, "upsert_zip_payload", lambda *args, **kwargs: None)
    monkeypatch.setattr(local_health_poll, "_refresh_local_forecast", fail_forecast)

    stats = asyncio.run(local_health_poll.run("current"))

    assert current_calls == ["78754"]
    assert stats["current_updated"] == 1
    assert stats["forecast_updated"] == 0


def test_forecast_mode_skips_current_snapshot(monkeypatch) -> None:
    monkeypatch.setattr(
        local_health_poll.pg,
        "fetch",
        lambda *args, **kwargs: [{"zip": "78754", "lat": 30.3, "lon": -97.6}],
    )

    async def fail_current(*args, **kwargs):  # noqa: ANN002, ANN003, ARG001
        raise AssertionError("current snapshot should not run in forecast mode")

    async def fake_forecast(*args, **kwargs):  # noqa: ANN002, ANN003, ARG001
        return 7

    monkeypatch.setattr(local_health_poll, "assemble_for_zip", fail_current)
    monkeypatch.setattr(local_health_poll, "_refresh_local_forecast", fake_forecast)

    stats = asyncio.run(local_health_poll.run("forecast"))

    assert stats["current_updated"] == 0
    assert stats["forecast_updated"] == 7
