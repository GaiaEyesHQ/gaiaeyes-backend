"""DONKI tests use only synthetic credentials, mocked HTTP, and a mocked DB."""

import asyncio
import gzip
import importlib.util
import json
import runpy
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ingest_nasa_donki.py"
REAL_CLIENT = httpx.AsyncClient
TEST_KEY = "synthetic-donki-test-key"
PARAMS = {"startDate": "2026-10-10", "endDate": "2026-10-12", "api_key": TEST_KEY}
PRIMARY = "https://api.nasa.gov/DONKI"
FALLBACK = "https://ccmc.gsfc.nasa.gov/DONKI-API/get"
NOW = datetime(2026, 10, 12, 12, tzinfo=timezone.utc)


@pytest.fixture
def ingest(monkeypatch):
    for name, value in {
        "SUPABASE_DB_URL": "postgresql://synthetic:synthetic@127.0.0.1/unused",
        "NASA_API_KEY": TEST_KEY,
        "DONKI_BASE_PRIMARY": PRIMARY,
        "DONKI_BASE_FALLBACK": FALLBACK,
        "GOES_XRS_1DAY_URL": "https://goes.example.test/xrays.json",
        "DONKI_PRIMARY_RETRIES": "0",
        "DONKI_FALLBACK_RETRIES": "0",
        "START_DAYS_AGO": "2",
        "OUTPUT_JSON_GZIP": "false",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("OUTPUT_JSON_PATH", raising=False)
    spec = importlib.util.spec_from_file_location("donki_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.asyncpg, "connect", AsyncMock(side_effect=AssertionError("Unexpected DB access")))
    monkeypatch.setattr(module.asyncio, "sleep", AsyncMock())
    monkeypatch.setattr(module, "sleepy", AsyncMock())

    def no_live_client(*args, **kwargs):
        raise AssertionError("Live HTTP is forbidden in DONKI tests")

    monkeypatch.setattr(module.httpx, "AsyncClient", no_live_client)
    return module


def fetch_with(ingest, handler, **kwargs):
    async def run():
        # Even a caller that opts into redirects cannot leak the key that way.
        async with REAL_CLIENT(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
            return await ingest.fetch(client, "FLR", PARAMS, **kwargs)
    return asyncio.run(run())


def install_main_client(ingest, monkeypatch, handler):
    monkeypatch.setattr(ingest.httpx, "AsyncClient", lambda: REAL_CLIENT(transport=httpx.MockTransport(handler)))

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW

    monkeypatch.setattr(ingest, "datetime", FixedDatetime)


def event_for(request):
    if request.url.path.endswith("/FLR"):
        return {"flrID": "test-flare", "beginTime": "2026-10-12T09:00Z",
                "peakTime": "2026-10-12T09:05Z", "classType": "C1.2"}
    return {"activityID": "test-cme", "startTime": "2026-10-12T10:00Z", "cmeAnalyses": []}


def test_default_fallback_uses_new_ccmc_endpoint(ingest, monkeypatch):
    monkeypatch.delenv("DONKI_BASE_FALLBACK")
    spec = importlib.util.spec_from_file_location("donki_defaults", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.BASE_FALLBACK == FALLBACK


@pytest.mark.parametrize("payload", [[], [{"flrID": "test-flare", "beginTime": "2026-10-12T09:00Z"}]])
def test_primary_success_and_valid_empty_are_not_failures(ingest, payload):
    requests = []
    sources = set()

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=payload)

    assert fetch_with(ingest, handler, sources=sources) == payload
    assert len(requests) == 1
    assert requests[0].url.params["api_key"] == TEST_KEY
    assert requests[0].extensions["timeout"]["connect"] == 10
    assert requests[0].extensions["timeout"]["read"] == 45
    assert sources == {PRIMARY + "/FLR"}
    assert PARAMS["api_key"] == TEST_KEY


@pytest.mark.parametrize("status", [400, 401, 403, 404, 429, 500, 502, 503])
def test_http_failure_uses_keyless_fallback(ingest, status):
    requests = []
    sources = set()

    def handler(request):
        requests.append(request)
        return httpx.Response(status if len(requests) == 1 else 200, json=[])

    assert fetch_with(ingest, handler, sources=sources) == []
    assert [r.url.host for r in requests] == ["api.nasa.gov", "ccmc.gsfc.nasa.gov"]
    assert "api_key" not in requests[1].url.params
    assert requests[1].url.path == "/DONKI-API/get/FLR"
    assert requests[1].url.params["startDate"] == PARAMS["startDate"]
    assert sources == {FALLBACK + "/FLR"}


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_redirects_are_never_followed(ingest, status):
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.host == "api.nasa.gov":
            return httpx.Response(status, headers={"Location": "https://other.example.test/leak?api_key=" + TEST_KEY})
        return httpx.Response(200, json=[])

    assert fetch_with(ingest, handler) == []
    assert [r.url.host for r in requests] == ["api.nasa.gov", "ccmc.gsfc.nasa.gov"]
    assert TEST_KEY not in str(requests[-1].url)


def test_moved_fallback_redirect_cannot_count_as_empty(ingest, monkeypatch):
    monkeypatch.setattr(ingest, "BASES", [PRIMARY, "https://kauai.ccmc.gsfc.nasa.gov/DONKI/WS/get"])
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.host == "api.nasa.gov":
            return httpx.Response(503)
        return httpx.Response(301, headers={"Location": "https://ccmc.gsfc.nasa.gov/news/major-updates/"})

    with pytest.raises(ingest.DonkiFetchError):
        fetch_with(ingest, handler)
    assert len(requests) == 2
    assert "api_key" not in requests[-1].url.params


@pytest.mark.parametrize("body", [b"<html>Moved</html>", b"{broken", b"null", b"true", b"42", b'"text"', b'{}', b'[null]', b'[{},42]'])
def test_malformed_or_wrong_shape_payload_falls_back(ingest, body):
    requests = []

    def handler(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, content=body)
        return httpx.Response(200, json=[])

    assert fetch_with(ingest, handler) == []
    assert len(requests) == 2


@pytest.mark.parametrize("base", [
    "https://ccmc.gsfc.nasa.gov/DONKI-API/get",
    "https://api.nasa.gov.example.test/DONKI",
    "https://example.test/api.nasa.gov/DONKI",
    "http://api.nasa.gov/DONKI",
    "https://api.nasa.gov:444/DONKI",
    "https://api.nasa.gov./DONKI",
])
def test_primary_override_cannot_receive_nasa_key(ingest, monkeypatch, base):
    monkeypatch.setattr(ingest, "BASES", [base, FALLBACK])
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=[])

    assert fetch_with(ingest, handler) == []
    assert len(requests) == 1
    assert "api_key" not in requests[0].url.params


def test_even_nasa_host_in_fallback_slot_receives_no_key(ingest, monkeypatch):
    monkeypatch.setattr(ingest, "BASES", [FALLBACK, PRIMARY])
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(503 if len(requests) == 1 else 200, json=[])

    assert fetch_with(ingest, handler) == []
    assert all("api_key" not in request.url.params for request in requests)


@pytest.mark.parametrize("base", [
    "https://api.nasa.gov/DONKI?api_key=" + TEST_KEY,
    "https://synthetic:" + TEST_KEY + "@api.nasa.gov/DONKI",
    "https://api.nasa.gov/DONKI#" + TEST_KEY,
])
def test_base_with_embedded_secret_is_rejected_without_logging_it(ingest, monkeypatch, capsys, base):
    monkeypatch.setattr(ingest, "BASES", [base, FALLBACK])
    requests = []
    sources = set()

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=[])

    assert fetch_with(ingest, handler, sources=sources) == []
    assert len(requests) == 1
    assert requests[0].url.host == "ccmc.gsfc.nasa.gov"
    assert sources == {FALLBACK + "/FLR"}
    assert TEST_KEY not in capsys.readouterr().err


@pytest.mark.parametrize("failure", ["timeout", "connect", "http", "json"])
def test_all_provider_failures_raise_without_secret_logs(ingest, monkeypatch, capsys, failure):
    monkeypatch.setattr(ingest, "PRIMARY_RETRIES", 1)
    monkeypatch.setattr(ingest, "FALLBACK_RETRIES", 2)
    requests = []

    def handler(request):
        requests.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("Secret in exception: " + TEST_KEY, request=request)
        if failure == "connect":
            raise httpx.ConnectError("Secret in exception: " + TEST_KEY, request=request)
        if failure == "http":
            return httpx.Response(503, text=TEST_KEY)
        return httpx.Response(200, content=("invalid JSON " + TEST_KEY).encode())

    with pytest.raises(ingest.DonkiFetchError) as error:
        fetch_with(ingest, handler)
    assert len(requests) == (2 if failure == "json" else 5)
    assert TEST_KEY not in str(error.value)
    assert TEST_KEY not in capsys.readouterr().err


@pytest.mark.parametrize("day_mode", [False, True])
@pytest.mark.parametrize("compressed", [False, True])
def test_complete_empty_range_emits_fresh_empty_summary(ingest, monkeypatch, tmp_path, capsys, day_mode, compressed):
    output = tmp_path / "flares_cmes.json"
    target = Path(str(output) + ".gz") if compressed else output
    target.write_bytes(b"previous-output")
    monkeypatch.setattr(ingest, "OUTPUT_JSON_PATH", str(output))
    monkeypatch.setattr(ingest, "OUTPUT_JSON_GZIP", compressed)
    monkeypatch.setattr(ingest, "DAY_MODE", day_mode)
    install_main_client(ingest, monkeypatch, lambda request: httpx.Response(200, json=[]))

    asyncio.run(ingest.main())

    data = json.loads(gzip.decompress(target.read_bytes()) if compressed else target.read_bytes())
    assert data["timestamp_utc"] == "2026-10-12T12:00:00Z"
    assert data["flares"]["recent"] == []
    assert data["cmes"]["last_72h"] == []
    assert data["cmes"]["headline"] == "No CMEs in last 72h"
    assert data["sources"] == {"flr_source": PRIMARY + "/FLR", "cme_source": PRIMARY + "/CME"}
    ingest.asyncpg.connect.assert_not_awaited()
    assert "No DONKI events in range." in capsys.readouterr().out


@pytest.mark.parametrize("failure_slice", [0, 1, 2, 5])
@pytest.mark.parametrize("compressed", [False, True])
def test_failed_daily_slice_preserves_all_prior_outputs(ingest, monkeypatch, tmp_path, capsys, failure_slice, compressed):
    output = tmp_path / "flares_cmes.json"
    target = Path(str(output) + ".gz") if compressed else output
    target.write_bytes(b"last-known-good-output")
    before = target.stat().st_mtime_ns
    monkeypatch.setattr(ingest, "OUTPUT_JSON_PATH", str(output))
    monkeypatch.setattr(ingest, "OUTPUT_JSON_GZIP", compressed)
    monkeypatch.setattr(ingest, "DAY_MODE", True)
    successes = 0

    def handler(request):
        nonlocal successes
        assert request.url.host != "goes.example.test"
        if successes == failure_slice:
            return httpx.Response(503)
        successes += 1
        return httpx.Response(200, json=[event_for(request)])

    install_main_client(ingest, monkeypatch, handler)
    with pytest.raises(ingest.DonkiFetchError):
        asyncio.run(ingest.main())
    assert successes == failure_slice
    assert target.read_bytes() == b"last-known-good-output"
    assert target.stat().st_mtime_ns == before
    ingest.asyncpg.connect.assert_not_awaited()
    assert "No DONKI events" not in capsys.readouterr().out


def test_failed_range_after_successful_flares_never_writes(ingest, monkeypatch, tmp_path):
    output = tmp_path / "flares_cmes.json"
    output.write_text("previous")
    monkeypatch.setattr(ingest, "OUTPUT_JSON_PATH", str(output))
    monkeypatch.setattr(ingest, "DAY_MODE", False)

    def handler(request):
        return httpx.Response(200, json=[event_for(request)]) if request.url.path.endswith("/FLR") else httpx.Response(503)

    install_main_client(ingest, monkeypatch, handler)
    with pytest.raises(ingest.DonkiFetchError):
        asyncio.run(ingest.main())
    assert output.read_text() == "previous"
    ingest.asyncpg.connect.assert_not_awaited()


def test_successful_fallback_upserts_and_emits_existing_schema(ingest, monkeypatch, tmp_path):
    output = tmp_path / "flares_cmes.json"
    monkeypatch.setattr(ingest, "OUTPUT_JSON_PATH", str(output))
    monkeypatch.setattr(ingest, "DAY_MODE", False)
    conn = AsyncMock()
    monkeypatch.setattr(ingest.asyncpg, "connect", AsyncMock(return_value=conn))

    def handler(request):
        if request.url.host == "api.nasa.gov":
            return httpx.Response(503)
        assert "api_key" not in request.url.params
        return httpx.Response(200, json=[] if request.url.host == "goes.example.test" else [event_for(request)])

    install_main_client(ingest, monkeypatch, handler)
    asyncio.run(ingest.main())
    conn.executemany.assert_awaited_once()
    assert len(conn.executemany.call_args.args[1]) == 2
    conn.close.assert_awaited_once()
    data = json.loads(output.read_text())
    assert set(data) == {"timestamp_utc", "flares", "cmes", "sources"}
    assert data["flares"]["max_24h"] == "C1.2"
    assert data["cmes"]["stats"]["total_72h"] == 1
    assert data["sources"] == {"flr_source": FALLBACK + "/FLR", "cme_source": FALLBACK + "/CME"}
    assert TEST_KEY not in output.read_text()


def test_cli_incomplete_fetch_exits_nonzero(ingest, monkeypatch, capsys):
    def fail_run(coro):
        error = coro.cr_frame.f_globals["DonkiFetchError"]
        coro.close()
        raise error("CME fetch failed for all DONKI providers")

    monkeypatch.setattr(asyncio, "run", fail_run)
    with pytest.raises(SystemExit) as error:
        runpy.run_path(str(SCRIPT), run_name="__main__")
    assert error.value.code == 1
    assert "existing database rows and JSON unchanged" in capsys.readouterr().err


@pytest.mark.parametrize("event", [
    {}, {"error": "Service is unavailable"},
    {"flrID": "test-flare"},
    {"flrID": 123, "beginTime": "2026-10-12T09:00Z"},
    {"beginTime": "not-a-date"},
    {"beginTime": "2026-10-12T09:00"},
    {"beginTime": "2026-10-12T09:00Z", "peakTime": "not-a-date"},
    {"beginTime": "2026-10-12T09:00Z", "endTime": []},
    {"beginTime": "2026-10-12T09:00Z", "classType": {}},
])
def test_invalid_flare_event_uses_fallback(ingest, event):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=[event] if len(requests) == 1 else [event_for(request)])

    result = fetch_with(ingest, handler)
    assert len(requests) == 2
    assert result[0]["flrID"] == "test-flare"


