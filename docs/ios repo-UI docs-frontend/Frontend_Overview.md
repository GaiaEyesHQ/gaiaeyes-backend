# Gaia Eyes iOS Frontend Technical Documentation

## Application entry point
- `GaiaExporterApp` is the SwiftUI entry that instantiates a shared `AppState`, registers background refresh/processing tasks, and injects the state into the main window scene hosting `ContentView`. 【F:ios/GaiaExporter/GaiaExporterApp.swift†L1-L22】

## Core state and data orchestration
- `ContentView` keeps its own `@StateObject` `AppState` plus cached JSON snapshots for features, time-series, and symptom code definitions using `@AppStorage`. It also tracks presentation flags, fetch throttling guards, and cached feature/symptom payloads to drive the UI. 【F:ios/GaiaExporter/Views/ContentView.swift†L55-L101】
- `AppState` centralizes backend configuration (base URL, bearer, user ID), log aggregation, BLE/Polar connectivity, and HealthKit integration. It persists configuration to `UserDefaults`, refreshes status periodically, registers background observers, and hydrates cached symptom queues at launch. 【F:ios/GaiaExporter/ViewModels/AppState.swift†L35-L146】
- Symptom events are queued through `AppState.enqueueSymptom` and flushed via `flushQueuedSymptoms`, which retries failed uploads, applies fallback symptom codes, and updates the published queue count that the UI surfaces. 【F:ios/GaiaExporter/ViewModels/AppState.swift†L168-L200】

## Fetching, caching, and refresh lifecycle
- The main `NavigationStack` body loads feature, forecast, space-series, and symptom payloads in parallel on first render via `.task`, and the same pipelines are re-run from the pull-to-refresh gesture. `ContentView` hydrates cached feature/series snapshots on appear, keeps them in sync with `@AppStorage` updates, and listens for custom refresh notifications to throttle upload-triggered refreshes. 【F:ios/GaiaExporter/Views/ContentView.swift†L816-L1094】【F:ios/GaiaExporter/Views/ContentView.swift†L981-L1053】
- Toasts, offline banners, and cached-state fallbacks expose fetch state to the user; the view tracks the most recent envelope metadata to indicate when data is stale or sourced from snapshots. 【F:ios/GaiaExporter/Views/ContentView.swift†L839-L918】

## Top-level dashboard composition
- The scrollable stack first renders the `SleepCard`, summarizing nightly duration, stage breakdown, and efficiency. 【F:ios/GaiaExporter/Views/ContentView.swift†L821-L837】【F:ios/GaiaExporter/Views/SleepCard.swift†L11-L76】
- A `HealthStatsCard` surfaces daily steps, heart-rate bounds, HRV average, SpO₂, and blood pressure, overlaying timestamps when rollups were updated. 【F:ios/GaiaExporter/Views/ContentView.swift†L857-L876】【F:ios/GaiaExporter/Views/ContentView.swift†L1616-L1640】
- `SymptomsTileView` combines a “log symptom” call-to-action, today/queued counts, and an optional sparkline; it triggers the logging sheet and reflects offline queues. 【F:ios/GaiaExporter/Views/ContentView.swift†L878-L885】【F:ios/GaiaExporter/Views/ContentView.swift†L1252-L1305】
- Space weather insights are rendered through `SpaceWeatherCard`, optional `SpaceAlertsCard`, and an Earthscope journal entry, each bound to the latest feature payload. 【F:ios/GaiaExporter/Views/ContentView.swift†L894-L937】【F:ios/GaiaExporter/Views/ContentView.swift†L1648-L1709】
- The dashboard optionally appends a geomagnetic forecast summary (`ForecastCard` + sheet) and multiseries charts overlaying Kp, Bz, Schumann resonance, and HR telemetry with symptom highlights. 【F:ios/GaiaExporter/Views/ContentView.swift†L929-L934】【F:ios/GaiaExporter/Views/ContentView.swift†L1772-L1802】【F:ios/GaiaExporter/Views/ContentView.swift†L1840-L1904】

