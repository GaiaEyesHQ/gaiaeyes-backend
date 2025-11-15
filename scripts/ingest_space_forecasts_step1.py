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
* OVATION auroral power nowcasts → ``ext.aurora_power`` +
  ``marts.aurora_outlook``.
* Coronal hole high-speed stream forecasts → ``ext.ch_forecast``.
* DONKI CME Scoreboard consensus → ``ext.cme_scoreboard``.
* D-RAP absorption indices → ``ext.drap_absorption`` +
  ``marts.drap_absorption_daily``.
* SWPC solar-cycle predictions → ``ext.solar_cycle_forecast`` +
  ``marts.solar_cycle_progress``.
* AE/AL/PC magnetometer chain (SuperMAG) → ``ext.magnetometer_chain`` +
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
import re
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


def _normalise_key(name: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "", name.strip().lower().replace(" ", "_"))


def _normalise_dict(data: dict[Any, Any]) -> dict[str, Any]:
    return {_normalise_key(str(k)): v for k, v in data.items()}


def _coerce_hemisphere(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    if text in {"n", "north", "northern"}:
        return "north"
    if text in {"s", "south", "southern"}:
        return "south"
    return None


def _aurora_timestamp(entry: dict[str, Any]) -> datetime | None:
    candidates = [
        entry.get("time_tag"),
        entry.get("time"),
        entry.get("timestamp"),
        entry.get("ts"),
        entry.get("observation_time"),
        entry.get("forecast_time"),
        entry.get("valid_time"),
    ]
    for value in candidates:
        ts = _parse_dt(value)
        if ts:
            return ts
    date_val = entry.get("date")
    time_val = entry.get("utctime") or entry.get("utc_time") or entry.get("hour")
    if date_val and time_val:
        ts = _parse_dt(f"{date_val} {time_val}")
        if ts:
            return ts
    return None


def _extract_aurora_rows(data: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    def emit(ts: datetime | None, hemisphere: Any, power: Any, raw_obj: Any) -> None:
        hemi = _coerce_hemisphere(hemisphere)
        if ts is None or hemi is None:
            return
        power_val = _parse_float(power)
        rows.append(
            {
                "ts_utc": ts,
                "hemisphere": hemi,
                "hemispheric_power_gw": power_val,
                "wing_kp": None,
                "raw": json.dumps(raw_obj),
            }
        )

    def handle_dict(obj: dict[str, Any]) -> None:
        norm = _normalise_dict(obj)
        ts = _aurora_timestamp(norm)

        def emit_from_mapping(mapping: Any, label: str | None = None) -> bool:
            emitted = False
            if isinstance(mapping, dict):
                for key, value in mapping.items():
                    hemi = _coerce_hemisphere(key)
                    if hemi:
                        emit(ts, hemi, value, {"hemisphere": hemi, "power": value, "source": label or "map"})
                        emitted = True
            elif isinstance(mapping, list):
                for entry in mapping:
                    if isinstance(entry, dict):
                        hemi = entry.get("hemisphere") or entry.get("hemi") or entry.get("label")
                        emit(
                            _aurora_timestamp(_normalise_dict(entry)) or ts,
                            hemi,
                            entry.get("hemispheric_power")
                            or entry.get("hemisphere_power")
                            or entry.get("power"),
                            entry,
                        )
                        emitted = True
            return emitted

        if emit_from_mapping(obj.get("Hemisphere Power") or obj.get("Hemispheric Power")):
            return
        if emit_from_mapping(norm.get("hemisphere_power") or norm.get("hemispheric_power")):
            return

        power_value = (
            norm.get("hemisphere_power")
            or norm.get("hemispheric_power")
            or norm.get("hemispheric_power_gw")
            or norm.get("power")
        )
        hemi_value = norm.get("hemisphere") or norm.get("hemi")
        if power_value is not None and hemi_value is not None:
            emit(ts, hemi_value, power_value, obj)

        data_block = obj.get("data") or obj.get("coordinates")
        if isinstance(data_block, list):
            # OVATION grid format: each entry is [longitude, latitude, aurora_value].
            if data_block and isinstance(data_block[0], (list, tuple)) and len(data_block[0]) >= 3:
                north_vals: list[float] = []
                south_vals: list[float] = []
                for entry in data_block:
                    if not isinstance(entry, (list, tuple)) or len(entry) < 3:
                        continue
                    lon, lat, aur_val = entry[0], entry[1], entry[2]
                    try:
                        lat_f = float(lat)
                        aur_f = float(aur_val)
                    except (TypeError, ValueError):
                        continue
                    if lat_f > 0:
                        north_vals.append(aur_f)
                    elif lat_f < 0:
                        south_vals.append(aur_f)
                if north_vals:
                    total = sum(north_vals)
                    emit(
                        ts,
                        "north",
                        total,
                        {"hemisphere": "north", "sum": total, "count": len(north_vals), "source": "ovation_grid"},
                    )
                if south_vals:
                    total = sum(south_vals)
                    emit(
                        ts,
                        "south",
                        total,
                        {"hemisphere": "south", "sum": total, "count": len(south_vals), "source": "ovation_grid"},
                    )
                return
            # Fallback: list of dict records with hemisphere/power fields.
            for entry in data_block:
                if isinstance(entry, dict):
                    entry_norm = _normalise_dict(entry)
                    hemi = entry_norm.get("hemisphere") or entry_norm.get("hemi")
                    power = entry_norm.get("hemispheric_power") or entry_norm.get("hemisphere_power")
                    emit(_aurora_timestamp(entry_norm) or ts, hemi, power, entry)

        for key, value in norm.items():
            if "power" not in key:
                continue
            hemi = None
            if "north" in key:
                hemi = "north"
            elif "south" in key:
                hemi = "south"
            elif key.endswith("_n"):
                hemi = "north"
            elif key.endswith("_s"):
                hemi = "south"
            if hemi is not None:
                emit(ts, hemi, value, {"hemisphere": hemi, "power": value, "source": key})

        for hemi_key in ("north", "south"):
            block = obj.get(hemi_key) or obj.get(hemi_key.capitalize())
            if isinstance(block, dict):
                emit(ts, hemi_key, block.get("hemisphere_power") or block.get("power"), block)

    if isinstance(data, list):
        for entry in data:
            if isinstance(entry, dict):
                handle_dict(entry)
    elif isinstance(data, dict):
        handle_dict(data)

    return rows


_DRAP_PIVOT_COL = re.compile(r"(?P<region>[a-z]+)_(?P<freq>[0-9]+(?:\.[0-9]+)?)m?hz?")


def _parse_frequency(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().lower()
    if not text:
        return None
    multiplier = 1.0
    if text.endswith("khz"):
        multiplier = 0.001
    elif text.endswith("hz") and not text.endswith("mhz"):
        multiplier = 1e-6
    cleaned = re.sub(r"[^0-9.]+", "", text)
    if not cleaned:
        return None
    try:
        return float(cleaned) * multiplier
    except ValueError:
        return None


def _parse_drap_timestamp(entry: dict[str, Any]) -> datetime | None:
    for key in (
        "time_tag",
        "timestamp",
        "time",
        "utc_time",
        "utctime",
        "valid_time",
    ):
        ts = _parse_dt(entry.get(key))
        if ts:
            return ts
    date_val = entry.get("date")
    time_val = entry.get("utctime") or entry.get("utc_time") or entry.get("time")
    if date_val and time_val:
        ts = _parse_dt(f"{date_val} {time_val}")
        if ts:
            return ts
    return None


def _normalise_region(region: Any) -> str:
    if not region:
        return "global"
    text = str(region).strip().lower()
    mapping = {
        "equator": "equatorial",
        "mid": "midlat",
        "midlatitude": "midlat",
        "polar_cap": "polar",
    }
    return mapping.get(text, text)


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
        "api_key": os.getenv("NASA_API_KEY"),
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
    logger.info("Fetching auroral power (OVATION JSON)")
    aurora_data = await fetch_json(
        client,
        "https://services.swpc.noaa.gov/json/ovation_aurora_latest.json",
    )
    rows = _extract_aurora_rows(aurora_data)
    now = datetime.now(tz=UTC)
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
        outlook_rows.append(
            {
                "valid_from": ts,
                "valid_to": ts + timedelta(hours=1),
                "hemisphere": hemisphere,
                "headline": _aurora_headline(power, None),
                "power_gw": power,
                "wing_kp": None,
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

    header_cols: list[str] | None = None
    records: list[dict[str, Any]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(":"):
            continue
        if line.startswith("#"):
            header_cols = [_normalise_key(part) for part in line.lstrip("#").split()]
            continue
        parts = line.split()
        if header_cols is None:
            header_cols = [_normalise_key(part) for part in parts]
            continue
        if not parts:
            continue
        count = min(len(parts), len(header_cols))
        record = {header_cols[i]: parts[i] for i in range(count)}
        records.append(record)

    if not records:
        logger.warning("No parsable DRAP records found in text feed; skipping")
        return

    cutoff = datetime.now(tz=UTC) - timedelta(days=days)
    rows: list[dict[str, Any]] = []
    for entry in records:
        norm = _normalise_dict(entry)
        ts = _parse_drap_timestamp(norm)
        if ts is None or ts < cutoff:
            continue
        region_value = (
            norm.get("region")
            or norm.get("band")
            or norm.get("latitude_band")
            or norm.get("sector")
        )
        freq_value = norm.get("frequency") or norm.get("freq")
        absorption_value = (
            norm.get("absorption_db")
            or norm.get("absorption")
            or norm.get("db")
        )
        freq = _parse_frequency(freq_value)
        absorption = _parse_float(absorption_value)
        added = False
        if freq is not None and absorption is not None:
            rows.append(
                {
                    "ts_utc": ts,
                    "frequency_mhz": freq,
                    "region": _normalise_region(region_value),
                    "absorption_db": absorption,
                    "raw": json.dumps(entry),
                }
            )
            added = True
        if added:
            continue
        for key, value in norm.items():
            match = _DRAP_PIVOT_COL.match(key)
            if not match:
                continue
            freq = _parse_frequency(match.group("freq"))
            absorption = _parse_float(value)
            if freq is None or absorption is None:
                continue
            rows.append(
                {
                    "ts_utc": ts,
                    "frequency_mhz": freq,
                    "region": _normalise_region(match.group("region")),
                    "absorption_db": absorption,
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
    logger.info("Fetching AE/AL/PC magnetometer indices from SuperMAG")
    stations_filter = os.getenv("SUPERMAG_STATIONS")
    end_time = datetime.now(tz=UTC)
    start_time = end_time - timedelta(days=days)
    params = {
        "start": start_time.strftime("%Y%m%d%H%M"),
        "end": end_time.strftime("%Y%m%d%H%M"),
        "fmt": "json",
    }
    if stations_filter:
        params["stations"] = stations_filter
    primary_url = "https://supermag.jhuapl.edu/mag/indices/SuperMAG_AE.json"
    fallback_url = "https://supermag.jhuapl.edu/mag/"

    def extract_records(payload: Any) -> list[Any]:
        if isinstance(payload, dict):
            for key in (
                "data",
                "records",
                "indices",
                "result",
                "values",
                "MagIdx",
                "magidx",
            ):
                block = payload.get(key)
                if isinstance(block, list):
                    return block
        elif isinstance(payload, list):
            return payload
        return []

    try:
        data = await fetch_json(client, primary_url, params)
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        logger.warning(
            "Primary SuperMAG AE endpoint failed (%s); falling back to generic feed",
            exc,
        )
        data = None

    records = extract_records(data) if data is not None else []
    if not records:
        try:
            data = await fetch_json(client, fallback_url, params)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                logger.warning(
                    "SuperMAG fallback endpoint returned 404; skipping magnetometer ingest",
                )
                return
            raise
        except json.JSONDecodeError:
            logger.warning(
                "SuperMAG fallback endpoint returned non-JSON content; skipping magnetometer ingest",
            )
            return
        records = extract_records(data)
    if not records:
        logger.warning(
            "SuperMAG response did not include records; skipping magnetometer ingest",
        )
        return

    rows: list[dict[str, Any]] = []
    for entry in records:
        if not isinstance(entry, dict):
            continue
        norm = _normalise_dict(entry)
        ts = _parse_dt(
            entry.get("time_tag")
            or entry.get("time")
            or entry.get("timestamp")
            or norm.get("timestamp")
            or norm.get("datetime")
            or norm.get("utctime")
        )
        if ts is None:
            date_field = (
                entry.get("date")
                or entry.get("date_utc")
                or entry.get("Date_UTC")
                or norm.get("date")
                or norm.get("date_utc")
            )
            time_field = (
                entry.get("time_utc")
                or entry.get("Time_UTC")
                or norm.get("time_utc")
            )
            if date_field and time_field:
                ts = _parse_dt(f"{date_field}T{time_field}")
        if ts is None:
            continue
        station = (
            entry.get("station")
            or entry.get("station_code")
            or entry.get("observatory")
            or entry.get("site")
            or entry.get("code")
            or norm.get("station")
            or norm.get("station_code")
        )
        if not station:
            station = entry.get("index") or entry.get("source") or "supermag_global"
        ae = _parse_float(
            entry.get("ae")
            or entry.get("AE")
            or norm.get("sme")
            or norm.get("sm_e")
        )
        al = _parse_float(
            entry.get("al")
            or entry.get("AL")
            or norm.get("sml")
            or norm.get("sm_l")
        )
        au = _parse_float(
            entry.get("au")
            or entry.get("AU")
            or norm.get("smu")
            or norm.get("sm_u")
        )
        pc = _parse_float(
            entry.get("pc")
            or entry.get("PC")
            or norm.get("smr")
            or norm.get("sm_r")
        )
        if ae is None and al is None and au is None and pc is None:
            continue
        rows.append(
            {
                "ts_utc": ts,
                "station": station,
                "ae": ae,
                "al": al,
                "au": au,
                "pc": pc,
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
        async with httpx.AsyncClient() as client:
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
