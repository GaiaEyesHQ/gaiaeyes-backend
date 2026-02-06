import json
import os
import re
from datetime import datetime, timedelta, timezone

from ..db import pg

TTL_MIN = int(os.getenv("LOCAL_SIGNALS_TTL_MINUTES", "60"))


def _norm_zip(z: str) -> str:
    """Normalize ZIP: strip non-alphanumerics and upper-case."""
    return re.sub(r"[^0-9A-Za-z]", "", (z or "")).upper()


def upsert_zip_payload(zip_code: str, payload: dict, asof: datetime | None = None) -> None:
    asof = asof or datetime.now(timezone.utc)
    expires_at = asof + timedelta(minutes=TTL_MIN)
    z = _norm_zip(zip_code)
    pg.execute(
        """
        insert into ext.local_signals_cache (zip, asof, payload, expires_at)
        values (%s, %s, %s, %s)
        on conflict (zip, asof)
        do update set payload = excluded.payload, expires_at = excluded.expires_at
        """,
        z,
        asof,
        json.dumps(payload),
        expires_at,
    )


def latest_for_zip(zip_code: str) -> dict | None:
    z = _norm_zip(zip_code)
    row = pg.fetchrow(
        """
        select payload from ext.local_signals_cache
        where zip = %s and expires_at > now()
        order by asof desc limit 1
        """,
        z,
    )
    if not row:
        return None
    payload = row["payload"]
    if isinstance(payload, str):
        return json.loads(payload)
    return payload


# New helper functions
def latest_row(zip_code: str) -> dict | None:
    """
    Return the newest non-expired row for a ZIP with both asof and payload.
    Payload is JSON-decoded into a dict.
    """
    z = _norm_zip(zip_code)
    row = pg.fetchrow(
        """
        select asof, payload
        from ext.local_signals_cache
        where zip = %s and expires_at > now()
        order by asof desc
        limit 1
        """,
        z,
    )
    if not row:
        return None
    payload = row["payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    return {"asof": row["asof"], "payload": payload}


def nearest_row_to(zip_code: str, target_asof: datetime, window_hours: int = 3) -> dict | None:
    """
    Return the cached row whose asof is closest to target_asof within +/- window_hours.

    This is useful to compute 24h deltas: call with target_asof = latest_asof - 24h.
    """
    z = _norm_zip(zip_code)
    lower = target_asof - timedelta(hours=window_hours)
    upper = target_asof + timedelta(hours=window_hours)
    row = pg.fetchrow(
        """
        select asof, payload
        from ext.local_signals_cache
        where zip = %s
          and asof between %s and %s
        order by abs(extract(epoch from (asof - %s))) asc
        limit 1
        """,
        z,
        lower,
        upper,
        target_asof,
    )
    if not row:
        return None
    payload = row["payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    return {"asof": row["asof"], "payload": payload}


def upsert_snapshot(zip_code: str, asof: datetime, payload: dict, ttl_minutes: int | None = None) -> None:
    """
    Convenience wrapper that mirrors upsert_zip_payload but takes explicit asof and optional ttl override.
    """
    ttl = int(os.getenv("LOCAL_SIGNALS_TTL_MINUTES", "60")) if ttl_minutes is None else int(ttl_minutes)
    expires_at = asof + timedelta(minutes=ttl)
    z = _norm_zip(zip_code)
    pg.execute(
        """
        insert into ext.local_signals_cache (zip, asof, payload, expires_at)
        values (%s, %s, %s, %s)
        on conflict (zip, asof)
        do update set payload = excluded.payload, expires_at = excluded.expires_at
        """,
        z,
        asof,
        json.dumps(payload),
        expires_at,
    )


def get_previous_approx(zip_code: str, asof: datetime, min_hours: int = 18, max_hours: int = 36) -> dict | None:
    """
    Return the snapshot closest to *asof* within (asof - max_hours .. asof - min_hours),
    or None if none exists. Payload is JSON-decoded into a dict.
    """
    z = _norm_zip(zip_code)
    row = pg.fetchrow(
        """
        select asof, payload
          from ext.local_signals_cache
         where zip = %s
           and asof >= %s - make_interval(hours => %s)
           and asof <= %s - make_interval(hours => %s)
         order by abs(extract(epoch from (asof - %s))) asc
         limit 1
        """,
        z,
        asof,
        max_hours,
        asof,
        min_hours,
        asof,
    )
    if not row:
        return None
    payload = row["payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    return {"asof": row["asof"], "payload": payload}


def latest_and_ref(zip_code: str, ref_hours: int = 24, window_hours: int = 3) -> tuple[dict | None, dict | None]:
    """
    Convenience: returns (latest_row, reference_row_near_latest_minus_ref_hours).
    Each element is a dict like {"asof": datetime, "payload": dict} or None.
    """
    latest = latest_row(zip_code)
    if not latest:
        return None, None
    target = latest["asof"] - timedelta(hours=ref_hours)
    ref = nearest_row_to(zip_code, target, window_hours=window_hours)
    return latest, ref


def purge_old(retain_days: int = 14) -> None:
    """
    Delete old cache rows to keep the table lean.
    """
    pg.execute(
        "delete from ext.local_signals_cache where asof < now() - make_interval(days => %s)",
        retain_days,
    )
