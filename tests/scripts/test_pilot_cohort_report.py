from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.pilot_cohort_report import build_report, main


UTC = timezone.utc
START = datetime(2026, 9, 10, tzinfo=UTC)
END = datetime(2026, 9, 11, tzinfo=UTC)


def _account(user_id: str, created_at: str) -> dict[str, str]:
    return {"id": user_id, "created_at": created_at}


def _event(
    user_id: str,
    name: str,
    timestamp: str,
    *,
    event_id: str = "",
    platform: str = "ios",
) -> dict[str, str]:
    return {
        "user_id": user_id,
        "client_event_id": event_id,
        "event_name": name,
        "event_ts_utc": timestamp,
        "platform": platform,
        "session_id": "session",
    }


def _report(
    accounts: list[dict[str, str]],
    events: list[dict[str, str]],
    *,
    as_of: str = "2026-09-21T00:00:00Z",
    account_through: str = "2026-09-11T00:00:00Z",
    event_from: str = "2026-09-10T00:00:00Z",
    event_through: str = "2026-09-21T00:00:00Z",
    excluded: set[str] | None = None,
) -> dict:
    return build_report(
        accounts_coverage={"through": account_through},
        account_rows=accounts,
        events_coverage={"from": event_from, "through": event_through},
        event_rows=events,
        pilot_start=START,
        pilot_end=END,
        as_of=datetime.fromisoformat(as_of.replace("Z", "+00:00")),
        excluded_user_ids=excluded or set(),
    )


def test_automatic_onboarding_events_do_not_count_as_meaningful_use() -> None:
    report = _report(
        [_account("new-user", "2026-09-10T01:00:00Z")],
        [
            _event("new-user", "onboarding_completed", "2026-09-10T01:10:00Z"),
            _event("new-user", "first_insight_viewed", "2026-09-10T01:11:00Z"),
        ],
    )

    assert report["cohort"]["known_ios_accounts"] == 1
    assert report["first_meaningful_use_24h"]["numerator"] == 0
    assert "first_insight_viewed" not in report["first_meaningful_use_24h"]["meaningful_events"]


def test_duplicate_client_event_is_counted_once() -> None:
    report = _report(
        [_account("new-user", "2026-09-10T01:00:00Z")],
        [
            _event("new-user", "symptom_logged", "2026-09-10T01:10:00Z", event_id="same-event"),
            _event("new-user", "symptom_logged", "2026-09-10T01:10:00Z", event_id="same-event"),
        ],
    )

    assert report["deduplication"]["duplicates_removed"] == 1
    assert report["first_meaningful_use_24h"]["numerator"] == 1


def test_internal_users_and_old_accounts_are_excluded() -> None:
    report = _report(
        [
            _account("internal", "2026-09-10T01:00:00Z"),
            _account("old", "2026-09-09T23:59:59Z"),
            _account("external", "2026-09-10T02:00:00Z"),
        ],
        [
            _event("internal", "symptom_logged", "2026-09-10T01:05:00Z"),
            _event("old", "symptom_logged", "2026-09-10T00:05:00Z"),
            _event("external", "guide_opened", "2026-09-10T02:05:00Z"),
        ],
        excluded={"internal"},
    )

    assert report["cohort"]["observed_new_external_accounts"] == 1
    assert report["cohort"]["internal_or_test_accounts_excluded"] == 1
    assert report["cohort"]["old_accounts_excluded"] == 1


def test_24_hour_and_day_6_to_8_boundaries_are_half_open() -> None:
    report = _report(
        [
            _account("inside", "2026-09-10T00:00:00Z"),
            _account("at-24h", "2026-09-10T00:30:00Z"),
        ],
        [
            _event("inside", "symptom_logged", "2026-09-10T00:10:00Z"),
            _event("inside", "guide_opened", "2026-09-16T00:10:00Z"),
            _event("inside", "guide_opened", "2026-09-19T00:10:00Z"),
            _event("at-24h", "onboarding_completed", "2026-09-10T01:00:00Z"),
            _event("at-24h", "symptom_logged", "2026-09-11T00:30:00Z"),
        ],
    )

    assert report["first_meaningful_use_24h"]["numerator"] == 1
    assert report["first_meaningful_use_24h"]["matured_denominator"] == 2
    assert report["d7_return"]["numerator"] == 1
    assert report["d7_return"]["matured_denominator"] == 1


def test_incomplete_account_export_reports_total_as_unknown() -> None:
    report = _report(
        [_account("new-user", "2026-09-10T01:00:00Z")],
        [_event("new-user", "guide_opened", "2026-09-10T01:05:00Z")],
        account_through="2026-09-10T12:00:00Z",
    )

    assert report["cohort"]["observed_new_external_accounts"] == 1
    assert report["cohort"]["new_external_accounts_total"] is None
    assert report["coverage"]["accounts_complete_for_pilot"] is False


def test_incomplete_event_coverage_censors_first_use_instead_of_reporting_zero() -> None:
    report = _report(
        [_account("new-user", "2026-09-10T20:00:00Z")],
        [_event("new-user", "onboarding_completed", "2026-09-10T20:05:00Z")],
        as_of="2026-09-11T00:00:00Z",
        event_through="2026-09-11T00:00:00Z",
    )

    assert report["cohort"]["platform_window_censored_accounts"] == 0
    assert report["first_meaningful_use_24h"]["matured_denominator"] == 0
    assert report["first_meaningful_use_24h"]["rate"] is None
    assert report["first_meaningful_use_24h"]["censored_accounts"] == 1


