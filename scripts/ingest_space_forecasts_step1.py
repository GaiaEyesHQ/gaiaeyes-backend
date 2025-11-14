#!/usr/bin/env python3
"""Gaia Eyes Step 1: ingest predictive space-weather feeds.

This script orchestrates the Step 1 ingestion backlog described in the
30-day roadmap.  It collects a collection of upstream space-weather feeds
and persists them into the new ``ext`` and ``marts`` Supabase schemas.

Datasets handled here:

* NASA DONKI WSA–Enlil simulations → ``ext.enlil_forecast``
  with derived arrival rollups in ``marts.cme_arrivals``.
* GOES proton flux and S-scale classification → ``ext.sep_flux``.
* GOES >2 MeV electron flux / radiation belt outlooks →
  ``ext.radiation_belts`` + ``marts.radiation_belts_daily``.
* OVATION auroral power and Wing Kp forecasts →
  ``ext.aurora_power`` + ``marts.aurora_outlook``.
* Coronal hole high-speed stream forecasts → ``ext.ch_forecast``.
* DONKI CME Scoreboard consensus → ``ext.cme_scoreboard``.
* D-RAP absorption indices → ``ext.drap_absorption`` +
  ``marts.drap_absorption_daily``.
* SWPC solar-cycle predictions → ``ext.solar_cycle_forecast`` +
  ``marts.solar_cycle_progress``.
* AE/AL/PC magnetometer chain → ``ext.magnetometer_chain`` +
  ``marts.magnetometer_regional``.

The implementation follows the existing ingestion pattern used by other
scripts in ``scripts/``: fetch data via ``httpx``, normalise records, and
upsert them using an asyncpg connection that points at Supabase.  The
script can be executed end-to-end or narrowed to specific feeds via the
``--only`` CLI flag.  A ``--dry-run`` mode avoids any database writes so
that transformations can be validated locally without credentials.

Usage examples::

    poetry run python scripts/ingest_space_forecasts_step1.py --days 5
    poetry run python scripts/ingest_space_forecasts_step1.py --only enlil
    python scripts/ingest_space_forecasts_step1.py --dry-run --only aurora

Environment variables::

    SUPABASE_DB_URL   – required unless ``--dry-run`` is supplied.
    NASA_API          – key for DONKI (defaults to ``DEMO_KEY``).

The code intentionally keeps third-party dependencies minimal so that it
fits the existing ingestion runtime used in production workers.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Sequence

import asyncpg
import httpx

logger = logging.getLogger("gaiaeyes.ingest.step1")


def _parse_dt(value: str | None) -> datetime | None:
    """Parse ISO8601-ish timestamps used by NOAA/NASA feeds."""

    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        # Normalise trailing ``Z`` to ``+00:00`` for fromisoformat.
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        # Some feeds return fractional seconds but others do not; letting
        # ``fromisoformat`` handle both makes the function robust.
        return datetime.fromisoformat(value).astimezone(UTC)
    except ValueError:
        # Try a couple of common fallbacks (space separator, missing offset).
        try:
            return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
        except ValueError:
            try:
                return datetime.strptime(value, "%Y-%m-%dT%H:%M").replace(tzinfo=UTC)
            except ValueError:
                logger.debug("could not parse datetime value %s", value)
                return None


def _parse_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def _s_scale_from_flux(flux: float | None) -> tuple[str | None, int | None]:
    """Return NOAA S-scale class and integer index for a flux measurement."""

    if flux is None:
        return None, None
    thresholds = [
        (5, 100_000),
        (4, 10_000),
        (3, 1_000),
        (2, 100),
        (1, 10),
    ]
    for idx, limit in thresholds:
        if flux >= limit:
            return f"S{idx}", idx
    return "S0", 0


def _radiation_risk(flux: float | None) -> str:
    if flux is None:
        return "unknown"
    if flux >= 1e7:
        return "extreme"
    if flux >= 1e6:
        return "severe"
    if flux >= 1e5:
        return "high"
    if flux >= 1e4:
        return "elevated"
    if flux >= 1e3:
        return "moderate"
    return "quiet"


def _aurora_headline(power_gw: float | None, kp: float | None) -> str:
    if power_gw is None and kp is None:
        return "Auroral outlook unavailable"
    parts: list[str] = []
    if power_gw is not None:
        if power_gw >= 80:
            parts.append("Major aurora power")
        elif power_gw >= 60:
            parts.append("Active aurora")
        elif power_gw >= 40:
            parts.append("Elevated aurora")
        else:
            parts.append("Quiet aurora")
    if kp is not None:
        parts.append(f"Wing Kp {kp:.1f}")
    return " – ".join(parts)


def _region_from_station(station: str | None) -> str:
    if not station:
        return "global"
    station = station.lower()
    if station in {"ale", "ccf", "sit", "cka", "cmo"}:
        return "auroral"
    if station in {"aae", "ams", "hon", "sjg"}:
        return "equatorial"
    if station in {"lyr", "nur", "sor", "brw"}:
        return "polar"
    return "global"


@dataclass(slots=True)
class SupabaseWriter:
    dsn: str | None
    dry_run: bool = False
    _conn: asyncpg.Connection | None = None

    async def __aenter__(self) -> "SupabaseWriter":
        if not self.dsn or self.dry_run:
            return self
        self._conn = await asyncpg.connect(self.dsn)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        if self._conn is not None:
            await self._conn.close()
        self._conn = None

    async def upsert_many(
        self,
        schema: str,
        table: str,
        rows: Sequence[dict[str, Any]],
        conflict_cols: Sequence[str] | None = None,
        *,
        constraint: str | None = None,
        skip_update_cols: Sequence[str] | None = None,
    ) -> int:
        if not rows:
            return 0
        if self.dry_run or not self._conn:
            logger.info("[dry-run] would upsert %s rows into %s.%s", len(rows), schema, table)
            return len(rows)

        cols = list(rows[0].keys())
        quoted_cols = ", ".join(f'"{c}"' for c in cols)
        placeholders = ", ".join(f"${idx}" for idx in range(1, len(cols) + 1))
        skip_cols = set(skip_update_cols or [])
        if not skip_cols and conflict_cols:
            skip_cols.update(conflict_cols)
        update_cols = [c for c in cols if c not in skip_cols]
        if constraint:
            quoted_constraint = constraint if constraint.startswith("\"") else f'"{constraint}"'
            if update_cols:
                updates = ", ".join(f'"{c}" = excluded."{c}"' for c in update_cols)
                conflict_clause = (
                    f"on conflict on constraint {quoted_constraint} do update set {updates}"
                )
            else:
                conflict_clause = f"on conflict on constraint {quoted_constraint} do nothing"
        elif conflict_cols:
            conflict = ", ".join(f'"{c}"' for c in conflict_cols)
            if update_cols:
                updates = ", ".join(f'"{c}" = excluded."{c}"' for c in update_cols)
                conflict_clause = f"on conflict ({conflict}) do update set {updates}"
            else:
                conflict_clause = f"on conflict ({conflict}) do nothing"
        else:
            conflict_clause = ""
        sql = f"""
            insert into {schema}.{table} ({quoted_cols})
            values ({placeholders})
            {conflict_clause}
        """
        values = [tuple(row[col] for col in cols) for row in rows]
        async with self._conn.transaction():
            await self._conn.executemany(sql, values)
        return len(rows)



async def fetch_json(client: httpx.AsyncClient, url: str, params: dict[str, Any] | None = None) -> Any:
    resp = await client.get(url, params=params, timeout=60)
    resp.raise_for_status()
    return resp.json()


# Helper to fetch plain text (e.g., DRAP text products)
async def fetch_text(
    client: httpx.AsyncClient,
    url: str,
    params: dict[str, Any] | None = None,
) -> str:
    """Fetch a text resource (e.g., DRAP text products)."""
    resp = await client.get(url, params=params, timeout=60)
    resp.raise_for_status()
    return resp.text


async def ingest_enlil(
    client: httpx.AsyncClient,
    writer: SupabaseWriter,
    days: int,
) -> None:
    logger.info("Fetching WSA–Enlil simulations")
    now = datetime.now(tz=UTC)
    params = {
        "startDate": (now - timedelta(days=days)).strftime("%Y-%m-%d"),
        "endDate": now.strftime("%Y-%m-%d"),
        "api_key": os.getenv("NASA_API", "DEMO_KEY"),
    }
    data = await fetch_json(client, "https://api.nasa.gov/DONKI/WSAEnlilSimulations", params)
    ext_rows: list[dict[str, Any]] = []
    mart_rows: list[dict[str, Any]] = []
    for entry in data or []:
        if not isinstance(entry, dict):
            continue
        simulation_id = entry.get("simulationID") or entry.get("simulationId")
        if not simulation_id:
            # Fallback to the completion timestamp so that the row is not lost.
            simulation_id = (entry.get("modelCompletionTime") or "unknown").replace(" ", "_")
        model_run = _parse_dt(entry.get("modelCompletionTime"))
        ext_rows.append(
            {
                "simulation_id": simulation_id,
                "model_run": model_run,
                "activity_id": entry.get("activityID") or entry.get("activityId"),
                "model_type": entry.get("modelType"),
                "impact_count": len(entry.get("impactList") or []),
                "raw": json.dumps(entry),
                "fetched_at": now,
            }
        )
        for impact in entry.get("impactList") or []:
            if not isinstance(impact, dict):
                continue
            arrival = _parse_dt(impact.get("arrivalTime") or impact.get("arrival_time"))
            if arrival is None:
                continue
            kp_est = _parse_float(impact.get("kp"))
            mart_rows.append(
                {
                    "arrival_time": arrival,
                    "simulation_id": simulation_id,
                    "location": impact.get("location") or impact.get("impactTarget"),
                    "cme_speed_kms": _parse_float(impact.get("speed")),
                    "kp_estimate": kp_est,
                    "confidence": impact.get("impactConfidence"),
                    "raw": json.dumps(impact),
                    "created_at": now,
                }
            )

    if ext_rows:
        await writer.upsert_many("ext", "enlil_forecast", ext_rows, ["simulation_id"])
    if mart_rows:
        await writer.upsert_many(
            "marts",
            "cme_arrivals",
            mart_rows,
            conflict_cols=None,
            constraint="cme_arrivals_pkey",
            skip_update_cols=["arrival_time", "simulation_id", "location"],
        )


async def ingest_sep_flux(
    client: httpx.AsyncClient,
    writer: SupabaseWriter,
    days: int,
) -> None:
    logger.info("Fetching GOES proton flux")
    data = await fetch_json(
        client,
        "https://services.swpc.noaa.gov/json/goes/primary/integral-protons-3-day.json",
    )
    cutoff = datetime.now(tz=UTC) - timedelta(days=days)
    rows: list[dict[str, Any]] = []
    for entry in data or []:
        if not isinstance(entry, dict):
            continue
        ts = _parse_dt(entry.get("time_tag"))
        if ts is None or ts < cutoff:
            continue
        satellite = entry.get("satellite")
        energy = entry.get("energy")
        flux = _parse_float(entry.get("flux"))
        s_scale, s_index = (None, None)
        if isinstance(energy, str) and ">=10" in energy.replace(" ", ""):
            s_scale, s_index = _s_scale_from_flux(flux)
        rows.append(
            {
                "ts_utc": ts,
                "satellite": str(satellite) if satellite is not None else None,
                "energy_band": energy,
                "flux": flux,
                "s_scale": s_scale,
                "s_scale_index": s_index,
                "raw": json.dumps(entry),
            }
        )
    if rows:
        await writer.upsert_many(
            "ext",
            "sep_flux",
            rows,
            ["ts_utc", "satellite", "energy_band"],
        )


async def ingest_radiation_belts(
    client: httpx.AsyncClient,
    writer: SupabaseWriter,
    days: int,
) -> None:
    logger.info("Fetching GOES electron flux")
    data = await fetch_json(
        client,
        "https://services.swpc.noaa.gov/json/goes/primary/integral-electrons-3-day.json",
    )
    cutoff = datetime.now(tz=UTC) - timedelta(days=days)
    rows: list[dict[str, Any]] = []
    for entry in data or []:
        if not isinstance(entry, dict):
            continue
        ts = _parse_dt(entry.get("time_tag"))
        if ts is None or ts < cutoff:
            continue
        energy = entry.get("energy")
        if isinstance(energy, str) and "2" not in energy:
            continue
        flux = _parse_float(entry.get("flux"))
        rows.append(
            {
                "ts_utc": ts,
                "satellite": str(entry.get("satellite")) if entry.get("satellite") else None,
                "energy_band": energy,
                "flux": flux,
                "risk_level": _radiation_risk(flux),
                "raw": json.dumps(entry),
            }
        )
    if rows:
        await writer.upsert_many(
            "ext",
            "radiation_belts",
            rows,
            ["ts_utc", "satellite", "energy_band"],
        )

    # Build daily rollups per satellite.
    grouped: dict[tuple[date, str], list[float]] = defaultdict(list)
    for row in rows:
        ts = row["ts_utc"]
        sat = row["satellite"] or "unknown"
        flux = row.get("flux")
        if ts is None or flux is None:
            continue
        grouped[(ts.date(), sat)].append(flux)
    daily_rows: list[dict[str, Any]] = []
    now = datetime.now(tz=UTC)
    for (day, sat), values in grouped.items():
        if not values:
            continue
        max_flux = max(values)
        avg_flux = sum(values) / len(values)
        daily_rows.append(
            {
                "day": day,
                "satellite": sat,
                "max_flux": max_flux,
                "avg_flux": avg_flux,
                "risk_level": _radiation_risk(max_flux),
                "computed_at": now,
            }
        )
    if daily_rows:
        await writer.upsert_many(
            "marts",
            "radiation_belts_daily",
            daily_rows,
            ["day", "satellite"],
        )


async def ingest_aurora(
    client: httpx.AsyncClient,
    writer: SupabaseWriter,
) -> None:
    logger.info("Fetching auroral power (OVATION); Wing Kp deprecated and handled elsewhere")
    aurora_data = await fetch_json(
        client,
        "https://services.swpc.noaa.gov/json/ovation_aurora_latest.json",
    )
    rows: list[dict[str, Any]] = []
    now = datetime.now(tz=UTC)
    # Wing Kp endpoint (rtsw/wing-kp.json) has been deprecated. We no longer fetch Kp here,
    # and will source Kp from the existing ext.space_weather / marts rollups instead.
    latest_kp: float | None = None
    for entry in aurora_data or []:
        if not isinstance(entry, dict):
            continue
        ts = _parse_dt(entry.get("time_tag") or entry.get("time"))
        hemisphere = entry.get("hemisphere") or entry.get("hemi")
        power = _parse_float(entry.get("hemispheric_power") or entry.get("power"))
        if ts is None or hemisphere is None:
            continue
        rows.append(
            {
                "ts_utc": ts,
                "hemisphere": hemisphere.lower(),
                "hemispheric_power_gw": power,
                "wing_kp": latest_kp,
                "raw": json.dumps(entry),
            }
        )
    if rows:
        await writer.upsert_many(
            "ext",
            "aurora_power",
            rows,
            ["ts_utc", "hemisphere"],
        )

    outlook_rows: list[dict[str, Any]] = []
    for row in rows:
        ts = row["ts_utc"]
        hemisphere = row["hemisphere"]
        power = row.get("hemispheric_power_gw")
        kp = row.get("wing_kp")
        outlook_rows.append(
            {
                "valid_from": ts,
                "valid_to": ts + timedelta(hours=1),
                "hemisphere": hemisphere,
                "headline": _aurora_headline(power, kp),
                "power_gw": power,
                "wing_kp": kp,
                "confidence": "medium" if power and power >= 40 else "low",
                "created_at": now,
            }
        )
    if outlook_rows:
        await writer.upsert_many(
            "marts",
            "aurora_outlook",
            outlook_rows,
            ["valid_from", "hemisphere"],
        )


async def ingest_coronal_hole(
    client: httpx.AsyncClient,
    writer: SupabaseWriter,
    days: int,
) -> None:
    logger.info("Fetching coronal-hole forecasts")
    data = await fetch_json(
        client,
        "https://services.swpc.noaa.gov/json/rtsw/rtsw_wind_1m.json",
    )
    cutoff = datetime.now(tz=UTC) - timedelta(days=days)
    rows: list[dict[str, Any]] = []
    for entry in data or []:
        if not isinstance(entry, dict):
            continue
        ts = _parse_dt(entry.get("time_tag") or entry.get("time"))
        if ts is None or ts < cutoff:
            continue
        rows.append(
            {
                "forecast_time": ts,
                "source": entry.get("source") or "swpc",
                "speed_kms": _parse_float(entry.get("solar_wind_speed")),
                "density_cm3": _parse_float(entry.get("proton_density")),
                "raw": json.dumps(entry),
            }
        )
    if rows:
        await writer.upsert_many(
            "ext",
            "ch_forecast",
            rows,
            ["forecast_time", "source"],
        )


async def ingest_cme_scoreboard(
    client: httpx.AsyncClient,
    writer: SupabaseWriter,
    days: int,
) -> None:
    logger.info("Fetching DONKI CME Scoreboard")
    now = datetime.now(tz=UTC)
    # Use the CCMC CME Scoreboard API. Wing-style DONKI endpoint has been retired.
    params = {
        "CMEtimeStart": (now - timedelta(days=days)).strftime("%Y-%m-%d"),
        "CMEtimeEnd": now.strftime("%Y-%m-%d"),
        # Include active and closed-out CMEs and do not skip “no arrival observed” events.
        "skipNoArrivalObservedCMEs": "false",
        "closeOutCMEsOnly": "false",
    }
    data = await fetch_json(
        client,
        "https://kauai.ccmc.gsfc.nasa.gov/CMEscoreboard/WS/get/predictions",
        params,
    )
    rows: list[dict[str, Any]] = []
    for entry in data or []:
        if not isinstance(entry, dict):
            continue
        event_time = _parse_dt(entry.get("cmeTime"))
        if event_time is None:
            continue
        rows.append(
            {
                "event_time": event_time,
                "team_name": entry.get("teamName"),
                "scoreboard_id": entry.get("scoreboardId"),
                "predicted_arrival": _parse_dt(entry.get("predictedArrivalTime")),
                "observed_arrival": _parse_dt(entry.get("observedArrivalTime")),
                "kp_predicted": _parse_float(entry.get("kpPrediction")),
                "raw": json.dumps(entry),
            }
        )
    if rows:
        await writer.upsert_many(
            "ext",
            "cme_scoreboard",
            rows,
            ["event_time", "team_name"],
        )


async def ingest_drap(
    client: httpx.AsyncClient,
    writer: SupabaseWriter,
    days: int,
) -> None:
    logger.info("Fetching D-RAP absorption indices")
    try:
        text = await fetch_text(
            client,
            "https://services.swpc.noaa.gov/text/drap_global_frequencies.txt",
        )
    except httpx.HTTPStatusError as exc:
        # The documented DRAP product is provided as a text product
        # (drap_global_frequencies.txt). Do not fail the whole Step 1 run
        # if this feed 404s; log and skip until a proper endpoint is wired up.
        status = exc.response.status_code if exc.response is not None else None
        if status == 404:
            logger.warning(
                "D-RAP text endpoint not available (404); skipping DRAP ingest for now"
            )
            return
        raise

    # Parse the DRAP text into a list of dicts using the first non-comment line as a header.
    header_cols: list[str] | None = None
    records: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if header_cols is None:
            header_cols = parts
            continue
        if len(parts) < len(header_cols):
            continue
        record = {header_cols[i]: parts[i] for i in range(len(header_cols))}
        records.append(record)

    if not records:
        logger.warning("No parsable DRAP records found in text feed; skipping")
        return

    data = records

    cutoff = datetime.now(tz=UTC) - timedelta(days=days)
    rows: list[dict[str, Any]] = []
    for entry in data or []:
        if not isinstance(entry, dict):
            continue
        ts = _parse_dt(entry.get("time_tag") or entry.get("time"))
        if ts is None or ts < cutoff:
            continue
        rows.append(
            {
                "ts_utc": ts,
                "frequency_mhz": _parse_float(entry.get("frequency")),
                "region": entry.get("region") or entry.get("location"),
                "absorption_db": _parse_float(entry.get("absorption")),
                "raw": json.dumps(entry),
            }
        )
    if rows:
        await writer.upsert_many(
            "ext",
            "drap_absorption",
            rows,
            conflict_cols=None,
            constraint="drap_absorption_pkey",
            skip_update_cols=["ts_utc", "region", "frequency_mhz"],
        )

    grouped: dict[tuple[date, str], list[float]] = defaultdict(list)
    now = datetime.now(tz=UTC)
    for row in rows:
        ts = row["ts_utc"]
        region = (row.get("region") or "global").lower()
        absorption = row.get("absorption_db")
        if ts is None or absorption is None:
            continue
        grouped[(ts.date(), region)].append(absorption)
    daily_rows: list[dict[str, Any]] = []
    for (day, region), values in grouped.items():
        if not values:
            continue
        daily_rows.append(
            {
                "day": day,
                "region": region,
                "max_absorption_db": max(values),
                "avg_absorption_db": sum(values) / len(values),
                "created_at": now,
            }
        )
    if daily_rows:
        await writer.upsert_many(
            "marts",
            "drap_absorption_daily",
            daily_rows,
            ["day", "region"],
        )


async def ingest_solar_cycle(
    client: httpx.AsyncClient,
    writer: SupabaseWriter,
) -> None:
    logger.info("Fetching solar-cycle forecasts")
    data = await fetch_json(
        client,
        "https://services.swpc.noaa.gov/json/solar-cycle/predicted-solar-cycle.json",
    )
    rows: list[dict[str, Any]] = []
    mart_rows: list[dict[str, Any]] = []
    for entry in data or []:
        if not isinstance(entry, dict):
            continue
        issued = _parse_dt(entry.get("issueTime") or entry.get("issued"))
        forecast_month = _parse_dt(entry.get("forecastTime") or entry.get("time_tag"))
        if forecast_month is None:
            continue
        sunspot = _parse_float(entry.get("predicted_ssn") or entry.get("sunspot_number"))
        flux = _parse_float(entry.get("predicted_f107"))
        rows.append(
            {
                "forecast_month": forecast_month.date(),
                "issued_at": issued,
                "sunspot_number": sunspot,
                "f10_7_flux": flux,
                "raw": json.dumps(entry),
            }
        )
        mart_rows.append(
            {
                "forecast_month": forecast_month.date(),
                "sunspot_number": sunspot,
                "f10_7_flux": flux,
                "issued_at": issued,
                "confidence": entry.get("confidence") or "baseline",
            }
        )
    if rows:
        await writer.upsert_many(
            "ext",
            "solar_cycle_forecast",
            rows,
            ["forecast_month"],
        )
    if mart_rows:
        await writer.upsert_many(
            "marts",
            "solar_cycle_progress",
            mart_rows,
            ["forecast_month"],
        )


async def ingest_magnetometer(
    client: httpx.AsyncClient,
    writer: SupabaseWriter,
    days: int,
) -> None:
    logger.info("Fetching AE/AL/PC magnetometer indices")
    try:
        data = await fetch_json(
            client,
            "https://services.swpc.noaa.gov/json/rtsw/indices.json",
        )
    except httpx.HTTPStatusError as exc:
        # The documented real-time indices feed under rtsw/indices.json is not available
        # or has been retired in the current SWPC JSON catalog. Do not fail the entire
        # Step 1 ingestion if this endpoint 404s; log and skip until a maintained source
        # for AE/AL/PC indices is wired up.
        status = exc.response.status_code if exc.response is not None else None
        if status == 404:
            logger.warning(
                "Magnetometer indices JSON endpoint not available (404); skipping magnetometer ingest for now"
            )
            return
        raise
    cutoff = datetime.now(tz=UTC) - timedelta(days=days)
    rows: list[dict[str, Any]] = []
    for entry in data or []:
        if not isinstance(entry, dict):
            continue
        ts = _parse_dt(entry.get("time_tag") or entry.get("time"))
        if ts is None or ts < cutoff:
            continue
        station = entry.get("station") or entry.get("observatory")
        rows.append(
            {
                "ts_utc": ts,
                "station": station,
                "ae": _parse_float(entry.get("ae")),
                "al": _parse_float(entry.get("al")),
                "au": _parse_float(entry.get("au")),
                "pc": _parse_float(entry.get("pc")),
                "raw": json.dumps(entry),
            }
        )
    if rows:
        await writer.upsert_many(
            "ext",
            "magnetometer_chain",
            rows,
            ["ts_utc", "station"],
        )

    grouped: dict[tuple[datetime, str], dict[str, Any]] = {}
    for row in rows:
        ts = row["ts_utc"]
        region = _region_from_station(row.get("station"))
        key = (ts.replace(minute=0, second=0, microsecond=0), region)
        bucket = grouped.setdefault(
            key,
            {
                "ts": key[0],
                "region": region,
                "ae": [],
                "al": [],
                "au": [],
                "pc": [],
                "stations": set(),
            },
        )
        bucket["stations"].add(row.get("station"))
        for field in ("ae", "al", "au", "pc"):
            value = row.get(field)
            if value is not None:
                bucket[field].append(value)

    mart_rows: list[dict[str, Any]] = []
    now = datetime.now(tz=UTC)
    for bucket in grouped.values():
        mart_rows.append(
            {
                "ts_utc": bucket["ts"],
                "region": bucket["region"],
                "ae": max(bucket["ae"]) if bucket["ae"] else None,
                "al": min(bucket["al"]) if bucket["al"] else None,
                "au": max(bucket["au"]) if bucket["au"] else None,
                "pc": max(bucket["pc"]) if bucket["pc"] else None,
                "stations": json.dumps(sorted(s for s in bucket["stations"] if s)),
                "created_at": now,
            }
        )
    if mart_rows:
        await writer.upsert_many(
            "marts",
            "magnetometer_regional",
            mart_rows,
            ["ts_utc", "region"],
        )


async def run_ingestion(args: argparse.Namespace) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    feeds = {
        "enlil": ingest_enlil,
        "sep": ingest_sep_flux,
        "radiation": ingest_radiation_belts,
        "aurora": ingest_aurora,
        "coronal": ingest_coronal_hole,
        "scoreboard": ingest_cme_scoreboard,
        "drap": ingest_drap,
        "solar": ingest_solar_cycle,
        "magnetometer": ingest_magnetometer,
    }
    selected = set(args.only or feeds.keys())
    invalid = selected - feeds.keys()
    if invalid:
        raise SystemExit(f"Unknown feed(s): {', '.join(sorted(invalid))}")

    dsn = os.getenv("SUPABASE_DB_URL")
    if not args.dry_run and not dsn:
        raise SystemExit("SUPABASE_DB_URL is required unless --dry-run is supplied")

    async with SupabaseWriter(dsn, dry_run=args.dry_run) as writer:
        async with httpx.AsyncClient(headers={"User-Agent": args.user_agent}) as client:
            if "enlil" in selected:
                await ingest_enlil(client, writer, args.days)
            if "sep" in selected:
                await ingest_sep_flux(client, writer, args.days)
            if "radiation" in selected:
                await ingest_radiation_belts(client, writer, args.days)
            if "aurora" in selected:
                await ingest_aurora(client, writer)
            if "coronal" in selected:
                await ingest_coronal_hole(client, writer, args.days)
            if "scoreboard" in selected:
                await ingest_cme_scoreboard(client, writer, args.days)
            if "drap" in selected:
                await ingest_drap(client, writer, args.days)
            if "solar" in selected:
                await ingest_solar_cycle(client, writer)
            if "magnetometer" in selected:
                await ingest_magnetometer(client, writer, args.days)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest space-weather forecast datasets")
    parser.add_argument("--days", type=int, default=3, help="look-back window for time-series feeds")
    parser.add_argument(
        "--only",
        nargs="+",
        help="subset of feeds to run (enlil, sep, radiation, aurora, coronal, scoreboard, drap, solar, magnetometer)",
    )
    parser.add_argument("--dry-run", action="store_true", help="skip Supabase writes")
    parser.add_argument(
        "--user-agent",
        default="gaiaeyes-backend/step1 (contact: ops@gaiaeyes.com)",
        help="HTTP User-Agent when talking to upstream APIs",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        asyncio.run(run_ingestion(args))
    except KeyboardInterrupt:
        raise SystemExit(130)


if __name__ == "__main__":  # pragma: no cover - exercised via CLI
    main()
