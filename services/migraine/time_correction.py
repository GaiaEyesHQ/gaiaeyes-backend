"""Explicit canonical time corrections; event occurrence timestamps keep their meaning."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, Field, model_validator

from services.migraine.episode_contract import ContractModel, EpisodeState, EpisodeTimestamp


class CorrectionTimestamp(EpisodeTimestamp):
    original_time: str = Field(min_length=16, max_length=32)
    timezone_name: str = Field(min_length=1, max_length=160)
    utc_offset_minutes: int = Field(ge=-840, le=840)
    timezone_source: Literal["user"] = "user"

    @model_validator(mode="after")
    def consistent_wall_time(self):
        wall = datetime.fromisoformat(self.original_time)
        if wall.tzinfo is not None:
            raise ValueError("original_time must be a local wall time without an offset")
        local = self.utc.astimezone(ZoneInfo(self.timezone_name))
        if local.replace(tzinfo=None) != wall or local.utcoffset() != timedelta(minutes=self.utc_offset_minutes):
            raise ValueError("Local time, timezone, offset and UTC must identify the same valid instant; choose the DST occurrence explicitly")
        self.original_time = wall.isoformat(timespec="seconds")
        return self


class TimeCorrectionIn(ContractModel):
    request_id: UUID
    expected_revision: int = Field(ge=0)
    expected_canonical_updated_at: AwareDatetime
    start: CorrectionTimestamp | None = None
    end: CorrectionTimestamp | None = None
    state: EpisodeState | None = None

    @model_validator(mode="after")
    def explicit_intent(self):
        if not self.model_fields_set & {"start", "end", "state"}:
            raise ValueError("Supply a start, end or state correction")
        for name in ("start", "state"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null; omit it to retain it")
        self.expected_canonical_updated_at = self.expected_canonical_updated_at.astimezone(UTC)
        return self

    def canonical_request(self) -> dict:
        values = self.model_dump(mode="json")
        return {name: values[name] for name in self.model_fields_set}
