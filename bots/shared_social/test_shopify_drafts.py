import unittest
from bots.shared_social.shopify_drafts import design_key, make_drafts


def product(handle, title, status="ACTIVE"):
    return {
        "id": handle, "handle": handle, "title": title, "status": status,
        "featuredMedia": {"preview": {"image": {"url": "https://cdn.shopify.com/a.jpg"}}},
    }


class ShopifyDraftTests(unittest.TestCase):
    def test_groups_same_artwork_across_products(self):
        items = [product("sticker-mississippi-blue-wave", "Mississippi Blue Wave Sticker"),
                 product("mug-mississippi-blue-wave", "Mississippi Blue Wave Mug")]
        drafts = make_drafts(items)
        self.assertEqual(len(drafts), 1)
        self.assertEqual(drafts[0]["design_key"], "mississippi-blue-wave")
        self.assertFalse(drafts[0]["approved"])

    def test_rejects_inactive_and_previously_used(self):
        items = [product("sticker-one", "One", "DRAFT"), product("mug-two", "Two")]
        self.assertEqual(make_drafts(items, ["two"]), [])

    def test_draft_has_no_publish_instruction(self):
        draft = make_drafts([product("mug-cat", "Cat Mug")])[0]
        self.assertEqual(draft["status"], "needs_review")
        self.assertEqual(draft["product_url"], "https://modpanic.com/products/mug-cat")


if __name__ == "__main__":
    unittest.main()
