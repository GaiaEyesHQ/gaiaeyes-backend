"""History publication regressions; all network traffic uses synthetic responses."""

from copy import deepcopy
from collections import Counter
import datetime as dt
import errno
import http.client
import io
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse

import pytest
import yaml

from scripts import build_compare_series as compare
from scripts import history_json as history
from scripts import ingest_usgs_history as ingest
from scripts import supabase_storage as storage
from scripts import sync_quakes_history as sync


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def histories():
    now = dt.datetime.now(dt.timezone.utc)
    today = now.date().isoformat()
    yesterday = (now.date() - dt.timedelta(days=1)).isoformat()
    stamp = now.isoformat().replace("+00:00", "Z")
    quakes = {
        "timestamp_utc": stamp,
        "daily": [{"date": yesterday, "all": 20}, {"date": today, "all": 0}],
        "monthly": [{"month": today[:7], "all": 20}],
        "series": {key: [[yesterday, 20], [today, 0]] for key in history.QUAKE_DAILY},
    }
    quakes["series"].update({key: [[today[:7], 20]] for key in ("m5p_monthly", "m6p_monthly")})
    space = {"timestamp_utc": stamp, "series": {key: [[yesterday, 3.5]] for key in history.SPACE_DAILY}}
    return quakes, space


@pytest.fixture(autouse=True)
def isolate_network(monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("Unexpected live network call")
    monkeypatch.setattr(sync.urllib.request, "urlopen", unexpected)
    monkeypatch.setattr(storage.requests, "post", unexpected)
    monkeypatch.setenv("SUPABASE_URL", "https://storage.example.invalid")
    monkeypatch.setenv("BUCKET", "space-visuals")
    monkeypatch.setattr(storage, "SUPABASE_URL", "https://storage.example.invalid")
    monkeypatch.setattr(storage, "BUCKET", "space-visuals")
    monkeypatch.setattr(storage, "SERVICE_KEY", "synthetic-do-not-log")


def public_response(monkeypatch, data):
    calls = []
    def open_url(request, **kwargs):
        calls.append(request)
        return io.BytesIO(json.dumps(data).encode())
    monkeypatch.setattr(sync.urllib.request, "urlopen", open_url)
    return calls


def invoke(monkeypatch, mode, path):
    monkeypatch.setenv("OUTPUT_JSON_PATH", str(path))
    monkeypatch.setattr(sys, "argv", ["sync_quakes_history.py", mode])
    return sync.main()


def test_publish_uses_json_object_and_verifies_anonymous_readback(tmp_path, histories, monkeypatch, capsys):
    quakes, _ = histories
    path = tmp_path / "media/data/quakes_history.json"
    path.parent.mkdir(parents=True)
    raw = json.dumps(quakes).encode()
    path.write_bytes(raw)
    uploads = []
    def post(url, **kwargs):
        uploads.append((url, kwargs))
        return type("Response", (), {"status_code": 201})()
    monkeypatch.setattr(storage.requests, "post", post)
    reads = public_response(monkeypatch, quakes)
    assert invoke(monkeypatch, "publish", path) == 0
    assert not (tmp_path / "media/images/space").exists()
    assert len(uploads) == 1
    url, kwargs = uploads[0]
    assert url.endswith("/storage/v1/object/space-visuals/data/quakes_history.json")
    assert kwargs["data"] == raw
    assert kwargs["headers"]["Content-Type"] == "application/json"
    assert kwargs["headers"]["x-upsert"] == "true"
    assert len(reads) == 1
    assert reads[0].full_url.startswith(sync.public_url() + "?v=")
    assert not reads[0].has_header("Authorization")
    output = capsys.readouterr()
    assert "newest_quake_day=" in output.out
    assert "synthetic-do-not-log" not in output.out + output.err


@pytest.mark.parametrize("contents", [None, "", "{invalid", "null", "[]", "{}"])
def test_invalid_or_missing_json_fails_before_upload(tmp_path, monkeypatch, contents):
    path = tmp_path / "quakes_history.json"
    if contents is not None:
        path.write_text(contents)
    assert invoke(monkeypatch, "publish", path) == 1


@pytest.mark.parametrize("status", [400, 401, 403, 500])
def test_storage_publication_failure_is_not_success(tmp_path, histories, monkeypatch, capsys, status):
    path = tmp_path / "quakes_history.json"
    path.write_text(json.dumps(histories[0]))
    monkeypatch.setattr(storage.requests, "post", lambda *a, **kw: type(
        "Response", (), {"status_code": status, "text": "synthetic-do-not-log"})())
    assert invoke(monkeypatch, "publish", path) == 1
    error = capsys.readouterr().err
    assert "history upload failed" in error
    assert "synthetic-do-not-log" not in error


@pytest.mark.parametrize("failure", ["missing", "network", "invalid", "mismatch"])
def test_upload_success_requires_matching_public_json(tmp_path, histories, monkeypatch, failure):
    quakes, _ = histories
    path = tmp_path / "quakes_history.json"
    path.write_text(json.dumps(quakes))
    monkeypatch.setattr(storage, "upload_bytes", lambda *a: sync.public_url())
    def open_url(*args, **kwargs):
        if failure == "missing":
            raise urllib.error.HTTPError(sync.public_url(), 404, "NoSuchKey", {}, None)
        if failure == "network":
            raise urllib.error.URLError("unreachable")
        if failure == "invalid":
            return io.BytesIO(b"not JSON")
        different = deepcopy(quakes)
        different["series"]["m5p_daily"][0][1] += 1
        return io.BytesIO(json.dumps(different).encode())
    monkeypatch.setattr(sync.urllib.request, "urlopen", open_url)
    assert invoke(monkeypatch, "publish", path) == 1


def test_fetch_preserves_public_contract_and_needs_no_write_credentials(tmp_path, histories, monkeypatch):
    monkeypatch.setattr(storage, "SERVICE_KEY", None)
    reads = public_response(monkeypatch, histories[0])
    path = tmp_path / "media/data/quakes_history.json"
    assert invoke(monkeypatch, "fetch", path) == 0
    assert json.loads(path.read_text()) == histories[0]
    assert not reads[0].has_header("Authorization")


def test_fetch_rejects_stale_data_without_replacing_local_copy(tmp_path, histories, monkeypatch):
    quakes, _ = histories
    quakes["series"]["all_daily"] = [["2025-11-26", 20]]
    public_response(monkeypatch, quakes)
    path = tmp_path / "quakes_history.json"
    path.write_text("existing published file")
    assert invoke(monkeypatch, "fetch", path) == 1
    assert path.read_text() == "existing published file"


@pytest.mark.parametrize("kind", ["generation", "points", "zero_filled", "future", "empty", "invalid", "nan", "boolean", "negative"])
def test_quake_validation_rejects_bad_or_stale_inputs(histories, kind):
    quakes, _ = histories
    if kind == "generation":
        quakes["timestamp_utc"] = "2025-11-26T05:00:00Z"
    elif kind == "points":
        quakes["series"]["m5p_daily"] = [["2025-11-26", 20]]
    elif kind == "zero_filled":
        today = dt.datetime.now(dt.timezone.utc).date().isoformat()
        quakes["series"]["all_daily"] = [["2025-11-26", 20], [today, 0]]
    elif kind == "future":
        quakes["timestamp_utc"] = "2099-01-01T00:00:00Z"
    elif kind == "empty":
        quakes["series"]["m6p_daily"] = []
    else:
        quakes["series"]["all_daily"][-1][1] = {
            "invalid": "twenty", "nan": float("nan"), "boolean": True, "negative": -1,
        }[kind]
    with pytest.raises(ValueError):
        history.validate_quakes_history(quakes)


def write_inputs(tmp_path, histories, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    for name, payload in zip(("quakes_history", "space_history"), histories):
        (data / f"{name}.json").write_text(json.dumps(payload))
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path))
    monkeypatch.delenv("OUTPUT_JSON_PATH", raising=False)
    return data


