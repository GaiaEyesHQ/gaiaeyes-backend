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


# New helper: project amplitude keys if present
def _project_amplitude(row: Dict) -> Dict[str, Optional[float]]:
    """Return amplitude proxy keys if present (robust to schema drift)."""
    amp = {}
    for k in ("sr_total_0_20", "band_7_9", "band_13_15", "band_18_20"):
        if k in row:
            amp[k] = row.get(k)
    return amp


# New: fetch latest primary from ext.schumann
async def _fetch_latest_ext_primary(conn) -> Optional[Dict]:
    """Fetch latest primary snapshot from ext.schumann tall rows.

    We pivot channels into columns using FILTER aggregates.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            with latest_ts as (
              select max(ts_utc) as ts_utc
              from ext.schumann
              where (meta->>'is_primary')::boolean is true
            )
            select
              s.ts_utc,
              max(s.ts_utc) as generated_at,
              max(s.value_num) filter (where s.channel='fundamental_hz') as f0,
              max(s.value_num) filter (where s.channel='F1') as f1,
              max(s.value_num) filter (where s.channel='F2') as f2,
              max(s.value_num) filter (where s.channel='F3') as f3,
              max(s.value_num) filter (where s.channel='F4') as f4,
              max(s.value_num) filter (where s.channel='F5') as f5,
              max(s.value_num) filter (where s.channel='sr_total_0_20') as sr_total_0_20,
              max(s.value_num) filter (where s.channel='band_7_9') as band_7_9,
              max(s.value_num) filter (where s.channel='band_13_15') as band_13_15,
              max(s.value_num) filter (where s.channel='band_18_20') as band_18_20,
              -- bins + axis metadata live inside meta.raw on each row; pick any primary row at this ts
              (max(s.meta->'raw'->'spectrogram_bins')) as spectrogram_bins,
              (max((s.meta->'raw'->>'freq_start_hz')::float)) as freq_start_hz,
              (max((s.meta->'raw'->>'freq_step_hz')::float)) as freq_step_hz,
              (max((s.meta->'raw'->>'quality_score')::float)) as quality_score,
              (max((s.meta->'raw'->>'usable')::boolean)) as usable,
              (max(s.meta->'primary_source')) as primary_source
            from ext.schumann s
            join latest_ts lt on s.ts_utc = lt.ts_utc
            where (s.meta->>'is_primary')::boolean is true
            group by s.ts_utc
            """,
            prepare=False,
        )
        return await cur.fetchone()


