from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import logging
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, conint

from bots.definitions.load_definition_base import load_definition_base
from bots.gauges.gauge_scorer import _SYMPTOM_GAUGE_EFFECTS, fetch_user_tags
from bots.patterns.pattern_engine_job import OUTCOME_SYMPTOM_CODES
from services.personalization.health_context import canonicalize_tag_keys
from services.patterns.personal_relevance import (
    compute_personal_relevance,
    fetch_best_pattern_rows,
    fetch_recent_outcome_summary,
    pattern_anchor_statement,
    resolve_current_drivers,
)
from ..db import get_db
from ..db import symptoms as symptoms_db

router = APIRouter(prefix="/symptoms", tags=["symptoms"])

logger = logging.getLogger(__name__)

DEFAULT_TIMEZONE = os.getenv("GAIA_TIMEZONE", "America/Chicago")
try:
    LOCAL_TZ = ZoneInfo(DEFAULT_TIMEZONE)
except Exception:
    LOCAL_TZ = ZoneInfo("America/Chicago")


_ERR_LOAD_CODES = "Failed to load symptom codes"
_ERR_RECORD_EVENT = "Failed to record symptom event"
_ERR_LOAD_TODAY = "Failed to load today's symptoms"
_ERR_LOAD_DAILY = "Failed to load daily symptom summary"
_ERR_LOAD_DIAG = "Failed to load diagnostic summary"
_ERR_LOAD_CURRENT = "Failed to load current symptoms"
_ERR_LOAD_TIMELINE = "Failed to load current symptom timeline"
_ERR_RECORD_CURRENT_UPDATE = "Failed to update current symptom state"
_ERR_DELETE_CURRENT = "Failed to delete current symptom"

DEFAULT_CURRENT_WINDOW_HOURS = 12
MAX_CURRENT_WINDOW_HOURS = 48
DEFAULT_CURRENT_TIMELINE_DAYS = 7
MAX_CURRENT_TIMELINE_DAYS = 90

_SYMPTOM_OUTCOME_KEYS: Dict[str, set[str]] = {}
for _outcome_key, _symptom_codes in OUTCOME_SYMPTOM_CODES.items():
    for _code in _symptom_codes:
        _SYMPTOM_OUTCOME_KEYS.setdefault(_code.strip().replace("-", "_").replace(" ", "_").upper(), set()).add(_outcome_key)


def _require_user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id missing from request context")
    return user_id


class SymptomEventIn(BaseModel):
    symptom_code: str = Field(..., min_length=1)
    ts_utc: Optional[datetime] = None
    severity: Optional[conint(ge=0, le=10)] = None
    free_text: Optional[str] = None
    tags: Optional[List[str]] = None


class SymptomEnvelope(BaseModel):
    ok: bool = True
    error: Optional[str] = None
    friendly_error: Optional[str] = None


class SymptomEventData(BaseModel):
    id: str
    ts_utc: str


class SymptomEventResponse(SymptomEnvelope):
    data: Optional[SymptomEventData] = None


class SymptomTodayOut(BaseModel):
    symptom_code: str
    ts_utc: str
    severity: Optional[int] = None
    free_text: Optional[str] = None


class SymptomTodayResponse(SymptomEnvelope):
    data: List[SymptomTodayOut] = Field(default_factory=list)


class SymptomDailyRow(BaseModel):
    day: str
    symptom_code: str
    events: int
    mean_severity: Optional[float] = None
    last_ts: Optional[str] = None


class SymptomDailyResponse(SymptomEnvelope):
    data: List[SymptomDailyRow] = Field(default_factory=list)


class SymptomDiagRow(BaseModel):
    symptom_code: str
    events: int
    last_ts: Optional[str] = None


class SymptomDiagResponse(SymptomEnvelope):
    data: List[SymptomDiagRow] = Field(default_factory=list)


class SymptomCodeRow(BaseModel):
    symptom_code: str
    label: str
    description: Optional[str] = None
    is_active: bool = True


