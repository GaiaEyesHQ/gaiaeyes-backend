"""Deterministic Mod Panic artwork grouping and platform-specific review drafts."""
import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlsplit

from bots.shared_social.captions import captions_for

SHOP_DOMAIN = "modpanic.com"
# Remove complete format words only at the ends, never meaningful words inside artwork names.
FORMATS = (
    "40oz-stanley-style-carrier-with-strap-and-pockets", "crossbody-bag-small",
    "car-coaster", "tote-bag", "prayer-candle",
    "modcore-coaster", "stone-coaster", "tea-towel", "kitchen-towel", "wall-print",
    "hoodie-dress", "crop-top", "t-shirt", "tshirt", "sticker", "magnet", "mug",
    "koozie", "towel", "hoodie", "socks",
)


def slug(value):
    value = str(value).lower().replace("'", "").replace("’", "")
    return re.sub(r"[^a-z0-9]+", "-", value).strip("-")


def design_key(product, overrides=None):
    overrides = overrides or {}
    explicit = overrides.get(product.get("id")) or overrides.get(product.get("handle"))
    tagged = {str(tag)[8:] for tag in product.get("tags", []) if str(tag).startswith("artwork:")}
    if len(tagged) > 1 and not explicit:
        raise ValueError("Conflicting artwork tags; supply an explicit artwork mapping")
    if explicit or tagged:
        key = str(explicit or next(iter(tagged)))
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", key) or len(key) > 160:
            raise ValueError("Artwork mappings must contain a nonempty stable slug")
        return key
    handle = slug(product.get("handle", ""))
    for fmt in FORMATS:
        if handle.startswith(fmt + "-"):
            candidate = handle[len(fmt) + 1:]
            if not re.search(r"-price-\d|-(?:copy|yml)$", candidate):
                return candidate
            break
    # Older handles contain size/price/copy fragments; their visible titles are cleaner.
    title = slug(product.get("title", ""))
    for fmt in FORMATS:
        if title.endswith("-" + fmt):
            return title[:-len(fmt)-1]
        if title.startswith(fmt + "-"):
            return title[len(fmt)+1:]
    return title


def safe_url(value, *, image=False):
    if not isinstance(value, str) or any(ord(c) <= 32 for c in value) or "\\" in value:
        return False
    try:
        url = urlsplit(value)
        if url.scheme != "https" or url.username or url.password or url.port or url.fragment:
            return False
        if image:
            return (url.netloc == "cdn.shopify.com" and
                    url.path.startswith("/s/files/1/0416/3757/6867/") and
                    not any(part in (".", "..") for part in url.path.split("/")) and
                    "%" not in url.path)
        return (url.netloc in (SHOP_DOMAIN, "www." + SHOP_DOMAIN) and
                bool(re.fullmatch(r"/products/[a-z0-9][a-z0-9_-]*", url.path)) and not url.query)
    except ValueError:
        return False


def product_image(product):
    media = product.get("featuredMedia") or {}
    return (((media.get("preview") or {}).get("image") or {}).get("url") or "")


def make_drafts(products, previously_used=(), *, overrides=None):
    groups = defaultdict(list)
    used = set(previously_used)
    for product in products:
        if (product.get("status") != "ACTIVE" or product.get("vendor") != "Mod Panic" or
                not re.fullmatch(r"gid://shopify/Product/\d+", str(product.get("id", "")))):
            continue
        handle = product.get("handle", "")
        url, image = product.get("onlineStoreUrl"), product_image(product)
        if not safe_url(url) or not safe_url(image, image=True) or urlsplit(url).path != f"/products/{handle}":
            continue
        key = design_key(product, overrides)
        if not key or key in used:
            continue
        title = " ".join(str(product.get("title", "")).split())[:180]
        if not title:
            continue
        groups[key].append({"id": product["id"], "handle": handle, "title": title,
                            "url": url, "image_url": image})
    drafts = []
    for key, products in sorted(groups.items()):
        products.sort(key=lambda p: (not p["handle"].startswith("wall_print-"), p["handle"], p["id"]))
        hero = products[0]
        title, url = hero["title"], hero["url"]
        drafts.append({
            "brand": "mod_panic", "design_key": key,
            "draft_id": hashlib.sha256(("mod_panic:" + key).encode()).hexdigest()[:20],
            "product_id": hero["id"], "product_title": title, "product_url": url,
            "image_url": hero["image_url"], "products": products,
            **captions_for(key, hero),
            "review_notes": ["Verify artwork grouping, image/title match, rights, and product availability before approval."],
            "status": "needs_review", "approved": False,
        })
    return drafts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--used-keys")
    args = parser.parse_args()
    products = json.loads(Path(args.catalog).read_text())
    used = json.loads(Path(args.used_keys).read_text()) if args.used_keys else []
    if not isinstance(products, list) or not isinstance(used, list):
        raise ValueError("Expected JSON arrays")
    drafts = make_drafts(products, used)
    Path(args.output).write_text(json.dumps(drafts, indent=2) + "\n")
    print(f"Generated {len(drafts)} review-only drafts")


if __name__ == "__main__":
    main()
