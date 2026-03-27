from __future__ import annotations

import logging
import os
from typing import Optional, Literal
import datetime as dt

import psycopg
import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.security.auth import require_supabase_jwt

router = APIRouter(prefix="/v1/billing", tags=["billing"])

logger = logging.getLogger(__name__)

STRIPE_API_KEY = os.environ.get("STRIPE_API_KEY", "").strip()
SUCCESS_URL = os.environ.get("CHECKOUT_SUCCESS_URL", "").strip()
CANCEL_URL = os.environ.get("CHECKOUT_CANCEL_URL", "").strip()
SUPABASE_DB_URL = os.environ.get("SUPABASE_DB_URL", os.environ.get("DATABASE_URL", "")).strip()

PRICE_MAP = {
    "plus_monthly": os.environ.get("STRIPE_PRICE_PLUS_MONTHLY", "").strip(),
    "plus_yearly": os.environ.get("STRIPE_PRICE_PLUS_YEARLY", "").strip(),
    "pro_monthly": os.environ.get("STRIPE_PRICE_PRO_MONTHLY", "").strip(),
    "pro_yearly": os.environ.get("STRIPE_PRICE_PRO_YEARLY", "").strip(),
}


def _db_conn():
    if not SUPABASE_DB_URL:
        raise HTTPException(status_code=500, detail="Server DB not configured (SUPABASE_DB_URL)")
    return psycopg.connect(SUPABASE_DB_URL)


def _get_user_email(user_id: str) -> Optional[str]:
    with _db_conn() as conn, conn.cursor() as cur:
        cur.execute("select email from auth.users where id = %s", (user_id,))
        row = cur.fetchone()
    return row[0] if row else None


def _table_columns(schema: str, table: str) -> list[str]:
    with _db_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            select column_name
            from information_schema.columns
            where table_schema = %s
              and table_name = %s
            order by ordinal_position
            """,
            (schema, table),
        )
        rows = cur.fetchall()
    return [str(row[0]) for row in rows or [] if row and row[0]]


def _pick(cols: list[str], candidates: list[str]) -> Optional[str]:
    lowered = {str(col).lower(): str(col) for col in cols}
    for candidate in candidates:
        match = lowered.get(candidate.lower())
        if match:
            return match
    return None


def _get_entitlement_rows(user_id: str, email: Optional[str]):
    cols = _table_columns("public", "app_user_entitlements")
    if not cols:
        return [], user_id, "direct"

    user_col = _pick(cols, ["user_id"])
    key_col = _pick(cols, ["entitlement_key", "key"])
    term_col = _pick(cols, ["term"])
    active_col = _pick(cols, ["is_active", "active", "enabled"])
    started_col = _pick(cols, ["started_at", "created_at"])
    expires_col = _pick(cols, ["expires_at"])
    updated_col = _pick(cols, ["updated_at", "created_at"])

    if not user_col or not key_col:
        return [], user_id, "direct"

    select_specs = [
        (key_col, f"ue.{key_col}", "entitlement_key"),
        (term_col, f"ue.{term_col}" if term_col else None, "term"),
        (
            f"coalesce({active_col}, true)" if active_col else None,
            f"coalesce(ue.{active_col}, true)" if active_col else None,
            "is_active",
        ),
        (started_col, f"ue.{started_col}" if started_col else None, "started_at"),
        (expires_col, f"ue.{expires_col}" if expires_col else None, "expires_at"),
        (updated_col, f"ue.{updated_col}" if updated_col else None, "updated_at"),
    ]
    select_parts = [
        f"{direct_expr} as {alias}" if direct_expr else (
            "true as is_active" if alias == "is_active" else
            "null::text as term" if alias == "term" else
            f"null::timestamptz as {alias}"
        )
        for direct_expr, _, alias in select_specs
    ]
    fallback_parts = [
        f"{fallback_expr} as {alias}" if fallback_expr else (
            "true as is_active" if alias == "is_active" else
            "null::text as term" if alias == "term" else
            f"null::timestamptz as {alias}"
        )
        for _, fallback_expr, alias in select_specs
    ]
    direct_sql = (
        f"select {', '.join(select_parts)} "
        f"from public.app_user_entitlements "
        f"where {user_col} = %s "
        f"order by {key_col}"
    )
    fallback_sql = (
        f"select distinct {', '.join(fallback_parts)}, "
        f"ue.{user_col} as resolved_user_id "
        f"from public.app_stripe_customers sc "
        f"join public.app_user_entitlements ue on ue.{user_col} = sc.user_id "
        f"where lower(sc.email) = lower(%s) "
        f"order by entitlement_key, updated_at desc nulls last, started_at desc nulls last"
    )

    with _db_conn() as conn, conn.cursor() as cur:
        cur.execute(
            direct_sql,
            (user_id,),
        )
        rows = cur.fetchall()
        if rows or not email:
            return rows, user_id, "direct"

        cur.execute(fallback_sql, (email,))
        fallback_rows = cur.fetchall()

    if not fallback_rows:
        return [], user_id, "direct"

    resolved_user_id = fallback_rows[0][6]
    rows = [row[:6] for row in fallback_rows]
    return rows, resolved_user_id, "email_map"


def _get_or_create_customer(email: Optional[str], user_id: str) -> str:
    with _db_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            select customer_id
            from public.app_stripe_customers
            where user_id = %s
            order by updated_at desc nulls last, created_at desc
            limit 1
            """,
            (user_id,),
        )
        row = cur.fetchone()
        if row and row[0]:
            return row[0]

    customer_id = None
    if email:
        with _db_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                select customer_id
                from public.app_stripe_customers
                where lower(email) = lower(%s)
                order by updated_at desc nulls last, created_at desc
                limit 1
                """,
                (email,),
            )
            row = cur.fetchone()
            if row and row[0]:
                customer_id = row[0]

    if not customer_id:
        customer = stripe.Customer.create(email=email) if email else stripe.Customer.create()
        customer_id = customer["id"]

    with _db_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            insert into public.app_stripe_customers(customer_id, user_id, email)
            values (%s, %s, %s)
            on conflict (customer_id) do update
               set user_id = excluded.user_id,
                   email = coalesce(excluded.email, public.app_stripe_customers.email),
                   updated_at = now()
            """,
            (customer_id, user_id, email),
        )
        conn.commit()

    return customer_id


