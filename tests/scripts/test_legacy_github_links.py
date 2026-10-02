"""Regression cases for the repository's old-owner link guard; standard library only."""

import contextlib
import io
from pathlib import Path
import subprocess
import tempfile
import unittest

from scripts.check_legacy_github_links import (
    LEGACY_EXCEPTIONS,
    LEGACY_OWNER,
    legacy_references,
    main,
    scan_repository,
)


class LegacyReferenceTest(unittest.TestCase):
    def test_obsolete_pages_origins_fail(self):
        for prefix in ("https://", "http://", "//", ""):
            with self.subTest(prefix=prefix):
                self.assertTrue(legacy_references(f"{prefix}{LEGACY_OWNER}.github.io/gaiaeyes-media/a.png"))

    def test_obsolete_github_repository_origins_fail(self):
        for host in ("github.com/", "www.github.com/", "raw.githubusercontent.com/",
                     "api.github.com/repos/", "codeload.github.com/"):
            with self.subTest(host=host):
                self.assertTrue(legacy_references(f"https://{host}{LEGACY_OWNER}/gaiaeyes-media/main/a.png"))

    def test_media_cdn_ssh_and_repository_shorthand_fail(self):
        for reference in (
            f"https://cdn.jsdelivr.net/gh/{LEGACY_OWNER}/gaiaeyes-media@main/a.png",
            f"https://fastly.jsdelivr.net/gh/{LEGACY_OWNER}/backgrounds/a.png",
            f"git@github.com:{LEGACY_OWNER}/gaiaeyes-backend.git",
            f"ssh://git@github.com/{LEGACY_OWNER}/gaiaeyes-backend.git",
            f"github:{LEGACY_OWNER}/gaiaeyes-media",
            f"{LEGACY_OWNER}/gaiaeyes-media",
            f"uses: {LEGACY_OWNER}/an-action@v1",
        ):
            with self.subTest(reference=reference):
                self.assertTrue(legacy_references(reference))

    def test_case_and_json_escaped_urls_fail(self):
        url = f"https://github.com/{LEGACY_OWNER}/gaiaeyes-media"
        self.assertTrue(legacy_references(url.upper()))
        self.assertTrue(legacy_references(url.replace("/", r"\/")))

    def test_local_paths_and_account_labels_pass(self):
        for value in (
            f"/Users/{LEGACY_OWNER}/Documents/GitHub/gaiaeyes-backend",
            f"/Users/{LEGACY_OWNER}/gaiaeyes-media",
            f"file:///home/{LEGACY_OWNER}/gaiaeyes-media",
            rf"C:\Users\{LEGACY_OWNER}\gaiaeyes-media",
            f"C:/Users/{LEGACY_OWNER}/gaiaeyes-media",
            f"./{LEGACY_OWNER}/Documents", f"~/{LEGACY_OWNER}/Documents",
            f"Projects | {LEGACY_OWNER}@example.invalid's Org",
            f"Local user: {LEGACY_OWNER}",
        ):
            with self.subTest(value=value):
                self.assertFalse(legacy_references(value))

    def test_current_owner_and_similar_names_pass(self):
        for value in (
            "https://GaiaEyesHQ.github.io/gaiaeyes-media",
            "https://github.com/GaiaEyesHQ/gaiaeyes-media",
            f"https://github.com/{LEGACY_OWNER}-tools/repo",
            f"https://other{LEGACY_OWNER}.github.io/repo",
            f"https://{LEGACY_OWNER}.github.io.example.invalid/repo",
        ):
            with self.subTest(value=value):
                self.assertFalse(legacy_references(value))

    def test_local_path_on_same_line_cannot_hide_obsolete_url(self):
        line = f'/Users/{LEGACY_OWNER}/Documents: "https://{LEGACY_OWNER}.github.io/gaiaeyes-media"'
        self.assertEqual(1, len(legacy_references(line)))


class RepositoryGuardTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)

    def track(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
        subprocess.run(["git", "-C", str(self.root), "add", "--", path], check=True)

    def test_exact_legacy_exceptions_remain_and_do_not_hide_other_files(self):
        old_url = f"https://{LEGACY_OWNER}.github.io/gaiaeyes-media/a.png"
        for path in LEGACY_EXCEPTIONS:
            self.track(path, old_url)
        self.assertEqual([], scan_repository(self.root))
        self.track("docs/MediaPaths.swift", old_url)
        self.track(".github/workflows/guard-media-links.yml", old_url)
        self.assertEqual({"docs/MediaPaths.swift", ".github/workflows/guard-media-links.yml"},
                         {f.path for f in scan_repository(self.root)})

    def test_docs_tmp_and_paths_with_spaces_or_newlines_are_checked(self):
        paths = ("docs/note with spaces.md", "tmp/saved.txt", "docs/line\nbreak.md")
        for path in paths:
            self.track(path, f"Allowed heading\n{LEGACY_OWNER}/gaiaeyes-media\n")
        findings = scan_repository(self.root)
        self.assertEqual(set(paths), {f.path for f in findings})
        self.assertTrue(all(f.line == 2 for f in findings))

    def test_cli_passes_local_paths_and_fails_actual_links(self):
        self.track("docs/example.md", f"/Users/{LEGACY_OWNER}/Documents/GitHub/project\n")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(0, main(["--root", str(self.root)]))
            self.track("source.txt", f"https://raw.githubusercontent.com/{LEGACY_OWNER}/gaiaeyes-media/main/a.png")
            self.assertEqual(1, main(["--root", str(self.root)]))

    def test_git_errors_fail_instead_of_passing_as_no_matches(self):
        with tempfile.TemporaryDirectory() as outside_git:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(2, main(["--root", outside_git]))


if __name__ == "__main__":
    unittest.main()
