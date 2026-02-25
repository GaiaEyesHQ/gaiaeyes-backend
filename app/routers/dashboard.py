from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import date, datetime, timezone
from functools import lru_cache
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query, Request, HTTPException
from psycopg.rows import dict_row

from app.db import get_db
from app.security.auth import require_read_auth, require_write_auth
from bots.definitions.load_definition_base import load_definition_base
from services.gauges.zones import decorate_gauge


router = APIRouter(prefix="/v1", tags=["dashboard"])
logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _load_dashboard_definition() -> Dict[str, Any]:
    definition, _ = load_definition_base()
    return definition


def _safe_dashboard_definition() -> Dict[str, Any]:
    try:
        return _load_dashboard_definition()
    except Exception as exc:
        logger.warning("[dashboard] failed to load gauge definition base: %s", exc)
        return {}


def _normalized_default_zones(definition: Dict[str, Any]) -> list[Dict[str, Any]]:
    raw = (definition.get("gauge_zones") or {}).get("default") or []
    zones: list[Dict[str, Any]] = []
    for zone in raw:
        if not isinstance(zone, dict):
            continue
        key = str(zone.get("key") or "").strip()
        try:
            min_val = int(round(float(zone.get("min"))))
            max_val = int(round(float(zone.get("max"))))
        except Exception:
            continue
        if not key:
            continue
        if min_val > max_val:
            min_val, max_val = max_val, min_val
        zones.append({"min": min_val, "max": max_val, "key": key})
    zones.sort(key=lambda item: (item["min"], item["max"]))
    return zones


def _gauge_labels(definition: Dict[str, Any]) -> Dict[str, str]:
    labels: Dict[str, str] = {}
    for gauge in definition.get("gauges") or []:
        if not isinstance(gauge, dict):
            continue
        key = str(gauge.get("key") or "").strip()
        label = str(gauge.get("label") or "").strip()
        if key and label:
            labels[key] = label

    output_gauge = (definition.get("health_metrics_overlay") or {}).get("output_gauge")
    if isinstance(output_gauge, dict):
        key = str(output_gauge.get("key") or "").strip()
        label = str(output_gauge.get("label") or "").strip()
        if key and label:
            labels[key] = label

    return labels


def _decorate_gauges(gauges: Dict[str, Any], definition: Dict[str, Any]) -> Dict[str, Dict[str, Optional[str]]]:
    out: Dict[str, Dict[str, Optional[str]]] = {}
    for gauge_key, raw_value in gauges.items():
        item = decorate_gauge(gauge_key, raw_value, definition)
        zone_key = item.get("zone_key")
        zone_label = item.get("zone_label")
        if zone_key is None and item.get("value") is None:
            out[gauge_key] = {"zone": "calibrating", "label": zone_label}
            continue
        if zone_key:
            out[gauge_key] = {"zone": zone_key, "label": zone_label}
    return out


def _coerce_day(value: Optional[date]) -> date:
    return value or datetime.now(timezone.utc).date()


