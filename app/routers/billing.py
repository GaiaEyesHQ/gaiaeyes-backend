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

    with _db_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            select entitlement_key, term, is_active, started_at, expires_at, updated_at
            from public.app_user_entitlements
            where user_id = %s
            order by entitlement_key
            """,
            (user_id,),
        )
        rows = cur.fetchall()

    email = _get_user_email(user_id)
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

    return {"ok": True, "user_id": user_id, "email": email, "entitlements": entitlements}
