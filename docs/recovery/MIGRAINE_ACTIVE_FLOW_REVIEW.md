# Migraine persistence and guided-flow review

Work is isolated on `codex/migraine-active-flow`, based on origin/main `4e8e8e4c913c5856e5112107437ffc5d62802549`. No production data, secret values, deployments, runtime flags, automatic migrations, releases, or unrelated temperature/Heart Awareness changes are included.

## Findings and corrections

- **Confirmed visibility defect, not evidence of deletion:** `fetch_current_symptom_items` used a 12-hour last-interaction filter, and the response deduplicated by symptom code. Older unresolved migraines disappeared from the current list, and another migraine ID could be hidden. Unresolved migraine IDs now survive both the window and item cap; older records remain reviewable without assigned end times.
- **Confirmed partial-save risk:** raw logging could acknowledge success after canonical episode creation failed, and the iOS decoder previously synthesized success from an unreadable response. Event/episode creation is now atomic and acknowledges the matching onset plus canonical ID. Retries use that same onset; simultaneous attempts are serialized.
- **Separate calendar cause:** the calendar uses canonical overlap queries, not the current-symptom 12-hour query. Its existing unsupported message maps to capability/storage unavailability (503). The source change adds foreground/save refresh and preserves error-vs-empty distinctions; it does not prove or alter the live flag. Calendar overlap and day boundaries remain half-open with device-local ranges converted to UTC.
- **Lifecycle integrity:** zero stays zero, ending is explicit, later edits do not rewrite end time, retries do not append duplicates, and an older newly delivered severity cannot overwrite a newer report.
- **Current versus highest severity:** the saved summary loads a dedicated owner-scoped full episode timeline. Its maximum is labelled highest recorded, separate from the last reported value. Missing timeline capability is shown explicitly.

## iOS review surfaces

Home provides Add details, Update severity, End migraine, summary, and calendar. Additional unresolved migraine IDs are available in a disclosure group. Initial guided logging covers explicit start, optional severity, symptoms/early signs, pain locations, medicines, other relief, context/notes, and an editable review. Close retains a draft; Save commits the completed portion so details can be continued later. Medicine time is explicit; optional dose and relief never receive inferred values. Favorites are explicitly pinned names. The same canonical episode appears in Home, saved summary, and calendar.

Calendar and legacy symptom entry/editing remain available. The new guide is reached from Home and the saved summary. The existing release-candidate capability configuration controls availability; ordinary release defaults are unchanged. Automatic reopen prompts and unknown-onset records are deferred.

## Independent review

A separate reviewer inspected save, lifecycle, account, and calendar paths using source and synthetic data. Four substantive findings were fixed: overlapping Symptoms refreshes, out-of-order first-arrival severity, whitespace-normalized note acknowledgements, and timezone-dependent regeneration of a pending detail request. The reviewer confirmed all four corrections and reported no remaining substantive blocker. Independent checks passed 31 backend tests; an actual-model Swift probe preserved detail arrays, exact decimals, timezone metadata, and retain/clear/set notes. Live configuration and simulator execution were outside that review.

## Verification

Backend checks passed: 72 focused API, contract, follow-up, calendar, and time-correction tests with the environment cleared and external socket connections blocked; 5 PostgreSQL persistence regressions in a disposable local database. These include old unresolved episodes beyond the display cap, separate migraine IDs, explicit zero, end-time preservation, full timelines, stale severity rejection, duplicate retry, atomic rollback, concurrent creation retry, account ownership, cross-midnight overlap, and a 25-hour DST day.

The PostgreSQL runner accepts an existing binary directory and creates its own private temporary cluster with TCP disabled, synthetic fixtures only, and automatic teardown. It never resets another task's cluster:

```sh
python scripts/run_migraine_active_postgres_tests.py /path/to/postgresql/bin
```

