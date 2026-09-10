# Migraine episode detail contract

Status: **local model, additive persistence, and authenticated backend integration; not deployed**.
Version `1.0` is implemented in `services/migraine/episode_contract.py`; the
reviewable migration and repository are
`supabase/migrations/20260908002922_add_migraine_episode_details.sql` and
`app/db/migraine.py`. The existing symptom follow-up route and two
owner-filtered migraine-detail routes now use that repository. No production
migration, client UI, import parser, or provider adapter is included in this
slice.

## Purpose

Follow-up, medicine logging, reports, and imports must describe the same
migraine episode rather than creating parallel records. The contract adds
structured detail around the existing symptom event and symptom episode; it
does not replace either one.

## Field meaning

| Contract field | Meaning and rule |
|---|---|
| `episode_id` | Identity of the existing `raw.user_symptom_episodes` row, or a staging UUID during import preview. |
| `symptom_event_id` | Link to the onset event in `raw.user_symptom_events`. Required for live manual, Siri, follow-up, and HealthKit-normalized records. It may be absent only in an import preview before commit. |
| `symptom_code` | Fixed to `MIGRAINE` for this contract. Other symptom families need their own reviewed contract or an explicit later generalization. |
| `state`, `start`, `end`, `severity` | Current episode state and timing. A resolved episode may have a recorded or unknown end; an active episode cannot have an end. Clearing an end does not reopen the episode. End cannot precede start. Severity is optional and remains 0–10 when supplied. |
| timestamp provenance | Every episode start/end and medicine time contains normalized aware UTC plus explicit timezone provenance. Original local text, IANA timezone, and offset are retained when known; `unknown` is an honest allowed provenance value. |
| `early_signs` | Optional user-reported signs. Absence means not supplied, not “none occurred.” |
| `contexts` | Optional exposure or context entries. `kind` and `source` keep a user-reported exposure distinct from device, health-record, imported, or environmental context. Context does not assert causation. |
| `medicines` | User-entered name and time, with optional amount/unit pair and optional reported relief. This is a report of what the user entered, not dosage advice or evidence of effectiveness. |
| `notes` | Optional free text for the episode. |
| `provenance` | Source type/platform for every episode. Imports additionally require provider, external event ID, SHA-256 file hash, import-run ID, row reference, and mapping version for review, de-duplication, and reversal. |
| `lifecycle` | Revision plus created/updated timestamps. A deletion timestamp and scope must appear together. These fields describe edit/delete state; they do not perform deletion. |

Unknown fields are rejected. This prevents a provider adapter from silently
dropping or inventing mappings. Optional fields remain `null` or empty until a
user or a source actually supplies them.

## Existing architecture mapping

| Existing Gaia Eyes field/path | Contract mapping |
|---|---|
| `raw.user_symptom_events.id` | `symptom_event_id` |
| `raw.user_symptom_events.ts_utc` | Original source onset; preserved when a canonical onset is corrected |
| `raw.user_symptom_events.severity` | initial `severity` |
| `raw.user_symptom_episodes.id` | `episode_id` |
| `raw.user_symptom_episodes.current_state` | `state` |
| `raw.user_symptom_episodes.started_at` | `start.utc` |
| `raw.user_symptom_episodes.resolution_ts` | `end.utc` when resolved |
| `raw.user_symptom_episodes.latest_note_text` | latest plain-text projection of `notes`; it is not storage for structured medicine/context data |
| `raw.user_symptom_episode_updates` | append-only audit entries for later edits/state changes; onset history must not be rewritten |
| existing follow-up scheduler/routes | collector/editor for contract details; no parallel reminder system |

Structured early signs, contexts, medicines, full timezone provenance, import
provenance, and contract revisions are stored as a validated contract snapshot
in an additive, user-owned detail table. The repository keeps the existing
episode and onset event as canonical identity, uses optimistic revisions, and
writes an append-only snapshot audit in the same transaction. It does not
overload `follow_up_state`, `latest_note_text`, or generic exposure records to
imply treatment.

