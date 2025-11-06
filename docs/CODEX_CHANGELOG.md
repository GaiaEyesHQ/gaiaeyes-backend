# Codex Change Log

Document noteworthy backend/front-end changes implemented via Codex tasks. Keep the newest entries at the top.

## 2024-04-06 — Cache fallback envelope tweaks

- Updated `/v1/features/today` to always return a populated data block (with defaults when necessary) while surfacing outage causes via `diagnostics.error`, preventing the iOS dashboard from entering a refresh loop during database timeouts.
- Added regression coverage ensuring error paths fall back to the cached snapshot and remain `ok:true`.
- Refreshed the iOS follow-up notes to call out that `ok` stays true during cache usage so the app must read the diagnostics flags.

## 2024-04-05 — Features endpoint cache hardening

- Guarded `/v1/features/today` against pgBouncer pool exhaustion by attempting a manual connection acquisition and falling back to the last-good cache snapshot when the pool is saturated.
- Extended diagnostics with `cache_fallback`, `pool_timeout`, and `error` markers so client teams can detect when cached data was served.
- Added automated tests covering the new cache fallback branch and updated docs describing the behavior.
