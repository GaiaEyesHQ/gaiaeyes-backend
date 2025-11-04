from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, conint

from ..db import get_db
from ..db import symptoms as symptoms_db

router = APIRouter(prefix="/symptoms", tags=["symptoms"])


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


class SymptomEventOut(BaseModel):
    ok: bool = True
    id: str
    ts_utc: str


class SymptomTodayOut(BaseModel):
    symptom_code: str
    ts_utc: str
    severity: Optional[int] = None
    free_text: Optional[str] = None


class SymptomDailyRow(BaseModel):
    day: str
    symptom_code: str
    events: int
    mean_severity: Optional[float] = None
    last_ts: Optional[str] = None


class SymptomDiagRow(BaseModel):
    symptom_code: str
    events: int
    last_ts: Optional[str] = None


@router.post("", response_model=SymptomEventOut)
async def create_symptom_event(
    payload: SymptomEventIn,
    request: Request,
    conn=Depends(get_db),
):
    user_id = _require_user_id(request)
    result = await symptoms_db.insert_symptom_event(
        conn,
        user_id,
        symptom_code=payload.symptom_code,
        ts_utc=payload.ts_utc,
        severity=payload.severity,
        free_text=payload.free_text,
        tags=payload.tags,
    )
    if not result.get("id") or not result.get("ts_utc"):
        raise HTTPException(status_code=500, detail="Failed to persist symptom event")
    return SymptomEventOut(id=result["id"], ts_utc=result["ts_utc"])


@router.get("/today", response_model=List[SymptomTodayOut])
async def get_symptoms_today(request: Request, conn=Depends(get_db)):
    user_id = _require_user_id(request)
    rows = await symptoms_db.fetch_symptoms_today(conn, user_id)
    return [SymptomTodayOut(**row) for row in rows]


@router.get("/daily", response_model=List[SymptomDailyRow])
async def get_symptoms_daily(
    request: Request,
    conn=Depends(get_db),
    days: int = Query(30, ge=1, le=365),
):
    user_id = _require_user_id(request)
    rows = await symptoms_db.fetch_daily_summary(conn, user_id, days)
    return [SymptomDailyRow(**row) for row in rows]


@router.get("/diag", response_model=List[SymptomDiagRow])
async def get_symptom_diag(
    request: Request,
    conn=Depends(get_db),
    days: int = Query(30, ge=1, le=365),
):
    user_id = _require_user_id(request)
    rows = await symptoms_db.fetch_diagnostics(conn, user_id, days)
    return [SymptomDiagRow(**row) for row in rows]
