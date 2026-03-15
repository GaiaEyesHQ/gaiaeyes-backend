from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query, Response
from psycopg.rows import dict_row

from app.db import get_db, settings


router = APIRouter(prefix="/v1/earth/schumann/tomsk_params")

TOMSK_FREQUENCY_CHANNELS = {
    "F1": "sos70_F1_hz",
    "F2": "sos70_F2_hz",
    "F3": "sos70_F3_hz",
    "F4": "sos70_F4_hz",
}

TOMSK_AMPLITUDE_CHANNELS = {
    "A1": "sos70_A1",
    "A2": "sos70_A2",
    "A3": "sos70_A3",
    "A4": "sos70_A4",
}

TOMSK_Q_CHANNELS = {
    "Q1": "sos70_Q1",
    "Q2": "sos70_Q2",
    "Q3": "sos70_Q3",
    "Q4": "sos70_Q4",
}

TOMSK_ALL_CHANNELS = {
    **TOMSK_FREQUENCY_CHANNELS,
    **TOMSK_AMPLITUDE_CHANNELS,
    **TOMSK_Q_CHANNELS,
}

TOMSK_F1_CHANNEL = TOMSK_FREQUENCY_CHANNELS["F1"]
TREND_WINDOW_POINTS = 8

_PIVOT_SELECT = ",\n              ".join(
    f'max(s.value_num) filter (where s.channel=\'{channel}\') as "{label}"'
    for label, channel in TOMSK_ALL_CHANNELS.items()
)


def _iso(ts: Any) -> Optional[str]:
    if isinstance(ts, datetime):
        return ts.astimezone(timezone.utc).isoformat()
    if isinstance(ts, date):
        return datetime.combine(ts, datetime.min.time(), tzinfo=timezone.utc).isoformat()
    return None


def _apply_cache_headers(response: Response, payload: object, max_age: int) -> None:
    response.headers["Cache-Control"] = f"public, max-age={max_age}"
    try:
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True, default=str)
        digest = hashlib.sha1(body.encode("utf-8")).hexdigest()
        response.headers["ETag"] = f'W/"{digest}"'
    except Exception:
        return


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_bool(value: Any) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "f", "no", "n", "off"}:
        return False
    return None


def _quality_threshold() -> float:
    return float(getattr(settings, "SCHUMANN_TOMSK_MIN_QUALITY_SCORE", 0.55) or 0.55)


def _row_get(row: Dict[str, Any], key: str) -> Any:
    if key in row:
        return row.get(key)
    lowered = key.lower()
    if lowered in row:
        return row.get(lowered)
    return None


def _derive_quality_from_meta(meta: Any) -> tuple[Optional[bool], Optional[float]]:
    if not isinstance(meta, dict):
        return None, None

    chart_status = meta.get("chart_status")
    if not isinstance(chart_status, dict):
        return None, None

    statuses = [
        str(status).strip().lower()
        for status in (chart_status.get("F"), chart_status.get("A"), chart_status.get("Q"))
        if status is not None
    ]
    if not statuses:
        return None, None

    ok_count = sum(1 for status in statuses if status == "ok")
    quality_score = ok_count / len(statuses)
    usable = ok_count == len(statuses)
    return usable, quality_score


def _tomsk_is_usable(usable: Optional[bool], quality_score: Optional[float]) -> bool:
    return usable is True and quality_score is not None and quality_score >= _quality_threshold()


def _quality_flags(usable: Optional[bool], quality_score: Optional[float]) -> List[str]:
    flags: List[str] = []
    if usable is False:
        flags.append("unusable")
    if quality_score is None:
        flags.append("missing_quality_score")
    elif quality_score < _quality_threshold():
        flags.append("low_quality")
    return flags


def _trend_direction(delta: Optional[float]) -> str:
    if delta is None or abs(delta) < 1e-9:
        return "flat"
    return "up" if delta > 0 else "down"


def _build_value_map(row: Dict[str, Any], labels: Dict[str, str]) -> Dict[str, Optional[float]]:
    return {label: _to_float(_row_get(row, label)) for label in labels}


