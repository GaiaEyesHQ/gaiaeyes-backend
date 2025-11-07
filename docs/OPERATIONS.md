# Operations Runbook

## Supabase configuration
- Set **POOL_MODE=transaction** for the project's pgBouncer configuration when using async clients.
- Keep the project in the "Running" state; paused projects will close existing connections and cause client pool churn.
- Tune pgBouncer `idle_timeout` to be at least 60 seconds so short gaps in traffic do not recycle connections immediately.

## Render environment
- `DATABASE_URL` should target the pgBouncer endpoint on port **6543** and include `sslmode=require` in the query string.
- Restarting the service will automatically reopen the shared async connection pool during FastAPI startup.
- When pgBouncer begins terminating connections the backend now automatically fails over to
  the configured `DIRECT_URL` (if provided). Watch for `[DB] connection failure` log lines to
  confirm the switch and ensure the direct connection remains reachable.

## Connectivity checks
Run the following from a Render shell or any environment that has network access to Supabase:

```bash
psql "$DATABASE_URL" -c "select now()"
```

A successful response confirms the credentials, pgBouncer endpoint, and SSL settings are all valid.

## Service health endpoint
- `/health` now exposes `db`, `db_sticky_age`, and `db_latency_ms`. The latency field reports the
  duration of the most recent probe (in milliseconds) so you can see when pgBouncer handshakes are
  slowing down even if the sticky grace period keeps the service marked as healthy.
- The backend keeps returning the last known `db` result for up to 30 seconds after a failed probe
  to avoid flapping during transient network hiccups. Once the grace window expires the endpoint
  flips to `db:false`, which is what the mobile client already understands for gating refreshes.
- No front-end changes are required; the iOS client will continue to honor `db:false` while the new
  latency metric simply adds operator visibility.
