# api/webhooks.py
from __future__ import annotations

import os
import hmac
import hashlib
import json
import datetime as dt
from typing import Optional, Tuple
import uuid

from fastapi import APIRouter, Header, HTTPException, Request, Depends, Query
from pydantic import BaseModel
import psycopg

router = APIRouter()

def _looks_like_uuid(s: str) -> bool:
    try:
        uuid.UUID(str(s))
        return True
    except Exception:
        return False

# --- Environment ---
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()
SUPABASE_DB_URL = os.environ.get("SUPABASE_DB_URL", os.environ.get("DATABASE_URL", "")).strip()

if not SUPABASE_DB_URL:
    # We keep the router loadable even if DB is missing (for local dev),
    # but DB-backed endpoints will raise a clear error.
    pass


# --- DB helpers ---
def _db_conn():
    if not SUPABASE_DB_URL:
        raise HTTPException(status_code=500, detail="Server DB not configured (SUPABASE_DB_URL)")
    return psycopg.connect(SUPABASE_DB_URL)


def _map_price_to_entitlement(price_id: str) -> Tuple[str, str]:
    """
    Returns (entitlement_key, term) for a Stripe price_id based on public.app_price_map.
    """
    with _db_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            select entitlement_key, term
            from public.app_price_map
            where price_id = %s and provider = 'stripe'
            """,
            (price_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=400, detail=f"Unknown price_id mapping: {price_id}")
        return row[0], row[1]


def _upsert_user_entitlement(
    user_id: str,
    entitlement_key: str,
    term: str,
    expires_at: Optional[dt.datetime],
) -> None:
    """
    Calls public.upsert_user_entitlement(...).
    """
    with _db_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "select public.upsert_user_entitlement(%s, %s, %s, %s, %s)",
            (user_id, entitlement_key, "stripe", term, expires_at),
        )
        conn.commit()


def _upsert_customer_map(customer_id: str, user_id: Optional[str], email: Optional[str]) -> None:
    """
    Record (or update) the Stripe customer_id → app user mapping.
    Expects table:
      public.app_stripe_customers(
        customer_id text primary key,
        user_id uuid null,
        email text null,
        created_at timestamptz default now(),
        updated_at timestamptz default now()
      )
    """
    with _db_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            insert into public.app_stripe_customers(customer_id, user_id, email)
            values (%s, %s, %s)
            on conflict (customer_id) do update
               set user_id = coalesce(excluded.user_id, public.app_stripe_customers.user_id),
                   email   = coalesce(excluded.email, public.app_stripe_customers.email),
                   updated_at = now()
            """,
            (customer_id, user_id, email),
        )
        conn.commit()


def _resolve_user_id_from_customer(customer_id: str) -> Optional[str]:
    """
    Look up app user_id by Stripe customer_id, if we've seen a completed checkout.
    """
    with _db_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "select user_id from public.app_stripe_customers where customer_id = %s",
            (customer_id,),
        )
        row = cur.fetchone()
    return row[0] if row else None


def _resolve_user_id_from_metadata(obj: dict) -> Optional[str]:
    """
    Prefer a real app user UUID passed via Stripe metadata:
      - subscription_data[metadata][user_id] (preferred)
      - session metadata.user_id
    We intentionally do NOT trust client_reference_id as a user_id (it may be "wp-123").
    """
    md = obj.get("metadata") or {}
    uid = md.get("user_id")
    if uid and _looks_like_uuid(uid):
        return str(uid)
    return None

