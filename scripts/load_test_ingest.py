#!/usr/bin/env python3
"""
Synthetic load test for Gaia Eyes health sample ingestion.

This script writes synthetic `/v1/samples/batch` payloads using the same
developer-token pattern as the app smoke monitor: `Authorization: Bearer ...`
plus `X-Dev-UserId`. It intentionally uses only the Python standard library.

Key environment variables:
- GAIA_LOAD_BASE_URL or GAIA_MONITOR_BASE_URL: target API base URL.
- GAIA_LOAD_AUTH_BEARER, GAIA_MONITOR_AUTH_BEARER, DEV_BEARER, or WRITE_TOKENS:
  bearer token used for authenticated writes.
- GAIA_LOAD_TZ: timezone query parameter, defaults to America/Chicago.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable
from uuid import NAMESPACE_DNS, uuid5


def _first_env(names: Iterable[str]) -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""


def _first_token_env(names: Iterable[str]) -> str:
    value = _first_env(names)
    if not value:
        return ""
    return value.replace("\n", ",").split(",", 1)[0].strip()


def _default_base_url() -> str:
    return (
        os.getenv("GAIA_LOAD_BASE_URL")
        or os.getenv("GAIA_MONITOR_BASE_URL")
        or "http://127.0.0.1:8000"
    ).rstrip("/")


def _default_bearer() -> str:
    return _first_token_env(
        (
            "GAIA_LOAD_AUTH_BEARER",
            "GAIA_MONITOR_AUTH_BEARER",
            "DEV_BEARER",
            "WRITE_TOKENS",
        )
    )


def _is_local_url(base_url: str) -> bool:
    parsed = urllib.parse.urlparse(base_url)
    host = (parsed.hostname or "").lower()
    return host in {"localhost", "127.0.0.1", "::1"}


def _iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((pct / 100.0) * (len(ordered) - 1))))
    return ordered[index]


@dataclass(frozen=True)
class RequestResult:
    target: str
    status: int
    ok: bool
    db: bool | None
    received: int
    inserted: int
    buffered: int
    skipped: int
    error: str
    elapsed_ms: float


def _sample_for(user_id: str, index: int, base_time: datetime) -> dict[str, Any]:
    sample_time = base_time + timedelta(minutes=index)
    end_time = sample_time + timedelta(minutes=1)
    kind = index % 4
    common = {
        "user_id": user_id,
        # Production constrains this column to real client OS values.
        # Keep synthetic rows identifiable through source/user_id instead.
        "device_os": "ios",
        "source": "loadtest",
        "start_time": _iso_z(sample_time),
        "end_time": _iso_z(end_time),
    }
    if kind == 0:
        return {**common, "type": "heart_rate", "value": 62 + (index % 55), "unit": "count/min"}
    if kind == 1:
        return {**common, "type": "respiratory_rate", "value": 12 + (index % 8), "unit": "count/min"}
    if kind == 2:
        return {**common, "type": "step_count", "value": 1 + (index % 85), "unit": "count"}
    return {**common, "type": "sleep_stage", "value_text": ["inBed", "core", "deep", "rem"][index % 4]}


def _make_samples(user_id: str, rows: int, user_index: int) -> list[dict[str, Any]]:
    base_time = datetime.now(timezone.utc) - timedelta(days=2, hours=user_index)
    return [_sample_for(user_id, index, base_time) for index in range(rows)]


def _headers(bearer: str, user_id: str) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "gaiaeyes-load-test/1.0",
        "X-Dev-UserId": user_id,
    }
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    return headers


def _request_json(
    method: str,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any] | None,
    timeout: float,
) -> tuple[int, dict[str, Any], float]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            return response.status, json.loads(raw) if raw else {}, elapsed_ms
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"error": raw[:240]}
        return exc.code, parsed, elapsed_ms
    except urllib.error.URLError as exc:
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        return 0, {"error": str(exc.reason)}, elapsed_ms


def _post_chunk(
    base_url: str,
    bearer: str,
    user_id: str,
    tz_name: str,
    chunk: list[dict[str, Any]],
    timeout: float,
) -> RequestResult:
    url = f"{base_url}/v1/samples/batch?{urllib.parse.urlencode({'tz': tz_name})}"
    status, data, elapsed_ms = _request_json(
        "POST",
        url,
        _headers(bearer, user_id),
        {"samples": chunk},
        timeout,
    )
    return RequestResult(
        target="POST /v1/samples/batch",
        status=status,
        ok=bool(data.get("ok")),
        db=data.get("db") if isinstance(data.get("db"), bool) else None,
        received=int(data.get("received") or 0),
        inserted=int(data.get("inserted") or 0),
        buffered=int(data.get("buffered") or 0),
        skipped=int(data.get("skipped") or 0),
        error=str(data.get("error") or ""),
        elapsed_ms=elapsed_ms,
    )


def _get_read_path(base_url: str, bearer: str, user_id: str, path: str, timeout: float) -> RequestResult:
    status, data, elapsed_ms = _request_json(
        "GET",
        f"{base_url}/{path.lstrip('/')}",
        _headers(bearer, user_id),
        None,
        timeout,
    )
    return RequestResult(
        target=f"GET /{path.lstrip('/')}",
        status=status,
        ok=200 <= status <= 299 and data.get("ok") is not False,
        db=data.get("db") if isinstance(data.get("db"), bool) else None,
        received=0,
        inserted=0,
        buffered=0,
        skipped=0,
        error=str(data.get("error") or data.get("detail") or ""),
        elapsed_ms=elapsed_ms,
    )


def _run_user(args: argparse.Namespace, user_index: int) -> list[RequestResult]:
    user_id = str(uuid5(NAMESPACE_DNS, f"gaiaeyes-loadtest:{args.run_id}:{user_index}"))
    samples = _make_samples(user_id, args.rows_per_user, user_index)
    results: list[RequestResult] = []

    for offset in range(0, len(samples), args.chunk_size):
        chunk = samples[offset : offset + args.chunk_size]
        results.append(_post_chunk(args.base_url, args.bearer, user_id, args.tz, chunk, args.timeout))
        if args.chunk_pause_ms > 0:
            time.sleep(args.chunk_pause_ms / 1000.0)

    if args.include_reads:
        today = datetime.now(timezone.utc).date().isoformat()
        read_paths = [
            f"v1/features/today?{urllib.parse.urlencode({'tz': args.tz})}",
            "v1/users/me/drivers",
            f"v1/dashboard?{urllib.parse.urlencode({'day': today})}",
        ]
        for path in read_paths:
            results.append(_get_read_path(args.base_url, args.bearer, user_id, path, args.timeout))

    return results


def _print_summary(results: list[RequestResult], started: float) -> int:
    elapsed = time.perf_counter() - started
    latencies = [result.elapsed_ms for result in results]
    status_counts: dict[int, int] = {}
    error_counts: dict[str, int] = {}
    for result in results:
        status_counts[result.status] = status_counts.get(result.status, 0) + 1
        if result.error:
            error_counts[result.error] = error_counts.get(result.error, 0) + 1

    total_received = sum(result.received for result in results)
    total_inserted = sum(result.inserted for result in results)
    total_buffered = sum(result.buffered for result in results)
    total_skipped = sum(result.skipped for result in results)
    failures = [result for result in results if not result.ok and result.buffered == 0]
    buffered_failures = [result for result in results if result.buffered > 0]

    by_target: dict[str, dict[str, Any]] = {}
    for target in sorted({result.target for result in results}):
        target_results = [result for result in results if result.target == target]
        target_latencies = [result.elapsed_ms for result in target_results]
        by_target[target] = {
            "requests": len(target_results),
            "received": sum(result.received for result in target_results),
            "inserted": sum(result.inserted for result in target_results),
            "buffered": sum(result.buffered for result in target_results),
            "skipped": sum(result.skipped for result in target_results),
            "status_counts": {
                str(status): sum(1 for result in target_results if result.status == status)
                for status in sorted({result.status for result in target_results})
            },
            "latency_ms": {
                "min": round(min(target_latencies), 1) if target_latencies else 0,
                "p50": round(statistics.median(target_latencies), 1) if target_latencies else 0,
                "p95": round(_percentile(target_latencies, 95), 1),
                "max": round(max(target_latencies), 1) if target_latencies else 0,
            },
        }

    print(json.dumps(
        {
            "requests": len(results),
            "elapsed_seconds": round(elapsed, 2),
            "requests_per_second": round(len(results) / elapsed, 2) if elapsed > 0 else 0,
            "received": total_received,
            "inserted": total_inserted,
            "buffered": total_buffered,
            "skipped": total_skipped,
            "status_counts": status_counts,
            "error_counts": error_counts,
            "latency_ms": {
                "min": round(min(latencies), 1) if latencies else 0,
                "p50": round(statistics.median(latencies), 1) if latencies else 0,
                "p95": round(_percentile(latencies, 95), 1),
                "max": round(max(latencies), 1) if latencies else 0,
            },
            "by_target": by_target,
        },
        indent=2,
        sort_keys=True,
    ))
    if failures:
        print(f"FAIL: {len(failures)} requests failed without buffering", file=sys.stderr)
        return 1
    if buffered_failures:
        print(f"WARN: {len(buffered_failures)} requests were buffered/deferred", file=sys.stderr)
        return 2
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Synthetic Gaia Eyes ingest load test.")
    parser.add_argument("--base-url", default=_default_base_url(), help="API base URL; defaults to localhost.")
    parser.add_argument("--bearer", default=_default_bearer(), help="Write bearer token; defaults to env.")
    parser.add_argument("--users", type=int, default=5, help="Number of synthetic users.")
    parser.add_argument("--rows-per-user", type=int, default=400, help="Synthetic samples per user.")
    parser.add_argument("--chunk-size", type=int, default=200, help="Rows per /v1/samples/batch request.")
    parser.add_argument("--concurrency", type=int, default=5, help="Concurrent synthetic users.")
    parser.add_argument("--timeout", type=float, default=30.0, help="Per-request timeout seconds.")
    parser.add_argument("--tz", default=os.getenv("GAIA_LOAD_TZ", "America/Chicago"), help="Timezone query value.")
    parser.add_argument("--run-id", default=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    parser.add_argument("--chunk-pause-ms", type=int, default=60, help="Pause between chunks for each user.")
    parser.add_argument("--include-reads", action="store_true", help="Also hit common app read endpoints per user.")
    parser.add_argument("--dry-run", action="store_true", help="Print plan and first sample without writing.")
    parser.add_argument(
        "--allow-non-local-write",
        action="store_true",
        help="Required when base URL is not localhost/127.0.0.1/::1.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    args.base_url = args.base_url.rstrip("/")
    args.users = max(1, args.users)
    args.rows_per_user = max(1, args.rows_per_user)
    args.chunk_size = max(1, args.chunk_size)
    args.concurrency = max(1, min(args.concurrency, args.users))

    first_user = str(uuid5(NAMESPACE_DNS, f"gaiaeyes-loadtest:{args.run_id}:0"))
    first_sample = _make_samples(first_user, 1, 0)[0]
    if args.dry_run:
        print(json.dumps(
            {
                "base_url": args.base_url,
                "users": args.users,
                "rows_per_user": args.rows_per_user,
                "chunk_size": args.chunk_size,
                "concurrency": args.concurrency,
                "bearer_configured": bool(args.bearer),
                "run_id": args.run_id,
                "first_user": first_user,
                "first_sample": first_sample,
            },
            indent=2,
            sort_keys=True,
        ))
        return 0

    if not args.bearer:
        print("Missing bearer. Set GAIA_LOAD_AUTH_BEARER, DEV_BEARER, or WRITE_TOKENS.", file=sys.stderr)
        return 2
    if not _is_local_url(args.base_url) and not args.allow_non_local_write:
        print(
            "Refusing to write to non-local base URL without --allow-non-local-write.",
            file=sys.stderr,
        )
        return 2

    print(
        f"Running ingest load test base={args.base_url} users={args.users} "
        f"rows_per_user={args.rows_per_user} chunk_size={args.chunk_size} "
        f"concurrency={args.concurrency} include_reads={args.include_reads}",
        file=sys.stderr,
    )
    started = time.perf_counter()
    all_results: list[RequestResult] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [executor.submit(_run_user, args, user_index) for user_index in range(args.users)]
        for future in concurrent.futures.as_completed(futures):
            all_results.extend(future.result())
    return _print_summary(all_results, started)


if __name__ == "__main__":
    raise SystemExit(main())
