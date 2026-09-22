"""Opt-in bounded draft preparation/receipt. Never renders or publishes content."""
import argparse
import asyncio
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import psycopg
from app.db import earthscope_writer as queue
from services.earthscope_writer_contract import DraftError, require
from services.earthscope_public_facts import collect_public_inputs, prepare_public_packet


async def qualified_public_facts(conn, day, *, now):
    inputs = await collect_public_inputs(conn, day)
    return prepare_public_packet(day, now=now, **inputs)


async def public_facts(conn, day, *, now):
    packet, _ = await qualified_public_facts(conn, day, now=now)
    return packet


async def run_shadow(conn, day, version, worker_id, wait_seconds):
    require(type(wait_seconds) is int and 1 <= wait_seconds <= 900, "invalid_wait")
    now = await queue.now_at(conn)
    packet, qualification = await qualified_public_facts(conn, day, now=now)
    job = await queue.enqueue(conn, packet, version, worker_id, now + timedelta(seconds=wait_seconds), "dated_production_facts")
    await conn.commit()
    stop = time.monotonic() + wait_seconds
    while True:
        row = await queue.receipt(conn, job["job_id"], version, worker_id)
        await conn.commit()
        if row["status"] in {"returned", "failed", "expired"}:
            return {"status": row["status"], "job_id": row["job_id"], "job_version": version,
                    "facts_sha256": row["facts_sha256"], "claim_id": row["claim_id"],
                    "failure_code": row["failure_code"], "outcome": row["outcome"],
                    "outcome_sha256": row["outcome_sha256"], "acknowledgement_id": row["acknowledgement_id"],
                    "mode": "local_shadow_only", "production_consumption": False,
                    "facts_packet": packet, "source_qualification": qualification}
        remaining = stop - time.monotonic()
        if remaining <= 0:
            # No requeue, regeneration or silently extended deadline.
            await conn.execute("""update content.earthscope_writer_jobs set failure_code='shadow_wait_timeout'
                where job_id=%s and job_version=%s and status in ('queued','claimed')""", (row['job_id'], version))
            await conn.commit()
            return {"status": "shadow_wait_timeout", "job_id": row["job_id"], "job_version": version,
                    "queue_status": row["status"], "mode": "local_shadow_only", "production_consumption": False,
                    "facts_packet": packet, "source_qualification": qualification}
        await asyncio.sleep(min(2, remaining))


async def configured_shadow(day, version, wait_seconds):
    if os.getenv("EARTHSCOPE_DRAFT_SHADOW_ENABLED", "0") != "1":
        return {"status": "disabled", "production_consumption": False}
    dsn = os.getenv("EARTHSCOPE_DRAFT_PREPARER_DSN", "")
    worker_id = os.getenv("EARTHSCOPE_DRAFT_WORKER_ID", "")
    if not dsn or not worker_id:
        return {"status": "preparer_unconfigured", "production_consumption": False}
    try:
        async with await psycopg.AsyncConnection.connect(dsn, connect_timeout=5) as conn:
            await conn.execute("set role gaia_earthscope_writer_preparer")
            await conn.execute("set statement_timeout='8s'")
            await conn.execute("set lock_timeout='3s'")
            await conn.commit()
            return await asyncio.wait_for(run_shadow(conn, day, version, worker_id, wait_seconds), timeout=wait_seconds + 25)
    except DraftError as exc:
        return {"status": exc.code, "production_consumption": False}
    except (asyncio.TimeoutError, TimeoutError):
        return {"status": "shadow_wait_timeout", "production_consumption": False}
    except Exception:
        return {"status": "storage_unavailable", "production_consumption": False}


def write_receipt(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".draft-receipt-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.link(name, path)  # Preserve any existing receipt or later edit.
    finally:
        os.unlink(name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--day", type=date.fromisoformat, default=datetime.now(timezone.utc).date())
    parser.add_argument("--version", type=int, default=1)
    parser.add_argument("--wait-seconds", type=int, default=300)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    result = asyncio.run(configured_shadow(args.day, args.version, args.wait_seconds))
    write_receipt(args.receipt, result)
    print(json.dumps({"status": result["status"], "production_consumption": False}))
    return 0 if result["status"] in {"disabled", "returned"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
