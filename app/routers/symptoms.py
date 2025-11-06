from __future__ import annotations

from datetime import datetime
from typing import List, Optional

import logging
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, conint

from ..db import get_db
from ..db import symptoms as symptoms_db

router = APIRouter(prefix="/symptoms", tags=["symptoms"])

logger = logging.getLogger(__name__)


_ERR_LOAD_CODES = "Failed to load symptom codes"
_ERR_RECORD_EVENT = "Failed to record symptom event"
_ERR_LOAD_TODAY = "Failed to load today's symptoms"
_ERR_LOAD_DAILY = "Failed to load daily symptom summary"
_ERR_LOAD_DIAG = "Failed to load diagnostic summary"


def _require_user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id missing from request context")
    return user_id


class SymptomEventIn(BaseModel):
    symptom_code: str = Field(..., min_length=1)
    ts_utc: Optional[datetime] = None
    severity: Optional[conint(ge=1, le=5)] = None
    free_text: Optional[str] = None
    tags: Optional[List[str]] = None


class SymptomEnvelope(BaseModel):
    ok: bool = True
    error: Optional[str] = None
    raw_error: Optional[str] = None
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


def _normalize_symptom_code(value: str) -> str:
    return value.strip().replace(" ", "_").replace("-", "_").upper()


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

    try:
        code_rows = await symptoms_db.fetch_symptom_codes(conn)
    except Exception as exc:  # pragma: no cover - exercised via tests
        logger.exception("failed to load codes for symptom post", extra={"user_id": user_id})
        raw_error = _error_text(exc)
        return JSONResponse(
            status_code=200,
            content={
                "ok": False,
                "data": None,
                "error": raw_error,
                "raw_error": raw_error,
                "friendly_error": _ERR_LOAD_CODES,
            },
        )

    lookup = {
        _normalize_symptom_code(row["symptom_code"]): row
        for row in code_rows
    }

    if not lookup:
        raise HTTPException(status_code=500, detail="No symptom codes configured")

    other_code = "OTHER" if "OTHER" in lookup else None

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
        if other_code is None:
            raise HTTPException(status_code=500, detail="OTHER symptom code missing from catalog")
        normalized_code = other_code

    logger.info(
        "symptom_event",
        extra={
            "user_id": user_id,
            "symptom_code": normalized_code,
            "severity": payload.severity,
        },
    )

    try:
        result = await symptoms_db.insert_symptom_event(
            conn,
            user_id,
            symptom_code=normalized_code,
            ts_utc=payload.ts_utc,
            severity=payload.severity,
            free_text=payload.free_text,
            tags=payload.tags,
        )
    except Exception as exc:  # pragma: no cover - exercised via tests
        logger.exception("failed to insert symptom event", extra={"user_id": user_id, "symptom_code": normalized_code})
        raw_error = _error_text(exc)
        return JSONResponse(
            status_code=200,
            content={
                "ok": False,
                "data": None,
                "error": raw_error,
                "raw_error": raw_error,
                "friendly_error": _ERR_RECORD_EVENT,
            },
        )
    if not result.get("id") or not result.get("ts_utc"):
        raise HTTPException(status_code=500, detail="Failed to persist symptom event")
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
        raw_error = _error_text(exc)
        return _failure(
            SymptomTodayResponse(
                ok=False,
                data=[],
                error=raw_error,
                raw_error=raw_error,
                friendly_error=_ERR_LOAD_TODAY,
            )
        )
    data = [SymptomTodayOut(**row) for row in rows or []]
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
        raw_error = _error_text(exc)
        return _failure(
            SymptomDailyResponse(
                ok=False,
                data=[],
                error=raw_error,
                raw_error=raw_error,
                friendly_error=_ERR_LOAD_DAILY,
            )
        )
    data = [SymptomDailyRow(**row) for row in rows or []]
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
        raw_error = _error_text(exc)
        return _failure(
            SymptomDiagResponse(
                ok=False,
                data=[],
                error=raw_error,
                raw_error=raw_error,
                friendly_error=_ERR_LOAD_DIAG,
            )
        )
    data = [SymptomDiagRow(**row) for row in rows or []]
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
        raw_error = _error_text(exc)
        return _failure(
            SymptomCodeResponse(
                ok=False,
                data=[],
                error=raw_error,
                raw_error=raw_error,
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
