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

`Guide` now opens a dedicated Guide Hub instead of the earlier lightweight orientation sheet.
Its toolbar entry is icon-only and uses the shared guide avatar system, with the cat-first top-left state mapped to `cat_avatar_icon` for compact presentation.

Guide Hub is the centralized home for:

- Daily Check-In
- Daily Poll / lightweight feedback
- EarthScope / What Matters Now entry
- Understanding Gaia Eyes
- future guide-driven follow-ups and helper moments

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

The Home surface no longer duplicates those destinations with a separate quick-links row. Cross-section movement should happen through the shared bottom navigation model.

`All Drivers` now adds a matching bottom navigation strip inside its sheet so users can jump directly to `Home`, `Body`, `Patterns`, `Outlook`, or `Explore` without closing back through the modal flow first.

## Debug / developer controls

The old top-right debug toggle is no longer exposed as a primary app-shell action.

The in-app debug panel/log toggle now lives under:

- `Settings` -> `Advanced` -> `Developer Controls` -> `Show in-app debug panel`

This preserves the existing developer workflow without making debug affordances the reviewer-facing top-right control.

## Reviewer checks

- Confirm the 5 tabs remain visible when moving between the main app sections.
- Confirm the top-left guide entry is icon-only and opens Guide Hub.
- Confirm Guide Hub shows Daily Check-In, Daily Poll, EarthScope, and Understanding Gaia Eyes sections.
- Confirm `Settings` opens from the top-right.
- Confirm the Guide section in Settings shows the shared avatar preview and the reserved app-icon preference path.
- Confirm the Home tab no longer shows the old quick-links row.
- Confirm the `All Drivers` sheet shows the bottom tab shortcuts and each one returns to the matching main tab.
- Confirm the debug panel can still be enabled from `Settings` -> `Advanced`.
- Confirm existing sheets and detail routes still open for symptom logging, current symptoms, daily check-in, all drivers, local conditions, Schumann, and settings.