def test_immature_d7_cohort_is_not_in_return_denominator() -> None:
    report = _report(
        [_account("new-user", "2026-09-10T01:00:00Z")],
        [_event("new-user", "symptom_logged", "2026-09-10T01:05:00Z")],
        as_of="2026-09-17T00:00:00Z",
        event_through="2026-09-17T00:00:00Z",
    )

    assert report["first_meaningful_use_24h"]["numerator"] == 1
    assert report["d7_return"]["matured_denominator"] == 0
    assert report["d7_return"]["rate"] is None
    assert report["d7_return"]["censored_activated_accounts"] == 1


def test_aggregate_output_does_not_disclose_identity_or_health_text() -> None:
    user_id = "private-user-id"
    health_text = "private migraine note"
    report = _report(
        [_account(user_id, "2026-09-10T01:00:00Z")],
        [
            {
                **_event(user_id, "symptom_logged", "2026-09-10T01:05:00Z"),
                "symptom_name": "Migraine",
                "note": health_text,
            }
        ],
    )

    rendered = json.dumps(report)
    assert user_id not in rendered
    assert health_text not in rendered
    assert "Migraine" not in rendered
    assert report["privacy"] == {
        "individual_user_ids_in_output": False,
        "health_text_in_output": False,
    }


@pytest.mark.parametrize("platform", ["android", ""])
def test_non_ios_or_missing_platform_does_not_satisfy_ios_first_use(platform: str) -> None:
    report = _report(
        [_account("new-user", "2026-09-10T01:00:00Z")],
        [
            _event("new-user", "onboarding_completed", "2026-09-10T01:05:00Z"),
            _event(
                "new-user",
                "symptom_logged",
                "2026-09-10T02:00:00Z",
                platform=platform,
            ),
        ],
    )

    assert report["cohort"]["known_ios_accounts"] == 1
    assert report["first_meaningful_use_24h"]["qualifying_platform"] == "ios"
    assert report["first_meaningful_use_24h"]["matured_denominator"] == 1
    assert report["first_meaningful_use_24h"]["numerator"] == 0


def test_android_event_does_not_satisfy_ios_d7_return() -> None:
    report = _report(
        [_account("new-user", "2026-09-10T01:00:00Z")],
        [
            _event("new-user", "symptom_logged", "2026-09-10T01:05:00Z"),
            _event(
                "new-user",
                "guide_opened",
                "2026-09-16T01:05:00Z",
                platform="android",
            ),
        ],
    )

    assert report["d7_return"]["qualifying_platform"] == "ios"
    assert report["d7_return"]["matured_denominator"] == 1
    assert report["d7_return"]["numerator"] == 0


def _write_cli_fixtures(directory: Path) -> tuple[Path, Path]:
    accounts = directory / "accounts.json"
    events = directory / "events.json"
    accounts.write_text(
        json.dumps(
            {
                "coverage": {"through": "2026-09-11T00:00:00Z"},
                "accounts": [],
            }
        ),
        encoding="utf-8",
    )
    events.write_text(
        json.dumps(
            {
                "coverage": {
                    "from": "2026-09-10T00:00:00Z",
                    "through": "2026-09-20T12:00:00Z",
                },
                "events": [],
            }
        ),
        encoding="utf-8",
    )
    return accounts, events


def _cli_args(accounts: Path, events: Path, output: Path) -> list[str]:
    return [
        "--accounts",
        str(accounts),
        "--events",
        str(events),
        "--pilot-start",
        "2026-09-10T00:00:00Z",
        "--pilot-end",
        "2026-09-11T00:00:00Z",
        "--as-of",
        "2026-09-20T12:00:00Z",
        "--output",
        str(output),
    ]


def test_output_cannot_overwrite_input(tmp_path: Path) -> None:
    accounts, events = _write_cli_fixtures(tmp_path)
    original = accounts.read_bytes()

    with pytest.raises(SystemExit):
        main(_cli_args(accounts, events, accounts))

    assert accounts.read_bytes() == original


def test_existing_output_is_preserved(tmp_path: Path) -> None:
    accounts, events = _write_cli_fixtures(tmp_path)
    output = tmp_path / "checkpoint.json"
    output.write_text("existing checkpoint\n", encoding="utf-8")

    with pytest.raises(SystemExit):
        main(_cli_args(accounts, events, output))

    assert output.read_text(encoding="utf-8") == "existing checkpoint\n"


def test_output_cannot_overwrite_exclusion_input(tmp_path: Path) -> None:
    accounts, events = _write_cli_fixtures(tmp_path)
    exclusions = tmp_path / "excluded-users.txt"
    exclusions.write_text("internal-user\n", encoding="utf-8")
    original = exclusions.read_bytes()
    args = _cli_args(accounts, events, exclusions)
    args.extend(["--exclude-user-ids-file", str(exclusions)])

    with pytest.raises(SystemExit):
        main(args)

    assert exclusions.read_bytes() == original


@pytest.mark.parametrize("alias_kind", ["symlink", "hardlink"])
def test_output_alias_cannot_overwrite_input(tmp_path: Path, alias_kind: str) -> None:
    accounts, events = _write_cli_fixtures(tmp_path)
    alias = tmp_path / f"accounts-{alias_kind}.json"
    if alias_kind == "symlink":
        alias.symlink_to(accounts)
    else:
        os.link(accounts, alias)
    original = accounts.read_bytes()

    with pytest.raises(SystemExit):
        main(_cli_args(accounts, events, alias))

    assert accounts.read_bytes() == original