async def _call_dashboard_payload(conn, user_id: str, day: date) -> tuple[Dict[str, Any], bool]:
    sqls = [
        ("select app.get_dashboard_payload(%s::uuid, %s::date) as payload", (user_id, day)),
        ("select app.get_dashboard_payload(%s::date, %s::uuid) as payload", (day, user_id)),
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
                    return payload, False
        except Exception as exc:
            last_exc = exc
            try:
                await conn.rollback()
            except Exception:
                pass
            continue
    if last_exc is not None:
        logger.warning(
            "[dashboard] get_dashboard_payload RPC unavailable for user/day fallback path: %s",
            last_exc,
        )
    # Do not hard-fail dashboard rendering when the RPC signature differs across environments.
    return {}, True


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
    debug: bool = Query(False),
    conn=Depends(get_db),
):
    started = time.perf_counter()
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id missing from request context")
    day = _coerce_day(day)
    payload, rpc_fallback_used = await _call_dashboard_payload(conn, user_id, day)
    if not isinstance(payload, dict):
        payload = {}

    paid_probe = await _probe_paid_user(conn, user_id)
    entitled = paid_probe.get("entitled")
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

    definition = _safe_dashboard_definition()
    if definition:
        out["gauge_zones"] = _normalized_default_zones(definition)
        out["gauge_labels"] = _gauge_labels(definition)
        gauges = out.get("gauges")
        if isinstance(gauges, dict):
            out["gauges_meta"] = _decorate_gauges(gauges, definition)

    if debug:
        out["_debug"] = {
            "user_id": user_id,
            "requested_day": day.isoformat(),
            "entitlement_probe": paid_probe,
            "payload_keys": sorted(payload.keys()) if isinstance(payload, dict) else [],
            "rpc_fallback_used": rpc_fallback_used,
            "used_gauge_fallback": bool(
                (not payload.get("gauges") and gauge_fallback.get("gauges"))
                or (not payload.get("alerts") and gauge_fallback.get("alerts"))
            ),
        }

    elapsed_ms = round((time.perf_counter() - started) * 1000.0, 1)
    logger.info(
        "[dashboard] user=%s day=%s ms=%s gauges=%s alerts=%s entitled=%s probe=%s member=%s public=%s",
        user_id,
        day.isoformat(),
        elapsed_ms,
        bool(out.get("gauges")),
        len(out.get("alerts") or []),
        out.get("entitled"),
        paid_probe.get("matched_strategy"),
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


async def _probe_paid_user(conn, user_id: str) -> Dict[str, Any]:
    checks = [
        (
            "active_view_with_is_active",
            """
            select 1
              from public.app_user_entitlements_active
             where user_id = %s
               and is_active = true
             limit 1
            """,
            (user_id,),
        ),
        (
            "active_view_without_is_active",
            """
            select 1
              from public.app_user_entitlements_active
             where user_id = %s
             limit 1
            """,
            (user_id,),
        ),
        (
            "base_table_active_and_not_expired",
            """
            select 1
              from public.app_user_entitlements
             where user_id = %s
               and coalesce(is_active, true) = true
               and coalesce(expires_at, now() + interval '100 years') > now()
             limit 1
            """,
            (user_id,),
        ),
        (
            "base_table_not_expired_only",
            """
            select 1
              from public.app_user_entitlements
             where user_id = %s
               and coalesce(expires_at, now() + interval '100 years') > now()
             limit 1
            """,
            (user_id,),
        ),
        (
            "email_mapped_entitlement",
            """
            with me as (
                select lower(email) as email
                  from auth.users
                 where id = %s::uuid
            )
            select 1
              from public.app_stripe_customers sc
              join me on lower(sc.email) = me.email
              join public.app_user_entitlements ue on ue.user_id = sc.user_id
             where coalesce(ue.expires_at, now() + interval '100 years') > now()
               and coalesce(ue.is_active, true) = true
             limit 1
            """,
            (user_id,),
        ),
    ]

    saw_error = False
    check_results: list[Dict[str, Any]] = []
    for label, sql, params in checks:
        row_found = False
        err_text: Optional[str] = None
        try:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(sql, params, prepare=False)
                row = await cur.fetchone()
                row_found = bool(row)
        except Exception as exc:
            saw_error = True
            err_text = str(exc)
            logger.warning("[dashboard] entitlement check '%s' failed for user=%s: %s", label, user_id, exc)
            try:
                await conn.rollback()
            except Exception:
                pass
        check_results.append(
            {
                "strategy": label,
                "matched": row_found,
                "error": err_text,
            }
        )
        if row_found:
            return {
                "entitled": True,
                "matched_strategy": label,
                "checks": check_results,
            }

    return {
        "entitled": (None if saw_error else False),
        "matched_strategy": None,
        "checks": check_results,
    }


async def _is_paid_user(conn, user_id: str) -> Optional[bool]:
    probe = await _probe_paid_user(conn, user_id)
    return probe.get("entitled")


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
