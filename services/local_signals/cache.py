import json
import os
from datetime import datetime, timedelta, timezone

from ..db import pg

TTL_MIN = int(os.getenv("LOCAL_SIGNALS_TTL_MINUTES", "60"))


def upsert_zip_payload(zip_code: str, payload: dict, asof: datetime | None = None) -> None:
    asof = asof or datetime.now(timezone.utc)
    expires_at = asof + timedelta(minutes=TTL_MIN)
    pg.execute(
        """
        insert into ext.local_signals_cache (zip, asof, payload, expires_at)
        values (%s, %s, %s, %s)
        on conflict (zip, asof)
        do update set payload = excluded.payload, expires_at = excluded.expires_at
        """,
        zip_code,
        asof,
        json.dumps(payload),
        expires_at,
    )


def latest_for_zip(zip_code: str) -> dict | None:
    row = pg.fetchrow(
        """
        select payload from ext.local_signals_cache
        where zip = %s and expires_at > now()
        order by asof desc limit 1
        """,
        zip_code,
    )
    if not row:
        return None
    payload = row["payload"]
    if isinstance(payload, str):
        return json.loads(payload)
    return payload
