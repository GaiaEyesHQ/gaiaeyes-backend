#!/usr/bin/env python3
"""Reject obsolete GitHub owner references, not local usernames or account labels."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
import sys


LEGACY_OWNER = "gennwu"
# These two files intentionally recognize legacy origins for migration/compatibility.
# Keep exact paths: another file with the same basename is not exempt.
LEGACY_EXCEPTIONS = frozenset({
    "gaiaeyes-ios/ios/GaiaExporter/Services/MediaPaths.swift",
    "gaiaeyes-ios/.github/workflows/guard-media-links.yml",
})

_owner = re.escape(LEGACY_OWNER)
_boundary = r"(?=$|[/:?#\s\"'<>()[\]{},;`])"
LEGACY_REFERENCE = re.compile(
    # Pages origins, including scheme-less and protocol-relative references.
    rf"(?<![\w.-]){_owner}\.github\.io{_boundary}"
    # GitHub web, raw, API and archive origins, including SSH's host:owner form.
    rf"|(?<![\w.-])(?:www\.github\.com[/:]|github\.com[/:]|"
    rf"raw\.githubusercontent\.com/|codeload\.github\.com/|"
    rf"api\.github\.com/repos/){_owner}{_boundary}"
    # GitHub repositories served by jsDelivr.
    rf"|(?<![\w.-])(?:[a-z0-9-]+\.)?jsdelivr\.net/gh/{_owner}{_boundary}"
    # Explicit GitHub shorthand and bare owner/repo references. A preceding path
    # separator excludes local /Users/<owner>/... and Windows/mixed paths.
    rf"|(?<![\w.-])github:{_owner}/[\w.-]+"
    rf"|(?<![\w./\\:~-]){_owner}/[\w.-]+",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    reference: str


def legacy_references(text: str) -> list[str]:
    # JSON may escape URL slashes; still examine each reference independently so
    # a legitimate local path on the same line cannot hide an obsolete URL.
    return [match.group() for match in LEGACY_REFERENCE.finditer(text.replace(r"\/", "/"))]


def scan_repository(root: Path) -> list[Finding]:
    """Check all tracked text, including docs and tmp; no baseline allowlist."""
    result = subprocess.run(
        ["git", "-C", str(root), "grep", "--no-color", "-I", "-i", "-n", "-z",
         "-e", LEGACY_OWNER, "--", "."],
        capture_output=True,
    )
    if result.returncode not in (0, 1):
        raise RuntimeError("Could not scan tracked files: " + result.stderr.decode(errors="replace").strip())

    findings = []
    remaining = result.stdout
    # git grep -z separates the path and line number with NUL, and source lines
    # with a newline. Parse in that order to support spaces/newlines in filenames.
    while remaining:
        path_bytes, separator, remaining = remaining.partition(b"\0")
        if not separator:
            raise RuntimeError("Unexpected git grep path record")
        line_bytes, separator, remaining = remaining.partition(b"\0")
        if not separator:
            raise RuntimeError("Unexpected git grep line record")
        source, _, remaining = remaining.partition(b"\n")
        path = path_bytes.decode(errors="surrogateescape")
        if path in LEGACY_EXCEPTIONS:
            continue
        for reference in legacy_references(source.decode(errors="replace")):
            findings.append(Finding(path, int(line_bytes), reference))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    try:
        findings = scan_repository(args.root)
    except (OSError, RuntimeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    for finding in findings:
        print(f"{finding.path}:{finding.line}: obsolete GitHub reference: {finding.reference}")
    if findings:
        print("Replace obsolete origins with verified GaiaEyesHQ references.", file=sys.stderr)
        return 1
    print("No obsolete GitHub owner references outside the two legacy compatibility files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
