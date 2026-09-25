"""Changed-path tests only: owned Unix-socket PG, synthetic copy, fake HTTP.

No model, external database, platform or publishing call is permitted.
"""
import copy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4
from unittest.mock import patch

import psycopg
import pytest
import requests
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("primary_queue_fixture", Path(__file__).with_name("test_earthscope_writer.py"))
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
postgres, database, anyio_backend = base.postgres, base.database, base.anyio_backend

from app.db import earthscope_writer as queue
from scripts import earthscope_local_primary as runner
from services import earthscope_local_primary as primary
from services.earthscope_delivery import DeliveryAttempt
from services.earthscope_writer_contract import DraftError, sha256, job_envelope

NOW = datetime(2026, 9, 24, 15, tzinfo=timezone.utc)
POLICY = {"acceptance_id": "synthetic-local-test", "validator_id": "synthetic-validator",
          "caption_profile": "synthetic-complete-profile"}
ENV = {"EARTHSCOPE_WRITER_MODE": "local_primary", **{"EARTHSCOPE_LOCAL_" + k.upper(): v for k, v in POLICY.items()},
       "SUPABASE_URL": "https://fixture.invalid", "SUPABASE_SERVICE_ROLE_KEY": "synthetic-no-access",
       "EARTHSCOPE_MEDIA_REVISION": "f" * 64, "FB_PAGE_ID": "synthetic-fb", "IG_USER_ID": "synthetic-ig"}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("External HTTP is forbidden in this test")
    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)


def bundle():
    value = {"schema_version": "1.0", "title": "Synthetic Context Check",
             "caption": "Synthetic review copy only. Keep today's observations separate from personal conclusions.",
             "snapshot": "The synthetic day contains dated observations. Missing signals remain unknown.",
             "affects": "Some people may notice changes. These fixture sentences are not live health guidance.",
             "playbook": "- Record your own context\n- Keep a useful routine\n- Compare dated observations",
             "voiceover": "Synthetic voiceover retained for compatibility; the scheduled reel stays music only.",
             "hashtags": "#Synthetic #Review #Fixture"}
    value["social_variants"] = {k: {"caption": value["caption"] if k == "default" else k + " " + value["caption"],
                                   "hashtags": value["hashtags"]} for k in ("default", "ig", "fb")}
    value["reel_story"] = {k: "Synthetic " + k + " copy." for k in primary.REEL_FIELDS}
    return value


def returned_row(now=NOW):
    facts = base.facts(now, "dated_production_facts")
    row = {"job_id": facts["job_id"], "job_version": 1, "day": now.date(),
           "facts_packet": facts, "facts_sha256": sha256(facts), "input_classification": "dated_production_facts",
           "deadline_at": now + timedelta(minutes=5), "lease_expires_at": now + timedelta(minutes=5),
           "claim_id": str(uuid4()), "acknowledgement_id": str(uuid4()), "status": "returned"}
    result = base.outcome(job_envelope(row), now=now)
    result["draft"]["bundle"] = bundle()
    result["draft"]["validation"]["provenance"].update(bundle_sha256=sha256(bundle()), caption_profile=POLICY["caption_profile"])
    row.update(outcome=result, outcome_sha256=sha256(result))
    return row


def post():
    return primary.publication_post(returned_row(), POLICY, now=NOW)


def test_default_off_and_explicit_operator_qualification():
    assert primary.writer_mode({}) == "legacy"
    assert primary.load_primary_post({}) is None
    for env in ({}, {"EARTHSCOPE_WRITER_MODE": "typo"}, {"EARTHSCOPE_WRITER_MODE": "local_primary"}):
        with pytest.raises(DraftError):
            primary.activation(env)
    assert primary.activation(ENV) == POLICY


def test_complete_return_maps_copy_verbatim_and_preserves_unknowns():
    value = post()
    for key in ("caption", "snapshot", "affects", "playbook", "voiceover", "reel_story"):
        assert value["metrics_json"]["sections"][key] == bundle()[key]
    assert value["metrics_json"]["social_variants"] == bundle()["social_variants"]
    assert value["metrics_json"]["quakes_count"] is None
    assert value["metrics_json"]["space_json"]["sw_now"] is None
    assert primary.daily_json(value)["timestamp_utc"] == value["metrics_json"]["facts_as_of"]


