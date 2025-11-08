# /v1/features/today

The `/v1/features/today` endpoint returns a consolidated “daily features” snapshot for the authenticated user. The handler performs several safety checks to ensure mobile clients always receive a stable envelope, even when the mart has gaps.

## Query parameters

| Name | Type | Default | Description |
| ---- | ---- | ------- | ----------- |
| `tz` | string | `America/Chicago` | IANA timezone used to resolve “today”. The server computes `(now() at time zone :tz)::date` and uses that local day for all lookups and diagnostics. |

## Response envelope

```
{
  "ok": true|false,
  "data": { ... } | null,
  "error": string|null,
  "diagnostics": {
    "branch": "scoped" | "anonymous",
    "day": "YYYY-MM-DD" | null,
    "day_used": "YYYY-MM-DD" | null,
    "source": "today" | "freshened" | "yesterday" | "empty" | "cache",
    "mart_row": true|false,
    "freshened": true|false,
    "statement_timeout_ms": int,
    "requested_user_id": uuid|null,
    "user_id": uuid|null,
    "updated_at": ISO8601|null,
    "max_day": "YYYY-MM-DD" | null,
    "total_rows": int|null,
    "tz": string,
    "cache_fallback": true|false,
    "cacheFallback": true|false,   // camelCase alias for mobile clients
    "cache_hit": true|false,
    "cache_age_seconds": float|null,
    "cache_rehydrated": true|false,
    "cache_updated": true|false,
    "cache_snapshot_initial": { ... },
    "cache_snapshot_final": { ... },
    "payload_summary": { ... },
    "trace": ["2025-11-09T04:12:00Z fetched mart row", ...],
    "pool_timeout": true|false,
    "error": string|null,
    "last_error": string|null,
    "enrichment_errors": [string, ...],
    "refresh_attempted": true|false,
    "refresh_scheduled": true|false,
    "refresh_reason": "interval"|"stale_cache"|"error"|null,
    "refresh_forced": true|false
  }
}
```

When `ok:true` the handler always returns an object in `data` (an empty `{}` when no snapshot exists) so tiles stay rendered. If the database connection is unavailable the handler now fails fast with `ok:false`, `data:null`, and `error:"db_timeout"|"db_unavailable"`. In that case diagnostics still include cache metadata and `diagnostics.cacheFallback:true` so callers can continue showing the previous payload while backing off retries.

`diagnostics.cache_hit` flags when the handler served the last-good snapshot, and
`diagnostics.cacheFallback`/`cache_fallback` show whether cached data was required because
the primary query failed or rehydrated. `diagnostics.cache_age_seconds` reports how old that payload was when returned. If the
database returns an empty snapshot but cached data exists, the handler now rehydrates the
response from the cache and surfaces `diagnostics.cache_rehydrated:true` so operators know
the data was preserved from a previous call. When the service schedules a background
refresh it records `refresh_attempted`, whether it was actually `refresh_scheduled`, and
the `refresh_reason` (`interval` for the normal five-minute cadence, `stale_cache` when
the snapshot is older than fifteen minutes, or `error` when the database query failed).
`refresh_forced` indicates that the debounce was skipped because of staleness or an error
condition. When an empty payload is rehydrated from cache the diagnostics keep
`day_used` aligned with the cached snapshot for visibility, but background refreshes are
scheduled against the current local day so a stale cache entry cannot trap the mart on
yesterday’s data.

`diagnostics.enrichment_errors` lists any enrichment queries (sleep aggregation, space
weather, Schumann resonance, etc.) that were skipped because they hit the short timeout.
The handler still returns data, but these entries allow the UI to annotate partially
freshened payloads.

`diagnostics.cache_snapshot_initial` and `diagnostics.cache_snapshot_final` provide
lightweight summaries of the cache state before and after the request, highlighting
whether health, sleep, space-weather, or Schumann sections contained non-null values.
`diagnostics.payload_summary` performs the same check on the payload returned to the
client, while `diagnostics.cache_updated` flags when the handler wrote a new snapshot to
the cache during the request. The `diagnostics.trace` array records timestamped steps in
the decision tree (for example when a mart row loads, when cached data is reused, or when
a background refresh is scheduled) so engineers can copy/paste a textual log instead of
relying on screenshots of the debug overlay.

## Source selection

1. **Today’s mart row** – if `marts.daily_features` already contains `(user_id, today_local)` the handler hydrates it with live sleep and space weather context.
2. **Freshen** – if today’s row is missing, the handler performs a short “freshen” by combining `gaia.daily_summary`, raw sleep samples, and space-weather feeds. The response is annotated with `source:"freshened"` and `freshened:true`.
3. **Yesterday fallback** – when neither of the above produce data, the handler loads yesterday’s mart row and marks `source:"yesterday"`.
4. **Cache fallback** – when the service cannot obtain a database connection (for example when pgBouncer is saturated) *or* when the mart query itself errors, the handler serves the last-good payload from the in-memory/Redis cache, marks `cache_fallback:true`, and records the failure inside `diagnostics.last_error`. Pool saturation also toggles `pool_timeout:true`. Clients continue to receive populated tiles even while the database is briefly unavailable.
5. **Rehydrate from cache** – when the mart returns an empty snapshot but the cache still
   holds a previous payload, the handler now reuses that cached data. Diagnostics set
   `cache_fallback:true`, `cache_hit:true`, and `cache_rehydrated:true` so the UI knows the
   payload came from cache even though the database request technically succeeded.
6. **Empty** – if no data or cache entry exists, the response is `{}` with `source:"empty"`.
   Even in this case the handler now returns `ok:true` so dashboards keep rendering
   defaults while diagnostics report the outage reason.

Because diagnostics are always returned, client teams can inspect `diagnostics.day_used`, `source`, and `mart_row` to understand which branch served the payload.

## Cache diagnostics and background refresh

When the handler falls back to the cached snapshot, diagnostics now expose how old that
payload is and whether a background mart refresh was queued. If the cached data is older
than fifteen minutes the refresh request bypasses the debounce window so new data is
computed as soon as possible; otherwise, refreshes run on a five-minute cadence per user.
These fields allow the UI to surface "refreshing" indicators while still showing the last
successful snapshot. Even when diagnostics report a cached `day_used`, the mart refresh
targets the current day to unblock fresh data generation.
