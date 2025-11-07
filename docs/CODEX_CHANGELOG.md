# Codex Change Log

Document noteworthy backend/front-end changes implemented via Codex tasks. Keep the newest entries at the top.

## 2024-04-13 — Clamp feature enrichment timeouts

- Wrapped the feature mart lookups and enrichment queries in short asyncio timeouts so
  `/v1/features/today` fails over to cached data instead of stalling clients when the
  database hangs. Diagnostics now record the timed-out components so engineers can see
  which feeds were skipped.
- Reused the freshened context for enrichment to avoid redundant queries and added
  guardrails that fall back to cached or snapshot payloads after timeout events.
- Documented the new `enrichment_errors` diagnostics field for mobile teams reviewing
  `/v1/features/today` responses.
- Ensured the database pool no longer infers pgBouncer mode purely from the port so
  explicit `pgbouncer` flags remain the only trigger for that backend selection.

## 2024-04-12 — Stop fabricating direct DB fallbacks

- Roll back the inferred port-5432 fallback: when pgBouncer is unreachable we now only
  switch to a direct connection if `DIRECT_URL` (or an explicit alternate DSN) is
  configured. This avoids hanging connection attempts to hosts that do not expose the
  primary Postgres port.
- Explicitly require `DIRECT_URL` to be set before wiring any fallback so pgBouncer
  connection strings without explicit ports no longer trigger a fabricated direct DSN.
- Added regression coverage ensuring pgBouncer mode skips the fallback when `DIRECT_URL`
  is missing, while still honoring an explicit direct connection when provided.

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
