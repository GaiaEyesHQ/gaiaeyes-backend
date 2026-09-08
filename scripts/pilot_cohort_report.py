#!/usr/bin/env python3
"""Build a privacy-preserving pilot cohort report from explicit JSON exports.

This script is intentionally local and standard-library only. It does not query
Supabase, the Gaia Eyes API, App Store Connect, or Facebook.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


MEANINGFUL_EVENTS = {
    "daily_checkin_completed",
    "exposure_logged",
    "guide_opened",
    "symptom_logged",
}


def _parse_timestamp(value: Any, *, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_fixture(path: Path, *, rows_key: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not read valid JSON fixture: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    coverage = payload.get("coverage")
    rows = payload.get(rows_key)
    if not isinstance(coverage, dict):
        raise ValueError(f"{path} must contain a coverage object")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"{path} must contain a {rows_key} array of objects")
    return coverage, rows


def _account_id(row: Mapping[str, Any], *, row_number: int) -> str:
    value = row.get("id") or row.get("user_id")
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"account row {row_number} is missing id/user_id")
    return value.strip()


def _event_user_id(row: Mapping[str, Any], *, row_number: int) -> str:
    value = row.get("user_id")
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"event row {row_number} is missing user_id")
    return value.strip()


def _dedupe_events(rows: Sequence[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    unique: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for index, row in enumerate(rows, start=1):
        user_id = _event_user_id(row, row_number=index)
        event_name = str(row.get("event_name") or "").strip()
        if not event_name:
            raise ValueError(f"event row {index} is missing event_name")
        event_ts = _parse_timestamp(row.get("event_ts_utc"), field=f"event row {index} event_ts_utc")
        client_event_id = str(row.get("client_event_id") or "").strip()
        if client_event_id:
            key = ("client", user_id, client_event_id)
        else:
            key = (
                "fallback",
                user_id,
                event_name,
                _iso(event_ts),
                str(row.get("platform") or "").strip().lower(),
                str(row.get("session_id") or "").strip(),
            )
        if key in seen:
            continue
        seen.add(key)
        normalized = dict(row)
        normalized["_user_id"] = user_id
        normalized["_event_name"] = event_name
        normalized["_event_ts"] = event_ts
        normalized["_platform"] = str(row.get("platform") or "").strip().lower()
        unique.append(normalized)
    return unique, len(rows) - len(unique)


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


def build_report(
    *,
    accounts_coverage: Mapping[str, Any],
    account_rows: Sequence[dict[str, Any]],
    events_coverage: Mapping[str, Any],
    event_rows: Sequence[dict[str, Any]],
    pilot_start: datetime,
    pilot_end: datetime,
    as_of: datetime,
    excluded_user_ids: Iterable[str] = (),
) -> dict[str, Any]:
    pilot_start = pilot_start.astimezone(timezone.utc)
    pilot_end = pilot_end.astimezone(timezone.utc)
    as_of = as_of.astimezone(timezone.utc)
    if not pilot_start < pilot_end:
        raise ValueError("pilot start must be before pilot end")
    if as_of < pilot_start:
        raise ValueError("as-of must not be before pilot start")

    accounts_through = _parse_timestamp(accounts_coverage.get("through"), field="accounts coverage.through")
    events_from = _parse_timestamp(events_coverage.get("from"), field="events coverage.from")
    events_through = _parse_timestamp(events_coverage.get("through"), field="events coverage.through")
    if events_from > events_through:
        raise ValueError("events coverage.from must not be after coverage.through")

    effective_accounts_through = min(accounts_through, as_of)
    effective_events_through = min(events_through, as_of)
    excluded = {str(value).strip() for value in excluded_user_ids if str(value).strip()}

    parsed_accounts: list[dict[str, Any]] = []
    internal_excluded = 0
    old_accounts_excluded = 0
    future_accounts_ignored = 0
    seen_account_ids: set[str] = set()
    for index, row in enumerate(account_rows, start=1):
        user_id = _account_id(row, row_number=index)
        if user_id in seen_account_ids:
            continue
        seen_account_ids.add(user_id)
        created_at = _parse_timestamp(row.get("created_at"), field=f"account row {index} created_at")
        if created_at > effective_accounts_through:
            future_accounts_ignored += 1
            continue
        if user_id in excluded:
            internal_excluded += 1
            continue
        if created_at < pilot_start:
            old_accounts_excluded += 1
            continue
        if created_at >= pilot_end:
            continue
        parsed_accounts.append({"user_id": user_id, "created_at": created_at})

    unique_events, duplicates_removed = _dedupe_events(event_rows)
    events_by_user: dict[str, list[dict[str, Any]]] = {}
    for event in unique_events:
        event_ts = event["_event_ts"]
        if event_ts < events_from or event_ts > effective_events_through:
            continue
        events_by_user.setdefault(event["_user_id"], []).append(event)
    for rows in events_by_user.values():
        rows.sort(key=lambda item: item["_event_ts"])

    accounts_complete = effective_accounts_through >= pilot_end
    known_ios_accounts: list[dict[str, Any]] = []
    platform_unclassified = 0
    platform_window_censored = 0
    for account in parsed_accounts:
        created_at = account["created_at"]
        platform_end = created_at + timedelta(hours=24)
        account_events = events_by_user.get(account["user_id"], [])
        has_ios_event = any(
            event["_platform"] == "ios" and created_at <= event["_event_ts"] < platform_end
            for event in account_events
        )
        if has_ios_event:
            known_ios_accounts.append(account)
        elif events_from > created_at or effective_events_through < platform_end:
            platform_window_censored += 1
        else:
            platform_unclassified += 1

    first_use_numerator = 0
    first_use_denominator = 0
    first_use_censored = 0
    observed_activation_while_censored = 0
    matured_activations: list[tuple[str, datetime]] = []
    for account in known_ios_accounts:
        created_at = account["created_at"]
        window_end = created_at + timedelta(hours=24)
        account_events = events_by_user.get(account["user_id"], [])
        meaningful = [
            event
            for event in account_events
            if event["_event_name"] in MEANINGFUL_EVENTS
            and event["_platform"] == "ios"
            and created_at <= event["_event_ts"] < window_end
        ]
        complete_window = events_from <= created_at and effective_events_through >= window_end
        if not complete_window:
            first_use_censored += 1
            if meaningful:
                observed_activation_while_censored += 1
            continue
        first_use_denominator += 1
        if meaningful:
            first_use_numerator += 1
            matured_activations.append((account["user_id"], meaningful[0]["_event_ts"]))

    d7_numerator = 0
    d7_denominator = 0
    d7_censored = 0
    for user_id, activation_ts in matured_activations:
        return_start = activation_ts + timedelta(days=6)
        return_end = activation_ts + timedelta(days=9)
        complete_window = events_from <= return_start and effective_events_through >= return_end
        if not complete_window:
            d7_censored += 1
            continue
        d7_denominator += 1
        returned = any(
            event["_event_name"] in MEANINGFUL_EVENTS
            and event["_platform"] == "ios"
            and return_start <= event["_event_ts"] < return_end
            for event in events_by_user.get(user_id, [])
        )
        if returned:
            d7_numerator += 1

    unknowns: list[str] = []
    if not accounts_complete:
        unknowns.append("new account export does not cover the full pilot window")
    if platform_window_censored:
        unknowns.append("some new accounts lack a fully observed 24-hour platform window")
    if platform_unclassified:
        unknowns.append("some new accounts have no iOS event in the observed 24-hour platform window")
    if first_use_censored:
        unknowns.append("some known iOS accounts lack complete 24-hour first-use coverage")
    if d7_censored:
        unknowns.append("some activated accounts have not completed the full day-6-through-day-8 return window")

    return {
        "schema_version": "1.0",
        "pilot": {
            "start": _iso(pilot_start),
            "end_exclusive": _iso(pilot_end),
            "as_of": _iso(as_of),
            "source_attribution": "unknown",
        },
        "coverage": {
            "accounts_through": _iso(accounts_through),
            "events_from": _iso(events_from),
            "events_through": _iso(events_through),
            "effective_events_through": _iso(effective_events_through),
            "accounts_complete_for_pilot": accounts_complete,
        },
        "cohort": {
            "observed_new_external_accounts": len(parsed_accounts),
            "new_external_accounts_total": len(parsed_accounts) if accounts_complete else None,
            "known_ios_accounts": len(known_ios_accounts),
            "platform_unclassified_accounts": platform_unclassified,
            "platform_window_censored_accounts": platform_window_censored,
            "internal_or_test_accounts_excluded": internal_excluded,
            "old_accounts_excluded": old_accounts_excluded,
            "future_accounts_ignored": future_accounts_ignored,
        },
        "first_meaningful_use_24h": {
            "qualifying_platform": "ios",
            "meaningful_events": sorted(MEANINGFUL_EVENTS),
            "numerator": first_use_numerator,
            "matured_denominator": first_use_denominator,
            "rate": _rate(first_use_numerator, first_use_denominator),
            "censored_accounts": first_use_censored,
            "observed_activated_while_censored": observed_activation_while_censored,
        },
        "d7_return": {
            "qualifying_platform": "ios",
            "window": "[activation + 6 days, activation + 9 days)",
            "numerator": d7_numerator,
            "matured_denominator": d7_denominator,
            "rate": _rate(d7_numerator, d7_denominator),
            "censored_activated_accounts": d7_censored,
        },
        "deduplication": {
            "input_events": len(event_rows),
            "unique_events": len(unique_events),
            "duplicates_removed": duplicates_removed,
        },
        "unknowns": unknowns,
        "privacy": {
            "individual_user_ids_in_output": False,
            "health_text_in_output": False,
        },
    }


def _excluded_ids(values: Sequence[str], path: Path | None) -> set[str]:
    excluded = {value.strip() for value in values if value.strip()}
    if path is not None:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise ValueError(f"could not read excluded-user file: {path}") from exc
        excluded.update(line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#"))
    return excluded


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accounts", type=Path, required=True, help="JSON account export fixture")
    parser.add_argument("--events", type=Path, required=True, help="JSON analytics-event export fixture")
    parser.add_argument("--pilot-start", required=True, help="inclusive ISO-8601 pilot start")
    parser.add_argument("--pilot-end", required=True, help="exclusive ISO-8601 pilot end")
    parser.add_argument("--as-of", required=True, help="ISO-8601 reporting cutoff")
    parser.add_argument("--exclude-user-id", action="append", default=[], help="internal/test user id to exclude")
    parser.add_argument("--exclude-user-ids-file", type=Path, help="newline-delimited internal/test user ids")
    parser.add_argument("--output", type=Path, help="optional output JSON path; stdout when omitted")
    return parser


def _same_file(left: Path, right: Path) -> bool:
    try:
        return os.path.samefile(left, right)
    except (FileNotFoundError, OSError):
        return left.resolve(strict=False) == right.resolve(strict=False)


def _write_new_output(path: Path, rendered: str, *, protected_paths: Sequence[Path]) -> None:
    for protected in protected_paths:
        if _same_file(path, protected):
            raise ValueError(f"output must not overwrite input: {protected}")
    try:
        with path.open("x", encoding="utf-8") as output_file:
            output_file.write(rendered)
    except FileExistsError as exc:
        raise ValueError(f"output already exists and was not replaced: {path}") from exc
    except OSError as exc:
        raise ValueError(f"could not create output: {path}") from exc


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        accounts_coverage, account_rows = _load_fixture(args.accounts, rows_key="accounts")
        events_coverage, event_rows = _load_fixture(args.events, rows_key="events")
        report = build_report(
            accounts_coverage=accounts_coverage,
            account_rows=account_rows,
            events_coverage=events_coverage,
            event_rows=event_rows,
            pilot_start=_parse_timestamp(args.pilot_start, field="pilot start"),
            pilot_end=_parse_timestamp(args.pilot_end, field="pilot end"),
            as_of=_parse_timestamp(args.as_of, field="as-of"),
            excluded_user_ids=_excluded_ids(args.exclude_user_id, args.exclude_user_ids_file),
        )
    except ValueError as exc:
        parser.error(str(exc))

    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        protected_paths = [args.accounts, args.events]
        if args.exclude_user_ids_file is not None:
            protected_paths.append(args.exclude_user_ids_file)
        try:
            _write_new_output(args.output, rendered, protected_paths=protected_paths)
        except ValueError as exc:
            parser.error(str(exc))
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
