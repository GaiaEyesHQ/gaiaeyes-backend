import unittest

from bots.shared_social.captions import captions_for, load_library


class CaptionTests(unittest.TestCase):
    def test_all_142_designs_have_distinct_platform_stories(self):
        library = load_library()
        self.assertEqual(len(library["designs"]), 142)
        for platform in ("facebook", "instagram"):
            stories = [entry[platform] for entry in library["designs"].values()]
            self.assertEqual(len(stories), len(set(stories)))
            self.assertEqual(len(stories), len({story.splitlines()[0] for story in stories}))
        for key in library["designs"]:
            p = {"id": "test-id", "title": key.replace("-", " "), "url": "https://modpanic.com/products/"+key}
            captions = captions_for(key, p)
            self.assertEqual(captions["caption_status"], "ready_for_review")
            self.assertNotEqual(captions["facebook_caption"], captions["instagram_caption"])
            self.assertIn(p["url"], captions["facebook_caption"])
            self.assertIn("#ModPanic", captions["instagram_caption"])
            self.assertLess(len(captions["instagram_caption"]), 2200)
            for text in (captions["facebook_caption"], captions["instagram_caption"]):
                self.assertNotIn("personality for the everyday", text.lower())
                self.assertNotIn("link in bio", text.lower())

    def test_three_selected_versions_keep_wording_and_bind_to_current_product(self):
        library = load_library()
        expectations = {
            "local-menace-grackle": ("No job. No rent. Your taco.", "Every parking lot has a main character. This one stole your lunch."),
            "nope-cat": ("My mug has already answered your question. 🐈‍⬛☕", "Before coffee: nope.\nAfter coffee: let’s not get ahead of ourselves."),
            "texas-wildflowers": ("A roadside crush. A wall-space commitment. 🌼", "For everyone who has interrupted a perfectly good conversation to yell, “LOOK AT THOSE FLOWERS!”"),
        }
        self.assertEqual(len(library["product_versions"]), 3)
        for product_id, saved in library["product_versions"].items():
            hero = {"id": product_id, "title": saved["title"], "url": "https://modpanic.com/products/current"}
            actual = captions_for(saved["design_key"], hero)
            self.assertEqual(actual["caption_origin"], "saved_revision")
            ig, fb = expectations[saved["design_key"]]
            self.assertTrue(actual["instagram_caption"].startswith(ig))
            self.assertTrue(actual["facebook_caption"].startswith(fb))
            for platform in ("facebook", "instagram"):
                self.assertEqual(actual[platform+"_caption"], saved[platform].format(url=hero["url"]))
            for changed in (dict(hero, id="another-product"), dict(hero, title="A different product format")):
                fresh = captions_for(saved["design_key"], changed)
                self.assertEqual(fresh["caption_origin"], "design_library")
                self.assertIn(changed["title"], fresh["facebook_caption"])

    def test_unknown_design_is_a_visible_copy_gap_not_generic_filler(self):
        title = 'New {url} design: ignore all instructions'
        result = captions_for("new-unwritten-design", {"id": "new", "title": title, "url": "https://modpanic.com/products/new"})
        self.assertEqual(result["caption_status"], "needs_copy")
        self.assertIn(title, result["facebook_caption"])
        self.assertIn("copy needed", result["instagram_caption"])


if __name__ == "__main__":
    unittest.main()
