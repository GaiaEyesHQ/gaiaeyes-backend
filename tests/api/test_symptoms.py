from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, List, Optional
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

ROOT = Path(__file__).resolve().parents[2]
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import app
from app.db import get_db, symptoms as symptoms_db

UTC = timezone.utc


class FakeSymptomStore:
    def __init__(self) -> None:
        self.events: List[dict] = []
        self.counter = 0
        self.now = datetime(2024, 4, 2, 12, 0, tzinfo=UTC)

    def _next_id(self) -> str:
        self.counter += 1
        return f"evt-{self.counter}"

    def _ensure_ts(self, ts: Optional[datetime]) -> datetime:
        if ts is None:
            return self.now
        if ts.tzinfo is None:
            return ts.replace(tzinfo=UTC)
        return ts.astimezone(UTC)

    def insert(
        self,
        user_id: str,
        *,
        symptom_code: str,
        ts_utc: Optional[datetime] = None,
        severity: Optional[int] = None,
        free_text: Optional[str] = None,
        tags: Optional[Iterable[str]] = None,
    ) -> dict:
        ts = self._ensure_ts(ts_utc)
        event = {
            "id": self._next_id(),
            "user_id": user_id,
            "symptom_code": symptom_code,
            "ts_utc": ts,
            "severity": severity,
            "free_text": free_text,
            "tags": list(tags or []),
        }
        self.events.append(event)
        return {"id": event["id"], "ts_utc": ts.isoformat()}

    def today(self, user_id: str) -> List[dict]:
        today = self.now.date()
        results: List[dict] = []
        for event in sorted(self.events, key=lambda e: e["ts_utc"], reverse=True):
            if event["user_id"] != user_id:
                continue
            if event["ts_utc"].date() != today:
                continue
            results.append(
                {
                    "symptom_code": event["symptom_code"],
                    "ts_utc": event["ts_utc"].isoformat(),
                    "severity": event["severity"],
                    "free_text": event["free_text"],
                }
            )
        return results

    def daily(self, user_id: str, days: int) -> List[dict]:
        cutoff = self.now - timedelta(days=days - 1)
        grouped: dict[tuple[str, str], List[dict]] = {}
        for event in self.events:
            if event["user_id"] != user_id:
                continue
            if event["ts_utc"] < cutoff:
                continue
            key = (event["ts_utc"].date().isoformat(), event["symptom_code"])
            grouped.setdefault(key, []).append(event)

        rows: List[dict] = []
        for (day, code), events in grouped.items():
            severities = [e["severity"] for e in events if e["severity"] is not None]
            mean = sum(severities) / len(severities) if severities else None
            last_ts = max(e["ts_utc"] for e in events)
            rows.append(
                {
                    "day": day,
                    "symptom_code": code,
                    "events": len(events),
                    "mean_severity": mean,
                    "last_ts": last_ts.isoformat(),
                }
            )

        rows.sort(key=lambda r: r["symptom_code"])
        rows.sort(key=lambda r: datetime.fromisoformat(r["day"]), reverse=True)
        return rows

    def diag(self, user_id: str, days: int) -> List[dict]:
        cutoff = self.now - timedelta(days=days - 1)
        grouped: dict[str, List[dict]] = {}
        for event in self.events:
            if event["user_id"] != user_id:
                continue
            if event["ts_utc"] < cutoff:
                continue
            grouped.setdefault(event["symptom_code"], []).append(event)

        rows: List[dict] = []
        for code, events in grouped.items():
            last_ts = max(e["ts_utc"] for e in events)
            rows.append(
                {
                    "symptom_code": code,
                    "events": len(events),
                    "last_ts": last_ts.isoformat(),
                }
            )
        rows.sort(key=lambda r: r["symptom_code"])
        return rows


@pytest.fixture(autouse=True)
def override_dev_bearer():
    from app import db

    original = db.settings.DEV_BEARER
    db.settings.DEV_BEARER = "test-token"
    try:
        yield
    finally:
        db.settings.DEV_BEARER = original


