import json
import unittest
from unittest.mock import patch

import requests

from bots.shared_social.shopify_catalog import (
    API_VERSION, CATALOG_QUERY, IDENTITY_QUERY, SHOP_DOMAIN, SHOP_ID,
    CatalogConfig, CatalogError, ShopifyCatalog,
)


class Response:
    def __init__(self, body=None, status=200, headers=None, raw=None):
        self.status_code = status
        self.headers = headers or {"X-Shopify-API-Version": API_VERSION}
        self.raw = raw if raw is not None else json.dumps(body).encode()
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def iter_content(self, size):
        yield self.raw


class Session:
    def __init__(self, responses):
        self.responses, self.calls = iter(responses), []
    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        result = next(self.responses)
        if isinstance(result, Exception):
            raise result
        return result


def identity(scopes=("read_products",), shop_id=SHOP_ID):
    return Response({"data": {"shop": {"id": shop_id, "myshopifyDomain": SHOP_DOMAIN},
                              "currentAppInstallation": {"accessScopes": [{"handle": s} for s in scopes]}}})


def page(ids=(), more=False, cursor=None):
    return Response({"data": {"products": {"nodes": [{"id": i} for i in ids],
                                            "pageInfo": {"hasNextPage": more, "endCursor": cursor}}}})


class CatalogTests(unittest.TestCase):
    def client(self, responses):
        session = Session(responses)
        return ShopifyCatalog(CatalogConfig("secret-do-not-log"), session=session, sleep=lambda _: None), session

    def test_reads_all_pages_with_fixed_queries_and_token_only_in_header(self):
        client, session = self.client([identity(), page(["1"], True, "next"), page(["2"])])
        snapshot = client.fetch()
        self.assertEqual([p["id"] for p in snapshot["products"]], ["1", "2"])
        self.assertTrue(snapshot["complete"])
        self.assertFalse(session.trust_env)
        for url, kwargs in session.calls:
            self.assertEqual(url, f"https://{SHOP_DOMAIN}/admin/api/{API_VERSION}/graphql.json")
            self.assertIn(kwargs["json"]["query"], (IDENTITY_QUERY, CATALOG_QUERY))
            self.assertFalse(kwargs["allow_redirects"])
            self.assertNotIn("secret-do-not-log", json.dumps(kwargs["json"]))
        self.assertEqual(session.calls[-1][1]["json"]["variables"], {"after": "next"})

    def test_rejects_wrong_store_or_broad_scopes_before_catalog(self):
        for response in [identity(("read_products", "write_products")), identity(("read_orders", "read_products")),
                         identity(()), identity(shop_id="another-shop")]:
            client, session = self.client([response])
            with self.assertRaises(CatalogError):
                client.fetch()
            self.assertEqual(len(session.calls), 1)

    def test_redirects_auth_errors_malformed_json_and_version_drift_fail(self):
        for response in [Response({}, 302), Response({}, 401), Response(raw=b"not-json"),
                         Response({}, headers={"X-Shopify-API-Version": "2099-01"}), Response([]),
                         Response({"data": None}), Response({"errors": [{"message": "secret-do-not-log"}]})]:
            client, _ = self.client([response])
            with self.assertRaises(CatalogError) as caught:
                client.fetch()
            self.assertNotIn("secret-do-not-log", str(caught.exception))

    def test_transport_errors_redacted_and_token_hidden(self):
        client, _ = self.client([requests.RequestException("secret-do-not-log")])
        with self.assertRaises(CatalogError) as caught:
            client.fetch()
        self.assertNotIn("secret-do-not-log", str(caught.exception))
        self.assertNotIn("secret-do-not-log", repr(client.config))

    def test_missing_token_does_not_fallback_to_other_brands(self):
        with patch.dict("os.environ", {"FB_ACCESS_TOKEN": "secret", "GAIA_EYES_FB_ACCESS_TOKEN": "secret",
                                      "SHOPIFY_ACCESS_TOKEN": "broad-token", "SHOPIFY_CLIENT_ID": "other-app",
                                      "SHOPIFY_CLIENT_SECRET": "other-secret"}, clear=True):
            with self.assertRaises(CatalogError):
                CatalogConfig.from_environment()

    def test_http_and_graphql_throttle_retries_are_bounded(self):
        for throttle in [Response({}, 429), Response({}, 503),
                         Response({"errors": [{"extensions": {"code": "THROTTLED"}}]})]:
            client, session = self.client([throttle, throttle, identity(), page()])
            self.assertEqual(client.fetch()["products"], [])
            self.assertEqual(len(session.calls), 4)
            client, session = self.client([throttle] * 3)
            with self.assertRaises(CatalogError):
                client.fetch()
            self.assertEqual(len(session.calls), 3)

    def test_no_partial_snapshot_on_pagination_errors(self):
        for last in [page(["2"], True, "same"), page(["1"]), page([], True, "other"),
                     Response({"data": {"products": {"nodes": []}}}), Response({}, 500)]:
            client, _ = self.client([identity(), page(["1"], True, "same"), last, last, last])
            with self.assertRaises(CatalogError):
                client.fetch()

    def test_oversized_response_and_arbitrary_operation_rejected(self):
        client, session = self.client([Response(raw=b" " * (4 * 1024 * 1024 + 1))])
        with self.assertRaises(CatalogError):
            client.fetch()
        with self.assertRaises(CatalogError):
            client._query("mutation { productDelete { id } }")
        self.assertEqual(len(session.calls), 1)


