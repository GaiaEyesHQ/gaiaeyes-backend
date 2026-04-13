from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.db import get_db
from app.db import feedback as feedback_db
from app.security.auth import require_read_auth, require_write_auth


router = APIRouter(prefix="/v1/feedback", tags=["feedback"])

_ERR_LOAD_DAILY_CHECKIN = "Failed to load daily check-in"
_ERR_SAVE_DAILY_CHECKIN = "Failed to save daily check-in"
_ERR_DISMISS_DAILY_CHECKIN = "Failed to update daily check-in prompt"

_COMPARE_VALUES = {"better", "same", "worse"}
_ENERGY_VALUES = {"good", "manageable", "low", "depleted"}
_USABLE_ENERGY_VALUES = {"plenty", "enough", "limited", "very_limited"}
_SYSTEM_LOAD_VALUES = {"light", "moderate", "heavy", "overwhelming"}
_PAIN_VALUES = {"none", "a_little", "noticeable", "strong"}
_MOOD_VALUES = {"calm", "slightly_off", "noticeable", "strong"}
_SLEEP_IMPACT_VALUES = {"yes_strongly", "yes_somewhat", "not_much", "unsure"}
_PREDICTION_MATCH_VALUES = {"mostly_right", "partly_right", "not_really"}
_EXPOSURE_VALUES = set(feedback_db.DEFAULT_EXPOSURE_OPTIONS)


def _require_user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id missing from request context")
    return user_id


def _trimmed_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


def _error_text(exc: Exception) -> str:
    text = str(exc)
    return text if text else exc.__class__.__name__


