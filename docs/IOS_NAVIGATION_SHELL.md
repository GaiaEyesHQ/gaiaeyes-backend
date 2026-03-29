# iOS Navigation Shell

## Current shell

Gaia Eyes now uses a persistent 5-tab bottom navigation model in the iOS app:

- Home
- Body
- Patterns
- Outlook
- Explore

The shell is implemented in `gaiaeyes-ios/ios/GaiaExporter/Views/ContentView.swift` and keeps the top signal strip visible across the main tab roots.

## Global entry points

- Top-left: `Guide`
- Top-right: `Settings`

`Guide` is a lightweight orientation sheet that routes first-time users into the correct primary tab.

`Settings` is now the canonical place for:

- experience/profile preferences
- notifications
- health and location preferences
- account/membership
- advanced and developer controls

## Primary tab ownership

Each major concept has one primary home:

- `Home`: Mission Control, What Matters Now, EarthScope summary, signal strip context
- `Body`: symptom logging, current symptoms, daily check-in, sleep, health stats, recent body context
- `Patterns`: strongest patterns, emerging patterns, body-signal patterns
- `Outlook`: 24h / 72h / 7d forecast guidance and “what may help”
- `Explore`: deeper system context including all drivers, space weather, local conditions, magnetosphere, Schumann, hazards, and earthquakes

## Debug / developer controls

The old top-right debug toggle is no longer exposed as a primary app-shell action.

The in-app debug panel/log toggle now lives under:

- `Settings` -> `Advanced` -> `Developer Controls` -> `Show in-app debug panel`

This preserves the existing developer workflow without making debug affordances the reviewer-facing top-right control.

## Reviewer checks

- Confirm the 5 tabs remain visible when moving between the main app sections.
- Confirm `Guide` opens from the top-left and can route into each tab.
- Confirm `Settings` opens from the top-right.
- Confirm the debug panel can still be enabled from `Settings` -> `Advanced`.
- Confirm existing sheets and detail routes still open for symptom logging, current symptoms, daily check-in, all drivers, local conditions, Schumann, and settings.
