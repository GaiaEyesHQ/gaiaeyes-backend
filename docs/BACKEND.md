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
- `GET /v1/space/forecast/outlook` — consolidated outlook with `kp/bz/sw` **now** fields (from `marts.space_weather_daily`), plus `bulletins`, `swpc_text_alerts`, and `forecast_daily` from `marts.space_forecast_daily_latest`.
- `GET /v1/space/forecast/bulletins`
- `GET /v1/space/alerts/swpc`
- `GET /v1/space/series` and `GET /v1/series` (legacy alias)
- `GET /v1/series/lunar-overlay` — full/new moon marker metadata for chart overlays (`start`/`end` date range)

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
  - Returns: `weather` (temp/humidity/precip_prob/pressure + 24h deltas when cached), `air` (AQI/category/pollutant from AirNow), `allergens` (overall/current pollen context when a provider key is configured), `moon` (phase/illum), `where` (resolved coords), `asof`, and `forecast_daily` from `marts.local_forecast_daily`.
  - Notes: NOAA NWS requires a User‑Agent (see `WEATHER_UA`). Daily allergen rows are populated from Google Pollen when `GOOGLE_POLLEN_API_KEY` is present; Google currently provides up to 5 pollen forecast days, so later local forecast rows may keep pollen fields null. Endpoint may be publicly readable when allowlisted.

### Subscriptions & entitlements
- `POST /v1/billing/checkout` — server-created Stripe Checkout session. **Requires Supabase JWT** and stamps `metadata.user_id` (and `subscription_data.metadata.user_id`) for webhook mapping.
- `GET /v1/billing/entitlements` — returns current entitlements for the signed-in Supabase user.
- `POST /webhooks/stripe` — see **Webhooks → Billing**; Stripe Checkout/Invoices/Subscriptions events are processed here.
- `POST /webhooks/revenuecat` — see **Webhooks → Billing**; iOS in‑app purchases via RevenueCat are processed here.

### Features + symptoms
- `GET /v1/features/today` (daily features snapshot)
- `GET /v1/lunar/current` (current UTC-day lunar context)
- `GET /v1/insights/lunar` (authenticated observational lunar pattern summary)
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
- Targeted command for the forecast/allergen work: `python3 -m unittest tests.services.test_pollen tests.services.test_forecast_outlook tests.test_outlook_route`.

## Recent changes
- New: `/webhooks/stripe` and `/webhooks/revenuecat` for subscription billing (Stripe/RevenueCat).
- New: `/v1/hazards/gdacs` and `/v1/hazards/gdacs/full` (GDACS RSS upgrade; includes fires, floods, droughts, etc.).
- New: `/v1/local/check` aggregates NWS hourly grid, AirNow AQI, and moon phase; supports ZIP or lat/lon; cached snapshots power 24h deltas.
- New: `/v1/local/check` now also carries normalized current allergen context when Google Pollen is configured.
- New: `marts.daily_features` now stores canonical lunar context (`moon_phase_fraction`, `moon_illumination_pct`, `moon_phase_label`, `days_from_full_moon`, `days_from_new_moon`) keyed by UTC day, and `app.user_experience_profiles` now supports `lunar_sensitivity_declared` for presentation-only preference handling.
- New: `/v1/lunar/current`, `/v1/insights/lunar`, and `/v1/series/lunar-overlay` expose investigational lunar context and observational per-user comparisons without making causal or medical claims.
- New: `/v1/users/me/outlook` builds a user-scoped 24h/72h/7d outlook from normalized local forecast inputs plus parsed SWPC 3-day, weekly, and advisory bulletin rows.
- Updated: `/v1/local/check` now also returns the next 7 daily local forecast rows from `marts.local_forecast_daily`, including allergen forecast buckets/indexes when available.
- Updated: `/v1/space/forecast/outlook` now includes real‑time `kp/bz/solar_wind` “now” fields from `marts.space_weather_daily`, returns `bulletins`/SWPC text when available, and carries `forecast_daily` rows from `marts.space_forecast_daily_latest`.
- Updated: `/v1/features/today` and `/v1/space/series` now surface lunar context directly so iOS and WordPress can annotate existing trend charts instead of introducing a parallel chart API.
- Deprecated: legacy root endpoints `/gdacs`, `/brief`, `/kp_schumann` in favor of `/v1/hazards/*` namespace.