class CurrentSymptomUpdateIn(BaseModel):
    state: Optional[str] = None
    severity: Optional[conint(ge=0, le=10)] = None
    note_text: Optional[str] = None
    ts_utc: Optional[datetime] = None


class CurrentSymptomDriverOut(BaseModel):
    key: str
    label: str
    severity: Optional[str] = None
    state: Optional[str] = None
    display: Optional[str] = None
    relation: Optional[str] = None
    related_symptoms: List[str] = Field(default_factory=list)
    confidence: Optional[str] = None
    pattern_hint: Optional[str] = None


class CurrentSymptomPatternOut(BaseModel):
    id: str
    signal_key: str
    signal: str
    outcome_key: str
    outcome: str
    confidence: Optional[str] = None
    text: Optional[str] = None


class CurrentSymptomItemOut(BaseModel):
    id: str
    symptom_code: str
    label: str
    severity: Optional[int] = None
    original_severity: Optional[int] = None
    logged_at: str
    last_interaction_at: Optional[str] = None
    current_state: str
    note_preview: Optional[str] = None
    note_count: int = 0
    likely_drivers: List[CurrentSymptomDriverOut] = Field(default_factory=list)
    pattern_hint: Optional[CurrentSymptomPatternOut] = None
    gauge_keys: List[str] = Field(default_factory=list)
    current_context_badge: Optional[str] = None


class CurrentSymptomSummaryOut(BaseModel):
    active_count: int = 0
    new_count: int = 0
    ongoing_count: int = 0
    improving_count: int = 0
    last_updated_at: Optional[str] = None
    follow_up_available: bool = False


class CurrentSymptomFollowUpOut(BaseModel):
    notifications_enabled: bool = False
    enabled: bool = False
    notification_family_enabled: bool = False
    cadence: str = "balanced"
    states: List[str] = Field(default_factory=list)
    symptom_codes: List[str] = Field(default_factory=list)


class CurrentSymptomsSnapshotOut(BaseModel):
    generated_at: str
    window_hours: int
    summary: CurrentSymptomSummaryOut
    items: List[CurrentSymptomItemOut] = Field(default_factory=list)
    contributing_drivers: List[CurrentSymptomDriverOut] = Field(default_factory=list)
    pattern_context: List[CurrentSymptomPatternOut] = Field(default_factory=list)
    follow_up_settings: CurrentSymptomFollowUpOut


class CurrentSymptomsResponse(SymptomEnvelope):
    data: Optional[CurrentSymptomsSnapshotOut] = None


class CurrentSymptomItemResponse(SymptomEnvelope):
    data: Optional[CurrentSymptomItemOut] = None


class CurrentSymptomDeleteOut(BaseModel):
    episode_id: str
    symptom_code: str
    deleted_at: Optional[str] = None


class CurrentSymptomDeleteResponse(SymptomEnvelope):
    data: Optional[CurrentSymptomDeleteOut] = None


class CurrentSymptomTimelineEntryOut(BaseModel):
    id: str
    episode_id: str
    symptom_code: str
    label: str
    update_kind: str
    state: Optional[str] = None
    severity: Optional[int] = None
    note_text: Optional[str] = None
    occurred_at: str


class CurrentSymptomTimelineResponse(SymptomEnvelope):
    data: List[CurrentSymptomTimelineEntryOut] = Field(default_factory=list)


def _normalize_symptom_code(value: str) -> str:
    return value.strip().replace(" ", "_").replace("-", "_").upper()


def _storage_symptom_code(value: str) -> str:
    return value.strip().replace(" ", "_").replace("-", "_").lower()


def _normalize_current_state(value: Optional[str]) -> str:
    token = str(value or "new").strip().lower()
    return token if token in {"new", "ongoing", "improving", "resolved"} else "new"


def _trimmed_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


def _label_from_code(value: Optional[str]) -> str:
    token = _normalize_symptom_code(value or "OTHER")
    return token.replace("_", " ").title()


def _gauge_keys_for_symptom(symptom_code: str) -> List[str]:
    effects = _SYMPTOM_GAUGE_EFFECTS.get(_normalize_symptom_code(symptom_code)) or {}
    return sorted(key for key in effects.keys())


