# Operations Runbook

## Supabase configuration
- Set **POOL_MODE=transaction** for the project's pgBouncer configuration when using async clients.
- Keep the project in the "Running" state; paused projects will close existing connections and cause client pool churn.
- Tune pgBouncer `idle_timeout` to be at least 60 seconds so short gaps in traffic do not recycle connections immediately.

## Render environment
- `DATABASE_URL` should target the pgBouncer endpoint on port **6543** and include `sslmode=require` in the query string.
- Restarting the service will automatically reopen the shared async connection pool during FastAPI startup.
- When pgBouncer begins terminating connections the backend automatically fails over to the
  configured `DIRECT_URL` (if provided). Consecutive `PoolTimeout` errors (two in a row)
  trigger the swap and emit `[POOL] failover → direct postgres (after N timeouts)` followed
  by `[POOL] backend=direct`. Watch for those log lines to confirm the service is running
  against the fallback and that the direct connection remains reachable.
- Pool acquisition timeouts now reset once a healthy checkout occurs. When pgBouncer recovers
  you will see `[POOL] backend=pgbouncer` after the watchdog successfully probes it again.

## Connectivity checks
Run the following from a Render shell or any environment that has network access to Supabase:

```bash
psql "$DATABASE_URL" -c "select now()"
```

A successful response confirms the credentials, pgBouncer endpoint, and SSL settings are all valid.

### Automated connectivity diagnostics
- Run `scripts/db_diagnose.py --pretty` to probe the same DSNs that the service will
  use. The script first validates that `DATABASE_URL` resolves to pgBouncer (when
  requested) and that a direct fallback is configured. It then times connectivity to
  each target, returning JSON output similar to:

  ```json
  {
    "configuration": {
      "active_label": "pgbouncer",
      "fallback": {
        "conninfo": "postgres://...",
        "label": "direct"
      },
      "primary": {
        "conninfo": "postgres://...",
        "label": "pgbouncer"
      }
    },
    "results": {
      "active_label": "pgbouncer",
      "fallback": {
        "error": null,
        "label": "direct",
        "latency_ms": 92,
        "ok": true
      },
      "primary": {
        "error": "timeout",
        "label": "pgbouncer",
        "latency_ms": 5000,
        "ok": false
      }
    }
  }
  ```

- Use the output to decide which component needs attention:
  - If pgBouncer times out but the direct connection succeeds, restart pgBouncer or
    temporarily fail the service over to the direct DSN.
  - If both targets fail, the underlying Postgres instance or network is likely
    unavailable and should be escalated before relying on cached data.
- After remediation, rerun the script and `curl https://<host>/health` until `db:true`
  is reported to confirm ingestion and feature refreshes will resume.

## Service health endpoint
- `/health` now exposes `db`, `db_sticky_age`, and an embedded `monitor` snapshot. The snapshot
  includes `db_ok`, `consec_ok`, `consec_fail`, and `since/last_change` timestamps maintained by the
  asynchronous health monitor task.
- The monitor uses hysteresis: it flips to unhealthy only after two consecutive probe failures and
  requires two consecutive successes before declaring recovery. `db_sticky_age` reports how long the
  current state has been held so you can spot prolonged outages at a glance.
- No front-end changes are required; the mobile client still keys off `db:false`, while operations
  can examine the `monitor` block for deeper context without re-probing the database from the route.

## Database diagnostics
- `GET /v1/diag/db` summarizes the active pool backend (`pgbouncer` vs. `direct`), current min/max
  settings, timeout, and the number of checked-out connections. It also mirrors the health monitor
  state so you can track how long the pool has been unhealthy.
- When deeper visibility is required, `GET /v1/diag/dbpool` (admin-protected) surfaces the raw pool
  counters returned by psycopg (`open`, `used`, `waiting`).

## Feature cache retention during outages
- The `/v1/features/today` handler stores the last successful payload in Redis (and a local in-memory
  fallback) so the app can show tiles while the marts catch up.
- Set the optional `FEATURES_CACHE_TTL_SECONDS` environment variable to extend how long those
  snapshots are retained. The default remains six hours; increasing the value (for example, to
  several days) keeps the previous data available during prolonged database downtime.
- Invalid or non-positive values are ignored and logged at startup so experiment safely. When the
  override is active, the cache layer logs `[CACHE] ttl override enabled (...)` confirming the TTL
  in effect.

## Ingestion behavior during outages
- `/v1/samples/batch` now checks the health monitor before touching the database. When `db:false`
  the handler immediately rejects the batch with `error:"db_unavailable"`, allowing callers to back
  off without waiting for a timeout. Once the monitor reports healthy again, normal inserts resume.
- Successful inserts trigger at most one mart refresh per user every ~20 seconds. The refresh runs
  via a background task after a 2-second delay (`[MART] scheduled refresh (delayed) ...`), ensuring
  bursts of batches do not flood Postgres while allowing fresh features shortly after recovery.

## 2025-11 Stabilization Updates

- Render now uses the **direct Supabase host on port 5432** for all background refreshes and health probes.  
  PgBouncer endpoints (`aws-1-us-east-2.pooler.supabase.com:6543`) remain defined but are no longer primary.
- `DATABASE_URL` continues to point to the pooler, while `DIRECT_URL` provides the direct fallback — confirmed via:
  ```
  curl -s "$BASE/health" | jq '.monitor.pool_backend'
  ```
  Expect `"direct"` when running stable.
- The watchdog now self-recovers after connectivity interruptions, using `[POOL] backend=direct` until pgBouncer recovers.
- A lightweight deferred backoff (`1.5–2.0s`) was added between inserts and `marts.refresh_daily_features_user()` calls.
  This stabilizes commits from HealthKit uploads and prevents transient transaction-aborted errors.
- Redis cache behavior remains unchanged; stale features are served when `db:false`, and automatic refresh resumes once
  connectivity is restored.
- Do **not** revert `sslmode=require` or the connection parameters on port 5432; those are verified stable in Render’s
  direct-connection mode.
