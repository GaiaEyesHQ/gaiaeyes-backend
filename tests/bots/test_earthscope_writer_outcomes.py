"""Writer-only fake-provider/cache tests; no generation main or publishing."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import types
from unittest.mock import patch

import httpx
from openai import RateLimitError
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
SOURCE = Path(os.environ.get("GAIA_WRITER_TEST_SOURCE", ROOT / "bots/earthscope_post/earthscope_generate.py"))
stub = types.ModuleType("supabase")
stub.create_client = lambda *_args, **_kwargs: object()
spec = importlib.util.spec_from_file_location("g033_writer_subject", SOURCE)
writer = importlib.util.module_from_spec(spec)
with patch("dotenv.load_dotenv", return_value=False), patch.dict(sys.modules, {"supabase": stub}), patch.dict(
    os.environ, {"SUPABASE_URL": "https://fixture.invalid", "SUPABASE_SERVICE_ROLE_KEY": "fake-no-access"}
):
    spec.loader.exec_module(writer)

CTX = {"day": "2026-09-18", "platform": "default", "kp_max_24h": 2.0, "bz_min": 1.0,
       "solar_wind_kms": 350.0, "cmes_24h": 0, "flares_24h": 0,
       "recent_captions": [], "banned_openers": []}
COPY = {"caption": "Focus can come in waves. Leave room for a slower pace.",
        "snapshot": "The field looks steady. No new flare activity adds pressure.",
        "affects": "Some people may find attention easier to sustain.",
        "playbook": "- Keep the day simple\n- Protect your evening routine",
        "hashtags": "#GaiaEyes #SpaceWeather"}


def response(payload):
    return types.SimpleNamespace(model="resolved-fake-writer", choices=[types.SimpleNamespace(
        message=types.SimpleNamespace(content=json.dumps(payload)), finish_reason="stop")])


def credit_error(code, *, in_type=False):
    body = {"code": None if in_type else code, "type": code if in_type else "requests",
            "message": "PRIVATE_ERROR_MARKER credit_balance_exhausted"}
    reply = httpx.Response(429, request=httpx.Request("POST", "https://fixture.invalid/chat"))
    return RateLimitError("PRIVATE_ERROR_MARKER credit_balance_exhausted", response=reply, body=body)


class Provider:
    def __init__(self, *results):
        self.results = list(results)
        self.calls = []
        self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.calls.append(kwargs)
        result = self.results[min(len(self.calls) - 1, len(self.results) - 1)]
        if isinstance(result, Exception):
            raise result
        return result


@pytest.fixture(autouse=True)
def isolated_run(monkeypatch):
    monkeypatch.setattr(writer, "_writer_model", lambda: "requested-fake-writer")
    monkeypatch.setattr(writer, "EARTHSCOPE_FORCE_RULES", False)
    monkeypatch.setattr(writer, "EARTHSCOPE_DEBUG_REWRITE", True)
    monkeypatch.setattr(writer, "_hybrid_rewrite_enabled", lambda: True)
    monkeypatch.setattr(writer, "openai_client", lambda: None)
    monkeypatch.setattr(writer, "_recent_titles", lambda *_args, **_kwargs: set())
    monkeypatch.setattr(writer, "_recent_openers", lambda *_args, **_kwargs: set())
    writer._REWRITE_CACHE.clear()
    writer._reset_runtime_trace()


def test_accepted_model_copy_retains_resolved_model_through_cache():
    provider = Provider(response({"candidates": [COPY]}))
    first = writer._get_cached_rewrite(provider, CTX)
    first_trace = writer._trace_snapshot()
    second = writer._get_cached_rewrite(provider, CTX)
    trace = writer._trace_snapshot()
    assert len(provider.calls) == 1 and first == second
    assert first_trace.get("rewrite_outcome", {}).get("origin") == "model"
    assert first_trace["rewrite_outcome"]["cache_hit"] is False
    assert trace["rewrite_outcome"]["cache_hit"] is True and trace["rewrite_used"] is True
    assert trace["rewrite_outcome"]["model"] == "resolved-fake-writer"
    assert trace["rewrite_outcome"]["requested_model"] == "requested-fake-writer"
    assert trace["rewrite_outcome"]["provider"] == "openai"
    assert set(second) == set(COPY)
    assert "resolved-fake-writer" not in json.dumps(second)


@pytest.mark.parametrize("code", ["insufficient_quota", "credit_balance_exhausted"])
@pytest.mark.parametrize("in_type", [False, True])
def test_terminal_credit_stops_later_stages_and_cached_fallback_keeps_origin(monkeypatch, capsys, code, in_type):
    provider = Provider(credit_error(code, in_type=in_type))
    monkeypatch.setattr(writer, "openai_client", lambda: provider)
    sections = writer.generate_long_sections(CTX)
    caption, tags = writer.generate_short_caption(CTX, live_sections=dict(zip(("snapshot", "affects", "playbook"), sections)))
    assert writer._llm_title_from_context(provider, CTX, None) is None
    assert writer._rewrite_facebook_caption_from_spine(provider, ctx=CTX, title="A steadier day",
        default_caption=caption, default_hashtags=tags, sections={"snapshot": sections[0], "affects": sections[1], "playbook": sections[2]}) is None
    assert writer._rewrite_reel_from_final_caption(provider, ctx=CTX, caption=caption, snapshot=sections[0], affects=sections[1]) is None
    cached = writer._get_cached_rewrite(provider, CTX)
    assert len(provider.calls) == 1
    trace = writer._trace_snapshot()
    assert trace["terminal_writer_error"] == code
    assert trace["rewrite_used"] is False and trace["rewrite_cache_hit"] is True
    assert trace["rewrite_outcome"]["origin"] == "fallback"
    assert trace["rewrite_outcome"]["provider"] == "deterministic"
    assert trace["rewrite_outcome"]["model"] is None
    assert trace["rewrite_outcome"]["error"]["code"] == code
    assert sections[:3] == (cached["snapshot"], cached["affects"], cached["playbook"])
    assert caption and tags
    assert not any(item["outcome"] == "accepted_model" for item in trace["writer_outcomes"])
    assert {item["origin"] for item in trace["writer_outcomes"] if item["stage"] in {"caption", "sections"}} == {"fallback"}
    assert "PRIVATE_ERROR_MARKER" not in capsys.readouterr().out
    monkeypatch.setattr(writer, "EARTHSCOPE_DEBUG_REWRITE", False)
    writer._log_writer_outcome()
    logged = capsys.readouterr().out
    assert logged.startswith("[earthscope.writer] ") and "PRIVATE_ERROR_MARKER" not in logged
    assert json.loads(logged.removeprefix("[earthscope.writer] "))["rewrite_outcome"]["origin"] == "fallback"
    assert "credit_balance_exhausted" not in json.dumps(cached)


@pytest.mark.parametrize("code", ["rate_limit_exceeded", None])
def test_transient_rate_limit_does_not_latch_even_when_message_mentions_credit(code):
    provider = Provider(credit_error(code), response(COPY))
    out = writer._get_cached_rewrite(provider, CTX)
    assert len(provider.calls) == 2 and out["caption"] == COPY["caption"]
    trace = writer._trace_snapshot()
    assert trace.get("terminal_writer_error") is None
    assert trace.get("rewrite_outcome", {}).get("origin") == "model"
    assert trace["writer_requests"][0]["error"]["category"] == ("rate_limit" if code else "provider_error")


def test_missing_response_model_is_not_replaced_by_requested_alias():
    reply = response({"candidates": [COPY]})
    del reply.model
    writer._get_cached_rewrite(Provider(reply), CTX)
    outcome = writer._trace_snapshot().get("rewrite_outcome", {})
    assert outcome.get("origin") == "model" and outcome["model"] is None
    assert outcome["requested_model"] == "requested-fake-writer"


def test_validation_failure_caches_the_existing_qualitative_copy():
    provider = Provider(response({}))
    out = writer._get_cached_rewrite(provider, CTX)
    assert len(provider.calls) == 3
    assert out["snapshot"] == writer._scrub_banned_phrases(writer._qualitative_snapshot(CTX))
    assert out["caption"] == writer._scrub_banned_phrases(writer._sanitize_caption(writer._fallback_caption_for_tone(writer._tone_from_ctx(CTX), CTX)))
    writer._get_cached_rewrite(provider, CTX)
    trace = writer._trace_snapshot()
    assert len(provider.calls) == 3 and trace["rewrite_used"] is False
    assert trace["rewrite_outcome"]["origin"] == "fallback"
    assert trace["rewrite_outcome"]["reason"] == "validation_failed"
    assert all(item["outcome"] != "accepted_model" for item in trace["writer_outcomes"])


def test_plain_cache_entry_has_unknown_origin_instead_of_model_success():
    key, _ = writer._rewrite_cache_key(CTX)
    writer._REWRITE_CACHE[key] = dict(COPY)
    out = writer._get_cached_rewrite(None, CTX)
    assert out == COPY
    assert writer._trace_snapshot()["rewrite_used"] is False
    assert writer._trace_snapshot()["rewrite_outcome"]["origin"] == "unknown"


def test_terminal_latch_and_cache_end_at_the_next_generation_reset():
    provider = Provider(credit_error("insufficient_quota"), response({"candidates": [COPY]}))
    writer._get_cached_rewrite(provider, CTX)
    assert len(provider.calls) == 1
    writer._reset_runtime_trace()
    out = writer._get_cached_rewrite(provider, CTX)
    assert len(provider.calls) == 2 and out["caption"] == COPY["caption"]
    assert writer._trace_snapshot()["terminal_writer_error"] is None
    assert writer._trace_snapshot()["rewrite_outcome"]["origin"] == "model"


def test_compatibility_parameter_retry_is_preserved():
    provider = Provider(TypeError("unexpected keyword argument 'max_completion_tokens'"), response({"candidates": [COPY]}))
    writer._get_cached_rewrite(provider, CTX)
    assert len(provider.calls) == 2
    assert "max_completion_tokens" in provider.calls[0] and "max_tokens" in provider.calls[1]
    assert "temperature" in provider.calls[1]
    assert writer._trace_snapshot().get("rewrite_outcome", {}).get("origin") == "model"


def test_retained_accepted_copy_keeps_origin_when_similarity_retry_fails(monkeypatch):
    provider = Provider(response({}), response(COPY), credit_error("insufficient_quota"))
    monkeypatch.setattr(writer, "_caption_too_similar", lambda *_args: True)
    out = writer._get_cached_rewrite(provider, CTX)
    assert len(provider.calls) == 3 and out["caption"] == COPY["caption"]
    trace = writer._trace_snapshot()
    assert trace.get("rewrite_outcome", {}).get("origin") == "model"
    assert trace["rewrite_outcome"]["error"] is None
    assert trace["terminal_writer_error"] == "insufficient_quota"


def test_runtime_snapshot_does_not_gain_later_writer_events():
    provider = Provider(response(COPY))
    before = writer._trace_snapshot()
    writer._chat_create_compat(provider, model="requested-fake-writer")
    assert before.get("writer_requests") == []
    assert len(writer._trace_snapshot()["writer_requests"]) == 1


def test_forced_rules_still_returns_copy_without_provider_calls(monkeypatch):
    provider = Provider(AssertionError("No provider call expected"))
    monkeypatch.setattr(writer, "openai_client", lambda: provider)
    monkeypatch.setattr(writer, "EARTHSCOPE_FORCE_RULES", True)
    assert all(writer.generate_long_sections(CTX))
    assert all(writer.generate_short_caption(CTX))
    assert provider.calls == []
    trace = writer._trace_snapshot()
    assert len(trace.get("writer_outcomes", [])) == 2
    assert all(item["outcome"] == "fallback" for item in trace["writer_outcomes"])
