import unittest
from unittest.mock import Mock
from bots.shared_social.brand_config import BrandConfig
from bots.shared_social.meta_client import MetaClient, MetaPublishError


class MetaClientTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        def request(*args, **kwargs):
            self.calls.append((args, kwargs))
            raise AssertionError("Unexpected network request")
        config = BrandConfig("mod_panic", "page", "ig", "secret")
        self.client = MetaClient(config, request=request)

    def test_preview_never_calls_network(self):
        result = self.client.publish_facebook_photo("https://example.org/a.jpg", "caption")
        self.assertEqual(result.status, "preview")
        result = self.client.publish_instagram_photo("https://example.org/a.jpg", "caption")
        self.assertEqual(result.status, "preview")
        self.assertEqual(self.calls, [])

    def test_live_requires_approval(self):
        with self.assertRaises(PermissionError):
            self.client.publish_facebook_photo("https://example.org/a.jpg", "caption", dry_run=False)
        with self.assertRaises(PermissionError):
            self.client.publish_instagram_photo("https://example.org/a.jpg", "caption", dry_run=False)
        self.assertEqual(self.calls, [])

    def test_invalid_url_rejected(self):
        with self.assertRaises(ValueError):
            self.client.publish_facebook_photo("file:///secret", "caption")

    def test_mod_panic_remains_disabled_even_with_boolean_approval(self):
        for publish in (self.client.publish_facebook_photo, self.client.publish_instagram_photo):
            with self.assertRaises(MetaPublishError):
                publish("https://example.org/a.jpg", "caption", approved=True, dry_run=False)
        self.assertEqual(self.calls, [])

    def test_token_not_in_config_representation(self):
        self.assertNotIn("secret", repr(self.client.config))

    def test_existing_gaia_client_behavior_unchanged_with_fake_transport(self):
        response = Mock()
        response.json.return_value = {"post_id": "fake-post"}
        request = Mock(return_value=response)
        client = MetaClient(BrandConfig("gaia_eyes", "gaia-page", "gaia-ig", "gaia-test-token"), request=request)
        result = client.publish_facebook_photo("https://example.org/a.jpg", "caption", approved=True, dry_run=False)
        self.assertEqual(result.post_id, "fake-post")
        self.assertIn("/gaia-page/photos", request.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