@pytest.mark.parametrize("mutation", ["failed", "stale", "hash", "binding", "validator", "profile", "missing_field", "missing_variant", "synthetic"])
def test_unqualified_return_never_maps_to_production(mutation):
    row = returned_row()
    now = NOW
    if mutation == "failed": row["status"] = "failed"
    elif mutation == "stale": now += timedelta(days=1)
    elif mutation == "hash": row["facts_packet"]["facts"]["kp_now"] = 9
    elif mutation == "binding": row["outcome"]["claim_id"] = str(uuid4())
    elif mutation == "validator": row["outcome"]["draft"]["validation"]["validator_id"] = "other"
    elif mutation == "profile": row["outcome"]["draft"]["validation"]["provenance"]["caption_profile"] = "older"
    elif mutation == "missing_field": del row["outcome"]["draft"]["bundle"]["snapshot"]
    elif mutation == "missing_variant": del row["outcome"]["draft"]["bundle"]["social_variants"]["fb"]
    elif mutation == "synthetic": row["input_classification"] = "synthetic_review_fixture"
    row["outcome"]["draft"]["validation"]["provenance"]["bundle_sha256"] = sha256(row["outcome"]["draft"]["bundle"])
    row["outcome_sha256"] = sha256(row["outcome"])
    with pytest.raises(DraftError):
        primary.publication_post(row, POLICY, now=now)


def test_acknowledged_same_day_return_remains_reusable_after_lease():
    row = returned_row()
    value = primary.publication_post(row, POLICY, now=NOW + timedelta(minutes=20))
    assert value == primary.publication_post(row, POLICY, now=NOW)


def test_all_consumers_reject_wrong_artifact_or_day(tmp_path):
    value = post()
    path = tmp_path / "post.json"
    path.write_text(json.dumps(value))
    env = {**ENV, "TARGET_DAY": value["day"], "EARTHSCOPE_PRIMARY_POST_PATH": str(path),
           "EARTHSCOPE_PRIMARY_POST_SHA256": sha256(value)}
    assert primary.load_primary_post(env, now=NOW) == value
    for altered, now in (({**env, "TARGET_DAY": "2026-09-23"}, NOW), (env, NOW + timedelta(days=1)),
                         ({**env, "EARTHSCOPE_PRIMARY_POST_SHA256": "a" * 64}, NOW)):
        with pytest.raises(DraftError): primary.load_primary_post(altered, now=now)


class Response:
    def __init__(self, value, code=200): self.value, self.status_code = value, code
    def json(self): return copy.deepcopy(self.value)


class Rest:
    def __init__(self, existing=None, fail_post=False):
        self.row, self.fail_post, self.calls = existing, fail_post, []
    def get(self, url, **kwargs):
        self.calls.append(("get", kwargs))
        return Response([self.row] if self.row else [])
    def post(self, url, **kwargs):
        self.calls.append(("post", kwargs))
        self.row = self.row or copy.deepcopy(kwargs["json"][0])
        if self.fail_post: raise requests.Timeout("synthetic lost acknowledgement")
        return Response([], 201)
    def patch(self, url, **kwargs):
        self.calls.append(("patch", kwargs))
        self.row.update(kwargs["json"])
        return Response([self.row])


def test_public_insert_readback_and_exact_retry_without_overwrite():
    value, http = post(), Rest()
    assert runner.publish_once(value, ENV, session=http) == "inserted_and_read_back"
    assert runner.publish_once(value, ENV, session=http) == "existing_exact_public_row"
    assert sum(k == "post" for k, _ in http.calls) == 1
    assert "ignore-duplicates" in http.calls[1][1]["headers"]["Prefer"]
    assert http.calls[0][1]["params"]["user_id"] == "is.null"


def test_public_conflict_and_uncertain_post_never_retry_blindly():
    value = post()
    other = {**value, "caption": "Already published legacy copy"}
    http = Rest(other)
    with pytest.raises(DraftError, match="publication_conflict"):
        runner.publish_once(value, ENV, session=http)
    assert len(http.calls) == 1
    http = Rest(fail_post=True)
    with pytest.raises(requests.Timeout): runner.publish_once(value, ENV, session=http)
    assert sum(k == "post" for k, _ in http.calls) == 1
    assert runner.publish_once(value, ENV, session=http) == "existing_exact_public_row"


