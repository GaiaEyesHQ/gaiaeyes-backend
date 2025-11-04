from typing import Dict, List, Optional

import requests

class WPClient:
    def __init__(self, base_url: str, username: str, app_password: str, timeout: int = 15):
        self.base = base_url.rstrip("/")
        self.auth = (username, app_password)
        self.timeout = timeout

    # ---------- Taxonomy helpers ----------
    def _find_term(self, taxonomy: str, name: str) -> Optional[int]:
        r = requests.get(
            f"{self.base}/wp-json/wp/v2/{taxonomy}",
            params={"search": name, "per_page": 100},
            auth=self.auth, timeout=self.timeout,
        )
        r.raise_for_status()
        for term in r.json():
            if term.get("name", "").lower() == name.lower():
                return int(term["id"])
        return None

    def ensure_term(self, taxonomy: str, name: str, slug: Optional[str] = None) -> int:
        term_id = self._find_term(taxonomy, name)
        if term_id is not None:
            return term_id
        data = {"name": name}
        if slug:
            data["slug"] = slug
        r = requests.post(
            f"{self.base}/wp-json/wp/v2/{taxonomy}",
            json=data,
            auth=self.auth,
            timeout=self.timeout,
        )
        r.raise_for_status()
        return int(r.json()["id"])

    def ensure_category(self, name: str, slug: Optional[str] = None) -> int:
        return self.ensure_term("categories", name, slug)

    def ensure_tag(self, name: str, slug: Optional[str] = None) -> int:
        return self.ensure_term("tags", name, slug)

    # ---------- Post upsert ----------
    def get_post_by_slug(self, slug: str) -> Optional[Dict]:
        r = requests.get(
            f"{self.base}/wp-json/wp/v2/posts",
            params={"slug": slug},
            auth=self.auth,
            timeout=self.timeout,
        )
        r.raise_for_status()
        data = r.json()
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
    ) -> Dict:
        existing = self.get_post_by_slug(slug)
        payload = {
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
            r = requests.put(
                f"{self.base}/wp-json/wp/v2/posts/{post_id}",
                json=payload,
                auth=self.auth,
                timeout=self.timeout,
            )
            r.raise_for_status()
            return r.json()

        r = requests.post(
            f"{self.base}/wp-json/wp/v2/posts",
            json=payload,
            auth=self.auth,
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()
