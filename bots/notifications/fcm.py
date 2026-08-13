from __future__ import annotations

import json
import os
from typing import Any, Dict

import requests
from google.auth.transport.requests import Request
from google.oauth2 import service_account


_FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"


class FcmClient:
    def __init__(self, project_id: str, credentials) -> None:
        self.project_id = project_id
        self.credentials = credentials

    @classmethod
    def from_environment(cls) -> "FcmClient":
        raw = os.getenv("FCM_SERVICE_ACCOUNT_JSON", "").strip()
        if not raw:
            raise RuntimeError("Missing required environment variable: FCM_SERVICE_ACCOUNT_JSON")
        info = json.loads(raw)
        project_id = str(os.getenv("FCM_PROJECT_ID") or info.get("project_id") or "").strip()
        if not project_id:
            raise RuntimeError("FCM project id is missing")
        credentials = service_account.Credentials.from_service_account_info(
            info,
            scopes=[_FCM_SCOPE],
        )
        return cls(project_id=project_id, credentials=credentials)

    def send(
        self,
        *,
        device_token: str,
        title: str,
        body: str,
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        self.credentials.refresh(Request())
        response = requests.post(
            f"https://fcm.googleapis.com/v1/projects/{self.project_id}/messages:send",
            headers={
                "Authorization": f"Bearer {self.credentials.token}",
                "Content-Type": "application/json; UTF-8",
            },
            json={
                "message": {
                    "token": device_token,
                    "data": {
                        "title": title,
                        "body": body,
                        **{str(key): str(value) for key, value in data.items() if value is not None},
                    },
                    "android": {"priority": "high"},
                }
            },
            timeout=20,
        )
        raw_body = response.text
        try:
            parsed = response.json()
        except ValueError:
            parsed = {}
        return {
            "ok": response.ok,
            "status_code": response.status_code,
            "body": parsed,
            "raw_body": raw_body,
        }