@pytest.mark.parametrize("patch", [
    {"activityID": []}, {"startTime": None}, {"startTime": "broken"},
    {"cmeAnalyses": "broken"}, {"cmeAnalyses": [None]},
    {"analyses": [42]}, {"cmeAnalyses": [{"speed": {}}]},
    {"cmeAnalyses": [{"speed": "NaN"}]},
    {"cmeAnalyses": [{"speed": "Infinity"}]},
    {"cmeAnalyses": [{"isEarthDirected": "true"}]},
])
def test_invalid_cme_event_preserves_outputs_if_both_providers_invalid(ingest, monkeypatch, tmp_path, patch):
    output = tmp_path / "flares_cmes.json"
    output.write_text("last-known-good")
    monkeypatch.setattr(ingest, "OUTPUT_JSON_PATH", str(output))
    monkeypatch.setattr(ingest, "DAY_MODE", False)
    requests = []

    def handler(request):
        requests.append(request)
        event = event_for(request)
        if request.url.path.endswith("/CME"):
            event.update(patch)
        return httpx.Response(200, json=[event])

    install_main_client(ingest, monkeypatch, handler)
    with pytest.raises(ingest.DonkiFetchError):
        asyncio.run(ingest.main())
    assert len(requests) == 3  # Valid FLR, invalid primary CME, invalid fallback CME.
    assert output.read_text() == "last-known-good"
    ingest.asyncpg.connect.assert_not_awaited()


