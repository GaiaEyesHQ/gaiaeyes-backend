# G-017 — Android structured migraine client contract

September 16, 2026. **G017-R01 precision repair is review-ready; coordinator acceptance pending.** Production and unit-test Kotlin compiled; 46 focused offline JVM tests passed: 30 contract/transport tests plus 16 existing logging/DTO/queue tests. No UI activation, device acceptance, production verification or release is claimed.

Assignment: `/Users/gennwu/Documents/Codex/2026-09-06/turn-my-astra-strategy-planning-conversation/outputs/jennifer-os-starter-kit/operations/checkpoints/20260916-G017/ASSIGNMENT.md`.

Evidence: `/Users/gennwu/Documents/Codex/2026-09-05/we/outputs/g017-android-migraine-client/`.

## G017-R01 — timestamp precision repair

Independent review reproduced a successful backend normalization that the initial Android acknowledgement rejected: `2026-09-15T13:05:06.123456789Z` becomes `2026-09-15T13:05:06.123456Z` in the actual Python canonical timestamp model. The previous full-nanosecond comparison could leave that save permanently unconfirmed. This was reproduced with a synthetic canonical model, not observed on a device.

**Selected policy:** canonicalize UTC to an instant and truncate fractional seconds to microseconds before freezing the outbound JSON snapshot. Never round into the next microsecond/second, read the clock, mutate the caller's objects or rewrite original-time/timezone metadata. `MigraineTimestamp` copies change only `utc`. The same helper defines acknowledgement precision.

This applies to early-sign `reported_at`, context `observed_at`, medicine `taken_at`, medicine `relief_reported_at`, and caller-supplied follow-up `ts_utc`. Six-digit fractions retain their value; equivalent UTC offsets canonicalize to `Z`; nonzero sub-microseconds are discarded deliberately. Instant serialization may shorten insignificant trailing zeros. `original_time` can still retain the caller's original nanosecond text, and `timezone_source`, `timezone_name` and `utc_offset_minutes` remain untouched. Ordered repeated medicine entries and exact BigDecimal doses are unchanged.

`GaiaApiClient` still freezes the JSON once before I/O and compares that snapshot on response. Identity, prompt, state and next-revision checks are unchanged. A different microsecond or metadata value remains unconfirmed; no retry or GET fallback was added. The caller retains its original input while the stable outbound representation carries the supported precision.

One offline focused Gradle run passed **46 tests**, adding six regressions to the retained 40-test baseline. Coverage includes confirmed normalized PATCH and follow-up saves with one recorded attempt, all four structured timestamp locations, stable caller-supplied follow-up timestamps, six-digit and offset equivalence, truncation at second/pre-epoch boundaries, untouched metadata/ordered medicines/exact dose, and rejection of a genuinely different microsecond or metadata.

Only `MigraineResponses.kt`, its model/client tests and this scoped handoff changed for R01. `GaiaApiClient.kt`, the synthetic fixture, G018 source and prior evidence remain preserved. This repair adds no UI, backend migration, activation, device or release work. H18 is still pending and does not block this client repair.

Current evidence, source hashes, incremental/cumulative diffs, XML results and the copied independent review: `/Users/gennwu/Documents/Codex/2026-09-05/we/outputs/g017-timestamp-precision-repair-20260916/`. Original G017 evidence remains frozen at the earlier path above. The new packet records current hashes rather than overwriting historical pins.

## Outcome and scope

Android's existing `GaiaApiClient` can now read a canonical episode's structured migraine detail, patch its signs/contexts/medicines/notes, and submit a structured follow-up answer. The new DTOs retain ordered entries, exact decimal values and timestamp metadata. A write returns success only after its response matches the intended episode, submitted fields and next revision; a follow-up also requires the corresponding answered prompt and current episode state.

These methods have no production UI call sites. There is no new database, queue, backend route, dependency, activation flag, screen or generic medical disclaimer. Existing basic current-symptom routes, DTOs, authentication and journal queue behavior remain unchanged. No app-visible surface changed, so website/member-hub UI parity is not applicable to this contract-only increment.

