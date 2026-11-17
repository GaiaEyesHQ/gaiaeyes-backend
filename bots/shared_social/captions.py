"""Design-specific editorial copy, separate platform voices, and explicit copy gaps."""
from functools import lru_cache
import json
from pathlib import Path
import re
from string import Formatter


@lru_cache(maxsize=1)
def load_library():
    data = json.loads(Path(__file__).with_name("caption_library.json").read_text())
    if data.get("schema_version") != 1 or not isinstance(data.get("designs"), dict):
        raise ValueError("Invalid caption library")
    for entry in data["designs"].values():
        for key in ("instagram", "facebook", "cta"):
            if not isinstance(entry.get(key), str) or not entry[key].strip():
                raise ValueError("Both platform stories and a CTA are required")
        if (not isinstance(entry.get("hashtags"), list) or
                not all(re.fullmatch(r"#[A-Za-z0-9]+", tag) for tag in entry["hashtags"])):
            raise ValueError("Invalid caption hashtags")
    versions = data.get("product_versions")
    if not isinstance(versions, dict):
        raise ValueError("Invalid product-specific captions")
    for entry in versions.values():
        if entry.get("design_key") not in data["designs"] or not entry.get("title"):
            raise ValueError("Product captions must bind to a design and title")
        for platform in ("facebook", "instagram"):
            for _, field, spec, conversion in Formatter().parse(entry[platform]):
                if field is not None and (field != "url" or spec or conversion):
                    raise ValueError("Only a plain product URL substitution is allowed")
    return data


def captions_for(design_key, product):
    """Product is the current eligible hero; saved format-specific wording is bound to it."""
    library = load_library()
    title, url = product["title"], product["url"]
    entry = library["designs"].get(design_key)
    if entry is None:
        # Never disguise unreviewed generic filler as tailored copy for a new design.
        return {"facebook_caption": f"Design-specific copy needed: {title}\n\n{url}",
                "instagram_caption": f"Design-specific copy needed: {title}",
                "caption_status": "needs_copy", "caption_origin": "missing_design",
                "caption_style": "playful_design_specific_v1"}
    version = library["product_versions"].get(product["id"], {})
    if version.get("design_key") == design_key and version.get("title") == title:
        facebook = version["facebook"].format(url=url)
        instagram = version["instagram"].format(url=url)
        origin = "saved_revision"
    else:
        facebook = f"{entry['facebook']}\n\n{title}\n\n{entry['cta']}: {url}"
        instagram = (f"{entry['instagram']}\n\n{title} at modpanic.com.\n\n"
                     + " ".join(["#ModPanic", *entry["hashtags"]]))
        origin = "design_library"
    if len(instagram) > 2200 or len(facebook) > 5000 or facebook == instagram:
        raise ValueError("Captions must fit their platform and have distinct wording")
    return {"facebook_caption": facebook, "instagram_caption": instagram,
            "caption_status": "ready_for_review", "caption_origin": origin,
            "caption_style": "playful_design_specific_v1"}
