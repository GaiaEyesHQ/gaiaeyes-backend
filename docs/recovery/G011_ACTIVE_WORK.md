# G-011 Active Work — iOS migraine follow-up and medicine editing

Status: **accepted_complete** as bounded local implementation, including G-R19, by the coordinator's September 10 UTC G-012 dispatch. Physical/release acceptance remains separate. Current continuation: [G012_ACTIVE_WORK.md](G012_ACTIVE_WORK.md).
Sole coordinator-assigned writer: **Audit Gaia Eyes project state**, task `01a074da-1e28-7772-92b7-2b0163664c13`.

## September 9 closeout — G-R19

- Actual follow-up and historical-editor request inputs now stay disabled during both structured and legacy saves, with visible saving feedback. Drafts remain intact and editable after errors, conflicts or cancellation.
- Deterministic delayed local responses exercise the actual forms: **24 tests / 39 executed cases passed**, including twelve new G-R19 UI cases and six existing UI regressions. Final arm64 Release simulator build, fixture-exclusion checks, source hashes and static checks passed.
- Current [handoff and evidence](/Users/gennwu/Documents/Codex/2026-09-05/we/outputs/g011-gr19/HANDOFF.md) preserve the prior accepted packet unchanged. Exactly three source/test files changed for G-R19; eleven accepted hashes remain unchanged.
- The [next historical-event/calendar proposal](/Users/gennwu/Documents/Codex/2026-09-05/we/outputs/g011-gr19/NEXT_HISTORY_CALENDAR_INCREMENT.md) records missing complete date-range history/pagination and explicit onset/end editing, with acceptance checks. It is ready for separate scoping, not implemented or a new owner-imposed order.
- D010–D012 Google organization verification/app-record creation facts are reconciled in recovery docs; no fresh console inspection is implied. D028 imports remain deferred. No deployment, personal-export handling or backend work occurred.
- Next action: coordinator review of G-R19/full G-011, then choose the next bounded core task. Physical-device acceptance and Android/website parity remain separate.

## Prior September 9 closeout — G-R15 through G-R18

- G-R15, G-R16, G-R17 and G-R18 are repaired and locally verified. No unresolved finding remains in this repair slice; the coordinator owns acceptance.
- Handoff: [G-011 review repairs](/Users/gennwu/Documents/Codex/2026-09-05/we/outputs/g011-review-repairs/HANDOFF.md). That packet includes exact commands, current source hashes, the full delta from frozen reviewed originals, final logs, backend-generated fixtures, simulator results and actual UI screenshots.
- Verification: 21 tests / 36 executed cases (30 client/workflow cases plus six actual UI tests), zero failures; current Swift/backend serializer round trip passed; final arm64 Release simulator build and fixture-exclusion check passed; diff/shell checks passed.
- Saved records and metadata are preserved. Actual save acknowledgement must match account, episode, prompt, state, next revision and edited content. Existing detail GETs cannot prove the exact follow-up response; uncertain results retain the draft for an identical explicit retry. Definite errors, cancellation and account changes do not claim success.
- Actual follow-up and history screens use injected local responses during tests. General startup auth/billing/background/push work is skipped in synthetic verification. Feature remains disabled by default and unavailable in Release; synthetic transport is Debug-only.
- Accepted G-008–G-010 backend work remains intact. No production, phone, deployment, release, account enrollment, provider ingestion or dependency changes occurred. Other dirty work is preserved.
- **D028:** provider samples received privately; H09 availability resolved. Imports follow logging, follow-up, medication, editable events and calendar, with no new order within that core group. Reports and existing outreach commitments remain. See [MIGRAINE_IMPORT_REFERENCES.md](MIGRAINE_IMPORT_REFERENCES.md). No importer work began.
- Next action: coordinator review of the packet, then reconcile the next authorized core task. Do not resume old audit, Samsung, enrollment or production checks from historical notes below.

## Ownership handoff — 2026-09-08 09:45 CDT

- The current assignment is yielding G-011 to the continuing audit task to
  avoid overlapping writers in this checkout.
- No G-R15 through G-R18 source repair was started in this turn; all four
  findings remain open.
- No build, test, deployment, migration, app release, or production/device
  mutation was performed.
- The unlocked Samsung briefly appeared to ADB as `SM-S918U1` and then
  disconnected before a diagnostic trace completed. That historical phone
  path is outside this yielded G-011 assignment and no speculative Android
  change was made.
