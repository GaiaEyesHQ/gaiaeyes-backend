# Android polish and iOS parity repair brief

September 6, 2026 · Owner feedback and source review · Implementation pending

## Current direction

Jennifer reports that Android feels weaker than the Apple version: Explore is jumbled and partial, weather appears to belong to Settings, wording needs work, and the app feels sluggish. **Android product quality and parity come before continuing store/release preparation.** The Google Play account and app record are complete per Jennifer; they do not establish product readiness. Acquisition preparation and independent iOS/product work can continue.

This direction comes from Jennifer's current feedback. The repair sequence below is an assistant recommendation, not a claim that every proposed design or technical change has been accepted or implemented. No deadline, broad rewrite, new feature expansion or publication is committed here.

## What the source establishes

| Area | Inspected evidence | Implication |
|---|---|---|
| Explore structure | Android combines a summary, five signal cards, weather, a full driver grid and backend status in [ExploreScreen](/Users/gennwu/Documents/GitHub/gaiaeyes-backend/gaiaeyes-android/app/src/main/java/com/gaiaeyes/app/ui/GaiaEyesApp.kt:2999). The [iOS hub](/Users/gennwu/Documents/GitHub/gaiaeyes-backend/gaiaeyes-ios/ios/GaiaExporter/Views/ContentView.swift:15120) uses compact destinations with All Drivers separate. | Presence of all categories does not establish navigation or visual parity. |
| Partial sections | [Android card construction](/Users/gennwu/Documents/GitHub/gaiaeyes-backend/gaiaeyes-android/app/src/main/java/com/gaiaeyes/app/ui/GaiaEyesApp.kt:3411) omits categories whose payloads are absent. Space Weather derives its summary from the magnetosphere payload. | Missing data can remove destinations; compare detail content as well as card titles with iOS. |
| Weather and location | Weather is already linked from Explore, below the signal stack. Settings calls its location preferences “Local conditions.” | Surface weather clearly and distinguish it from location controls. Jennifer's installed build may differ from this checkout; her experience is not disproved by source presence. |
| Loading | [ExploreRepository](/Users/gennwu/Documents/GitHub/gaiaeyes-backend/gaiaeyes-android/app/src/main/java/com/gaiaeyes/app/data/ExploreRepository.kt:21) starts four requests concurrently but returns one result after all finish. Cached fallback is stamped with a new composite save time; `ok=false` does not enter the exception-only unavailable list. | Investigate slow-source coupling and honest per-source freshness. This is a source-level finding, not a measured explanation of phone sluggishness. |
| Rendering | Explore uses a scrolling non-lazy Column; the iOS reference uses LazyVStack. | Profile composition and scrolling before deciding whether rendering changes are needed. These implementations alone do not prove a performance defect. |

## First repair sequence

1. **Explore and weather.** Use the existing iOS hub as the reference: All Drivers → Space Weather → Local Conditions → Magnetosphere → Schumann Resonance; Earthquakes and Hazards under More to Explore. Make All Drivers a separate destination. Use consistent card density and clear back navigation. Keep each destination visible with loading, unavailable or saved-data states. Keep service diagnostics in Settings; show actionable data problems next to affected content. Label location controls “Location preferences,” and link to them from weather when setup is needed.
2. **Detail completeness and wording.** Compare each Android destination with the current iOS build for useful information, hierarchy, units, explanations and freshness. Record every gap as missing implementation, unavailable data, intentional platform difference or open product choice. Shorten duplicated introductions and vague technical labels. Preserve useful health capability and contextual uncertainty; do not introduce repetitive generic disclaimers.
3. **Responsiveness.** Capture cold/warm launch, cached tab entry, scrolling, refresh and slow/offline cases on the same device before and after fixes. Separate time to first usable content from time to all fresh data. Inspect per-request timing, main-thread/frame behavior and repeated refresh cancellation. Then implement the smallest measured fix; evaluate progressive per-card updates and source-specific status for the observed repository behavior. Do not simply increase timeouts or mark reused data fresh.
4. **Whole-app acceptance.** Walk Home, Body, Patterns, Outlook, Explore, Guide, Settings, onboarding and return-from-background. Check large text, back navigation, loading/error/empty states, location off/ZIP/device modes and account changes. Preserve billing, notifications, signing and store declarations as separately tracked release work.

## Completion evidence

- Comparable Android/iOS screen captures and a short gap register with explicit dispositions; matching titles alone is insufficient.
- Weather easy to find from Explore; location preferences clearly describe configuration.
- Full, partial, missing and cached data retain a coherent layout and honest timestamps/status.
- Recorded before/after device timings and frame behavior for reported sluggishness; appropriate Android build, lint and focused behavior tests pass after implementation.
- Jennifer reviews the repaired build's coherence and responsiveness before Android product acceptance is closed.

**Verified here:** static Android/iOS source comparison and existing documentation. ADB listed no connected devices during this pass. The installed Android/iOS versions, screen appearance and device timings remain unverified. No application code, installed build, backend or console configuration was changed. No answer from Jennifer is required for this repair brief; device/build identification is needed when runtime reproduction begins.