Direct table access remains owner-filtered and read-only for authenticated
clients. Mutations stay behind the backend repository so a direct table write
cannot bypass revision, parent-ownership, and audit behavior. The authenticated
backend routes are described below; no direct Data API mutation is added.

## Saved time corrections (G-013)

The [time-correction contract](MIGRAINE_TIME_CORRECTION_CONTRACT.md) adds a default-off owner/revision/token-protected operation for canonical `started_at` and `resolution_ts`. It preserves raw events and original update occurrence timestamps, and appends the correction to the existing detail revision audit. Current summary readers use a live correction-aware projection. This operation is distinct from ordinary update `ts_utc` / structured `occurred_at`.

## Local backend API integration

- `GET /v1/symptoms/current/{episode_id}/migraine-detail` projects the existing
  canonical migraine episode plus any structured detail snapshot.
- `PATCH /v1/symptoms/current/{episode_id}/migraine-detail` requires
  `expected_revision` and applies only supplied structured fields.
- `POST /v1/symptoms/follow-ups/{prompt_id}/respond` retains its legacy request
  behavior. An optional nested `migraine` block stores the same structured
  fields atomically with the existing prompt response.

For list fields, omission keeps the stored value and `[]` explicitly clears it;
JSON `null` is rejected. For notes, omission keeps the stored value and `null`
explicitly clears it. Missing medicine or relief remains distinct from an
explicit empty medicine list or `reported_relief: "none"`. Stale conflicting
revisions return a conflict, while an exact retry of the immediately completed
revision is idempotent and cannot duplicate medicine entries. A missing
unapplied migration returns a capability error; legacy follow-up requests that
omit the structured block continue to work without that migration.

Canonical state/note projection, structured detail, revision audit, and prompt
changes share one outer transaction. The structured prompt path locks and
validates the canonical episode/detail revision before locking and answering
the prompt. Exact sequential or concurrent replays return the stored result
without another prompt, canonical, detail, or audit write; conflicting stale
requests fail before overwriting newer data. Gauge refresh happens only after
the outer request transaction commits and only for the affected user. The
original symptom onset event and episode identity are never replaced by a
follow-up edit.

Import runs and episode links are separate from clinical episode identity. A
durable identity registry maps a stable provider event ID or reviewed clinical
fingerprint (`source_identity_key`) to the canonical episode; a new file hash or
run ID alone cannot create a second episode. Preview, committed, and reversed
run states remain explicit. Replaying the same run or linking a later run reuses
the stored detail without overwriting user edits. Reversing one committed run
removes only that run's links, retains an episode referenced by another import,
and retains both the episode and stable identity after a structured edit or any
user-authored canonical symptom follow-up/update. That protection is not
limited by the update's reported event time or by which linked run is reversed
first.

Canonical deletion requires positive import-ownership evidence; an import link
alone is not ownership. The future importer must create both the canonical
symptom event and episode with the exact source `import:<import-run-id>`. Commit
derives and stores that proof from the canonical rows rather than accepting a
caller boolean. Re-linking a pre-existing manual episode therefore remains
non-owned and reversal preserves it. Missing or ambiguous origin proof also
preserves the episode. This is intentionally loss-averse. The deletion and
retention rules have now executed against a disposable PostgreSQL 17 database;
provider-specific import behavior remains unclaimed until a future importer
creates canonical rows using the same reviewed source rule.

## Compatibility and lifecycle rules

1. Live creation continues through the canonical symptom writer, which creates
   the symptom event and reuses/creates its linked episode.
2. Import preview may assign a staging `episode_id` with no
   `symptom_event_id`. Commit must create the canonical onset event first, then
   link the existing episode system; it must not create a parallel migraine
   table.
