#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, stdev
from typing import Any, Dict, List, Mapping, Optional, Sequence
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from dotenv import load_dotenv
from psycopg.rows import dict_row

import psycopg

from bots.social_alerts.shadow_drafts import build_shadow_payload, write_shadow_payload, write_shadow_review_markdown


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return float(value)
    except Exception:
        return None


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        ts = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return ts.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    return text or None


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, tuple):
        return [_jsonable(v) for v in value]
    if isinstance(value, datetime):
        return _iso(value)
    if isinstance(value, date):
        return value.isoformat()
    if hasattr(value, "as_tuple"):
        converted = _safe_float(value)
        return converted if converted is not None and math.isfinite(converted) else str(value)
    return value


def _first_float(*values: Any) -> Optional[float]:
    for value in values:
        parsed = _safe_float(value)
        if parsed is not None:
            return parsed
    return None


def _percentile_rank(values: Sequence[float], target: float) -> Optional[float]:
    if not values:
        return None
    count = sum(1 for value in values if value <= target)
    return count / len(values)


def _build_schumann_snapshot(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    normalized: List[Dict[str, Any]] = []
    for row in rows:
        value = _safe_float(row.get("value_hz"))
        if value is None:
            continue
        normalized.append(
            {
                "day": row.get("day"),
                "value_hz": value,
                "f1_hz": _safe_float(row.get("f1_hz")),
                "station_id": row.get("station_id"),
            }
        )
    normalized.sort(key=lambda item: str(item.get("day") or ""))
    if not normalized:
        return {}

    deltas: List[Dict[str, Any]] = []
    previous: Optional[Dict[str, Any]] = None
    for row in normalized:
        if previous is not None:
            deltas.append(
                {
                    "day": row.get("day"),
                    "delta_f0": abs(float(row["value_hz"]) - float(previous["value_hz"])),
                    "value_hz": row.get("value_hz"),
                    "f1_hz": row.get("f1_hz"),
                    "station_id": row.get("station_id"),
                }
            )
        previous = row

    latest = normalized[-1]
    if not deltas:
        return {
            "value_hz": latest.get("value_hz"),
            "combined": {"f1_hz": latest.get("f1_hz") or latest.get("value_hz")},
            "station_id": latest.get("station_id"),
            "day": _iso(latest.get("day")),
        }

    latest_delta = deltas[-1]
    values = [float(item["delta_f0"]) for item in deltas if item.get("delta_f0") is not None]
    zscore = None
    if len(values) >= 14:
        std = stdev(values)
        if std > 0:
            zscore = (float(latest_delta["delta_f0"]) - mean(values)) / std

    return {
        "zscore_30d": zscore,
        "pct_30d": _percentile_rank(values, float(latest_delta["delta_f0"])),
        "stddev_24h": latest_delta.get("delta_f0"),
        "value_hz": latest_delta.get("value_hz"),
        "combined": {"f1_hz": latest_delta.get("f1_hz") or latest_delta.get("value_hz")},
        "station_id": latest_delta.get("station_id"),
        "day": _iso(latest_delta.get("day")),
        "sample_count": len(values),
    }


def _active_states_from_schumann(schumann: Mapping[str, Any]) -> List[Dict[str, Any]]:
    zscore = _safe_float(schumann.get("zscore_30d"))
    percentile = _safe_float(schumann.get("pct_30d"))
    if not ((zscore is not None and zscore >= 2.0) or (percentile is not None and percentile >= 0.9)):
        return []
    return [
        {
            "signal_key": "schumann.variability_24h",
            "state": "elevated",
            "value": schumann.get("stddev_24h"),
            "evidence": {
                "source": "marts.schumann_daily_v2_or_daily",
                "metric": "abs_delta_f0_day_to_day",
                "stddev_24h": schumann.get("stddev_24h"),
                "zscore_30d": zscore,
                "pct_30d": percentile,
                "n_points": schumann.get("sample_count"),
                "ts": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            },
        }
    ]


def build_existing_signal_snapshot(
    *,
    space_daily: Optional[Mapping[str, Any]] = None,
    latest_space: Optional[Mapping[str, Any]] = None,
    schumann_rows: Sequence[Mapping[str, Any]] = (),
    quakes: Sequence[Mapping[str, Any]] = (),
    hazards: Sequence[Mapping[str, Any]] = (),
    generated_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Normalize existing Gaia Eyes rows into the Social Alerts shadow input shape."""
    daily = dict(space_daily or {})
    latest = dict(latest_space or {})
    schumann = _build_schumann_snapshot(schumann_rows)
    active_states = _active_states_from_schumann(schumann)

    now_ts = _iso(latest.get("ts_utc") or daily.get("updated_at"))
    snapshot = {
        "generated_at": generated_at
        or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source_mode": "db_snapshot",
        "space_weather": {
            "timestamp_utc": now_ts,
            "now": {
                "kp": _first_float(latest.get("kp_index"), daily.get("kp_now"), daily.get("kp_max")),
                "bz_nt": _first_float(latest.get("bz_nt"), daily.get("bz_now"), daily.get("bz_min")),
                "solar_wind_kms": _first_float(
                    latest.get("sw_speed_kms"),
                    daily.get("sw_speed_now_kms"),
                    daily.get("sw_speed_avg"),
                ),
            },
            "last_24h": {
                "kp_max": _first_float(daily.get("kp_max")),
            },
            "xray_max_class": str(daily.get("xray_max_class") or "").strip() or None,
            "flares_count": daily.get("flares_count"),
            "cmes_count": daily.get("cmes_count"),
            "cmes_max_speed_kms": daily.get("cmes_max_speed_kms"),
        },
        "space_daily": _jsonable(daily),
        "schumann": _jsonable(schumann),
        "active_states": _jsonable(active_states),
        "quakes": {"events": [_jsonable(item) for item in quakes]},
        "hazards": {"items": [_jsonable(item) for item in hazards]},
        "source_refs": [
            "marts.space_weather_daily",
            "ext.space_weather",
            "marts.schumann_daily_v2_or_daily",
            "ext.earthquakes",
            "ext.global_hazards",
        ],
    }
    return _jsonable(snapshot)


def _fetch_one(conn: psycopg.Connection, query: str, params: Sequence[Any] = ()) -> Dict[str, Any]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(query, params)
        row = cur.fetchone()
        return dict(row or {})


def _fetch_all(conn: psycopg.Connection, query: str, params: Sequence[Any] = ()) -> List[Dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(query, params)
        return [dict(row) for row in cur.fetchall()]


def _fetch_space_daily(conn: psycopg.Connection) -> Dict[str, Any]:
    return _fetch_one(
        conn,
        """
        select day,
               kp_now,
               kp_max,
               bz_now,
               bz_min,
               sw_speed_now_kms,
               sw_speed_avg,
               xray_max_class,
               flares_count,
               cmes_count,
               cmes_max_speed_kms,
               updated_at
          from marts.space_weather_daily
         where day <= (now() at time zone 'utc')::date
         order by day desc
         limit 1
        """,
    )


def _fetch_latest_space(conn: psycopg.Connection) -> Dict[str, Any]:
    return _fetch_one(
        conn,
        """
        select ts_utc, kp_index, bz_nt, sw_speed_kms
          from ext.space_weather
         where kp_index is not null
            or bz_nt is not null
            or sw_speed_kms is not null
         order by ts_utc desc
         limit 1
        """,
    )


def _fetch_schumann_rows(conn: psycopg.Connection, lookback_days: int = 45) -> List[Dict[str, Any]]:
    try:
        rows = _fetch_all(
            conn,
            """
            select day, f0::float as value_hz, f1::float as f1_hz, 'daily_v2' as station_id
              from marts.schumann_daily_v2
             where day >= (now() at time zone 'utc')::date - (%s || ' days')::interval
               and f0 is not null
             order by day asc
            """,
            (lookback_days,),
        )
        if rows:
            return rows
    except Exception:
        pass

    try:
        return _fetch_all(
            conn,
            """
            select day,
                   f0_avg_hz::float as value_hz,
                   f1_avg_hz::float as f1_hz,
                   station_id
              from marts.schumann_daily
             where station_id = 'cumiana'
               and day >= (now() at time zone 'utc')::date - (%s || ' days')::interval
               and f0_avg_hz is not null
             order by day asc
            """,
            (lookback_days,),
        )
    except Exception:
        return []


def _fetch_quakes(conn: psycopg.Connection, hours: int = 48, min_mag: float = 5.0, limit: int = 50) -> List[Dict[str, Any]]:
    try:
        return _fetch_all(
            conn,
            """
            select origin_time as time_utc,
                   mag,
                   depth_km,
                   lat,
                   lon,
                   place,
                   src as source,
                   coalesce(meta->>'url', '') as url,
                   event_id as id
              from ext.earthquakes
             where origin_time >= now() - (%s || ' hours')::interval
               and mag is not null
               and mag >= %s
             order by origin_time desc
             limit %s
            """,
            (hours, min_mag, limit),
        )
    except Exception:
        return []


def _fetch_hazards(conn: psycopg.Connection, hours: int = 48, limit: int = 30) -> List[Dict[str, Any]]:
    try:
        return _fetch_all(
            conn,
            """
            select source,
                   kind,
                   title,
                   location,
                   severity,
                   started_at,
                   ended_at,
                   payload
              from ext.global_hazards
             where coalesce(started_at, ingested_at) >= now() - (%s || ' hours')::interval
             order by coalesce(started_at, ingested_at) desc
             limit %s
            """,
            (hours, limit),
        )
    except Exception:
        return []


def fetch_db_snapshot(db_url: str, *, quake_hours: int = 48, hazard_hours: int = 48) -> Dict[str, Any]:
    with psycopg.connect(db_url, row_factory=dict_row) as conn:
        return build_existing_signal_snapshot(
            space_daily=_fetch_space_daily(conn),
            latest_space=_fetch_latest_space(conn),
            schumann_rows=_fetch_schumann_rows(conn),
            quakes=_fetch_quakes(conn, hours=quake_hours),
            hazards=_fetch_hazards(conn, hours=hazard_hours),
        )


def write_snapshot(snapshot: Mapping[str, Any], output_path: Path | str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _default_snapshot_path() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Path("tmp") / "social_alerts_shadow" / f"{stamp}-snapshot.json"


def _db_url() -> str:
    load_dotenv()
    raw = (
        os.environ.get("SUPABASE_DB_URL", "").strip()
        or os.environ.get("DIRECT_URL", "").strip()
        or os.environ.get("DATABASE_URL", "").strip()
    )
    return _clean_db_url(raw)


def _clean_db_url(db_url: str) -> str:
    if not db_url:
        return ""
    parsed = urlparse(db_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.pop("pgbouncer", None)
    query.pop("prepare_threshold", None)
    query.setdefault("sslmode", "require")
    return urlunparse(parsed._replace(query=urlencode(query)))


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a Social Alerts shadow input snapshot from existing Gaia Eyes DB sources.")
    parser.add_argument("--output", default="", help="Snapshot JSON output path.")
    parser.add_argument("--shadow-output", default="", help="Optional shadow draft JSON output path.")
    parser.add_argument(
        "--review-output",
        nargs="?",
        const="auto",
        default="",
        help="Optional Markdown review path. Use without a value to write beside the shadow JSON.",
    )
    parser.add_argument("--max-drafts", type=int, default=6, help="Maximum shadow drafts to include.")
    parser.add_argument("--quake-hours", type=int, default=48, help="Trailing earthquake lookback window.")
    parser.add_argument("--hazard-hours", type=int, default=48, help="Trailing hazard lookback window.")
    args = parser.parse_args()

    db_url = _db_url()
    if not db_url:
        raise SystemExit("Missing SUPABASE_DB_URL, DIRECT_URL, or DATABASE_URL for Social Alerts snapshot generation.")

    snapshot = fetch_db_snapshot(db_url, quake_hours=args.quake_hours, hazard_hours=args.hazard_hours)
    snapshot_path = write_snapshot(snapshot, args.output or _default_snapshot_path())
    print(f"[social_alerts.snapshot] wrote snapshot -> {snapshot_path}")

    if args.shadow_output or args.review_output:
        shadow_payload = build_shadow_payload(snapshot, max_drafts=args.max_drafts)
        shadow_path = write_shadow_payload(shadow_payload, args.shadow_output or snapshot_path.with_name(f"{snapshot_path.stem}-shadow.json"))
        print(f"[social_alerts.snapshot] wrote {shadow_payload['draft_count']} draft(s) -> {shadow_path}")
        if args.review_output:
            review_path = shadow_path.with_suffix(".md") if args.review_output == "auto" else Path(args.review_output)
            write_shadow_review_markdown(shadow_payload, review_path)
            print(f"[social_alerts.snapshot] wrote review markdown -> {review_path}")


if __name__ == "__main__":
    main()
