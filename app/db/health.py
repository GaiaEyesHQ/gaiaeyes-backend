from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from psycopg_pool import PoolTimeout

from . import (
    get_pool,
    get_pool_metrics,
    handle_connection_failure,
    handle_pool_timeout,
)


logger = logging.getLogger(__name__)


class DBHealthMonitor:
    """Background task that tracks database availability with hysteresis."""

    _PROBE_INTERVAL_SECONDS = 3.0
    _PROBE_TIMEOUT_SECONDS = 0.3
    _REQUIRED_SUCCESSES = 2
    _REQUIRED_FAILURES = 2

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._task: Optional[asyncio.Task] = None
        self._db_ok: bool = True
        now = datetime.now(timezone.utc)
        self._since: datetime = now
        self._last_change: datetime = now
        self._last_probe: Optional[datetime] = None
        self._consec_ok: int = 0
        self._consec_fail: int = 0
        self._stopped = asyncio.Event()

    async def start(self) -> None:
        async with self._lock:
            if self._task is None or self._task.done():
                self._stopped.clear()
                self._task = asyncio.create_task(self._run(), name="db-health-monitor")

    async def stop(self) -> None:
        async with self._lock:
            task = self._task
            if not task:
                return
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            finally:
                self._task = None
                self._stopped.set()

    async def _run(self) -> None:
        try:
            while True:
                await self._probe_once()
                await asyncio.sleep(self._PROBE_INTERVAL_SECONDS)
        except asyncio.CancelledError:  # pragma: no cover - cooperative shutdown
            raise
        except Exception:  # pragma: no cover - defensive logging
            logger.exception("[HEALTH] monitor loop crashed")

    async def _probe_once(self) -> None:
        success = False
        try:
            pool = await get_pool()
            async with pool.connection(timeout=self._PROBE_TIMEOUT_SECONDS) as conn:
                async with conn.cursor() as cur:
                    await cur.execute("select 1;")
            success = True
        except PoolTimeout as exc:
            await handle_pool_timeout("health monitor timeout")
            logger.warning("[HEALTH] monitor pool timeout: %s", exc)
        except Exception as exc:
            await handle_connection_failure(exc)
            logger.warning("[HEALTH] monitor probe failed: %s", exc)
        finally:
            self._record_probe(success)

    def _record_probe(self, success: bool) -> None:
        now = datetime.now(timezone.utc)
        self._last_probe = now
        if success:
            self._consec_ok += 1
            self._consec_fail = 0
            if not self._db_ok and self._consec_ok >= self._REQUIRED_SUCCESSES:
                self._set_state(True, now, reason=f"consec_ok={self._consec_ok}")
        else:
            self._consec_fail += 1
            self._consec_ok = 0
            if self._db_ok and self._consec_fail >= self._REQUIRED_FAILURES:
                self._set_state(False, now, reason=f"consec_fail={self._consec_fail}")

    def _set_state(self, ok: bool, when: datetime, *, reason: str) -> None:
        self._db_ok = ok
        self._since = when
        self._last_change = when
        if ok:
            logger.info("[HEALTH] db=True  (%s)", reason)
        else:
            logger.warning("[HEALTH] db=False (%s)", reason)

    def get_db_ok(self) -> bool:
        return self._db_ok

    def get_sticky_age_ms(self) -> int:
        base = self._since if self._since else datetime.now(timezone.utc)
        delta = datetime.now(timezone.utc) - base
        return int(delta.total_seconds() * 1000)

    def snapshot(self) -> Dict[str, Any]:
        since_iso = self._since.isoformat()
        last_change_iso = self._last_change.isoformat()
        pool_metrics = get_pool_metrics()
        return {
            "db_ok": self._db_ok,
            "since": since_iso,
            "last_change": last_change_iso,
            "consec_ok": self._consec_ok,
            "consec_fail": self._consec_fail,
            "last_probe": self._last_probe.isoformat() if self._last_probe else None,
            "sticky_age_ms": self.get_sticky_age_ms(),
            "pool_backend": pool_metrics.get("backend"),
        }


_health_monitor: Optional[DBHealthMonitor] = None


def get_health_monitor() -> Optional[DBHealthMonitor]:
    return _health_monitor


async def ensure_health_monitor_started() -> DBHealthMonitor:
    global _health_monitor
    if _health_monitor is None:
        _health_monitor = DBHealthMonitor()
    await _health_monitor.start()
    return _health_monitor


async def stop_health_monitor() -> None:
    monitor = _health_monitor
    if monitor is not None:
        await monitor.stop()
