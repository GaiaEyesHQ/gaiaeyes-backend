"""Range/cursor contract for canonical migraine history; no secondary store."""
from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.db import symptoms as symptoms_db


class HistoryChanged(Exception):
    pass


class HistoryCursor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    user_id: UUID
    start: AwareDatetime
    end: AwareDatetime
    as_of: AwareDatetime
    snapshot: str = Field(pattern=r"^[0-9a-f]{32}$")
    last_start: AwareDatetime
    last_id: UUID


async def read_history(conn, user_id: str, *, start: datetime, end: datetime,
                       limit: int = 50, cursor: str | None = None) -> dict:
    if (start.tzinfo is None or end.tzinfo is None or not start < end
            or end - start > timedelta(days=62) or not 1 <= limit <= 100):
        raise ValueError("Use an aware, increasing range of at most 62 days and limit 1–100")
    scope = UUID(user_id)
    start, end = start.astimezone(timezone.utc), end.astimezone(timezone.utc)
    previous = None
    if cursor is not None:
        try:
            if not cursor or len(cursor) > 2048:
                raise ValueError()
            raw = base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True)
            previous = HistoryCursor.model_validate_json(raw)
            if (previous.user_id != scope or previous.start != start or previous.end != end
                    or previous.last_start >= end):
                raise ValueError()
        except Exception as exc:
            raise ValueError("Invalid cursor for this account and range") from exc
    as_of = previous.as_of if previous else datetime.now(timezone.utc)
    page = await symptoms_db.fetch_migraine_episode_range(
        conn, str(scope), start=start, end=end, as_of=as_of, limit=limit,
        after_start=previous.last_start if previous else None,
        after_id=str(previous.last_id) if previous else None,
    )
    if previous and previous.snapshot != page["snapshot"]:
        raise HistoryChanged("Migraine history changed; refresh this month from the first page")
    rows = page["items"]
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = None
    if has_more:
        last = rows[-1]
        value = HistoryCursor(user_id=scope, start=start, end=end, as_of=as_of,
                              snapshot=page["snapshot"], last_start=last["started_at"], last_id=last["id"])
        next_cursor = base64.urlsafe_b64encode(value.model_dump_json().encode()).decode().rstrip("=")
    return {"items": rows, "start": start.isoformat(), "end": end.isoformat(),
            "as_of": as_of.isoformat(), "snapshot": page["snapshot"],
            "next_cursor": next_cursor, "complete": not has_more}
