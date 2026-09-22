"""Strict, draft-only server binding for gaia-draft-worker-v1-r1."""
from datetime import date, datetime, timezone
import hashlib
import json
import re

WORKER_CONTRACT = "gaia-draft-worker-v1-r1"
MAX_BODY_BYTES = 1024 * 1024
FACT_KEYS = {
    "kp_now", "kp_max_24h", "bz_min", "solar_wind_kms", "flares_24h", "cmes_24h",
    "schumann_value_hz", "aurora_headline", "aurora_window", "quakes_count",
    "severe_summary", "recent_signal_history",
}
INPUT_KEYS = {"schema_version", "job_id", "sample_kind", "example_status", "day",
              "facts_as_of", "geographic_scope", "source_manifest", "facts", "recent_public_copy"}
OUTCOME_KEYS = {
    "schema_version", "artifact_kind", "worker_contract", "status", "terminal", "recorded_at",
    "job_id", "job_version", "facts_sha256", "claim_id", "job_envelope_sha256",
    "input_classification", "current_conditions_eligible", "writer_invoked", "issues", "draft",
    "partial_output_sha256", "failed_result_diagnostic", "outcome_role", "eligibility",
}
TERMINAL_STATUSES = {
    "draft_review_ready", "deadline_expired_before_work", "claim_expired_before_work", "writer_busy",
    "malformed_writer_output", "validation_failed", "interrupted_local_partial",
    "deadline_expired_after_writer", "claim_expired_after_writer", "facts_stale_after_writer",
}
ELIGIBILITY = {key: False for key in (
    "editorial_acceptance", "renderer", "publisher", "production_return", "production_activation")}
SHA_RE = re.compile(r"[0-9a-f]{64}")
ID_RE = re.compile(r"[a-z0-9][a-z0-9._-]{2,79}")


class DraftError(ValueError):
    def __init__(self, code, status=400):
        self.code, self.status = code, status
        super().__init__(code)


def require(condition, code="invalid_job", status=400):
    if not condition:
        raise DraftError(code, status)


def canonical(value):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                          allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, OverflowError, UnicodeError) as exc:
        raise DraftError("invalid_request") from exc


def sha256(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def timestamp(value):
    try:
        require(isinstance(value, str))
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        require(parsed.utcoffset() is not None)
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError) as exc:
        raise DraftError("invalid_job") from exc


def validate_facts(packet, classification, now):
    require(isinstance(packet, dict) and set(packet) == INPUT_KEYS)
    require(len(canonical(packet)) <= 65536 and packet["schema_version"] == "1.0")
    require(isinstance(packet["sample_kind"], str) and packet["sample_kind"] in {"quiet", "active", "missing_data"})
    require(all(isinstance(packet[k], str) and packet[k].strip() for k in
                ("job_id", "example_status", "day", "facts_as_of", "geographic_scope")))
    require(ID_RE.fullmatch(packet["job_id"]) is not None)
    try:
        day = date.fromisoformat(packet["day"])
        require(day.isoformat() == packet["day"])
    except ValueError as exc:
        raise DraftError("invalid_job") from exc
    observed = timestamp(packet["facts_as_of"])
    require(observed <= now and observed.date() == day, "facts_stale", 410)
    if classification == "dated_production_facts":
        require(packet["example_status"] == "production_observed_input")
        require(day == now.date(), "facts_stale", 410)
    else:
        require(classification == "synthetic_review_fixture" and packet["example_status"].startswith("synthetic_"))
    facts = packet["facts"]
    require(isinstance(facts, dict) and set(facts) == FACT_KEYS)
    for key in FACT_KEYS - {"aurora_headline", "aurora_window", "severe_summary", "recent_signal_history"}:
        require(facts[key] is None or type(facts[key]) in (int, float))
    for key in ("aurora_headline", "aurora_window", "severe_summary"):
        require(facts[key] is None or isinstance(facts[key], str))
    require(isinstance(facts["recent_signal_history"], list))
    sources = packet["source_manifest"]
    require(isinstance(sources, list) and 0 < len(sources) <= 20)
    for source in sources:
        require(isinstance(source, dict) and set(source) == {"source_id", "source_type", "source_path", "source_sha256"})
        require(all(isinstance(v, str) and v for v in source.values()))
        require(SHA_RE.fullmatch(source["source_sha256"]) is not None)
        if classification == "dated_production_facts":
            require((source["source_type"], source["source_path"]) in {
                ("canonical_public_mart", "marts.space_weather_daily"),
                ("canonical_public_mart", "marts.kp_obs"),
                ("canonical_public_mart", "marts.schumann_daily"),
                ("canonical_public_observation", "ext.schumann"),
                ("canonical_public_observation", "ext.space_weather"),
                ("canonical_public_observation", "ext.magnetosphere_pulse"),
                ("canonical_public_copy", "content.earthscope_writer_public_history"),
            })
    require(isinstance(packet["recent_public_copy"], list))
    for item in packet["recent_public_copy"]:
        require(isinstance(item, dict) and set(item) == {"source_id", "text"})
        require(all(isinstance(v, str) and v.strip() for v in item.values()))
    return day