def test_delivery_intent_blocks_duplicate_and_unknown_attempts():
    http, value = Rest(), post()
    first = DeliveryAttempt(value, "ig", "carousel", ENV, http)
    assert first.begin()
    second = DeliveryAttempt(value, "ig", "carousel", ENV, http)
    with pytest.raises(DraftError, match="reconciliation"): second.begin()
    first.finish({"success": True, "post_id": "synthetic-id"})
    assert second.begin() is False
    assert http.row["post_id"] == "synthetic-id"


def test_delivery_unknown_receipt_never_grants_second_publish():
    http, value = Rest(fail_post=True), post()
    first = DeliveryAttempt(value, "fb", "reel", ENV, http)
    with pytest.raises(requests.Timeout): first.begin()
    http.fail_post = False
    with pytest.raises(DraftError, match="reconciliation"):
        DeliveryAttempt(value, "fb", "reel", ENV, http).begin()


def test_failed_meta_result_is_durably_non_retryable():
    http = Rest()
    first = DeliveryAttempt(post(), "fb", "carousel", ENV, http)
    assert first.begin()
    with pytest.raises(DraftError, match="reconciliation"): first.finish({"success": False})
    assert http.row["state"] == "uncertain"


@pytest.fixture(scope="module")
def primary_schema(postgres):
    with psycopg.connect(**postgres[0]) as conn:
        conn.execute((ROOT / "supabase/migrations/20260924145345_earthscope_complete_public_copy_history.sql").read_text())


@pytest.mark.anyio
async def test_real_queue_retry_reuses_frozen_facts_and_ack(database, primary_schema, monkeypatch):
    calls = []
    async def collect(conn, day, *, now):
        calls.append(day)
        return base.facts(now, "dated_production_facts"), {}
    monkeypatch.setattr(runner, "qualified_public_facts", collect)
    now = datetime.now(timezone.utc)
    async with database("gaia_earthscope_writer_preparer") as conn:
        first = await runner.prepare_or_reuse(conn, now.date(), 1, base.WORKER, 30)
        second = await runner.prepare_or_reuse(conn, now.date(), 1, base.WORKER, 900)
        assert second["facts_sha256"] == first["facts_sha256"] and second["deadline_at"] == first["deadline_at"]
    assert len(calls) == 1
    async with database("gaia_earthscope_writer_backend") as conn:
        job = (await queue.claim_next(conn, base.WORKER, str(uuid4())))["job"]
        result = base.outcome(job)
        result["draft"]["bundle"] = bundle()
        result["draft"]["validation"]["provenance"].update(bundle_sha256=sha256(bundle()), caption_profile=POLICY["caption_profile"])
        await queue.return_outcome(conn, base.WORKER, result, sha256(result))
    async with database("gaia_earthscope_writer_preparer") as conn:
        value = await runner.await_post(conn, now.date(), 1, base.WORKER, 2, POLICY, "UTC")
        assert value["metrics_json"]["writer_source"]["facts_sha256"] == first["facts_sha256"]
    assert len(calls) == 1


@pytest.mark.anyio
async def test_real_queue_expiry_cannot_regenerate_or_increment_version(database, primary_schema, monkeypatch):
    now = datetime.now(timezone.utc)
    async with database("gaia_earthscope_writer_preparer") as conn:
        row = await queue.enqueue(conn, base.facts(now, "dated_production_facts"), 1, base.WORKER,
                                  now + timedelta(seconds=10), "dated_production_facts")
        await queue.expire(conn, base.WORKER, now + timedelta(seconds=11))
        with pytest.raises(DraftError, match="local_writer_expired"):
            await runner.await_post(conn, now.date(), 1, base.WORKER, 2, POLICY, "UTC")
        with pytest.raises(DraftError, match="job_version_conflict"):
            await runner.prepare_or_reuse(conn, now.date(), 2, base.WORKER, 2)


