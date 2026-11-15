from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
import warnings
from unittest.mock import patch

from bots.shared_social.sync_drafts import main
from bots.shared_social.shopify_catalog import CatalogError
from bots.shared_social.test_draft_queue import renderer, snapshot
from bots.shared_social.test_shopify_drafts import product


class CommandTests(unittest.TestCase):
    def test_offline_snapshot_to_review_queue_end_to_end(self):
        from bots.shared_social.draft_queue import sync
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "catalog.json"
            source.write_text(json.dumps(snapshot([product("mug-cat", "Cat Mug")])))
            output = Path(temp) / "queue"
            with patch("sys.argv", ["sync_drafts", "sync", "--catalog", str(source), "--output", str(output)]), \
                 patch("bots.shared_social.sync_drafts.sync", side_effect=lambda s, d, **k: sync(s, d, renderer=renderer, **k)), \
                 patch("bots.shared_social.sync_drafts.ShopifyCatalog") as network, redirect_stdout(io.StringIO()):
                main()
                network.assert_not_called()
            report = json.loads((output / "review.json").read_text())
            self.assertEqual(report["drafts"][0]["status"], "needs_review")
            self.assertFalse(report["publishing_enabled"])
            self.assertTrue((output / "review.html").is_file())

    def test_live_mode_calls_reader_without_meta_credentials(self):
        def process(snapshot_loader, *args, **kwargs):
            snapshot_loader()
            return {"drafts": []}
        with patch.dict("os.environ", {"MOD_PANIC_SHOPIFY_READ_TOKEN": "test-token"}, clear=True), \
             patch("sys.argv", ["sync_drafts", "sync", "--output", "unused"]), \
             patch("bots.shared_social.sync_drafts.ShopifyCatalog") as reader, \
             patch("bots.shared_social.sync_drafts.sync", side_effect=process) as sync, \
             redirect_stdout(io.StringIO()):
            reader.return_value.fetch.return_value = snapshot([])
            main()
            reader.return_value.fetch.assert_called_once_with()
            sync.assert_called_once()

    def test_missing_live_token_fails_without_network_or_queue_write(self):
        error = io.StringIO()
        with patch.dict("os.environ", {}, clear=True), \
             patch("sys.argv", ["sync_drafts", "sync", "--output", "unused"]), \
             patch("bots.shared_social.sync_drafts.ShopifyCatalog") as reader, \
             patch("bots.shared_social.sync_drafts.sync") as sync, redirect_stderr(error):
            with self.assertRaises(SystemExit) as caught:
                main()
            self.assertEqual(caught.exception.code, 1)
            reader.assert_not_called()
            sync.assert_not_called()
        self.assertIn("No posts were sent", error.getvalue())

    def test_verify_prints_metadata_without_queue_or_media_operations(self):
        output = io.StringIO()
        with patch.dict("os.environ", {"MOD_PANIC_SHOPIFY_CLIENT_ID": "id",
                                       "MOD_PANIC_SHOPIFY_CLIENT_SECRET": "private-secret"}, clear=True), \
             patch("sys.argv", ["sync_drafts", "verify"]), \
             patch("bots.shared_social.sync_drafts.ShopifyCatalog") as reader, \
             patch("bots.shared_social.sync_drafts.sync") as sync, \
             patch("bots.shared_social.sync_drafts.review") as review, redirect_stdout(output):
            reader.return_value.verify_access.return_value = {"scopes": ["read_products"], "publishing_enabled": False}
            main()
            reader.return_value.verify_access.assert_called_once_with()
            reader.return_value.fetch.assert_not_called()
            sync.assert_not_called()
            review.assert_not_called()
        self.assertEqual(json.loads(output.getvalue())["scopes"], ["read_products"])
        self.assertNotIn("private-secret", output.getvalue())

    def test_verify_failure_has_no_secret_output_or_queue_write(self):
        output, error = io.StringIO(), io.StringIO()
        with patch.dict("os.environ", {"MOD_PANIC_SHOPIFY_CLIENT_ID": "id",
                                       "MOD_PANIC_SHOPIFY_CLIENT_SECRET": "private-secret"}, clear=True), \
             patch("sys.argv", ["sync_drafts", "verify"]), \
             patch("bots.shared_social.sync_drafts.ShopifyCatalog") as reader, \
             patch("bots.shared_social.sync_drafts.sync") as sync, redirect_stdout(output), redirect_stderr(error):
            reader.return_value.verify_access.side_effect = CatalogError("private-secret")
            with self.assertRaises(SystemExit) as caught:
                main()
            self.assertEqual(caught.exception.code, 1)
            sync.assert_not_called()
        self.assertEqual(output.getvalue(), "")
        self.assertNotIn("private-secret", error.getvalue())

    def test_private_prompt_uses_no_environment_secret_or_echo(self):
        output = io.StringIO()
        with patch("sys.argv", ["sync_drafts", "verify", "--prompt"]), \
             patch("sys.stdin.isatty", return_value=True), patch("sys.stderr.isatty", return_value=True), \
             patch("bots.shared_social.sync_drafts.getpass.getpass", side_effect=[" local-id ", " local-secret "]) as prompt, \
             patch("bots.shared_social.sync_drafts.CatalogConfig.from_environment") as environment, \
             patch("bots.shared_social.sync_drafts.ShopifyCatalog") as reader, redirect_stdout(output):
            reader.return_value.verify_access.return_value = {"publishing_enabled": False}
            main()
            environment.assert_not_called()
            self.assertEqual(prompt.call_count, 2)
            config = reader.call_args.args[0]
            self.assertEqual(config.client_id, "local-id")
            self.assertEqual(config.client_secret, "local-secret")
        self.assertNotIn("local-secret", output.getvalue())

    def test_private_prompt_refuses_noninteractive_input(self):
        with patch("sys.argv", ["sync_drafts", "verify", "--prompt"]), \
             patch("sys.stdin.isatty", return_value=False), \
             patch("bots.shared_social.sync_drafts.getpass.getpass") as prompt, \
             patch("bots.shared_social.sync_drafts.ShopifyCatalog") as reader, redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                main()
            self.assertEqual(caught.exception.code, 1)
            prompt.assert_not_called()
            reader.assert_not_called()

    def test_cancelled_private_prompt_makes_no_requests(self):
        with patch("sys.argv", ["sync_drafts", "verify", "--prompt"]), \
             patch("sys.stdin.isatty", return_value=True), patch("sys.stderr.isatty", return_value=True), \
             patch("bots.shared_social.sync_drafts.getpass.getpass", side_effect=KeyboardInterrupt), \
             patch("bots.shared_social.sync_drafts.ShopifyCatalog") as reader:
            error = io.StringIO()
            # Preserve the interactive stderr contract while collecting the cancellation message.
            error.isatty = lambda: True
            with redirect_stderr(error), self.assertRaises(SystemExit) as caught:
                main()
            self.assertEqual(caught.exception.code, 130)
            reader.assert_not_called()
        self.assertIn("Cancelled", error.getvalue())

    def test_private_prompt_aborts_if_terminal_cannot_hide_input(self):
        import getpass
        def cannot_hide(_):
            warnings.warn("Cannot control echo", getpass.GetPassWarning)
            self.fail("Input would have been echoed")
        with patch("sys.argv", ["sync_drafts", "verify", "--prompt"]), \
             patch("sys.stdin.isatty", return_value=True), \
             patch("bots.shared_social.sync_drafts.getpass.getpass", side_effect=cannot_hide), \
             patch("bots.shared_social.sync_drafts.ShopifyCatalog") as reader:
            error = io.StringIO()
            error.isatty = lambda: True
            with redirect_stderr(error), self.assertRaises(SystemExit) as caught:
                main()
            self.assertEqual(caught.exception.code, 1)
            reader.assert_not_called()

    def test_workflow_runs_tests_on_pr_but_live_verification_is_manual_only(self):
        workflow = Path(".github/workflows/modpanic_social_preview.yml").read_text()
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("pull_request:", workflow)
        self.assertNotIn("schedule:", workflow)
        self.assertNotIn(": write", workflow)
        self.assertIn("default: false", workflow)
        self.assertIn("inputs.verify_shopify == true", workflow)
        self.assertIn("github.event_name == 'workflow_dispatch'", workflow)
        self.assertIn("needs: preview", workflow)
        self.assertEqual(workflow.count("secrets."), 2)
        self.assertIn("secrets.MOD_PANIC_SHOPIFY_CLIENT_ID", workflow)
        self.assertIn("secrets.MOD_PANIC_SHOPIFY_CLIENT_SECRET", workflow)
        self.assertNotIn("secrets.", workflow.split("  verify-shopify:")[0])
        self.assertNotIn("SHOPIFY_ACCESS_TOKEN", workflow)
        self.assertNotIn("FB_ACCESS_TOKEN", workflow)
        self.assertNotIn("sync_drafts sync", workflow)
        self.assertIn("sync_drafts verify", workflow)
        self.assertIn("unittest discover", workflow)

    def test_private_live_sync_completes_oauth_catalog_and_queue_without_meta(self):
        from bots.shared_social.draft_queue import sync
        from bots.shared_social.shopify_catalog import CatalogConfig, ShopifyCatalog
        from bots.shared_social.test_shopify_catalog import Session, Response, identity, oauth
        transport = Session([oauth(), identity(), Response({"data": {"products": {
            "nodes": [product("mug-cat", "Cat Mug"), product("sticker-cat", "Cat Sticker", number=2)],
            "pageInfo": {"hasNextPage": False, "endCursor": None}}}})])
        client = ShopifyCatalog(CatalogConfig(client_id="id", client_secret="local-secret"), session=transport)
        with tempfile.TemporaryDirectory() as temp, \
             patch("sys.argv", ["sync_drafts", "sync", "--prompt", "--output", temp]), \
             patch("sys.stdin.isatty", return_value=True), patch("sys.stderr.isatty", return_value=True), \
             patch("bots.shared_social.sync_drafts.getpass.getpass", side_effect=["id", "local-secret"]), \
             patch("bots.shared_social.sync_drafts.ShopifyCatalog", return_value=client), \
             patch("bots.shared_social.sync_drafts.sync", side_effect=lambda s, d, **k: sync(s, d, renderer=renderer, **k)), \
             redirect_stdout(io.StringIO()) as output:
            main()
            result = json.loads((Path(temp)/"review.json").read_text())
            self.assertEqual(result["last_sync"]["product_count"], 2)
            self.assertIsNotNone(result["last_sync"]["fetched_at"])
            self.assertEqual(len(result["drafts"]), 1)
            self.assertEqual(result["drafts"][0]["status"], "needs_review")
            self.assertEqual(len(transport.calls), 3)
            self.assertNotIn("local-secret", output.getvalue())
            self.assertNotIn("exchanged-token-do-not-log", output.getvalue())

    def test_later_catalog_page_failure_cannot_withdraw_existing_drafts(self):
        from bots.shared_social.draft_queue import sync, review
        from bots.shared_social.shopify_catalog import CatalogConfig, ShopifyCatalog
        from bots.shared_social.test_shopify_catalog import Session, Response, identity, oauth
        catalog = snapshot([product("mug-cat", "Cat Mug")])
        partial = Response({"data": {"products": {"nodes": catalog["products"],
                                                   "pageInfo": {"hasNextPage": True, "endCursor": "next"}}}})
        transport = Session([oauth(), identity(), partial, Response({"errors": [{"message": "internal"}]})])
        client = ShopifyCatalog(CatalogConfig(client_id="id", client_secret="local-secret"), session=transport)
        with tempfile.TemporaryDirectory() as temp:
            before = sync(catalog, temp, renderer=renderer)
            draft = before["drafts"][0]
            review(temp, draft["draft_id"], draft["revision"], "approved", "Reviewer")
            saved = (Path(temp)/"review.json").read_bytes()
            with patch.dict("os.environ", {"MOD_PANIC_SHOPIFY_CLIENT_ID": "id", "MOD_PANIC_SHOPIFY_CLIENT_SECRET": "secret"}, clear=True), \
                 patch("sys.argv", ["sync_drafts", "sync", "--output", temp]), \
                 patch("bots.shared_social.sync_drafts.ShopifyCatalog", return_value=client), \
                 redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                main()
            self.assertEqual(caught.exception.code, 1)
            self.assertEqual((Path(temp)/"review.json").read_bytes(), saved)
            self.assertEqual(len(transport.calls), 4)

    def test_private_prompt_cannot_be_used_with_an_offline_snapshot(self):
        with patch("sys.argv", ["sync_drafts", "sync", "--prompt", "--catalog", "snapshot.json", "--output", "unused"]), \
             patch("bots.shared_social.sync_drafts.getpass.getpass") as prompt, \
             redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            main()
        self.assertEqual(caught.exception.code, 2)
        prompt.assert_not_called()


if __name__ == "__main__":
    unittest.main()