def _outcome_keys_for_symptom(symptom_code: str) -> set[str]:
    return set(_SYMPTOM_OUTCOME_KEYS.get(_normalize_symptom_code(symptom_code), set()))


def _serialize_pattern_ref(ref: Dict[str, Any]) -> CurrentSymptomPatternOut:
    return CurrentSymptomPatternOut(
        id=str(ref.get("id") or ""),
        signal_key=str(ref.get("signal_key") or ""),
        signal=str(ref.get("signal") or _label_from_code(str(ref.get("signal_key") or ""))),
        outcome_key=str(ref.get("outcome_key") or ""),
        outcome=str(ref.get("outcome") or _label_from_code(str(ref.get("outcome_key") or ""))),
        confidence=ref.get("confidence"),
        text=pattern_anchor_statement(ref, variant="short"),
    )


def _serialize_driver(
    driver: Dict[str, Any],
    *,
    related_symptoms: Optional[List[str]] = None,
    best_ref: Optional[Dict[str, Any]] = None,
) -> CurrentSymptomDriverOut:
    relation = pattern_anchor_statement(best_ref, variant="short") if best_ref else "Currently active around your recent symptom window."
    return CurrentSymptomDriverOut(
        key=str(driver.get("key") or ""),
        label=str(driver.get("label") or _label_from_code(str(driver.get("key") or "Driver"))),
        severity=driver.get("severity"),
        state=driver.get("state"),
        display=driver.get("display"),
        relation=relation,
        related_symptoms=related_symptoms or [],
        confidence=best_ref.get("confidence") if best_ref else None,
        pattern_hint=pattern_anchor_statement(best_ref, variant="short") if best_ref else None,
    )


def _matching_pattern_refs(
    symptom_code: str,
    ranked_drivers: List[Dict[str, Any]],
) -> List[tuple[float, Dict[str, Any], Dict[str, Any]]]:
    outcome_keys = _outcome_keys_for_symptom(symptom_code)
    if not outcome_keys:
        return []

    matches: List[tuple[float, Dict[str, Any], Dict[str, Any]]] = []
    for driver in ranked_drivers:
        refs = driver.get("active_pattern_refs") or []
        if not isinstance(refs, list):
            continue
        for ref in refs:
            if not isinstance(ref, dict):
                continue
            if str(ref.get("outcome_key") or "") not in outcome_keys:
                continue
            matches.append((float(ref.get("relevance_score") or 0.0), driver, ref))

    matches.sort(
        key=lambda item: (
            -item[0],
            str(item[1].get("key") or ""),
            str(item[2].get("id") or ""),
        )
    )
    return matches


def _current_context_badge(
    *,
    state: str,
    likely_driver_count: int,
    pattern_hint: Optional[CurrentSymptomPatternOut],
) -> Optional[str]:
    if state == "new":
        return "Recently logged"
    if pattern_hint is not None:
        return "Pattern match"
    if likely_driver_count > 0:
        return "Signals active now"
    if state == "improving":
        return "Trending better"
    return None