def _find_user_uuid_by_email(email: Optional[str]) -> Optional[str]:
    if not email:
        return None
    with _db_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            select id::text
            from auth.users
            where lower(email) = lower(%s)
            order by created_at desc
            limit 1
            """,
            (email,),
        )
        row = cur.fetchone()
    return row[0] if row else None


# --- Stripe signature verification (no SDK) ---
def _verify_stripe_signature(raw_body: bytes, sig_header: Optional[str]) -> None:
    """
    Minimal verification compatible with Stripe's 'Stripe-Signature' header and
    endpoint signing secret. We compute HMAC-SHA256 over 't.{raw_body}' and
    compare against 'v1' in the header.
    """
    if not STRIPE_WEBHOOK_SECRET:
        # Accept if not configured (local dev), but warn by raising 500 in prod-like envs.
        raise HTTPException(status_code=500, detail="STRIPE_WEBHOOK_SECRET not configured")

    if not sig_header:
        raise HTTPException(status_code=400, detail="Missing Stripe-Signature header")

    # Parse header: e.g. "t=1700000000,v1=abcdef...,v0=..."
    parts = dict(kv.split("=", 1) for kv in sig_header.split(",") if "=" in kv)
    t = parts.get("t")
    v1 = parts.get("v1")
    if not t or not v1:
        raise HTTPException(status_code=400, detail="Malformed Stripe-Signature header")

    signed_payload = f"{t}.{raw_body.decode('utf-8')}".encode("utf-8")
    mac = hmac.new(STRIPE_WEBHOOK_SECRET.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    # constant-time compare
    if not hmac.compare_digest(mac, v1):
        raise HTTPException(status_code=401, detail="Invalid Stripe signature")


# --- Lightweight models kept for your existing hooks ---
class AlertPayload(BaseModel):
    kind: str
    rule: str
    payload: dict


class SocialPayload(BaseModel):
    text: str


# --- Existing demo hooks (kept) ---
@router.post("/hooks/earthscope")
async def earthscope_hook(body: AlertPayload, x_signature: str | None = Header(None)):
    # NOTE: If you still want HMAC over raw body for this path, use a middleware
    # that captures request.state.raw_body and verifies with your GA secret.
    return {"ok": True}


@router.post("/hooks/social")
async def social_hook(body: SocialPayload, x_signature: str | None = Header(None)):
    return {"ok": True, "accepted": body.text}


# --- Stripe webhook for subscriptions ---
@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request, stripe_signature: Optional[str] = Header(None, alias="Stripe-Signature")):
    """
    Handle subscription lifecycle events without the Stripe SDK.
    Supported types:
      - customer.subscription.created
      - customer.subscription.updated
      - customer.subscription.deleted
    """
    raw = await request.body()
    _verify_stripe_signature(raw, stripe_signature)

    try:
        event = json.loads(raw.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    evt_type = event.get("type") or ""
    obj = (event.get("data") or {}).get("object") or {}

    # Map Checkout Session -> (customer_id, user_id)
    if evt_type == "checkout.session.completed":
        # Session carries: customer, client_reference_id, metadata, etc.
        customer_id = obj.get("customer")
        if not customer_id:
            raise HTTPException(status_code=400, detail="checkout.session.completed missing 'customer'")

        # Try to get a real app user UUID from metadata
        user_id = _resolve_user_id_from_metadata(obj)

        # Fallback: map by email (Stripe includes customer_details.email or customer_email)
        email = None
        cd = obj.get("customer_details") or {}
        if isinstance(cd, dict):
            email = cd.get("email")
        if not email:
            email = obj.get("customer_email")

        if not user_id and email:
            user_id = _find_user_uuid_by_email(email)

        # Always upsert mapping; user_id may still be None (to be filled later when the user signs in)
        _upsert_customer_map(customer_id, user_id, email)
        return {"ok": True, "mapped": True, "event": evt_type, "customer": customer_id, "user_id": user_id, "email": email}

    # We only handle subscription events that include items[].price.id inline.
    if evt_type.startswith("customer.subscription."):
        # Resolve the app user
        user_id = _resolve_user_id_from_metadata(obj)
        if not user_id:
            cust = obj.get("customer")
            if cust:
                user_id = _resolve_user_id_from_customer(cust)
        if not user_id:
            raise HTTPException(
                status_code=400,
                detail="No user mapping found for subscription. Ensure checkout.session.completed mapped the customer (or user has signed in so email→UUID can be resolved).",
            )

        # Extract price_id from the first item
        items = (obj.get("items") or {}).get("data") or []
        if not items or not (items[0].get("price") or {}).get("id"):
            raise HTTPException(status_code=400, detail="No subscription items/price available in event")

        price_id = items[0]["price"]["id"]
        entitlement_key, term = _map_price_to_entitlement(price_id)

        # Expiration from period end (epoch seconds) when available
        expires_at: Optional[dt.datetime] = None
        if evt_type in ("customer.subscription.created", "customer.subscription.updated"):
            cpe = obj.get("current_period_end")
            if isinstance(cpe, (int, float)) and cpe > 0:
                expires_at = dt.datetime.utcfromtimestamp(int(cpe)).replace(tzinfo=dt.timezone.utc)

            _upsert_user_entitlement(user_id, entitlement_key, term, expires_at)
            return {"ok": True, "action": "upsert", "entitlement": entitlement_key, "term": term, "user_id": user_id}

        if evt_type == "customer.subscription.deleted":
            # Immediate termination
            _upsert_user_entitlement(user_id, entitlement_key, term, dt.datetime.now(dt.timezone.utc))
            return {"ok": True, "action": "cancel", "entitlement": entitlement_key, "user_id": user_id}

    # Unhandled event types are acknowledged to avoid retries.
    return {"ok": True, "ignored": evt_type}


# --- Minimal entitlements API ---
class ManualGrant(BaseModel):
    user_id: str
    entitlement_key: str  # 'plus' | 'pro'
    term: Optional[str] = None  # 'monthly' | 'yearly' | null
    expires_at: Optional[dt.datetime] = None
    admin_token: str


@router.get("/entitlements/{user_id}")
def get_entitlements(user_id: str):
    """
    Admin/Server-only helper. Prefer using Supabase REST/RPC from clients.
    """
    with _db_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            select user_id, entitlement_key, source, term, started_at, expires_at, updated_at
            from public.app_user_entitlements
            where user_id = %s
            order by entitlement_key
            """,
            (user_id,),
        )
        rows = cur.fetchall()
    return {"ok": True, "user_id": user_id, "entitlements": [
        {
            "user_id": r[0],
            "entitlement_key": r[1],
            "source": r[2],
            "term": r[3],
            "started_at": r[4],
            "expires_at": r[5],
            "updated_at": r[6],
        } for r in rows
    ]}


@router.post("/entitlements/manual-grant")
def manual_grant(payload: ManualGrant):
    """
    Manual override (for support). Protect with an ADMIN_TOKEN env var.
    """
    admin_token_env = os.environ.get("ADMIN_TOKEN", "")
    if not admin_token_env or payload.admin_token != admin_token_env:
        raise HTTPException(status_code=401, detail="Invalid admin token")

    _upsert_user_entitlement(
        user_id=payload.user_id,
        entitlement_key=payload.entitlement_key,
        term=payload.term or "monthly",
        expires_at=payload.expires_at,
    )
    return {"ok": True}