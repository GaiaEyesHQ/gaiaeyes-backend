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
REVENUECAT_WEBHOOK_AUTHORIZATION = os.environ.get("REVENUECAT_WEBHOOK_AUTHORIZATION", "").strip()
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


def _map_price_to_entitlement(price_id: str, provider: str = "stripe") -> Tuple[str, str]:
    """
    Returns (entitlement_key, term) for a provider product/price id based on public.app_price_map.
    """
    with _db_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            select entitlement_key, term
            from public.app_price_map
            where price_id = %s and provider = %s
            """,
            (price_id, provider),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=400, detail=f"Unknown {provider} product mapping: {price_id}")
        return row[0], row[1]


def _upsert_user_entitlement(
    user_id: str,
    entitlement_key: str,
    term: str,
    expires_at: Optional[dt.datetime],
    source: str = "stripe",
) -> None:
    """
    Calls public.upsert_user_entitlement(...).
    """
    with _db_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "select public.upsert_user_entitlement(%s, %s, %s, %s, %s)",
            (user_id, entitlement_key, source, term, expires_at),
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


def _verify_revenuecat_authorization(auth_header: Optional[str]) -> None:
    """
    RevenueCat webhook destinations can send a configured Authorization header.
    Treat that value as a shared secret when REVENUECAT_WEBHOOK_AUTHORIZATION is set.
    """
    if not REVENUECAT_WEBHOOK_AUTHORIZATION:
        return
    received = (auth_header or "").strip()
    expected = REVENUECAT_WEBHOOK_AUTHORIZATION
    allowed = {expected}
    if not expected.lower().startswith("bearer "):
        allowed.add(f"Bearer {expected}")
    if not any(hmac.compare_digest(received, candidate) for candidate in allowed):
        raise HTTPException(status_code=401, detail="Invalid RevenueCat authorization")


def _datetime_from_revenuecat_ms(value: object) -> Optional[dt.datetime]:
    if not isinstance(value, (int, float)) or value <= 0:
        return None
    return dt.datetime.fromtimestamp(float(value) / 1000.0, tz=dt.timezone.utc)


def _revenuecat_term_from_product(product_id: Optional[str], fallback: str = "monthly") -> str:
    text = (product_id or "").lower()
    if "year" in text or "annual" in text:
        return "yearly"
    if "month" in text:
        return "monthly"
    return fallback


def _revenuecat_entitlements(event: dict) -> list[str]:
    raw_ids = event.get("entitlement_ids")
    if isinstance(raw_ids, list):
        ids = [str(item).strip().lower() for item in raw_ids if str(item).strip()]
        if ids:
            return ids

    raw_id = event.get("entitlement_id")
    if isinstance(raw_id, str) and raw_id.strip():
        return [raw_id.strip().lower()]

    product_id = str(event.get("product_id") or "").lower()
    if "pro" in product_id:
        return ["pro"]
    if "plus" in product_id:
        return ["plus"]
    return []


def _revenuecat_user_id(event: dict) -> Optional[str]:
    candidates = [
        event.get("app_user_id"),
        event.get("original_app_user_id"),
    ]
    aliases = event.get("aliases")
    if isinstance(aliases, list):
        candidates.extend(aliases)
    for value in candidates:
        if value and _looks_like_uuid(str(value)):
            return str(value)
    return None


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

            _upsert_user_entitlement(user_id, entitlement_key, term, expires_at, source="stripe")
            return {"ok": True, "action": "upsert", "entitlement": entitlement_key, "term": term, "user_id": user_id}

        if evt_type == "customer.subscription.deleted":
            # Immediate termination
            _upsert_user_entitlement(user_id, entitlement_key, term, dt.datetime.now(dt.timezone.utc), source="stripe")
            return {"ok": True, "action": "cancel", "entitlement": entitlement_key, "user_id": user_id}

    # Unhandled event types are acknowledged to avoid retries.
    return {"ok": True, "ignored": evt_type}


@router.post("/webhooks/revenuecat")
async def revenuecat_webhook(request: Request, authorization: Optional[str] = Header(None, alias="Authorization")):
    """
    Handle RevenueCat subscription lifecycle events for iOS purchases.
    RevenueCat should be configured with app_user_id equal to the Supabase user UUID.
    """
    _verify_revenuecat_authorization(authorization)

    raw = await request.body()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event = payload.get("event") if isinstance(payload, dict) else None
    if not isinstance(event, dict):
        raise HTTPException(status_code=400, detail="Missing RevenueCat event")

    evt_type = str(event.get("type") or "").upper()
    product_id = str(event.get("product_id") or "")
    user_id = _revenuecat_user_id(event)
    if not user_id:
        return {"ok": True, "ignored": evt_type, "reason": "no_uuid_app_user_id"}

    entitlement_keys = _revenuecat_entitlements(event)
    if not entitlement_keys and product_id:
        try:
            key, term = _map_price_to_entitlement(product_id, provider="revenuecat")
            entitlement_keys = [key]
        except HTTPException:
            entitlement_keys = []
    if not entitlement_keys:
        return {"ok": True, "ignored": evt_type, "reason": "no_entitlement_mapping", "user_id": user_id}

    term = _revenuecat_term_from_product(product_id)
    expires_at = _datetime_from_revenuecat_ms(event.get("expiration_at_ms"))
    if product_id:
        try:
            _, mapped_term = _map_price_to_entitlement(product_id, provider="revenuecat")
            term = mapped_term or term
        except HTTPException:
            pass

    if evt_type == "EXPIRATION":
        expires_at = expires_at or dt.datetime.now(dt.timezone.utc)

    updated: list[str] = []
    for entitlement_key in entitlement_keys:
        if entitlement_key not in {"plus", "pro"}:
            continue
        _upsert_user_entitlement(
            user_id=user_id,
            entitlement_key=entitlement_key,
            term=term,
            expires_at=expires_at,
            source="revenuecat",
        )
        updated.append(entitlement_key)

    if not updated:
        return {"ok": True, "ignored": evt_type, "reason": "unsupported_entitlement", "user_id": user_id}

    return {
        "ok": True,
        "event": evt_type,
        "action": "upsert",
        "entitlements": updated,
        "term": term,
        "user_id": user_id,
        "expires_at": expires_at.isoformat() if expires_at else None,
    }


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

@router.get("/entitlements/health")
def entitlements_health(user_id: str):
    """
    Lightweight entitlement check for WP/iOS.
    Returns a simple tier ('free' | 'plus' | 'pro') and flags for each entitlement.
    Prefers the view public.app_user_entitlements_active; falls back to base table if needed.
    """
    rows = []
    # Try the active view first
    try:
        with _db_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                select entitlement_key, expires_at
                from public.app_user_entitlements_active
                where user_id = %s and is_active = true
                """,
                (user_id,),
            )
            rows = cur.fetchall()
    except Exception:
        # Fallback if the view doesn't exist; treat null expires_at as active
        with _db_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                select entitlement_key, expires_at
                from public.app_user_entitlements
                where user_id = %s
                  and coalesce(expires_at, now() + interval '100 years') > now()
                """,
                (user_id,),
            )
            rows = cur.fetchall()

    flags = {"plus": False, "pro": False}
    exp = {}
    for key, expires_at in rows:
        k = str(key).lower()
        if k in flags:
            flags[k] = True
            exp[k] = expires_at.isoformat() if expires_at else None

    tier = "free"
    if flags.get("pro"):
        tier = "pro"
    elif flags.get("plus"):
        tier = "plus"

    return {
        "ok": True,
        "user_id": user_id,
        "tier": tier,
        "entitlements": flags,
        "expires_at": exp,
    }


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
        source="manual",
    )
    return {"ok": True}
