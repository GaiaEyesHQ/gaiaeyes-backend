# EarthScope draft-worker delivery

This is a default-off, draft-only bridge for `gaia-draft-worker-v1-r1`. It does not replace the daily OpenAI writer or authorize publication. `local_primary` is not implemented. Queue outcomes remain separate from `content.daily_posts`, renderers and social posting.

## Worker HTTP contract

The API requires `EARTHSCOPE_DRAFT_QUEUE_ENABLED=1`, a configured `EARTHSCOPE_DRAFT_WORKER_ID` and `EARTHSCOPE_DRAFT_WORKER_TOKEN_SHA256`. Every request sends a dedicated `Authorization: Bearer …` token plus matching `X-Gaia-Worker-Id`. Use an opaque 32–256 character ASCII letter/digit/underscore/hyphen token, not an existing API, JWT or database credential. Only its lowercase SHA-256 digest belongs in server configuration. No credential is included in this repository.

`POST /v1/earthscope/writer/claim-next` accepts exactly:

```json
{"schema_version":"1.0","worker_contract":"gaia-draft-worker-v1-r1","claim_request_id":"persisted canonical UUID string"}
```

A successful response is `{"status":"claimed","job":{…}}` or `{"status":"idle","job":null}`. Persist the request ID before sending; reuse it on uncertain transport. Repeating an idle request keeps returning idle, even after another job appears. Use a new request ID for a new poll. A different request while this worker owns a live claim returns `409 worker_busy`.

The exact job keys are `schema_version`, `job_id`, `job_version`, `facts_sha256`, `facts_packet`, `deadline_at`, `claim`, `input_classification` and `requested_outcome`. `claim` has only `claim_id` and `lease_expires_at`. `requested_outcome` is always `draft_review_only`. Pass this job unchanged to the existing Local AI worker.

Claims are immutable, last at most 900 seconds and end no later than the prepared deadline. Jobs have at most a 1,800-second preparation window. There is no renewal, reassignment or automatic new version. The trusted preparer can explicitly create a higher version only after the previous version is terminal. Exact repeated preparation preserves the original deadline.

`POST /v1/earthscope/writer/return-outcome` accepts exactly `{"outcome":{…},"outcome_sha256":"…"}`. The outcome is the worker's complete, unchanged terminal callback object, not its delivery view. It binds job/version, facts hash, claim ID and canonical job-envelope hash; all editorial/renderer/publisher/production eligibility flags remain false. Ready drafts must carry the worker output validation/provenance structure with matching candidate/bundle hashes. This validates delivery provenance, not editorial quality or medical/scientific claims.

After committing outcome and acknowledgement atomically, the API returns `{"status":"acknowledged","outcome_sha256":"…","acknowledgement_id":"…"}`. A bound exact body/hash retry returns that same committed receipt even after expiry or day rollover. It cannot create a first late outcome. Wrong identity or conflicting duplicate rejects. The bridge must preserve its return intent/outcome before transport and must never invoke another generation to resolve uncertain acknowledgement. Non-ready terminal outcomes can be returned while their original window is valid, as clarified in the bridge compatibility decision.

Canonical hashing uses UTF-8 bytes from Python `json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)`. Hash the entire named object, not an indented artifact. This is the existing Python worker convention, not an RFC 8785 implementation. HTTP bodies are bounded at 1 MiB; facts at 64 KiB; writer output at 512 KiB; failed diagnostics at 256 KiB. Duplicate JSON keys and non-finite numbers reject.

Errors use `{"detail":{"code":"…"}}`: 400 invalid input/hash, 401 worker authentication/identity, 409 job/claim/facts/duplicate conflict, 410 expiry/staleness, and 503 disabled/unconfigured/unavailable storage. An outage is not an acknowledgement. Do not retry a definitive conflict indefinitely.

## Facts and shadow producer

