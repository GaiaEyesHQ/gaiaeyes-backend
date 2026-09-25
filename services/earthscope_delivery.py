"""At-most-one automatic Meta attempt per current day/channel.

The intent is durable BEFORE Meta is called. An uncertain request or receipt
never authorizes another publish; an operator must reconcile the platform.
"""
import os
from uuid import uuid4
from urllib.parse import urlsplit
import requests
from services.earthscope_writer_contract import require, sha256, SHA_RE


class DeliveryAttempt:
    def __init__(self, post, platform, kind, environ=None, session=None):
        env = os.environ if environ is None else environ
        require(platform in {"ig", "fb"} and kind in {"carousel", "reel"}, "unsupported_primary_delivery")
        self.session = session or requests.Session()
        self.url = (env.get("SUPABASE_REST_URL") or env.get("SUPABASE_URL", "").rstrip("/") + "/rest/v1").rstrip("/") + "/earthscope_delivery_attempts"
        parsed = urlsplit(self.url)
        key = env.get("SUPABASE_SERVICE_ROLE_KEY") or env.get("SUPABASE_SERVICE_KEY")
        require(parsed.scheme == "https" and parsed.hostname and not parsed.username
                and not parsed.password and not parsed.query and not parsed.fragment and key, "publisher_unconfigured")
        self.headers = {"apikey": key, "Authorization": "Bearer " + key,
                        "Accept-Profile": "content", "Content-Profile": "content"}
        destination = env.get("IG_USER_ID" if platform == "ig" else "FB_PAGE_ID")
        revision = env.get("EARTHSCOPE_MEDIA_REVISION", "")
        require(destination and SHA_RE.fullmatch(revision), "delivery_unconfigured")
        self.intent = {"day": post["day"], "channel": platform + "_" + kind,
                       "post_sha256": sha256(post), "destination_sha256": sha256(destination),
                       "media_revision": revision, "attempt_id": str(uuid4()), "state": "reserved"}
        self.params = {"day": "eq." + post["day"], "channel": "eq." + self.intent["channel"]}

    def begin(self):
        # Ignore conflicts rather than replacing an existing/ambiguous attempt.
        response = self.session.post(self.url, params={"on_conflict": "day,channel"},
            headers={**self.headers, "Prefer": "resolution=ignore-duplicates,return=representation"},
            json=[self.intent], timeout=(5, 20), allow_redirects=False)
        require(response.status_code in {200, 201}, "delivery_reservation_unconfirmed")
        response = self.session.get(self.url, params={**self.params, "select": "*", "limit": "2"},
            headers=self.headers, timeout=(5, 20), allow_redirects=False)
        require(response.status_code == 200, "delivery_reservation_unconfirmed")
        rows = response.json()
        require(isinstance(rows, list) and len(rows) == 1, "delivery_reservation_unconfirmed")
        row = rows[0]
        require(all(row.get(k) == self.intent[k] for k in ("post_sha256", "destination_sha256")), "delivery_conflict")
        if row["state"] == "published":
            return False
        require(row["attempt_id"] == self.intent["attempt_id"] and row["state"] == "reserved",
                "delivery_requires_reconciliation")
        return True

    def finish(self, result):
        state = "published" if result.get("success") is True and result.get("post_id") else "uncertain"
        receipt = {"state": state, "post_id": str(result["post_id"]) if state == "published" else None}
        response = self.session.patch(self.url,
            params={**self.params, "attempt_id": "eq." + self.intent["attempt_id"], "state": "eq.reserved"},
            headers={**self.headers, "Prefer": "return=representation"}, json=receipt,
            timeout=(5, 20), allow_redirects=False)
        require(response.status_code == 200, "delivery_receipt_unconfirmed")
        rows = response.json()
        require(isinstance(rows, list) and len(rows) == 1
                and all(rows[0].get(k) == v for k, v in receipt.items()), "delivery_receipt_unconfirmed")
        require(state == "published", "delivery_requires_reconciliation")
