"""Offline API-to-PHP contract checks using the actual public-post SELECT.

SQLite exercises the SELECT's filtering/order with synthetic rows. It is not a
Postgres schema or hosted-permission test. All other I/O is replaced locally.
"""
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from zoneinfo import ZoneInfo

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import settings
from app.routers import summary
from app.security import auth

USER = "00000000-0000-4000-8000-000000000042"
HEADERS = {"Authorization": "Bearer synthetic-read-token", "X-Dev-UserId": USER}
pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


class PublicPosts:
    def __init__(self, today):
        self.today = today
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.execute("attach database ':memory:' as content")
        self.db.execute("""create table content.daily_posts (
            day text, user_id text, platform text, title text, caption text,
            body_markdown text, hashtags text, metrics_json text,
            created_at text, updated_at text, sources_json text)""")
        self.queries = []
        self.fail_post = False
        self.rollbacks = 0

    def add(self, day, title="Synthetic public edition", platform="default", user=None):
        self.db.execute("insert into content.daily_posts values (?,?,?,?,?,?,?,?,?,?,?)", (
            day.isoformat(), user, platform, title, "A useful synthetic check-in.",
            "What may help\nKeep your usual supportive routines.", "#synthetic", "{}",
            "2020-01-01T00:00:00+00:00", "2099-01-01T00:00:00+00:00", "{}",
        ))

    def cursor(self, **kwargs):
        owner = self

        class Cursor:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def execute(self, query, params):
                if "from content.daily_posts" in query:
                    owner.queries.append((query, params))
                    if owner.fail_post:
                        raise TimeoutError("synthetic daily post timeout")
                    sql_params = tuple(p.isoformat() if isinstance(p, date) else p for p in params)
                    row = owner.db.execute(query.replace("%s", "?"), sql_params).fetchone()
                    self.row = dict(row) if row else None
                    if self.row and self.row.get("post_day") is not None:
                        # psycopg returns the table's date column as datetime.date.
                        self.row["post_day"] = date.fromisoformat(self.row["post_day"])
                elif "select max(day)" in query and "from marts.daily_features" in query:
                    self.row = {"max_day": owner.today, "total_rows": 1}
                else:
                    raise AssertionError(f"Unexpected SQL in isolated fixture: {query}")

            async def fetchone(self):
                return self.row

        return Cursor()

    async def rollback(self):
        self.rollbacks += 1


@pytest.fixture
def api(monkeypatch):
    today = datetime.now(ZoneInfo("America/Chicago")).date()
    posts = PublicPosts(today)
    state = {"cache": None, "cache_writes": [], "mode": "today"}
    app = FastAPI()
    # Same router/auth registration as app.main; no application startup jobs.
    app.include_router(summary.router, dependencies=[Depends(auth.require_read_auth)])

    async def connection():
        yield posts

    async def current_day(*args):
        return today

    def feature_row(day=today):
        return {"user_id": USER, "day": day, "steps_total": 42,
                "updated_at": datetime.now(timezone.utc)}

    async def mart(*args):
        if state["mode"] == "cache":
            return None, RuntimeError("synthetic mart failure")
        if state["mode"] == "freshened":
            return None, None
        return feature_row(), None

    async def daily_summary(*args):
        return feature_row()

    async def no_row(*args):
        return None

    async def empty(*args):
        return {}

    async def get_cache(*args):
        return state["cache"]

    async def set_cache(user, payload):
        assert user == USER
        state["cache_writes"].append(dict(payload))

    async def no_refresh(*args, **kwargs):
        return False

    app.dependency_overrides[summary._features_db_dependency] = connection
    monkeypatch.setattr(settings, "DEV_BEARER", "synthetic-dev-token")
    monkeypatch.setattr(auth, "READ_TOKENS", {"synthetic-read-token"})
    monkeypatch.setattr(auth, "WRITE_TOKENS", set())
    monkeypatch.setattr(auth, "PUBLIC_READ_PATHS", list(auth.DEFAULT_PUBLIC_READ))
    monkeypatch.setattr(auth, "decode_supabase_token", lambda token: None)
    monkeypatch.setattr(summary, "_current_day_local", current_day)
    monkeypatch.setattr(summary, "_query_mart_with_retry", mart)
    monkeypatch.setattr(summary, "_fetch_daily_summary", daily_summary)
    monkeypatch.setattr(summary, "_fetch_mart_row", no_row)
    monkeypatch.setattr(summary, "_fetch_snapshot_row", no_row)
    for name in ("_fetch_sleep_aggregate", "_fetch_space_weather_daily", "_fetch_current_space_weather",
                 "_fetch_latest_ulf_context", "_fetch_schumann_row"):
        monkeypatch.setattr(summary, name, empty)
    monkeypatch.setattr(summary, "get_last_good", get_cache)
    monkeypatch.setattr(summary, "set_last_good", set_cache)
    monkeypatch.setattr(summary, "_maybe_schedule_background_refresh", no_refresh)
    monkeypatch.setattr(summary, "_db_pressure_reason", lambda *args: None)
    monkeypatch.delenv("MEDIA_BASE_URL", raising=False)
    monkeypatch.delenv("GAIA_MEDIA_BASE", raising=False)
    yield app, posts, state
    posts.db.close()


