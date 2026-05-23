# Gaia Eyes 1.0.1 Reliability Plan

Last updated: 2026-05-16

This plan tracks the first post-launch reliability pass. The goal is to reduce visible broken states before adding larger product features.

## Phase 1: Low-Risk User-Visible Fixes

- Suppress stale HealthKit disconnected notices when the app has newer on-device read evidence or displayed health data.
- Treat `sleep_total_minutes = 0` as missing sleep upload data, not as a true zero-sleep night, so it cannot trigger the Less Sleep driver.
- Hide raw upstream HTML errors from earthquake and other feed cards; show a short retry message instead.
- Refresh cached local allergen payloads when the cache only has a provider source but no actual pollen signal fields.

## Phase 2: Outlook And Local Signal Completeness

- Audit `/v1/users/me/outlook` payloads against `/v1/local/check` and `/v1/space/forecast/outlook` for the same user/day.
- Ensure the 7-day Outlook has a useful row for each available forecast day when local or space signals meet visible thresholds.
- Add diagnostics for missing Outlook rows: local row count, space row count, pollen row count, skipped-low-signal days, and pattern-match availability.
- Decide whether the Outlook page should include today, tomorrow-forward only, or both with separate sections. Current user expectation is that clear 7-day local/space signals should not disappear from Outlook.
- Verify pollen/allergen behavior for multiple ZIP codes, including ZIPs where Google Pollen returns type-specific data without an overall index.

## Phase 3: Server Stability

- Separate Render process liveness from dependency readiness: point Render health checks at `/health/live`, and keep `/health` for DB/Redis diagnostics.
- Correlate Render instance failures with `/health`, DB pool waiting, Redis ingest queue depth, worker drain state, and upstream endpoint timeouts.
- Add runbook thresholds for manual restart: repeated failed health checks, non-draining Redis queue, persistent pool waiting, or repeated `connect: connection refused`.
- Prefer graceful fallback/cached responses for non-critical feeds when upstream providers return 5xx or HTML error pages.
- Keep large write bursts behind the ingest queue and worker drain limits.

## Phase 4: First Feature Additions

- Add temperature extremes and temperature swing as first-class drivers where local forecast data supports it.
- Add a New indicator and optional glow treatment for newly observed patterns.
- Add share-copy rotation from Supabase so each share type can have multiple approved captions.
- Improve moon phase visuals for new/full moon tracking.
- Scope a migraine-focused tracking module separately from the reliability release.

## Launch Guardrails

- Do not mix large product-depth work into 1.0.1 unless it fixes a visible reliability bug.
- Preserve cached/stale data with a notice instead of blanking sections on transient failures.
- Do not show raw provider errors, HTML bodies, or stack traces in the app.
- Add tests for any backend signal scoring or cache fallback changes.
