# Backend (FastAPI)

## Entry point + structure
- Entry point: `app/main.py` initializes the FastAPI app, middleware, CORS, DB pool, and routers.
- Routers live in `app/routers/` and are grouped by domain.
- Database access uses async psycopg connection pooling in `app/db/__init__.py`.
- Auth helpers live in `app/security/auth.py` and `app/utils/auth.py`.

## Auth strategy
- **Read tokens**: allowlisted via `READ_TOKENS` env var.
- **Write tokens**: allowlisted via `WRITE_TOKENS` env var.
- **Supabase JWT**: validated using `SUPABASE_JWT_SECRET` to extract `user_id`.
- **Dev override**: `DEV_BEARER` + `X-Dev-UserId` attach a user in dev/test.
- Certain GET routes can be publicly readable via `PUBLIC_READ_ENABLED` and `PUBLIC_READ_PATHS`.

## API surface (routes)
### Health + diagnostics
- `GET /health` (health check)
- `GET /v1/diag/db` (db diagnostics)
- `GET /v1/diag/dbpool` (pool diagnostics)
- `GET /v1/db/ping` (db ping)

### Hazards + badges
- `GET /gdacs`
- `GET /brief`
- `GET /kp_schumann`

### Space + visuals
- `GET /v1/space/visuals` (space visuals + media list)
- `GET /v1/space/visuals/public` (public visuals)
- `GET /v1/space/visuals/diag` (visuals diagnostics)
- `GET /v1/space/flares`
- `GET /v1/space/history`
- `GET /v1/space/xray/history`
- `GET /v1/space/magnetosphere`
- `GET /v1/space/forecast/summary`
- `GET /v1/space/forecast/outlook` (includes `bulletins` and `swpc_text_alerts` when available)
- `GET /v1/space/forecast/bulletins`
- `GET /v1/space/alerts/swpc`
- `GET /v1/space/series` and `GET /v1/series` (legacy alias)

### Earth + quakes
- `GET /v1/earth/schumann/latest`
- `GET /v1/quakes/daily`
- `GET /v1/quakes/events`
- `GET /v1/quakes/latest`
- `GET /v1/quakes/monthly`
- `GET /v1/quakes/history`

### Local health
- `GET /v1/local/check`

### Features + symptoms
- `GET /v1/features/today` (daily features snapshot)
- `POST /v1/symptoms` (log a symptom)
- `GET /v1/symptoms/today`
- `GET /v1/symptoms/daily`
- `GET /v1/symptoms/diag`
- `GET /v1/symptoms/codes`

### Ingest
- `POST /samples/batch` (samples batch ingest)
- `POST /v1/samples/batch` (compat alias)

### Webhooks
- `POST /hooks/earthscope`
- `POST /hooks/social`

## Validation strategy
- Pydantic models are used for request/response validation in routers.
- The backend returns safe envelopes (`{"ok": false, ...}`) on error to keep clients resilient.

## Supabase access
- The backend connects directly to Supabase Postgres via `DATABASE_URL` and optional `DIRECT_URL` failover.
- Storage uploads use `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`.

## Testing
- `tests/` exists for backend-related tests.
- No unified test runner is documented; if you add new tests, document the command in this file.