- One stale read-only `adb logcat -d` process from the interrupted diagnostic
  attempt was stopped before handoff. No G-011 source writer or test process
  remains active.
- Preserve the dirty files listed below exactly; the continuing task owns the
  reviewed G-R15 through G-R18 repairs.

## Coordinator review repairs

- **G-R15:** preserve all medicine and early-sign records plus untouched
  metadata; do not silently replace a multi-entry list from a single-entry UI.
- **G-R16:** do not treat an unchanged structured snapshot as proof that a
  failed follow-up, requested state, or pending prompt was saved.
- **G-R17:** round-trip actual backend JSON, including Decimal strings and
  semantically equivalent UTC timestamp formats.
- **G-R18:** replace demonstration-only verification with injected local
  responses that drive the real follow-up/editor workflow and prove draft
  retention, recovery, conflicts, clears, account changes, and capability
  fallback.

The findings above are preserved as the original review requirements; see the September 9 closeout for their disposition.

## Objective

Add a bounded iOS integration for the canonical structured migraine episode detail created in G-010. The existing symptom episode remains the identity and state authority. The client must be able to load, edit, save, retry, and read back optional medicine and follow-up detail without changing the legacy flow when the new capability is unavailable.

## Safety and compatibility boundaries

- The structured iOS path is disabled by default and is only enabled explicitly for local verification.
- No production or remote SQL, migration push, deployment, release, real-user write, import, report, outreach, or new dependency is authorized.
- Retain, explicit clear, missing medicine, explicit no medicine, unknown relief, and explicit no relief must remain distinct.
- A retry must reuse the same response timestamp and structured payload.
- Save failures and revision conflicts must keep the user's draft visible.
- Draft state must not be reused after the authenticated account scope changes.
- A detail GET cannot prove the specific prompt response. Require the matching successful POST acknowledgement; retain uncertain failures for an identical explicit retry. Neither unchanged canonical state nor matching detail alone proves success.

## Existing work to preserve

G-010 backend, contract and PostgreSQL verification have been accepted locally and remain preserved in the checkout. This client repair did not rewrite them. Some previously dirty work was committed by intervening work; use the frozen original-source delta when reviewing G-011.

## Planned files

- `gaiaeyes-ios/ios/GaiaExporter/Models/FeedbackModels.swift`
- `gaiaeyes-ios/ios/GaiaExporter/Services/APIClient.swift`
- `gaiaeyes-ios/ios/GaiaExporter/Views/CurrentSymptomsView.swift`
- `gaiaeyes-ios/ios/GaiaExporterTests/GaiaExporterTests.swift`
- focused local JSON fixtures if needed for deterministic decoding/UI state verification

## Parity note

This feature is iOS-only in G-011. Android client parity and website/member-hub presentation are intentionally deferred until this local contract and interaction pass review. The canonical backend contract is shared so those clients do not need a parallel data model.

## Historical September 8 verification — superseded by September 9 closeout

- Six focused client contract tests pass for decoding, retain/clear semantics,
  explicit negative medicine/relief values, stable retry payloads, account
  isolation, and the Debug-only feature gate.
- The full `GaiaExporterTests` target passes: 39 tests.
- A deterministic synthetic migraine follow-up UI test passes on iPhone 17,
  and its screenshot was visually reviewed for dark-background readability,
  wrapping, field visibility, and Save control visibility.
- A generic iOS Simulator Release build succeeds; the structured feature gate
  resolves false outside Debug builds.
- `git diff --check` passes.

Exact local evidence:

- `/tmp/gaia-g011-ios-focused-ui.log`
- `/tmp/gaia-g011-ios-tests.log`
- `/tmp/gaia-g011-ios-release-build.log`
- `/tmp/gaia-g011-migraine-follow-up.png`
- `/tmp/gaia-g011-derived/Logs/Test/Test-GaiaEyes-2026.09.08_01-05-33--0500.xcresult`
- `/tmp/gaia-g011-derived/Logs/Test/Test-GaiaEyes-2026.09.08_01-08-11--0500.xcresult`

## Remaining acceptance work

- Review the local code and synthetic UI evidence.
- Accept and deploy the G-010 migration/backend through the normal controlled
  process before enabling the iOS feature.
- Run authenticated device tests for save, readback, conflict, retry, explicit
  clear, sign-out/account change, and follow-up notification behavior.
- Implement Android and website/member-hub parity as separately reviewed work.
