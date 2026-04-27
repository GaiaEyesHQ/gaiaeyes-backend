#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
from pathlib import Path
from typing import Any, Dict, List

from redis.asyncio import Redis

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import close_pool, get_pool
from app.routers.ingest import (
    DEFAULT_TIMEZONE,
    INGEST_REDIS_QUEUE_KEY,
    BatchInsertError,
    SampleIn,
    _maybe_schedule_refresh,
    _resolve_timezone,
    _sample_refresh_days,
    _today_local,
    safe_insert_batch,
)


logger = logging.getLogger("ingest_queue_worker")


def _load_dotenv_if_available() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(".env")
    except Exception:
        return


def _queue_key() -> str:
    return os.getenv("GAIA_INGEST_REDIS_QUEUE_KEY", INGEST_REDIS_QUEUE_KEY)


def _redis_url() -> str:
    return os.getenv("REDIS_URL", "").strip()


async def _process_entry(entry: Dict[str, Any]) -> tuple[int, int]:
    samples_data = entry.get("samples") or []
    dev_uid = entry.get("dev_uid")
    refresh_user = entry.get("refresh_user")
    tz_name = str(entry.get("tz") or DEFAULT_TIMEZONE)
    tz_resolved, tzinfo = _resolve_timezone(tz_name)

    models: List[SampleIn] = []
    for payload in samples_data:
        try:
            models.append(SampleIn(**payload))
        except Exception as exc:
            logger.warning("[INGEST-WORKER] dropping invalid queued sample: %s", exc)

    if not models:
        return 0, 0

    pool = await get_pool()
    inserted, skipped, _ = await safe_insert_batch(
        pool,
        [(sample, idx) for idx, sample in enumerate(models)],
        dev_uid,
    )

    if refresh_user and inserted > 0:
        refresh_days = _sample_refresh_days(models, tzinfo) or [_today_local(tzinfo)]
        for day_local in refresh_days:
            await _maybe_schedule_refresh(refresh_user, day_local, inserted, tz_resolved)

    return inserted, skipped


async def _worker_loop(client: Redis, key: str, stop_event: asyncio.Event, *, retry_delay: float) -> None:
    while not stop_event.is_set():
        item = await client.blpop(key, timeout=5)
        if not item:
            continue

        _, raw = item
        try:
            entry = json.loads(raw)
        except Exception:
            logger.warning("[INGEST-WORKER] dropping corrupt queue payload")
            continue

        try:
            inserted, skipped = await _process_entry(entry if isinstance(entry, dict) else {})
            logger.info("[INGEST-WORKER] processed key=%s inserted=%d skipped=%d", key, inserted, skipped)
        except BatchInsertError as exc:
            logger.warning("[INGEST-WORKER] db unavailable; requeueing reason=%s", exc.reason)
            await client.lpush(key, raw)
            await asyncio.sleep(retry_delay)
        except Exception as exc:
            logger.exception("[INGEST-WORKER] unexpected failure; requeueing: %s", exc)
            await client.lpush(key, raw)
            await asyncio.sleep(retry_delay)


async def _run(args: argparse.Namespace) -> int:
    redis_url = args.redis_url or _redis_url()
    if not redis_url:
        raise RuntimeError("REDIS_URL is required for ingest queue worker")

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(signum, stop_event.set)
        except NotImplementedError:  # pragma: no cover - platform-specific
            pass

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO))
    client = Redis.from_url(redis_url, decode_responses=True)
    await client.ping()
    logger.info("[INGEST-WORKER] started key=%s", args.queue_key)

    try:
        await _worker_loop(client, args.queue_key, stop_event, retry_delay=args.retry_delay)
    finally:
        await client.aclose()
        await close_pool()
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Drain Redis-backed Gaia Eyes health ingest queue.")
    parser.add_argument("--redis-url", default="")
    parser.add_argument("--queue-key", default=_queue_key())
    parser.add_argument("--retry-delay", type=float, default=float(os.getenv("GAIA_INGEST_WORKER_RETRY_DELAY", "5.0")))
    parser.add_argument("--log-level", default=os.getenv("GAIA_LOG_LEVEL", "INFO"))
    return parser.parse_args()


def main() -> int:
    _load_dotenv_if_available()
    args = _parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
