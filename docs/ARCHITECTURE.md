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

  IOS -->|Bearer + X-Dev-UserId| API
  WP -->|Bearer + X-Dev-UserId| API
  API --> DB
  API --> Storage

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

## Known inconsistencies + TODOs (from current repo)
- **Schumann latest endpoint vs schema**: `/v1/earth/schumann/latest` reads `marts.daily_features` columns `f0..f5`, but the migration for `marts.daily_features` does not define those columns. This endpoint likely needs a schema alignment or a different source.
- **Webhook stubs**: `/hooks/*` endpoints are present but include TODOs and do not implement downstream actions yet.
- **Multiple data sources**: several components still fall back to JSON snapshots (gaiaeyes-media) while backend endpoints also exist. This creates duplicate paths that can drift.
- **Media base overlap**: multiple env vars (`VISUALS_MEDIA_BASE_URL`, `MEDIA_BASE_URL`, `GAIA_MEDIA_BASE`) can define the same base URL, which can cause confusion.
