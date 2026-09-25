"""Explicitly qualified consumption of the unchanged draft-only worker contract.

Worker validation is machine evidence, never editorial acceptance. Activation
is a separate operator-selected configuration after the D044 review.
"""
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from services.earthscope_writer_contract import (
    ID_RE, require, sha256, job_envelope, validate_facts, validate_outcome,
)

TEXT_FIELDS = ("title", "caption", "snapshot", "affects", "playbook", "voiceover")
REEL_FIELDS = ("hook", "signal", "effects", "pattern", "voiceover")
BUNDLE_KEYS = {*TEXT_FIELDS, "schema_version", "hashtags", "social_variants", "reel_story"}


def writer_mode(environ):
    mode = environ.get("EARTHSCOPE_WRITER_MODE", "legacy")
    require(mode in {"legacy", "local_primary"}, "invalid_writer_mode")
    return mode


def activation(environ):
    require(writer_mode(environ) == "local_primary", "local_primary_disabled")
    result = {}
    for key in ("ACCEPTANCE_ID", "VALIDATOR_ID", "CAPTION_PROFILE"):
        value = environ.get("EARTHSCOPE_LOCAL_" + key, "")
        require(isinstance(value, str) and 3 <= len(value) <= 160
                and all(32 < ord(c) < 127 for c in value), "local_primary_unqualified")
        result[key.lower()] = value
    return result


def current_day(day, now, tz_name="America/Chicago"):
    # The transport binds UTC-day facts; daily distribution also binds the
    # configured local day. Never relabel yesterday on a late retry.
    require(type(day) is date and now.utcoffset() is not None, "invalid_day")
    require(day == now.astimezone(timezone.utc).date()
            == now.astimezone(ZoneInfo(tz_name)).date(), "facts_stale", 410)


def validate_bundle(bundle):
    require(isinstance(bundle, dict) and set(bundle) == BUNDLE_KEYS, "incomplete_bundle")
    require(bundle["schema_version"] == "1.0", "invalid_bundle")
    def text(value, maximum):
        require(isinstance(value, str) and value.strip() and len(value) <= maximum
                and "\x00" not in value, "invalid_bundle")
    def tags(value):
        text(value, 600)
        require(1 <= len(value.split()) <= 30 and all(tag.startswith("#") for tag in value.split()), "invalid_bundle")
    for key in TEXT_FIELDS:
        text(bundle[key], 10000 if key not in {"title", "caption"} else 2200)
    tags(bundle["hashtags"])
    variants = bundle["social_variants"]
    require(isinstance(variants, dict) and set(variants) == {"default", "ig", "fb"}, "incomplete_bundle")
    for variant in variants.values():
        require(isinstance(variant, dict) and set(variant) == {"caption", "hashtags"}, "invalid_bundle")
        text(variant["caption"], 2200)
        tags(variant["hashtags"])
        require(len(variant["caption"] + "\n\n" + variant["hashtags"]) <= 2200,
                "social_caption_too_long")
    require(variants["default"]["caption"].strip() == bundle["caption"].strip(),
            "default_copy_mismatch")
    reel = bundle["reel_story"]
    require(isinstance(reel, dict) and set(reel) == set(REEL_FIELDS), "incomplete_bundle")
    for value in reel.values():
        text(value, 2000)


def publication_post(row, policy, *, now, tz_name="America/Chicago"):
    current_day(row["day"], now, tz_name)
    require(row["status"] == "returned" and row["acknowledgement_id"], "draft_not_ready")
    require(row["input_classification"] == "dated_production_facts", "synthetic_not_publishable")
    facts = row["facts_packet"]
    require(row["facts_sha256"] == sha256(facts), "facts_binding_mismatch")
    validate_facts(facts, row["input_classification"], now)
    job = job_envelope(row)
    outcome = row["outcome"]
    validate_outcome(outcome, row["outcome_sha256"], job, now)
    require(outcome["status"] == "draft_review_ready", "draft_not_ready")
    validation = outcome["draft"]["validation"]
    require(validation["validator_id"] == policy["validator_id"]
            and validation["provenance"].get("caption_profile") == policy["caption_profile"],
            "unqualified_validator")
    bundle = outcome["draft"]["bundle"]
    validate_bundle(bundle)
    sections = {key: bundle[key] for key in (*TEXT_FIELDS[1:], "reel_story")}
    metrics = dict(facts["facts"])
    metrics.update(sections=sections, social_variants=bundle["social_variants"],
                   facts_as_of=facts["facts_as_of"],
                   writer_source={"mode": "local_primary", **policy, "job_id": row["job_id"],
                       "job_version": row["job_version"], "facts_sha256": row["facts_sha256"],
                       "outcome_sha256": row["outcome_sha256"], "bundle_sha256": sha256(bundle),
                       "acknowledgement_id": row["acknowledgement_id"]})
    # The wire's wind can be a latest value or daily mean. Use a neutral
    # observation label instead of inventing an aggregation or current value.
    metrics["solar_wind_label"] = "SW speed (observed)"
    metrics["facts_scope"] = facts["geographic_scope"]
    metrics["space_json"] = {"kp_now": metrics["kp_now"], "sw_now": None, "bz_now": None,
                             "aurora_headline": metrics["aurora_headline"],
                             "aurora_window": metrics["aurora_window"]}
    body = "\n\n".join("## " + title + "\n" + bundle[key] for title, key in (
        ("Space Weather Snapshot", "snapshot"), ("How This Affects You", "affects"),
        ("Self-Care Playbook", "playbook")))
    return {"day": row["day"].isoformat(), "platform": "default", "user_id": None,
            "title": bundle["title"], "caption": bundle["caption"], "hashtags": bundle["hashtags"],
            "body_markdown": body, "metrics_json": metrics,
            "sources_json": facts["source_manifest"]}


def daily_json(post):
    sections = post["metrics_json"]["sections"]
    return {"day": post["day"], "title": post["title"], "caption": post["caption"],
            **{k: sections[k] for k in ("snapshot", "affects", "playbook")},
            "metrics": post["metrics_json"], "timestamp_utc": post["metrics_json"]["facts_as_of"]}


def load_primary_post(environ=None, *, now=None, allow_review=False):
    """All three consumers read the same run artifact; no latest-row fallback."""
    env = os.environ if environ is None else environ
    if writer_mode(env) != "local_primary":
        return None
    path, digest, target = (env.get(k, "") for k in (
        "EARTHSCOPE_PRIMARY_POST_PATH", "EARTHSCOPE_PRIMARY_POST_SHA256", "TARGET_DAY"))
    require(path and digest and target, "primary_artifact_missing")
    post = json.loads(Path(path).read_text())
    require(sha256(post) == digest, "primary_artifact_mismatch")
    require(post["day"] == target and post["platform"] == "default" and post["user_id"] is None,
            "primary_artifact_mismatch")
    current_day(date.fromisoformat(target), now or datetime.now(timezone.utc),
                env.get("GAIA_TIMEZONE") or "America/Chicago")
    require(post["metrics_json"]["writer_source"]["mode"] == "local_primary", "primary_artifact_mismatch")
    require(allow_review or post["metrics_json"]["writer_source"]["acceptance_id"] != "review-only-not-accepted",
            "editorial_acceptance_required")
    return post
