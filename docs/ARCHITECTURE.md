# Architecture

## System overview
```mermaid
flowchart LR
  subgraph Clients
    IOS[iOS App]
    WP[WordPress wp-content]
  end

  subgraph Backend
    API[FastAPI /app]
    DB[(Supabase Postgres)]
    Storage[(Supabase Storage)]
  end

  subgraph Billing
    STRIPE[Stripe Checkout / Customer Portal]
    RC[RevenueCat]
  end

  IOS -->|Bearer + X-Dev-UserId| API
  WP -->|Bearer + X-Dev-UserId| API
  API --> DB
  API --> Storage

  %% Web: server-created Stripe Checkout from WP
  WP -->|Supabase JWT + plan| API
  API -->|Create Checkout Session| STRIPE
  STRIPE -->|Webhooks| API

  %% iOS: IAP via RevenueCat
  IOS -->|IAP validation| RC
  RC -->|Webhooks| API

  subgraph Legacy
    Media[gaiaeyes-media JSON CDN]
  end
  IOS -->|CDN fallback| Media
  WP -->|JSON fallback| Media
```

## Universal truth
Supabase is the universal data source (Postgres + Auth + Storage). The backend owns writes to Supabase and exposes API endpoints for clients. JSON snapshots (gaiaeyes-media) are legacy fallbacks and are being phased out.

## Data flow: Health samples (iOS → Supabase)
```mermaid
sequenceDiagram
  participant iOS as iOS App
  participant API as FastAPI /v1/samples/batch
  participant DB as Supabase Postgres (gaia.samples)

  iOS->>API: POST /v1/samples/batch (HealthKit samples)
  API->>DB: INSERT rows (gaia.samples)
  API-->>iOS: ok/inserted/skipped
```

## Data flow: Space weather + visuals
```mermaid
sequenceDiagram
  participant Bots as Ingest scripts
  participant DB as Supabase Postgres
  participant API as FastAPI
  participant WP as WordPress

  Bots->>DB: ingest ext.* and marts.* tables
  API->>DB: read /v1/space/* + /v1/space/visuals
  WP->>API: fetch API endpoints when configured
  WP-->>Media: fallback to JSON if API unavailable
```

## Data flow: Symptoms
```mermaid
sequenceDiagram
  participant iOS as iOS App
  participant API as FastAPI /v1/symptoms
  participant DB as Supabase Postgres (raw.user_symptom_events)

  iOS->>API: POST /v1/symptoms
  API->>DB: INSERT raw.user_symptom_events
  API-->>iOS: ok/id
  iOS->>API: GET /v1/symptoms/daily
  API->>DB: read marts.symptom_daily
```

### Data flow: Subscriptions (web via Stripe)

```mermaid
sequenceDiagram
  participant U as User (WP)
  participant WP as WP (checkout button)
  participant API as FastAPI /v1/billing/checkout
  participant Stripe as Stripe Checkout
  participant WH as FastAPI /webhooks/stripe
  participant DB as Supabase (app_*)

  U->>WP: Click "Subscribe"
  WP->>API: POST /v1/billing/checkout (Supabase JWT, plan)
  API->>Stripe: Create Checkout Session (metadata.user_id)
  WP->>Stripe: Redirect to Checkout
  Stripe-->>U: Complete payment
  Stripe->>WH: webhook checkout.session.completed
  WH->>DB: upsert app_stripe_customers (customer_id ↔ user_id)
  Stripe->>WH: webhook customer.subscription.created/updated/deleted
  WH->>DB: upsert app_user_entitlements (plus/pro, term, is_active)
  WH-->>Stripe: 200 OK
```

Note: The iOS Subscribe view can use the same `/v1/billing/checkout` flow with a Supabase JWT for direct (non-IAP) subscriptions.

### Data flow: Subscriptions (iOS via RevenueCat)

```mermaid
sequenceDiagram
  participant iOS as iOS App
  participant RC as RevenueCat
  participant API as FastAPI /webhooks/revenuecat
  participant DB as Supabase (app_user_entitlements)

  iOS->>RC: Purchase / restore
  RC->>API: webhook (INITIAL_PURCHASE / RENEWAL / EXPIRATION)
  API->>DB: upsert app_user_entitlements (source=revenuecat)
  API-->>RC: 200 OK
```

## Key modules (back-end)
- **API entry point**: `app/main.py`
- **Auth**: `app/security/auth.py` + `app/utils/auth.py`
- **DB pool + failover**: `app/db/__init__.py`
- **Core routers**: `app/routers/*.py`
- **Webhook support**: `api/middleware.py`, `api/webhooks.py`

## Key modules (iOS)
- **App state + MVVM**: `gaiaeyes-ios/ios/GaiaExporter/ViewModels/AppState.swift`
- **Networking**: `gaiaeyes-ios/ios/GaiaExporter/Services/APIClient.swift`
- **Background sync**: `gaiaeyes-ios/ios/GaiaExporter/Services/HealthKitBackgroundSync.swift`

## Key modules (WordPress)
- **API helper**: `wp-content/mu-plugins/gaiaeyes-api-helpers.php`
- **Space visuals**: `wp-content/mu-plugins/gaiaeyes-space-visuals.php`
- **Space weather detail**: `wp-content/mu-plugins/gaiaeyes-space-weather-detail.php`
- **Theme shortcodes**: `wp-content/themes/neve/functions.php`
- **Subscriptions (WP)**: `wp-content/mu-plugins/gaia-subscriptions.php` (Stripe helper), `wp-content/mu-plugins/ge-pricing-table.php` (shortcode wrapper)

## Public API surface (selected)

- `/v1/space/visuals` – gallery of current images (relative paths + `cdn_base`)
- `/v1/space/forecast/outlook` – consolidated space-weather snapshot (now + 24–72h)
- `/v1/space/forecast/summary` – short human-readable summary + flags
- `/v1/hazards/gdacs` and `/v1/hazards/gdacs/full` – GDACS feed (recent + detailed)
- `/v1/local/check?zip=XXXXX` – local health signals (NWS + AirNow + moon)
- `/v1/billing/checkout` – server-created Stripe Checkout (requires Supabase JWT)
- `/v1/billing/entitlements` – current entitlements for signed-in users
- `/webhooks/stripe` – Stripe events (Checkout, Subscription)
- `/webhooks/revenuecat` – RevenueCat events (IAP)
- `/v1/auth/me/entitlements` – active entitlements for the current user

## Known inconsistencies + TODOs (from current repo)
- **Schumann latest endpoint**: RESOLVED — endpoint now reads from `marts.schumann_daily_v2` (and/or updated view). Remove the legacy path after prod verification.
- **Webhook stubs**: `/hooks/*` endpoints are present but include TODOs and do not implement downstream actions yet.
- **Multiple data sources**: several components still fall back to JSON snapshots (gaiaeyes-media) while backend endpoints also exist. This creates duplicate paths that can drift.
- **Media base overlap**: multiple env vars (`VISUALS_MEDIA_BASE_URL`, `MEDIA_BASE_URL`, `GAIA_MEDIA_BASE`) can define the same base URL, which can cause confusion.
- **Wing Kp**: `marts.space_weather_daily.wing_kp*` fields will remain `NULL` until an ingest for Wing Kp is added; track as a follow-up.
- **Env duplication**: consolidate `VISUALS_MEDIA_BASE_URL` / `MEDIA_BASE_URL` / `GAIA_MEDIA_BASE` after WP/iOS switchover is complete.
