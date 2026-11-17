import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from bots.shared_social.captions import load_library
from bots.shared_social.draft_queue import refresh_captions, review, sync
from bots.shared_social.shopify_catalog import CatalogError, SHOP_DOMAIN, SHOP_ID
from bots.shared_social.test_shopify_drafts import product


def snapshot(products):
    return {"schema_version": 1, "brand": "mod_panic", "shop_id": SHOP_ID,
            "shop_domain": SHOP_DOMAIN, "complete": True, "products": products}


def renderer(draft, directory):
    assets = {}
    (directory / "images").mkdir(exist_ok=True)
    for platform in ("facebook", "instagram"):
        data = (draft["image_url"] + platform).encode()
        digest = hashlib.sha256(data).hexdigest()
        path = f"images/{draft['draft_id']}-{platform}-{digest[:16]}.jpg"
        (directory / path).write_bytes(data)
        assets[platform] = {"path": path, "sha256": digest}
    return assets


def install_test_captions(case):
    # Keep synthetic catalog fixtures out of the real Mod Panic editorial library.
    fixture = {key: {"facebook": f"A {key} has opinions about your schedule.",
                     "instagram": f"The {key} is in charge today.",
                     "hashtags": ["#PetPeople"], "cta": "Meet the pet"} for key in ("cat", "dog")}
    editing = patch.dict(load_library()["designs"], fixture)
    editing.start()
    case.addCleanup(editing.stop)