The four governing strategy documents were rechecked: `PROJECT_STATE.md`, `PMF_STATE.md`, `DECISION_LOG.md` and `RECOMMENDED_NEXT_ACTIONS.md` already contain Jennifer's correction. Scalable acquisition/engagement and useful product/research development proceed together; immediate MRR is not a development gate. Medically meaningful capability remains an active staged direction, and disclosure should be contextual. Their accepted content was preserved in this increment.

## Source changes

| File under `gaiaeyes-android/` | Change |
|---|---|
| `app/src/main/java/com/gaiaeyes/app/core/network/GaiaApiClient.kt` | Three canonical methods, response/acknowledgement checks and narrowly scoped single-attempt transport; existing helpers remain in use by legacy operations |
| `app/src/main/java/com/gaiaeyes/app/core/network/MigraineResponses.kt` | Structured domain/response DTOs, decimal codec, explicit retain/set/clear representation, field validation and acknowledgement comparisons |
| `app/src/test/java/com/gaiaeyes/app/core/network/MigraineResponsesTest.kt` | Thirteen contract/serialization/legacy-payload tests, including precision boundaries and metadata preservation |
| `app/src/test/java/com/gaiaeyes/app/core/network/MigraineApiClientTest.kt` | Seventeen synthetic transport and acknowledgement tests, including normalized PATCH/follow-up confirmation, using existing Ktor/JUnit dependencies and no network |
| `app/src/test/resources/migraine-detail.json` | Synthetic backend-shaped fixture validated by the actual `MigraineEpisode` Pydantic model; no personal data |

## Canonical route mapping

All methods require a nonblank access token and send the existing `Authorization: Bearer …` header. IDs must be canonical UUID strings; invalid IDs are rejected before transport. No tokens or personal records were accessed for verification.

| Android method | Existing backend route | Payload / accepted result |
|---|---|---|
| `migraineDetail(token, episodeId)` | `GET /v1/symptoms/current/{episode_id}/migraine-detail` | No body. Require HTTP 200, `ok:true`, a valid `data` detail and matching episode identity |
| `updateMigraineDetail(token, episodeId, edit)` | `PATCH /v1/symptoms/current/{episode_id}/migraine-detail` | `expected_revision` plus at least one of `early_signs`, `contexts`, `medicines`, `notes`. Require matching fields and revision `expected_revision + 1` |
| `respondMigraineFollowUp(token, episodeId, promptId, request)` | `POST /v1/symptoms/follow-ups/{prompt_id}/respond` | `state`, stable caller-supplied `ts_utc`, nested `migraine` edit; optional `detail_choice`, `detail_text`, `note_text`, `time_bucket`. Require the answered prompt, matching current episode/state and matching structured detail at the next revision |

Route/schema evidence: `app/routers/symptoms.py` (`MigraineStructuredFieldsIn`, `MigraineFollowUpDetailsIn`, `MigraineEpisodeDetailUpdateIn`, the three route handlers), `services/migraine/episode_contract.py`, and optimistic revision/replay handling in `app/db/migraine.py`. Accepted iOS equivalents were read in `Models/MigraineEpisodeModels.swift`, `Services/APIClient.swift` and `Services/MigraineFollowUpWorkflow.swift`; none were changed.

The backend also supports `state`/`occurred_at` on the standalone PATCH. This slice deliberately exposes structured field editing there; state changes use the structured follow-up or existing basic update path. No Android history/editor integration or import mapping is implied.

## Field and missingness mapping