Focused backend test files: `tests/api/test_symptoms.py`, `tests/api/test_migraine_history.py`, `tests/services/test_migraine_follow_up.py`, `tests/services/test_migraine_episode_contract.py`, `tests/db/test_migraine.py`, `tests/services/test_migraine_time_correction.py`, and `tests/api/test_migraine_times.py`.

For iOS unit checks, use the `GaiaEyes` scheme with Debug and a disposable simulator/bundle. The app suppresses live service startup during XCTest. Run the four suites separately because the existing fixture transport uses shared static state: `MigraineGuideTests`, `MigraineEpisodeSummaryTests`, `MigraineHistoryTests`, and `MigraineFollowUpWorkflowTests`. The MigraineVerification configuration intentionally forces the app verification transport, so it is unsuitable for unit tests that inject the other fixture transport.

Representative commands from the repository root (replace the owned simulator UUID and result path):

```sh
xcodebuild -project gaiaeyes-ios/ios/GaiaExporter.xcodeproj \
  -scheme GaiaEyes -configuration Debug \
  -destination 'platform=iOS Simulator,id=<owned-simulator>' \
  -derivedDataPath /tmp/migraine-review-derived \
  -resultBundlePath /tmp/migraine-summary.xcresult \
  -parallel-testing-enabled NO \
  -only-testing:GaiaExporterTests/MigraineEpisodeSummaryTests \
  CODE_SIGNING_ALLOWED=NO PRODUCT_BUNDLE_IDENTIFIER=com.gaiaeyes.migraine.unit.synthetic test

xcodebuild -project gaiaeyes-ios/ios/GaiaExporter.xcodeproj \
  -scheme GaiaEyes-MigraineVerification -configuration MigraineVerification \
  -destination 'platform=iOS Simulator,id=<owned-simulator>' \
  -derivedDataPath /tmp/migraine-review-derived \
  -resultBundlePath /tmp/migraine-active-ui.xcresult \
  -parallel-testing-enabled NO \
  -only-testing:GaiaExporterUITests/MigraineAppIntegrationUITests/testMigraineHomeActionsDetailsSummaryEndAndCalendar \
  -only-testing:GaiaExporterUITests/MigraineAppIntegrationUITests/testMigraineNewDraftResumeAndPartialSaveLargeText \
  -only-testing:GaiaExporterUITests/MigraineAppIntegrationUITests/testMigraineUncertainCreationRetriesSameEpisode \
  -only-testing:GaiaExporterUITests/MigraineAppIntegrationUITests/testCalendarUnavailableViaTimeline \
  -only-testing:GaiaExporterUITests/MigraineAppIntegrationUITests/testAccountReplacementRejectsDelayedSaveAndAllowsExit \
  CODE_SIGNING_ALLOWED=NO test
```

UI checks use `GaiaEyes-MigraineVerification`, configuration `MigraineVerification`, code signing disabled, and parallel testing disabled. This configuration has a separate bundle identity and permits only synthetic fixture transport; it is not an accepted release build.

Swift unit results: 36 tests passed across the guide (7), saved summary (15), history (8), and follow-up workflow (6) suites. The guide suite passed in MigraineVerification; the three suites that inject their own transport passed in Debug with a separate synthetic bundle identifier. An initial attempt to run the summary suite in MigraineVerification was invalidated by its intentional transport override, then rerun successfully in Debug.

Five focused UI journeys passed (exit 0): active Home through severity zero/details/summary/explicit end/calendar, new draft resume and partial save at accessibility3, uncertain creation retry, calendar unavailable, and account replacement during delayed save. Screenshot review then corrected the date-picker label layout and added persistent medicine dose/unit/relief labels; the two affected guide journeys passed again (exit 0). Standard and accessibility screenshots were inspected as pixels.

Local evidence is under `/Users/gennwu/Documents/Codex/2026-10-13/task-2/`: `migraine-postgres.log`, `MigraineGuideTests-verified.xcresult`, the three `*-debug.xcresult` unit bundles, `migraine-ui-final.xcresult` (five journeys), and `migraine-ui-layout.xcresult` (two final layout rechecks). Human-readable synthetic screenshots and an index are in `migraine-review-screens/`; the corresponding raw attachment manifests/receipts are in `migraine-final-attachments/` and `migraine-layout-attachments/`. No personal screenshots or health records are included in the commit.

