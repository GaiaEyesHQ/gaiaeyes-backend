# Codex Change Log

Document noteworthy backend/front-end changes implemented via Codex tasks. Keep the newest entries at the top.

## 2024-04-12 — Restore automatic direct DB fallback

- Detect pgBouncer usage when the Supabase connection string already points to port 6543
  and automatically derive a direct Postgres fallback on port 5432 when no explicit
  `DIRECT_URL` is configured. This prevents connection loops that left the `/v1/features/today`
  endpoint stuck on cached payloads while pgBouncer was unavailable.
- Added regression coverage asserting the inferred fallback wiring.

## 2024-04-11 — Harden database connectivity and symptom fallbacks

- Update the async pool bootstrapper to respect the original `DATABASE_URL` port, only switch to pgBouncer when explicitly
  requested, and automatically fall back to a direct connection when the pgBouncer endpoint is unreachable. Diagnostics now
  expose the active backend and whether a fallback is available so the mobile client can make informed refresh decisions.
- Keep optional direct connection strings sanitized and reusable, ensuring refresh tasks and cache warmers share a single,
  self-healing pool configuration without fighting the front end.
- Fix the symptom tracker endpoints to capture the raised exception objects so error envelopes remain populated instead of
  crashing with `NameError`, restoring friendly errors in the iOS debug console.

## 2024-04-10 — Restore raw symptom errors with friendly fallbacks

- Bring back the database-provided error strings in the `error` field so existing
  clients stop looping during backend outages.
- Add a `friendly_error` companion field that carries the documented message for
  analytics/localization while keeping the envelope stable.
- Updated the Symptoms API docs and regression tests to cover the dual-error
  contract. No front-end work is required.

## 2024-04-09 — Stabilize symptom error envelopes

- Replace raw database exception messages across the symptom API with documented, user-facing strings so the mobile client receives consistent fallback payloads.
- Expand the symptom normalization regression tests to assert the safe errors for both read and write failures.
- No front-end updates required because the iOS app already expects the documented strings in `/docs/symptoms_api.md`.

## 2024-04-08 — Persist fallback errors without tripping the UI

- Added `diagnostics.last_error` and now clear `diagnostics.error` whenever cached/yesterday data is served successfully so existing clients stop treating fallbacks as hard failures.
- Updated the `/v1/features/today` docs and iOS follow-up checklist to consume the new field while keeping banners/debug copy informative.
- Extended the regression suite to lock in the adjusted diagnostics contract.

## 2024-04-07 — Cache fallback diagnostics

- Flag mart query failures as cache fallbacks so mobile clients throttle refreshes while still showing cached tiles.
- Ensure the diagnostics payload carries the triggering error (and pool timeout flag when relevant) when cached data is returned.
- Document the updated behavior for the iOS Codex assignee.

## 2024-04-06 — Cache fallback envelope tweaks

- Updated `/v1/features/today` to always return a populated data block (with defaults when necessary) while surfacing outage causes via `diagnostics.error`, preventing the iOS dashboard from entering a refresh loop during database timeouts.
- Added regression coverage ensuring error paths fall back to the cached snapshot and remain `ok:true`.
- Refreshed the iOS follow-up notes to call out that `ok` stays true during cache usage so the app must read the diagnostics flags.

## 2024-04-05 — Features endpoint cache hardening

- Guarded `/v1/features/today` against pgBouncer pool exhaustion by attempting a manual connection acquisition and falling back to the last-good cache snapshot when the pool is saturated.
- Extended diagnostics with `cache_fallback`, `pool_timeout`, and `error` markers so client teams can detect when cached data was served.
- Added automated tests covering the new cache fallback branch and updated docs describing the behavior.