| Wire field | Android representation and behavior |
|---|---|
| `data.revision`, `data.changed`, `data.episode` | `MigraineDetail`: nonnegative revision, Boolean change marker, canonical episode. `changed:false` can acknowledge an exact replay, but still requires the correct next revision and submitted values |
| `schema_version`, `episode_id`, `symptom_event_id`, `symptom_code`, `state` | Preserved identity/version/state. Current supported schema is `1.0`, symptom `MIGRAINE`; states are `new`, `ongoing`, `improving`, `worse`, `resolved`. A non-import live episode requires its canonical symptom-event linkage |
| `start`, `end`, `severity`, `notes` | Timestamp objects; nullable end/severity/notes. Severity zero remains zero and missing severity remains null. End must not precede start and may occur only on a resolved episode |
| Every structured timestamp | Response timestamp fields are preserved. Outbound `utc` is canonical UTC truncated to microseconds; `original_time`, `timezone_name`, `utc_offset_minutes` and `timezone_source` remain untouched. UTC comparisons use the same microsecond-precision instants, so equivalent offsets/UTC spellings are accepted; original metadata must still match. Backend remains authoritative for IANA-zone validity |
| `early_signs[]` | Ordered `label`, optional `code`, `reported_at`, `notes` |
| `contexts[]` | Ordered `kind`, `label`, `source`, optional `code`, `observed_at`, `notes` |
| `medicines[]` | Ordered `name`, `taken_at`, optional paired `dose_amount`/`dose_unit`, `reported_relief`, `relief_reported_at`, `notes`. Identical names/times remain separate entries; no invented backend medicine ID or name-based merging |
| `dose_amount` | `BigDecimal`: reads backend JSON strings and older JSON numbers without a `Double` conversion, writes a decimal string, compares numeric values without rounding. Zero/negative doses and half-specified dose/unit pairs are invalid in the actual backend contract; absence is represented by both fields missing/null |
| `reported_relief` | Preserve `none`, `a_little`, `some`, `a_lot`, `complete`, `unknown`, and null as distinct values. A relief timestamp requires a reported relief value |
| `provenance` | Preserve `source_type`, `source_platform`, `source_provider`, `external_event_id`, `source_file_hash`, `import_run_id`, `raw_row_ref`, `mapping_version`; this is response decoding, not an import implementation or research-consent mechanism |
| `lifecycle` | Preserve revision, creation/update/deletion timestamps and deletion scope. Reads reject deleted current-episode details. Outer revision zero with lifecycle one is the canonical unstored-detail case; positive outer/lifecycle revisions must agree |
| Edit collections | Kotlin null means omit/retain; an empty list sends `[]` to clear. Nonempty lists replace the ordered collection. Explicit JSON-null collections are never emitted |
| Edit notes | `MigraineTextChange.Retain` omits the key, `Clear` emits `notes:null`, and `Set` emits the supplied nonblank text |
| Follow-up acknowledgement | `prompt.id`, `prompt.episode_id`, symptom, `status:answered`; current episode ID/symptom/state; no same-ID `pending_follow_up`; valid `migraine_detail` matching the submitted state and edit. Missing or mismatched components never count as a successful answer |

Strings and optional entry metadata are retained. Acknowledgement comparison permits the backend's whitespace trimming, equivalent decimal scale and the documented UTC microsecond timestamp normalization; entry order/count and all submitted metadata must otherwise match. The outbound JSON snapshot is made before I/O and reused for acknowledgement comparison.

## Error and retry behavior

| Evidence received | Result / caller responsibility |
|---|---|
| Blank token, invalid UUID, invalid edit/dose or missing standalone edit | Local validation failure; zero transport calls |
| HTTP 401 | Existing `ApiUnauthorizedException`; no automatic token-refresh/write replay |
| HTTP 409 | `MigraineConflictException`; review current data before a new save |
| HTTP 400/403/422 | `MigraineRejectedException` with status; no resend |
| HTTP 404 with `detail:"Not Found"` | `MigraineUnavailableException` for an unavailable route |
| Other well-formed HTTP 404 | `MigraineEpisodeNotFoundException` |
| HTTP 503 with exact canonical storage-not-installed detail | `MigraineUnavailableException`; explicit capability failure |
| Write transport failure, generic 5xx/408/429/redirect, missing/malformed/false envelope, wrong identity/revision/fields or incomplete follow-up acknowledgement | `MigraineUnconfirmedWriteException`; retain the original request, show uncertainty and do not automatically resend |
| Coroutine cancellation | Propagates cancellation. It does not establish whether a submitted write committed; the eventual UI must retain the pending request/account scope before dispatch |
| Read transport failure / other well-formed unsuccessful status | `MigraineUnavailableException`; no write |
| Malformed/invalid read payload | `MigraineInvalidResponseException`; no usable detail or write |

