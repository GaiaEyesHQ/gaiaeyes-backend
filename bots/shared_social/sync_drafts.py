"""Read Shopify and update the local Mod Panic review queue; no scheduling or publishing."""
import argparse
import getpass
import json
from pathlib import Path
import sys
import warnings

from bots.shared_social.draft_images import ImageError
from bots.shared_social.draft_queue import review, sync
from bots.shared_social.shopify_catalog import CatalogConfig, CatalogError, ShopifyCatalog


def client_config(prompt=False):
    if not prompt:
        return CatalogConfig.from_environment()
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise CatalogError("Private credential entry requires an interactive terminal")
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        return CatalogConfig(client_id=getpass.getpass("Shopify Catalog Reader Client ID (hidden): ").strip(),
                             client_secret=getpass.getpass("Shopify Catalog Reader Client secret (hidden): ").strip())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    verify = commands.add_parser("verify", help="Verify Shopify credentials, store, and read-only scopes; write nothing")
    verify.add_argument("--prompt", action="store_true", help="Enter client credentials privately in an interactive terminal")
    fetch = commands.add_parser("sync", help="Automatically read the catalog and create review drafts")
    fetch.add_argument("--output", required=True, help="Persistent local queue directory")
    source = fetch.add_mutually_exclusive_group()
    source.add_argument("--catalog", help="Complete trusted snapshot for offline replay; omit for live Shopify")
    source.add_argument("--prompt", action="store_true", help="Enter client credentials privately for this live refresh")
    fetch.add_argument("--artwork-map", help="JSON object mapping product IDs or handles to stable artwork slugs")
    fetch.add_argument("--used-keys", help="JSON array of artwork keys already used; persisted as suppressed")
    approve = commands.add_parser("review", help="Record a local decision; never publish")
    approve.add_argument("--output", required=True)
    approve.add_argument("--draft-id", required=True)
    approve.add_argument("--revision", required=True)
    approve.add_argument("--decision", required=True, choices=("approved", "rejected"))
    approve.add_argument("--reviewer", required=True)
    args = parser.parse_args()
    try:
        if args.command == "verify":
            print(json.dumps(ShopifyCatalog(client_config(args.prompt)).verify_access(), sort_keys=True))
            return
        if args.command == "sync":
            overrides = json.loads(Path(args.artwork_map).read_text()) if args.artwork_map else {}
            used = json.loads(Path(args.used_keys).read_text()) if args.used_keys else []
            if not isinstance(overrides, dict) or not all(isinstance(v, str) for v in overrides.values()):
                raise ValueError("Artwork map must be a JSON object of strings")
            if not isinstance(used, list) or not all(isinstance(v, str) for v in used):
                raise ValueError("Used keys must be a JSON array of strings")
            snapshot = json.loads(Path(args.catalog).read_text()) if args.catalog else ShopifyCatalog(client_config(args.prompt)).fetch
            report = sync(snapshot, args.output, overrides=overrides, previously_used=used)
        else:
            report = review(args.output, args.draft_id, args.revision, args.decision, args.reviewer)
    except (EOFError, KeyboardInterrupt):
        parser.exit(130, "Cancelled. No posts were sent.\n")
    except (CatalogError, ImageError, ValueError, OSError, getpass.GetPassWarning):
        # Do not print exception chains, HTTP bodies, environment values, or arbitrary input.
        parser.exit(1, "Draft operation failed. Check Shopify credentials, app installation, read_products-only access, catalog, media, and review inputs. No posts were sent.\n")
    counts = {}
    for draft in report["drafts"]:
        counts[draft["status"]] = counts.get(draft["status"], 0) + 1
    print(json.dumps({"brand": "mod_panic", "publishing_enabled": False, "counts": counts}, sort_keys=True))


if __name__ == "__main__":
    main()