async def _build_current_symptoms_payload(
    conn,
    user_id: str,
    *,
    window_hours: int,
) -> CurrentSymptomsSnapshotOut:
    try:
        rows = await symptoms_db.fetch_current_symptom_items(conn, user_id, window_hours=window_hours)
    except Exception:
        rows = await symptoms_db.fetch_current_symptom_items_fallback(conn, user_id, window_hours=window_hours)

    now_day = datetime.now(timezone.utc).date()

    try:
        definition, _ = load_definition_base()
    except Exception:
        definition = {}

    try:
        raw_tags = await asyncio.to_thread(fetch_user_tags, user_id)
        user_tags = set(canonicalize_tag_keys(raw_tags))
    except Exception:
        user_tags = set()

    pattern_rows = await fetch_best_pattern_rows(conn, user_id)
    recent_outcomes = await fetch_recent_outcome_summary(conn, user_id, now_day)
    current_drivers, _, _ = await resolve_current_drivers(user_id=user_id, day=now_day, definition=definition)
    personal_relevance = compute_personal_relevance(
        day=now_day,
        drivers=current_drivers,
        pattern_rows=pattern_rows,
        user_tags=user_tags,
        recent_outcomes=recent_outcomes,
    )
    ranked_drivers = [dict(item) for item in personal_relevance.get("ranked_drivers") or [] if isinstance(item, dict)]
    follow_up = await symptoms_db.fetch_symptom_follow_up_settings(conn, user_id)

    items: List[CurrentSymptomItemOut] = []
    pattern_context: List[CurrentSymptomPatternOut] = []
    seen_pattern_ids: set[str] = set()

    for row in rows:
        matches = _matching_pattern_refs(str(row.get("symptom_code") or ""), ranked_drivers)
        seen_driver_keys: set[str] = set()
        likely_drivers: List[CurrentSymptomDriverOut] = []
        for _, driver, ref in matches:
            driver_key = str(driver.get("key") or "")
            if not driver_key or driver_key in seen_driver_keys:
                continue
            likely_drivers.append(_serialize_driver(driver, related_symptoms=[str(row.get("label") or "")], best_ref=ref))
            seen_driver_keys.add(driver_key)
            if len(likely_drivers) >= 3:
                break

        pattern_hint = _serialize_pattern_ref(matches[0][2]) if matches else None
        if pattern_hint and pattern_hint.id and pattern_hint.id not in seen_pattern_ids:
            pattern_context.append(pattern_hint)
            seen_pattern_ids.add(pattern_hint.id)

        state = _normalize_current_state(row.get("current_state"))
        item = CurrentSymptomItemOut(
            id=str(row.get("id") or ""),
            symptom_code=_normalize_symptom_code(str(row.get("symptom_code") or "")),
            label=str(row.get("label") or _label_from_code(str(row.get("symptom_code") or ""))),
            severity=row.get("current_severity"),
            original_severity=row.get("original_severity"),
            logged_at=str(row.get("started_at") or ""),
            last_interaction_at=row.get("last_interaction_at") or row.get("state_updated_at"),
            current_state=state,
            note_preview=_trimmed_text(row.get("latest_note_text")),
            note_count=int(row.get("note_count") or 0),
            likely_drivers=likely_drivers,
            pattern_hint=pattern_hint,
            gauge_keys=_gauge_keys_for_symptom(str(row.get("symptom_code") or "")),
            current_context_badge=_current_context_badge(
                state=state,
                likely_driver_count=len(likely_drivers),
                pattern_hint=pattern_hint,
            ),
        )
        items.append(item)

    contributing_drivers: List[CurrentSymptomDriverOut] = []
    if items:
        for driver in ranked_drivers[:4]:
            related_symptoms: List[str] = []
            best_ref: Optional[Dict[str, Any]] = None
            for item in items:
                for _, matched_driver, ref in _matching_pattern_refs(item.symptom_code, [driver]):
                    if str(matched_driver.get("key") or "") != str(driver.get("key") or ""):
                        continue
                    related_symptoms.append(item.label)
                    if best_ref is None:
                        best_ref = ref
            related_symptoms = list(dict.fromkeys([label for label in related_symptoms if label]))
            contributing_drivers.append(
                _serialize_driver(
                    driver,
                    related_symptoms=related_symptoms,
                    best_ref=best_ref,
                )
            )

    last_updated_at = max(
        [item.last_interaction_at or item.logged_at for item in items if (item.last_interaction_at or item.logged_at)],
        default=None,
    )
    summary = CurrentSymptomSummaryOut(
        active_count=len(items),
        new_count=sum(1 for item in items if item.current_state == "new"),
        ongoing_count=sum(1 for item in items if item.current_state == "ongoing"),
        improving_count=sum(1 for item in items if item.current_state == "improving"),
        last_updated_at=last_updated_at,
        follow_up_available=bool(items) and bool(follow_up.get("enabled") or follow_up.get("notification_family_enabled")),
    )

    return CurrentSymptomsSnapshotOut(
        generated_at=datetime.now(timezone.utc).isoformat(),
        window_hours=window_hours,
        summary=summary,
        items=items,
        contributing_drivers=contributing_drivers,
        pattern_context=pattern_context[:3],
        follow_up_settings=CurrentSymptomFollowUpOut(
            notifications_enabled=bool(follow_up.get("notifications_enabled")),
            enabled=bool(follow_up.get("enabled")),
            notification_family_enabled=bool(follow_up.get("notification_family_enabled")),
            cadence=str(follow_up.get("cadence") or "balanced"),
            states=[_normalize_current_state(value) for value in (follow_up.get("states") or [])],
            symptom_codes=[_normalize_symptom_code(value) for value in (follow_up.get("symptom_codes") or []) if value],
        ),
    )


