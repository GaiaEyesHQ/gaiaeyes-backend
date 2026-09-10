# G-013 — canonical migraine time correction

Status: **implemented and verified locally; contract recorded before implementation**, September 10, 2026 UTC. Local/default-off increment; no deployment or source-event rewrite.

## API and meaning

`GET /v1/symptoms/current/{episode_id}/migraine-times` loads the owner-filtered canonical timing, structured detail/revision and canonical `updated_at` token. `POST` to the same path submits a deliberate correction. Both require `GAIA_MIGRAINE_TIME_EDITING_ENABLED=1`, the additive audit capability and both correction-aware read projections. Missing capability is 503. Existing event/update/detail endpoints retain their meanings.

Request fields:

- `request_id`: a new UUID for a new correction; retained unchanged for an identical retry.
- `expected_revision`: exact currently loaded structured revision (zero if no detail exists).
- `expected_canonical_updated_at`: currently loaded canonical timestamp; protects against intervening legacy edits that do not advance the structured revision.
- `start`: omitted means retain; a complete timestamp sets onset; null is invalid.
- `end`: omitted means retain; a complete timestamp sets end; null deliberately clears the recorded end.
- `state`: omitted means retain; an explicit existing episode state changes it. Null is invalid.

At least one correction field must be supplied. A set timestamp includes aware UTC, IANA timezone, original local wall time and UTC offset, with user provenance. The wall time, zone, offset and UTC must describe the same instant. Supported datetime microseconds are preserved in both normalized UTC and local values, the request fingerprint/audit and acknowledgement; normalized requests must revalidate without losing precision. Gaps are rejected; a repeated DST wall time requires an explicit occurrence/offset. Invalid input is never silently normalized into a different local time. New stored times cannot be in the future beyond a five-minute clock tolerance. End must be at or after onset.

An ongoing episode has no recorded end. A resolved episode may have an explicit end or an **unknown end**. Clearing an end retains the state; it never reopens an episode. Setting an end on an ongoing episode requires an explicit resolved state. Reopening an ended episode requires an explicit non-resolved state and explicit end clearing. An inconsistent legacy end is shown as unknown for the validated detail, while its actual stored value is available in the time-edit context and preserved in the correction audit. The user can repair it without inventing an original duration.

## Atomic persistence and retries

Lock canonical episode first and structured detail second, always with owner predicates. Check request identity, expected revision and canonical timestamp under those locks. Update canonical `started_at` / `resolution_ts` / explicit state, the projected detail snapshot, revision and before/after audit in one outer transaction. Preserve all omitted notes, medicine/sign/context entries, source provenance, raw onset events and original update rows. No new symptom event or medicine record is created by a correction.

The existing detail-revision table receives nullable correction request/metadata columns and an owner/request unique index. Metadata records the normalized request, previous raw canonical timing and timestamp provenance, resulting timing and affected refresh dates. Existing revision payloads and source events remain unchanged. The first correction therefore preserves original values even when no detail snapshot existed before it.

An exact repeated request ID/body returns the recorded acknowledgement without another canonical write, revision, audit or prompt. Reusing that ID with another body/episode returns 409. A different request with stale tokens returns 409 even if its values resemble a saved snapshot. An acknowledgement identifies request, episode, applied revision and current revision; an older acknowledged correction cannot masquerade as the latest state. A supplied correction that changes nothing is rejected without writing.

Initial interaction/state timestamps that still equal the old onset follow a corrected onset; later interactions retain their own occurrence times. An explicit state transition records the current interaction/state-change time. A time-only correction does not claim a new current symptom interaction.

## Follow-up and derived effects

Resolved state expires pending/snoozed prompts. A time-only correction does not create another prompt. A pending, undelivered onset-anchored prompt moves with the onset, clamped to now; delivered and explicitly snoozed reminders retain their timing. Explicit reopening uses the existing preferences/cadence/limit rules. These changes share the correction transaction; retries and rollbacks cannot duplicate prompts.