class CheckoutReq(BaseModel):
    plan: Literal["plus_monthly", "plus_yearly", "pro_monthly", "pro_yearly"]
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None


def _iso(ts: Optional[dt.datetime]) -> Optional[str]:
    if not ts:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=dt.timezone.utc)
    return ts.isoformat()


@router.post("/checkout")
def create_checkout_session(payload: CheckoutReq, request: Request, _: None = Depends(require_supabase_jwt)):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Missing user_id")

    if not STRIPE_API_KEY:
        raise HTTPException(status_code=500, detail="STRIPE_API_KEY not configured")
    stripe.api_key = STRIPE_API_KEY

    price_id = PRICE_MAP.get(payload.plan)
    if payload.plan not in PRICE_MAP:
        raise HTTPException(status_code=400, detail=f"Unknown plan '{payload.plan}'")
    if not price_id:
        raise HTTPException(status_code=500, detail=f"Stripe price not configured for '{payload.plan}'")

    success_url = payload.success_url or SUCCESS_URL
    cancel_url = payload.cancel_url or CANCEL_URL
    if not success_url or not cancel_url:
        raise HTTPException(status_code=500, detail="Checkout success/cancel URL not configured")

    email = _get_user_email(user_id)
    customer_id = _get_or_create_customer(email, user_id)

    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            customer=customer_id,
            metadata={"user_id": user_id},
            subscription_data={"metadata": {"user_id": user_id}},
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            allow_promotion_codes=True,
        )
    except stripe.error.StripeError as exc:
        logger.exception("stripe checkout session failed", extra={"user_id": user_id})
        raise HTTPException(status_code=502, detail=f"Stripe error: {exc.user_message or str(exc)}") from exc

    return {"ok": True, "url": session["url"], "session_id": session["id"]}


@router.get("/entitlements")
def get_entitlements(request: Request, _: None = Depends(require_supabase_jwt)):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Missing user_id")

    email = _get_user_email(user_id)
    rows, entitlements_user_id, matched_via = _get_entitlement_rows(user_id, email)
    if matched_via != "direct":
        logger.info(
            "billing entitlements resolved via email mapping",
            extra={
                "request_user_id": user_id,
                "entitlements_user_id": entitlements_user_id,
                "email": email,
            },
        )
    entitlements = [
        {
            "key": row[0],
            "term": row[1],
            "is_active": row[2],
            "started_at": _iso(row[3]),
            "expires_at": _iso(row[4]),
            "updated_at": _iso(row[5]),
        }
        for row in rows
    ]

    return {
        "ok": True,
        "user_id": user_id,
        "email": email,
        "entitlements": entitlements,
        "matched_via": matched_via,
        "entitlements_user_id": entitlements_user_id,
    }
