"""Bounded queue preparation, qualified consumption and public-row readback.

No model/provider calls or fallback writer. Only the existing trusted cloud
publisher key writes daily_posts; the queue preparer never has that privilege.
"""
import argparse
import asyncio
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import psycopg
import requests
from app.db import earthscope_writer as queue
from scripts.earthscope_draft_shadow import qualified_public_facts, write_receipt
from scripts.earthscope_preparer_identity import connection_options
from services.earthscope_writer_contract import DraftError, ID_RE, require, sha256
from services.earthscope_local_primary import activation, current_day, publication_post, daily_json


async def prepare_or_reuse(conn, day, version, worker_id, wait_seconds):
    require(type(version) is int and 1 <= version <= 999999, "invalid_version")
    require(ID_RE.fullmatch(worker_id) is not None, "invalid_worker")
    require(type(wait_seconds) is int and 1 <= wait_seconds <= 900, "invalid_wait")
    # Serialize the initial read/collect/enqueue. Retries reuse the durable facts
    # even when upstream observations or their timestamps have advanced.
    async with conn.transaction():
        await conn.execute("select pg_advisory_xact_lock(hashtextextended(%s,0))", ("earthscope-primary:" + day.isoformat(),))
        row = await queue.one(conn, """select * from content.earthscope_writer_jobs
            where day=%s order by job_version desc limit 1 for update""", (day,))
        if row:
            require(row["job_version"] == version and row["intended_worker_id"] == worker_id
                    and row["input_classification"] == "dated_production_facts", "job_version_conflict")
            return row
        now = await queue.now_at(conn)
        packet, _ = await qualified_public_facts(conn, day, now=now)
        return await queue.enqueue(conn, packet, version, worker_id,
                                   now + timedelta(seconds=wait_seconds), "dated_production_facts")


async def await_post(conn, day, version, worker_id, wait_seconds, policy, tz_name):
    current_day(day, await queue.now_at(conn), tz_name)
    row = await prepare_or_reuse(conn, day, version, worker_id, wait_seconds)
    await conn.commit()
    stop = time.monotonic() + wait_seconds
    while True:
        row = await queue.receipt(conn, row["job_id"], version, worker_id)
        await conn.commit()
        if row["status"] == "returned":
            post = publication_post(row, policy, now=await queue.now_at(conn), tz_name=tz_name)
            return post
        require(row["status"] not in {"failed", "expired"}, "local_writer_" + row["status"])
        remaining = stop - time.monotonic()
        require(remaining > 0, "local_writer_wait_timeout")
        await asyncio.sleep(min(2, remaining))


async def configured_post(day, version, wait_seconds, environ, *, review_only=False):
    policy_env = environ if not review_only else {
        **environ, "EARTHSCOPE_WRITER_MODE": "local_primary",
        "EARTHSCOPE_LOCAL_ACCEPTANCE_ID": "review-only-not-accepted"}
    policy = activation(policy_env)
    dsn = environ.get("EARTHSCOPE_DRAFT_PREPARER_DSN", "")
    worker = environ.get("EARTHSCOPE_DRAFT_WORKER_ID", "")
    require(dsn and worker, "preparer_unconfigured")
    async with await psycopg.AsyncConnection.connect(**connection_options(environ)) as conn:
        await conn.execute("set role gaia_earthscope_writer_preparer")
        await conn.execute("set statement_timeout='8s'")
        await conn.execute("set lock_timeout='3s'")
        await conn.commit()
        return await asyncio.wait_for(
            await_post(conn, day, version, worker, wait_seconds, policy,
                       environ.get("GAIA_TIMEZONE") or "America/Chicago"), timeout=wait_seconds + 25)


def publish_once(post, environ, *, session=None):
    """Insert-only with exact readback. No blind retry after an ambiguous POST."""
    session = session or requests.Session()
    url = (environ.get("SUPABASE_REST_URL") or (environ.get("SUPABASE_URL", "").rstrip("/") + "/rest/v1")).rstrip("/")
    parsed = urlsplit(url)
    key = environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    require(parsed.scheme == "https" and parsed.hostname and not parsed.username
            and not parsed.password and not parsed.query and not parsed.fragment and key, "publisher_unconfigured")
    headers = {"apikey": key, "Authorization": "Bearer " + key,
               "Accept-Profile": "content", "Content-Profile": "content"}
    params = {"select": ",".join(post), "day": "eq." + post["day"],
              "platform": "eq.default", "user_id": "is.null", "limit": "2"}
    def read():
        response = session.get(url + "/daily_posts", params=params, headers=headers, timeout=(5, 20), allow_redirects=False)
        require(response.status_code == 200, "publication_read_failed")
        rows = response.json()
        require(isinstance(rows, list) and len(rows) <= 1, "publication_conflict")
        if rows:
            require(rows[0] == post, "publication_conflict")
        return bool(rows)
    if read():
        return "existing_exact_public_row"
    response = session.post(url + "/daily_posts", params={"on_conflict": "day,platform"},
        headers={**headers, "Prefer": "resolution=ignore-duplicates,return=representation"},
        json=[post], timeout=(5, 20), allow_redirects=False)
    require(response.status_code in {200, 201}, "publication_write_failed")
    require(read(), "publication_not_confirmed")
    return "inserted_and_read_back"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--day", type=date.fromisoformat, required=True)
    parser.add_argument("--version", type=int, default=1)
    parser.add_argument("--wait-seconds", type=int, default=600)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--post-output", type=Path, required=True)
    parser.add_argument("--daily-output", type=Path, required=True)
    parser.add_argument("--review-only", action="store_true", help="Real queue exchange and local artifacts only; no public-row write")
    args = parser.parse_args()
    result = {"mode": "local_primary", "day": args.day.isoformat(), "status": "failed", "production_consumption": False}
    try:
        post = asyncio.run(configured_post(args.day, args.version, args.wait_seconds, os.environ, review_only=args.review_only))
        # Retain the exact accepted transport result before the public write.
        write_receipt(args.post_output, post)
        result.update(post_sha256=sha256(post), writer_source=post["metrics_json"]["writer_source"])
        result["publication"] = "not_requested" if args.review_only else publish_once(post, os.environ)
        write_receipt(args.daily_output, daily_json(post))
        result.update(status="review_ready" if args.review_only else "ready", production_consumption=not args.review_only)
        if os.getenv("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a") as handle:
                handle.write("post_sha256=" + sha256(post) + "\n")
    except DraftError as exc:
        result["status"] = exc.code
    except (TimeoutError, asyncio.TimeoutError):
        result["status"] = "local_writer_wait_timeout"
    except Exception:
        # Never emit DSNs, tokens, raw response bodies or exception details.
        result["status"] = "local_primary_unavailable"
    write_receipt(args.receipt, result)
    print(json.dumps({k: result[k] for k in ("status", "mode", "production_consumption")}))
    return 0 if result["status"] in {"ready", "review_ready"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
