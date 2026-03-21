from __future__ import annotations

import asyncio
import json
import logging
import math
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from itertools import combinations
from typing import Any, Iterable, Sequence

import asyncpg
import httpx


LOG_LEVEL = os.getenv("GAIA_LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger("gaiaeyes.geomag_ulf")

USGS_GEOMAG_URL = os.getenv("USGS_GEOMAG_URL", "https://geomag.usgs.gov/ws/data/")
HTTP_TIMEOUT_SECS = float(os.getenv("HTTP_TIMEOUT_SECS", "20"))
HTTP_RETRY_TRIES = int(os.getenv("HTTP_RETRY_TRIES", "3"))
HTTP_RETRY_BASE_SLEEP = float(os.getenv("HTTP_RETRY_BASE_SLEEP", "1.5"))
HTTP_USER_AGENT = os.getenv(
    "HTTP_USER_AGENT",
    "gaiaeyes.com contact: gaiaeyes7.83@gmail.com",
)

ULF_STATIONS = [item.strip().upper() for item in os.getenv("ULF_STATIONS", "BOU,CMO").split(",") if item.strip()]
ULF_FETCH_MINUTES = max(60, int(os.getenv("ULF_FETCH_MINUTES", "180")))
ULF_WINDOW_SECONDS = max(60, int(os.getenv("ULF_WINDOW_SECONDS", "300")))
ULF_CONTEXT_MODE = os.getenv("ULF_CONTEXT_MODE", "context").strip().lower() or "context"
ULF_ENABLE_LOCALTIME_PERCENTILE = os.getenv("ULF_ENABLE_LOCALTIME_PERCENTILE", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
ULF_MIN_HISTORY_ROWS = max(24, int(os.getenv("ULF_MIN_HISTORY_ROWS", "72")))
SOURCE = "usgs"

WINDOW_MINUTES = max(1, ULF_WINDOW_SECONDS // 60)
_EXPECTED_STATION_COUNT = max(1, len(ULF_STATIONS))


@dataclass(slots=True)
class StationWindow:
    station_id: str
    ts_utc: datetime
    component_used: str
    component_substituted: bool
    dbdt_rms: float | None
    ulf_rms_broad: float | None
    ulf_band_proxy: float | None
    ulf_index_station: float | None
    ulf_index_localtime: float | None
    persistence_30m: float | None
    persistence_90m: float | None
    quality_flags: list[str]
    dbdt_trace: tuple[float, ...] = field(default_factory=tuple, repr=False)


@dataclass(slots=True)
class ContextWindow:
    ts_utc: datetime
    stations_used: list[str]
    regional_intensity: float | None
    regional_coherence: float | None
    regional_persistence: float | None
    context_class: str | None
    confidence_score: float | None
    quality_flags: list[str]


def _resolve_dsn() -> str:
    dsn = os.getenv("SUPABASE_DB_URL") or os.getenv("DIRECT_URL") or os.getenv("DATABASE_URL")
    if not dsn:
        raise RuntimeError("Missing SUPABASE_DB_URL, DIRECT_URL, or DATABASE_URL for database access")
    return dsn


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _parse_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        result = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(result) or math.isinf(result):
        return None
    if abs(result) >= 90000:
        return None
    return result


def _floor_window(ts_utc: datetime) -> datetime:
    minute = ts_utc.minute - (ts_utc.minute % WINDOW_MINUTES)
    return ts_utc.replace(minute=minute, second=0, microsecond=0)


def _mean(values: Iterable[float | None]) -> float | None:
    valid = [float(value) for value in values if value is not None]
    if not valid:
        return None
    return sum(valid) / len(valid)


def _rms(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return math.sqrt(sum(value * value for value in values) / len(values))


def _build_dbdt_trace_from_values(values: Sequence[float]) -> list[float]:
    trace: list[float] = []
    for left, right in zip(values, values[1:]):
        trace.append((right - left) / 60.0)
    return trace


def _build_dbdt_trace(points: Sequence[tuple[datetime, float]]) -> list[float]:
    trace: list[float] = []
    for (left_ts, left_value), (right_ts, right_value) in zip(points, points[1:]):
        delta_seconds = (right_ts - left_ts).total_seconds()
        if delta_seconds <= 0:
            continue
        trace.append((right_value - left_value) / delta_seconds)
    return trace


def _sorted_flags(flags: Iterable[str]) -> list[str]:
    return sorted({flag for flag in flags if flag})


def _pairwise_correlation(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) < 3 or len(right) < 3:
        return None
    count = min(len(left), len(right))
    left_values = list(left[-count:])
    right_values = list(right[-count:])
    left_mean = sum(left_values) / count
    right_mean = sum(right_values) / count
    left_dev = [value - left_mean for value in left_values]
    right_dev = [value - right_mean for value in right_values]
    numerator = sum(a * b for a, b in zip(left_dev, right_dev))
    left_energy = math.sqrt(sum(value * value for value in left_dev))
    right_energy = math.sqrt(sum(value * value for value in right_dev))
    if left_energy == 0 or right_energy == 0:
        return None
    corr = numerator / (left_energy * right_energy)
    return max(-1.0, min(1.0, corr))


async def _fetch_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict[str, Any],
) -> Any:
    last_exc: Exception | None = None
    for attempt in range(1, HTTP_RETRY_TRIES + 1):
        try:
            response = await client.get(url, params=params)
            if response.status_code in {429, 500, 502, 503, 504}:
                response.raise_for_status()
            response.raise_for_status()
            return response.json()
        except (httpx.TimeoutException, httpx.HTTPStatusError, httpx.RequestError, json.JSONDecodeError) as exc:
            last_exc = exc
            if attempt >= HTTP_RETRY_TRIES:
                break
            sleep_seconds = HTTP_RETRY_BASE_SLEEP * attempt
            logger.warning(
                "ulf fetch retry station=%s attempt=%s/%s error=%s",
                params.get("id"),
                attempt,
                HTTP_RETRY_TRIES,
                exc,
            )
            await asyncio.sleep(sleep_seconds)
    assert last_exc is not None
    raise last_exc


async def fetch_station_series(
    station_id: str,
    start_utc: datetime,
    end_utc: datetime,
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    params = {
        "id": station_id,
        "format": "json",
        "elements": "H,X",
        "sampling_period": 60,
        "type": "variation",
        "starttime": start_utc.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "endtime": end_utc.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }

    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(
            timeout=httpx.Timeout(HTTP_TIMEOUT_SECS),
            headers={"User-Agent": HTTP_USER_AGENT},
        )

    try:
        payload = await _fetch_json(client, USGS_GEOMAG_URL, params=params)
    finally:
        if owns_client:
            await client.aclose()

    times = payload.get("times") or []
    values = payload.get("values") or []
    by_component = {
        str(item.get("id") or item.get("metadata", {}).get("element") or "").upper(): item.get("values") or []
        for item in values
        if isinstance(item, dict)
    }
    rows: list[dict[str, Any]] = []
    for index, raw_ts in enumerate(times):
        ts_utc = _parse_dt(raw_ts)
        if ts_utc is None:
            continue
        rows.append(
            {
                "ts_utc": ts_utc,
                "H": _parse_float(by_component.get("H", [None] * len(times))[index] if index < len(by_component.get("H", [])) else None),
                "X": _parse_float(by_component.get("X", [None] * len(times))[index] if index < len(by_component.get("X", [])) else None),
            }
        )
    rows.sort(key=lambda item: item["ts_utc"])
    return rows


def choose_component(rows: list[dict[str, Any]]) -> tuple[str | None, bool]:
    if not rows:
        return None, False
    total_rows = len(rows)
    valid_h = sum(1 for row in rows if row.get("H") is not None)
    valid_x = sum(1 for row in rows if row.get("X") is not None)
    if valid_h and (valid_h >= max(5, int(total_rows * 0.75)) or valid_h >= valid_x):
        return "H", False
    if valid_x:
        return "X", True
    if valid_h:
        return "H", False
    return None, False


def compute_dbdt_rms(values: list[float]) -> float | None:
    return _rms(_build_dbdt_trace_from_values(values))


def compute_band_proxy(values: list[float]) -> float | None:
    """Return a minute-resolution ULF proxy, not true Pc5 spectral power."""
    if len(values) < 3:
        return None
    baseline = sum(values) / len(values)
    centered = [value - baseline for value in values]
    smoothed: list[float] = []
    for index in range(len(centered)):
        start = max(0, index - 1)
        end = min(len(centered), index + 2)
        bucket = centered[start:end]
        smoothed.append(sum(bucket) / len(bucket))
    return _rms(smoothed)


def build_5m_windows(rows: list[dict[str, Any]], component: str) -> list[StationWindow]:
    buckets: dict[datetime, list[tuple[datetime, float]]] = {}
    valid_points = [
        (row["ts_utc"], row[component])
        for row in rows
        if row.get("ts_utc") is not None and row.get(component) is not None
    ]
    for ts_utc, value in valid_points:
        bucket = _floor_window(ts_utc)
        buckets.setdefault(bucket, []).append((ts_utc, float(value)))

    windows: list[StationWindow] = []
    for bucket_start in sorted(buckets):
        points = sorted(buckets[bucket_start], key=lambda item: item[0])
        if len(points) < 4:
            continue

        flags: list[str] = []
        if len(points) < WINDOW_MINUTES:
            flags.append("missing_samples")
        if any((right[0] - left[0]).total_seconds() > 90 for left, right in zip(points, points[1:])):
            flags.append("missing_samples")

        values = [value for _, value in points]
        trace = _build_dbdt_trace(points)
        segment_end = bucket_start + timedelta(minutes=WINDOW_MINUTES)
        segment_start = segment_end - timedelta(minutes=15)
        segment_values = [
            value
            for ts_utc, value in valid_points
            if segment_start <= ts_utc < segment_end
        ]
        proxy_input = segment_values if len(segment_values) >= 5 else values

        windows.append(
            StationWindow(
                station_id="",
                ts_utc=bucket_start,
                component_used=component,
                component_substituted=False,
                dbdt_rms=_rms(trace),
                ulf_rms_broad=_rms(trace),
                ulf_band_proxy=compute_band_proxy(proxy_input),
                ulf_index_station=None,
                ulf_index_localtime=None,
                persistence_30m=None,
                persistence_90m=None,
                quality_flags=_sorted_flags(flags),
                dbdt_trace=tuple(trace),
            )
        )

    return windows


async def load_station_history_rows(
    conn: asyncpg.Connection,
    station_id: str,
    first_ts_utc: datetime,
) -> list[asyncpg.Record]:
    return await conn.fetch(
        """
        select ts_utc, dbdt_rms, ulf_index_station
          from marts.ulf_activity_5m
         where station_id = $1
           and ts_utc >= $2
           and ts_utc < $3
         order by ts_utc asc
        """,
        station_id,
        first_ts_utc - timedelta(days=7),
        first_ts_utc,
    )


def compute_percentile_index(value: float | None, history: list[float]) -> float | None:
    if value is None:
        return None
    valid = sorted(float(item) for item in history if item is not None)
    if len(valid) < ULF_MIN_HISTORY_ROWS:
        return None
    rank = sum(1 for item in valid if item <= value)
    return round((rank / len(valid)) * 100.0, 2)


def compute_persistence(recent_values: list[float], minutes: int) -> float | None:
    del minutes
    result = _mean(recent_values)
    return round(result, 2) if result is not None else None


def compute_coherence(windows: list[StationWindow]) -> float | None:
    if len(windows) < 2:
        return None

    scores: list[float] = []
    for left, right in combinations(windows, 2):
        corr = _pairwise_correlation(left.dbdt_trace, right.dbdt_trace)
        if corr is not None:
            scores.append((corr + 1.0) / 2.0)
            continue
        if left.ulf_index_station is not None and right.ulf_index_station is not None:
            scores.append(max(0.0, 1.0 - min(abs(left.ulf_index_station - right.ulf_index_station) / 100.0, 1.0)))
    if not scores:
        return None
    return round(sum(scores) / len(scores), 3)


def classify_context(intensity: float | None, coherence: float | None) -> str | None:
    if intensity is None:
        return None
    if intensity >= 80 and coherence is not None and coherence >= 0.7:
        return "Strong (coherent)"
    if intensity >= 60 and coherence is not None and coherence >= 0.5:
        return "Elevated (coherent)"
    if intensity >= 40:
        return "Active (diffuse)"
    return "Quiet"


def compute_confidence_score(
    coherence: float | None,
    stations_used: int,
    quality_flags: list[str],
) -> float | None:
    if stations_used <= 0:
        return None

    if coherence is None:
        score = 0.4 if stations_used == 1 else 0.55
    else:
        score = coherence

    score *= min(1.0, stations_used / _EXPECTED_STATION_COUNT)

    penalties = {
        "fallback_component": 0.08,
        "missing_samples": 0.10,
        "low_history": 0.12,
        "single_station": 0.25,
    }
    for flag in quality_flags:
        score -= penalties.get(flag, 0.0)
    return round(max(0.0, min(1.0, score)), 3)


def compute_context_row(ts_utc: datetime, windows: list[StationWindow]) -> ContextWindow:
    flags: list[str] = []
    for window in windows:
        flags.extend(window.quality_flags)
    if len(windows) == 1:
        flags.append("single_station")

    intensity = _mean(window.ulf_index_station for window in windows)
    persistence_inputs = [
        window.persistence_30m if window.persistence_30m is not None else window.persistence_90m
        for window in windows
    ]
    persistence = _mean(persistence_inputs)
    coherence = compute_coherence(windows)
    context_flags = _sorted_flags(flags)

    return ContextWindow(
        ts_utc=ts_utc,
        stations_used=sorted(window.station_id for window in windows),
        regional_intensity=round(intensity, 2) if intensity is not None else None,
        regional_coherence=coherence,
        regional_persistence=round(persistence, 2) if persistence is not None else None,
        context_class=classify_context(intensity, coherence),
        confidence_score=compute_confidence_score(coherence, len(windows), context_flags),
        quality_flags=context_flags,
    )


def _apply_station_history(
    station_id: str,
    component_substituted: bool,
    windows: list[StationWindow],
    history_rows: Sequence[asyncpg.Record],
) -> list[StationWindow]:
    if not windows:
        return []

    history_metrics = [
        {
            "ts_utc": row["ts_utc"],
            "dbdt_rms": row["dbdt_rms"],
            "ulf_index_station": row["ulf_index_station"],
        }
        for row in history_rows
    ]
    enriched: list[StationWindow] = []
    for window in windows:
        flags = list(window.quality_flags)
        if component_substituted:
            flags.append("fallback_component")

        dbdt_history = [
            float(item["dbdt_rms"])
            for item in history_metrics
            if item.get("dbdt_rms") is not None
        ]
        ulf_index_station = compute_percentile_index(window.dbdt_rms, dbdt_history)
        if window.dbdt_rms is not None and ulf_index_station is None:
            flags.append("low_history")

        current_localtime = None
        if ULF_ENABLE_LOCALTIME_PERCENTILE and window.ulf_band_proxy is not None:
            same_hour_history = [
                float(item["dbdt_rms"])
                for item in history_metrics
                if item.get("dbdt_rms") is not None and item["ts_utc"].hour == window.ts_utc.hour
            ]
            current_localtime = compute_percentile_index(window.dbdt_rms, same_hour_history)

        recent_30m = [
            float(item["ulf_index_station"])
            for item in history_metrics
            if item.get("ulf_index_station") is not None
            and item["ts_utc"] >= window.ts_utc - timedelta(minutes=30)
        ]
        recent_90m = [
            float(item["ulf_index_station"])
            for item in history_metrics
            if item.get("ulf_index_station") is not None
            and item["ts_utc"] >= window.ts_utc - timedelta(minutes=90)
        ]
        if ulf_index_station is not None:
            recent_30m.append(ulf_index_station)
            recent_90m.append(ulf_index_station)

        enriched_window = StationWindow(
            station_id=station_id,
            ts_utc=window.ts_utc,
            component_used=window.component_used,
            component_substituted=component_substituted,
            dbdt_rms=round(window.dbdt_rms, 6) if window.dbdt_rms is not None else None,
            ulf_rms_broad=round(window.ulf_rms_broad, 6) if window.ulf_rms_broad is not None else None,
            ulf_band_proxy=round(window.ulf_band_proxy, 6) if window.ulf_band_proxy is not None else None,
            ulf_index_station=ulf_index_station,
            ulf_index_localtime=current_localtime,
            persistence_30m=compute_persistence(recent_30m, 30),
            persistence_90m=compute_persistence(recent_90m, 90),
            quality_flags=_sorted_flags(flags),
            dbdt_trace=window.dbdt_trace,
        )
        enriched.append(enriched_window)
        history_metrics.append(
            {
                "ts_utc": enriched_window.ts_utc,
                "dbdt_rms": enriched_window.dbdt_rms,
                "ulf_index_station": enriched_window.ulf_index_station,
            }
        )

    return enriched


def _build_context_rows(station_rows: Sequence[StationWindow]) -> list[ContextWindow]:
    windows_by_ts: dict[datetime, list[StationWindow]] = {}
    for row in station_rows:
        windows_by_ts.setdefault(row.ts_utc, []).append(row)
    return [compute_context_row(ts_utc, windows) for ts_utc, windows in sorted(windows_by_ts.items())]


async def upsert_station_rows(conn: asyncpg.Connection, rows: list[StationWindow]) -> int:
    if not rows:
        return 0
    sql = """
        insert into marts.ulf_activity_5m (
            station_id,
            ts_utc,
            window_seconds,
            component_used,
            component_substituted,
            dbdt_rms,
            ulf_rms_broad,
            ulf_band_proxy,
            ulf_index_station,
            ulf_index_localtime,
            persistence_30m,
            persistence_90m,
            quality_flags,
            source
        ) values (
            $1, $2, $3, $4, $5,
            $6, $7, $8, $9, $10,
            $11, $12, $13::jsonb, $14
        )
        on conflict (station_id, ts_utc) do update
        set
            window_seconds = excluded.window_seconds,
            component_used = excluded.component_used,
            component_substituted = excluded.component_substituted,
            dbdt_rms = excluded.dbdt_rms,
            ulf_rms_broad = excluded.ulf_rms_broad,
            ulf_band_proxy = excluded.ulf_band_proxy,
            ulf_index_station = excluded.ulf_index_station,
            ulf_index_localtime = excluded.ulf_index_localtime,
            persistence_30m = excluded.persistence_30m,
            persistence_90m = excluded.persistence_90m,
            quality_flags = excluded.quality_flags,
            source = excluded.source
    """
    values = [
        (
            row.station_id,
            row.ts_utc,
            ULF_WINDOW_SECONDS,
            row.component_used,
            row.component_substituted,
            row.dbdt_rms,
            row.ulf_rms_broad,
            row.ulf_band_proxy,
            row.ulf_index_station,
            row.ulf_index_localtime,
            row.persistence_30m,
            row.persistence_90m,
            json.dumps(row.quality_flags),
            SOURCE,
        )
        for row in rows
    ]
    async with conn.transaction():
        await conn.executemany(sql, values)
    return len(rows)


async def upsert_context_rows(conn: asyncpg.Connection, rows: list[ContextWindow]) -> int:
    if not rows:
        return 0
    sql = """
        insert into marts.ulf_context_5m (
            ts_utc,
            stations_used,
            regional_intensity,
            regional_coherence,
            regional_persistence,
            context_class,
            confidence_score,
            quality_flags
        ) values ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)
        on conflict (ts_utc) do update
        set
            stations_used = excluded.stations_used,
            regional_intensity = excluded.regional_intensity,
            regional_coherence = excluded.regional_coherence,
            regional_persistence = excluded.regional_persistence,
            context_class = excluded.context_class,
            confidence_score = excluded.confidence_score,
            quality_flags = excluded.quality_flags
    """
    values = [
        (
            row.ts_utc,
            row.stations_used,
            row.regional_intensity,
            row.regional_coherence,
            row.regional_persistence,
            row.context_class,
            row.confidence_score,
            json.dumps(row.quality_flags),
        )
        for row in rows
    ]
    async with conn.transaction():
        await conn.executemany(sql, values)
    return len(rows)


async def _process_station(
    conn: asyncpg.Connection,
    client: httpx.AsyncClient,
    station_id: str,
    start_utc: datetime,
    end_utc: datetime,
) -> list[StationWindow]:
    rows = await fetch_station_series(station_id, start_utc, end_utc, client=client)
    component_used, component_substituted = choose_component(rows)
    if component_used is None:
        logger.warning("ulf station skipped station=%s reason=no_component", station_id)
        return []
    if component_substituted:
        logger.warning("ulf station fallback component station=%s component=%s", station_id, component_used)

    base_windows = build_5m_windows(rows, component_used)
    if not base_windows:
        logger.warning("ulf station skipped station=%s reason=no_windows", station_id)
        return []

    first_ts_utc = min(window.ts_utc for window in base_windows)
    history_rows = await load_station_history_rows(conn, station_id, first_ts_utc)
    windows = _apply_station_history(station_id, component_substituted, base_windows, history_rows)

    low_history_count = sum(1 for window in windows if "low_history" in window.quality_flags)
    missing_count = sum(1 for window in windows if "missing_samples" in window.quality_flags)
    logger.info(
        "ulf station processed station=%s source_rows=%s windows=%s low_history=%s missing_samples=%s component=%s",
        station_id,
        len(rows),
        len(windows),
        low_history_count,
        missing_count,
        component_used,
    )
    return windows


async def _run() -> None:
    dsn = _resolve_dsn()
    end_utc = datetime.now(UTC).replace(second=0, microsecond=0)
    start_utc = end_utc - timedelta(minutes=ULF_FETCH_MINUTES)

    timeout = httpx.Timeout(HTTP_TIMEOUT_SECS)
    headers = {"User-Agent": HTTP_USER_AGENT}

    logger.info(
        "ulf ingest start stations=%s fetch_minutes=%s window_seconds=%s mode=%s",
        ",".join(ULF_STATIONS),
        ULF_FETCH_MINUTES,
        ULF_WINDOW_SECONDS,
        ULF_CONTEXT_MODE,
    )

    station_rows: list[StationWindow] = []
    async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
        conn = await asyncpg.connect(dsn)
        try:
            for station_id in ULF_STATIONS:
                try:
                    station_rows.extend(await _process_station(conn, client, station_id, start_utc, end_utc))
                except Exception as exc:
                    logger.exception("ulf station failed station=%s error=%s", station_id, exc)

            context_rows = _build_context_rows(station_rows)
            station_upserts = await upsert_station_rows(conn, station_rows)
            context_upserts = await upsert_context_rows(conn, context_rows)
        finally:
            await conn.close()

    logger.info(
        "ulf ingest complete station_rows=%s station_upserts=%s context_rows=%s context_upserts=%s",
        len(station_rows),
        station_upserts,
        len(context_rows),
        context_upserts,
    )


def run() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    run()