def _build_point(row: Dict[str, Any]) -> Dict[str, Any]:
    usable = _to_bool(row.get("usable"))
    quality_score = _to_float(row.get("quality_score"))
    if usable is None or quality_score is None:
        derived_usable, derived_quality = _derive_quality_from_meta(row.get("meta"))
        if usable is None:
            usable = derived_usable
        if quality_score is None:
            quality_score = derived_quality

    point: Dict[str, Any] = {
        "ts": _iso(row.get("ts_utc")),
        "usable": usable,
        "quality_score": quality_score,
    }
    for label in TOMSK_ALL_CHANNELS:
        point[label] = _to_float(_row_get(row, label))
    point["quality_flags"] = _quality_flags(point["usable"], point["quality_score"])
    return point


def _build_trend_map(points: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    window = points[-TREND_WINDOW_POINTS:]
    trend: Dict[str, Dict[str, Any]] = {}
    for key in TOMSK_ALL_CHANNELS:
        values = [point.get(key) for point in window if point.get(key) is not None]
        if len(values) < 2:
            continue
        delta = float(values[-1]) - float(values[0])
        trend[key] = {"delta": delta, "dir": _trend_direction(delta)}
    return trend


def _coherence_from_points(points: List[Dict[str, Any]], usable_for_fusion: bool) -> Optional[Dict[str, Any]]:
    if not usable_for_fusion:
        return None

    q1_points = [
        point["Q1"]
        for point in points
        if point.get("Q1") is not None and "low_quality" not in point.get("quality_flags", [])
    ]
    if not q1_points:
        q1_points = [point["Q1"] for point in points if point.get("Q1") is not None]
    if not q1_points:
        return None

    latest_q1 = float(q1_points[-1])
    sorted_q1 = sorted(float(value) for value in q1_points)
    if len(sorted_q1) == 1:
        percentile = 1.0
    else:
        count_le = sum(1 for value in sorted_q1 if value <= latest_q1)
        percentile = (count_le - 1) / (len(sorted_q1) - 1)

    if percentile >= 0.67:
        label = "high"
    elif percentile >= 0.34:
        label = "medium"
    else:
        label = "low"

    return {
        "label": label,
        "percentile": round(percentile, 4),
        "q1_value": latest_q1,
    }


def _structured_latest_payload(
    station_id: str,
    latest_row: Optional[Dict[str, Any]],
    series_rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    if not latest_row:
        return {
            "ok": True,
            "generated_at": None,
            "station_id": station_id,
            "usable": False,
            "usable_for_fusion": False,
            "quality_score": None,
            "frequency_hz": {label: None for label in TOMSK_FREQUENCY_CHANNELS},
            "amplitude": {label: None for label in TOMSK_AMPLITUDE_CHANNELS},
            "q_factor": {label: None for label in TOMSK_Q_CHANNELS},
            "trend_2h": {},
            "coherence": None,
        }

    points = [_build_point(row) for row in series_rows]
    usable = _to_bool(latest_row.get("usable"))
    quality_score = _to_float(latest_row.get("quality_score"))
    if usable is None or quality_score is None:
        derived_usable, derived_quality = _derive_quality_from_meta(latest_row.get("meta"))
        if usable is None:
            usable = derived_usable
        if quality_score is None:
            quality_score = derived_quality
    usable_for_fusion = _tomsk_is_usable(usable, quality_score)

    return {
        "ok": True,
        "generated_at": _iso(latest_row.get("ts_utc")),
        "station_id": station_id,
        "usable": usable,
        "usable_for_fusion": usable_for_fusion,
        "quality_score": quality_score,
        "frequency_hz": _build_value_map(latest_row, TOMSK_FREQUENCY_CHANNELS),
        "amplitude": _build_value_map(latest_row, TOMSK_AMPLITUDE_CHANNELS),
        "q_factor": _build_value_map(latest_row, TOMSK_Q_CHANNELS),
        "trend_2h": _build_trend_map(points),
        "coherence": _coherence_from_points(points, usable_for_fusion),
    }


def build_schumann_tomsk_fusion(
    cumiana_harmonics: Dict[str, Any],
    tomsk_latest: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    cumiana_f0 = _to_float((cumiana_harmonics or {}).get("f0"))
    enabled = bool(getattr(settings, "SCHUMANN_FUSE_TOMSK", True))

    if not enabled or not tomsk_latest:
        return {
            "enabled": enabled,
            "tomsk_usable": False,
            "display_f0_hz": cumiana_f0,
            "display_f0_source": "cumiana",
            "secondary_f0_hz": None,
            "secondary_f0_source": None,
            "coherence": None,
        }

    tomsk_usable = bool(tomsk_latest.get("usable_for_fusion"))
    tomsk_f1 = _to_float((tomsk_latest.get("frequency_hz") or {}).get("F1"))
    coherence = tomsk_latest.get("coherence")

    if tomsk_usable and tomsk_f1 is not None:
        return {
            "enabled": enabled,
            "tomsk_usable": True,
            "display_f0_hz": tomsk_f1,
            "display_f0_source": "tomsk",
            "secondary_f0_hz": cumiana_f0,
            "secondary_f0_source": "cumiana",
            "coherence": coherence,
            "tomsk_quality_score": tomsk_latest.get("quality_score"),
        }

    return {
        "enabled": enabled,
        "tomsk_usable": False,
        "display_f0_hz": cumiana_f0,
        "display_f0_source": "cumiana",
        "secondary_f0_hz": None,
        "secondary_f0_source": None,
        "coherence": None,
        "tomsk_quality_score": tomsk_latest.get("quality_score"),
    }


async def _fetch_tomsk_latest_row(conn, station_id: str) -> Optional[Dict[str, Any]]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            f"""
            with anchor as (
              select ts_utc, meta
              from ext.schumann
              where station_id = %s
                and channel = %s
              order by ts_utc desc
              limit 1
            )
            select
              a.ts_utc,
              a.meta,
              {_PIVOT_SELECT},
              COALESCE(
                (a.meta->>'usable')::boolean,
                (a.meta->'raw'->>'usable')::boolean
              ) as usable,
              COALESCE(
                (a.meta->>'quality_score')::float,
                (a.meta->'raw'->>'quality_score')::float
              ) as quality_score
            from anchor a
            join ext.schumann s
              on s.station_id = %s
             and s.ts_utc = a.ts_utc
            group by a.ts_utc, a.meta
            """,
            (station_id, TOMSK_F1_CHANNEL, station_id),
            prepare=False,
        )
        return await cur.fetchone()


async def _fetch_tomsk_series_rows(conn, station_id: str, hours: int) -> List[Dict[str, Any]]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            f"""
            with anchor as (
              select ts_utc, meta
              from ext.schumann
              where station_id = %s
                and channel = %s
                and ts_utc >= now() - (%s * interval '1 hour')
              order by ts_utc asc
            )
            select
              a.ts_utc,
              a.meta,
              {_PIVOT_SELECT},
              COALESCE(
                (a.meta->>'usable')::boolean,
                (a.meta->'raw'->>'usable')::boolean
              ) as usable,
              COALESCE(
                (a.meta->>'quality_score')::float,
                (a.meta->'raw'->>'quality_score')::float
              ) as quality_score
            from anchor a
            join ext.schumann s
              on s.station_id = %s
             and s.ts_utc = a.ts_utc
            group by a.ts_utc, a.meta
            order by a.ts_utc asc
            """,
            (station_id, TOMSK_F1_CHANNEL, hours, station_id),
            prepare=False,
        )
        return await cur.fetchall()


async def fetch_tomsk_latest_payload(conn, station_id: str = "tomsk") -> Dict[str, Any]:
    latest_row = await _fetch_tomsk_latest_row(conn, station_id=station_id)
    series_rows = await _fetch_tomsk_series_rows(conn, station_id=station_id, hours=48)
    return _structured_latest_payload(station_id=station_id, latest_row=latest_row, series_rows=series_rows)


@router.get("/latest")
async def schumann_tomsk_params_latest(
    response: Response,
    station_id: str = Query("tomsk"),
    conn=Depends(get_db),
):
    payload = await fetch_tomsk_latest_payload(conn, station_id=station_id)
    _apply_cache_headers(response, payload, 60)
    return payload


@router.get("/series")
async def schumann_tomsk_params_series(
    response: Response,
    hours: int = Query(48, ge=1, le=168),
    station_id: str = Query("tomsk"),
    conn=Depends(get_db),
):
    rows = await _fetch_tomsk_series_rows(conn, station_id=station_id, hours=hours)
    points = [_build_point(row) for row in rows]
    payload = {
        "ok": True,
        "station_id": station_id,
        "count": len(points),
        "points": points,
    }
    _apply_cache_headers(response, payload, 300)
    return payload