3. Import provenance retains provider, external event ID, file hash, mapping
   version, and run. Clinical de-duplication uses provider plus the stable
   `source_identity_key`, independent of run and file hash. A provider adapter
   must resolve that identity before creating the canonical onset event. When
   the import creates the onset, both canonical rows must use
   `source=import:<import-run-id>` so ownership can be proven without a
   caller-supplied flag. The adapter must create those canonical rows and call
   `commit_migraine_import_episode` on the same connection inside one outer
   transaction. A competing identity conflict must roll back the candidate
   onset rows with the failed commit rather than leave an orphan episode.
4. Structured edits increment `lifecycle.revision`, update `updated_at`, and
   append a detail snapshot audit. Canonical state/note projections also append
   the existing symptom episode-update audit. Neither path mutates the original
   onset event.
5. Existing episode deletion remains user/account scoped and cascades through
   existing episode ownership. Imported-history deletion must additionally
   remove the selected import run and recalculate affected derivatives.
6. Reports display unknown optional values as unknown/not provided. They must
   not turn a missing medicine, context, early sign, or relief value into a
   negative answer.
7. Provider-specific mappings require redacted real exports and a reviewed
   mapping version. The generic fixtures do not claim Migraine Buddy, Bearable,
   or any other provider compatibility.

## Synthetic verification fixtures

- `live_siri_episode.json` covers a linked live episode, timezone provenance,
  early signs, mixed context sources, user-entered medicine, and reported
  relief.
- `generic_import_episode.json` covers an import preview with reversible,
  de-duplicable provenance and intentionally missing optional clinical detail.

The tests also reject reversed timing, incomplete live linkage, incomplete
import provenance, partial dose data, and unmapped extra fields.

Repository tests additionally cover cross-account parent rejection, stale
revision rejection, transaction orchestration around detail/audit failure,
file-independent import identity, same-run replay, later-run re-linking without
overwriting user-edited detail, duplicate clinical identity rejection, both
two-run reversal orders, backdated user notes/state/follow-up protection,
missing detail markers, manual-episode re-link protection, and deletion only
with positive canonical import-origin evidence and no independent user history.
The scripted repository tests are supplemented by
`tests/db/test_migraine_postgres_integration.py`, which applies the unchanged
migration to a private disposable PostgreSQL 17 cluster and exercises real
foreign keys, grants, RLS, rollback, competing connections, replay, reversal,
the adapter outer-transaction requirement, authenticated request-shaped
follow-up persistence, explicit clearing, exact sequential and concurrent
retry behavior, cross-account isolation, separate-connection visibility before
gauge refresh, and both immediate audit-failure and deferred outer-commit
rollback. The request-path tests also verify the canonical note preview/count
returned after structured note save and clear. Run the focused suite with
`./scripts/run_migraine_postgres_tests.sh`; it rejects non-private or remote
database targets before connecting, verifies a disposable marker after
connecting, preserves its exact log, and stops/removes the temporary cluster.
The current review-ready G-010 run passed 63 tests. That fixture does not emulate
GoTrue, PostgREST, the Supabase gateway/pooler, or other hosted integration
surfaces. The pgTAP suite remains pending because pgTAP is not installed in the
isolated runtime. No production database was used as a substitute.

## Local iOS integration status

G-011 adds a local iOS client for this contract through the existing current
symptom follow-up and historical symptom editor. The client distinguishes
omitted fields from explicit clears, missing medicine from an explicit “No
medicine taken,” and unknown relief from explicit “No relief.” It reuses a
stable response timestamp across retries, sends an optimistic expected
revision, preserves the draft on errors or conflicts, and requires structured
detail readback before treating an ambiguous structured save as recovered.

The integration is disabled by default and cannot activate in a Release build.
It is available only in a local Debug build with the explicit
`-gaia-enable-structured-migraine-follow-up` launch argument or
`GAIA_ENABLE_STRUCTURED_MIGRAINE_FOLLOW_UP=1`. No hosted migration, backend
deployment, TestFlight build, or production activation is part of G-011.
Android and website/member-hub presentation are intentionally deferred; a
repository search found no equivalent editable migraine-medicine surface to
update without creating a new parallel UI.