def _build_current_symptom_item_out(row: Dict[str, Any]) -> CurrentSymptomItemOut:
    state = _normalize_current_state(row.get("current_state"))
    pattern_hint = None
    return CurrentSymptomItemOut(
        id=str(row.get("id") or ""),
        symptom_code=_normalize_symptom_code(str(row.get("symptom_code") or "")),
        label=str(row.get("label") or _label_from_code(str(row.get("symptom_code") or ""))),
        severity=row.get("current_severity"),
        original_severity=row.get("original_severity"),
        logged_at=str(row.get("started_at") or ""),
        last_interaction_at=row.get("last_interaction_at") or row.get("state_updated_at"),
        current_state=state,
        note_preview=_trimmed_text(row.get("latest_note_text")),
        note_count=int(row.get("note_count") or (1 if _trimmed_text(row.get("latest_note_text")) else 0)),
        likely_drivers=[],
        pattern_hint=pattern_hint,
        gauge_keys=_gauge_keys_for_symptom(str(row.get("symptom_code") or "")),
        current_context_badge="Resolved" if state == "resolved" else _current_context_badge(state=state, likely_driver_count=0, pattern_hint=pattern_hint),
    )


async def _commit_if_supported(conn) -> None:
    commit = getattr(conn, "commit", None)
    if callable(commit):
        await commit()


async def _refresh_gauges_for_symptom(user_id: str, ts_utc: str) -> None:
    try:
        event_ts = datetime.fromisoformat(ts_utc.replace("Z", "+00:00"))
        if event_ts.tzinfo is None:
            event_ts = event_ts.replace(tzinfo=LOCAL_TZ)
        event_day = event_ts.astimezone(LOCAL_TZ).date()
    except Exception:
        event_day = datetime.now(LOCAL_TZ).date()

    def _run() -> None:
        from bots.gauges.gauge_scorer import score_user_day

        score_user_day(user_id, event_day, force=True)

    try:
        await asyncio.to_thread(_run)
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.warning(
            "symptom gauge refresh failed user=%s day=%s err=%s",
            user_id,
            event_day,
            exc,
        )