@pytest.mark.parametrize("event", [{}, {"error": "Service is unavailable"}])
def test_list_of_error_objects_never_becomes_no_events(ingest, monkeypatch, tmp_path, event):
    output = tmp_path / "flares_cmes.json"
    output.write_text("last-known-good")
    monkeypatch.setattr(ingest, "OUTPUT_JSON_PATH", str(output))
    install_main_client(ingest, monkeypatch, lambda request: httpx.Response(200, json=[event]))
    with pytest.raises(ingest.DonkiFetchError):
        asyncio.run(ingest.main())
    assert output.read_text() == "last-known-good"
    ingest.asyncpg.connect.assert_not_awaited()


@pytest.mark.parametrize("path,event", [
    ("FLR", {"flrID": "test", "beginTime": "2026-10-12T09:00Z", "peakTime": None, "endTime": None, "classType": None}),
    ("FLR", {"eventID": "test-alias", "beginTime": "2026-10-12T09:00Z"}),
    ("FLR", {"activityID": "test-alias", "beginTime": "2026-10-12T09:00Z"}),
    ("FLR", {"beginTime": "2026-10-12T09:00Z"}),
    ("CME", {"eventID": "test-alias", "startTime": "2026-10-12T09:00Z", "cmeAnalyses": None}),
    ("CME", {"startTime": "2026-10-12T09:00Z", "cmeAnalyses": {"speed": None, "isEarthDirected": None}}),
    ("CME", {"startTime": "2026-10-12T09:00Z", "analyses": [{"speed": "600", "isEarthDirected": False}]}),
])
def test_optional_nulls_and_existing_aliases_remain_valid(ingest, path, event):
    assert ingest.valid_donki_event(event, path)


def test_negative_lookback_preserves_outputs_without_network(ingest, monkeypatch, tmp_path):
    output = tmp_path / "flares_cmes.json"
    output.write_text("last-known-good")
    monkeypatch.setattr(ingest, "OUTPUT_JSON_PATH", str(output))
    monkeypatch.setattr(ingest, "DAYS", -1)
    with pytest.raises(ingest.DonkiFetchError, match="START_DAYS_AGO"):
        asyncio.run(ingest.main())
    assert output.read_text() == "last-known-good"
    ingest.asyncpg.connect.assert_not_awaited()


def test_zero_lookback_fetches_both_today_slices(ingest, monkeypatch, tmp_path):
    output = tmp_path / "flares_cmes.json"
    monkeypatch.setattr(ingest, "OUTPUT_JSON_PATH", str(output))
    monkeypatch.setattr(ingest, "DAYS", 0)
    monkeypatch.setattr(ingest, "DAY_MODE", True)
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=[])

    install_main_client(ingest, monkeypatch, handler)
    asyncio.run(ingest.main())
    assert len(requests) == 3  # FLR, CME, and the optional GOES supplement.
    assert all(r.url.params["startDate"] == "2026-10-12" for r in requests[:2])
    assert output.exists()
