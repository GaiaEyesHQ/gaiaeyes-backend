import os
import unittest
from unittest.mock import patch

from bots.shared_social.brand_config import BrandConfig


class BrandConfigTests(unittest.TestCase):
    def test_brand_separation(self):
        env = {
            "GAIA_EYES_FB_PAGE_ID": "gaia-page",
            "GAIA_EYES_IG_USER_ID": "gaia-ig",
            "GAIA_EYES_FB_ACCESS_TOKEN": "gaia-secret",
            "MOD_PANIC_FB_PAGE_ID": "mod-page",
            "MOD_PANIC_IG_USER_ID": "mod-ig",
            "MOD_PANIC_FB_ACCESS_TOKEN": "mod-secret",
        }
        with patch.dict(os.environ, env, clear=True):
            gaia = BrandConfig.from_environment("gaia_eyes")
            mod = BrandConfig.from_environment("mod_panic")
        self.assertEqual(gaia.facebook_page_id, "gaia-page")
        self.assertEqual(mod.facebook_page_id, "mod-page")
        self.assertNotEqual(gaia.access_token, mod.access_token)

    def test_missing_credentials_fail_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                BrandConfig.from_environment("mod_panic")

    def test_unknown_brand_rejected(self):
        with self.assertRaises(ValueError):
            BrandConfig.from_environment("other")


if __name__ == "__main__":
    unittest.main()
