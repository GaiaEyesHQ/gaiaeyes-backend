# Space Weather Detail + Stats Cards (iOS parity guidance)

This note captures the requested iOS changes so Codex can extend the space-weather experience without disrupting the current home dashboard. It assumes the backend exposes `/v1/space/visuals` and related feature payloads already documented elsewhere in this repo.

## Safety and backup expectations
- Before modifying any Swift/React Native files, create a backup commit or branch in the `gaiaeyes-ios` repo (e.g., `git switch -c feature/space-weather-detail-backup`) so the current dashboard can be restored quickly.
- When touching view files (`ContentView.swift`, `SpaceWeatherCard.swift`, new detail views), duplicate the originals into `*.bak` files only if Git history/branching is unavailable; avoid shipping `.bak` artifacts in the final PR.
- Keep existing Health/Sleep cards, Earthscope, Symptoms/Weekly Trends flows untouched—new work should be additive and hidden behind navigation from the current Space Weather card.

## UX layout goals
- Home dashboard: retain the existing `SpaceWeatherCard` footprint but append compact stats rows that link to detail screens instead of displaying full imagery. Suggested stats:
  - **Aurora**: KP index, hemispheric power, probability badge; tap leads to a Space Weather Detail view.
  - **Solar/Space visuals**: count of available overlays (NASA, Cumiana), most recent timestamp; tap leads to the detail gallery with toggleable overlays.
  - **Earthquakes**: summary count/magnitude for the day; tap leads to the existing Earthscope detail if available.
- Detail page: a dedicated Space Weather detail screen accessible from the card. Use the same navigation pattern as existing forecast sheets (e.g., `NavigationLink` from `SpaceWeatherCard`). Within the detail view:
  - Display the imagery gallery/overlays powered by `/v1/space/visuals`, grouped by source (NASA, Cumiana) with toggles for overlays/series.
  - Keep performance lean: reuse cached payloads bound to `@AppStorage` keys to avoid refetching on every open.
  - Provide quick navigation chips for Aurora, Solar Visuals, and Earthquakes sections; this keeps the UI scannable and offloads heavy charts from the home screen.

## Data + model wiring
- Reuse the existing feature/series fetchers in `ContentView` and any helper types already used by `SpaceWeatherCard` so the detail screen consumes cached data instead of duplicating network calls.
- Ensure `/v1/space/visuals` parsing is gated by feature flags so missing fields do not break the home card; map overlay availability into lightweight stats for the dashboard row.
- Cache parsed payloads for offline viewing; mirror the patterns described in `Frontend_Overview.md` (AppState + @AppStorage) for consistency with the rest of the app.

## Navigation and performance safeguards
- Add a single navigation entry point from the existing Space Weather card (e.g., `NavigationLink` or sheet) to the new detail view; do not auto-push or expand on the home screen.
- Keep detail charts/images lazy-loaded and optionally paged to prevent UI hitches on older devices.
- Make sure background refresh timers remain unchanged; the new detail view should listen to the same refresh notifications instead of starting its own timers.

## Attribution and content scope
- Include source credit strings (NASA, SWPC, VLF.it) in the detail view captions but keep them collapsed on the home card to avoid clutter.
- Until Tomsk ingestion is re-enabled, hide `tomsk_*` entries and focus on NASA + Cumiana overlays.

## Acceptance checklist for Codex
- [ ] Create a backup branch or commit before edits; no `.bak` files in the final diff unless requested.
- [ ] Home dashboard remains light: only stat rows added to Space Weather card; no full imagery on the home screen.
- [ ] New Space Weather detail screen shows overlay gallery + aurora stats and mirrors web layout, using cached data paths.
- [ ] Earthquake and aurora stat tiles link to their respective detail sections, preserving existing Health/Sleep/Earthscope/Symptom flows.
- [ ] Lint/tests for iOS project pass (e.g., `fastlane tests` or current suite) after integration.
