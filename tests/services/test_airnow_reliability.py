import asyncio
import logging
import os
from datetime import datetime, timezone

import httpx
import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://unused:unused@127.0.0.1:1/unused")

from services.external import airnow
from services.local_signals import aggregator

pytestmark = pytest.mark.anyio("asyncio")


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def providers(monkeypatch):
    calls = []

    async def empty_latlon(lat, lon, distance_miles=None):
        calls.append(("latlon", distance_miles))
        return []

    async def empty_zip(zip_code, distance_miles=None):
        calls.append(("zip", distance_miles))
        return []

    monkeypatch.setattr(airnow, "DEFAULT_RADIUS_MI", 25)
    monkeypatch.setattr(airnow, "CURRENT_TOTAL_BUDGET_SECONDS", 12.0)
    monkeypatch.setattr(airnow, "REQUEST_TIMEOUT_SECONDS", 10.0)
    monkeypatch.setattr(airnow, "current_by_latlon", empty_latlon)
    monkeypatch.setattr(airnow, "current_by_zip", empty_zip)
    return calls


async def test_one_deadline_covers_all_endpoints_and_radii(monkeypatch, providers):
    clock = [100.0]
    timeouts = []
    monkeypatch.setattr(aggregator, "monotonic", lambda: clock[0])

    async def fake_wait_for(request, timeout):
        timeouts.append(timeout)
        result = await request
        clock[0] += min(5.0, timeout)
        if timeout < 5.0:
            raise TimeoutError("simulated provider delay")
        return result

    monkeypatch.setattr(aggregator.asyncio, "wait_for", fake_wait_for)
    assert await aggregator._fetch_air_quality("76541", 31.1, -97.7) == []
    assert timeouts == [10.0, 7.0, 2.0]
    assert providers == [("latlon", 25), ("latlon", 50), ("latlon", 100)]
    assert clock[0] == 112.0


@pytest.mark.parametrize("status", [410, 502, 504])
async def test_outage_is_two_attempts_and_logs_no_credentials(monkeypatch, providers, caplog, status):
    request = httpx.Request("GET", airnow.LATLON_BASE, params={"API_KEY": "must-not-log-this-key"})
    response = httpx.Response(status, request=request)

    async def fail_latlon(lat, lon, distance_miles=None):
        providers.append(("latlon", distance_miles))
        response.raise_for_status()

    async def fail_zip(zip_code, distance_miles=None):
        providers.append(("zip", distance_miles))
        response.raise_for_status()

    monkeypatch.setattr(airnow, "current_by_latlon", fail_latlon)
    monkeypatch.setattr(airnow, "current_by_zip", fail_zip)
    with caplog.at_level(logging.WARNING):
        assert await aggregator._fetch_air_quality("76541", 31.1, -97.7) == []
    assert providers == [("latlon", 25), ("zip", 25)]
    assert "HTTPStatusError" in caplog.text
    assert f"status={status}" in caplog.text
    assert "must-not-log-this-key" not in caplog.text
    assert "API_KEY" not in caplog.text
    assert "https://" not in caplog.text


async def test_error_then_empty_alternate_does_not_expand_radii(monkeypatch, providers):
    async def fail_latlon(*args, **kwargs):
        providers.append(("latlon", kwargs["distance_miles"]))
        raise httpx.ReadTimeout("a credential-bearing error must not be logged")

    monkeypatch.setattr(airnow, "current_by_latlon", fail_latlon)
    assert await aggregator._fetch_air_quality("76541", 31.1, -97.7) == []
    assert providers == [("latlon", 25), ("zip", 25)]


async def test_budget_cancels_and_waits_for_provider_cleanup(monkeypatch, providers):
    events = []
    active = 0
    monkeypatch.setattr(airnow, "CURRENT_TOTAL_BUDGET_SECONDS", 0.05)
    monkeypatch.setattr(airnow, "REQUEST_TIMEOUT_SECONDS", 0.03)

    async def slow_provider(*args, **kwargs):
        nonlocal active
        active += 1
        events.append("started")
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            events.append("cancelled")
            raise
        finally:
            await asyncio.sleep(0.005)
            active -= 1
            events.append("closed")

    monkeypatch.setattr(airnow, "current_by_latlon", slow_provider)
    monkeypatch.setattr(airnow, "current_by_zip", slow_provider)
    assert await aggregator._fetch_air_quality("76541", 31.1, -97.7) == []
    assert events == ["started", "cancelled", "closed", "started", "cancelled", "closed"]
    assert active == 0


async def test_outer_cancellation_propagates_without_zip_retry(monkeypatch, providers):
    started = asyncio.Event()
    closed = asyncio.Event()

    async def slow_provider(*args, **kwargs):
        started.set()
        try:
            await asyncio.sleep(10)
        finally:
            await asyncio.sleep(0)
            closed.set()

    monkeypatch.setattr(airnow, "current_by_latlon", slow_provider)
    task = asyncio.create_task(aggregator._fetch_air_quality("76541", 31.1, -97.7))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert closed.is_set()
    assert providers == []


