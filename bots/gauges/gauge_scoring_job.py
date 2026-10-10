#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from typing import Iterable, Set, Tuple

from services.db import pg
from bots.gauges.gauge_scorer import DEFAULT_TIMEZONE, LOCAL_TZ, score_user_day


LOG_LEVEL = os.getenv("GAIA_LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)


RECENT_ACTIVITY_DAYS = max(1, int(os.getenv("GAIA_GAUGE_RECENT_ACTIVITY_DAYS", "7")))
DEFAULT_WORKERS = min(8, max(1, int(os.getenv("GAIA_GAUGE_WORKERS", "4"))))


def _fetch_user_ids(failures: list[str]) -> Set[str]:
    user_ids: Set[str] = set()
    try:
        rows = pg.fetch(
            """
            select distinct user_id
              from app.user_locations
             where updated_at >= now() - (%s::int * interval '1 day')
            """,
            RECENT_ACTIVITY_DAYS,
        )
        user_ids.update([r["user_id"] for r in rows if r.get("user_id")])
    except Exception as exc:
        failures.append("app.user_locations")
        logger.warning("[gauges] eligibility_source_failed source=app.user_locations error_type=%s", type(exc).__name__)

    try:
        rows = pg.fetch(
            """
            select distinct user_id
              from public.app_user_entitlements_active
             where is_active = true
            """
        )
        user_ids.update([r["user_id"] for r in rows if r.get("user_id")])
    except Exception as exc:
        failures.append("public.app_user_entitlements_active")
        logger.warning("[gauges] eligibility_source_failed source=public.app_user_entitlements_active error_type=%s", type(exc).__name__)

    try:
        rows = pg.fetch(
            """
            select distinct user_id
              from gaia.samples
             where start_time >= now() - (%s::int * interval '1 day')
            """,
            RECENT_ACTIVITY_DAYS,
        )
        user_ids.update([r["user_id"] for r in rows if r.get("user_id")])
    except Exception as exc:
        failures.append("gaia.samples")
        logger.warning("[gauges] eligibility_source_failed source=gaia.samples error_type=%s", type(exc).__name__)

    try:
        rows = pg.fetch(
            """
            select distinct user_id
              from raw.app_analytics_events
             where event_ts_utc >= now() - (%s::int * interval '1 day')
            """,
            RECENT_ACTIVITY_DAYS,
        )
        user_ids.update([r["user_id"] for r in rows if r.get("user_id")])
    except Exception as exc:
        failures.append("raw.app_analytics_events")
        logger.warning("[gauges] eligibility_source_failed source=raw.app_analytics_events error_type=%s", type(exc).__name__)

    return user_ids


def _verify_outputs(
    expected: Set[Tuple[str, date]],
    refreshed: Set[Tuple[str, date]],
    started_at: datetime,
    evaluations: dict[Tuple[str, date], dict],
    summary: dict,
) -> list[str]:
    summary.update(
        outputs_found=0,
        outputs_matching_evaluation=0,
        outputs_superseded=0,
        oldest_output_changed_at=None,
        latest_output_changed_at=None,
    )
    if not expected:
        return []
    user_ids = sorted({user_id for user_id, _ in expected})
    days = [day for _, day in expected]
    rows = pg.fetch(
        """
        select user_id, day, updated_at, inputs_hash
          from marts.user_gauges_day
         where user_id = any(%s::uuid[])
           and day between %s::date and %s::date
        """,
        user_ids,
        min(days),
        max(days),
    )
    found = {(str(row["user_id"]), row["day"]): row for row in rows}
    errors: list[str] = []
    changed_at: list[datetime] = []
    for key in sorted(expected, key=lambda item: (item[0], item[1])):
        evaluation = evaluations.get(key, {})
        if not evaluation.get("inputs_hash") or not evaluation.get("evaluated_at"):
            errors.append("not_evaluated")
        row = found.get(key)
        if row is None:
            errors.append("missing_output")
            continue
        updated_at = row.get("updated_at")
        if isinstance(updated_at, datetime) and updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        if evaluation.get("inputs_hash") and row.get("inputs_hash") != evaluation["inputs_hash"]:
            # The old fingerprint still persisted after an actual input change.
            # A different third hash can be a concurrent writer; report that
            # separately instead of declaring an unrelated timestamp stale.
            if evaluation.get("output_existed") and row.get("inputs_hash") == evaluation.get("previous_inputs_hash"):
                errors.append("changed_inputs_pending")
            else:
                verified_at = evaluation.get("verified_output_updated_at")
                if isinstance(verified_at, datetime) and verified_at.tzinfo is None:
                    verified_at = verified_at.replace(tzinfo=timezone.utc)
                evaluated_at = evaluation.get("evaluated_at")
                if isinstance(evaluated_at, datetime) and evaluated_at.tzinfo is None:
                    evaluated_at = evaluated_at.replace(tzinfo=timezone.utc)
                # A later writer may legitimately replace this run's snapshot.
                # Accept that only with atomic evidence our own exact hash was
                # stored, or observed on an unchanged skip. A newer timestamp
                # alone is not evidence that our evaluated output ever existed.
                if (
                    evaluation.get("verified_output_inputs_hash") == evaluation["inputs_hash"]
                    and isinstance(verified_at, datetime)
                    and isinstance(evaluated_at, datetime)
                    and isinstance(updated_at, datetime)
                    and updated_at > verified_at
                    and updated_at >= evaluated_at - timedelta(seconds=5)
                    and row.get("inputs_hash")
                ):
                    summary["outputs_superseded"] += 1
                else:
                    errors.append("input_hash_mismatch")
        elif evaluation.get("inputs_hash"):
            summary["outputs_matching_evaluation"] += 1
        if not isinstance(updated_at, datetime):
            errors.append("missing_updated_at")
            continue
        changed_at.append(updated_at)
        if key in refreshed and updated_at < started_at - timedelta(seconds=5):
            errors.append("stale_updated_at")
    summary["outputs_found"] = len(expected.intersection(found))
    summary["oldest_output_changed_at"] = min(changed_at).isoformat() if changed_at else None
    summary["latest_output_changed_at"] = max(changed_at).isoformat() if changed_at else None
    return errors


def _iter_users(user_ids: Iterable[str], limit: int | None) -> Iterable[str]:
    count = 0
    for uid in user_ids:
        yield uid
        count += 1
        if limit and count >= limit:
            break


def _score_chunk(
    items: list[Tuple[str, date]],
    *,
    force: bool,
) -> list[Tuple[Tuple[str, date], dict | None, str | None, dict]]:
    results: list[Tuple[Tuple[str, date], dict | None, str | None, dict]] = []
    # Keep one connection per worker so concurrency remains bounded and each
    # user avoids repeated TLS/pool handshakes across the score's small queries.
    with pg.connection_scope():
        for uid, target_day in items:
            key = (uid, target_day)
            diagnostics: dict = {}
            try:
                result = score_user_day(uid, target_day, force=force, diagnostics=diagnostics)
                results.append((key, result, None, diagnostics))
            except Exception as exc:
                results.append((key, None, type(exc).__name__, diagnostics))
                logger.error("[gauges] score_failed error_type=%s", type(exc).__name__)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute daily gauge scores for users.")
    parser.add_argument(
        "--day",
        default=None,
        help="Optional day override in YYYY-MM-DD. Defaults once per batch to the scorer's resolved GAIA_TIMEZONE day (America/Chicago fallback).",
    )
    parser.add_argument("--user-id", default=None, help="Optional single user_id override.")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of users processed.")
    parser.add_argument("--force", action="store_true", help="Recompute even if inputs_hash matches.")
    args = parser.parse_args()

    started_at = datetime.now(timezone.utc)
    eligibility_failures: list[str] = []
    if args.user_id:
        user_ids = {args.user_id}
    else:
        user_ids = _fetch_user_ids(eligibility_failures)

    expected: Set[Tuple[str, date]] = set()
    refreshed: Set[Tuple[str, date]] = set()
    failures: list[str] = []
    evaluations: dict[Tuple[str, date], dict] = {}
    unchanged_inputs = 0

    # Use the same resolved zone as the scorer's raw-input intervals. Capture
    # once so notification preferences or a midnight-crossing batch cannot
    # select a different persisted day for another user.
    target_day = date.fromisoformat(args.day) if args.day else started_at.astimezone(LOCAL_TZ).date()
    items = [
        (
            str(uid),
            target_day,
        )
        for uid in _iter_users(sorted(user_ids), args.limit)
    ]
    expected.update(items)
    worker_count = min(DEFAULT_WORKERS, len(items)) if items else 0
    logger.info(
        "[gauges] scoring users=%d day=%s scoring_timezone=%s workers=%d",
        len(items),
        target_day.isoformat(),
        DEFAULT_TIMEZONE,
        worker_count,
    )

    if items:
        chunks = [items[index::worker_count] for index in range(worker_count)]
        try:
            with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="gauge") as executor:
                chunk_results = executor.map(lambda chunk: _score_chunk(chunk, force=args.force), chunks)
                for results in chunk_results:
                    for key, result, error, diagnostics in results:
                        if diagnostics:
                            evaluations[key] = diagnostics
                        if error is not None:
                            failures.append("score_exception")
                        elif not result or not result.get("ok"):
                            failures.append("score_not_ok")
                        elif not result.get("skipped"):
                            refreshed.add(key)
                        elif result.get("skip_reason") == "unchanged_inputs":
                            unchanged_inputs += 1
                        else:
                            failures.append("unexplained_skip")
        except Exception as exc:
            failures.append("worker_failed")
            logger.error("[gauges] worker_failed error_type=%s", type(exc).__name__)

    evaluation_times = [item["evaluated_at"] for item in evaluations.values() if item.get("evaluated_at")]
    summary = {
        "scope": "selected_users" if args.user_id or args.limit else "all_eligible_users",
        "day": target_day.isoformat(),
        "scoring_timezone": DEFAULT_TIMEZONE,
        "started_at": started_at.isoformat(),
        "eligible_users": len(user_ids) if not args.user_id else None,
        "expected_outputs": len(expected),
        "evaluated": len(evaluation_times),
        "first_evaluated_at": min(evaluation_times).isoformat() if evaluation_times else None,
        "last_evaluated_at": max(evaluation_times).isoformat() if evaluation_times else None,
        "refreshed": len(refreshed),
        "unchanged_inputs": unchanged_inputs,
        "eligibility_source_failures": eligibility_failures,
        "verification_completed": False,
    }
    try:
        failures.extend(_verify_outputs(expected, refreshed, started_at, evaluations, summary))
        summary["verification_completed"] = True
    except Exception as exc:
        failures.append("verification_failed")
        logger.error("[gauges] output verification failed error_type=%s", type(exc).__name__)

    summary["completed_at"] = datetime.now(timezone.utc).isoformat()
    summary["failures"] = dict(Counter(failures))
    summary["status"] = "fail" if failures or eligibility_failures else "pass"
    logger.log(
        logging.ERROR if summary["status"] == "fail" else logging.INFO,
        "[gauges] evaluation_summary=%s",
        json.dumps(summary, sort_keys=True),
    )
    if failures or eligibility_failures:
        logger.error("[gauges] failed counts=%s eligibility_source_failures=%d", dict(Counter(failures)), len(eligibility_failures))
        raise SystemExit(1)
    logger.info("[gauges] done users=%d refreshed=%d", len(expected), len(refreshed))


if __name__ == "__main__":
    main()
