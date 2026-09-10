"""Provider-neutral migraine episode detail contract.

This module validates the shared shape used by future follow-up, report, and
import work. It does not persist records or replace the existing symptom event
and episode tables.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator


ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
LongText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
EpisodeState = Literal["new", "ongoing", "improving", "worse", "resolved"]
TimezoneSource = Literal["user", "device", "provider", "imported_offset", "unknown"]
DetailSource = Literal["user_reported", "device", "health_record", "environmental_service", "import"]
ReliefLevel = Literal["none", "a_little", "some", "a_lot", "complete", "unknown"]
SourceType = Literal["manual", "siri", "follow_up", "healthkit", "import"]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EpisodeTimestamp(ContractModel):
    utc: AwareDatetime
    original_time: ShortText | None = None
    timezone_name: ShortText | None = None
    utc_offset_minutes: int | None = Field(default=None, ge=-840, le=840)
    timezone_source: TimezoneSource

    @field_validator("utc")
    @classmethod
    def normalize_utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)

    @field_validator("timezone_name")
    @classmethod
    def validate_timezone_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone_name must be a valid IANA timezone") from exc
        return value


class EarlySign(ContractModel):
    label: ShortText
    code: ShortText | None = None
    reported_at: EpisodeTimestamp | None = None
    notes: LongText | None = None


class EpisodeContext(ContractModel):
    kind: Literal["exposure", "context"]
    label: ShortText
    code: ShortText | None = None
    observed_at: EpisodeTimestamp | None = None
    source: DetailSource
    notes: LongText | None = None


class MedicineTaken(ContractModel):
    name: ShortText
    taken_at: EpisodeTimestamp
    dose_amount: Decimal | None = Field(default=None, gt=0)
    dose_unit: ShortText | None = None
    reported_relief: ReliefLevel | None = None
    relief_reported_at: EpisodeTimestamp | None = None
    notes: LongText | None = None

    @model_validator(mode="after")
    def require_complete_optional_dose(self) -> "MedicineTaken":
        if (self.dose_amount is None) != (self.dose_unit is None):
            raise ValueError("dose_amount and dose_unit must be supplied together")
        if self.relief_reported_at is not None and self.reported_relief is None:
            raise ValueError("relief_reported_at requires reported_relief")
        return self


class EpisodeProvenance(ContractModel):
    source_type: SourceType
    source_platform: ShortText
    source_provider: ShortText | None = None
    external_event_id: ShortText | None = None
    source_file_hash: ShortText | None = None
    import_run_id: UUID | None = None
    raw_row_ref: ShortText | None = None
    mapping_version: ShortText | None = None

    @field_validator("source_file_hash")
    @classmethod
    def validate_source_file_hash(cls, value: str | None) -> str | None:
        if value is not None and re.fullmatch(r"[0-9a-fA-F]{64}", value) is None:
            raise ValueError("source_file_hash must be a 64-character SHA-256 hex digest")
        return value.lower() if value is not None else None

    @model_validator(mode="after")
    def require_import_provenance(self) -> "EpisodeProvenance":
        if self.source_type != "import":
            return self
        required = {
            "source_provider": self.source_provider,
            "external_event_id": self.external_event_id,
            "source_file_hash": self.source_file_hash,
            "import_run_id": self.import_run_id,
            "raw_row_ref": self.raw_row_ref,
            "mapping_version": self.mapping_version,
        }
        missing = [name for name, value in required.items() if value is None]
        if missing:
            raise ValueError(f"import provenance missing: {', '.join(missing)}")
        return self


class EpisodeLifecycle(ContractModel):
    revision: int = Field(default=1, ge=1)
    created_at: AwareDatetime
    updated_at: AwareDatetime
    deleted_at: AwareDatetime | None = None
    deletion_scope: Literal["episode", "import_run", "account"] | None = None

    @field_validator("created_at", "updated_at", "deleted_at")
    @classmethod
    def normalize_lifecycle_timestamp(cls, value: datetime | None) -> datetime | None:
        return value.astimezone(UTC) if value is not None else None

    @model_validator(mode="after")
    def validate_order_and_deletion(self) -> "EpisodeLifecycle":
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot be earlier than created_at")
        if (self.deleted_at is None) != (self.deletion_scope is None):
            raise ValueError("deleted_at and deletion_scope must be supplied together")
        if self.deleted_at is not None and self.deleted_at < self.created_at:
            raise ValueError("deleted_at cannot be earlier than created_at")
        return self


class MigraineEpisode(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    episode_id: UUID
    symptom_event_id: UUID | None = None
    symptom_code: Literal["MIGRAINE"] = "MIGRAINE"
    state: EpisodeState
    start: EpisodeTimestamp
    end: EpisodeTimestamp | None = None
    severity: int | None = Field(default=None, ge=0, le=10)
    early_signs: list[EarlySign] = Field(default_factory=list)
    contexts: list[EpisodeContext] = Field(default_factory=list)
    medicines: list[MedicineTaken] = Field(default_factory=list)
    notes: LongText | None = None
    provenance: EpisodeProvenance
    lifecycle: EpisodeLifecycle

    @model_validator(mode="after")
    def validate_episode(self) -> "MigraineEpisode":
        if self.end is not None and self.end.utc < self.start.utc:
            raise ValueError("end cannot be earlier than start")
        if self.state != "resolved" and self.end is not None:
            raise ValueError("only resolved episodes may have an end timestamp")
        if self.provenance.source_type != "import" and self.symptom_event_id is None:
            raise ValueError("live episodes require symptom_event_id linkage")
        return self
