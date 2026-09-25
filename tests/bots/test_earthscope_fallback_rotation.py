"""Fallback selection regression: no provider, DB, renderer or publisher calls."""
import importlib.util
import os
from pathlib import Path
import sys
import types
from unittest.mock import patch

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
stub = types.ModuleType("supabase")
stub.create_client = lambda *_args, **_kwargs: object()
spec = importlib.util.spec_from_file_location("fallback_rotation_subject", ROOT / "bots/earthscope_post/earthscope_generate.py")
writer = importlib.util.module_from_spec(spec)
with patch("dotenv.load_dotenv", return_value=False), patch.dict(sys.modules, {"supabase": stub}), patch.dict(
    os.environ, {"SUPABASE_URL": "https://fixture.invalid", "SUPABASE_SERVICE_ROLE_KEY": "fake-no-access"}
):
    spec.loader.exec_module(writer)

STANDARD = "Standard energy field—consistency wins today."
ORDINARY = "Ordinary signal mix today—small steady choices do the work."
MIDDLE = "Middle-lane space weather today—keep the rhythm simple."


@pytest.mark.parametrize("day", ["2026-09-22", "2026-09-23"])
def test_exhausted_neutral_pool_uses_least_recent_hook_not_hash_repeat(day):
    # Sep22/23 natural history includes all three options, with Standard most recent.
    history = [STANDARD, STANDARD, ORDINARY, MIDDLE, ORDINARY]
    ctx = {"day": day, "platform": "default", "banned_openers": history[:3],
           "recent_captions": [h + " — Kp 2.0 (snapshot at write time)" for h in history]}
    assert writer._fallback_caption_for_tone("neutral", ctx) == MIDDLE


def test_duplicate_old_use_does_not_hide_a_recent_use():
    result = writer._stable_choice(["A.", "B.", "C."], seed_text="fixed",
                                   banned_openers=["A.", "B.", "C.", "A."])
    assert result == "C."


def test_history_matches_first_sentence_and_case():
    assert writer._stable_choice(["A.", "B."], seed_text="fixed",
        banned_openers=["a. More details.", "b. Older details."]) == "B."


def test_unused_candidate_is_preferred_over_any_used_candidate():
    assert writer._stable_choice(["A.", "B.", "C."], seed_text="fixed",
        banned_openers=["A.", "B."]) == "C."


@pytest.mark.parametrize("tone", ["neutral", "calm", "unsettled", "stormy"])
def test_repeated_fallback_days_remain_deterministic_without_consecutive_hook_repeats(tone):
    recent = []
    outputs = []
    for number in range(10, 25):
        ctx = {"day": f"2026-09-{number}", "platform": "default",
               "banned_openers": recent[:3], "recent_captions": recent[:5]}
        value = writer._fallback_caption_for_tone(tone, ctx)
        assert writer._fallback_caption_for_tone(tone, ctx) == value
        if outputs:
            assert value != outputs[-1]
        outputs.append(value)
        recent.insert(0, value)


@pytest.mark.parametrize(("options", "history", "expected"), [
    ([], [], ""), ([""], ["A."], ""), (["A."], ["A."], "A."),
])
def test_empty_and_single_option_pools_are_explicit(options, history, expected):
    assert writer._stable_choice(options, seed_text="fixed", banned_openers=history) == expected


def test_rotation_changes_only_selection_and_keeps_copy_sections_and_facts():
    ctx = {"day": "2026-09-23", "platform": "default", "kp_max_24h": 1.0,
           "bz_min": -3.48, "solar_wind_kms": 288, "schumann_value_hz": 7.65,
           "recent_captions": [STANDARD, STANDARD, ORDINARY, MIDDLE, ORDINARY],
           "banned_openers": [STANDARD, STANDARD, ORDINARY]}
    before = dict(ctx)
    sections = writer._rule_copy(ctx)
    caption = writer._fallback_caption_for_tone(writer._tone_from_ctx(ctx), ctx)
    assert caption == MIDDLE
    assert ctx == before
    assert writer._rule_copy(ctx) == sections
    assert writer._caption_with_approved_hook(caption, "Tiny Symptoms Still Count") == caption
