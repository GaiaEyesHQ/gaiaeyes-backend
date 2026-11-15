"""Pinned, least-privilege Shopify catalog reader. This module has no mutations."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
import time

import requests

SHOP_DOMAIN = "oops-hand-sanitizer.myshopify.com"
SHOP_ID = "gid://shopify/Shop/41637576867"
API_VERSION = "2026-10"
IDENTITY_QUERY = """query ModPanicIdentity {
  shop { id myshopifyDomain }
  currentAppInstallation { accessScopes { handle } }
}"""
CATALOG_QUERY = """query ModPanicCatalog($after: String) {
  products(first: 50, after: $after, sortKey: ID, query: "status:active") {
    nodes {
      id title handle status vendor productType onlineStoreUrl tags
      featuredMedia { preview { image { url } } }
    }
    pageInfo { hasNextPage endCursor }
  }
}"""


class CatalogError(RuntimeError):
    """Safe diagnostic: never include response bodies, URLs with tokens, or headers."""


@dataclass(frozen=True)
class CatalogConfig:
    access_token: str = field(default="", repr=False)
    client_id: str = field(default="", repr=False)
    client_secret: str = field(default="", repr=False)

    def __post_init__(self):
        if self.access_token and (self.client_id or self.client_secret):
            raise CatalogError("Configure either a read token or client credentials, not both")
        if not self.access_token and not (self.client_id and self.client_secret):
            raise CatalogError("Configure both Mod Panic Shopify client credentials")

    @classmethod
    def from_environment(cls):
        return cls(
            access_token=os.environ.get("MOD_PANIC_SHOPIFY_READ_TOKEN", "").strip(),
            client_id=os.environ.get("MOD_PANIC_SHOPIFY_CLIENT_ID", "").strip(),
            client_secret=os.environ.get("MOD_PANIC_SHOPIFY_CLIENT_SECRET", "").strip(),
        )


class ShopifyCatalog:
    def __init__(self, config, *, session=None, sleep=time.sleep, clock=time.monotonic):
        self.config = config
        self.session = session or requests.Session()
        self.session.trust_env = False  # No proxy or .netrc credential inheritance.
        self.sleep = sleep
        self.clock = clock
        self._token = ""
        self._expires_at = 0

    @staticmethod
    def _read_json(response, limit):
        chunks, size = [], 0
        for chunk in response.iter_content(65536):
            size += len(chunk)
            if size > limit:
                raise CatalogError("Shopify response exceeded the size limit")
            chunks.append(chunk)
        body = json.loads(b"".join(chunks))
        if not isinstance(body, dict):
            raise CatalogError("Invalid Shopify response")
        return body

    def _get_access_token(self):
        if self.config.access_token:
            return self.config.access_token
        if self._token and self.clock() < self._expires_at - 60:
            return self._token
        # Never persist exchanged tokens or fall back to an expired token on failure.
        self._token, self._expires_at = "", 0
        for attempt in range(3):
            issued_at = self.clock()
            try:
                with self.session.post(
                    f"https://{SHOP_DOMAIN}/admin/oauth/access_token",
                    data={"grant_type": "client_credentials", "client_id": self.config.client_id,
                          "client_secret": self.config.client_secret},
                    headers={"Accept": "application/json"},
                    timeout=(10, 45), allow_redirects=False, stream=True,
                ) as response:
                    if response.status_code == 429 or 500 <= response.status_code < 600:
                        if attempt == 2:
                            raise CatalogError("Shopify authentication unavailable after bounded retries")
                        self.sleep(2 ** attempt)
                        continue
                    if response.status_code != 200:
                        raise CatalogError("Shopify authentication rejected; check app installation and credentials")
                    body = self._read_json(response, 64 * 1024)
                token, lifetime, scope = body.get("access_token"), body.get("expires_in"), body.get("scope")
                if (not isinstance(token, str) or not token or len(token) > 4096
                        or any(c.isspace() for c in token)
                        or type(lifetime) is not int or not 60 < lifetime <= 86400):
                    raise CatalogError("Invalid Shopify token response")
                if not isinstance(scope, str) or {s.strip() for s in scope.split(",")} != {"read_products"}:
                    raise CatalogError("Use a dedicated app granting only read_products")
                if self.clock() >= issued_at + lifetime - 60:
                    raise CatalogError("Shopify token has insufficient remaining lifetime")
                self._token, self._expires_at = token, issued_at + lifetime
                return self._token
            except (requests.RequestException, ValueError, UnicodeError):
                raise CatalogError("Shopify authentication transport or response failure") from None
        raise CatalogError("Shopify authentication did not complete")

    def _query(self, query, variables=None):
        if query not in (IDENTITY_QUERY, CATALOG_QUERY):
            raise CatalogError("Only the fixed catalog queries are permitted")
        for attempt in range(3):
            try:
                with self.session.post(
                    f"https://{SHOP_DOMAIN}/admin/api/{API_VERSION}/graphql.json",
                    headers={"X-Shopify-Access-Token": self._get_access_token()},
                    json={"query": query, "variables": variables or {}},
                    timeout=(10, 45), allow_redirects=False, stream=True,
                ) as response:
                    if response.status_code == 429 or 500 <= response.status_code < 600:
                        if attempt == 2:
                            raise CatalogError("Shopify is unavailable after bounded retries")
                        self.sleep(2 ** attempt)
                        continue
                    if response.status_code != 200:
                        raise CatalogError("Shopify rejected the catalog read; check the dedicated token")
                    version = response.headers.get("X-Shopify-API-Version")
                    if version and version != API_VERSION:
                        raise CatalogError("Shopify API version changed; review the pinned query")
                    body = self._read_json(response, 4 * 1024 * 1024)
                errors = body.get("errors")
                if errors:
                    throttled = isinstance(errors, list) and all(
                        isinstance(e, dict) and isinstance(e.get("extensions"), dict)
                        and e["extensions"].get("code") == "THROTTLED"
                        for e in errors
                    )
                    if throttled and attempt < 2:
                        self.sleep(2 ** attempt)
                        continue
                    raise CatalogError("Shopify query failed; no catalog changes saved")
                if not isinstance(body.get("data"), dict):
                    raise CatalogError("Missing Shopify data")
                return body["data"]
            except (requests.RequestException, ValueError, UnicodeError):
                raise CatalogError("Shopify transport or response failure; no catalog changes saved") from None
        raise CatalogError("Shopify read did not complete")

    def verify_access(self):
        """Authenticate and verify the store/scopes without reading products or writing files."""
        identity = self._query(IDENTITY_QUERY)
        try:
            shop = identity["shop"]
            scopes = {s["handle"] for s in identity["currentAppInstallation"]["accessScopes"]}
            if shop["id"] != SHOP_ID or shop["myshopifyDomain"] != SHOP_DOMAIN:
                raise CatalogError("Shopify account is not the pinned Mod Panic store")
            if scopes != {"read_products"}:
                raise CatalogError("Use a dedicated token granting only read_products")
        except (KeyError, TypeError, AttributeError):
            raise CatalogError("Incomplete Shopify identity response") from None
        return {"brand": "mod_panic", "shop_id": SHOP_ID, "shop_domain": SHOP_DOMAIN,
                "scopes": ["read_products"], "publishing_enabled": False}

    def fetch(self):
        self.verify_access()
        try:
            products, seen_ids, cursors = [], set(), set()
            cursor = None
            for _ in range(200):
                page = self._query(CATALOG_QUERY, {"after": cursor})["products"]
                nodes, info = page["nodes"], page["pageInfo"]
                if not isinstance(nodes, list) or type(info["hasNextPage"]) is not bool:
                    raise CatalogError("Invalid Shopify pagination")
                for product in nodes:
                    if not isinstance(product, dict) or not product.get("id"):
                        raise CatalogError("Invalid Shopify product")
                    if product["id"] in seen_ids:
                        raise CatalogError("Catalog changed during pagination; rerun the full sync")
                    seen_ids.add(product["id"])
                    products.append(product)
                if not info["hasNextPage"]:
                    return {"schema_version": 1, "brand": "mod_panic", "shop_id": SHOP_ID,
                            "shop_domain": SHOP_DOMAIN, "complete": True,
                            "source": "Shopify Admin API", "fetched_at": datetime.now(timezone.utc).isoformat(),
                            "products": products}
                cursor = info["endCursor"]
                if not nodes or not isinstance(cursor, str) or not cursor or cursor in cursors:
                    raise CatalogError("Shopify pagination did not advance")
                cursors.add(cursor)
        except (KeyError, TypeError, AttributeError):
            raise CatalogError("Incomplete Shopify catalog response") from None
        raise CatalogError("Catalog exceeded the page limit; no partial snapshot saved")
