"""Durable draft queue; caller commits before acknowledging a transport request."""
from contextlib import asynccontextmanager
from datetime import timedelta, timezone
from uuid import UUID, uuid4

from psycopg.rows import dict_row
from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb

from services.earthscope_writer_contract import (
    DraftError, canonical, job_envelope, require, sha256, validate_facts, validate_outcome,
    timestamp,
)


async def one(conn, sql, params=()):
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(sql, params)
        return await cur.fetchone()


async def now_at(conn, injected=None):
    value = injected if injected is not None else (await one(conn, "select clock_timestamp() as ts"))["ts"]
    require(value.utcoffset() is not None)
    return value.astimezone(timezone.utc)


@asynccontextmanager
async def transaction(conn):
    # Domain failures may follow a deliberate durable expiry transition. Keep
    # that transition; unexpected database exceptions still roll back normally.
    error = None
    async with conn.transaction():
        try:
            yield
        except DraftError as exc:
            error = exc
    if error:
        raise error


async def expire(conn, worker_id, now):
    await conn.execute("""
        update content.earthscope_writer_jobs
        set status='expired', completed_at=%s,
            failure_code=case when lease_expires_at <= %s then 'claim_expired'
                              when deadline_at <= %s then 'job_expired' else 'facts_stale' end
        where intended_worker_id=%s and status in ('queued','claimed')
          and (deadline_at <= %s or lease_expires_at <= %s
               or (input_classification='dated_production_facts' and day <> %s))
    """, (now, now, now, worker_id, now, now, now.date()))


async def enqueue(conn, packet, version, worker_id, deadline_at, classification, *, now=None):
    require(isinstance(packet, dict))
    require(type(version) is int and 1 <= version <= 999999)
    require(isinstance(worker_id, str) and 3 <= len(worker_id) <= 80)
    async with transaction(conn):
        await conn.execute("select pg_advisory_xact_lock(hashtextextended(%s,0))", ("earthscope-job:" + str(packet.get("job_id")),))
        clock = await now_at(conn, now)
        day = validate_facts(packet, classification, clock)
        require(deadline_at.utcoffset() is not None and clock < deadline_at <= clock + timedelta(seconds=1800))
        await expire(conn, worker_id, clock)
        prior = await one(conn, """select * from content.earthscope_writer_jobs
            where job_id=%s order by job_version desc limit 1 for update""", (packet["job_id"],))
        if prior and prior["job_version"] == version:
            require(prior["facts_sha256"] == sha256(packet) and prior["input_classification"] == classification
                    and prior["intended_worker_id"] == worker_id, "job_conflict", 409)
            return prior
        if prior:
            require(version > prior["job_version"] and prior["status"] not in ("queued", "claimed"), "job_version_conflict", 409)
        try:
            async with conn.transaction():
                return await one(conn, """insert into content.earthscope_writer_jobs
                    (job_id,job_version,day,intended_worker_id,input_classification,facts_packet,facts_sha256,created_at,deadline_at)
                    values (%s,%s,%s,%s,%s,%s,%s,%s,%s) returning *""",
                    (packet["job_id"], version, day, worker_id, classification, Jsonb(packet), sha256(packet), clock, deadline_at))
        except UniqueViolation as exc:
            raise DraftError("job_conflict", 409) from exc


