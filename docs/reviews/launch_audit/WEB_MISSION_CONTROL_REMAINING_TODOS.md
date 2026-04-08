# Web Mission Control Remaining Todos

This file tracks the website-specific work that remains after the current Mission Control stabilization pass.

## High priority

- Replace the remaining EarthScope-style Guide snapshot with a cleaner canonical Guide payload and writer.
- Add Guide unseen/glow state to the website once the backend guide-state model exists.
- Finish the Schumann public-page speed pass:
  - cache-first payload
  - stale-while-revalidate behavior
  - non-blocking background refresh / cron refresh
  - lazy-load heatmap and heavier below-the-fold visuals
- Replace the current dashboard EarthScope section on the public/member website with the same compact Current Outlook model used in the app/web member hub.
- Add clearer degraded-state UI on web surfaces when backend DB health is false.

## Settings / personalization

- Add timezone controls to web Settings and wire them to the existing backend preference model.
- Add favorite symptom preferences so the web picker can surface user-priority symptoms first.
- Add notification / follow-up preferences to web Settings.

## Body / symptom workflow

- Add optimistic UI for active symptom feedback actions on the website.
- Add a small saved / retry state on each symptom action.
- Expand the symptom catalog with the first GI symptom set once backend/app parity is ready.
- Add favorite symptom shortcuts before any freeform custom symptom system.

## Outlook / drivers / copy

- Continue trimming repetitive wording across Mission Control, Body, Outlook, and Guide.
- Promote specific pollen types in Outlook/drivers when source data supports it.
- Surface humidity more clearly in local/outlook website views.
- Update energy labels across the website once the backend/app energy-label change ships.

## Later

- Lightweight Guide walkthrough / explainer flow.
- Supportive recommendation visuals and tone enhancements in Guide.
- Profile-aware pacing suggestions once the unified support/recommendation catalog exists.