@router.post("", response_model=SymptomEventResponse)
async def create_symptom_event(
    payload: SymptomEventIn,
    request: Request,
    conn=Depends(get_db),
    strict: bool = Query(
        False,
        description="If true, reject unknown symptom codes instead of mapping them to OTHER",
    ),
):
    user_id = _require_user_id(request)
    normalized_code = _normalize_symptom_code(payload.symptom_code)
    effective_severity = payload.severity if payload.severity is not None else 5

    try:
        code_rows = await symptoms_db.fetch_symptom_codes(conn)
    except Exception as exc:  # pragma: no cover - exercised via tests
        logger.exception("failed to load codes for symptom post", extra={"user_id": user_id})
        return JSONResponse(
            status_code=200,
            content={
                "ok": False,
                "data": None,
                "error": _error_text(exc),
                "friendly_error": _ERR_LOAD_CODES,
            },
        )

    lookup = {
        _normalize_symptom_code(row["symptom_code"]): row
        for row in code_rows
    }

    if not lookup:
        raise HTTPException(status_code=500, detail="No symptom codes configured")

    other_key = "OTHER" if "OTHER" in lookup else None

    if normalized_code not in lookup:
        if strict:
            valid_codes = sorted(lookup.keys())
            return JSONResponse(
                status_code=400,
                content={
                    "ok": False,
                    "data": None,
                    "error": "unknown symptom_code",
                    "valid": valid_codes,
                },
            )
        if other_key is None:
            raise HTTPException(status_code=500, detail="OTHER symptom code missing from catalog")
        normalized_code = other_key

    matched_row = lookup.get(normalized_code)
    if matched_row is None:
        raise HTTPException(status_code=500, detail="Resolved symptom code missing from catalog")
    canonical_code = _storage_symptom_code(str(matched_row["symptom_code"]))

    logger.info(
        "symptom_event",
        extra={
            "user_id": user_id,
            "symptom_code": canonical_code,
            "symptom_code_normalized": normalized_code,
            "severity": effective_severity,
        },
    )

    try:
        result = await symptoms_db.insert_symptom_event(
            conn,
            user_id,
            symptom_code=canonical_code,
            ts_utc=payload.ts_utc,
            severity=effective_severity,
            free_text=payload.free_text,
            tags=payload.tags,
        )
    except Exception as exc:  # pragma: no cover - exercised via tests
        logger.exception("failed to insert symptom event", extra={"user_id": user_id, "symptom_code": canonical_code})
        return JSONResponse(
            status_code=200,
            content={
                "ok": False,
                "data": None,
                "error": _error_text(exc),
                "friendly_error": _ERR_RECORD_EVENT,
            },
        )
    if not result.get("id") or not result.get("ts_utc"):
        raise HTTPException(status_code=500, detail="Failed to persist symptom event")
    try:
        await symptoms_db.ensure_symptom_episode_for_event(
            conn,
            user_id,
            symptom_event_id=str(result["id"]),
            symptom_code=canonical_code,
            ts_utc=payload.ts_utc,
            severity=effective_severity,
            note_text=payload.free_text,
        )
    except Exception as exc:  # pragma: no cover - migration rollout fallback
        logger.warning(
            "symptom episode sync failed user=%s event=%s err=%s",
            user_id,
            result.get("id"),
            exc,
        )
    await _commit_if_supported(conn)
    await _refresh_gauges_for_symptom(user_id, result["ts_utc"])
    data = SymptomEventData(id=result["id"], ts_utc=result["ts_utc"])
    return SymptomEventResponse(data=data, error=None)


def _success(payload: SymptomEnvelope) -> dict:
    return payload.model_dump()


def _failure(payload: SymptomEnvelope) -> JSONResponse:
    return JSONResponse(status_code=200, content=payload.model_dump())


def _error_text(exc: Exception) -> str:
    text = str(exc)
    return text if text else exc.__class__.__name__


@router.get("/today", response_model=SymptomTodayResponse)
async def get_symptoms_today(request: Request, conn=Depends(get_db)):
    user_id = _require_user_id(request)
    try:
        rows = await symptoms_db.fetch_symptoms_today(conn, user_id)
    except Exception as exc:  # pragma: no cover - exercised via tests
        logger.exception("failed to load todays symptoms", extra={"user_id": user_id})
        return _failure(
            SymptomTodayResponse(
                ok=False,
                data=[],
                error=_error_text(exc),
                friendly_error=_ERR_LOAD_TODAY,
            )
        )
    data = [
        SymptomTodayOut(
            symptom_code=_normalize_symptom_code(str(row["symptom_code"])),
            ts_utc=row["ts_utc"],
            severity=row.get("severity"),
            free_text=row.get("free_text"),
        )
        for row in rows or []
    ]
    return _success(SymptomTodayResponse(data=data))


@router.get("/daily", response_model=SymptomDailyResponse)
async def get_symptoms_daily(
    request: Request,
    conn=Depends(get_db),
    days: int = Query(30, ge=1, le=365),
):
    user_id = _require_user_id(request)
    try:
        rows = await symptoms_db.fetch_daily_summary(conn, user_id, days)
    except Exception as exc:  # pragma: no cover - exercised via tests
        logger.exception("failed to load daily symptoms", extra={"user_id": user_id, "days": days})
        return _failure(
            SymptomDailyResponse(
                ok=False,
                data=[],
                error=_error_text(exc),
                friendly_error=_ERR_LOAD_DAILY,
            )
        )
    data = [
        SymptomDailyRow(
            day=row["day"],
            symptom_code=_normalize_symptom_code(str(row["symptom_code"])),
            events=row["events"],
            mean_severity=row.get("mean_severity"),
            last_ts=row.get("last_ts"),
        )
        for row in rows or []
    ]
    return _success(SymptomDailyResponse(data=data))


