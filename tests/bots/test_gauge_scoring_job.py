from __future__ import annotations

from datetime import datetime, timezone

from bots.gauges import gauge_scoring_job


def test_local_day_uses_user_timezone_across_utc_boundary() -> None:
    now_utc = datetime(2026, 7, 12, 2, 30, tzinfo=timezone.utc)

    assert gauge_scoring_job._local_day("America/Chicago", now_utc=now_utc).isoformat() == "2026-07-11"
    assert gauge_scoring_job._local_day("UTC", now_utc=now_utc).isoformat() == "2026-07-12"


def test_fetch_user_ids_includes_recent_healthkit_and_app_users(monkeypatch) -> None:
    responses = iter(
        [
            [],
            [],
            [{"user_id": "healthkit-user"}],
            [{"user_id": "recent-app-user"}],
        ]
    )
    monkeypatch.setattr(gauge_scoring_job.pg, "fetch", lambda *args, **kwargs: next(responses))

    assert gauge_scoring_job._fetch_user_ids() == {"healthkit-user", "recent-app-user"}
