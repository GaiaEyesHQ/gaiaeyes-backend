# Stats Cards Cache Fallback Notes

The backend now surfaces two new diagnostics on `/v1/features/today` to indicate when cached data was returned instead of a fresh mart snapshot:

- `diagnostics.cache_fallback` — `true` when the handler served the last good payload from Redis / in-memory cache.
- `diagnostics.pool_timeout` — `true` when the cache fallback was triggered because the database pool was saturated (pgBouncer timeout).
- `diagnostics.error` — populated with the last connection/query error so the UI can display an actionable banner.

To keep the iOS dashboard stable and avoid the refresh loop that was observed, please queue the following Codex task for the SwiftUI repo:

1. **Surface the new diagnostics.** Extend the feature envelope parsing in `ContentView.swift` so the `FeatureFetchState` tracks `cacheFallback`, `poolTimeout`, and `error` strings alongside the existing `source` metadata. The backend now keeps `ok:true` even when the cache path is used, so the UI must rely on these diagnostics to detect outages. Use the decoded flags to show the existing stale-data toast/badge path instead of hard-refreshing immediately. 【F:ios/GaiaExporter/Views/ContentView.swift†L839-L918】
2. **Throttle follow-up refreshes.** When `cacheFallback` is `true`, pause automatic retries for ~2 minutes before the next fetch attempt (reuse the existing `featuresRetryWorkItem` guard). Only resume aggressive retries once diagnostics show `cacheFallback == false`. This prevents the UI from hammering the backend while the database pool recovers. 【F:ios/GaiaExporter/Views/ContentView.swift†L981-L1053】
3. **Display a user-facing banner.** Reuse the offline/stale badge styling to display a short message such as “Showing cached data while the network recovers” when `cacheFallback` is `true`. Include the diagnostics `error` text in the debug panel so testers can confirm the backend reason, since the top-level `error` field will remain `null` during these fallbacks. 【F:ios/GaiaExporter/Views/ContentView.swift†L972-L974】【F:ios/GaiaExporter/Views/ContentView.swift†L1731-L1751】
4. **Protect the pull-to-refresh gesture.** Update the pull-to-refresh handler to respect the new cooldown when `cacheFallback` is active so manual refreshes still work but do not queue multiple simultaneous fetches. 【F:ios/GaiaExporter/Views/ContentView.swift†L1015-L1094】

These tweaks ensure the dashboard keeps showing the last-good stats during short outages instead of repeatedly refreshing and freezing the UI.