def _validate_choice(value: str, allowed: set[str], *, detail: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in allowed:
        raise HTTPException(status_code=400, detail=detail)
    return normalized


class FeedbackEnvelope(BaseModel):
    ok: bool = True
    error: Optional[str] = None
    friendly_error: Optional[str] = None


class DailyCheckInPromptOut(BaseModel):
    id: str
    day: str
    phase: Optional[str] = None
    question_text: str
    scheduled_for: Optional[str] = None
    delivered_at: Optional[str] = None
    active_symptom_labels: List[str] = Field(default_factory=list)
    recent_symptom_codes: List[str] = Field(default_factory=list)
    pain_logged_recently: bool = False
    energy_logged_recently: bool = False
    mood_logged_recently: bool = False
    sleep_logged_recently: bool = False
    suggested_pain_types: List[str] = Field(default_factory=list)
    suggested_energy_details: List[str] = Field(default_factory=list)
    suggested_mood_types: List[str] = Field(default_factory=list)
    suggested_sleep_impacts: List[str] = Field(default_factory=list)
    push_delivery_enabled: bool = False
    status: Optional[str] = None


class DailyCheckInEntryOut(BaseModel):
    day: str
    prompt_id: Optional[str] = None
    compared_to_yesterday: str
    energy_level: str
    usable_energy: str
    system_load: str
    pain_level: str
    pain_type: Optional[str] = None
    energy_detail: Optional[str] = None
    mood_level: str
    mood_type: Optional[str] = None
    sleep_impact: Optional[str] = None
    prediction_match: Optional[str] = None
    note_text: Optional[str] = None
    completed_at: Optional[str] = None
    exposures: List[str] = Field(default_factory=list)


class FeedbackCalibrationSummaryOut(BaseModel):
    window_days: int = 21
    total_checkins: int = 0
    mostly_right: int = 0
    partly_right: int = 0
    not_really: int = 0
    match_rate: Optional[float] = None
    resolved_count: int = 0
    improving_count: int = 0
    worse_count: int = 0


class DailyCheckInSettingsOut(BaseModel):
    enabled: bool = False
    push_enabled: bool = False
    cadence: str = "balanced"
    reminder_time: str = "20:00"


class DailyCheckInStatusOut(BaseModel):
    prompt: Optional[DailyCheckInPromptOut] = None
    latest_entry: Optional[DailyCheckInEntryOut] = None
    target_day: Optional[str] = None
    calibration_summary: FeedbackCalibrationSummaryOut
    settings: DailyCheckInSettingsOut


class DailyCheckInStatusEnvelope(FeedbackEnvelope):
    data: Optional[DailyCheckInStatusOut] = None


class DailyCheckInEntryEnvelope(FeedbackEnvelope):
    data: Optional[DailyCheckInEntryOut] = None


class DailyCheckInPromptEnvelope(FeedbackEnvelope):
    data: Optional[DailyCheckInPromptOut] = None


class DailyCheckInEntryIn(BaseModel):
    prompt_id: Optional[str] = None
    day: str
    compared_to_yesterday: str
    energy_level: str
    usable_energy: str
    system_load: str
    pain_level: str
    pain_type: Optional[str] = None
    energy_detail: Optional[str] = None
    mood_level: str
    mood_type: Optional[str] = None
    sleep_impact: Optional[str] = None
    prediction_match: Optional[str] = None
    note_text: Optional[str] = None
    exposures: List[str] = Field(default_factory=list)
    completed_at: Optional[datetime] = None


class DailyCheckInPromptActionIn(BaseModel):
    action: str = "dismiss"
    snooze_hours: Optional[int] = Field(default=None, ge=1, le=48)


def _build_prompt_out(payload: Dict[str, Any]) -> DailyCheckInPromptOut:
    context = payload.get("prompt_payload") or {}
    return DailyCheckInPromptOut(
        id=str(payload.get("id") or ""),
        day=str(payload.get("prompt_day") or (context.get("target_day") or "")),
        phase=_trimmed_text(context.get("phase")),
        question_text=str(payload.get("question_text") or ""),
        scheduled_for=payload.get("scheduled_for"),
        delivered_at=payload.get("delivered_at"),
        active_symptom_labels=[str(value) for value in (context.get("active_symptom_labels") or []) if value],
        recent_symptom_codes=[str(value).upper() for value in (context.get("recent_symptom_codes") or []) if value],
        pain_logged_recently=bool(context.get("pain_logged_recently")),
        energy_logged_recently=bool(context.get("energy_logged_recently")),
        mood_logged_recently=bool(context.get("mood_logged_recently")),
        sleep_logged_recently=bool(context.get("sleep_logged_recently")),
        suggested_pain_types=[str(value) for value in (context.get("suggested_pain_types") or []) if value],
        suggested_energy_details=[str(value) for value in (context.get("suggested_energy_details") or []) if value],
        suggested_mood_types=[str(value) for value in (context.get("suggested_mood_types") or []) if value],
        suggested_sleep_impacts=[str(value) for value in (context.get("suggested_sleep_impacts") or []) if value],
        push_delivery_enabled=bool(payload.get("push_delivery_enabled")),
        status=_trimmed_text(payload.get("status")),
    )


def _build_entry_out(payload: Dict[str, Any]) -> DailyCheckInEntryOut:
    return DailyCheckInEntryOut(
        day=str(payload.get("day") or ""),
        prompt_id=_trimmed_text(payload.get("prompt_id")),
        compared_to_yesterday=str(payload.get("compared_to_yesterday") or ""),
        energy_level=str(payload.get("energy_level") or ""),
        usable_energy=str(payload.get("usable_energy") or ""),
        system_load=str(payload.get("system_load") or ""),
        pain_level=str(payload.get("pain_level") or ""),
        pain_type=_trimmed_text(payload.get("pain_type")),
        energy_detail=_trimmed_text(payload.get("energy_detail")),
        mood_level=str(payload.get("mood_level") or ""),
        mood_type=_trimmed_text(payload.get("mood_type")),
        sleep_impact=_trimmed_text(payload.get("sleep_impact")),
        prediction_match=_trimmed_text(payload.get("prediction_match")),
        note_text=_trimmed_text(payload.get("note_text")),
        completed_at=payload.get("completed_at"),
        exposures=[str(value) for value in (payload.get("exposures") or []) if str(value or "").strip()],
    )


def _success(payload: FeedbackEnvelope) -> dict:
    return payload.model_dump()


def _failure(payload: FeedbackEnvelope) -> JSONResponse:
    return JSONResponse(status_code=200, content=payload.model_dump())


@router.get("/daily-checkin", response_model=DailyCheckInStatusEnvelope, dependencies=[Depends(require_read_auth)])
async def get_daily_check_in_status(request: Request, conn=Depends(get_db)):
    user_id = _require_user_id(request)
    try:
        status = await feedback_db.fetch_daily_check_in_status(conn, user_id)
    except Exception as exc:  # pragma: no cover - exercised via tests
        return _failure(
            DailyCheckInStatusEnvelope(
                ok=False,
                data=None,
                error=_error_text(exc),
                friendly_error=_ERR_LOAD_DAILY_CHECKIN,
            )
        )

    return _success(
        DailyCheckInStatusEnvelope(
            data=DailyCheckInStatusOut(
                prompt=_build_prompt_out(status["prompt"]) if status.get("prompt") else None,
                latest_entry=_build_entry_out(status["latest_entry"]) if status.get("latest_entry") else None,
                target_day=_trimmed_text(status.get("target_day")),
                calibration_summary=FeedbackCalibrationSummaryOut(**(status.get("calibration_summary") or {})),
                settings=DailyCheckInSettingsOut(**(status.get("settings") or {})),
            )
        )
    )


@router.post("/daily-checkin", response_model=DailyCheckInEntryEnvelope, dependencies=[Depends(require_write_auth)])
async def submit_daily_check_in(
    payload: DailyCheckInEntryIn,
    request: Request,
    conn=Depends(get_db),
):
    user_id = _require_user_id(request)
    try:
        day_value = date.fromisoformat(payload.day)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid check-in day") from exc

    try:
        saved = await feedback_db.save_daily_check_in(
            conn,
            user_id,
            prompt_id=_trimmed_text(payload.prompt_id),
            day=day_value,
            compared_to_yesterday=_validate_choice(payload.compared_to_yesterday, _COMPARE_VALUES, detail="invalid comparison value"),
            energy_level=_validate_choice(payload.energy_level, _ENERGY_VALUES, detail="invalid energy value"),
            usable_energy=_validate_choice(payload.usable_energy, _USABLE_ENERGY_VALUES, detail="invalid usable energy value"),
            system_load=_validate_choice(payload.system_load, _SYSTEM_LOAD_VALUES, detail="invalid system load value"),
            pain_level=_validate_choice(payload.pain_level, _PAIN_VALUES, detail="invalid pain value"),
            pain_type=_trimmed_text(payload.pain_type),
            energy_detail=_trimmed_text(payload.energy_detail),
            mood_level=_validate_choice(payload.mood_level, _MOOD_VALUES, detail="invalid mood value"),
            mood_type=_trimmed_text(payload.mood_type),
            sleep_impact=_validate_choice(payload.sleep_impact, _SLEEP_IMPACT_VALUES, detail="invalid sleep impact value") if payload.sleep_impact else None,
            prediction_match=_validate_choice(payload.prediction_match, _PREDICTION_MATCH_VALUES, detail="invalid prediction-match value") if payload.prediction_match else None,
            note_text=_trimmed_text(payload.note_text),
            exposures=[
                _validate_choice(str(value), _EXPOSURE_VALUES, detail="invalid exposure value")
                for value in payload.exposures
                if str(value or "").strip()
            ],
            completed_at=payload.completed_at,
        )
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - exercised via tests
        return _failure(
            DailyCheckInEntryEnvelope(
                ok=False,
                data=None,
                error=_error_text(exc),
                friendly_error=_ERR_SAVE_DAILY_CHECKIN,
            )
        )

    return _success(DailyCheckInEntryEnvelope(data=_build_entry_out(saved)))


@router.post("/daily-checkin/{prompt_id}/dismiss", response_model=DailyCheckInPromptEnvelope, dependencies=[Depends(require_write_auth)])
async def dismiss_daily_check_in(
    prompt_id: str,
    payload: DailyCheckInPromptActionIn,
    request: Request,
    conn=Depends(get_db),
):
    user_id = _require_user_id(request)
    try:
        prompt = await feedback_db.dismiss_daily_check_in(
            conn,
            user_id,
            prompt_id,
            action=payload.action,
            snooze_hours=payload.snooze_hours,
        )
    except Exception as exc:  # pragma: no cover - exercised via tests
        return _failure(
            DailyCheckInPromptEnvelope(
                ok=False,
                data=None,
                error=_error_text(exc),
                friendly_error=_ERR_DISMISS_DAILY_CHECKIN,
            )
        )
    return _success(DailyCheckInPromptEnvelope(data=_build_prompt_out(prompt)))
