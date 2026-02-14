from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import date, datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query, Request, HTTPException
from psycopg.rows import dict_row

from app.db import get_db
from app.security.auth import require_read_auth, require_write_auth


router = APIRouter(prefix="/v1", tags=["dashboard"])
logger = logging.getLogger(__name__)


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


def _post_row_to_payload(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not row:
        return None
    return {
        "day": str(row.get("day")) if row.get("day") else None,
        "title": row.get("title"),
        "caption": row.get("caption"),
        "body_markdown": row.get("body_markdown"),
        "updated_at": (
            row.get("updated_at").astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            if isinstance(row.get("updated_at"), datetime)
            else None
        ),
    }


async def _fetch_public_post(conn, day: date) -> Optional[Dict[str, Any]]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            select day, title, caption, body_markdown, updated_at
              from content.daily_posts
             where day <= %s
             order by day desc, updated_at desc
             limit 1
            """,
            (day,),
            prepare=False,
        )
        row = await cur.fetchone()
    return _post_row_to_payload(row)


async def _fetch_member_post(conn, user_id: str, day: date) -> Optional[Dict[str, Any]]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            select day, title, caption, body_markdown, updated_at
              from content.daily_posts_user
             where user_id = %s
               and day <= %s
               and platform = 'member'
             order by day desc, updated_at desc
             limit 1
            """,
            (user_id, day),
            prepare=False,
        )
        row = await cur.fetchone()
    return _post_row_to_payload(row)


async def _fetch_latest_gauges(conn, user_id: str, day: date) -> Dict[str, Any]:
    try:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                select day, pain, focus, heart, stamina, energy, sleep, mood, health_status, alerts_json
                  from marts.user_gauges_day
                 where user_id = %s
                   and day <= %s
                 order by day desc
                 limit 1
                """,
                (user_id, day),
                prepare=False,
            )
            row = await cur.fetchone()
    except Exception:
        return {}

    if not row:
        return {}

    gauges = {
        "pain": row.get("pain"),
        "focus": row.get("focus"),
        "heart": row.get("heart"),
        "stamina": row.get("stamina"),
        "energy": row.get("energy"),
        "sleep": row.get("sleep"),
        "mood": row.get("mood"),
        "health_status": row.get("health_status"),
    }
    alerts = row.get("alerts_json")
    if isinstance(alerts, str):
        try:
            alerts = json.loads(alerts)
        except Exception:
            alerts = []
    if not isinstance(alerts, list):
        alerts = []

    return {
        "day": str(row.get("day")) if row.get("day") else None,
        "gauges": gauges,
        "alerts": alerts,
    }


@router.get("/dashboard", dependencies=[Depends(require_read_auth)])
async def dashboard(
    request: Request,
    day: Optional[date] = Query(None),
    conn=Depends(get_db),
):
    started = time.perf_counter()
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id missing from request context")
    day = _coerce_day(day)
    payload = await _call_dashboard_payload(conn, user_id, day)
    if not isinstance(payload, dict):
        payload = {}

    entitled = await _is_paid_user(conn, user_id)
    public_post = await _fetch_public_post(conn, day)
    member_post = await _fetch_member_post(conn, user_id, day)
    personal_post = payload.get("personal_post")

    resolved_member = member_post or personal_post

    out = dict(payload)
    out["entitled"] = entitled
    out["member_post"] = resolved_member
    out["public_post"] = public_post

    gauge_fallback = await _fetch_latest_gauges(conn, user_id, day)
    if not out.get("gauges") and gauge_fallback.get("gauges"):
        out["gauges"] = gauge_fallback.get("gauges")
    if not out.get("alerts") and gauge_fallback.get("alerts"):
        out["alerts"] = gauge_fallback.get("alerts")
    if not out.get("day") and gauge_fallback.get("day"):
        out["day"] = gauge_fallback.get("day")

    elapsed_ms = round((time.perf_counter() - started) * 1000.0, 1)
    logger.info(
        "[dashboard] user=%s day=%s ms=%s gauges=%s alerts=%s entitled=%s member=%s public=%s",
        user_id,
        day.isoformat(),
        elapsed_ms,
        bool(out.get("gauges")),
        len(out.get("alerts") or []),
        out.get("entitled"),
        bool(out.get("member_post")),
        bool(out.get("public_post")),
    )
    return out


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


async def _is_paid_user(conn, user_id: str) -> Optional[bool]:
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
        try:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    select 1
                      from public.app_user_entitlements
                     where user_id = %s
                       and coalesce(is_active, true) = true
                       and coalesce(expires_at, now() + interval '100 years') > now()
                     limit 1
                    """,
                    (user_id,),
                    prepare=False,
                )
                row = await cur.fetchone()
                return bool(row)
        except Exception:
            return None


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