@router.get("/diag", response_model=SymptomDiagResponse)
async def get_symptom_diag(
    request: Request,
    conn=Depends(get_db),
    days: int = Query(30, ge=1, le=365),
):
    user_id = _require_user_id(request)
    try:
        rows = await symptoms_db.fetch_diagnostics(conn, user_id, days)
    except Exception as exc:  # pragma: no cover - exercised via tests
        logger.exception("failed to load diagnostic summary", extra={"user_id": user_id, "days": days})
        return _failure(
            SymptomDiagResponse(
                ok=False,
                data=[],
                error=_error_text(exc),
                friendly_error=_ERR_LOAD_DIAG,
            )
        )
    data = [
        SymptomDiagRow(
            symptom_code=_normalize_symptom_code(str(row["symptom_code"])),
            events=row["events"],
            last_ts=row.get("last_ts"),
        )
        for row in rows or []
    ]
    return _success(SymptomDiagResponse(data=data))


class SymptomCodeResponse(SymptomEnvelope):
    data: List[SymptomCodeRow] = Field(default_factory=list)


@router.get("/codes", response_model=SymptomCodeResponse)
async def list_symptom_codes(
    response: Response,
    conn=Depends(get_db),
    include_inactive: bool = Query(False, description="Return inactive codes as well"),
):
    try:
        rows = await symptoms_db.fetch_symptom_codes(conn, include_inactive=include_inactive)
    except Exception as exc:  # pragma: no cover - exercised via tests
        logger.exception("failed to load symptom codes", extra={"include_inactive": include_inactive})
        return _failure(
            SymptomCodeResponse(
                ok=False,
                data=[],
                error=_error_text(exc),
                friendly_error=_ERR_LOAD_CODES,
            )
        )

    response.headers["Cache-Control"] = "public, max-age=300"

    normalized_rows: List[SymptomCodeRow] = []
    for row in rows:
        normalized_rows.append(
            SymptomCodeRow(
                symptom_code=_normalize_symptom_code(row["symptom_code"]),
                label=row["label"],
                description=row.get("description"),
                is_active=bool(row.get("is_active", False)),
            )
        )
    return _success(SymptomCodeResponse(data=normalized_rows))


@router.get("/current", response_model=CurrentSymptomsResponse)
async def get_current_symptoms(
    request: Request,
    conn=Depends(get_db),
    window_hours: int = Query(DEFAULT_CURRENT_WINDOW_HOURS, ge=1, le=MAX_CURRENT_WINDOW_HOURS),
):
    user_id = _require_user_id(request)
    try:
        snapshot = await _build_current_symptoms_payload(conn, user_id, window_hours=window_hours)
    except Exception as exc:  # pragma: no cover - exercised via tests
        logger.exception("failed to load current symptoms", extra={"user_id": user_id, "window_hours": window_hours})
        return _failure(
            CurrentSymptomsResponse(
                ok=False,
                data=None,
                error=_error_text(exc),
                friendly_error=_ERR_LOAD_CURRENT,
            )
        )
    return _success(CurrentSymptomsResponse(data=snapshot))