Manual review:

1. Launch `GaiaEyes-MigraineVerification` on a disposable simulator with its synthetic launch arguments; confirm the receipt contains only the `.invalid` fixture service.
2. Review an older active episode, save severity zero, add details, and confirm the same ID and prior peak in the summary.
3. Explicitly select an end time. Confirm removal from Home and retention in the calendar.
4. Close an unfinished new guide, resume it, and save only the selected fields. Reopen and inspect the saved summary.
5. Exercise an uncertain save and account replacement. Drafts must remain isolated, and stale responses must not become acknowledgements.
6. Review standard and accessibility-size screenshots, including buttons, labels, and optional/unanswered values.

Website parity: shared backend lifecycle/acknowledgement fixes apply to its existing API proxy; the native guided editor and Home UI are intentionally deferred on the website under the iOS-only approved scope.

## Changed paths

- `app/db/symptoms.py`
- `app/routers/symptoms.py`
- `docs/OPEN_QUESTIONS.md`
- `docs/contracts/MIGRAINE_EPISODE_CONTRACT.md`
- `docs/recovery/MIGRAINE_ACTIVE_FLOW_REVIEW.md`
- `gaiaeyes-ios/ios/GaiaExporter/Models/MigraineEpisodeModels.swift`
- `gaiaeyes-ios/ios/GaiaExporter/Models/MigraineEpisodeSummary.swift`
- `gaiaeyes-ios/ios/GaiaExporter/Models/MigraineGuideModels.swift`
- `gaiaeyes-ios/ios/GaiaExporter/Models/SymptomModels.swift`
- `gaiaeyes-ios/ios/GaiaExporter/Services/APIClient.swift`
- `gaiaeyes-ios/ios/GaiaExporter/Services/MigraineAppVerification.swift`
- `gaiaeyes-ios/ios/GaiaExporter/Services/MigraineFixtureSupport.swift`
- `gaiaeyes-ios/ios/GaiaExporter/Services/MigraineFollowUpWorkflow.swift`
- `gaiaeyes-ios/ios/GaiaExporter/Services/MigraineTimeFixture.swift`
- `gaiaeyes-ios/ios/GaiaExporter/ViewModels/AppState.swift`
- `gaiaeyes-ios/ios/GaiaExporter/ViewModels/MigraineEpisodeSummaryStore.swift`
- `gaiaeyes-ios/ios/GaiaExporter/ViewModels/MigraineGuideStore.swift`
- `gaiaeyes-ios/ios/GaiaExporter/Views/ContentView.swift`
- `gaiaeyes-ios/ios/GaiaExporter/Views/CurrentSymptomsView.swift`
- `gaiaeyes-ios/ios/GaiaExporter/Views/MigraineEpisodeSummaryView.swift`
- `gaiaeyes-ios/ios/GaiaExporter/Views/MigraineGuideView.swift`
- `gaiaeyes-ios/ios/GaiaExporter/Views/MigraineHistoryView.swift`
- `gaiaeyes-ios/ios/GaiaExporter/Views/MigraineHomeSection.swift`
- `gaiaeyes-ios/ios/GaiaExporterTests/MigraineEpisodeSummaryTests.swift`
- `gaiaeyes-ios/ios/GaiaExporterTests/MigraineGuideTests.swift`
- `gaiaeyes-ios/ios/GaiaExporterUITests/MigraineAppIntegrationUITests.swift`
- `scripts/run_migraine_active_postgres_tests.py`
- `services/migraine/episode_contract.py`
- `services/migraine/follow_up.py`
- `tests/api/test_migraine_history.py`
- `tests/api/test_symptoms.py`
- `tests/db/test_migraine_active.py`
- `tests/services/test_migraine_follow_up.py`
