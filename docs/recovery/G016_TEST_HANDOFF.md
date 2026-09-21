# G016 development preview and remaining test handoff

## September 20 native acceptance — G036

Ordinary Xcode GUI execution now verifies **56 model cases + the existing gate (57 total)** and **all nine saved-summary UI journeys + one editor compatibility journey** on an owned arm64 iPhone 17e / iOS 26.5 Simulator. Positive function/parameter identities, explicit success and no unexplained skips are recorded. Corrected focused UI runs supplement the retained initial full run; the initial run was not entirely green. This supersedes the pending/unexecuted statements in the historical sections below.

The tests now explicitly verify the existing public `/health` preflight, correctly locate the loading activity indicator, and require actual enlarged text before accepting the accessibility fixture. A DEBUG-only synthetic override ensures summary content receives accessibility3 sizing. Exact dose, full note ending, missingness, error/retry, ordinary revision-0 episodes, account switching, selected-day retention and acknowledged-note reopening were verified. Fresh request receipts show GET-only summaries and exactly one intended synthetic note update followed by a fresh read, with unchanged structured revision/lifecycle.

A fresh **Release arm64 simulator build succeeded** through the same GUI route on September 20, **19:39:35–19:42:20 UTC**. All **15 fixture markers are absent from strings and symbols**. The executable is retained with SHA-256 `8b4d8c4e9ae567e7e57778e7e49015701b1bdac9bcaa32805baca09cadd63795`. Distribution signing was disabled; the Mach-O has only the linker's ad-hoc signature, no team/certificate/resource seal. No Release app was installed, run, uploaded or distributed. Default-off/Release feature gates remain unchanged.

[Current native handoff, result bundles, request receipts, reviewed screenshots and source diff](/Users/gennwu/Documents/Codex/2026-09-05/we/outputs/g036-ios-native-verification/HANDOFF.md). The disposable G036 simulator was removed and the user's original Xcode project/scheme/destination restored. G031/G034 diagnostics were not rerun. Physical-device, authenticated backend, Siri, HealthKit, subscriptions, push and distribution acceptance remain separate. G035's accepted Android APK and the four reconciled strategy documents were preserved.

## September 17 source update — G032

The saved-summary parity review selected one contract-backed gap: iOS now includes each recorded context's **Type** (`kind`) and **Source** (`source`), distinguishing user reports from device, health-record, environmental-service and imported observations. Existing observation-time/note positions, order, read-only behavior, account guards and Debug/default-off gates are unchanged. Android already displays these fields; G030 remains the unchanged owner debug APK. The two changed iOS files are the summary projection and its model tests; the previous 18-file G016 source pin set is historical, with those two explicitly superseded in the G032 diff.

Offline source checks found two missing data paths before the change and four checks passing afterward, including the unchanged view consumption paths. Four wrong-field/hardcoded in-memory mutations were rejected. This is **source verification only**, not Swift typechecking or native test execution. Added Swift regression inventory: ten context-kind/source combinations plus one same-label order/time/full-note case, all **unexecuted**. Current planned summary model inventory is **56 cases (45 existing + 11 new)**, plus the separate existing gate case; previous 45-case references below describe the pre-G032 source. Existing UI/Release acceptance remains pending.

G031's zero-test cancelled/unknown attempt remains intact and is not rerun. Any future fresh authorized runner must require an explicit successful result, a positive expected executed count and the expected case identities, zero failures, and no unexplained skipped/missing cases before advancing. For the current model+gate selection that means 56+1 expected cases, verified against the fresh result tree rather than treating `failedTests == 0` as success. Do not modify/reuse the consumed G031 runner. No new owner prerequisite is established.

[G032 parity matrix, exact diff, source-check receipts and acceptance limits](/Users/gennwu/Documents/Codex/2026-09-05/we/outputs/g032-saved-summary-parity/HANDOFF.md). This source update authorizes no Xcode, simulator/device, backend, account, release or new APK action.

Reconciled September 15 America/Chicago (September 16 UTC). **Device Debug compilation is evidenced; G016 runtime and fresh Release acceptance remain pending.** This is a docs/read-only handoff for coordinator review, not a request to run a command now.

## September 17 execution update

