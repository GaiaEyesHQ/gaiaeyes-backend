"""Dated public inputs for the existing draft wire; no network or generation.

The public writer's main path, not its unused JSON loaders, is the reference.
Keep the qualification ledger beside the packet: aggregate update time is not
an individual observation time. SQL callers supply only explicit projections.
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import math

from psycopg.rows import dict_row

from services.earthscope_writer_contract import FACT_KEYS, require, sha256, validate_facts

PUBLIC_SOURCES = {
    "space": ("canonical_public_mart", "marts.space_weather_daily"),
    "kp": ("canonical_public_mart", "marts.kp_obs"),
    "schumann": ("canonical_public_observation", "ext.schumann"),
    "kp_fallback": ("canonical_public_observation", "ext.space_weather"),
    "pulse": ("canonical_public_observation", "ext.magnetosphere_pulse"),
    "copy": ("canonical_public_copy", "content.earthscope_writer_public_history"),
}
SPACE_COLUMNS = ("day", "updated_at", "kp_max", "bz_min", "sw_speed_avg", "flares_count",
                 "cmes_count", "sw_speed_now_kms", "sw_speed_now", "now_ts", "kp_now")
COPY_COLUMNS = ("day", "updated_at", "title", "caption", "ig_caption", "fb_caption",
                "kp_max_24h", "bz_min", "solar_wind_kms")


def utc(value):
    try:
        dt = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc) if dt.utcoffset() is not None else None
    except (TypeError, ValueError, OverflowError):
        return None


def day_value(value):
    try:
        return value if type(value) is date else date.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None


def number(value, low=None, high=None, *, integer=False):
    if isinstance(value, bool) or value is None:
        return None
    try:
        n = float(value)
        if not math.isfinite(n) or (low is not None and n < low) or (high is not None and n > high):
            return None
        if integer:
            return int(n) if n.is_integer() else None
        return n
    except (ValueError, TypeError, OverflowError):
        return None


def normalized(value):
    if isinstance(value, datetime):
        stamp = utc(value)
        return stamp.isoformat() if stamp else value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return number(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: normalized(v) for k, v in value.items()}
    if isinstance(value, list):
        return [normalized(v) for v in value]
    return value


def projected(row, keys):
    return normalized({k: (row or {}).get(k) for k in keys})


def observed_status(value, day, now, *, hours=None):
    stamp = utc(value)
    if stamp is None:
        return "missing_observation_time"
    if stamp > now:
        return "future_observation"
    if stamp.date() != day:
        return "different_observation_day"
    if hours is not None and now - stamp > timedelta(hours=hours):
        return "stale_observation"
    return "current"


def prepare_public_packet(day, *, now, space, kp=None, schumann=(), kp_fallback=None,
                          pulse=None, public_copy=(), synthetic=False):
    """Return (unchanged-wire packet, public provenance/qualification ledger).

    ``synthetic`` is an explicit offline fixture choice; the deployed producer
    never passes it. Unknown optional inputs remain null, never numerical zero.
    """
    now = utc(now)
    require(now is not None and type(day) is date, "invalid_public_clock")
    require(space is not None, "public_facts_unavailable")
    source = projected(space, SPACE_COLUMNS)
    aggregate_time = utc(source["updated_at"])
    require(day_value(source["day"]) == day and aggregate_time is not None
            and aggregate_time.date() == day and aggregate_time <= now
            and (synthetic or now.date() == day), "facts_stale", 410)
    # A refreshed row cannot turn an explicitly wrong-day observation into today.
    if source["now_ts"] is not None:
        require(observed_status(source["now_ts"], day, now) == "current", "public_source_conflict", 410)

    facts = dict.fromkeys(FACT_KEYS)
    ledger = {"adapter": "earthscope_public_facts_v2", "synthetic": synthetic,
              "day": day.isoformat(), "qualified_at": now.isoformat(),
              "aggregate_updated_at": aggregate_time.isoformat(),
              "aggregate_time_is_observation_time": False, "sources": {}, "fields": {}, "omissions": []}
    manifest = []

    def record(key, projection, status):
        source_type, path = PUBLIC_SOURCES[key]
        sid = f"{key}-{day.isoformat()}"
        manifest.append({"source_id": sid, "source_type": source_type,
                         "source_path": path, "source_sha256": sha256(projection)})
        ledger["sources"][key] = {"source_id": sid, "source_path": path, "status": status,
                                  "projection": projection, "source_sha256": sha256(projection)}
        return sid

    record("space", source, "current_day_aggregate")

    def field(key, value, origin, meaning):
        facts[key] = value
        ledger["fields"][key] = {"source": origin, "meaning": meaning,
                                 "status": "available" if value is not None else "unknown"}

    for key, col, low, high, integer in (
        ("kp_max_24h", "kp_max", 0, 9, False), ("bz_min", "bz_min", None, None, False),
        ("flares_24h", "flares_count", 0, None, True), ("cmes_24h", "cmes_count", 0, None, True),
    ):
        field(key, number(source[col], low, high, integer=integer), "space." + col,
              "UTC calendar-day aggregate, not a rolling 24h window; CME count does not imply Earth direction")
    wind = number(source["sw_speed_now_kms"], 100, 2000)
    wind_col = "sw_speed_now_kms"
    if wind is None:
        wind, wind_col = number(source["sw_speed_now"], 100, 2000), "sw_speed_now"
    if wind is None or source["now_ts"] is None:
        wind, wind_col = number(source["sw_speed_avg"], 100, 2000), "sw_speed_avg"
    field("solar_wind_kms", wind, "space." + wind_col,
          "UTC-day mean" if wind_col == "sw_speed_avg" else "latest daily-mart value; now_ts is shared latest contributing observation, not wind-specific")

    kp_row = projected(kp, ("kp_time", "kp"))
    kp_status = observed_status(kp_row["kp_time"], day, now, hours=12) if kp else "missing"
    record("kp", kp_row if kp else None, kp_status)
    latest_kp = number(kp_row["kp"], 0, 9) if kp_status == "current" else None
    kp_origin = "kp.kp"
    # The API fallback starts with daily.kp_now, then ext.space_weather, then pulse.
    fallback_row = projected(kp_fallback, ("ts_utc", "kp_index"))
    fallback_status = observed_status(fallback_row["ts_utc"], day, now, hours=12) if kp_fallback else "missing"
    record("kp_fallback", fallback_row if kp_fallback else None, fallback_status)
    pulse_row = projected(pulse, ("ts", "kp_latest"))
    pulse_status = observed_status(pulse_row["ts"], day, now, hours=12) if pulse else "missing"
    record("pulse", pulse_row if pulse else None, pulse_status)
    if latest_kp is None:
        daily_kp = number(source["kp_now"], 0, 9)
        if daily_kp is not None and observed_status(source["now_ts"], day, now, hours=12) == "current":
            latest_kp, kp_origin = daily_kp, "space.kp_now"
        elif fallback_status == "current" and number(fallback_row["kp_index"], 0, 9) is not None:
            latest_kp, kp_origin = number(fallback_row["kp_index"], 0, 9), "kp_fallback.kp_index"
        elif pulse_status == "current":
            latest_kp, kp_origin = number(pulse_row["kp_latest"], 0, 9), "pulse.kp_latest"
    field("kp_now", latest_kp, kp_origin, "same UTC-day observation within 12 hours; daily fallback has only a shared observation timestamp")

    sr_rows = [projected(r, ("station_id", "day", "f0_avg_hz", "last_fundamental_ts")) for r in schumann]
    sr_rows.sort(key=lambda r: (str(r["day"]), str(r["station_id"])))
    selected, rejected = [], []
    for row in sr_rows:
        status = observed_status(row["last_fundamental_ts"], day, now)
        if day_value(row["day"]) != day:
            status = "different_aggregate_day"
        if status == "current" and number(row["f0_avg_hz"], 0) is not None:
            selected.append(row)
        else:
            rejected.append({"station_id": row["station_id"], "status": status})
    record("schumann", sr_rows, "current" if selected else "missing_or_stale")
    ledger["sources"]["schumann"]["rejected"] = rejected
    ledger["sources"]["schumann"]["derivation"] = (
        "ext.schumann fundamental_hz: finite nonnegative sample mean and maximum actual ts_utc; "
        "UTC [day, day+1) bounds; future latest sample disqualifies the station")
    groups = [[number(r["f0_avg_hz"]) for r in selected if station in str(r["station_id"]).lower()]
              for station in ("tomsk", "cumiana")]
    values = [round(sum(g) / len(g), 2) for g in groups if g]
    if not values:
        values = [number(r["f0_avg_hz"]) for r in selected]
    sr = round(sum(values) / len(values), 2) if values else None
    field("schumann_value_hz", sr, "schumann.f0_avg_hz", "mean of available same-day station-group means; station measurement, not global personal exposure")

    # Same active Kp threshold as legacy, without turning an observed maximum into a forecast.
    ref = facts["kp_max_24h"] if facts["kp_max_24h"] is not None else latest_kp
    aurora = None if ref is None or ref < 5 else ("G3+ aurora possible" if ref >= 7 else "G2 aurora possible" if ref >= 6 else "G1 aurora possible")
    field("aurora_headline", aurora, "derived:kp", "legacy Kp band; no location-specific visibility or forecast evidence")
    field("aurora_window", "Observed UTC day; Kp-based context, not a forecast" if aurora else None,
          "derived:kp", "observed context, not Next 24h/72h")

    # Only the filtered view may supply copy: never grant the preparer the mixed public/member table.
    rows = [projected(r, COPY_COLUMNS) for r in public_copy]
    rows.sort(key=lambda r: (str(r["day"]), str(r["updated_at"]), str(r["caption"])), reverse=True)
    copy_id = record("copy", rows, "historical_context_only")
    recent, history, seen = [], [], set()
    for row in rows:
        old_day, updated = day_value(row["day"]), utc(row["updated_at"])
        if old_day is None or not day - timedelta(days=21) <= old_day < day or updated is None or updated > now:
            ledger["omissions"].append("public_copy_invalid_date_or_update")
            continue
        if old_day in seen:
            ledger["omissions"].append("duplicate_public_copy_day")
            continue
        seen.add(old_day)
        # Five recent caption sets plus titles across the bounded 21-day window.
        for key in (("caption", "ig_caption", "fb_caption", "title") if len(seen) <= 5 else ("title",)):
            value = row[key]
            if isinstance(value, str) and value.strip():
                recent.append({"source_id": f"{copy_id}:{old_day}:{key}", "text": value.strip()[:2048]})
        # Carryover is bounded to the three preceding calendar days, not three arbitrary old posts.
        if day - old_day <= timedelta(days=3):
            history.append({"source_id": copy_id, "day": old_day.isoformat(),
                            "source_updated_at": updated.isoformat(), "historical_only": True,
                            "kp_max_24h": number(row["kp_max_24h"], 0, 9),
                            "bz_min": number(row["bz_min"]),
                            "solar_wind_kms": number(row["solar_wind_kms"], 100, 2000)})
    facts["recent_signal_history"] = history
    for key in ("quakes_count", "severe_summary"):
        field(key, None, "none", "no active loader in legacy main; unavailable is not zero/calm")
    missing = [k for k in ("kp_max_24h", "bz_min", "solar_wind_kms") if facts[k] is None]
    sample = "missing_data" if missing else "active" if facts["kp_max_24h"] >= 4 or facts["bz_min"] <= -6 or wind >= 500 else "quiet"
    packet = {"schema_version": "1.0", "job_id": "earthscope-" + day.strftime("%Y%m%d"),
              "sample_kind": sample, "example_status": "synthetic_public_facts" if synthetic else "production_observed_input",
              "day": day.isoformat(), "facts_as_of": aggregate_time.isoformat(),
              "geographic_scope": (
                  "Global public space context; local weather and quake context unavailable. "
                  "Kp maximum/Bz minimum/event counts are UTC calendar-day aggregates, not rolling 24h. "
                  f"facts_as_of is aggregate update time; shared latest observation time={source['now_ts'] or 'unknown'}. "
                  f"Solar wind uses {wind_col}; current Kp source={kp_origin if latest_kp is not None else 'unknown'}. "
                  f"Kp observation times: mart={kp_row['kp_time'] or 'unknown'}, "
                  f"raw fallback={fallback_row['ts_utc'] or 'unknown'}, pulse={pulse_row['ts'] or 'unknown'}; "
                  "only same-day values within 12h qualify for the now field. "
                  f"Schumann uses same-day station means with dated samples ({len(selected)} rows); not global exposure. "
                  "Null means unavailable, stale, invalid or intentionally omitted, never quiet. "
                  "Aurora is observed Kp-based context, not a local forecast. Recent signals/copy are historical only; "
                  "stored public copy is not proof of publication or scientific truth."
              ), "source_manifest": manifest, "facts": facts, "recent_public_copy": recent}
    ledger["missing_core_fields"] = missing
    ledger["facts_sha256"] = sha256(packet)
    validate_facts(packet, "synthetic_review_fixture" if synthetic else "dated_production_facts", now)
    return packet, ledger


async def collect_public_inputs(conn, day):
    """Bounded read-only projections; a privilege/schema error aborts preparation."""
    async def rows(sql, args=()):
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(sql, args)
            return await cur.fetchall()
    space = await rows("select " + ",".join(SPACE_COLUMNS) + " from marts.space_weather_daily where day=%s", (day,))
    kp = await rows("select kp_time,kp from marts.kp_obs order by kp_time desc limit 1")
    # Preserve the existing mart view/consumers. Its date(ts_utc) depends on the
    # session zone and it has no observation timestamp. Aggregate the same raw
    # public measurements with explicit UTC bounds, retaining actual sample time.
    start = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
    sr = await rows("""select station_id,(ts_utc at time zone 'UTC')::date as day,
                              avg(value_num) as f0_avg_hz,max(ts_utc) as last_fundamental_ts
                       from ext.schumann
                       where ts_utc >= %s and ts_utc < %s and channel='fundamental_hz'
                         and value_num >= 0 and value_num < 'Infinity'::numeric
                       group by station_id,(ts_utc at time zone 'UTC')::date
                       order by station_id limit 32""", (start, start+timedelta(days=1)))
    fallback = await rows("select ts_utc,kp_index from ext.space_weather where kp_index is not null order by ts_utc desc limit 1")
    pulse = await rows("select ts,kp_latest from ext.magnetosphere_pulse order by ts desc limit 1")
    copy = await rows("select " + ",".join(COPY_COLUMNS) + """ from content.earthscope_writer_public_history
                       where day < %s and day >= %s order by day desc,updated_at desc limit 21""", (day, day-timedelta(days=21)))
    return {"space": space[0] if space else None, "kp": kp[0] if kp else None, "schumann": sr,
            "kp_fallback": fallback[0] if fallback else None, "pulse": pulse[0] if pulse else None, "public_copy": copy}