@pytest.mark.anyio
async def test_real_schema_public_only_history_and_cloud_delivery_privileges(database, primary_schema):
    from psycopg.types.json import Jsonb
    day = NOW.date()
    async with database() as conn:
        await conn.execute("delete from content.daily_posts where day is not null")
        for user in (None, str(uuid4())):
            await conn.execute("insert into content.daily_posts(day,updated_at,user_id,platform,title,metrics_json) values (%s,%s,%s,'default',%s,%s)",
                (day, NOW, user, "public fixture" if user is None else "private fixture",
                 Jsonb({"sections": {"snapshot": "PUBLIC" if user is None else "PRIVATE", "reel_story": {"hook": "public hook"}}})))
    async with database("gaia_earthscope_writer_preparer") as conn:
        row = await queue.one(conn, "select title,snapshot,reel_hook from content.earthscope_writer_public_history where day=%s", (day,))
        assert row == {"title": "public fixture", "snapshot": "PUBLIC", "reel_hook": "public hook"}
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            await conn.execute("select * from content.earthscope_delivery_attempts")
    for role in ("anon", "authenticated"):
        async with database(role) as conn:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                await conn.execute("select * from content.earthscope_delivery_attempts")
    async with database("service_role") as conn:
        await conn.execute("insert into content.earthscope_delivery_attempts(day,channel,post_sha256,destination_sha256,media_revision,attempt_id,state) values (%s,'ig_reel',%s,%s,%s,%s,'reserved')", (day, "a"*64, "b"*64, "c"*64, str(uuid4())))
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            await conn.execute("delete from content.earthscope_delivery_attempts")