async def claim_next(conn, worker_id, request_id, *, now=None):
    try:
        require(isinstance(request_id, str) and str(UUID(request_id)) == request_id, "invalid_request")
    except (ValueError, TypeError) as exc:
        raise DraftError("invalid_request") from exc
    async with transaction(conn):
        await conn.execute("select pg_advisory_xact_lock(hashtextextended(%s,0))", ("earthscope-worker:" + worker_id,))
        clock = await now_at(conn, now)
        await expire(conn, worker_id, clock)
        previous = await one(conn, """select job_id,job_version from content.earthscope_writer_claim_requests
            where worker_id=%s and claim_request_id=%s""", (worker_id, request_id))
        if previous:
            if previous["job_id"] is None:
                return {"status": "idle", "job": None}
            row = await one(conn, """select * from content.earthscope_writer_jobs
                where job_id=%s and job_version=%s for update""", (previous["job_id"], previous["job_version"]))
            require(row["status"] != "expired" and clock < row["deadline_at"] and clock < row["lease_expires_at"], "claim_expired", 410)
            require(row["facts_sha256"] == sha256(row["facts_packet"]), "facts_binding_mismatch", 409)
            return {"status": "claimed", "job": job_envelope(row)}
        busy = await one(conn, """select 1 from content.earthscope_writer_jobs
            where intended_worker_id=%s and status='claimed' limit 1""", (worker_id,))
        require(not busy, "worker_busy", 409)
        row = await one(conn, """select * from content.earthscope_writer_jobs
            where intended_worker_id=%s and status='queued'
            order by created_at,job_id,job_version for update skip locked limit 1""", (worker_id,))
        if row:
            require(row["facts_sha256"] == sha256(row["facts_packet"]), "facts_binding_mismatch", 409)
            validate_facts(row["facts_packet"], row["input_classification"], clock)
            row = await one(conn, """update content.earthscope_writer_jobs
                set status='claimed',claim_id=%s,claimed_at=%s,lease_expires_at=%s
                where job_id=%s and job_version=%s returning *""",
                (str(uuid4()), clock, min(clock + timedelta(seconds=900), row["deadline_at"]), row["job_id"], row["job_version"]))
        await conn.execute("""insert into content.earthscope_writer_claim_requests
            (worker_id,claim_request_id,job_id,job_version) values (%s,%s,%s,%s)""",
            (worker_id, request_id, row["job_id"] if row else None, row["job_version"] if row else None))
        return {"status": "claimed", "job": job_envelope(row)} if row else {"status": "idle", "job": None}


def acknowledgement(row):
    return {"status": "acknowledged", "outcome_sha256": row["outcome_sha256"],
            "acknowledgement_id": row["acknowledgement_id"]}


async def return_outcome(conn, worker_id, outcome, digest, *, now=None):
    require(isinstance(outcome, dict) and digest == sha256(outcome), "hash_mismatch")
    require(isinstance(outcome.get("job_id"), str) and type(outcome.get("job_version")) is int, "invalid_outcome")
    async with transaction(conn):
        row = await one(conn, """select * from content.earthscope_writer_jobs
            where job_id=%s and job_version=%s for update""", (outcome["job_id"], outcome["job_version"]))
        require(row is not None and row["intended_worker_id"] == worker_id, "claim_mismatch", 409)
        require(row["claim_id"] is not None and row["claim_id"] == outcome.get("claim_id"), "claim_mismatch", 409)
        # Readback of a committed receipt is idempotent even if its lease is now over.
        if row["acknowledgement_id"]:
            require(row["outcome_sha256"] == digest and canonical(row["outcome"]) == canonical(outcome), "outcome_conflict", 409)
            return acknowledgement(row)
        clock = await now_at(conn, now)
        if row["status"] == "expired" or clock >= row["deadline_at"] or clock >= row["lease_expires_at"] or (
            row["input_classification"] == "dated_production_facts" and row["day"] != clock.date()
        ):
            code = "facts_stale" if row["day"] != clock.date() and row["input_classification"] == "dated_production_facts" else "claim_expired"
            await conn.execute("""update content.earthscope_writer_jobs set status='expired',completed_at=%s,failure_code=%s
                where job_id=%s and job_version=%s""", (clock, code, row["job_id"], row["job_version"]))
            raise DraftError(code, 410)
        require(row["status"] == "claimed", "claim_mismatch", 409)
        latest = await one(conn, "select max(job_version) as version from content.earthscope_writer_jobs where job_id=%s", (row["job_id"],))
        require(latest["version"] == row["job_version"], "job_version_conflict", 409)
        require(row["facts_sha256"] == sha256(row["facts_packet"]), "facts_binding_mismatch", 409)
        validate_facts(row["facts_packet"], row["input_classification"], clock)
        validate_outcome(outcome, digest, job_envelope(row), clock)
        require(timestamp(outcome["recorded_at"]) >= row["claimed_at"], "invalid_outcome")
        row = await one(conn, """update content.earthscope_writer_jobs
            set status=%s,outcome=%s,outcome_sha256=%s,acknowledgement_id=%s,completed_at=%s,failure_code=%s
            where job_id=%s and job_version=%s returning *""",
            ("returned" if outcome["status"] == "draft_review_ready" else "failed", Jsonb(outcome), digest, str(uuid4()), clock,
             None if outcome["status"] == "draft_review_ready" else outcome["status"], row["job_id"], row["job_version"]))
        return acknowledgement(row)


async def receipt(conn, job_id, version, worker_id, *, now=None):
    async with transaction(conn):
        clock = await now_at(conn, now)
        await expire(conn, worker_id, clock)
        return await one(conn, """select * from content.earthscope_writer_jobs
            where job_id=%s and job_version=%s and intended_worker_id=%s""", (job_id, version, worker_id))