def job_envelope(row):
    return {
        "schema_version": "1.0", "job_id": row["job_id"], "job_version": row["job_version"],
        "facts_sha256": row["facts_sha256"], "facts_packet": row["facts_packet"],
        "deadline_at": row["deadline_at"].astimezone(timezone.utc).isoformat(),
        "claim": {"claim_id": row["claim_id"], "lease_expires_at": row["lease_expires_at"].astimezone(timezone.utc).isoformat()},
        "input_classification": row["input_classification"], "requested_outcome": "draft_review_only",
    }


def validate_outcome(value, digest, job, now):
    require(isinstance(value, dict) and set(value) == OUTCOME_KEYS, "invalid_outcome")
    require(len(canonical(value)) < MAX_BODY_BYTES and digest == sha256(value), "hash_mismatch")
    require(value["schema_version"] == "1.0" and value["worker_contract"] == WORKER_CONTRACT, "invalid_outcome")
    require(value["artifact_kind"] == "durable_draft_only_worker_outcome" and value["terminal"] is True, "invalid_outcome")
    require(isinstance(value["status"], str) and value["status"] in TERMINAL_STATUSES
            and value["outcome_role"] == "draft_review_only_not_editorially_accepted", "invalid_outcome")
    require(isinstance(value["eligibility"], dict) and set(value["eligibility"]) == set(ELIGIBILITY)
            and all(v is False for v in value["eligibility"].values()), "invalid_outcome")
    for key in ("job_id", "job_version", "facts_sha256", "input_classification"):
        require(type(value[key]) is type(job[key]) and value[key] == job[key], "facts_binding_mismatch", 409)
    require(value["claim_id"] == job["claim"]["claim_id"], "claim_mismatch", 409)
    require(value["job_envelope_sha256"] == sha256(job), "facts_binding_mismatch", 409)
    require(timestamp(value["recorded_at"]) <= now, "invalid_outcome")
    require(type(value["writer_invoked"]) is bool and type(value["current_conditions_eligible"]) is bool, "invalid_outcome")
    require(value["current_conditions_eligible"] is (job["input_classification"] == "dated_production_facts"), "invalid_outcome")
    require(isinstance(value["issues"], list) and all(isinstance(s, str) for s in value["issues"]), "invalid_outcome")
    partial = value["partial_output_sha256"]
    require(partial is None or (isinstance(partial, str) and SHA_RE.fullmatch(partial)), "invalid_outcome")
    require(len(canonical(value["draft"])) <= 524288 and len(canonical(value["failed_result_diagnostic"])) <= 262144, "invalid_outcome")
    if value["status"] == "draft_review_ready":
        draft = value["draft"]
        require(value["writer_invoked"] is True and not value["issues"], "invalid_outcome")
        require(isinstance(draft, dict) and set(draft) == {"schema_version", "candidate", "bundle", "validation"}, "invalid_outcome")
        require(len(canonical(draft)) <= 524288 and draft["schema_version"] == "1.0", "invalid_outcome")
        require(isinstance(draft["candidate"], dict) and isinstance(draft["bundle"], dict), "invalid_outcome")
        v = draft["validation"]
        require(isinstance(v, dict) and set(v) == {"status", "issues", "validator_id", "provenance"}, "invalid_outcome")
        require(v["status"] == "passed" and v["issues"] == [] and isinstance(v["validator_id"], str) and v["validator_id"], "invalid_outcome")
        expected = {"job_id": job["job_id"], "job_version": job["job_version"], "facts_sha256": job["facts_sha256"],
                    "candidate_sha256": sha256(draft["candidate"]), "bundle_sha256": sha256(draft["bundle"])}
        require(isinstance(v["provenance"], dict) and all(v["provenance"].get(k) == x for k, x in expected.items()), "facts_binding_mismatch", 409)