## Symptom logging workflow
- Activating the log button presents `SymptomsLogSheet`, a `NavigationStack` sheet that surfaces queued counts/offline state, preset symptom buttons, optional severity slider, notes field, and toolbar actions. Submission emits a `SymptomQueuedEvent` that `ContentView` uploads asynchronously while disabling dismissal. 【F:ios/GaiaExporter/Views/ContentView.swift†L1079-L1094】【F:ios/GaiaExporter/Views/ContentView.swift†L1320-L1444】
- Success and error states bubble back through `symptomToastMessage` overlays and the queued-count badge, while `AppState` manages persistence of custom presets restored from cached code definitions. 【F:ios/GaiaExporter/Views/ContentView.swift†L878-L906】【F:ios/GaiaExporter/Views/ContentView.swift†L1320-L1361】【F:ios/GaiaExporter/Views/ContentView.swift†L132-L147】【F:ios/GaiaExporter/ViewModels/AppState.swift†L168-L200】

## Tools, settings, and diagnostics
- A nested “Tools & Settings” disclosure hosts configurable backend connection fields, HealthKit sync shortcuts, BLE status, and Polar ECG summaries, all bound to `AppState` so edits persist instantly. 【F:ios/GaiaExporter/Views/ContentView.swift†L938-L973】【F:ios/GaiaExporter/Views/ContentView.swift†L1454-L1611】【F:ios/GaiaExporter/ViewModels/AppState.swift†L35-L102】
- `BleStatusSection` links to the dedicated `BleSettingsView`, where users can scan/connect peripherals, toggle automated uploads, and control Polar streaming sessions. 【F:ios/GaiaExporter/Views/ContentView.swift†L1570-L1605】【F:ios/GaiaExporter/Views/BleSettingsView.swift†L5-L99】
- The optional `DebugPanel` exposes an expandable live log sourced from `AppState.log`, mirroring backend sync events and queued uploads for troubleshooting. 【F:ios/GaiaExporter/Views/ContentView.swift†L972-L974】【F:ios/GaiaExporter/Views/ContentView.swift†L1731-L1751】【F:ios/GaiaExporter/ViewModels/AppState.swift†L56-L154】

## Background sync touchpoints
- Toolbar actions trigger HealthKit permissions and manual exports through `AppState` methods (e.g., `syncSteps7d`, `syncSleep7d`), while `ContentView` listens for `.featuresShouldRefresh` notifications fired by background uploaders to rehydrate the dashboard. 【F:ios/GaiaExporter/Views/ContentView.swift†L938-L1053】【F:ios/GaiaExporter/Views/ContentView.swift†L1491-L1533】【F:ios/GaiaExporter/ViewModels/AppState.swift†L168-L200】
- Background task registration in `GaiaExporterApp` ensures periodic syncs continue even when the UI is inactive, with lifecycle hooks (`scenePhase`, `.onDisappear`) cancelling pending refresh tasks to avoid runaway updates. 【F:ios/GaiaExporter/GaiaExporterApp.swift†L8-L22】【F:ios/GaiaExporter/Views/ContentView.swift†L1015-L1094】

## Extending the dashboard
- New cards should follow the existing pattern: bind to cached feature or series models, wrap layout inside `GroupBox`/`DisclosureGroup` for consistent styling, and update cached JSON keys to keep offline restores functional via the shared `@AppStorage` bindings. 【F:ios/GaiaExporter/Views/ContentView.swift†L821-L937】【F:ios/GaiaExporter/Views/ContentView.swift†L1007-L1023】
- Additional backend controls can be slotted into the Tools disclosure by extending `ActionsSection` or adding sibling sections observing `AppState`, ensuring persistence through `UserDefaults` and the background sync timers already in place. 【F:ios/GaiaExporter/Views/ContentView.swift†L938-L973】【F:ios/GaiaExporter/Views/ContentView.swift†L1454-L1536】【F:ios/GaiaExporter/ViewModels/AppState.swift†L35-L146】
