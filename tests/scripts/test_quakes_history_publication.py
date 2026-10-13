"""History publication regressions; all network traffic uses synthetic responses."""

from copy import deepcopy
from collections import Counter
import datetime as dt
import io
import json
from pathlib import Path
import sys
import urllib.error

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
