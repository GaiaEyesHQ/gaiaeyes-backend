# Operations Runbook

## Supabase configuration
- Set **POOL_MODE=transaction** for the project's pgBouncer configuration when using async clients.
- Keep the project in the "Running" state; paused projects will close existing connections and cause client pool churn.
- Tune pgBouncer `idle_timeout` to be at least 60 seconds so short gaps in traffic do not recycle connections immediately.

## Render environment
- `DATABASE_URL` should target the pgBouncer endpoint on port **6543** and include `sslmode=require` in the query string.
- Restarting the service will automatically reopen the shared async connection pool during FastAPI startup.

## Connectivity checks
Run the following from a Render shell or any environment that has network access to Supabase:

```bash
psql "$DATABASE_URL" -c "select now()"
```

A successful response confirms the credentials, pgBouncer endpoint, and SSL settings are all valid.