def test_compare_preserves_series_labels_and_valid_utc_stamp(tmp_path, histories, monkeypatch):
    data = write_inputs(tmp_path, histories, monkeypatch)
    compare.main()
    output = json.loads((data / "compare_series.json").read_text())
    expected = {**histories[0]["series"], "m4p_daily": [], **histories[1]["series"]}
    assert output["series"] == expected
    assert set(output["labels"]) == set(expected)
    assert output["timestamp_utc"].endswith("Z")
    assert set(output) == {"timestamp_utc", "series", "labels", "meta"}


@pytest.mark.parametrize("source", ["quakes_history", "space_history"])
@pytest.mark.parametrize("failure", ["missing", "malformed", "empty", "old_stamp", "old_points"])
def test_compare_does_not_overwrite_output_from_bad_history(tmp_path, histories, monkeypatch, source, failure):
    data = write_inputs(tmp_path, histories, monkeypatch)
    path = data / f"{source}.json"
    payload = json.loads(path.read_text())
    if failure == "missing":
        path.unlink()
    elif failure == "malformed":
        path.write_text("invalid JSON")
    else:
        if failure == "old_stamp":
            payload["timestamp_utc"] = "2025-11-26T05:00:00Z"
        else:
            key = "all_daily" if source == "quakes_history" else "kp_daily_max"
            payload["series"][key] = [] if failure == "empty" else [["2025-11-26", 20]]
        path.write_text(json.dumps(payload))
    output = data / "compare_series.json"
    output.write_text("last good comparison")
    with pytest.raises(ValueError, match=source):
        compare.main()
    assert output.read_text() == "last good comparison"


