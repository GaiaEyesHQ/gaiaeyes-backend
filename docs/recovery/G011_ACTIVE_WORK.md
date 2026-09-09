# G-011 Active Work — iOS migraine follow-up and medicine editing

Status: **running_review_repairs**, explicit September 9 retry authorized.
Sole coordinator-assigned writer: **Audit Gaia Eyes project state**,
task `01a074da-1e28-7772-92b7-2b0163664c13`.

## Resume here — September 9

- Current slice: G-R17 Decimal/timestamp interoperability, then G-R15 list and
  metadata preservation with actual-source/backend-generated fixture checks.
- Continue directly afterward with G-R16 truthful uncertain-save handling and
  G-R18 injected responses through the actual editor/follow-up workflow.
- All four findings remain open at this acceptance checkpoint. Reviewed source
  hashes match the coordinator's original findings; originals are preserved in
  `/Users/gennwu/Documents/Codex/2026-09-05/we/work/g011-review-repairs/20260909/`.
- Feature remains disabled by default and unavailable in Release. Accepted
  backend work is preserved. No production, deployment, phone, provider import,
  new dependency, or historical audit/Samsung diversion is in scope.
- Shared manager report is atomically marked `running_review_repairs`; preserve
  its prior handoff. The coordinator owns portfolio/events/human registers.
- If a platform action is denied again, record the exact error and stop that
  action; do not reroute it or claim it ran.

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

Next command: inspect the coordinator evidence bundle and current follow-up
model/view seams before making targeted changes.

## Objective

Add a bounded iOS integration for the canonical structured migraine episode detail created in G-010. The existing symptom episode remains the identity and state authority. The client must be able to load, edit, save, retry, and read back optional medicine and follow-up detail without changing the legacy flow when the new capability is unavailable.

## Safety and compatibility boundaries

- The structured iOS path is disabled by default and is only enabled explicitly for local verification.
- No production or remote SQL, migration push, deployment, release, real-user write, import, report, outreach, or new dependency is authorized.
- Retain, explicit clear, missing medicine, explicit no medicine, unknown relief, and explicit no relief must remain distinct.
- A retry must reuse the same response timestamp and structured payload.
- Save failures and revision conflicts must keep the user's draft visible.
- Draft state must not be reused after the authenticated account scope changes.
- Readback after a recoverable failure is the proof of a structured save; unchanged canonical symptom state alone is not proof.

## Existing work to preserve

G-010 backend, contract, and PostgreSQL verification changes are present in the working tree and have been accepted locally. They must not be reverted or rewritten as part of this client slice.

## Planned files

- `gaiaeyes-ios/ios/GaiaExporter/Models/FeedbackModels.swift`
- `gaiaeyes-ios/ios/GaiaExporter/Services/APIClient.swift`
- `gaiaeyes-ios/ios/GaiaExporter/Views/CurrentSymptomsView.swift`
- `gaiaeyes-ios/ios/GaiaExporterTests/GaiaExporterTests.swift`
- focused local JSON fixtures if needed for deterministic decoding/UI state verification

## Parity note

This feature is iOS-only in G-011. Android client parity and website/member-hub presentation are intentionally deferred until this local contract and interaction pass review. The canonical backend contract is shared so those clients do not need a parallel data model.

## Local verification completed

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
