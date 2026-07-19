import datetime as dt

import pytest

from services.external import nws


pytestmark = pytest.mark.anyio("asyncio")


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _observation(timestamp: str, temperature: float) -> dict:
    return {
        "properties": {
            "timestamp": timestamp,
            "temperature": {"value": temperature},
            "relativeHumidity": {"value": 50.0},
            "barometricPressure": {"value": 101500.0},
        }
    }


@pytest.mark.anyio
async def test_station_conditions_keep_fresh_nearest_station(monkeypatch):
    now = dt.datetime.now(dt.timezone.utc)
    station_calls: list[str] = []

    async def _fake_get_json(url: str):
        if url == "stations-url":
            return {
                "features": [
                    {"properties": {"stationIdentifier": "NEAREST"}},
                    {"properties": {"stationIdentifier": "SECOND"}},
                ]
            }
        station_calls.append(url)
        return _observation((now - dt.timedelta(minutes=10)).isoformat(), 21.0)

    monkeypatch.setattr(nws, "_get_json", _fake_get_json)

    result = await nws._station_latest_conditions(
        {"properties": {"observationStations": "stations-url"}}
    )

    assert result["temp_c"] == 21.0
    assert station_calls == [f"{nws.BASE}/stations/NEAREST/observations/latest?require_qc=true"]


@pytest.mark.anyio
async def test_station_conditions_use_freshest_nearby_station_when_nearest_is_stale(monkeypatch):
    now = dt.datetime.now(dt.timezone.utc)
    observations = {
        "NEAREST": _observation((now - dt.timedelta(minutes=20)).isoformat(), 20.0),
        "SECOND": _observation((now - dt.timedelta(minutes=35)).isoformat(), 21.0),
        "THIRD": _observation((now - dt.timedelta(minutes=25)).isoformat(), 22.0),
        "FOURTH": _observation((now - dt.timedelta(minutes=18)).isoformat(), 23.0),
        "FIFTH": _observation((now - dt.timedelta(minutes=8)).isoformat(), 24.0),
    }

    async def _fake_get_json(url: str):
        if url == "stations-url":
            return {
                "features": [
                    {"properties": {"stationIdentifier": "NEAREST"}},
                    {"properties": {"stationIdentifier": "SECOND"}},
                    {"properties": {"stationIdentifier": "THIRD"}},
                    {"properties": {"stationIdentifier": "FOURTH"}},
                    {"properties": {"stationIdentifier": "FIFTH"}},
                ]
            }
        station_id = url.split("/stations/", 1)[1].split("/", 1)[0]
        return observations[station_id]

    monkeypatch.setattr(nws, "_get_json", _fake_get_json)

    result = await nws._station_latest_conditions(
        {"properties": {"observationStations": "stations-url"}}
    )

    assert result["temp_c"] == 24.0
    assert result["obs_time"] == observations["FIFTH"]["properties"]["timestamp"]


@pytest.mark.anyio
async def test_station_conditions_choose_newest_rolling_observation_regardless_of_order(monkeypatch):
    now = dt.datetime.now(dt.timezone.utc)
    older = _observation((now - dt.timedelta(hours=2)).isoformat(), 19.0)
    newer = _observation((now - dt.timedelta(hours=1)).isoformat(), 21.0)

    async def _fake_get_json(url: str):
        if url == "stations-url":
            return {"features": [{"properties": {"stationIdentifier": "NEAREST"}}]}
        if "/latest?" in url:
            return {"properties": {"timestamp": now.isoformat()}}
        return {"features": [newer, older]}

    monkeypatch.setattr(nws, "_get_json", _fake_get_json)

    result = await nws._station_latest_conditions(
        {"properties": {"observationStations": "stations-url"}}
    )

    assert result["temp_c"] == 21.0
    assert result["obs_time"] == newer["properties"]["timestamp"]
