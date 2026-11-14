"""Reusable, brand-scoped Meta image publisher.

No Gaia Eyes content queries, global Page IDs, or implicit publishing.
The legacy EarthScope poster is deliberately left unchanged.
"""
from dataclasses import dataclass
from typing import Callable
import requests

from bots.shared_social.brand_config import BrandConfig


@dataclass(frozen=True)
class PublishResult:
    brand: str
    platform: str
    status: str
    post_id: str | None = None


class MetaPublishError(RuntimeError):
    pass


class MetaClient:
    def __init__(self, config: BrandConfig, *, graph_version="v24.0",
                 request: Callable | None = None):
        self.config = config
        self.graph_base = f"https://graph.facebook.com/{graph_version}"
        self._request = request or requests.request

    def _call(self, method, path, data=None, params=None):
        # Tokens are intentionally never included in raised exceptions.
        payload = dict(data or {})
        query = dict(params or {})
        (query if method == "GET" else payload)["access_token"] = self.config.access_token
        try:
            response = self._request(method, f"{self.graph_base}/{path}",
                                     data=payload if method != "GET" else None,
                                     params=query if method == "GET" else None,
                                     timeout=30)
            response.raise_for_status()
            body = response.json()
            if not isinstance(body, dict) or body.get("error"):
                raise MetaPublishError("Meta returned an unsuccessful response")
            return body
        except (requests.RequestException, ValueError) as exc:
            raise MetaPublishError("Meta request failed; inspect secure execution logs") from None

    def publish_facebook_photo(self, image_url: str, caption: str, *, approved=False, dry_run=True):
        if not image_url.startswith("https://"):
            raise ValueError("Image must have a public HTTPS URL")
        if dry_run:
            return PublishResult(self.config.brand, "facebook", "preview")
        if not approved:
            raise PermissionError("Live publishing requires explicit approval")
        result = self._call("POST", f"{self.config.facebook_page_id}/photos",
                            data={"url": image_url, "caption": caption})
        return PublishResult(self.config.brand, "facebook", "published", result.get("post_id") or result.get("id"))

    def publish_instagram_photo(self, image_url: str, caption: str, *, approved=False, dry_run=True):
        if not image_url.startswith("https://"):
            raise ValueError("Image must have a public HTTPS URL")
        if dry_run:
            return PublishResult(self.config.brand, "instagram", "preview")
        if not approved:
            raise PermissionError("Live publishing requires explicit approval")
        user_id = self.config.instagram_user_id
        container = self._call("POST", f"{user_id}/media",
                               data={"image_url": image_url, "caption": caption})
        if not container.get("id"):
            raise MetaPublishError("Instagram did not return a creation ID")
        # Single-image containers can require processing time; caller should
        # implement status polling before enabling this path in production.
        raise MetaPublishError("Instagram live publishing disabled pending container polling")
