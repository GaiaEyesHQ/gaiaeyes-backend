# `/v1/diag/features`

The `/v1/diag/features` endpoint exposes high-level diagnostics for the "features today" rollup. It is authenticated with the standard bearer token and never returns raw sample data.

## Request

```bash
curl -s -H "Authorization: Bearer <token>" \
  "https://<host>/v1/diag/features"
```

The response includes:

- `features`: metadata about the most recent `/v1/features/today` query, including the requested user id, which branch (scoped vs. fallback) was used, and the latest `day`/`updated_at` timestamps.
  - `cache_fallback` and `pool_timeout` highlight when the handler served cached data because the database pool was saturated.
  - `cache_hit` reports whether the cached snapshot was served immediately, while `cache_age_seconds` shows how old it was when returned.
  - `cache_rehydrated` is `true` when the mart returned an empty payload but cached data was available and reused for the response.
  - `cache_updated` flags when `/v1/features/today` wrote a new snapshot during the request and the
    `cache_snapshot_initial` / `cache_snapshot_final` blocks summarize which sections (health,
    sleep, space weather, Schumann, post copy) contained non-null values before and after the
    handler ran.
  - `payload_summary` provides the same snapshot for the payload returned to the caller so teams can
    quickly confirm whether the health, sleep, or space-weather cards were populated.
  - `trace` is a timestamped list of decision points (mart lookups, cache fallbacks, background
    refreshes, etc.) that doubles as a copyable debug log in the mobile app.
  - `error` reflects the error message when the endpoint itself returned `ok:false`.
  - `last_error` captures the most recent failure that triggered a fallback so clients can log the cause without treating cached data as an outage.
  - `enrichment_errors` lists non-fatal enrichment steps (sleep, space weather, posts) that
    timed out but left the payload otherwise usable.
  - `refresh_attempted`, `refresh_scheduled`, `refresh_reason`, and `refresh_forced` capture the background mart refresh cadence triggered by the request. Even when `day_used` reflects a cached snapshot, the refresh scheduler targets the current local day so stale cache entries don't stall new data creation.
- `tables`: row counts and latest timestamps for the tables that feed the feature rollup.
  - `marts.daily_features` shows the global feature mart freshness (`max_day` and `max_updated_at`).
  - `marts.schumann_daily` reports the latest Schumann resonance day available.
  - `ext.space_weather` reports the latest upstream solar weather timestamp.
  - When a user id is supplied, user-scoped tables are also included:
    - `gaia.daily_summary` (latest `date` recorded).
    - `gaia.samples_last_24h` (samples ingested for the user over the last 24 hours with earliest/latest timestamps).
- `sanity_checks`: quick max-value probes for the tables noted in the acceptance criteria. These align with the SQL snippets documented in the task description.

Example fragment:

```json
{
  "features": {
    "branch": "scoped",
    "requested_user_id": "...",
    "user_id": "...",
    "day": "2024-05-06",
    "updated_at": "2024-05-06T12:34:00Z",
    "max_day": "2024-05-06",
    "total_rows": 128,
    "has_row": true,
    "statement_timeout_ms": 60000,
    "cache_fallback": false,
    "pool_timeout": false,
    "error": null,
    "last_error": null
  },
  "tables": {
    "marts.daily_features": {
      "rows": 800,
      "max_day": "2024-05-06",
      "max_updated_at": "2024-05-06T12:45:00Z"
    },
    "gaia.samples_last_24h": {
      "rows": 3200,
      "earliest_start_time": "2024-05-05T13:00:00Z",
      "latest_start_time": "2024-05-06T12:58:00Z"
    }
  },
  "sanity_checks": {
    "marts.daily_features.max_day": "2024-05-06",
    "gaia.daily_summary.max_date": "2024-05-06",
    "gaia.samples.max_start_time": "2024-05-06T12:58:00Z"
  }
}
```

## Optional diagnostics from `/v1/features/today`

Append `?diag=1` to the existing `/v1/features/today` request to embed the same `features` diagnostic block alongside the data payload.

## Troubleshooting common diagnostics

- **`branch: "anonymous"` with `source: "empty"`** – The handler never resolved a user id for the request, so it short-circuited before
  it could touch the mart or the cache. The trace will include the line `anonymous request - skipping user scoped lookups`, which
  comes directly from the anonymous branch inside `_collect_features`.
  Confirm that the caller is presenting a valid Supabase JWT or, when using the developer bearer token, that an `X-Dev-UserId`
  header with a UUID value is attached. Without a scoped user id, `/v1/features/today` intentionally returns an empty payload and
  the cards in the app will stay frozen. 【F:app/routers/summary.py†L983-L1007】【F:app/utils/auth.py†L46-L72】
