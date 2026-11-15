import copy
import json
from pathlib import Path
import unittest
from bots.shared_social.shopify_drafts import design_key, make_drafts, safe_url

FIXTURE = Path(__file__).with_name("fixtures") / "modpanic_products.json"


def product(handle, title, status="ACTIVE", number=1):
    return {"id": f"gid://shopify/Product/{number}", "handle": handle, "title": title,
            "status": status, "vendor": "Mod Panic", "tags": [],
            "onlineStoreUrl": f"https://modpanic.com/products/{handle}",
            "featuredMedia": {"preview": {"image": {"url": "https://cdn.shopify.com/s/files/1/0416/3757/6867/files/a.jpg"}}}}


class ShopifyDraftTests(unittest.TestCase):
    def test_actual_catalog_groups_seven_mississippi_formats(self):
        data = json.loads(FIXTURE.read_text())
        drafts = make_drafts(data["products"])
        group = next(d for d in drafts if d["design_key"] == "mississippi-blue-wave")
        self.assertEqual(len(group["products"]), 7)
        self.assertFalse(group["approved"])
        self.assertEqual(group["status"], "needs_review")

    def test_variant_count_order_and_repeated_input_do_not_create_extra_artworks(self):
        items = [product("sticker-cat", "Cat Sticker"), product("mug-cat", "Cat Mug", number=2)]
        items[1]["variants"] = {"nodes": [{"id": str(i)} for i in range(250)]}
        first = make_drafts(items)
        self.assertEqual(len(first), 1)
        self.assertEqual(first, make_drafts(list(reversed(items))))
        self.assertEqual(make_drafts(items, ["cat"]), [])

    def test_legacy_suffixes_and_explicit_mapping(self):
        self.assertEqual(design_key(product("austin-cat-magnet-1", "Austin Cat Magnet")), "austin-cat")
        p = product("odd-handle", "Something Else")
        self.assertEqual(design_key(p, {p["id"]: "austin-cat"}), "austin-cat")
        p["tags"] = ["artwork:cat"]
        self.assertEqual(design_key(p), "cat")
        p["tags"].append("artwork:dog")
        with self.assertRaises(ValueError):
            design_key(p)
        with self.assertRaises(ValueError):
            design_key(p, {p["id"]: "../../escape"})

    def test_different_artworks_and_colorways_stay_distinct(self):
        items = [product("mug-austin-cat", "Austin Cat Mug"),
                 product("mug-austin-cat-black-and-white", "Austin Cat Black And White Mug", number=2),
                 product("mug-mug-life", "Mug Life Mug", number=3)]
        self.assertEqual({d["design_key"] for d in make_drafts(items)},
                         {"austin-cat", "austin-cat-black-and-white", "mug-life"})

    def test_extended_formats_and_legacy_price_fragments_group_by_artwork(self):
        items = [product("mug-howdy-from-texas", "Howdy From Texas Mug"),
                 product("howdy-from-texas-car-coaster", "Howdy From Texas Car Coaster", number=2),
                 product("tea_towel-howdy-from-texas-price-12-copy", "Howdy From Texas Tea Towel", number=3),
                 product("howdy-from-texas-tote-bag", "Howdy From Texas Tote Bag", number=4)]
        self.assertEqual(len(make_drafts(items)), 1)
        self.assertEqual(len(make_drafts(items)[0]["products"]), 4)

    def test_skips_inactive_unpublished_wrong_brand_missing_or_unsafe_media(self):
        valid = product("mug-cat", "Cat Mug")
        invalid = []
        for field, value in [("status", "DRAFT"), ("status", "ARCHIVED"), ("onlineStoreUrl", None),
                             ("vendor", "Gaia Eyes"), ("id", "unknown"), ("title", ""),
                             ("onlineStoreUrl", "https://modpanic.com/products/different")]:
            p = copy.deepcopy(valid)
            p[field] = value
            invalid.append(p)
        p = copy.deepcopy(valid)
        p["featuredMedia"] = None
        invalid.append(p)
        self.assertEqual(make_drafts(invalid), [])

    def test_strict_url_validation(self):
        for url in ["http://modpanic.com/products/cat", "https://modpanic.com.evil.test/products/cat",
                    "https://x@modpanic.com/products/cat", "https://modpanic.com:443/products/cat",
                    "https://modpanic.com/products/../admin", "https://modpanic.com/products/a?evil=1",
                    "https://127.0.0.1/a", "https://modpanic.com/products/a\n"]:
            self.assertFalse(safe_url(url), url)
        for url in ["https://cdn.shopify.com/another-store/a.jpg", "https://cdn.shopify.com:443/s/files/1/0416/3757/6867/a.jpg",
                    "https://cdn.shopify.com/s/files/1/0416/3757/6867/../a.jpg",
                    "https://cdn.shopify.com/s/files/1/0416/3757/6867/%2e%2e/a.jpg"]:
            self.assertFalse(safe_url(url, image=True), url)

    def test_platform_captions_are_distinct_and_no_unverified_claims(self):
        draft = make_drafts([product("mug-cat", "Cat Mug")])[0]
        self.assertIn(draft["product_url"], draft["facebook_caption"])
        self.assertIn("#ModPanic", draft["instagram_caption"])
        self.assertNotIn("link in", draft["instagram_caption"])
        self.assertLess(len(draft["instagram_caption"]), 2200)
        self.assertNotIn("Original", draft["instagram_caption"])
        self.assertNotEqual(draft["facebook_caption"], draft["instagram_caption"])


if __name__ == "__main__":
    unittest.main()
