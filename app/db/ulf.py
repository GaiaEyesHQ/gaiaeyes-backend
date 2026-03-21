from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from psycopg.rows import dict_row

UTC = timezone.utc


def _normalize_ts(ts: Optional[datetime]) -> Optional[datetime]:
    if ts is None:
        return None
    if ts.tzinfo is None:
        return ts.replace(tzinfo=UTC)
    return ts.astimezone(UTC)


def _serialize_ts(ts: Optional[datetime]) -> Optional[str]:
    value = _normalize_ts(ts)
    return value.isoformat() if value else None


def _to_float(value: Decimal | float | None) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return value


def _serialize_station_row(row: dict | None) -> dict | None:
    if not row:
        return None
    return {
        "station_id": row.get("station_id"),
        "ts_utc": _serialize_ts(row.get("ts_utc")),
        "component_used": row.get("component_used"),
        "component_substituted": bool(row.get("component_substituted", False)),
        "dbdt_rms": _to_float(row.get("dbdt_rms")),
        "ulf_rms_broad": _to_float(row.get("ulf_rms_broad")),
        "ulf_band_proxy": _to_float(row.get("ulf_band_proxy")),
        "ulf_index_station": _to_float(row.get("ulf_index_station")),
        "ulf_index_localtime": _to_float(row.get("ulf_index_localtime")),
        "persistence_30m": _to_float(row.get("persistence_30m")),
        "persistence_90m": _to_float(row.get("persistence_90m")),
        "quality_flags": list(row.get("quality_flags") or []),
    }


def _serialize_context_row(row: dict | None) -> dict | None:
    if not row:
        return None
    return {
        "ts_utc": _serialize_ts(row.get("ts_utc")),
        "stations_used": list(row.get("stations_used") or []),
        "regional_intensity": _to_float(row.get("regional_intensity")),
        "regional_coherence": _to_float(row.get("regional_coherence")),
        "regional_persistence": _to_float(row.get("regional_persistence")),
        "context_class": row.get("context_class"),
        "confidence_score": _to_float(row.get("confidence_score")),
        "quality_flags": list(row.get("quality_flags") or []),
    }


async def get_latest_ulf_context(conn) -> dict | None:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            select
              ts_utc,
              stations_used,
              regional_intensity,
              regional_coherence,
              regional_persistence,
              context_class,
              confidence_score,
              quality_flags
            from marts.ulf_context_5m
            order by ts_utc desc
            limit 1
            """,
            prepare=False,
        )
        row = await cur.fetchone()
    return _serialize_context_row(row)


async def get_latest_ulf_by_station(conn, *, ts_utc: datetime | None = None) -> list[dict]:
    async with conn.cursor(row_factory=dict_row) as cur:
        if ts_utc is not None:
            await cur.execute(
                """
                select
                  station_id,
                  ts_utc,
                  component_used,
                  component_substituted,
                  dbdt_rms,
                  ulf_rms_broad,
                  ulf_band_proxy,
                  ulf_index_station,
                  ulf_index_localtime,
                  persistence_30m,
                  persistence_90m,
                  quality_flags
                from marts.ulf_activity_5m
                where ts_utc = %s
                order by station_id asc
                """,
                (_normalize_ts(ts_utc),),
                prepare=False,
            )
        else:
            await cur.execute(
                """
                select distinct on (station_id)
                  station_id,
                  ts_utc,
                  component_used,
                  component_substituted,
                  dbdt_rms,
                  ulf_rms_broad,
                  ulf_band_proxy,
                  ulf_index_station,
                  ulf_index_localtime,
                  persistence_30m,
                  persistence_90m,
                  quality_flags
                from marts.ulf_activity_5m
                order by station_id asc, ts_utc desc
                """,
                prepare=False,
            )
        rows = await cur.fetchall()
    return [_serialize_station_row(row) for row in rows or [] if row]


async def get_ulf_context_series(conn, hours: int) -> list[dict]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            select
              ts_utc,
              stations_used,
              regional_intensity,
              regional_coherence,
              regional_persistence,
              context_class,
              confidence_score,
              quality_flags
            from marts.ulf_context_5m
            where ts_utc >= now() - (%s * interval '1 hour')
            order by ts_utc asc
            """,
            (hours,),
            prepare=False,
        )
        rows = await cur.fetchall()
    return [_serialize_context_row(row) for row in rows or [] if row]


async def get_ulf_station_series(conn, hours: int, station_id: str | None = None) -> list[dict]:
    params: list[object] = [hours]
    where_station = ""
    if station_id:
        where_station = "and station_id = %s"
        params.append(station_id.upper())

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            f"""
            select
              station_id,
              ts_utc,
              component_used,
              component_substituted,
              dbdt_rms,
              ulf_rms_broad,
              ulf_band_proxy,
              ulf_index_station,
              ulf_index_localtime,
              persistence_30m,
              persistence_90m,
              quality_flags
            from marts.ulf_activity_5m
            where ts_utc >= now() - (%s * interval '1 hour')
              {where_station}
            order by ts_utc asc, station_id asc
            """,
            tuple(params),
            prepare=False,
        )
        rows = await cur.fetchall()
    return [_serialize_station_row(row) for row in rows or [] if row]