The structured client is initialized lazily with redirects and connection retries disabled. Structured write bodies use Ktor `ReadChannelContent`; the installed Ktor 3.3.3 OkHttp engine converts these into `StreamRequestBody` with `isOneShot() == true`. This also addresses OkHttp response-driven retries such as `503` with `Retry-After: 0`, beyond the connection-retry setting. Legacy operations retain their existing client configuration. Injected clients used by tests must preserve the same no-retry/no-redirect policy.

There is no automatic write loop, persisted queue or GET-after-error fallback. A detail GET cannot prove that a particular follow-up prompt was answered. This increment does not implement pending-request persistence, account-switch recovery or an explicit retry UI; those are prerequisites for the future editor, not claims made about this client slice.

## Verification and limits

Run from `gaiaeyes-android/` with the installed Android Studio JBR:

```sh
JAVA_HOME='/Applications/Android Studio.app/Contents/jbr/Contents/Home' ./gradlew --offline :app:testDebugUnitTest \
  --tests 'com.gaiaeyes.app.core.network.MigraineResponsesTest' \
  --tests 'com.gaiaeyes.app.core.network.MigraineApiClientTest' \
  --tests 'com.gaiaeyes.app.core.network.HomeContextResponsesTest' \
  --tests 'com.gaiaeyes.app.core.network.JournalResponsesTest' \
  --tests 'com.gaiaeyes.app.core.work.JournalDrainWorkerTest' \
  --tests 'com.gaiaeyes.app.core.quicklog.QuickLogCoordinatorTest'
```

- **Current R01 pass:** 46 tests, zero failures/errors/skips, in one offline run. Production and unit-test Kotlin compilation succeeded. Current evidence contains `gradle-focused-01.log`, six XML copies in `test-results/` and `test-summary.json`. The original G017 40-test pass and its `gradle-focused-04.log` remain unchanged in the frozen original packet.
- **Covered:** backend-shaped detail, string/numeric exact decimals, zero vs unknown/missing values, ordered repeated medicines and metadata, omission vs clear, stable timestamps, identity/revision/field acknowledgement, 401/409/404/422/503, malformed/false replies, lost responses, cancellation, redirects and one recorded attempt, plus legacy payload/auth/queue/quick-log compatibility.
- **Synthetic only:** an in-memory Ktor engine records outgoing requests without live API calls. Socket-level/device/provider acceptance is not established by these tests. Ktor transport behavior was also checked against installed primary source; see `transport-source-evidence.json`.
- **Earlier attempts retained:** the first run needed Ktor's test-engine internal API opt-in; subsequent harness fixes added timeout capability and the correct Ktor call context. These were test harness failures, not verified backend failures. Logs `01`–`03` remain available. The earlier pre-G017 XML was copied to `prior-unit-results/` before testing.
- **Original G017 preservation receipt:** 53 prior handoff/docs/social-evidence files and all 18 accepted G016 source/input hashes match. See `preservation-after.json`. The preceding manager report and canonical G016 test handoff remain copied in this packet.
- **Not performed:** APK/release build, lint/full test sweep, device/ADB/install, iOS execution, production API/DB calls, backend deployment, notification, import/export or store action. Source search found no UI calls to the three new methods. No purchase, external message or public content change occurred.

## Smallest next visible increment

After coordinator review, select one existing Android current-migraine entry and add a bounded detail/editor journey using these DTOs and routes. Keep separate medicine entries and exact untouched metadata; let users explicitly retain or clear values. Add account-bound immutable pending-request state before dispatch, preserve uncertain saves/cancellation, show conflicts without overwriting, and require the complete follow-up acknowledgement. Exercise the actual editor with synthetic fixtures, then separately verify the authenticated backend/device path before activation. A known unavailable backend should produce a useful unavailable state without claiming the episode was saved.

Calendar, reports, imports, reminders and full voice parity remain separate assignments. G016's focused iOS runtime/UI/Release checks remain in its accepted handoff, with no renewed owner-phone or H13/H14 request from G017. Coordinator owns portfolio state, the human queue and final acceptance.