async def test_next_poll_retries_after_outage_without_failure_cache(monkeypatch, providers):
    async def fail(*args, **kwargs):
        raise httpx.ReadTimeout("timeout")

    monkeypatch.setattr(airnow, "current_by_latlon", fail)
    monkeypatch.setattr(airnow, "current_by_zip", fail)
    assert await aggregator._fetch_air_quality("76541", 31.1, -97.7) == []

    async def recovered(*args, **kwargs):
        return [{"AQI": 0, "Category": {"Name": "Good"}}]

    monkeypatch.setattr(airnow, "current_by_latlon", recovered)
    assert (await aggregator._fetch_air_quality("76541", 31.1, -97.7))[0]["AQI"] == 0


@pytest.mark.parametrize("rows", [None, {}, {"error": "missing"}, [None], [{"AQI": None}], [{"AQI": -999}], [{"AQI": True}], [{"AQI": float("nan")}], [{"AQI": float("inf")}], [{"AQI": "unknown"}], [{"Category": {"Name": "Good"}}]])
async def test_invalid_provider_readings_remain_missing(monkeypatch, providers, rows):
    async def invalid(*args, **kwargs):
        return rows

    monkeypatch.setattr(airnow, "current_by_latlon", invalid)
    monkeypatch.setattr(airnow, "current_by_zip", invalid)
    assert await aggregator._fetch_air_quality("76541", 31.1, -97.7) == []


async def test_http_client_cleans_up_on_budget_timeout(monkeypatch):
    closed = asyncio.Event()
    monkeypatch.setattr(airnow, "API_KEY", "test-key-never-print")
    monkeypatch.setattr(airnow, "CURRENT_TOTAL_BUDGET_SECONDS", 0.01)

    class SlowClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            await asyncio.sleep(0)
            closed.set()

        async def get(self, *args, **kwargs):
            await asyncio.sleep(10)

    monkeypatch.setattr(airnow.httpx, "AsyncClient", SlowClient)
    assert await aggregator._fetch_air_quality("76541", 31.1, -97.7) == []
    assert closed.is_set()


async def test_http_client_info_does_not_log_key_url(monkeypatch, caplog):
    key = "test-key-never-print"
    monkeypatch.setattr(airnow, "API_KEY", key)
    client_type = httpx.AsyncClient

    def respond(request):
        return httpx.Response(502, request=request)

    def client(**kwargs):
        return client_type(transport=httpx.MockTransport(respond), **kwargs)

    monkeypatch.setattr(airnow.httpx, "AsyncClient", client)
    # Keep provider client logger levels intact, as in API and cron startup.
    with caplog.at_level(logging.INFO):
        assert await aggregator._fetch_air_quality("76541", 31.1, -97.7) == []
    assert "status=502" in caplog.text
    assert key not in caplog.text
    assert "API_KEY" not in caplog.text
    assert "https://" not in caplog.text


@pytest.mark.parametrize("aqi", [None, 0, 101])
async def test_assembly_keeps_weather_and_never_reages_cached_aqi(monkeypatch, aqi):
    weather = {"temp_c": 22.0, "pressure_hpa": 1012.0, "obs_time": "2026-10-11T03:00:00+00:00", "humidity_pct": 0}
    old_row = {"asof": datetime(2020, 1, 1, tzinfo=timezone.utc), "payload": {"air": {"aqi": 12, "category": "Good"}}}
    monkeypatch.setattr(aggregator, "zip_to_latlon", lambda zip_code: (31.1, -97.7))
    monkeypatch.setattr(aggregator, "latest_and_ref", lambda *a, **k: (old_row, None))
    monkeypatch.setattr(aggregator, "get_previous_approx", lambda *a, **k: None)
    monkeypatch.setattr(aggregator, "nearest_row_to", lambda *a, **k: None)
    monkeypatch.setattr(aggregator, "moon_phase", lambda *a: {})

    async def nws_snapshot(*args):
        return weather

    async def aq_snapshot(*args):
        return [{"AQI": aqi, "Category": {"Name": "Good" if aqi == 0 else "Unhealthy for Sensitive Groups"}}] if aqi is not None else []

    async def pollen_snapshot(*args, **kwargs):
        return {}

    monkeypatch.setattr(aggregator.nws, "hourly_by_latlon", nws_snapshot)
    monkeypatch.setattr(aggregator, "_fetch_air_quality", aq_snapshot)
    monkeypatch.setattr(aggregator, "_fetch_pollen_forecast", pollen_snapshot)
    payload = await aggregator.assemble_for_zip("76541")
    assert payload["weather"]["temp_c"] == 22.0
    assert payload["weather"]["pressure_hpa"] == 1012.0
    assert payload["weather"]["humidity_pct"] == 0
    assert payload["air"]["aqi"] == aqi
    assert payload["air"]["available"] is (aqi is not None)
    assert payload["health"]["flags"]["aqi_flag"] == ({None: None, 0: "good", 101: "usg"}[aqi])
    assert payload["asof"] == weather["obs_time"]