async def response_for(api, headers=HEADERS):
    async with AsyncClient(transport=ASGITransport(app=api[0]), base_url="http://synthetic.test") as client:
        return await client.get("/v1/features/today?tz=America/Chicago", headers=headers)


def render_response(response, tmp_path, expected_state, expected_text):
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True and payload["error"] is None
    serialized = response.text
    assert "synthetic-read-token" not in serialized
    assert "PRIVATE SENTINEL" not in serialized and "FUTURE SENTINEL" not in serialized
    input_path = tmp_path / "api-response.json"
    input_path.write_text(json.dumps(payload, indent=2) + "\n")
    result = subprocess.run([
        "php", str(ROOT / "tests/fixtures/wordpress_experience.php"),
        "api-response", "earthscope", str(input_path),
    ], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0 and not result.stderr, result.stderr
    rendered = json.loads(result.stdout)
    html = rendered["html"]
    assert expected_text in html
    if expected_state:
        assert f'data-state="{expected_state}"' in html
    assert len(rendered["requests"]) == 1
    assert "/v1/features/today?" in rendered["requests"][0]["url"]
    assert "fixture-server-secret" not in html
    (tmp_path / "earthscope.html").write_text(html)
    (tmp_path / "case.json").write_text(json.dumps({
        "expected_state": expected_state, "expected_text": expected_text,
        "feature_day": payload["data"]["day"], "post_day": payload["data"]["post_day"],
        "post_published_at": payload["data"]["post_published_at"],
        "http_requests": "One intercepted features request; zero real HTTP requests",
    }, indent=2) + "\n")
    return html


@pytest.mark.parametrize("age,mode", [(0, "today"), (1, "today"), (0, "freshened")])
async def test_selected_public_post_reaches_php_with_its_own_day(api, tmp_path, age, mode):
    _, posts, state = api
    state["mode"] = mode
    post_day = posts.today - timedelta(days=age)
    posts.add(post_day)
    posts.add(post_day, "Website variant", "web")
    posts.add(post_day, "Social variant", "facebook")
    posts.add(post_day - timedelta(days=1), "Older public edition")
    posts.add(posts.today, "PRIVATE SENTINEL", user=USER)
    posts.add(posts.today + timedelta(days=1), "FUTURE SENTINEL")
    response = await response_for(api)
    data = response.json()["data"]
    assert data["day"] == posts.today.isoformat()
    assert data["post_title"] == "Synthetic public edition"
    assert data["post_day"] == post_day.isoformat()
    assert data["post_published_at"] is None  # Neither created_at nor updated_at is publication time.
    assert data["steps_total"] == 42
    assert len(posts.queries) == 1 and posts.queries[0][1] == (posts.today,)
    assert state["cache_writes"][-1]["post_day"] == post_day
    html = render_response(response, tmp_path, "current" if age == 0 else "stale",
                           "Current edition" if age == 0 else "Earlier edition")
    assert f"Edition {post_day.isoformat()} (America/Chicago)" in html
    assert " · Published " not in html


@pytest.mark.parametrize("metadata", [
    {},
    {"post_day": None, "post_published_at": None},
    {"post_day": "2026-02-30", "post_published_at": "not a timestamp"},
    {"post_day": True, "post_published_at": 123456789},
    {"post_day": "2026-09-21T12:00:00Z", "post_published_at": "2026-09-21"},
    {"post_day": datetime(2026, 9, 21), "post_published_at": "2026-09-21T12:00:00"},
], ids=["legacy", "null", "invalid", "wrong-types", "date-time-mismatch", "naive-time"])
async def test_cached_missing_or_invalid_metadata_stays_unknown(api, tmp_path, metadata):
    _, posts, state = api
    state["mode"] = "cache"
    state["cache"] = {"day": posts.today.isoformat(), "updated_at": datetime.now(timezone.utc).isoformat(),
                      "source": "snapshot", "post_title": "Synthetic cached edition", **metadata}
    posts.add(posts.today)  # A separate current row must not date cached content.
    response = await response_for(api)
    data = response.json()["data"]
    assert data["post_day"] is None and data["post_published_at"] is None
    assert response.json()["diagnostics"]["cache_fallback"] is True
    assert not posts.queries
    # Existing snapshot fallback can re-cache the same content without enrichment.
    assert state["cache_writes"][-1].get("post_day") == metadata.get("post_day")
    html = render_response(response, tmp_path, "unknown", "Publication day unavailable")
    assert " · Edition " not in html and " · Published " not in html


async def test_cached_explicit_metadata_preserves_edition_and_timestamp_instant(api, tmp_path):
    _, posts, state = api
    state["mode"] = "cache"
    yesterday = posts.today - timedelta(days=1)
    stamp = datetime.combine(yesterday, datetime.min.time(), ZoneInfo("America/Chicago"))
    state["cache"] = {"day": posts.today.isoformat(), "source": "snapshot",
                      "post_title": "Synthetic cached edition", "post_day": yesterday.isoformat(),
                      "post_published_at": stamp.isoformat()}
    response = await response_for(api)
    assert response.json()["data"]["post_published_at"] == stamp.astimezone(timezone.utc).isoformat()
    assert not posts.queries
    html = render_response(response, tmp_path, "stale", "Earlier edition")
    assert " · Published " in html


@pytest.mark.parametrize("failure", [False, True], ids=["no-public-post", "post-query-timeout"])
async def test_absent_or_failed_post_keeps_feature_data_and_unavailable_edition(api, tmp_path, failure):
    _, posts, state = api
    posts.add(posts.today, "PRIVATE SENTINEL", user=USER)
    posts.add(posts.today + timedelta(days=1), "FUTURE SENTINEL")
    posts.fail_post = failure
    response = await response_for(api)
    data = response.json()["data"]
    assert data["steps_total"] == 42 and data["post_title"] is None
    assert data["post_day"] is None and data["post_published_at"] is None
    assert bool(posts.rollbacks) is failure
    errors = response.json()["diagnostics"].get("enrichment_errors", [])
    assert any("daily post timed out" in item for item in errors) is failure
    render_response(response, tmp_path, None, "EarthScope is unavailable")


@pytest.mark.parametrize("headers,status", [
    ({}, 401),
    ({"Authorization": "Bearer invalid-synthetic-token", "X-Dev-UserId": USER}, 401),
    ({"Authorization": "Bearer synthetic-read-token"}, 200),
], ids=["unauthenticated", "invalid-auth", "read-token-without-identity"])
async def test_metadata_does_not_expand_auth_or_anonymous_enrichment(api, headers, status):
    api[1].add(api[1].today)
    response = await response_for(api, headers)
    assert response.status_code == status
    assert not api[1].queries and not api[2]["cache_writes"]
    if status == 200:
        data = response.json()["data"]
        assert data["user_id"] is None and data["post_title"] is None
        assert data["post_day"] is None and data["post_published_at"] is None


async def test_database_unavailable_retains_production_error_envelope(api, monkeypatch):
    async def unavailable_connection():
        yield None

    api[0].dependency_overrides[summary._features_db_dependency] = unavailable_connection
    # The router has a legacy pytest-only error-data override; test the real envelope.
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    response = await response_for(api)
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False and body["data"] is None
    assert body["error"] == "db_unavailable"
    assert not api[1].queries and not api[2]["cache_writes"]
