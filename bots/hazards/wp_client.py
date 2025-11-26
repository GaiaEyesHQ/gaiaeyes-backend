import os
import time
from typing import Any, Dict, List, Optional
import requests


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


class WPClient:
    """
    Minimal WordPress REST client using Application Passwords.
    Expects env:
      WP_SITE_URL        e.g., https://staging2.gaiaeyes.com
      WP_USERNAME        e.g., admin@example.com (user tied to the app password)
      WP_APP_PASSWORD    e.g., abcd efgh ijkl mnop (spaces OK; we strip them)
    """

    def __init__(self) -> None:
        site = _env("WP_SITE_URL")
        if not site.startswith("http"):
            raise RuntimeError("WP_SITE_URL must be an absolute URL (https://...).")
        self.api_base = site.rstrip("/") + "/wp-json/wp/v2"
        self.user = _env("WP_USERNAME")
        self.app_pw = _env("WP_APP_PASSWORD").replace(" ", "")
        if not (self.user and self.app_pw):
            raise RuntimeError("WP_USERNAME and WP_APP_PASSWORD env vars are required.")
        self.session = requests.Session()
        self.session.auth = (self.user, self.app_pw)
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "GaiaEyesHazardsBot/1.0"
        })
        self.timeout = 20

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        url = f"{self.api_base}/{path.lstrip('/')}"
        last_exc = None
        for attempt in range(4):
            try:
                r = self.session.request(method, url, timeout=self.timeout, **kwargs)
                if 200 <= r.status_code < 300:
                    return r
                if r.status_code in (401, 403):
                    snippet = r.text[:200] if r.text else ""
                    raise RuntimeError(f"WP auth failed {r.status_code} on {url}: {snippet}")
                if r.status_code == 404:
                    snippet = r.text[:200] if r.text else ""
                    raise RuntimeError(f"WP route not found {url}: {snippet}")
                if r.status_code in (429, 500, 502, 503, 504):
                    time.sleep(1.5 * (attempt + 1))
                    continue
                snippet = r.text[:200] if r.text else ""
                raise RuntimeError(f"WP error {r.status_code} on {url}: {snippet}")
            except requests.RequestException as e:
                last_exc = e
                time.sleep(1.0 * (attempt + 1))
        if last_exc:
            raise last_exc
        raise RuntimeError(f"WP request failed after retries: {url}")

    def _json(self, r: requests.Response) -> Any:
        ctype = (r.headers.get("Content-Type") or "").lower()
        if "application/json" not in ctype:
            raise RuntimeError(f"Expected JSON, got {ctype} (status {r.status_code}): {r.text[:200]}")
        try:
            return r.json()
        except Exception as e:
            raise RuntimeError(f"Failed to parse JSON (status {r.status_code}): {e} | Body: {r.text[:200]}")

    def _find_term(self, taxonomy: str, name: str) -> Optional[int]:
        params = {"search": name, "per_page": 100, "context": "edit"}
        r = self._request("GET", f"{taxonomy}", params=params)
        data = self._json(r)
        for term in data:
            tname = (term.get("name") or "").strip().lower()
            if tname == name.strip().lower():
                return int(term["id"])
        return None

    def ensure_term(self, taxonomy: str, name: str, slug: Optional[str] = None) -> int:
        tid = self._find_term(taxonomy, name)
        if tid:
            return tid
        payload = {"name": name}
        if slug:
            payload["slug"] = slug
        r = self._request("POST", f"{taxonomy}", json=payload)
        data = self._json(r)
        return int(data["id"])

    def ensure_category(self, name: str, slug: Optional[str] = None) -> int:
        return self.ensure_term("categories", name, slug)

    def ensure_tag(self, name: str, slug: Optional[str] = None) -> int:
        return self.ensure_term("tags", name, slug)

    # ---------- Post upsert ----------
    def get_post_by_slug(self, slug: str) -> Optional[Dict[str, Any]]:
        params = {"slug": slug, "per_page": 1, "context": "edit"}
        r = self._request("GET", "posts", params=params)
        data = self._json(r)
        return data[0] if data else None

    def upsert_post(
        self,
        *,
        slug: str,
        title: str,
        content: str,
        status: str = "publish",
        categories: Optional[List[int]] = None,
        tags: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        existing = self.get_post_by_slug(slug)
        payload: Dict[str, Any] = {
            "title": title,
            "content": content,
            "status": status,
            "slug": slug,
        }
        if categories:
            payload["categories"] = categories
        if tags:
            payload["tags"] = tags

        if existing:
            post_id = existing["id"]
            r = self._request("PUT", f"posts/{post_id}", json=payload)
            return self._json(r)

        r = self._request("POST", "posts", json=payload)
        return self._json(r)