@router.get("/current/timeline", response_model=CurrentSymptomTimelineResponse)
async def get_current_symptom_timeline(
    request: Request,
    conn=Depends(get_db),
    days: int = Query(DEFAULT_CURRENT_TIMELINE_DAYS, ge=1, le=MAX_CURRENT_TIMELINE_DAYS),
):
    user_id = _require_user_id(request)
    try:
        rows = await symptoms_db.fetch_current_symptom_timeline(conn, user_id, days=days)
    except Exception:
        try:
            rows = await symptoms_db.fetch_current_symptom_timeline_fallback(conn, user_id, days=days)
        except Exception as exc:  # pragma: no cover - exercised via tests
            logger.exception("failed to load current symptom timeline", extra={"user_id": user_id, "days": days})
            return _failure(
                CurrentSymptomTimelineResponse(
                    ok=False,
                    data=[],
                    error=_error_text(exc),
                    friendly_error=_ERR_LOAD_TIMELINE,
                )
            )

    data = [
        CurrentSymptomTimelineEntryOut(
            id=str(row.get("id") or ""),
            episode_id=str(row.get("episode_id") or row.get("id") or ""),
            symptom_code=_normalize_symptom_code(str(row.get("symptom_code") or "")),
            label=str(row.get("label") or _label_from_code(str(row.get("symptom_code") or ""))),
            update_kind=str(row.get("update_kind") or "state_change"),
            state=_normalize_current_state(row.get("state")) if row.get("state") is not None else None,
            severity=row.get("severity"),
            note_text=_trimmed_text(row.get("note_text")),
            occurred_at=str(row.get("occurred_at") or ""),
        )
        for row in rows or []
    ]
    return _success(CurrentSymptomTimelineResponse(data=data))


@router.post("/current/{episode_id}/updates", response_model=CurrentSymptomItemResponse)
async def update_current_symptom(
    episode_id: str,
    payload: CurrentSymptomUpdateIn,
    request: Request,
    conn=Depends(get_db),
):
    user_id = _require_user_id(request)
    if payload.state is None and payload.severity is None and _trimmed_text(payload.note_text) is None:
        raise HTTPException(status_code=400, detail="No symptom update fields supplied")

    try:
        row = await symptoms_db.record_symptom_episode_update(
            conn,
            user_id,
            episode_id,
            state=_normalize_current_state(payload.state) if payload.state is not None else None,
            severity=payload.severity,
            note_text=payload.note_text,
            occurred_at=payload.ts_utc,
        )
    except Exception as exc:  # pragma: no cover - exercised via tests
        logger.exception("failed to update current symptom", extra={"user_id": user_id, "episode_id": episode_id})
        return _failure(
            CurrentSymptomItemResponse(
                ok=False,
                data=None,
                error=_error_text(exc),
                friendly_error=_ERR_RECORD_CURRENT_UPDATE,
            )
        )

    await _commit_if_supported(conn)
    refresh_ts = str(row.get("last_interaction_at") or row.get("state_updated_at") or row.get("started_at") or "")
    if refresh_ts:
        await _refresh_gauges_for_symptom(user_id, refresh_ts)
    return _success(CurrentSymptomItemResponse(data=_build_current_symptom_item_out(row)))


@router.delete("/current/{episode_id}", response_model=CurrentSymptomDeleteResponse)
async def delete_current_symptom(
    episode_id: str,
    request: Request,
    conn=Depends(get_db),
):
    user_id = _require_user_id(request)
    try:
        deleted = await symptoms_db.delete_symptom_episode(conn, user_id, episode_id)
    except Exception as exc:  # pragma: no cover - exercised via tests
        logger.exception("failed to delete current symptom", extra={"user_id": user_id, "episode_id": episode_id})
        return _failure(
            CurrentSymptomDeleteResponse(
                ok=False,
                data=None,
                error=_error_text(exc),
                friendly_error=_ERR_DELETE_CURRENT,
            )
        )

    await _commit_if_supported(conn)
    refresh_ts = str(deleted.get("last_interaction_at") or deleted.get("ts_utc") or deleted.get("started_at") or "")
    if refresh_ts:
        await _refresh_gauges_for_symptom(user_id, refresh_ts)
    return _success(
        CurrentSymptomDeleteResponse(
            data=CurrentSymptomDeleteOut(
                episode_id=str(deleted.get("episode_id") or episode_id),
                symptom_code=_normalize_symptom_code(str(deleted.get("symptom_code") or "")),
                deleted_at=datetime.now(timezone.utc).isoformat(),
            )
        )
    )