class QueueTests(unittest.TestCase):
    def setUp(self):
        install_test_captions(self)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.catalog = snapshot([product("mug-cat", "Cat Mug")])

    def sync(self, catalog=None, **kwargs):
        return sync(self.catalog if catalog is None else catalog, self.path, renderer=renderer, **kwargs)

    def approve(self, draft=None):
        d = draft or self.sync()["drafts"][0]
        return review(self.path, d["draft_id"], d["revision"], "approved", "Test reviewer")

    def test_caption_refresh_invalidates_approval_without_changing_catalog_or_images(self):
        before = self.approve()
        old = before["drafts"][0]
        with patch.dict(load_library()["designs"]["cat"], {"facebook": "The cat has filed a formal objection."}):
            after = refresh_captions(self.path)
            new = after["drafts"][0]
            self.assertNotEqual(old["revision"], new["revision"])
            self.assertEqual(new["status"], "needs_review")
            self.assertIsNone(new["reviewer"])
            self.assertEqual(after["last_sync"], before["last_sync"])
            for field in ("images", "products", "last_seen", "draft_id", "product_id"):
                self.assertEqual(old[field], new[field])
            with self.assertRaisesRegex(ValueError, "changed"):
                self.approve(old)
            self.assertEqual(after["last_caption_update"]["changed_drafts"], 1)
            repeated = refresh_captions(self.path)
            self.assertEqual(after, repeated)
            self.assertIn("Catalog-check time is unchanged", (self.path/"review.html").read_text())
            self.assertEqual(self.sync()["drafts"][0]["revision"], new["revision"])

    def test_caption_refresh_preserves_withdrawn_and_suppressed_rows(self):
        self.catalog["products"].append(product("mug-dog", "Dog Mug", number=2))
        self.sync(previously_used=["dog"])
        before = self.sync(snapshot([]))
        after = refresh_captions(self.path)
        self.assertEqual(before, after)

    def test_caption_refresh_fails_atomically_when_any_asset_is_tampered(self):
        self.catalog["products"].append(product("mug-dog", "Dog Mug", number=2))
        before = self.sync()
        saved = (self.path/"review.json").read_bytes()
        bad = before["drafts"][-1]["images"]["instagram"]["path"]
        (self.path/bad).write_bytes(b"tampered")
        with patch.dict(load_library()["designs"]["cat"], {"facebook": "New cat wording"}):
            with self.assertRaisesRegex(ValueError, "image changed"):
                refresh_captions(self.path)
        self.assertEqual(saved, (self.path/"review.json").read_bytes())
        with sqlite3.connect(self.path/"queue.sqlite3") as db:
            self.assertEqual(db.execute("SELECT count(*) FROM caption_updates").fetchone()[0], 0)

    def test_new_design_with_missing_copy_cannot_be_approved(self):
        result = self.sync(snapshot([product("mug-new-unknown-design", "New Unknown Design Mug")]))
        draft = result["drafts"][0]
        self.assertEqual(draft["caption_status"], "needs_copy")
        with self.assertRaisesRegex(ValueError, "tailored captions"):
            self.approve(draft)
        rejected = review(self.path, draft["draft_id"], draft["revision"], "rejected", "Reviewer")
        self.assertEqual(rejected["drafts"][0]["status"], "rejected")

    def test_rerun_is_idempotent_and_keeps_approval_for_exact_revision(self):
        first = self.sync()["drafts"][0]
        self.assertEqual(first["status"], "needs_review")
        self.approve(first)
        second = self.sync()["drafts"]
        self.assertEqual(len(second), 1)
        self.assertEqual(second[0]["status"], "approved")
        self.assertEqual(first["revision"], second[0]["revision"])
        self.assertFalse(json.loads((self.path / "review.json").read_text())["publishing_enabled"])

    def test_product_change_invalidates_approval_and_old_revision_is_rejected(self):
        old = self.sync()["drafts"][0]
        self.approve(old)
        self.catalog["products"].append(product("sticker-cat", "Cat Sticker", number=2))
        current = self.sync()["drafts"][0]
        self.assertEqual(current["status"], "needs_review")
        self.assertNotEqual(current["revision"], old["revision"])
        with self.assertRaisesRegex(ValueError, "changed"):
            self.approve(old)

    def test_same_url_changed_image_bytes_invalidates_approval(self):
        self.approve()
        def changed(draft, directory):
            assets = renderer(draft, directory)
            for asset in assets.values():
                (directory / asset["path"]).write_bytes(b"changed image")
                asset["sha256"] = hashlib.sha256(b"changed image").hexdigest()
            return assets
        report = sync(self.catalog, self.path, renderer=changed)
        self.assertEqual(report["drafts"][0]["status"], "needs_review")

    def test_removed_unpublished_and_returning_products_require_review(self):
        old = self.sync()["drafts"][0]
        self.approve(old)
        empty = self.sync(snapshot([]))["drafts"][0]
        self.assertEqual(empty["status"], "withdrawn")
        with self.assertRaises(ValueError):
            self.approve(old)
        returned = self.sync()["drafts"][0]
        self.assertEqual(returned["status"], "needs_review")
        self.assertNotEqual(returned["revision"], old["revision"])
        with self.assertRaisesRegex(ValueError, "changed"):
            self.approve(old)
        self.approve(returned)
        self.assertEqual(self.sync()["drafts"][0]["status"], "approved")
        self.catalog["products"][0]["onlineStoreUrl"] = None
        self.assertEqual(self.sync()["drafts"][0]["status"], "withdrawn")

    def test_rejection_and_used_artwork_suppression_survive_reruns(self):
        draft = self.sync()["drafts"][0]
        review(self.path, draft["draft_id"], draft["revision"], "rejected", "Reviewer")
        self.assertEqual(self.sync()["drafts"][0]["status"], "rejected")
        self.sync(previously_used=["cat"])
        self.catalog["products"][0]["title"] = "Changed Cat Mug"
        self.assertEqual(self.sync()["drafts"][0]["status"], "suppressed")
        with self.assertRaises(ValueError):
            self.approve()

    def test_partial_wrong_shop_or_duplicate_snapshot_cannot_change_queue(self):
        self.approve()
        before = (self.path / "review.json").read_bytes()
        invalid = [dict(self.catalog, complete=False), dict(self.catalog, brand="gaia_eyes"),
                   dict(self.catalog, shop_id="wrong"), dict(self.catalog, products=self.catalog["products"]*2)]
        for catalog in invalid:
            with self.assertRaises(ValueError):
                self.sync(catalog)
        self.assertEqual(before, (self.path / "review.json").read_bytes())

    def test_used_artwork_ledger_survives_absence_and_first_seen_later(self):
        self.sync(snapshot([]), previously_used=["cat"])
        self.assertEqual(self.sync()["drafts"][0]["status"], "suppressed")
        self.sync(snapshot([]))
        self.assertEqual(self.sync()["drafts"][0]["status"], "suppressed")

    def test_render_failure_keeps_entire_previous_queue_and_decisions(self):
        self.approve()
        before = (self.path / "review.json").read_bytes()
        def fail(*args):
            raise RuntimeError("image missing")
        with self.assertRaises(RuntimeError):
            sync(self.catalog, self.path, renderer=fail)
        self.assertEqual(before, (self.path / "review.json").read_bytes())
        self.assertEqual(self.sync()["drafts"][0]["status"], "approved")

    def test_tampered_or_missing_assets_block_approval(self):
        draft = self.sync()["drafts"][0]
        path = self.path / draft["images"]["facebook"]["path"]
        path.write_bytes(b"modified")
        with self.assertRaisesRegex(ValueError, "image changed"):
            self.approve(draft)
        path.unlink()
        with self.assertRaisesRegex(ValueError, "missing"):
            self.approve(draft)

    def test_tampered_payload_blocks_review_even_if_stored_revision_matches(self):
        draft = self.sync()["drafts"][0]
        with sqlite3.connect(self.path / "queue.sqlite3") as db:
            payload = json.loads(db.execute("SELECT payload FROM drafts").fetchone()[0])
            payload["facebook_caption"] = "tampered"
            db.execute("UPDATE drafts SET payload=?", (json.dumps(payload),))
        with self.assertRaisesRegex(ValueError, "changed"):
            self.approve(draft)

    def test_brand_mismatch_and_missing_reviewer_fail_closed(self):
        draft = self.sync()["drafts"][0]
        with self.assertRaises(ValueError):
            review(self.path, draft["draft_id"], draft["revision"], "approved", " ")
        with sqlite3.connect(self.path / "queue.sqlite3") as db:
            db.execute("UPDATE metadata SET value='gaia_eyes' WHERE key='brand'")
        with self.assertRaises(ValueError):
            self.sync()

    def test_review_html_escapes_catalog_text_and_uses_only_local_images(self):
        self.catalog["products"][0]["title"] = '<script>alert("x")</script> Mug'
        self.sync()
        text = (self.path / "review.html").read_text()
        self.assertNotIn("<script>", text)
        self.assertIn("&lt;script&gt;", text)
        self.assertIn("Content-Security-Policy", text)
        self.assertNotIn('<img src="https:', text)

    def test_review_audit_records_revision_reviewer_and_decision(self):
        draft = self.sync()["drafts"][0]
        self.approve(draft)
        with sqlite3.connect(self.path / "queue.sqlite3") as db:
            row = db.execute("SELECT draft_id, revision, decision, reviewer FROM reviews").fetchone()
        self.assertEqual(row, (draft["draft_id"], draft["revision"], "approved", "Test reviewer"))

    def test_delete_one_format_updates_group_and_preserves_unrelated_approval(self):
        self.catalog["products"] += [product("sticker-cat", "Cat Sticker", number=2),
                                      product("mug-dog", "Dog Mug", number=3)]
        first = {d["design_key"]: d for d in self.sync()["drafts"]}
        for draft in first.values():
            self.approve(draft)
        self.catalog["products"] = self.catalog["products"][1:]
        changed = {d["design_key"]: d for d in self.sync()["drafts"]}
        self.assertEqual(len(changed), 2)
        self.assertEqual(changed["cat"]["draft_id"], first["cat"]["draft_id"])
        self.assertEqual(changed["cat"]["status"], "needs_review")
        self.assertEqual(changed["cat"]["product_title"], "Cat Sticker")
        self.assertEqual(changed["cat"]["products"], [p for p in first["cat"]["products"] if p["handle"] == "sticker-cat"])
        self.assertNotIn("/products/mug-cat", changed["cat"]["facebook_caption"])
        self.assertNotIn("/products/mug-cat", (self.path/"review.html").read_text())
        self.assertEqual(changed["dog"]["status"], "approved")
        self.assertEqual(changed["dog"]["revision"], first["dog"]["revision"])

    def test_title_and_link_changes_require_new_review_with_stable_artwork_key(self):
        self.catalog["products"][0]["tags"] = ["artwork:cat"]
        old = self.sync()["drafts"][0]
        self.approve(old)
        self.catalog["products"][0]["title"] = "Revised Cat Mug"
        renamed = self.sync()["drafts"][0]
        self.assertEqual(renamed["status"], "needs_review")
        self.assertNotEqual(old["revision"], renamed["revision"])
        self.approve(renamed)
        self.catalog["products"][0].update(handle="mug-cat-new", onlineStoreUrl="https://modpanic.com/products/mug-cat-new")
        linked = self.sync()["drafts"][0]
        self.assertEqual(linked["draft_id"], old["draft_id"])
        self.assertEqual(linked["status"], "needs_review")

    def test_empty_complete_catalog_withdraws_all_and_hides_active_cards(self):
        self.catalog["products"].append(product("mug-dog", "Dog Mug", number=2))
        for draft in self.sync()["drafts"]:
            self.approve(draft)
        report = self.sync(snapshot([]))
        self.assertTrue(all(d["status"] == "withdrawn" for d in report["drafts"]))
        self.assertNotIn("<article>", (self.path/"review.html").read_text())
        self.assertEqual(report["last_sync"]["product_count"], 0)

    def test_malformed_product_is_not_treated_as_deletion(self):
        self.approve()
        before = (self.path/"review.json").read_bytes()
        cases = []
        for field in ("title", "status", "vendor", "onlineStoreUrl", "featuredMedia", "tags"):
            data = copy.deepcopy(self.catalog)
            del data["products"][0][field]
            cases.append(data)
        for field, value in (("id", []), ("tags", "tag"), ("title", None), ("featuredMedia", {}),
                             ("featuredMedia", {"preview": []}), ("onlineStoreUrl", 4)):
            data = copy.deepcopy(self.catalog)
            data["products"][0][field] = value
            cases.append(data)
        for invalid in cases:
            with self.assertRaises(ValueError):
                self.sync(invalid)
            self.assertEqual((self.path/"review.json").read_bytes(), before)

    def test_live_fetch_failure_preserves_queue_and_last_successful_refresh(self):
        self.approve()
        before = (self.path/"review.json").read_bytes()
        def failed_fetch():
            raise CatalogError("incomplete catalog")
        with self.assertRaises(CatalogError):
            sync(failed_fetch, self.path, renderer=renderer)
        self.assertEqual((self.path/"review.json").read_bytes(), before)

    def test_live_fetch_runs_inside_exclusive_queue_lock(self):
        # A competing nonblocking lock must fail even during the network-fetch phase.
        import fcntl
        def fetch():
            with (self.path/".queue.lock").open("a") as other:
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return self.catalog
        report = sync(fetch, self.path, renderer=renderer)
        self.assertEqual(report["last_sync"]["product_count"], 1)

    def test_refresh_history_is_committed_with_queue_and_survives_review(self):
        self.catalog["fetched_at"] = "2026-11-15T06:00:00+00:00"
        first = self.sync()
        self.assertEqual(first["last_sync"]["fetched_at"], self.catalog["fetched_at"])
        self.assertEqual(first["last_sync"]["eligible_product_count"], 1)
        self.assertEqual(self.approve(first["drafts"][0])["last_sync"], first["last_sync"])
        def fail(*args):
            raise ValueError("render failed")
        with self.assertRaises(ValueError):
            sync(self.catalog, self.path, renderer=fail)
        with sqlite3.connect(self.path/"queue.sqlite3") as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM sync_runs").fetchone()[0], 1)
        page = (self.path/"review.html").read_text()
        self.assertIn("Shopify catalog retrieved", page)
        self.assertIn("Schedules are disabled", page)
        self.assertEqual(self.sync()["last_sync"]["id"], 2)


if __name__ == "__main__":
    unittest.main()