def test_actual_generator_contract_is_accepted(monkeypatch):
    yesterday = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)
    monkeypatch.setattr(ingest, "DAYS", 3)
    monkeypatch.setattr(ingest, "fetch_usgs", lambda *args: {
        "features": [{"properties": {"mag": 5.5, "time": int(yesterday.timestamp() * 1000)}}]
    })
    history.validate_quakes_history(ingest.build())


@pytest.mark.parametrize("days", [1, 30, 31, 60, 61, 730])
@pytest.mark.parametrize("at_midnight", [False, True])
def test_generator_covers_every_chunk_transition_once(monkeypatch, days, at_midnight):
    cutoff = dt.datetime(2026, 10, 13, 12, 34, 56, 789000, tzinfo=dt.timezone.utc)
    if at_midnight:
        cutoff = cutoff.replace(hour=0, minute=0, second=0, microsecond=0)
    start = (cutoff - dt.timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    stamps = {start + dt.timedelta(days=i, milliseconds=offset)
              for i in range(days) for offset in (0, 1, 12 * 3600 * 1000, 86400000 - 1)}
    stamps.update([start - dt.timedelta(milliseconds=1), cutoff - dt.timedelta(milliseconds=1),
                   cutoff, cutoff + dt.timedelta(milliseconds=1)])
    events = [{"properties": {"mag": 6.3, "time": int(stamp.timestamp() * 1000)}}
              for stamp in sorted(stamps)]
    calls = []

    class FixedDatetime(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return cutoff

    def inclusive_usgs(first, last):
        # Match USGS's inclusive endpoints, including duplicates at chunk edges.
        first, last = dt.datetime.fromisoformat(first), dt.datetime.fromisoformat(last)
        calls.append((first, last))
        return {"features": [event for event in events
                             if first.timestamp() * 1000 <= event["properties"]["time"]
                             <= last.timestamp() * 1000]}

    monkeypatch.setattr(ingest.dt, "datetime", FixedDatetime)
    monkeypatch.setattr(ingest, "DAYS", days)
    monkeypatch.setattr(ingest, "MONTHS", 30)
    monkeypatch.setattr(ingest, "fetch_usgs", inclusive_usgs)
    output = ingest.build()
    expected = Counter(stamp.date().isoformat() for stamp in stamps if start <= stamp < cutoff)
    assert len(output["daily"]) == days
    for row in output["daily"]:
        assert row == {"date": row["date"], "all": expected[row["date"]],
                       "m4p": expected[row["date"]], "m5p": expected[row["date"]],
                       "m6p": expected[row["date"]], "m7p": 0}
    monthly = Counter()
    for day, count in expected.items():
        monthly[day[:7]] += count
    for row in output["monthly"]:
        assert row["all"] == row["m5p"] == row["m6p"] == monthly[row["month"]]
    for key in ("all_daily", "m5p_daily", "m6p_daily"):
        assert output["series"][key] == [[row["date"], expected[row["date"]]] for row in output["daily"]]
    if start < cutoff:
        assert calls[0][0] == start and calls[-1][1] == cutoff
        assert all(first.tzinfo == last.tzinfo == dt.timezone.utc for first, last in calls)
        assert all(dt.timedelta(0) < last - first <= dt.timedelta(days=30) for first, last in calls)
        assert all(previous[1] == following[0] for previous, following in zip(calls, calls[1:]))
    else:
        assert calls == []
    assert output["daily"][-1]["all"] == expected[cutoff.date().isoformat()]
    assert (output["daily"][-1]["all"] == 0) if at_midnight else (output["daily"][-1]["all"] > 0)
    assert cutoff.isoformat().replace("+00:00", "Z") in output["meta"]["note"]


def test_generator_keeps_captured_cutoff_when_run_crosses_midnight(monkeypatch):
    cutoff = dt.datetime(2026, 10, 13, 23, 59, tzinfo=dt.timezone.utc)
    finished = cutoff + dt.timedelta(minutes=2)
    clock = iter([cutoff, finished])

    class AdvancingDatetime(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return next(clock)

    calls = []
    def fetch(first, last):
        calls.append((first, last))
        return {"features": [{"properties": {"mag": 5, "time": int((cutoff - dt.timedelta(seconds=1)).timestamp() * 1000)}}]}
    monkeypatch.setattr(ingest.dt, "datetime", AdvancingDatetime)
    monkeypatch.setattr(ingest, "DAYS", 1)
    monkeypatch.setattr(ingest, "fetch_usgs", fetch)
    output = ingest.build()
    assert calls == [("2026-10-13T00:00:00+00:00", cutoff.isoformat())]
    assert output["daily"][0]["date"] == "2026-10-13"
    assert output["daily"][0]["all"] == 1
    assert output["timestamp_utc"] == "2026-10-14T00:01:00Z"


@pytest.mark.parametrize("key", history.QUAKE_MONTHLY)
@pytest.mark.parametrize("bad", [None, [], "not an array", [["not a month", 3]], [["2025-11", 3]], [["2099-01", 3]]])
def test_missing_or_malformed_monthly_series_fail_before_publication(tmp_path, histories, monkeypatch, key, bad):
    quakes, _ = histories
    if bad is None:
        del quakes["series"][key]
    else:
        quakes["series"][key] = bad
    path = tmp_path / "quakes_history.json"
    path.write_text(json.dumps(quakes))
    assert invoke(monkeypatch, "publish", path) == 1
    with pytest.raises(ValueError, match=key):
        history.validate_quakes_history(quakes)


@pytest.mark.parametrize("key", ["m4p_daily", "m4p_monthly", "m5p_monthly", "m6p_monthly"])
@pytest.mark.parametrize("bad", [None, [], "not an array", [["bad date", 3]], "negative", "fractional", "nan", "duplicate"])
def test_malformed_optional_and_monthly_series_cannot_reach_compare(tmp_path, histories, monkeypatch, key, bad):
    quakes, _ = histories
    date = dt.datetime.now(dt.timezone.utc).date().isoformat()
    date = date[:7] if key.endswith("_monthly") else date
    if bad in ("negative", "fractional", "nan", "duplicate"):
        point = [date, {"negative": -1, "fractional": 1.5, "nan": float("nan"), "duplicate": 1}[bad]]
        bad = [point, point] if bad == "duplicate" else [point]
    quakes["series"][key] = bad
    data = write_inputs(tmp_path, histories, monkeypatch)
    output = data / "compare_series.json"
    output.write_text("last good comparison")
    with pytest.raises(ValueError, match=key):
        compare.main()
    assert output.read_text() == "last good comparison"


def test_optional_m4_daily_is_preserved_when_present(tmp_path, histories, monkeypatch):
    quakes, _ = histories
    quakes["series"]["m4p_daily"] = deepcopy(quakes["series"]["all_daily"])
    data = write_inputs(tmp_path, histories, monkeypatch)
    compare.main()
    output = json.loads((data / "compare_series.json").read_text())
    assert output["series"]["m4p_daily"] == quakes["series"]["m4p_daily"]


def test_workflows_publish_before_compare_and_commit_the_fetched_history():
    workflow = lambda name: yaml.load((ROOT / ".github/workflows" / name).read_text(), Loader=yaml.BaseLoader)
    publisher = workflow("quakes-history.yml")
    consumer = workflow("compare-series.yml")
    steps = publisher["jobs"]["run"]["steps"]
    upload = next(step for step in steps if "sync_quakes_history.py publish" in step.get("run", ""))
    generate = next(step for step in steps if "ingest_usgs_history.py" in step.get("run", ""))
    assert upload["env"]["OUTPUT_JSON_PATH"] == generate["env"]["OUTPUT_JSON_PATH"]
    assert upload["env"]["BUCKET"] == "space-visuals"
    assert steps.index(generate) < steps.index(upload)
    assert "continue-on-error" not in publisher["jobs"]["run"]
    for step in (generate, upload):
        assert "continue-on-error" not in step
        assert "if" not in step  # Default success() skips upload after generation fails.
    assert "space_visuals_upload_to_supabase.py" not in str(steps)
    assert "schedule" not in consumer["on"]
    assert consumer["on"]["workflow_run"] == {
        "workflows": ["quakes-history"], "types": ["completed"], "branches": ["main"],
    }
    job = consumer["jobs"]["run"]
    assert publisher["concurrency"] == consumer["concurrency"] == {
        "group": "quakes-history-publication", "cancel-in-progress": "false",
    }
    assert "github.event.workflow_run.conclusion == 'success'" in job["if"]
    runs = [step.get("run", "") for step in job["steps"]]
    fetch = next(i for i, run in enumerate(runs) if "sync_quakes_history.py fetch" in run)
    build = next(i for i, run in enumerate(runs) if "build_compare_series.py" in run)
    commit = next(i for i, run in enumerate(runs) if "publish_compare_series.sh gaiaeyes-media" in run)
    assert fetch < build < commit


class InterruptedBody(io.BytesIO):
    status = 200

    def __init__(self, error):
        super().__init__(b'{"features":[')
        self.error = error

    def read(self, *args, **kwargs):
        raise self.error


def usgs_response(raw, status=200):
    response = io.BytesIO(raw)
    response.status = status
    return response


def usgs_page(*ids):
    return usgs_response(json.dumps({"features": [{"id": event_id} for event_id in ids]}).encode())


def mock_usgs_responses(monkeypatch, responses):
    responses = iter(responses)
    calls, sleeps = [], []

    def open_url(request, *, timeout):
        calls.append((request.full_url, timeout))
        response = next(responses)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(ingest.urllib.request, "urlopen", open_url)
    monkeypatch.setattr(ingest.time, "sleep", sleeps.append)
    return calls, sleeps


@pytest.fixture
def usgs_clock(monkeypatch):
    cutoff = dt.datetime(2026, 10, 14, 12, tzinfo=dt.timezone.utc)

    class FixedDatetime(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return cutoff

    monkeypatch.setattr(ingest.dt, "datetime", FixedDatetime)
    return cutoff


@pytest.mark.parametrize("error", [
    http.client.IncompleteRead(b"partial", 100),
    http.client.RemoteDisconnected("synthetic disconnect"),
    ConnectionResetError("synthetic reset"),
    TimeoutError("synthetic timeout"),
    urllib.error.URLError(TimeoutError("synthetic timeout")),
    urllib.error.URLError(ConnectionRefusedError("synthetic refusal")),
    urllib.error.URLError(socket.gaierror(socket.EAI_AGAIN, "temporary DNS failure")),
    ssl.SSLEOFError("synthetic TLS EOF"),
    OSError(errno.ENETUNREACH, "synthetic unreachable network"),
    OSError(errno.EHOSTUNREACH, "synthetic unreachable host"),
])
@pytest.mark.parametrize("during_read", [False, True])
def test_usgs_recovers_from_transient_open_and_full_body_failures(monkeypatch, error, during_read):
    failed = InterruptedBody(error) if during_read else error
    recovered = usgs_page("one")
    calls, sleeps = mock_usgs_responses(monkeypatch, [failed, recovered])
    result = ingest.fetch_usgs("2026-10-01", "2026-10-14")
    assert result == {"type": "FeatureCollection", "features": [{"id": "one"}]}
    assert len(calls) == 2 and calls[0] == calls[1]
    assert calls[0][1] == 60
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(calls[0][0]).query)
    assert query["limit"] == ["5000"] and query["offset"] == ["1"]
    assert query["starttime"] == ["2026-10-01"] and query["endtime"] == ["2026-10-14"]
    assert query["orderby"] == ["time-asc"]
    assert sleeps == [2]
    assert recovered.closed
    if during_read:
        assert failed.closed


@pytest.mark.parametrize("framing", [
    b"Content-Length: 200\r\n\r\n",
    b"Transfer-Encoding: chunked\r\n\r\n20\r\n",
])
def test_usgs_recovers_from_actual_http_response_truncation(monkeypatch, framing):
    class SyntheticSocket:
        def makefile(self, *args, **kwargs):
            return io.BytesIO(b"HTTP/1.1 200 OK\r\n" + framing + b'{"features":[')

    # Use the real HTTP parser against in-memory bytes; no socket is opened.
    truncated = http.client.HTTPResponse(SyntheticSocket())
    truncated.begin()
    calls, sleeps = mock_usgs_responses(monkeypatch, [truncated, usgs_page("recovered")])
    assert ingest.fetch_usgs("2026-10-01", "2026-10-14")["features"] == [{"id": "recovered"}]
    assert len(calls) == 2 and calls[0] == calls[1] and sleeps == [2]
    assert truncated.closed


@pytest.mark.parametrize("status", [408, 429, 500, 502, 503, 504])
def test_usgs_retries_selected_http_errors_and_closes_responses(monkeypatch, status):
    body = io.BytesIO(b"synthetic service failure")
    error = urllib.error.HTTPError(ingest.USGS_API, status, "synthetic", {}, body)
    calls, sleeps = mock_usgs_responses(monkeypatch, [error, usgs_page("one")])
    assert ingest.fetch_usgs("2026-10-01", "2026-10-14")["features"] == [{"id": "one"}]
    assert len(calls) == 2 and calls[0] == calls[1]
    assert sleeps == [2] and body.closed


@pytest.mark.parametrize("status", [400, 401, 403, 404, 413, 501])
def test_usgs_permanent_http_failure_does_not_retry(monkeypatch, status):
    body = io.BytesIO(b"synthetic permanent failure")
    error = urllib.error.HTTPError(ingest.USGS_API, status, "synthetic", {}, body)
    calls, sleeps = mock_usgs_responses(monkeypatch, [error])
    with pytest.raises(urllib.error.HTTPError) as caught:
        ingest.fetch_usgs("2026-10-01", "2026-10-14")
    assert caught.value is error
    assert len(calls) == 1 and sleeps == [] and body.closed


@pytest.mark.parametrize("error", [
    ssl.SSLCertVerificationError("synthetic certificate failure"),
    urllib.error.URLError(ssl.SSLCertVerificationError("synthetic certificate failure")),
    socket.gaierror(socket.EAI_NONAME, "permanent DNS failure"),
    urllib.error.URLError(socket.gaierror(socket.EAI_NONAME, "permanent DNS failure")),
    urllib.error.URLError("unknown URL type"),
    PermissionError("synthetic permission failure"),
])
def test_usgs_permanent_connection_failure_does_not_retry(monkeypatch, error):
    calls, sleeps = mock_usgs_responses(monkeypatch, [error])
    with pytest.raises(type(error)) as caught:
        ingest.fetch_usgs("2026-10-01", "2026-10-14")
    assert caught.value is error
    assert len(calls) == 1 and sleeps == []


@pytest.mark.parametrize("raw", [b'{"features":[', b'\xff', b''])
def test_usgs_malformed_response_fails_without_retry(monkeypatch, raw):
    response = usgs_response(raw)
    calls, sleeps = mock_usgs_responses(monkeypatch, [response])
    with pytest.raises((json.JSONDecodeError, UnicodeDecodeError)):
        ingest.fetch_usgs("2026-10-01", "2026-10-14")
    assert len(calls) == 1 and sleeps == [] and response.closed


@pytest.mark.parametrize("during_read", [False, True])
def test_usgs_exhaustion_is_bounded_and_propagates(monkeypatch, during_read, capsys):
    errors = [http.client.IncompleteRead(b"partial", 100) for _ in range(4)]
    responses = [InterruptedBody(error) for error in errors] if during_read else errors
    calls, sleeps = mock_usgs_responses(monkeypatch, responses)
    with pytest.raises(http.client.IncompleteRead) as caught:
        ingest.fetch_usgs("2026-10-01", "2026-10-14")
    assert caught.value is errors[-1]
    assert len(calls) == 4 and len(set(calls)) == 1
    assert sleeps == [2, 4, 8]
    assert capsys.readouterr().err.count("retrying in") == 3
    if during_read:
        assert all(response.closed for response in responses)


def test_usgs_retries_same_page_and_deduplicates_using_raw_offsets(monkeypatch):
    monkeypatch.setattr(ingest, "USGS_PAGE_SIZE", 2)
    failed = InterruptedBody(http.client.IncompleteRead(b"partial", 100))
    calls, sleeps = mock_usgs_responses(monkeypatch, [
        usgs_page("a", "b"), failed, usgs_page("b", "c"),
        usgs_page("c", "c"), usgs_page("d"),
    ])
    result = ingest.fetch_usgs("2026-10-01", "2026-10-14")
    assert result["features"] == [{"id": event_id} for event_id in ("a", "b", "c", "d")]
    offsets = [urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)["offset"][0] for url, _ in calls]
    assert offsets == ["1", "3", "3", "5", "7"]
    assert calls[1] == calls[2] and sleeps == [2] and failed.closed


def test_usgs_each_page_has_its_own_retry_allowance(monkeypatch):
    monkeypatch.setattr(ingest, "USGS_PAGE_SIZE", 2)
    calls, sleeps = mock_usgs_responses(monkeypatch, [
        *[TimeoutError("first page") for _ in range(3)], usgs_page("a", "b"),
        *[TimeoutError("second page") for _ in range(3)], usgs_page("c"),
    ])
    assert len(ingest.fetch_usgs("2026-10-01", "2026-10-14")["features"]) == 3
    assert sleeps == [2, 4, 8, 2, 4, 8]
    assert len(calls) == 8
    assert len(set(calls[:4])) == len(set(calls[4:])) == 1
    assert calls[0] != calls[4]


def test_usgs_empty_terminal_page_and_missing_ids_are_preserved(monkeypatch):
    monkeypatch.setattr(ingest, "USGS_PAGE_SIZE", 2)
    response = usgs_response(b'{"features":[{"properties":{}},{"properties":{}}]}')
    calls, sleeps = mock_usgs_responses(monkeypatch, [response, usgs_page()])
    assert ingest.fetch_usgs("2026-10-01", "2026-10-14")["features"] == [{"properties": {}}] * 2
    assert len(calls) == 2 and sleeps == []


@pytest.mark.parametrize("has_full_page", [False, True])
def test_usgs_no_data_204_terminates_pagination(monkeypatch, has_full_page):
    monkeypatch.setattr(ingest, "USGS_PAGE_SIZE", 2)
    empty = usgs_response(b"", status=204)
    responses = [usgs_page("a", "b"), empty] if has_full_page else [empty]
    calls, sleeps = mock_usgs_responses(monkeypatch, responses)
    expected = [{"id": "a"}, {"id": "b"}] if has_full_page else []
    assert ingest.fetch_usgs("2026-10-01", "2026-10-14")["features"] == expected
    assert len(calls) == len(responses) and sleeps == [] and empty.closed


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("failure_point", ["first_page", "later_page", "later_chunk"])
def test_usgs_exhaustion_leaves_last_good_output_untouched(
        tmp_path, monkeypatch, usgs_clock, existing, failure_point):
    path = tmp_path / "quakes_history.json"
    original = b'{"synthetic":"last good history"}\n'
    if existing:
        path.write_bytes(original)
    monkeypatch.setenv("OUTPUT_JSON_PATH", str(path))
    monkeypatch.setattr(ingest, "DAYS", 31 if failure_point == "later_chunk" else 1)
    monkeypatch.setattr(ingest, "USGS_PAGE_SIZE", 2)
    first_page = [] if failure_point == "first_page" else [
        usgs_page("a", "b") if failure_point == "later_page" else usgs_page("a")
    ]
    calls, sleeps = mock_usgs_responses(monkeypatch, first_page + [
        InterruptedBody(http.client.IncompleteRead(b"partial", 100)) for _ in range(4)
    ])
    with pytest.raises(http.client.IncompleteRead):
        ingest.main()
    if existing:
        assert path.read_bytes() == original
    else:
        assert not path.exists()
    assert len(calls) == len(first_page) + 4 and sleeps == [2, 4, 8]


def test_usgs_recovered_download_writes_unchanged_history_contract(tmp_path, monkeypatch, usgs_clock):
    path = tmp_path / "quakes_history.json"
    monkeypatch.setenv("OUTPUT_JSON_PATH", str(path))
    monkeypatch.setattr(ingest, "DAYS", 1)
    event = {"id": "synthetic-quake", "properties": {
        "mag": 6.3, "time": int((usgs_clock - dt.timedelta(minutes=1)).timestamp() * 1000),
    }}
    calls, sleeps = mock_usgs_responses(monkeypatch, [
        InterruptedBody(http.client.IncompleteRead(b"partial", 100)),
        usgs_response(json.dumps({"features": [event, event]}).encode()),
    ])
    ingest.main()
    output = json.loads(path.read_text())
    assert set(output) == {"timestamp_utc", "window", "daily", "monthly", "series", "meta"}
    assert output["daily"] == [{"date": "2026-10-14", "all": 1, "m4p": 1, "m5p": 1, "m6p": 1, "m7p": 0}]
    assert output["series"]["all_daily"] == [["2026-10-14", 1]]
    assert output["series"]["m6p_monthly"] == [["2026-10", 1]]
    assert len(calls) == 2 and sleeps == [2]


def test_usgs_exhaustion_exits_nonzero_without_writing(tmp_path):
    path = tmp_path / "quakes_history.json"
    path.write_bytes(b"synthetic last good file\n")
    code = '''
import http.client, runpy, time, urllib.request
def interrupted(*args, **kwargs):
    raise http.client.IncompleteRead(b"synthetic partial", 100)
urllib.request.urlopen = interrupted
time.sleep = lambda seconds: None
runpy.run_path("scripts/ingest_usgs_history.py", run_name="__main__")
'''
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True,
                            timeout=10, env={"PATH": os.environ.get("PATH", ""),
                                             "OUTPUT_JSON_PATH": str(path), "HISTORY_DAYS": "2"})
    assert result.returncode != 0
    assert "IncompleteRead" in result.stderr and result.stderr.count("retrying in") == 3
    assert "wrote ->" not in result.stdout
    assert path.read_bytes() == b"synthetic last good file\n"
