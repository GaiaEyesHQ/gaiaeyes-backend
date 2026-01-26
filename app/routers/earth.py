from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from psycopg.rows import dict_row

from app.db import get_db


router = APIRouter(prefix="/v1")


def _iso(ts):
    if isinstance(ts, datetime):
        return ts.astimezone(timezone.utc).isoformat()
    if isinstance(ts, date):
        return datetime.combine(ts, datetime.min.time(), tzinfo=timezone.utc).isoformat()
    return None


def _project_harmonics(row: Dict) -> Dict[str, Optional[float]]:
    """Return only f0..f5 keys if present in the row (robust to schema drift)."""
    harmonics = {}
    for i in range(6):
        k = f"f{i}"
        if k in row:
            harmonics[k] = row.get(k)
    # Provide a convenience alias if combined_f1 exists
    if "combined_f1" in row:
        harmonics["combined_f1"] = row.get("combined_f1")
    return harmonics


@router.get("/earth/schumann/latest")
async def schumann_latest(conn=Depends(get_db)):
    """
    Returns the most recent Schumann harmonics snapshot.

    Primary source: marts.schumann_latest_v2 (if present)
    Fallback:       marts.schumann_latest, marts.schumann_daily_v2, then marts.schumann_daily
    """
    row = None

    # Try v2 "latest" view first
    try:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                select ts_utc, generated_at, f0, f1, f2, f3, f4, f5, combined_f1
                from marts.schumann_latest_v2
                order by coalesce(generated_at, ts_utc) desc
                limit 1
                """,
                prepare=False,
            )
            row = await cur.fetchone()
    except Exception:
        row = None

    # Fallback: canonical latest
    if not row:
        try:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    select ts_utc, generated_at, f0, f1, f2, f3, f4, f5, combined_f1
                    from marts.schumann_latest
                    order by coalesce(generated_at, ts_utc) desc
                    limit 1
                    """,
                    prepare=False,
                )
                row = await cur.fetchone()
        except Exception:
            row = None

    # Fallback: most recent daily (v2 first, then canonical)
    if not row:
        for daily_sql in (
            """
            select day as ts_utc, generated_at, f0, f1, f2, f3, f4, f5, combined_f1
            from marts.schumann_daily_v2
            order by day desc
            limit 1
            """,
            """
            select day as ts_utc, generated_at, f0, f1, f2, f3, f4, f5, combined_f1
            from marts.schumann_daily
            order by day desc
            limit 1
            """,
        ):
            try:
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(daily_sql, prepare=False)
                    r = await cur.fetchone()
                    if r:
                        row = r
                        break
            except Exception:
                continue

    if not row:
        return {"ok": True, "generated_at": None, "harmonics": {}}

    ts = row.get("generated_at") or row.get("ts_utc")
    return {
        "ok": True,
        "generated_at": _iso(ts),
        "harmonics": _project_harmonics(row),
    }


@router.get("/earth/schumann/daily")
async def schumann_daily(
    days: int = Query(30, ge=1, le=365),
    cols: List[str] = Query(default=[]),
    conn=Depends(get_db),
):
    """
    Returns daily Schumann harmonics for the most recent N days.
    Optional `cols` filters to a subset of fields (e.g., cols=f1&cols=combined_f1).
    Prefers marts.schumann_daily_v2 if present, otherwise falls back to marts.schumann_daily.
    """
    rows = None
    last_exc: Optional[Exception] = None

    for sql in (
        """
        select day as ts_utc, generated_at, f0, f1, f2, f3, f4, f5, combined_f1
        from marts.schumann_daily_v2
        order by day desc
        limit %s
        """,
        """
        select day as ts_utc, generated_at, f0, f1, f2, f3, f4, f5, combined_f1
        from marts.schumann_daily
        order by day desc
        limit %s
        """,
    ):
        try:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(sql, (days,), prepare=False)
                rows = await cur.fetchall()
                if rows is not None:
                    break
        except Exception as exc:  # pragma: no cover
            last_exc = exc
            rows = None

    if rows is None:
        return {"ok": False, "error": f"schumann_daily failed: {last_exc}"}

    out = []
    for r in rows:
        item = {
            "ts": _iso(r.get("generated_at") or r.get("ts_utc")),
            "harmonics": _project_harmonics(r),
        }
        if cols:
            item["harmonics"] = {k: v for k, v in item["harmonics"].items() if k in cols}
        out.append(item)

    return {"ok": True, "count": len(out), "rows": out}


@router.get("/earth/schumann/series")
async def schumann_series(
    limit: int = Query(2000, ge=10, le=20000),
    cols: List[str] = Query(default=[]),
    conn=Depends(get_db),
):
    """
    Returns raw Schumann time series from marts.schumann_telemetry.
    Use `limit` to bound rows (most-recent first). Use `cols` to filter keys.
    """
    try:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                select ts_utc, generated_at, f0, f1, f2, f3, f4, f5, combined_f1
                from marts.schumann_telemetry
                order by coalesce(generated_at, ts_utc) desc
                limit %s
                """,
                (limit,),
                prepare=False,
            )
            rows = await cur.fetchall()
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "error": f"schumann_series failed: {exc}"}

    out = []
    for r in rows:
        item = {
            "ts": _iso(r.get("generated_at") or r.get("ts_utc")),
            "harmonics": _project_harmonics(r),
        }
        if cols:
            item["harmonics"] = {k: v for k, v in item["harmonics"].items() if k in cols}
        out.append(item)

    return {"ok": True, "count": len(out), "rows": out}


@router.get("/earth/schumann/diag")
async def schumann_diag(conn=Depends(get_db)):
    """
    Lightweight diagnostics for Schumann tables.
    """
    def _safe_count(sql: str) -> Optional[int]:
        try:
            return sql  # placeholder for code clarity below (we execute inline)
        except Exception:
            return None

    counts: Dict[str, Optional[int]] = {
        "marts.schumann_latest_v2": None,
        "marts.schumann_daily_v2": None,
        "marts.schumann_latest": None,
        "marts.schumann_daily": None,
        "marts.schumann_telemetry": None,
    }

    try:
        async with conn.cursor(row_factory=dict_row) as cur:
            # latest_v2
            try:
                await cur.execute("select count(*) as c from marts.schumann_latest_v2", prepare=False)
                counts["marts.schumann_latest_v2"] = (await cur.fetchone())["c"]
            except Exception:
                counts["marts.schumann_latest_v2"] = None
            # daily_v2
            try:
                await cur.execute("select count(*) as c from marts.schumann_daily_v2", prepare=False)
                counts["marts.schumann_daily_v2"] = (await cur.fetchone())["c"]
            except Exception:
                counts["marts.schumann_daily_v2"] = None
            # latest
            try:
                await cur.execute("select count(*) as c from marts.schumann_latest", prepare=False)
                counts["marts.schumann_latest"] = (await cur.fetchone())["c"]
            except Exception:
                counts["marts.schumann_latest"] = None
            # daily
            try:
                await cur.execute("select count(*) as c from marts.schumann_daily", prepare=False)
                counts["marts.schumann_daily"] = (await cur.fetchone())["c"]
            except Exception:
                counts["marts.schumann_daily"] = None
            # telemetry
            try:
                await cur.execute("select count(*) as c from marts.schumann_telemetry", prepare=False)
                counts["marts.schumann_telemetry"] = (await cur.fetchone())["c"]
            except Exception:
                counts["marts.schumann_telemetry"] = None
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "error": f"schumann_diag failed: {exc}"}

    return {"ok": True, "counts": counts}