Production facts use UTC calendar days, matching the existing worker. `facts.day`, `facts_as_of`'s UTC date and server UTC today must match; future or stale packets reject at preparation, claim and first return. Synthetic fixtures require their synthetic classification and can never become current production facts. Wire timestamps are normalized to UTC independently of the database session timezone.

`scripts/earthscope_draft_shadow.py` is inactive unless `EARTHSCOPE_DRAFT_SHADOW_ENABLED=1`. It requires an explicitly configured `EARTHSCOPE_DRAFT_PREPARER_DSN` and worker ID; it never falls back to an application or unknown DSN. The [public-facts adapter](EARTHSCOPE_PUBLIC_FACTS.md) qualifies explicit projections from the active public writer's sources: daily space weather, timestamped Kp, same-day Schumann and filtered prior public copy. A local qualification ledger records normalized source projections, hashes, aggregate versus observation times, rejected inputs and field meanings. The packet and ledger are retained in the shadow receipt. No HTTP outlook route, unused JSON loader, private/user table, model or real-history import is called. Missing/stale optional inputs stay null; absence is never converted into calm/zero. See the parity matrix for intentional differences and unavailable API fallback fields.

The separate `earthscope_draft_shadow.yml` workflow has only manual dispatch, with an `enabled` input defaulting to false. It prepares and waits up to 300 seconds, then uploads only a draft receipt. It does not invoke the existing generator, renderer or poster. The original daily workflow/generator are unchanged. The CLI permits 1–900 seconds, records timeout/outage explicitly and refuses to overwrite an existing local receipt.

## Database and deployment prerequisites

The migration creates two internal tables: `content.earthscope_writer_jobs` and `content.earthscope_writer_claim_requests`. RLS is enabled; PUBLIC, anon, authenticated and service_role get no queue grants. Dedicated NOLOGIN roles separate backend claim/return operations from trusted preparation. Column grants prevent changing stored facts through the backend role. There are no SECURITY DEFINER functions or worker-facing enqueue/read-all/delete routes.

The router explicitly uses `SET LOCAL ROLE gaia_earthscope_writer_backend`; the standalone producer uses `SET ROLE gaia_earthscope_writer_preparer`. Target service identities and memberships must be verified before deployment. The migration creates no login, password or role membership and grants no mart access. Separately reviewed preparer access uses the original seven daily-mart columns plus the G046 revision of the unapplied G044 migration's additional public observation projections and filtered history view. That view is deliberately owner-checked with a security barrier and SELECT granted only to the preparer. Its fixed user_id-null/default-platform filter mirrors the public classification used by the existing summary API; selected metrics and bounded public text are the entire projection. The preparer receives no SELECT on the underlying mixed public/member table, and no function or write privilege is added. The Schumann projection now reads actual `ext.schumann` timestamps with explicit UTC-day grouping; the existing daily view remains unchanged. Two SELECT policies authorize only the preparer on Kp/pulse RLS tables. Target raw timestamp type, view ownership, existing grants and effective login SET ROLE membership must be verified before applying either migration. G045 confirmed both migration versions absent; only the revised G044 file is a valid fresh-install candidate, not its archived predecessor.

Claims use a transaction-scoped worker lock, row locking and a partial pending-job index. Outcomes lock the job, check identity/lease/provenance, commit the acknowledgement, then respond. Expired pending rows are durably marked during claim or receipt checks; no scheduler or background sweeper is installed. Old acknowledgement readback never makes a stale result current.

Local tests create a fresh owned PostgreSQL cluster on a private Unix socket with no TCP listener. They do not accept an application DSN. Run `venv/bin/python -m pytest -q tests/api/test_earthscope_writer.py` where the documented cached test runtime is available; unavailable local runtime is an explicit skipped transaction check, never a reason to substitute production.

Rollback starts by disabling API and producer flags. Preserve queue/receipt evidence; the code patch must match captured source hashes before reversal. No schema drop or data deletion is needed to stop the integration. Real shadow delivery, complete native package quality, deployed role/configuration acceptance and any eventual production switch remain separate acceptance stages.
