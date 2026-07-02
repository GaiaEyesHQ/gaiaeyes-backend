from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

os.environ.setdefault("SUPABASE_DB_URL", "postgresql://postgres:postgres@localhost:5432/postgres")

from bots.notifications import evaluate_push_notifications as push_eval


def _symptom_prompt_row(*, scheduled_for: datetime, delivered_at: datetime | None = None) -> dict:
    return {
        "id": "prompt-1",
        "episode_id": "episode-1",
        "symptom_code": "drained",
        "prompt_payload": {
            "symptom_label": "Drained",
            "episode_state": "ongoing",
        },
        "scheduled_for": scheduled_for,
        "delivered_at": delivered_at,
        "push_delivery_enabled": True,
    }


def test_symptom_followup_push_candidate_skips_already_delivered_prompt(monkeypatch) -> None:
    now = datetime(2026, 7, 1, 16, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(push_eval, "utc_now", lambda: now)
    monkeypatch.setattr(
        push_eval,
        "_feedback_prompt_rows",
        lambda user_id, prompt_type: [_symptom_prompt_row(scheduled_for=now - timedelta(hours=2), delivered_at=now - timedelta(hours=1))],
    )

    candidates = push_eval._build_prompt_candidates("user-1")

    assert not [candidate for candidate in candidates if candidate.family == "symptom_followups"]


def test_symptom_followup_push_candidate_skips_stale_prompt(monkeypatch) -> None:
    now = datetime(2026, 7, 1, 16, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(push_eval, "utc_now", lambda: now)
    monkeypatch.setattr(
        push_eval,
        "_feedback_prompt_rows",
        lambda user_id, prompt_type: [_symptom_prompt_row(scheduled_for=now - timedelta(days=30))],
    )

    candidates = push_eval._build_prompt_candidates("user-1")

    assert not [candidate for candidate in candidates if candidate.family == "symptom_followups"]


def test_symptom_followup_push_candidate_allows_fresh_undelivered_prompt(monkeypatch) -> None:
    now = datetime(2026, 7, 1, 16, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(push_eval, "utc_now", lambda: now)
    monkeypatch.setattr(
        push_eval,
        "_feedback_prompt_rows",
        lambda user_id, prompt_type: [_symptom_prompt_row(scheduled_for=now - timedelta(hours=2))],
    )

    candidates = push_eval._build_prompt_candidates("user-1")

    symptom_candidates = [candidate for candidate in candidates if candidate.family == "symptom_followups"]
    assert len(symptom_candidates) == 1
    assert symptom_candidates[0].title == "Still feeling drained?"