A correction-aware read projection uses canonical migraine onset while retaining the original raw event timestamp in source storage. Current daily/today summaries, gauge event inputs and pattern-engine symptom inputs must use that projection when installed, with legacy fallback when absent for ordinary reads. The post-correction refresh requires corrected event/daily sources directly: missing capability, denied access or failed required symptom SQL must propagate, never select original-event inputs or fabricate an empty history. Gauge writes occur only after those required reads succeed. Existing raw-event materialized tables are preserved; active lunar-pattern reads must use the corrected daily projection rather than those original-event totals. The legacy `symptom_x_space_daily` materialized artifact is not rebuilt into a new reporting product in this increment; its original-event semantics and later report integration remain explicit.

Only after commit, refresh the old/new affected computed gauge days (America/Chicago) and the affected user pattern window through existing scorer/job mechanisms. Include the normal recent pattern window and earlier affected dates so stale old-day rows are replaced. UTC daily counts and calendar overlap are live reads of the corrected canonical projection. Do not call a refresh before commit or after rollback.

A committed correction remains saved if a downstream refresh fails. Return a separate refresh status and retain the original receipt/dates so an identical explicit retry can repeat refresh without repeating the correction. No full-population refresh or production invocation is part of verification. Performance evidence is local and synthetic; full historical per-user rebuild cost is a release consideration.

## iOS behavior

Add a separately gated time section to the existing historical editor. Display loaded persisted start/end/state and timezone context. Start/end wall-time inputs preserve literal values; DST repeated-time choices are explicit. Retain/set/clear and state intent are visible. Save time correction separately from severity/notes/medicine updates, but share the pending-input and Done/dismissal lock across all save paths. Preserve the G-012 severity guard and protect new bindings against offscreen control recreation.

A matching successful acknowledgement refreshes the editor and calendar; changes across months appear when those months are selected. Validation/conflict/network/cancellation keeps the draft. Uncertain time-correction delivery retains the identical correction request until its receipt or explicit saved-version reconciliation. Check account generation before/after authorization and response awaits. No old-account acknowledgement may update the new account's view.

A matching legacy note acknowledgement reconciles only the submitted, returned note baseline; it cannot advance the structured revision or acknowledge medicine changes. A latest matching time receipt may advance the structured draft revision only when its stored non-time baseline still matches. On a genuine conflict, **Reload and keep my edits** loads the latest full detail under account validation, reapplies changed controls while retaining untouched saved entries/provenance, and requires review and a separate save. It never blindly advances a revision or silently submits the draft.

G-R23 distinguishes an initial definitive structured-detail conflict from uncertain delivery. Once a structured save may have been sent, retain its exact complete replacement patch, expected revision, episode and account. **Retry same migraine save** resends that request; it must never rebase a pending add onto a possibly committed medicines array. Keep note, medicine, severity, legacy-save and time controls locked while unresolved. Local validation has no pending request and needs no reload. An initial definitive 409 allows the ordinary explicit rebase; a 409 after uncertainty retains the original request and offers **Review saved details** instead.

The saved-detail GET is not an acknowledgement. Display the requested and saved entries, preserving repeated names/times and metadata. **Use saved version; set aside my edits** is a deliberate local choice: adopt the reviewed detail, retain the original request in the editor's set-aside state, and send no new write. Subsequent changes require a new deliberate edit. Pending/review/set-aside state lasts for the open editor; this is not a durable offline queue or a new backend receipt API. Account changes invalidate this state. The existing exact retry matcher and backend revision rules remain unchanged.

## Verification and boundaries

Use actual disposable PostgreSQL tests for owner filtering, strict timezone validation, retain/set/clear/state behavior, invalid legacy recovery, raw-event preservation, expected tokens, rollback, exact/changed retries, audit identity, shifted calendar/daily counts and prompt effects. Distinguish mocked API/refresh tests from real database execution. Exercise real Swift request/response serialization and actual editor/calendar controls with delayed synthetic replies; inspect smaller-phone layouts and Release exclusion.

Android/member-hub parity, physical-device/release acceptance, reports and the release-dependent outreach hold remain explicit. D028 keeps provider imports deferred. No provider samples, production SQL, social files, accounts or new dependencies are included.
