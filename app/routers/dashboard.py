from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query, Request, HTTPException
from psycopg.rows import dict_row

from app.db import get_db
from app.security.auth import require_read_auth, require_write_auth


router = APIRouter(prefix="/v1", tags=["dashboard"])


def _coerce_day(value: Optional[date]) -> date:
    return value or datetime.now(timezone.utc).date()


async def _call_dashboard_payload(conn, user_id: str, day: date) -> Dict[str, Any]:
    sqls = [
        ("select app.get_dashboard_payload(%s::uuid, %s::date) as payload", (user_id, day)),
        ("select app.get_dashboard_payload(%s::date, %s::uuid) as payload", (day, user_id)),
        ("select app.get_dashboard_payload(%s::date) as payload", (day,)),
    ]
    last_exc: Optional[Exception] = None
    for sql, params in sqls:
        try:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(sql, params, prepare=False)
                row = await cur.fetchone()
                payload = row.get("payload") if row else None
                if isinstance(payload, str):
                    payload = json.loads(payload)
                if isinstance(payload, dict):
                    return payload
        except Exception as exc:
            last_exc = exc
            continue
    raise RuntimeError(f"get_dashboard_payload failed: {last_exc}")


@router.get("/dashboard", dependencies=[Depends(require_read_auth)])
async def dashboard(
    request: Request,
    day: Optional[date] = Query(None),
    conn=Depends(get_db),
):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id missing from request context")
    day = _coerce_day(day)
    payload = await _call_dashboard_payload(conn, user_id, day)
    return payload


@router.get("/earthscope/member", dependencies=[Depends(require_read_auth)])
async def earthscope_member(
    request: Request,
    day: Optional[date] = Query(None),
    conn=Depends(get_db),
):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id missing from request context")
    day = _coerce_day(day)

    try:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                select day, title, caption, body_markdown, hashtags,
                       metrics_json, sources_json, updated_at
                  from content.daily_posts_user
                 where user_id = %s
                   and day = %s
                   and platform = 'member'
                 order by updated_at desc
                 limit 1
                """,
                (user_id, day),
                prepare=False,
            )
            row = await cur.fetchone()
    except Exception as exc:
        return {"ok": False, "error": f"member earthscope fetch failed: {exc}"}

    if not row:
        return {"ok": True, "post": None}

    return {
        "ok": True,
        "post": {
            "day": row.get("day"),
            "title": row.get("title"),
            "caption": row.get("caption"),
            "body_markdown": row.get("body_markdown"),
            "hashtags": row.get("hashtags"),
            "metrics_json": row.get("metrics_json"),
            "sources_json": row.get("sources_json"),
            "updated_at": (row.get("updated_at").astimezone(timezone.utc).isoformat()
                           if isinstance(row.get("updated_at"), datetime) else None),
        },
    }


async def _is_paid_user(conn, user_id: str) -> bool:
    try:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                select 1
                  from public.app_user_entitlements_active
                 where user_id = %s
                   and is_active = true
                 limit 1
                """,
                (user_id,),
                prepare=False,
            )
            row = await cur.fetchone()
            return bool(row)
    except Exception:
        return False


@router.post("/earthscope/member/regenerate", dependencies=[Depends(require_write_auth)])
async def earthscope_member_regenerate(
    request: Request,
    day: Optional[date] = Query(None),
    conn=Depends(get_db),
):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id missing from request context")
    day = _coerce_day(day)

    def _run() -> Dict[str, Any]:
        from bots.gauges.gauge_scorer import score_user_day
        from bots.earthscope_post.member_earthscope_generate import generate_member_post_for_user

        score_user_day(user_id, day, force=True)
        return generate_member_post_for_user(user_id, day, force=True)

    # Paid-only gate
    if not await _is_paid_user(conn, user_id):
        raise HTTPException(status_code=403, detail="member entitlement required")

    result = await asyncio.to_thread(_run)
    return {"ok": True, "result": result}