def oauth(**overrides):
    body = {"access_token": "exchanged-token-do-not-log", "scope": "read_products", "expires_in": 86399}
    body.update(overrides)
    return Response(body)


class ClientCredentialTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000

    def client(self, responses):
        session = Session(responses)
        config = CatalogConfig(client_id="catalog-app-id", client_secret="client-secret-do-not-log")
        return ShopifyCatalog(config, session=session, sleep=lambda _: None, clock=lambda: self.now), session

    def test_environment_supports_exactly_one_complete_authentication_mode(self):
        pair = {"MOD_PANIC_SHOPIFY_CLIENT_ID": " catalog-app-id ",
                "MOD_PANIC_SHOPIFY_CLIENT_SECRET": " client-secret-do-not-log "}
        with patch.dict("os.environ", pair, clear=True):
            config = CatalogConfig.from_environment()
        self.assertEqual(config.client_id, "catalog-app-id")
        self.assertEqual(config.client_secret, "client-secret-do-not-log")
        self.assertNotIn("client-secret-do-not-log", repr(config))
        for values in ({}, {"MOD_PANIC_SHOPIFY_CLIENT_ID": "id"},
                       {"MOD_PANIC_SHOPIFY_CLIENT_SECRET": "secret"},
                       {**pair, "MOD_PANIC_SHOPIFY_READ_TOKEN": "old-token"}):
            with self.subTest(keys=list(values)), patch.dict("os.environ", values, clear=True):
                with self.assertRaises(CatalogError):
                    CatalogConfig.from_environment()

    def test_exchange_uses_pinned_host_body_credentials_and_no_scope_override(self):
        client, session = self.client([oauth(), identity(), page(["1"])])
        self.assertEqual(len(client.fetch()["products"]), 1)
        url, kwargs = session.calls[0]
        self.assertEqual(url, f"https://{SHOP_DOMAIN}/admin/oauth/access_token")
        self.assertEqual(kwargs["data"], {"grant_type": "client_credentials", "client_id": "catalog-app-id",
                                          "client_secret": "client-secret-do-not-log"})
        self.assertNotIn("scope", kwargs["data"])
        self.assertNotIn("secret", url)
        self.assertFalse(session.trust_env)
        for _, arguments in session.calls:
            self.assertFalse(arguments["allow_redirects"])
            self.assertEqual(arguments["timeout"], (10, 45))
        for _, arguments in session.calls[1:]:
            self.assertEqual(arguments["headers"]["X-Shopify-Access-Token"], "exchanged-token-do-not-log")
            self.assertNotIn("client-secret-do-not-log", json.dumps(arguments))

    def test_refreshes_before_expiry_and_reuses_token_until_then(self):
        client, session = self.client([oauth(), identity(), identity(), oauth(access_token="second-token"), identity()])
        client.verify_access()
        self.now += 86338  # One second before the refresh window.
        client.verify_access()
        self.assertEqual(len(session.calls), 3)
        self.now += 1
        client.verify_access()
        self.assertEqual(len(session.calls), 5)
        self.assertEqual(session.calls[-1][1]["headers"]["X-Shopify-Access-Token"], "second-token")

    def test_refresh_failure_does_not_reuse_old_token(self):
        client, session = self.client([oauth(), identity(), Response({}, 401)])
        client.verify_access()
        self.now += 86399
        with self.assertRaises(CatalogError):
            client.verify_access()
        self.assertEqual(len(session.calls), 3)
        self.assertEqual(client._token, "")

    def test_rejects_broad_missing_or_malformed_token_scopes_before_graphql(self):
        for scope in ("read_products,write_products", "read_products,read_customers", "", None,
                      ["read_products"], "read_products,", "read_orders"):
            with self.subTest(scope=scope):
                client, session = self.client([oauth(scope=scope)])
                with self.assertRaises(CatalogError):
                    client.fetch()
                self.assertEqual(len(session.calls), 1)

    def test_independently_checks_installation_scopes_and_store_after_exchange(self):
        for data in (identity(("read_products", "write_products")), identity(shop_id="another-shop"),
                     Response({"data": {"shop": {"id": SHOP_ID, "myshopifyDomain": "another.myshopify.com"},
                                       "currentAppInstallation": {"accessScopes": [{"handle": "read_products"}]}}})):
            client, session = self.client([oauth(), data])
            with self.assertRaises(CatalogError):
                client.fetch()
            self.assertEqual(len(session.calls), 2)

    def test_malformed_token_and_expiry_fail_before_graphql(self):
        cases = [{"access_token": None}, {"access_token": ""}, {"access_token": "bad\r\ntoken"},
                 {"access_token": "x" * 4097}, {"access_token": 4}, {"expires_in": None},
                 {"expires_in": True}, {"expires_in": "86399"}, {"expires_in": 0},
                 {"expires_in": 60}, {"expires_in": 86401}]
        for values in cases:
            with self.subTest(fields=list(values)):
                client, session = self.client([oauth(**values)])
                with self.assertRaises(CatalogError):
                    client.fetch()
                self.assertEqual(len(session.calls), 1)

    def test_expiry_is_measured_conservatively_from_request_start(self):
        client, session = self.client([oauth(expires_in=120)])
        times = iter([1000, 1060])
        client.clock = lambda: next(times)
        with self.assertRaises(CatalogError):
            client.verify_access()
        self.assertEqual(len(session.calls), 1)

    def test_oauth_errors_are_bounded_redacted_and_do_not_read_products(self):
        for response in (Response({"error": "client-secret-do-not-log"}, 400), Response({}, 401),
                         Response({}, 403), Response({}, 302), Response(raw=b"not-json"), Response([]),
                         Response(raw=b" " * (64 * 1024 + 1)),
                         requests.RequestException("client-secret-do-not-log")):
            client, session = self.client([response])
            with self.assertRaises(CatalogError) as caught:
                client.fetch()
            self.assertNotIn("client-secret-do-not-log", str(caught.exception))
            self.assertNotIn("exchanged-token-do-not-log", str(caught.exception))
            self.assertEqual(len(session.calls), 1)

    def test_oauth_transient_retries_are_bounded(self):
        for status in (429, 503):
            client, session = self.client([Response({}, status), Response({}, status), oauth(), identity()])
            self.assertEqual(client.verify_access()["scopes"], ["read_products"])
            self.assertEqual(len(session.calls), 4)
            client, session = self.client([Response({}, status)] * 3)
            with self.assertRaises(CatalogError):
                client.verify_access()
            self.assertEqual(len(session.calls), 3)

    def test_verify_access_reads_no_catalog_and_returns_only_safe_metadata(self):
        client, session = self.client([oauth(), identity()])
        self.assertEqual(client.verify_access(), {"brand": "mod_panic", "shop_id": SHOP_ID,
                                                "shop_domain": SHOP_DOMAIN, "scopes": ["read_products"],
                                                "publishing_enabled": False})
        self.assertEqual(len(session.calls), 2)
        self.assertEqual(session.calls[-1][1]["json"]["query"], IDENTITY_QUERY)


if __name__ == "__main__":
    unittest.main()
