import json
import os
import re
from datetime import datetime, timedelta, timezone

from ..db import pg


TTL_MIN = int(os.getenv("LOCAL_SIGNALS_TTL_MINUTES", "60"))

_HAS_EXPIRES_AT: bool | None = None

def _has_expires_at() -> bool:
    global _HAS_EXPIRES_AT
    if _HAS_EXPIRES_AT is not None:
        return _HAS_EXPIRES_AT
    try:
        row = pg.fetchrow(
            """
            select 1
            from information_schema.columns
            where table_schema = 'ext'
              and table_name = 'local_signals_cache'
              and column_name = 'expires_at'
            limit 1
            """
        )
        _HAS_EXPIRES_AT = bool(row)
    except Exception:
        _HAS_EXPIRES_AT = False
    return _HAS_EXPIRES_AT


def _norm_zip(z: str) -> str:
    """Normalize ZIP: strip non-alphanumerics and upper-case."""
    return re.sub(r"[^0-9A-Za-z]", "", (z or "")).upper()


def upsert_zip_payload(zip_code: str, payload: dict, asof: datetime | None = None) -> None:
    asof = asof or datetime.now(timezone.utc)
    z = _norm_zip(zip_code)

    if _has_expires_at():
        ttl = int(os.getenv("LOCAL_SIGNALS_TTL_MINUTES", str(TTL_MIN)))
        expires_at = asof + timedelta(minutes=ttl)
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
        return

    pg.execute(
        """
        insert into ext.local_signals_cache (zip, asof, payload)
        values (%s, %s, %s)
        on conflict (zip, asof)
        do update set payload = excluded.payload
        """,
        z,
        asof,
        json.dumps(payload),
    )


def latest_for_zip(zip_code: str) -> dict | None:
    z = _norm_zip(zip_code)
    if _has_expires_at():
        row = pg.fetchrow(
            """
            select payload from ext.local_signals_cache
            where zip = %s and expires_at > now()
            order by asof desc limit 1
            """,
            z,
        )
    else:
        row = pg.fetchrow(
            """
            select payload from ext.local_signals_cache
            where zip = %s
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
    Return the newest row for a ZIP with both asof and payload.
    Payload is JSON-decoded into a dict.
    """
    z = _norm_zip(zip_code)
    if _has_expires_at():
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
    else:
        row = pg.fetchrow(
            """
            select asof, payload
            from ext.local_signals_cache
            where zip = %s
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
    Convenience wrapper that mirrors upsert_zip_payload but takes explicit asof.
    ttl_minutes is respected when expires_at exists; otherwise ignored.
    """
    z = _norm_zip(zip_code)

    if _has_expires_at():
        ttl = TTL_MIN if ttl_minutes is None else int(ttl_minutes)
        expires_at = asof + timedelta(minutes=ttl)
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
        return

    pg.execute(
        """
        insert into ext.local_signals_cache (zip, asof, payload)
        values (%s, %s, %s)
        on conflict (zip, asof)
        do update set payload = excluded.payload
        """,
        z,
        asof,
        json.dumps(payload),
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
    if ref is None:
        # Wider fallback window for irregular poll cadence
        ref = get_previous_approx(
            zip_code,
            latest["asof"],
            min_hours=max(1, ref_hours - 6),
            max_hours=ref_hours + 12,
        )
    return latest, ref


def purge_old(retain_days: int = 14) -> None:
    """
    Delete old cache rows to keep the table lean.
    """
    pg.execute(
        "delete from ext.local_signals_cache where asof < now() - make_interval(days => %s)",
        retain_days,
    )


# ---- Back-compat aliases & explicit exports ---------------------------------

# Some code paths / older routers expect alternative symbol names.
# Keep these aliases so imports like
#   from services.local_signals.cache import latest_for_zip, upsert_zip_payload
# ...or...
#   from services.local_signals.cache import get_latest_for_zip, put_zip_payload
# keep working even if upstream modules were written against older names.

get_latest_for_zip = latest_for_zip
put_zip_payload = upsert_zip_payload

# Be explicit about the public API of this module.
__all__ = [
    "upsert_zip_payload",
    "latest_for_zip",
    "latest_row",
    "nearest_row_to",
    "upsert_snapshot",
    "get_previous_approx",
    "latest_and_ref",
    "purge_old",
    # Back-compat alias symbols:
    "get_latest_for_zip",
    "put_zip_payload",
]