@pytest.fixture(autouse=True)
def override_db_dependency():
    async def _fake_db():
        yield object()

    app.dependency_overrides[get_db] = _fake_db
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def fake_store(monkeypatch):
    store = FakeSymptomStore()

    async def _insert(conn, user_id, **kwargs):
        return store.insert(user_id, **kwargs)

    async def _today(conn, user_id):
        return store.today(user_id)

    async def _daily(conn, user_id, days):
        return store.daily(user_id, days)

    async def _diag(conn, user_id, days):
        return store.diag(user_id, days)

    async def _codes(conn, include_inactive=True):  # noqa: ARG001
        return [
            {
                "symptom_code": "NERVE_PAIN",
                "label": "Nerve pain",
                "description": "Pins/needles, burning, or nerve pain",
                "is_active": True,
            },
            {
                "symptom_code": "HEADACHE",
                "label": "Headache",
                "description": "Headache or migraine",
                "is_active": True,
            },
            {
                "symptom_code": "OTHER",
                "label": "Other",
                "description": "Other symptom (use notes)",
                "is_active": True,
            },
        ]

    monkeypatch.setattr(symptoms_db, "insert_symptom_event", _insert)
    monkeypatch.setattr(symptoms_db, "fetch_symptoms_today", _today)
    monkeypatch.setattr(symptoms_db, "fetch_daily_summary", _daily)
    monkeypatch.setattr(symptoms_db, "fetch_diagnostics", _diag)
    monkeypatch.setattr(symptoms_db, "fetch_symptom_codes", _codes)

    return store


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_daily_aggregation_flow(client: AsyncClient, fake_store: FakeSymptomStore):
    user_id = str(uuid4())
    headers = {
        "Authorization": "Bearer test-token",
        "X-Dev-UserId": user_id,
    }

    event_payloads = [
        {
            "symptom_code": "nerve_pain",
            "ts_utc": "2024-04-01T08:00:00Z",
            "severity": 3,
        },
        {
            "symptom_code": "nerve_pain",
            "ts_utc": "2024-04-01T15:30:00Z",
            "severity": 4,
        },
        {
            "symptom_code": "headache",
            "ts_utc": "2024-04-02T07:45:00Z",
        },
    ]

    for payload in event_payloads:
        response = await client.post("/v1/symptoms", json=payload, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data.get("error") is None
        assert data.get("data") is not None
        assert "id" in data["data"]
        assert data["data"]["ts_utc"].endswith("Z") or data["data"]["ts_utc"].endswith("+00:00")

    today = await client.get("/v1/symptoms/today", headers=headers)
    assert today.status_code == 200
    today_payload = today.json()
    assert today_payload["ok"] is True
    assert len(today_payload["data"]) == 1
    assert today_payload["data"][0]["symptom_code"] == "HEADACHE"

    daily = await client.get("/v1/symptoms/daily?days=3", headers=headers)
    assert daily.status_code == 200
    daily_rows = daily.json()
    assert daily_rows["ok"] is True
    assert daily_rows["data"] == [
        {
            "day": "2024-04-02",
            "symptom_code": "HEADACHE",
            "events": 1,
            "mean_severity": None,
            "last_ts": "2024-04-02T07:45:00+00:00",
        },
        {
            "day": "2024-04-01",
            "symptom_code": "NERVE_PAIN",
            "events": 2,
            "mean_severity": 3.5,
            "last_ts": "2024-04-01T15:30:00+00:00",
        },
    ]

    diag = await client.get("/v1/symptoms/diag?days=3", headers=headers)
    assert diag.status_code == 200
    diag_rows = diag.json()
    assert diag_rows["ok"] is True
    assert diag_rows["data"] == [
        {
            "symptom_code": "HEADACHE",
            "events": 1,
            "last_ts": "2024-04-02T07:45:00+00:00",
        },
        {
            "symptom_code": "NERVE_PAIN",
            "events": 2,
            "last_ts": "2024-04-01T15:30:00+00:00",
        },
    ]
