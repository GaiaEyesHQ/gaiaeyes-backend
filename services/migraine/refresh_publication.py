"""Short, optimistic publication fences for correction-derived outputs.

No lock is held during computation. Canonical corrections advance generation;
worker claims/recoveries and successful publications advance writer_epoch.
"""
from __future__ import annotations
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator
from psycopg.rows import dict_row
from services.db import pg


class StaleRefreshPublication(RuntimeError):
    """Computed inputs or worker authority were superseded; retry from fresh reads."""


class RefreshPublicationUnavailable(RuntimeError):
    """A durable worker must never fall back to unfenced publication."""


@dataclass(frozen=True)
class PublicationSnapshot:
    generation: int = 0
    writer_epoch: int = 0
    storage_available: bool = False


@dataclass(frozen=True)
class WorkerPublication:
    user_id: str
    generation: int
    lease_token: str


_worker: ContextVar[WorkerPublication | None] = ContextVar('migraine_refresh_publisher', default=None)


@contextmanager
def worker_publication(user_id: str, generation: int, lease_token: str) -> Iterator[None]:
    value = WorkerPublication(str(user_id), int(generation), str(lease_token))
    if not value.user_id or not value.lease_token:
        raise ValueError('worker identity and lease token are required')
    token = _worker.set(value)
    try:
        yield
    finally:
        _worker.reset(token)


def is_worker_publication() -> bool:
    return _worker.get() is not None


def _available(conn) -> bool:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("select to_regclass('raw.migraine_time_refresh_users') is not null as available")
        return bool(cur.fetchone()['available'])


def _snapshot(row, available: bool = True) -> PublicationSnapshot:
    return PublicationSnapshot(int(row['generation']), int(row['writer_epoch']), available) if row else PublicationSnapshot(storage_available=available)


def capture_user_generation(user_id: str, conn=None) -> PublicationSnapshot:
    if conn is None:
        with pg._connection() as connection:
            return capture_user_generation(user_id, connection)
    worker = _worker.get()
    if worker is not None and worker.user_id != str(user_id):
        raise StaleRefreshPublication('worker user scope mismatch')
    if not _available(conn):
        if worker is not None:
            raise RefreshPublicationUnavailable('durable refresh storage is unavailable')
        return PublicationSnapshot()
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute('select generation,writer_epoch,lease_token,lease_until > clock_timestamp() as live_lease from raw.migraine_time_refresh_users where user_id=%s', (user_id,))
        row = cur.fetchone()
    if worker is not None:
        if not row or int(row['generation']) != worker.generation or str(row['lease_token']) != worker.lease_token or not row['live_lease']:
            raise StaleRefreshPublication('worker claim is no longer current')
    elif row and row['live_lease']:
        raise StaleRefreshPublication('durable worker owns this user')
    return _snapshot(row)


def capture_all_generations(conn=None) -> dict[str, PublicationSnapshot]:
    if conn is None:
        with pg._connection() as connection:
            return capture_all_generations(connection)
    if _worker.get() is not None:
        raise StaleRefreshPublication('a user-scoped worker cannot publish all users')
    if not _available(conn):
        return {}
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute('select user_id,generation,writer_epoch from raw.migraine_time_refresh_users')
        return {str(row['user_id']): _snapshot(row) for row in cur.fetchall()}


@contextmanager
def publication_guard(conn, user_id: str, snapshot: PublicationSnapshot) -> Iterator[bool]:
    """Atomically fence and publish; yield whether this is a correction user.

    Call only after input reads/computation. Caller must enter with an idle
    connection, or an explicitly scoped short transaction, never the long read
    transaction. The state row is held only until the publication commits.
    """
    worker = _worker.get()
    if worker is not None and worker.user_id != str(user_id):
        raise StaleRefreshPublication('worker user scope mismatch')
    with conn.transaction():
        with conn.cursor() as limits:
            limits.execute("set local lock_timeout = '2000ms'")
            limits.execute("set local statement_timeout = '5000ms'")
        if not _available(conn):
            if snapshot.storage_available or worker is not None:
                raise RefreshPublicationUnavailable('durable refresh storage disappeared')
            yield False
            return
        with conn.cursor(row_factory=dict_row) as cur:
            # Insert at publication, not capture, to close the no-row race with
            # a first correction. A competing correction waits only for this
            # short transaction; it never waits for input reads or computation.
            cur.execute('insert into raw.migraine_time_refresh_users (user_id) values (%s) on conflict (user_id) do nothing', (user_id,))
            cur.execute('select generation,writer_epoch,lease_token,lease_until > clock_timestamp() as live_lease from raw.migraine_time_refresh_users where user_id=%s for update', (user_id,))
            row = cur.fetchone()
            if int(row['generation']) != snapshot.generation or int(row['writer_epoch']) != snapshot.writer_epoch:
                raise StaleRefreshPublication('correction or publication superseded the computed inputs')
            if worker is not None:
                if int(row['generation']) != worker.generation or str(row['lease_token']) != worker.lease_token or not row['live_lease']:
                    raise StaleRefreshPublication('worker claim expired or was replaced')
            elif row['live_lease']:
                raise StaleRefreshPublication('durable worker owns this user')
            limits = pg._operation_timeout_settings.get()
            with pg.operation_timeouts(
                connect_timeout=min(limits[0], 5) if limits else 5,
                statement_timeout_ms=min(limits[1], 5000) if limits else 5000,
            ):
                yield bool(row['generation'] > 0 or worker is not None)
            if worker is not None:
                cur.execute('select lease_until > clock_timestamp() as live_lease from raw.migraine_time_refresh_users where user_id=%s', (user_id,))
                if not cur.fetchone()['live_lease']:
                    raise StaleRefreshPublication('worker claim expired during publication')
            cur.execute('update raw.migraine_time_refresh_users set writer_epoch=writer_epoch+1 where user_id=%s', (user_id,))
