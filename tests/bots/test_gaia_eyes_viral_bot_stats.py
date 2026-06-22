import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bots.earthscope_post.gaia_eyes_viral_bot import (
    _earthscope_hook_title,
    _format_public_playbook,
    _public_card_title,
    _public_card_text,
    _trim_public_affects,
    build_stats_rows,
    StatRow,
)


def _row_for_label(rows: list[StatRow], label: str) -> StatRow:
    for row in rows:
        if row.label == label:
            return row
    raise AssertionError(f"Missing row for {label}")


def test_bz_prefers_min_and_applies_severe_styling():
    feats = {
        "kp_max": 4.5,
        "bz_min": -8.0,
        "bz_current": -2.0,
        "sw_speed_avg": 505,
        "sch_any_fundamental_avg_hz": 7.83,
    }

    rows = build_stats_rows(feats, "avg")
    bz_row = _row_for_label(rows, "Bz (min)")

    assert bz_row.display == "-8.0 nT"
    assert bz_row.raw_value == pytest.approx(-8.0)
    assert bz_row.color == (239, 106, 106, 220)


def test_bz_falls_back_to_current_with_label():
    feats = {
        "kp_max": 3.2,
        "bz_min": None,
        "bz_current": -3.4,
        "sw_speed_avg": 455,
        "sch_any_fundamental_avg_hz": 7.7,
    }

    rows = build_stats_rows(feats, "avg")
    bz_row = _row_for_label(rows, "Bz (current)")

    assert bz_row.display == "-3.4 nT"
    assert bz_row.raw_value == pytest.approx(-3.4)
    assert bz_row.color == (100, 160, 220, 220)


@pytest.mark.parametrize(
    "feats",
    [
        {"kp_max": 2.1, "sw_speed_avg": 420, "sch_any_fundamental_avg_hz": 7.6},
        {
            "kp_max": 2.1,
            "bz_min": None,
            "bz_current": None,
            "bz_now": None,
            "sw_speed_avg": 420,
            "sch_any_fundamental_avg_hz": 7.6,
        },
    ],
)
def test_bz_missing_uses_placeholder(feats):
    rows = build_stats_rows(feats, "avg")
    bz_row = _row_for_label(rows, "Bz (current)")
    assert bz_row.display == "—"
    assert bz_row.raw_value is None


def test_earthscope_hook_title_leads_with_symptom_pattern():
    title = _earthscope_hook_title(
        "Focus and attention may come in shorter windows. Sleep wind-down can be more sensitive.",
        tone="unsettled",
        energy="Elevated",
    )

    assert title in {
        "Focus feeling scattered?",
        "Mentally all over the place?",
        "Attention running patchy?",
        "Brain feeling noisy?",
    }


def test_earthscope_hook_title_uses_calm_focus_language():
    title = _earthscope_hook_title(
        "Focus windows can be slightly extended as the field is mostly cooperative.",
        tone="neutral",
        energy="Calm",
    )

    assert title in {"Need a catch-up day?", "Ready to focus?", "Clear the mental tabs"}


def test_earthscope_hook_title_does_not_question_imperative_calm_hook(monkeypatch):
    monkeypatch.setattr(
        "bots.earthscope_post.gaia_eyes_viral_bot._daily_title_variant",
        lambda options, seed_text="": "Clear the mental tabs",
    )

    title = _earthscope_hook_title(
        "Focus windows can be slightly extended as the field is mostly cooperative.",
        tone="neutral",
        energy="Calm",
    )

    assert title == "Clear the mental tabs"


def test_public_card_title_prefers_stored_llm_title():
    title = _public_card_title("A good day to catch up", fallback="Ready to focus?")

    assert title == "A good day to catch up"


def test_public_card_title_uses_fallback_for_generic_or_dated_titles():
    assert _public_card_title("Daily EarthScope", fallback="Ready to focus?") == "Ready to focus?"
    assert _public_card_title("Daily EarthScope - Jun 21, 2026", fallback="Ready to focus?") == "Ready to focus?"


def test_public_card_text_removes_clinician_and_vibes_language():
    text = _public_card_text("Clinicians often see recovery patterns. Enjoy steady vibes.")

    assert "Clinicians" not in text
    assert "vibes" not in text
    assert "Gaia Eyes often sees" in text


def test_format_public_playbook_outputs_clean_bullets():
    text = _format_public_playbook("Use steady blocks\nKeep movement light")

    assert text.startswith("- Use steady blocks.\n- Keep movement light.")
    assert text.count("\n- ") >= 2


def test_trim_public_affects_keeps_first_three_sentences():
    text = _trim_public_affects("One. Two. Three. Four.")

    assert text == "One. Two. Three."
