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
- Certain GET routes can be publicly readable via `PUBLIC_READ_ENABLED` and `PUBLIC_READ_PATHS` (e.g., `/v1/local/check`, `/v1/space/forecast/outlook`).

## API surface (routes)
### Health + diagnostics
- `GET /health` (health check)
- `GET /v1/diag/db` (db diagnostics)
- `GET /v1/diag/dbpool` (pool diagnostics)
- `GET /v1/db/ping` (db ping)

### Hazards + badges
- `GET /v1/hazards/gdacs` — recent GDACS events (all types) with normalized summary fields.
- `GET /v1/hazards/gdacs/full` — full GDACS payloads (includes descriptive text/notes), accepts filters.
- `GET /v1/hazards/brief` — compact multi‑source hazards brief. *(Alias for legacy `/brief`.)*
- `GET /v1/hazards/kp_schumann` — compact KP + Schumann badge payload. *(Alias for legacy `/kp_schumann`.)*
- **Deprecated:** `/gdacs` → use `/v1/hazards/gdacs`.

### Space + visuals
- `GET /v1/space/visuals` (space visuals + media list)
- `GET /v1/space/visuals/public` (public visuals)
- `GET /v1/space/visuals/diag` (visuals diagnostics)
- `GET /v1/space/flares`
- `GET /v1/space/history`
- `GET /v1/space/xray/history`
- `GET /v1/space/magnetosphere`
- `GET /v1/space/forecast/summary`
- `GET /v1/space/forecast/outlook` — consolidated outlook with `kp/bz/sw` **now** fields (from `marts.space_weather_daily`), plus `bulletins` and `swpc_text_alerts` when available.
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
  - Query: `zip` (preferred) or `lat`,`lon`.
  - Returns: `weather` (temp/humidity/precip_prob/pressure + 24h deltas when cached), `air` (AQI/category/pollutant from AirNow), `moon` (phase/illum), `where` (resolved coords), `asof`.
  - Notes: NOAA NWS requires a User‑Agent (see `WEATHER_UA`). Endpoint may be publicly readable when allowlisted.

### Subscriptions & entitlements
- `POST /v1/billing/checkout` — server-created Stripe Checkout session. **Requires Supabase JWT** and stamps `metadata.user_id` (and `subscription_data.metadata.user_id`) for webhook mapping.
- `GET /v1/billing/entitlements` — returns current entitlements for the signed-in Supabase user.
- `POST /webhooks/stripe` — see **Webhooks → Billing**; Stripe Checkout/Invoices/Subscriptions events are processed here.
- `POST /webhooks/revenuecat` — see **Webhooks → Billing**; iOS in‑app purchases via RevenueCat are processed here.

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

## Webhooks

### Billing (subscriptions)
- `POST /webhooks/stripe` — handles `checkout.session.completed`, `customer.subscription.*`, `invoice.payment_*`. Records Stripe ↔ user mapping and upserts entitlements.
- `POST /webhooks/revenuecat` — handles RevenueCat/iOS purchase lifecycle events and upserts entitlements.

### Bots / automation
- `POST /hooks/earthscope`
- `POST /hooks/social`

## Validation strategy
- Pydantic models are used for request/response validation in routers.
- The backend returns safe envelopes (`{"ok": false, ...}`) on error to keep clients resilient.

## Supabase access
- The backend connects directly to Supabase Postgres via `DATABASE_URL` (or `SUPABASE_DB_URL`) with optional `DIRECT_URL` failover.
- Storage uploads use `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`.

## Subscriptions integration (data flow)
- Clients call `POST /v1/billing/checkout` with a Supabase JWT to create a Stripe Checkout Session (metadata includes the Supabase `user_id`).
- Stripe Checkout (or the Customer Portal) posts to `/webhooks/stripe`. The backend writes:
  - `public.app_stripe_customers(stripe_customer_id, user_id, created_at, updated_at)`
  - `public.app_user_entitlements(user_id, entitlement_key, term, source, started_at, expires_at, is_active, updated_at)`
- (Optional) RevenueCat posts to `/webhooks/revenuecat` with the same upsert behavior.
- Clients do not call these endpoints directly; they read entitlements from Supabase (or via the app’s entitlements helper).

## Testing
- `tests/` exists for backend-related tests.
- No unified test runner is documented; if you add new tests, document the command in this file.

## Recent changes
- New: `/webhooks/stripe` and `/webhooks/revenuecat` for subscription billing (Stripe/RevenueCat).
- New: `/v1/hazards/gdacs` and `/v1/hazards/gdacs/full` (GDACS RSS upgrade; includes fires, floods, droughts, etc.).
- New: `/v1/local/check` aggregates NWS hourly grid, AirNow AQI, and moon phase; supports ZIP or lat/lon; cached snapshots power 24h deltas.
- Updated: `/v1/space/forecast/outlook` now includes real‑time `kp/bz/solar_wind` “now” fields from `marts.space_weather_daily`, and returns `bulletins`/SWPC text when available.
- Deprecated: legacy root endpoints `/gdacs`, `/brief`, `/kp_schumann` in favor of `/v1/hazards/*` namespace.
