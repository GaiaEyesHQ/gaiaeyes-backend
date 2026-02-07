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
  ``marts.magnetometer_regional``. -- INGESTION NOT WORKING FOR SUPERMAG, MOVED TO PHASE 2 -- OTHER MAGNETOSPHERE DATA IN ext.magnetosphere_pulse - already has router

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
        # Normalise trailing Z and tolerate naive timestamps.
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except ValueError:
        # Try a couple of common fallbacks (space separator, missing offset).
        try:
            return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
        except ValueError:
            try:
                return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=UTC)
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


# --- Local helpers for robust field extraction ---
def _first_float(d: dict[str, Any], *keys: str) -> float | None:
    for k in keys:
        v = d.get(k)
        f = _parse_float(v)
        if f is not None:
            return f
    return None

def _first_nonempty(d: dict[str, Any], *keys: str) -> Any:
    for k in keys:
        v = d.get(k)
        if v is not None and v != "":
            return v
    return None


def _coalesce(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


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


# Helper to parse SWPC aurora hemi-power text table
def _parse_aurora_hemi_table(text: str) -> list[dict[str, Any]]:
    """
    Parse SWPC hemi-power text table into structured rows.

    Returns a list of dicts with:
      {"obs": datetime, "fcst": datetime|None, "north": float|None, "south": float|None}
    """
    rows: list[dict[str, Any]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or set(line) == {"-"}:
            continue
        # Expected tokens: OBS  FCST  NORTH  SOUTH
        parts = re.split(r"\s+", line)
        if len(parts) < 4:
            continue
        obs_s, fcst_s, north_s, south_s = parts[0], parts[1], parts[2], parts[3]
        # Examples: 2026-02-07_00:00
        def _ts(s: str) -> datetime | None:
            try:
                return datetime.strptime(s, "%Y-%m-%d_%H:%M").replace(tzinfo=UTC)
            except Exception:
                return _parse_dt(s)

        obs_dt = _ts(obs_s)
        fcst_dt = _ts(fcst_s)
        north = _parse_float(north_s)
        south = _parse_float(south_s)
        if obs_dt is None:
            continue
        rows.append({"obs": obs_dt, "fcst": fcst_dt, "north": north, "south": south})
    return rows


_DRAP_PIVOT_COL = re.compile(r"(?P<region>[a-z]+)_(?P<freq>[0-9]+(?:\.[0-9]+)?)m?hz?")


@dataclass
class DrapGrid:
    detected: bool
    valid_time: datetime | None
    frequency_mhz: float | None
    rows: list[tuple[float, float, float]]


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


def _parse_drap_grid(text: str) -> DrapGrid:
    """Parse the DRAP global grid text product into lat/lon/value triples."""

    valid_time: datetime | None = None
    frequency_mhz: float | None = None
    longitudes: list[float] | None = None
    waiting_for_longitudes = False
    rows: list[tuple[float, float, float]] = []

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            header = stripped.lstrip("#").strip()
            header_lower = header.lower()
            if "product valid at" in header_lower and valid_time is None:
                _, _, remainder = header.partition(":")
                ts_text = remainder.strip() or header
                ts_text = re.sub(r"\s*utc$", "", ts_text, flags=re.IGNORECASE)
                parsed = _parse_dt(ts_text)
                if parsed:
                    valid_time = parsed
            if frequency_mhz is None and "mhz" in header_lower:
                match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*mhz", header_lower)
                if match:
                    try:
                        frequency_mhz = float(match.group(1))
                    except ValueError:
                        pass
            if "latitude and longitude" in header_lower:
                waiting_for_longitudes = True
            continue
        if waiting_for_longitudes and longitudes is None:
            lon_values: list[float] = []
            for token in stripped.split():
                try:
                    lon_values.append(float(token))
                except ValueError:
                    continue
            if lon_values:
                longitudes = lon_values
                waiting_for_longitudes = False
            continue
        if longitudes is None:
            continue
        if re.fullmatch(r"-+", stripped):
            continue
        if "|" not in line:
            continue
        lat_text, values_text = line.split("|", 1)
        try:
            lat = float(lat_text.strip())
        except ValueError:
            logger.debug("Skipping DRAP row with invalid latitude: %s", lat_text)
            continue
        value_tokens = values_text.strip().split()
        if len(value_tokens) != len(longitudes):
            logger.debug(
                "Skipping DRAP row due to column mismatch (lat=%s)",
                lat_text.strip(),
            )
            continue
        parsed_values: list[float] = []
        valid_row = True
        for token in value_tokens:
            parsed_value = _parse_float(token)
            if parsed_value is None:
                valid_row = False
                break
            parsed_values.append(parsed_value)
        if not valid_row:
            logger.debug("Skipping DRAP row due to non-numeric values at lat=%s", lat)
            continue
        for lon, absorption in zip(longitudes, parsed_values):
            rows.append((lat, lon, absorption))

    detected = longitudes is not None
    return DrapGrid(
        detected=detected,
        valid_time=valid_time,
        frequency_mhz=frequency_mhz,
        rows=rows,
    )


def _parse_month_label(value: Any) -> date | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if re.fullmatch(r"\d{4}-\d{2}", text):
        text = f"{text}-01"
    try:
        parsed = datetime.strptime(text, "%Y-%m-%d").date()
        return parsed.replace(day=1)
    except ValueError:
        dt_value = _parse_dt(text)
        if dt_value:
            return date(dt_value.year, dt_value.month, 1)
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
            # --- Robust extraction of arrival, speed, kp_est, confidence ---
            # Arrival time
            arrival = _parse_dt(
                _first_nonempty(impact, "arrivalTime", "arrival_time", "impactArrivalTime", "impact_time")
            )
            if arrival is None:
                # Some feeds place arrival on nested keys or as 'time'
                arrival = _parse_dt(_first_nonempty(impact, "time", "timestamp"))

            # Speed (km/s) – accept multiple aliases; convert m/s if value is unusually large
            cme_speed_kms = _first_float(
                impact,
                "speed", "cmeSpeed", "impactSpeed", "radialSpeed", "velocity", "v", "speed_kms",
            )
            if cme_speed_kms is not None and cme_speed_kms > 3000:
                # looks like m/s, convert to km/s
                cme_speed_kms = cme_speed_kms / 1000.0
            # Sometimes speed sits on parent entry (simulation-level); try a gentle fallback
            if cme_speed_kms is None:
                cme_speed_kms = _first_float(entry, "speed", "cmeSpeed", "radialSpeed")

            # Kp estimate – prefer the highest available among common keys
            kp_candidates = []
            for key in ("kp", "maxKp", "predictedMaxKp", "kp_prediction", "kp_predicted", "kp90", "kp_90", "kp_180"):
                val = _parse_float(impact.get(key))
                if val is not None:
                    kp_candidates.append(val)
            kp_est = max(kp_candidates) if kp_candidates else None

            # Confidence – normalize to string; accept percentage or label
            confidence_val = _first_nonempty(impact, "impactConfidence", "confidence", "confidenceInPercentage")
            if isinstance(confidence_val, (int, float)):
                confidence = f"{confidence_val}%"
            else:
                confidence = str(confidence_val) if confidence_val is not None else None

            # Fallback: if Kp is missing, try to infer from ext.cme_scoreboard around the arrival window
            if kp_est is None and arrival is not None and writer._conn is not None:
                try:
                    row = await writer._conn.fetchrow(
                        """
                        select max(kp_predicted) as kp
                        from ext.cme_scoreboard
                        where coalesce(predicted_arrival, observed_arrival) between $1 and $2
                        """,
                        arrival - timedelta(hours=6),
                        arrival + timedelta(hours=6),
                    )
                    if row and row["kp"] is not None:
                        kp_est = float(row["kp"])
                except Exception as exc:
                    logger.debug("scoreboard Kp fallback failed: %s", exc)

            # Log missing fields for diagnostics
            if arrival is None:
                logger.debug("WSA-Enlil impact missing arrivalTime; simulation_id=%s keys=%s", simulation_id, list(impact.keys()))
            if cme_speed_kms is None:
                logger.debug("WSA-Enlil impact missing speed; simulation_id=%s", simulation_id)
            if kp_est is None:
                logger.debug("WSA-Enlil impact missing Kp estimate; simulation_id=%s", simulation_id)

            mart_rows.append(
                {
                    "arrival_time": arrival,
                    "simulation_id": simulation_id,
                    "location": impact.get("location") or impact.get("impactTarget"),
                    "cme_speed_kms": cme_speed_kms,
                    "kp_estimate": kp_est,
                    "confidence": confidence,
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


# --- Begin: ingest_xray_flux function ---
async def ingest_xray_flux(
    client: httpx.AsyncClient,
    writer: SupabaseWriter,
    days: int,
) -> None:
    logger.info("Fetching GOES X-ray flux")
    # Use the primary XRAYS 3-day product and filter to the requested window.
    data = await fetch_json(
        client,
        "https://services.swpc.noaa.gov/json/goes/primary/xrays-3-day.json",
    )
    cutoff = datetime.now(tz=UTC) - timedelta(days=days)
    rows: list[dict[str, Any]] = []
    for entry in data or []:
        if not isinstance(entry, dict):
            continue
        ts = _parse_dt(entry.get("time_tag"))
        if ts is None or ts < cutoff:
            continue
        flux = _parse_float(entry.get("flux"))
        rows.append(
            {
                "ts_utc": ts,
                "satellite": str(entry.get("satellite")) if entry.get("satellite") is not None else None,
                "energy_band": entry.get("energy"),
                "flux": flux,
                "raw": json.dumps(entry),
            }
        )
    if rows:
        await writer.upsert_many(
            "ext",
            "xray_flux",
            rows,
            ["ts_utc", "satellite", "energy_band"],
        )
# --- End: ingest_xray_flux function ---


async def ingest_aurora(
    client: httpx.AsyncClient,
    writer: SupabaseWriter,
) -> None:
    logger.info("Fetching auroral power (OVATION hemi-power text)")
    ext_rows: list[dict[str, Any]] = []
    outlook_rows: list[dict[str, Any]] = []
    now = datetime.now(tz=UTC)

    # 1) Prefer the concise hemi-power text table (north/south GW)
    try:
        text = await fetch_text(
            client,
            "https://services.swpc.noaa.gov/text/aurora-nowcast-hemi-power.txt",
        )
        hemi_records = _parse_aurora_hemi_table(text)
        for rec in hemi_records:
            obs = rec["obs"]
            fcst = rec.get("fcst") or (obs + timedelta(hours=1))
            for hemi in ("north", "south"):
                power = rec.get(hemi)
                if power is None:
                    continue
                ext_rows.append(
                    {
                        "ts_utc": obs,
                        "hemisphere": hemi,
                        "hemispheric_power_gw": power,
                        "wing_kp": None,
                        "raw": json.dumps(
                            {
                                "source": "aurora-nowcast-hemi-power.txt",
                                "obs": obs.isoformat(),
                                "fcst": fcst.isoformat() if isinstance(fcst, datetime) else None,
                                "hemisphere": hemi,
                                "power_gw": power,
                            }
                        ),
                    }
                )
                outlook_rows.append(
                    {
                        "valid_from": obs,
                        "valid_to": fcst if isinstance(fcst, datetime) else obs + timedelta(hours=1),
                        "hemisphere": hemi,
                        "headline": _aurora_headline(power, None),
                        "power_gw": power,
                        "wing_kp": None,
                        "confidence": "medium" if (power is not None and power >= 40) else "low",
                        "created_at": now,
                    }
                )
    except httpx.HTTPError as exc:
        logger.warning("Hemi-power text fetch failed (%s); will try JSON grid fallback", exc)

    # 2) Fallback to the JSON grid if the table produced no rows
    if not ext_rows:
        logger.info("Falling back to OVATION JSON grid for auroral power")
        try:
            aurora_data = await fetch_json(
                client,
                "https://services.swpc.noaa.gov/json/ovation_aurora_latest.json",
            )
            grid_rows = _extract_aurora_rows(aurora_data)
            for row in grid_rows:
                # _extract_aurora_rows already normalizes shape
                ext_rows.append(
                    {
                        "ts_utc": row["ts_utc"],
                        "hemisphere": row["hemisphere"],
                        "hemispheric_power_gw": row.get("hemispheric_power_gw"),
                        "wing_kp": row.get("wing_kp"),
                        "raw": json.dumps(row),
                    }
                )
                power = row.get("hemispheric_power_gw")
                outlook_rows.append(
                    {
                        "valid_from": row["ts_utc"],
                        "valid_to": row["ts_utc"] + timedelta(hours=1),
                        "hemisphere": row["hemisphere"],
                        "headline": _aurora_headline(power, row.get("wing_kp")),
                        "power_gw": power,
                        "wing_kp": row.get("wing_kp"),
                        "confidence": "medium" if (power is not None and power >= 40) else "low",
                        "created_at": now,
                    }
                )
        except httpx.HTTPError as exc:
            logger.warning("OVATION JSON fetch failed as well (%s); skipping aurora ingest", exc)

    if ext_rows:
        await writer.upsert_many(
            "ext",
            "aurora_power",
            ext_rows,
            ["ts_utc", "hemisphere"],
        )
    else:
        logger.warning("Aurora ingest produced no rows")

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
    """
    Ingest a proxy for CH/HSS using SWPC real-time solar wind (1‑minute) feed.
    We normalise timestamp, speed (km/s), and density (cm^-3) into ext.ch_forecast.
    """
    logger.info("Fetching coronal-hole / real-time wind proxies")
    try:
        data = await fetch_json(
            client,
            "https://services.swpc.noaa.gov/json/rtsw/rtsw_wind_1m.json",
        )
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        logger.warning("RTSW wind feed failed: %s", exc)
        return

    cutoff = datetime.now(tz=UTC) - timedelta(days=days)
    rows: list[dict[str, Any]] = []

    for entry in data or []:
        if not isinstance(entry, dict):
            continue

        ts = _parse_dt(entry.get("time_tag") or entry.get("time") or entry.get("timestamp"))
        if ts is None or ts < cutoff:
            continue

        # --- Robust speed/density extraction with fallbacks ---
        # Try scalar speed fields first
        sp_scalar = _parse_float(
            _coalesce(
                entry.get("proton_speed"),
                entry.get("bulk_speed"),
                entry.get("solar_wind_speed"),
                entry.get("plasma_speed"),
                entry.get("speed"),
                entry.get("flow_speed"),
                entry.get("bulk_speed_kms"),
                entry.get("v_kms"),
            )
        )

        # If no scalar, try vector components (vx, vy, vz) and compute magnitude
        speed_kms = None
        if sp_scalar is not None:
            # Heuristic: if value looks like m/s, convert to km/s
            speed_kms = sp_scalar / 1000.0 if sp_scalar > 3000 else sp_scalar
        else:
            vx = _parse_float(
                _coalesce(
                    entry.get("proton_vx_gse"),
                    entry.get("proton_vx_gsm"),
                    entry.get("vx_gse"),
                    entry.get("vx"),
                )
            )
            vy = _parse_float(
                _coalesce(
                    entry.get("proton_vy_gse"),
                    entry.get("proton_vy_gsm"),
                    entry.get("vy_gse"),
                    entry.get("vy"),
                )
            )
            vz = _parse_float(
                _coalesce(
                    entry.get("proton_vz_gse"),
                    entry.get("proton_vz_gsm"),
                    entry.get("vz_gse"),
                    entry.get("vz"),
                )
            )
            if vx is not None and vy is not None and vz is not None:
                sp = math.sqrt(vx * vx + vy * vy + vz * vz)
                speed_kms = sp / 1000.0 if sp > 3000 else sp

        # Sanity clamp improbable speeds
        if speed_kms is not None and not (50.0 <= speed_kms <= 3000.0):
            logger.debug("RTSW speed out of plausible range: %s km/s (discarding)", speed_kms)
            speed_kms = None

        # Density aliases
        density_cm3 = _parse_float(
            _coalesce(
                entry.get("proton_density"),
                entry.get("plasma_density"),
                entry.get("density"),
                entry.get("n_cm3"),
            )
        )

        # Only upsert if at least one metric is present; log a hint if neither
        if speed_kms is None and density_cm3 is None:
            logger.debug(
                "RTSW row had no speed or density; sample keys=%s",
                list(entry.keys())[:12],
            )
            continue

        rows.append(
            {
                "forecast_time": ts,
                "source": "rtsw_wind_1m",
                "speed_kms": speed_kms,
                "density_cm3": density_cm3,
                "raw": json.dumps(entry),
            }
        )

    if rows:
        inserted = await writer.upsert_many(
            "ext",
            "ch_forecast",
            rows,
            ["forecast_time", "source"],
        )
        logger.info("Upserted %d rows into ext.ch_forecast", inserted)
    else:
        logger.warning(
            "No rows parsed for ext.ch_forecast; sample=%s",
            (data[0] if isinstance(data, list) and data else None),
        )


async def ingest_cme_scoreboard(
    client: httpx.AsyncClient,
    writer: SupabaseWriter,
    days: int,
) -> None:
    """
    Ingest DONKI/CCMC CME Scoreboard predictions.

    Handles common shapes:
      - Top-level event fields: cmeID, observedTime, arrivalTime
      - Nested predictions[] with predictedMethodName, predictedArrivalTime,
        predictedMaxKpLowerRange/UpperRange, etc.
    """
    logger.info("Fetching DONKI CME Scoreboard")
    now = datetime.now(tz=UTC)
    params = {
        "CMEtimeStart": (now - timedelta(days=days)).strftime("%Y-%m-%d"),
        "CMEtimeEnd": now.strftime("%Y-%m-%d"),
        "format": "json",
    }

    try:
        data = await fetch_json(
            client,
            "https://kauai.ccmc.gsfc.nasa.gov/CMEscoreboard/WS/get/predictions",
            params,
        )
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        logger.warning("CME Scoreboard fetch failed: %s", exc)
        return

    # Normalise to iterable of event dicts
    if isinstance(data, list):
        events = data
    elif isinstance(data, dict):
        # Some responses may wrap under various keys
        for key in ("predictions", "result", "data", "records"):
            block = data.get(key)
            if isinstance(block, list):
                events = block
                break
        else:
            events = [data]
    else:
        events = []

    rows: list[dict[str, Any]] = []
    cutoff = now - timedelta(days=days)

    for ev in events:
        if not isinstance(ev, dict):
            continue

        event_time = _parse_dt(
            ev.get("observedTime")
            or ev.get("cmeTime")
            or ev.get("eventTime")
            or ev.get("event_time")
        )
        if event_time is None or event_time < cutoff:
            # If still no event timestamp, try any predicted-arrival as a proxy for filtering
            candidate = _parse_dt(ev.get("arrivalTime") or ev.get("predictedArrivalTime"))
            if candidate is None or candidate < cutoff:
                continue

        observed_arrival = _parse_dt(
            ev.get("observedArrivalTime") or ev.get("arrivalTime")
        )
        scoreboard_id = ev.get("scoreboardId") or ev.get("cmeID") or ev.get("cmeId")

        # Preferred: expand nested predictions
        preds = ev.get("predictions") or []
        if isinstance(preds, list) and preds:
            for p in preds:
                if not isinstance(p, dict):
                    continue
                predicted_arrival = _parse_dt(
                    p.get("predictedArrivalTime")
                    or p.get("arrivalTime")
                    or p.get("predicted_arrival_time")
                )
                # Kp: prefer the upper bound; else lower; else single kp field.
                kp_upper = _parse_float(
                    _coalesce(
                        p.get("predictedMaxKpUpperRange"),
                        p.get("predictedMaxKpUpper"),
                    )
                )
                kp_lower = _parse_float(
                    _coalesce(
                        p.get("predictedMaxKpLowerRange"),
                        p.get("predictedMaxKpLower"),
                    )
                )
                kp_pred = kp_upper if kp_upper is not None else kp_lower
                team_name = (
                    p.get("teamName")
                    or p.get("predictedMethodName")
                    or p.get("model")
                    or "unknown"
                )
                # Skip obviously incomplete predictions
                if predicted_arrival is None and kp_pred is None:
                    continue
                rows.append(
                    {
                        "event_time": event_time,
                        "team_name": team_name,
                        "scoreboard_id": scoreboard_id,
                        "predicted_arrival": predicted_arrival,
                        "observed_arrival": observed_arrival,
                        "kp_predicted": kp_pred,
                        "no_arrival_observed": (bool(ev.get("noArrivalObserved")) if ev.get("noArrivalObserved") is not None else None),
                        "cme_note": ev.get("cmeNote") or ev.get("cme_note"),
                        "prediction_note": p.get("predictionNote") or p.get("note"),
                        "raw": json.dumps({"event": ev, "prediction": p}),
                    }
                )
        else:
            # Fallback: single-layer shape (rare)
            predicted_arrival = _parse_dt(
                ev.get("predictedArrivalTime") or ev.get("arrivalTime")
            )
            kp_pred = _parse_float(
                _coalesce(
                    ev.get("kpPrediction"),
                    ev.get("kp_prediction"),
                    ev.get("kp"),
                )
            )
            team_name = ev.get("teamName") or "unknown"
            if predicted_arrival is not None or kp_pred is not None:
                rows.append(
                    {
                        "event_time": event_time,
                        "team_name": team_name,
                        "scoreboard_id": scoreboard_id,
                        "predicted_arrival": predicted_arrival,
                        "observed_arrival": observed_arrival,
                        "kp_predicted": kp_pred,
                        "no_arrival_observed": (bool(ev.get("noArrivalObserved")) if ev.get("noArrivalObserved") is not None else None),
                        "cme_note": ev.get("cmeNote") or ev.get("cme_note"),
                        "prediction_note": ev.get("predictionNote") or ev.get("note"),
                        "raw": json.dumps(ev),
                    }
                )

    if rows:
        inserted = await writer.upsert_many(
            "ext",
            "cme_scoreboard",
            rows,
            ["event_time", "team_name"],
        )
        logger.info("Upserted %d rows into ext.cme_scoreboard", inserted)
    else:
        logger.warning(
            "No CME scoreboard records parsed for %s → %s",
            params["CMEtimeStart"],
            params["CMEtimeEnd"],
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

    cutoff = datetime.now(tz=UTC) - timedelta(days=days)
    rows: list[dict[str, Any]] = []

    grid = _parse_drap_grid(text)
    if grid.detected:
        if grid.valid_time is None:
            logger.warning(
                "Detected DRAP grid but could not parse Product Valid At timestamp; skipping",
            )
            return
        if grid.valid_time < cutoff:
            logger.info(
                "DRAP grid is older than %s days (valid at %s); skipping",
                days,
                grid.valid_time,
            )
            return
        frequency = grid.frequency_mhz or 10.0
        for lat, lon, absorption in grid.rows:
            rows.append(
                {
                    "ts_utc": grid.valid_time,
                    "lat": lat,
                    "lon": lon,
                    "frequency_mhz": frequency,
                    "region": "global",
                    "absorption_db": absorption,
                    "raw": json.dumps({"lat": lat, "lon": lon, "value": absorption}),
                }
            )
        if not rows:
            logger.warning("Detected DRAP grid but no valid absorption rows were parsed")
    else:
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

    if not rows:
        logger.warning("No D-RAP rows survived parsing; skipping upsert")
        return
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
    global_issue: datetime | None = None
    if isinstance(data, dict):
        global_issue = _parse_dt(
            data.get("issueTime")
            or data.get("issued")
            or data.get("issue_time")
            or data.get("issue")
        )
        records = data.get("records") or data.get("data") or data.get("values")
        if isinstance(records, list):
            iterable = records
        else:
            iterable = [data]
    else:
        iterable = data or []
    for entry in iterable:
        if not isinstance(entry, dict):
            continue
        issued = _parse_dt(
            entry.get("issueTime")
            or entry.get("issue_time")
            or entry.get("issued")
            or entry.get("issued_at")
        )
        if issued is None:
            issued = global_issue
        forecast_month = _parse_month_label(
            entry.get("time-tag")
            or entry.get("time_tag")
            or entry.get("forecast_month")
            or entry.get("forecastTime")
        )
        if forecast_month is None:
            continue
        sunspot = _parse_float(entry.get("predicted_ssn") or entry.get("sunspot_number"))
        flux = _parse_float(
            entry.get("predicted_f10.7")
            or entry.get("predicted_f107")
            or entry.get("f10.7")
            or entry.get("f107")
        )
        rows.append(
            {
                "forecast_month": forecast_month,
                "issued_at": issued,
                "sunspot_number": sunspot,
                "f10_7_flux": flux,
                "raw": json.dumps(entry),
            }
        )
        mart_rows.append(
            {
                "forecast_month": forecast_month,
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
    primary_url = "https://supermag.jhuapl.edu/services/indices.php"
    fallback_url = "https://supermag.jhuapl.edu/mag/"

    USERNAME_ENV = "SUPERMAG_USERNAME"
    STATIONS_ENV = "SUPERMAG_STATIONS"

    username = os.getenv(USERNAME_ENV)
    stations_filter = os.getenv(STATIONS_ENV)

    if not username:
        logger.warning("%s is not configured; using proxy fallback from ext.magnetosphere_pulse", USERNAME_ENV)
        await ingest_magnetometer_proxy(writer, days)
        return

    logger.info("Fetching AE/AL/PC magnetometer indices from %s", primary_url)
    end_time = datetime.now(tz=UTC)
    start_time = end_time - timedelta(days=days)
    params = {
        "start": start_time.strftime("%Y%m%d%H%M"),
        "end": end_time.strftime("%Y%m%d%H%M"),
        "fmt": "json",
        "user": username,
    }
    if stations_filter:
        params["stations"] = stations_filter

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
            "SuperMAG response did not include records; falling back to proxy from ext.magnetosphere_pulse",
        )
        await ingest_magnetometer_proxy(writer, days)
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
            _coalesce(
                entry.get("ae"),
                entry.get("AE"),
                norm.get("sme"),
                norm.get("sm_e"),
            )
        )
        al = _parse_float(
            _coalesce(
                entry.get("al"),
                entry.get("AL"),
                norm.get("sml"),
                norm.get("sm_l"),
            )
        )
        au = _parse_float(
            _coalesce(
                entry.get("au"),
                entry.get("AU"),
                norm.get("smu"),
                norm.get("sm_u"),
            )
        )
        pc = _parse_float(
            _coalesce(
                entry.get("pc"),
                entry.get("PC"),
                norm.get("smr"),
                norm.get("sm_r"),
            )
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
        "xray": ingest_xray_flux,
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
            if "xray" in selected:
                await ingest_xray_flux(client, writer, args.days)
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
        help="subset of feeds to run (enlil, sep, radiation, xray, aurora, coronal, scoreboard, drap, solar, magnetometer)",
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

async def ingest_magnetometer_proxy(
    writer: SupabaseWriter,
    days: int,
) -> None:
    """
    Proxy fallback: derive coarse AE/AL/AU/PC-like indices from ext.magnetosphere_pulse.

    This is *not* a replacement for SuperMAG and should be treated as an
    approximation. We store the result into marts.magnetometer_regional with
    region='global' and stations=["proxy:magnetosphere_pulse"] so downstream
    refresh jobs can use it when true magnetometer data is unavailable.
    """
    if writer._conn is None:
        logger.warning("Proxy magnetometer requires a DB connection; skipping")
        return

    end_ts = datetime.now(tz=UTC)
    start_ts = end_ts - timedelta(days=days)

    rows = await writer._conn.fetch(
        """
        select ts, bz_nt, v_kms, n_cm3
        from ext.magnetosphere_pulse
        where ts >= $1 and ts < $2
        order by ts asc
        """,
        start_ts,
        end_ts,
    )
    if not rows:
        logger.info("magnetosphere_pulse had no rows in window; skipping proxy")
        return

    # Bucket by hour (UTC)
    buckets: dict[datetime, list[tuple[float | None, float | None, float | None]]] = {}
    for r in rows:
        ts: datetime = r["ts"]
        hour = ts.replace(minute=0, second=0, microsecond=0, tzinfo=UTC)
        buckets.setdefault(hour, []).append(
            (r["bz_nt"], r["v_kms"], r["n_cm3"])
        )

    def proxy_from_sample(bz: float | None, v: float | None, n: float | None) -> tuple[float, float, float]:
        """
        Heuristic proxies:
          - AE ~ coupling from southward Bz + elevated wind + density bursts
          - AL ~ ~60% of AE, negative (westward electrojet)
          - PC ~ velocity * sqrt(density) scaling (order-units, not calibrated)
        All outputs are clipped to non-pathological ranges.
        """
        bz_abs = abs(bz) if bz is not None else 0.0
        south = max(0.0, -(bz or 0.0))
        vv = v or 0.0
        nn = max(0.0, n or 0.0)

        ae = (south * 60.0) + max(0.0, vv - 300.0) * 0.5 + max(0.0, nn - 5.0) * 10.0
        al = -0.6 * ae
        pc = (vv * math.sqrt(nn)) / 400.0 if vv > 0 and nn > 0 else 0.0

        # Clamp to reasonable ballpark ranges
        ae = max(0.0, min(ae, 1500.0))
        al = max(-1500.0, min(al, -10.0 if ae > 0 else 0.0))
        pc = max(0.0, min(pc, 10.0))
        return ae, al, pc

    mart_rows: list[dict[str, Any]] = []
    now = datetime.now(tz=UTC)
    for hour, samples in buckets.items():
        ae_vals: list[float] = []
        al_vals: list[float] = []
        pc_vals: list[float] = []
        for bz, v, n in samples:
            ae_p, al_p, pc_p = proxy_from_sample(bz, v, n)
            ae_vals.append(ae_p)
            al_vals.append(al_p)
            pc_vals.append(pc_p)

        if not ae_vals and not al_vals and not pc_vals:
            continue

        mart_rows.append(
            {
                "ts_utc": hour,
                "region": "global",
                "ae": max(ae_vals) if ae_vals else None,
                "al": min(al_vals) if al_vals else None,
                "au": max(ae_vals) * 0.5 if ae_vals else None,  # rough symmetry
                "pc": max(pc_vals) if pc_vals else None,
                "stations": json.dumps(["proxy:magnetosphere_pulse"]),
                "created_at": now,
            }
        )

    if mart_rows:
        inserted = await writer.upsert_many(
            "marts",
            "magnetometer_regional",
            mart_rows,
            ["ts_utc", "region"],
        )
        logger.info("Upserted %d proxy rows into marts.magnetometer_regional", inserted)
    else:
        logger.info("Proxy magnetometer produced no rows; nothing to upsert")