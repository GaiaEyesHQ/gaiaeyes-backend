#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from typing import Dict, Iterable, Set, Tuple
from zoneinfo import ZoneInfo

from services.db import pg
from bots.gauges.gauge_scorer import score_user_day


LOG_LEVEL = os.getenv("GAIA_LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)


DEFAULT_TIMEZONE = os.getenv("GAIA_TIMEZONE", "America/Chicago")
RECENT_ACTIVITY_DAYS = max(1, int(os.getenv("GAIA_GAUGE_RECENT_ACTIVITY_DAYS", "7")))
DEFAULT_WORKERS = min(8, max(1, int(os.getenv("GAIA_GAUGE_WORKERS", "4"))))


def _fetch_user_ids() -> Set[str]:
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
        logger.warning("[gauges] app.user_locations fetch failed: %s", exc)

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
        logger.warning("[gauges] entitlements fetch failed: %s", exc)

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
        logger.warning("[gauges] recent HealthKit users fetch failed: %s", exc)

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
        logger.warning("[gauges] recent analytics users fetch failed: %s", exc)

    return user_ids


def _fetch_user_timezones(user_ids: Set[str]) -> Dict[str, str]:
    if not user_ids:
        return {}
    try:
        rows = pg.fetch(
            """
            select user_id, time_zone
              from app.user_notification_preferences
             where user_id = any(%s::uuid[])
            """,
            sorted(user_ids),
        )
    except Exception as exc:
        logger.warning("[gauges] user timezones fetch failed: %s", exc)
        return {}
    return {
        str(row["user_id"]): str(row.get("time_zone") or DEFAULT_TIMEZONE)
        for row in rows
        if row.get("user_id")
    }


def _local_day(time_zone_name: str | None, *, now_utc: datetime | None = None) -> date:
    now_utc = now_utc or datetime.now(timezone.utc)
    candidate = str(time_zone_name or DEFAULT_TIMEZONE).strip() or DEFAULT_TIMEZONE
    try:
        zone = ZoneInfo(candidate)
    except Exception:
        logger.warning("[gauges] invalid timezone=%s; using %s", candidate, DEFAULT_TIMEZONE)
        zone = ZoneInfo(DEFAULT_TIMEZONE)
    return now_utc.astimezone(zone).date()


def _verify_outputs(
    expected: Set[Tuple[str, date]],
    refreshed: Set[Tuple[str, date]],
    started_at: datetime,
) -> list[str]:
    if not expected:
        return []
    user_ids = sorted({user_id for user_id, _ in expected})
    days = [day for _, day in expected]
    rows = pg.fetch(
        """
        select user_id, day, updated_at
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
    for key in sorted(expected, key=lambda item: (item[0], item[1])):
        row = found.get(key)
        if row is None:
            errors.append(f"missing:{key[0]}:{key[1].isoformat()}")
            continue
        if key not in refreshed:
            continue
        updated_at = row.get("updated_at")
        if not isinstance(updated_at, datetime):
            errors.append(f"missing_updated_at:{key[0]}:{key[1].isoformat()}")
            continue
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        if updated_at < started_at - timedelta(seconds=5):
            errors.append(f"stale_updated_at:{key[0]}:{key[1].isoformat()}")
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
) -> list[Tuple[Tuple[str, date], dict | None, str | None]]:
    results: list[Tuple[Tuple[str, date], dict | None, str | None]] = []
    # Keep one connection per worker so concurrency remains bounded and each
    # user avoids repeated TLS/pool handshakes across the score's small queries.
    with pg.connection_scope():
        for uid, target_day in items:
            key = (uid, target_day)
            try:
                result = score_user_day(uid, target_day, force=force)
                results.append((key, result, None))
                logger.info(
                    "[gauges] user=%s day=%s ok=%s skipped=%s",
                    uid,
                    target_day,
                    result.get("ok"),
                    result.get("skipped"),
                )
            except Exception as exc:
                results.append((key, None, str(exc)))
                logger.exception("[gauges] user=%s failed: %s", uid, exc)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute daily gauge scores for users.")
    parser.add_argument(
        "--day",
        default=None,
        help="Optional day override in YYYY-MM-DD. Defaults to each user's local day.",
    )
    parser.add_argument("--user-id", default=None, help="Optional single user_id override.")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of users processed.")
    parser.add_argument("--force", action="store_true", help="Recompute even if inputs_hash matches.")
    args = parser.parse_args()

    if args.user_id:
        user_ids = {args.user_id}
    else:
        user_ids = _fetch_user_ids()

    timezones = _fetch_user_timezones(user_ids)
    started_at = datetime.now(timezone.utc)
    expected: Set[Tuple[str, date]] = set()
    refreshed: Set[Tuple[str, date]] = set()
    failures: list[str] = []

    day_override = date.fromisoformat(args.day) if args.day else None
    items = [
        (
            str(uid),
            day_override or _local_day(timezones.get(str(uid))),
        )
        for uid in _iter_users(sorted(user_ids), args.limit)
    ]
    expected.update(items)
    worker_count = min(DEFAULT_WORKERS, len(items)) if items else 0
    logger.info(
        "[gauges] scoring users=%d day=%s workers=%d",
        len(items),
        args.day or "per-user-local",
        worker_count,
    )

    if items:
        chunks = [items[index::worker_count] for index in range(worker_count)]
        with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="gauge") as executor:
            chunk_results = executor.map(lambda chunk: _score_chunk(chunk, force=args.force), chunks)
            for results in chunk_results:
                for (uid, target_day), result, error in results:
                    if error is not None:
                        failures.append(f"exception:{uid}:{target_day.isoformat()}")
                    elif not result or not result.get("ok"):
                        failures.append(f"not_ok:{uid}:{target_day.isoformat()}")
                    elif not result.get("skipped"):
                        refreshed.add((uid, target_day))

    try:
        failures.extend(_verify_outputs(expected, refreshed, started_at))
    except Exception as exc:
        failures.append("verification_failed")
        logger.exception("[gauges] output verification failed: %s", exc)

    if failures:
        logger.error("[gauges] failed count=%d details=%s", len(failures), failures)
        raise SystemExit(1)
    logger.info("[gauges] done users=%d refreshed=%d", len(expected), len(refreshed))


if __name__ == "__main__":
    main()