def test_workflow_carries_frozen_post_date_media_and_music_only(tmp_path):
    workflow = yaml.safe_load((ROOT / ".github/workflows/gaia_eyes_daily.yml").read_text())
    jobs = workflow["jobs"]
    assert jobs["generate"]["env"]["EARTHSCOPE_WRITER_MODE"].endswith("|| 'legacy' }}")
    for name in ("render", "post", "reel"):
        env = jobs[name]["env"]
        assert "outputs.post_sha256" in env["EARTHSCOPE_PRIMARY_POST_SHA256"]
        assert "outputs.target_day" in env["TARGET_DAY"]
    assert jobs["reel"]["env"]["REEL_VOICE_ENABLED"] == "0"
    for job in jobs.values():
        for step in job["steps"]:
            if "run" in step:
                script = step["run"]
                # Github expressions are opaque to bash, replace only for parsing.
                import re
                script = re.sub(r"\$\{\{.*?\}\}", "fixture", script)
                checked = subprocess.run(["bash", "-n"], input=script, text=True, capture_output=True)
                assert checked.returncode == 0, (step["name"], checked.stderr)
    resolve = next(x["run"] for x in jobs["generate"]["steps"] if x.get("id") == "writer")
    output = tmp_path / "github-output"
    env = {"PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"], "PYTHONPATH": str(ROOT), "GITHUB_OUTPUT": str(output),
           "GITHUB_RUN_ID": "1", "GITHUB_RUN_ATTEMPT": "2", "REQUESTED_DAY": "2026-09-24"}
    result = subprocess.run(["bash", "-c", resolve], env=env, cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "writer_mode=legacy" in output.read_text() and "target_day=2026-09-24" in output.read_text()


@pytest.mark.parametrize("current_kp,maximum_kp", [(4.3, 4.33), (4.3, None), (None, 4.33), (None, None)])
def test_actual_renderer_uses_only_frozen_copy_and_facts(monkeypatch, tmp_path, current_kp, maximum_kp):
    with patch("dotenv.load_dotenv", return_value=False):
        from bots.earthscope_post import gaia_eyes_viral_bot as render
    value, captures = post(), {}
    value["metrics_json"].update(kp_now=current_kp, kp_max_24h=maximum_kp)
    monkeypatch.setattr(render, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(render, "LOG_PATH", tmp_path / "cards.log")
    monkeypatch.setattr(primary, "load_primary_post", lambda **kw: value)
    def forbidden(*args, **kwargs): pytest.fail("Live/fallback path called by local-primary renderer")
    for name in ("fetch_daily_features_for", "fetch_post_for", "fetch_kp_index", "resolve_space_weather_metrics",
                 "load_earthscope_card", "generate_daily_forecast", "git_commit_push", "write_json_csv"):
        monkeypatch.setattr(render, name, forbidden)
    monkeypatch.setattr(render, "render_stats_card_from_features", lambda day, feats, *a, **kw: captures.update(stats=feats, stats_primary=kw.get("observed_context")) or "stats")
    monkeypatch.setattr(render, "render_card", lambda energy, caption, *a, **kw: captures.update(caption=caption, caption_primary=kw.get("observed_context")) or "caption")
    def text_card(title, text, *a, **kw):
        captures["playbook" if title == "Optional actions" else "affects"] = text
        return "text"
    monkeypatch.setattr(render, "render_text_card", text_card)
    monkeypatch.setattr(render, "save_all_cards", lambda *args: [])
    monkeypatch.setattr(render, "save_reel_backgrounds", lambda *args: [])
    render.main(render.parse_args(["--dry-run"]))
    assert "QUICK TIP" not in captures["affects"]
    assert captures["stats_primary"] is captures["caption_primary"] is True
    assert captures["playbook"] == bundle()["playbook"]
    assert captures["affects"] == bundle()["affects"]
    assert captures["stats"]["sw_speed_avg"] == value["metrics_json"]["solar_wind_kms"]
    assert captures["stats"]["solar_wind_label"] == "SW speed (observed)"
    assert captures["stats"].get("kp_max") == maximum_kp
    assert captures["stats"].get("kp_current") == current_kp


def test_actual_meta_uses_exact_variant_and_no_latest_lookup(monkeypatch):
    with patch("dotenv.load_dotenv", return_value=False):
        from bots.earthscope_post import meta_poster as meta
    value, captured = post(), []
    monkeypatch.setattr(primary, "load_primary_post", lambda: value)
    monkeypatch.setattr(meta, "PRIMARY_DELIVERY", None)
    for name in ("META_CREATE_RETRY_ATTEMPTS", "META_PUBLISH_RETRY_ATTEMPTS", "IG_REEL_CREATE_CYCLES", "MEDIA_BASE_OVERRIDE"):
        monkeypatch.setattr(meta, name, getattr(meta, name))
    monkeypatch.setattr(meta, "_select_post_with_fallback", lambda *a: pytest.fail("Latest lookup forbidden"))
    monkeypatch.setattr(meta, "ig_post_carousel", lambda urls, caption, **kw: captured.append(caption) or {"success": True})
    monkeypatch.setenv("EARTHSCOPE_MEDIA_REVISION", "f"*64)
    monkeypatch.setattr(sys, "argv", ["meta_poster.py", "post-carousel", "--platform", "ig", "--dry-run", "--media-base", "https://fixture.invalid/by-run/" + "f"*64])
    with pytest.raises(SystemExit) as exited: meta.main()
    assert exited.value.code == 0
    assert captured == [bundle()["social_variants"]["ig"]["caption"] + "\n\n" + bundle()["hashtags"]]
    assert meta.META_CREATE_RETRY_ATTEMPTS == meta.META_PUBLISH_RETRY_ATTEMPTS == meta.IG_REEL_CREATE_CYCLES == 1


def test_reel_main_selects_frozen_story_before_any_media_or_latest_fallback(monkeypatch, tmp_path):
    with patch("dotenv.load_dotenv", return_value=False):
        from bots.earthscope_post import reel_builder as reel
    value, captured = post(), []
    monkeypatch.setattr(primary, "load_primary_post", lambda: value)
    monkeypatch.setattr(reel, "which_ffmpeg", lambda: None)
    monkeypatch.setattr(reel, "IMAGES_DIR", tmp_path / "images")
    monkeypatch.setattr(reel, "REEL_OUT_PATH", tmp_path / "reel.mp4")
    monkeypatch.setattr(reel, "REEL_REQUIRE_VO", False)
    monkeypatch.setattr(reel, "REEL_VOICE_ENABLED", False)
    monkeypatch.setattr(reel, "pick_story_backgrounds", lambda *a: [tmp_path / str(i) for i in range(3)])
    for name in ("fetch_post_for_day", "_latest_day_from_content"):
        monkeypatch.setattr(reel, name, lambda *a: pytest.fail("Latest/live fallback forbidden"))
    class StopBeforeVideo(Exception): pass
    def hook(background, path, text, *, observed_context=False):
        captured.append((text, observed_context))
        raise StopBeforeVideo
    monkeypatch.setattr(reel, "build_hook_card", hook)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(StopBeforeVideo): reel.main()
    assert captured == [(bundle()["reel_story"]["hook"], True)]


def test_preparer_includes_bounded_complete_copy_context_in_existing_wire():
    from services.earthscope_public_facts import prepare_public_packet, utc
    from datetime import date
    fixture = json.loads((ROOT / "tests/fixtures/earthscope_public_facts.json").read_text())
    inputs = fixture["inputs"]
    row = inputs["public_copy"][0]
    row.update(snapshot="prior snapshot", affects="prior affects", playbook="prior playbook",
               voiceover="prior voice", reel_hook="prior hook", reel_signal="prior signal",
               reel_effects="prior effects", reel_pattern="prior pattern", reel_voiceover="prior reel voice")
    packet, ledger = prepare_public_packet(date.fromisoformat(fixture["day"]), now=utc(fixture["now"]), synthetic=True, **inputs)
    values = {r["text"] for r in packet["recent_public_copy"]}
    assert {"prior snapshot", "prior affects", "prior playbook", "prior voice", "prior hook", "prior signal", "prior effects", "prior pattern", "prior reel voice"} <= values
    assert ledger["facts_sha256"] == sha256(packet)


def test_review_cli_never_publishes_and_review_artifact_is_not_production_eligible(monkeypatch, tmp_path):
    value = post()
    value["metrics_json"]["writer_source"]["acceptance_id"] = "review-only-not-accepted"
    async def prepared(*args, **kwargs):
        assert kwargs["review_only"] is True
        return value
    monkeypatch.setattr(runner, "configured_post", prepared)
    monkeypatch.setattr(runner, "publish_once", lambda *a: pytest.fail("Review attempted public write"))
    paths = {k: tmp_path / (k + ".json") for k in ("receipt", "post-output", "daily-output")}
    monkeypatch.setattr(sys, "argv", ["local_primary.py", "--day", value["day"], "--review-only",
        *[item for k, v in paths.items() for item in ("--" + k, str(v))]])
    assert runner.main() == 0
    receipt = json.loads(paths["receipt"].read_text())
    assert receipt["status"] == "review_ready" and receipt["production_consumption"] is False
    env = {**ENV, "TARGET_DAY": value["day"], "EARTHSCOPE_PRIMARY_POST_PATH": str(paths["post-output"]),
           "EARTHSCOPE_PRIMARY_POST_SHA256": sha256(value)}
    with pytest.raises(DraftError, match="editorial_acceptance_required"):
        primary.load_primary_post(env, now=NOW)
    assert primary.load_primary_post(env, now=NOW, allow_review=True) == value


@pytest.mark.parametrize("content_day,timestamp,expected", [
    ("2026-09-24", "2026-09-24T00:15:00Z", "false"),
    ("2026-09-23", "2026-09-24T15:00:00Z", "true"),
])
def test_preflight_uses_content_day_not_observation_or_rewrite_time(monkeypatch, tmp_path, content_day, timestamp, expected):
    import io
    import datetime as dt
    workflow = yaml.safe_load((ROOT / ".github/workflows/gaia_eyes_daily.yml").read_text())
    script = workflow["jobs"]["preflight"]["steps"][0]["run"]
    python = script.split("python - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None): return NOW.astimezone(tz)
    monkeypatch.setattr(dt, "datetime", Clock)
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **kw: io.StringIO(json.dumps({"day": content_day, "timestamp_utc": timestamp})))
    output = tmp_path / "gate"
    for key, value in {"EVENT_NAME": "schedule", "GAIA_TIMEZONE": "America/Chicago",
                       "GITHUB_OUTPUT": str(output), "EARTHSCOPE_DAILY_URL": "https://fixture.invalid"}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    try: exec(compile(python, "actual-preflight", "exec"), {})
    except SystemExit as exc: assert exc.code == 0
    assert f"should_run={expected}" in output.read_text()
