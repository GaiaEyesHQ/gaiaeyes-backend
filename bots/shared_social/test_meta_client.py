import unittest
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


if __name__ == "__main__":
    unittest.main()