G031 subsequently authorized one fresh ordinary Xcode path after current preflight. Xcode 26.6 / iOS SDK and runtime 26.5, isolated DerivedData and package-cache copy, and a new owned iPhone 17e simulator were used. The focused model/gate invocation stopped at the 150-second no-output bound during `CreateBuildDescription` / clang discovery; its result bundle has **zero executed tests**, not a passing suite. UI/visual/request and Release steps were not started. The current source inventory below still applies, and all 18 accepted G016 source hashes match.

[G031's current handoff and retained result bundle](/Users/gennwu/Documents/Codex/2026-09-05/we/outputs/g031-ios-saved-summary-verification/HANDOFF.md) preserve the exact command, timing, cancellation, process ownership and cleanup. The owned simulator was deleted; the user's Xcode/build service and existing simulator were left intact. No automatic retry, Terminal workaround, old wrapper, or new owner prerequisite was introduced. Review this current evidence before selecting any later native action. The earlier successful device builds remain valid compilation evidence; no cause for the CLI stall has been established.

## Corrected build evidence

The existing Xcode `LogStoreManifest.plist` records a successful GaiaEyes build on **September 13, 16:13:16.596–16:14:02.823 UTC** (46.227 seconds). The retained `87840A3A-BBDF-4650-9165-9B6CDE0A37B0.xcactivitylog` explicitly records arm64 compilation of `MigraineEpisodeSummary.swift`, `MigraineEpisodeSummaryStore.swift`, `MigraineEpisodeSummaryView.swift` and `MigraineHistoryView.swift` at **16:13:22–25 UTC**, within that build, followed by device Debug link output. September 14 **08:01:59.715–08:02:00.406 UTC** is another successful build record; its 0.691-second duration is incremental evidence, not a complete rebuild.

The existing `Debug-iphoneos/GaiaEyes.app` executable and debug dylib are version 1.0.1/build 8 products. At the pre-G032 reconciliation, all **18 original accepted G016 source hashes matched**; G032 explicitly changes the summary projection and model tests as recorded above. Logs and current source hashes do not establish source-to-binary byte provenance, installation, successful launch, test execution, signing acceptance or a physical-device result. The September 11 compiler-discovery stalls remain historical failures; they no longer support a blanket claim that Gaia cannot build.

Exact records, decoded task timestamps, original compressed logs, artifact hashes and source comparisons are in the [reconciliation packet](/Users/gennwu/Documents/Codex/2026-09-05/we/outputs/g016-saved-episode-summary/build-evidence-reconciliation-20260915). The retained build manifest's only Testing record is September 7; it cannot establish execution of the later G016 tests. The inspected G016 evidence tree contains **zero summary PNGs and zero `g016-*-capture.json` runtime captures**.

## Currently supported development-preview path

The current [GaiaExporter project](/Users/gennwu/Documents/GitHub/gaiaeyes-backend/gaiaeyes-ios/ios/GaiaExporter.xcodeproj) supports ordinary owner-directed Xcode development preview using **GaiaEyes → Debug → an actual iPhone or installed iOS Simulator destination**. The deployment minimum is iOS 18.5. A generic device build destination cannot Run. Current destination availability was not inspected in this pass; the previously exercised simulator was **iPhone 17e / iOS 26.5**, ID `198F0747-87A0-42F7-82B0-CFA8516A99A7`.

The [shared scheme](/Users/gennwu/Documents/GitHub/gaiaeyes-backend/gaiaeyes-ios/ios/GaiaExporter.xcodeproj/xcshareddata/xcschemes/GaiaEyes.xcscheme) contains both test targets but no migraine launch flags. For a later isolated sample-data preview, the retained source-defined Run arguments are:

```text
-gaia-preview-migraine-follow-up-fixture
-gaia-enable-structured-migraine-follow-up
-gaia-enable-migraine-calendar
-gaia-enable-migraine-time-editing
-gaia-migraine-scenario
calendar-summary-full
```

The final line is the scenario value. This opens the actual calendar and summary/editor views with synthetic September episodes. Select September 8 and **View summary** on the second episode for the full saved-summary case. Its runtime acceptance is still pending. Replace only the scenario value with `entries-success` for the previously exercised medicine/follow-up view, `time-history-entries-success` for the combined medicine/time editor, or `calendar-success` for the earlier calendar fixture. Each is a separate fixture launch, not a complete authenticated session. Siri is not exercised by these fixtures.

The Debug fixture root bypasses normal auth/background startup and uses in-memory URLProtocol transport at `gaia-fixture.invalid`. It does not load personal episodes. For normal navigation, the source route is **Home Active Symptoms → Symptom history → Migraine calendar → View summary**. Removing fixture/scenario arguments returns to the ordinary app; the three feature flags alone expose real-data paths and do not activate backend capabilities. Release rejects those feature gates. Backend deployment/activation and authenticated device acceptance remain separate and were not checked here.

Retained, inspected historical visuals can be used immediately:

- [G014 follow-up and multi-entry medicine editor](/Users/gennwu/Documents/Codex/2026-09-05/we/outputs/g014-medicine-entry-editing/editor-accessibility-attachments/455EB452-18A9-4A98-9C6E-A2659879C8A8.png): distinct saved/draft counts, edited selection and separate added entries; actual synthetic simulator capture.
- [G013 calendar after time correction](/Users/gennwu/Documents/Codex/2026-09-05/we/outputs/g013-episode-time-editing/corrected-calendar.png): canonical corrected dates and selected day; predates the new View summary action.

Neither is a G016 summary screenshot or current phone proof. The September 13 `iphoneos` product is not a simulator installation. The old `/tmp/gaia-g011-derived` Debug/Release simulator app paths are absent; the retained G014 `release-GaiaEyes` is only an older unsigned simulator binary, not an installable signed app or G016 Release acceptance.

## Exact focused execution still needed

The coordinator can select a later owner-directed Xcode test handoff using the existing **GaiaEyes** scheme and Test navigator's individual suites/methods. Run only the following scope, sequentially with parallel testing off, and retain actual result bundles and failures. This pass ran none of it. Test-source parsing yields expected counts; only later executed result bundles can prove them.

**Model/store:** `GaiaExporterTests/MigraineEpisodeSummaryTests` — **45 parameterized executions across 13 test functions** — plus `GaiaExporterTests/MigraineHistoryTests/defaultAndReleaseGate` — **one existing gate case**. The [exact function/argument inventory](/Users/gennwu/Documents/Codex/2026-09-05/we/outputs/g016-saved-episode-summary/build-evidence-reconciliation-20260915/remaining-test-inventory.json) lists every name and case. Coverage includes ordinary stored revision 0/candidate revision 1; six invalid revision pairs; repeat GET-only ordinary reads; canonical-note acknowledgement with unchanged structured lifecycle; ordered medicines and exact dose; seven relief meanings; missingness/zero severity; two DST intervals; fourteen malformed/deleted variants; four API failure scenarios; account change during authorization; five late-response races; and refresh-failure/retry clearing.

**UI:** `GaiaExporterUITests/MigraineEpisodeSummaryUITests` — **nine journeys**:

| Exact method | Fixture | Required observation |
|---|---|---|
| `testCompleteSavedSummaryAndReturnPreserveSelectedDay` | `calendar-summary-full` | Saved timing/timezone, 3-hour duration, ordered medicines, exact dose, distinct relief, full notes, unchanged selected day/month after closing |
| `testMissingFieldsStayUnanswered` | `calendar-summary-empty` | Missing end/severity/signs/context/notes stay unanswered; no medicine entries does not claim no medicine taken |
| `testOrdinarySavedEpisodeOpensWithoutStructuredDetails` | `calendar-summary-unstructured` | Revision-0 ordinary episode opens with canonical note, empty medicines and no misleading Updated label; no prerequisite structured write |
| `testUnavailableThenRetryReadsSavedDetails` | `calendar-summary-retry` | Unavailable response shows an error, never an empty summary; explicit retry reads saved detail |
| `testMalformedReplyCannotDisplayASavedSummary` | `calendar-summary-malformed` | Invalid reply cannot become saved/empty-success content |
| `testAccountChangeRejectsDelayedSummary` | `calendar-summary-account` | Changed account removes delayed summary data |
| `testLargeTextKeepsExactDoseAndCompleteNotesReadable` | `calendar-summary-large` | Accessibility3 text retains full notes, exact dose and usable controls |
| `testAcknowledgedEditorNoteAppearsOnlyAfterReopeningSavedSummary` | `calendar-summary-edit` | One acknowledged legacy edit, then a fresh read shows the new canonical note while structured revision/lifecycle remain unchanged |
| `testSummaryEntryRemainsDefaultOff` | `calendar-summary-gated` | With calendar enable flag omitted, neither summary action nor detail request appears |

Then run `GaiaExporterUITests/MigraineCalendarUITests/testCalendarEditorCannotCloseDuringSave` as the **one existing editor compatibility journey**, for **10 UI journeys total**. UI tests supply their own fixture/scenario arguments; do not replace these with a real account or a general app smoke run. The retained test-timeout recipe uses model default/maximum 120/180 seconds and UI 180/240 seconds; execution supervision and fresh evidence paths must be selected in the later authorized handoff, not by copying stale commands blindly.

Retain each test bundle with source revision, local delta, configuration, destination/OS, start/end time, actual cases, failures and skips. Export the screenshots already attached by the tests and inspect normal text at the smaller phone size plus accessibility3: complete final note paragraph, exact `2.500000000000000001 mg`, missingness, canonical timing/timezone, error state, ordinary episode, account change and reopened saved note. Assertions alone do not replace visual inspection.

After a later authorized synthetic UI run, collect only the fixture's `tmp/g016-calendar-summary-*-capture.json` files from that run's app container, immediately with run/scenario identity. Capture writing is best-effort; a missing file is missing evidence. Do not copy app databases, tokens or personal history. Validate:

- All summary-only traffic is GET. Calendar list reads are expected; detail GET IDs must match the selected synthetic episode. First ID: `11111111-1111-4111-8111-111111111111`; second: `33333333-3333-4333-8333-333333333333`.
- Default-off has zero detail requests. Ordinary repeated reads preserve stored revision 0 and create no structured row.
- The acknowledged-note case contains exactly one intended POST to `/v1/symptoms/current/33333333-3333-4333-8333-333333333333/updates`; reopened detail contains the new note with stored revision 2 and unchanged structured lifecycle.
- Captures omit headers and contain only the synthetic request bodies and saved snapshots produced by the fixture.

## Fresh Release and later device boundaries

After focused runtime verification, a separately authorized **fresh unsigned arm64 Release simulator build of the reviewed G016 source** still must pass. Preserve its build-success log, executable and SHA-256, then verify all **15 fixture markers** from the pinned [marker inventory](/Users/gennwu/Documents/Codex/2026-09-05/we/outputs/g016-saved-episode-summary/build-evidence-reconciliation-20260915/remaining-test-inventory.json) are absent from symbols and strings. The existing `verify-release.py` hardcodes the now-absent temporary binary path and `release-final.log`; it is a preserved recipe, not a ready command for an arbitrary new output path. Do not run it against G014's older binary or silently reuse old logs. No checker/runner was changed in this reconciliation.

This Release check does not install or launch a signed app. Authenticated summary-after-edit, Siri phrase/routing, reminders/medicine/calendar behavior against approved deployed capability, account/HealthKit/subscription/push regression, accessibility, signing, TestFlight and physical-device acceptance remain in the preserved [device/release matrix](/Users/gennwu/Documents/Codex/2026-09-05/we/outputs/g016-saved-episode-summary/DEVICE_RELEASE_ACCEPTANCE.md), with its saved-summary build-blocker sentence superseded by this handoff. The summary is one saved episode; aggregate reports, PDF/CSV/share/export and imports are not complete.

## H13/H14 and authority

H13 is completed: one owner-run adapter invocation, verified Terminal ancestry, protective refusal and zero build launches. H14's Xcode-closed/all-guard-names-absent requirement belongs only to its particular prepared Terminal diagnostic. Its last preserved process observation is **September 15 06:50 UTC**, not a fresh status check. An ordinary Xcode preview/test is not contingent on satisfying that separate diagnostic. No causal explanation for the earlier CLI stall is proved by the newer builds.

All original diagnostic packets, guards and consumed paths are preserved. Their frozen source manifest also pins four recovery docs corrected in this pass; those doc hashes now differ while all 18 accepted code/guide hashes still match. Do not repin or run an old wrapper blindly. If the coordinator later chooses that diagnostic, its exact input state and prerequisite need separate reconciliation; this is not required to describe the ordinary Xcode test route above.

No build/test/native probe, Terminal control or substitute parent, app/process action, new runner, network/DB read, backend flag/deployment, or private-history access is authorized by this pass. Native execution remains a later coordinator-selected step because app compilation does not execute these tests or produce their screenshots/captures. The coordinator owns whether/how to request a narrowly scoped owner action; no repeat H13 or broad Xcode closure is requested here.

Android structured parity remains unfinished. September 15 writer and reel TTS `credit_balance_exhausted` is preserved context only; `LOCAL_AI_SOCIAL_WRITER_PROPOSAL.md` remains proposed. No social-writer implementation, pipeline edit, acquisition-strategy change, or new feature assignment is implied.
