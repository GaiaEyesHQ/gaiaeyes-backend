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
  "data": { ... },     // `{}` when no data is available
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
    "pool_timeout": true|false,
    "error": string|null
  }
}
```

`data` is never `null`. When a snapshot is unavailable the handler returns `{}` with `ok:true` so tiles can remain filled with the last-good content.

## Source selection

1. **Today’s mart row** – if `marts.daily_features` already contains `(user_id, today_local)` the handler hydrates it with live sleep and space weather context.
2. **Freshen** – if today’s row is missing, the handler performs a short “freshen” by combining `gaia.daily_summary`, raw sleep samples, and space-weather feeds. The response is annotated with `source:"freshened"` and `freshened:true`.
3. **Yesterday fallback** – when neither of the above produce data, the handler loads yesterday’s mart row and marks `source:"yesterday"`.
4. **Cache fallback** – when the service cannot obtain a database connection (for example when pgBouncer is saturated), the handler serves the last-good payload from the in-memory/Redis cache, marks `cache_fallback:true`, and sets `pool_timeout:true`. Clients continue to receive populated tiles even while the database is briefly unavailable.
5. **Empty** – if no data or cache entry exists, the response is `{}` with `source:"empty"` (and `ok:false` when a hard error occurs).

Because diagnostics are always returned, client teams can inspect `diagnostics.day_used`, `source`, and `mart_row` to understand which branch served the payload.
