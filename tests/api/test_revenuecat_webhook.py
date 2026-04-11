from __future__ import annotations

from pathlib import Path
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.api import webhooks


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(webhooks.router, prefix="/v1")
    return TestClient(app)


def test_revenuecat_webhook_upserts_uuid_entitlement(monkeypatch):
    writes: list[dict] = []

    def fake_upsert(user_id, entitlement_key, term, expires_at, source="stripe"):
        writes.append(
            {
                "user_id": user_id,
                "entitlement_key": entitlement_key,
                "term": term,
                "expires_at": expires_at,
                "source": source,
            }
        )

    monkeypatch.setattr(webhooks, "REVENUECAT_WEBHOOK_AUTHORIZATION", "test-secret")
    monkeypatch.setattr(webhooks, "_upsert_user_entitlement", fake_upsert)

    user_id = "e20a3e9e-1fc2-41ad-b6f7-656668310d13"
    resp = _client().post(
        "/v1/webhooks/revenuecat",
        headers={"Authorization": "test-secret"},
        json={
            "event": {
                "type": "INITIAL_PURCHASE",
                "app_user_id": user_id,
                "product_id": "com.gaiaeyes.pro.yearly",
                "entitlement_ids": ["pro"],
                "expiration_at_ms": 1_800_000_000_000,
            }
        },
    )

    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert len(writes) == 1
    assert writes[0]["user_id"] == user_id
    assert writes[0]["entitlement_key"] == "pro"
    assert writes[0]["term"] == "yearly"
    assert writes[0]["source"] == "revenuecat"
    assert writes[0]["expires_at"].year == 2027


def test_revenuecat_webhook_rejects_bad_authorization(monkeypatch):
    monkeypatch.setattr(webhooks, "REVENUECAT_WEBHOOK_AUTHORIZATION", "test-secret")

    resp = _client().post(
        "/v1/webhooks/revenuecat",
        headers={"Authorization": "wrong"},
        json={"event": {"type": "INITIAL_PURCHASE"}},
    )

    assert resp.status_code == 401


def test_revenuecat_webhook_ignores_non_uuid_app_user_id(monkeypatch):
    monkeypatch.setattr(webhooks, "REVENUECAT_WEBHOOK_AUTHORIZATION", "")

    resp = _client().post(
        "/v1/webhooks/revenuecat",
        json={
            "event": {
                "type": "INITIAL_PURCHASE",
                "app_user_id": "$RCAnonymousID:abc",
                "product_id": "com.gaiaeyes.plus.monthly",
            }
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["reason"] == "no_uuid_app_user_id"
