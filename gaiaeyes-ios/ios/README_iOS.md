# iOS Starter (SwiftUI + HealthKit)

## Create the project
1) Open Xcode → **File > New > Project…** → iOS **App**
2) Product Name: `GaiaEyesExporter` · Interface: **SwiftUI** · Language: **Swift**
3) Select your Team (Apple Developer account) and a unique Bundle Identifier.

## Capabilities
- In the project target → **Signing & Capabilities** → `+ Capability` → add **HealthKit**.

## Info.plist keys
Add these keys with user-facing explanations:
- `NSHealthShareUsageDescription` = "This app reads your health data to export and analyze it."
- `NSHealthUpdateUsageDescription` = "This app may write health data (not used in v1)."

## Add the files
Replace the generated App/ContentView with the files in this folder:
- `GaiaEyesExporterApp.swift`
- `ContentView.swift`
- `APIClient.swift`
- `HealthKitManager.swift`

## Run
- Build & run on a **real device** (HealthKit requires a device).
- In the app:
  - Set **API Base** (e.g., `http://YOUR-MAC-LAN-IP:8000`)
  - **Dev Bearer**: `devtoken123` (or whatever your backend `.env` uses)
  - **User UUID**: your test user’s `gaia.users.id`
  - Tap **Use Developer Credentials** in the Connection Settings drawer to prefill the Render dev defaults and `X-Dev-UserId`
    before hitting Ping/Sync.
  - Tap **Ping API** → **Request Health Permissions** → **Sync Now**.

## Clean build checklist
- **Product → Clean Build Folder** in Xcode before rerunning if the UI refuses to compile.
- **File → Packages → Reset Package Caches** to clear stale SwiftPM artifacts.
- Build the **GaiaExporter** app scheme directly (no tests) to confirm fixes locally.