async def _fetch_series_ext_primary(conn, limit: int) -> List[Dict]:
    """Fetch most-recent primary series from ext.schumann tall rows."""
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            with prim as (
              select ts_utc, channel, value_num, meta
              from ext.schumann
              where (meta->>'is_primary')::boolean is true
            )
            select
              ts_utc,
              max(ts_utc) as generated_at,
              max(value_num) filter (where channel='fundamental_hz') as f0,
              max(value_num) filter (where channel='F1') as f1,
              max(value_num) filter (where channel='F2') as f2,
              max(value_num) filter (where channel='F3') as f3,
              max(value_num) filter (where channel='F4') as f4,
              max(value_num) filter (where channel='F5') as f5,
              max(value_num) filter (where channel='sr_total_0_20') as sr_total_0_20,
              max(value_num) filter (where channel='band_7_9') as band_7_9,
              max(value_num) filter (where channel='band_13_15') as band_13_15,
              max(value_num) filter (where channel='band_18_20') as band_18_20,
              (max(meta->'raw'->'spectrogram_bins')) as spectrogram_bins,
              (max((meta->'raw'->>'freq_start_hz')::float)) as freq_start_hz,
              (max((meta->'raw'->>'freq_step_hz')::float)) as freq_step_hz,
              (max((meta->'raw'->>'quality_score')::float)) as quality_score,
              (max((meta->'raw'->>'usable')::boolean)) as usable,
              (max(meta->'primary_source')) as primary_source
            from prim
            group by ts_utc
            order by coalesce(generated_at, ts_utc) desc
            limit %s
            """,
            (limit,),
            prepare=False,
        )
        return await cur.fetchall()


@router.get("/earth/schumann/latest")
async def schumann_latest(conn=Depends(get_db)):
    """
    Returns the most recent Schumann harmonics snapshot.

    Primary source: marts.schumann_latest_v2 (if present)
    Fallback:       marts.schumann_latest, marts.schumann_daily_v2, then marts.schumann_daily
    Fallback:       ext.schumann primary rows (new ingest path)
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

    # Fallback: ext.schumann primary rows (new ingest path)
    if not row:
        try:
            row = await _fetch_latest_ext_primary(conn)
        except Exception:
            row = None

    if not row:
        return {"ok": True, "generated_at": None, "harmonics": {}, "amplitude": {}, "quality": {}}

    ts = row.get("generated_at") or row.get("ts_utc")
    return {
        "ok": True,
        "generated_at": _iso(ts),
        "harmonics": _project_harmonics(row),
        "amplitude": _project_amplitude(row),
        "quality": {
            "primary_source": row.get("primary_source"),
            "usable": row.get("usable"),
            "quality_score": row.get("quality_score"),
        },
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


# New endpoint: /earth/schumann/series_primary
@router.get("/earth/schumann/series_primary")
async def schumann_series_primary(
    limit: int = Query(192, ge=10, le=20000),
    include_bins: bool = Query(False),
    conn=Depends(get_db),
):
    """Primary Schumann series from ext.schumann (Cumiana preferred via is_primary).

    Default `limit=192` approximates 48h at 15-min cadence.
    Use `include_bins=true` to include spectrogram_bins per point (larger payload).
    """
    try:
        rows = await _fetch_series_ext_primary(conn, limit)
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "error": f"schumann_series_primary failed: {exc}"}

    out = []
    for r in rows:
        item = {
            "ts": _iso(r.get("generated_at") or r.get("ts_utc")),
            "harmonics": _project_harmonics(r),
            "amplitude": _project_amplitude(r),
            "quality": {
                "primary_source": r.get("primary_source"),
                "usable": r.get("usable"),
                "quality_score": r.get("quality_score"),
            },
            "axis": {
                "freq_start_hz": r.get("freq_start_hz"),
                "freq_step_hz": r.get("freq_step_hz"),
            },
        }
        if include_bins:
            item["spectrogram_bins"] = r.get("spectrogram_bins")
        out.append(item)

    return {"ok": True, "count": len(out), "rows": out}


# New endpoint: /earth/schumann/heatmap_48h
@router.get("/earth/schumann/heatmap_48h")
async def schumann_heatmap_48h(conn=Depends(get_db)):
    """Return a lightweight 48h heatmap grid from primary rows.

    Output is time-ascending for direct heatmap rendering.
    """
    try:
        rows = await _fetch_series_ext_primary(conn, 192)
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "error": f"schumann_heatmap_48h failed: {exc}"}

    # Order ascending
    rows = list(reversed(rows))

    # Pick axis metadata from the first row that has it
    freq_start_hz = None
    freq_step_hz = None
    for r in rows:
        if r.get("freq_start_hz") is not None and r.get("freq_step_hz") is not None:
            freq_start_hz = r.get("freq_start_hz")
            freq_step_hz = r.get("freq_step_hz")
            break

    points = []
    for r in rows:
        bins = r.get("spectrogram_bins")
        if bins is None:
            continue
        points.append({"ts": _iso(r.get("generated_at") or r.get("ts_utc")), "bins": bins})

    return {
        "ok": True,
        "axis": {"freq_start_hz": freq_start_hz, "freq_step_hz": freq_step_hz, "bins": 160},
        "count": len(points),
        "points": points,
    }