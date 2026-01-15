# Gaia Eyes — Backend, iOS, and WordPress

Gaia Eyes is a multi-surface system that combines a FastAPI backend, a Swift iOS app, and a WordPress front-end for space weather + health context. The backend is the canonical API surface for apps and sites, with Supabase as the source of truth for data storage, authentication, and media. The iOS app uploads HealthKit and BLE samples and reads summary endpoints; the WordPress site renders public dashboards with backend APIs where available and JSON fallbacks for legacy datasets.

```mermaid
flowchart LR
  subgraph Clients
    IOS[iOS App]
    WP[WordPress wp-content]
    Bots[Data ingest scripts/bots]
  end

  subgraph Backend
    API[FastAPI /app]
    DB[(Supabase Postgres)]
    Storage[(Supabase Storage)]
  end

  IOS -->|HTTP (Bearer / Dev User)| API
  WP -->|HTTP (Bearer / Dev User)| API
  Bots -->|DB writes / Storage uploads| DB
  Bots -->|Storage uploads| Storage
  API --> DB
  API --> Storage

  WP -->|Legacy JSON| Media[gaiaeyes-media JSON CDN]
  IOS -->|CDN fallback| Media
```

## Repo map
- `app/`: FastAPI application (routers, db access, auth) powering the backend API.
- `api/`: webhook middleware + routes used by the backend when enabled.
- `scripts/` + `bots/` + `workers/`: data ingest, batch processing, and cron-style jobs.
- `supabase/`: local Supabase config + migrations defining schemas/tables/views.
- `gaiaeyes-ios/`: Swift iOS app (GaiaExporter) and iOS docs.
- `wp-content/`: WordPress theme and mu-plugins that render the site.
- `docs/`: project documentation (architecture, deployment, component guides).

## Quickstart docs
- Backend: see `docs/BACKEND.md`
- iOS: see `docs/IOS_APP.md`
- WordPress: see `docs/WORDPRESS.md`
- Supabase: see `docs/SUPABASE.md`
- Render: see `docs/DEPLOY_RENDER.md`

## Source of truth
Supabase (Postgres + Auth + Storage) is the universal source of truth. Backend services read/write directly to Supabase and expose the API that clients should prefer. JSON files in `gaiaeyes-media` remain in use as fallbacks for the WordPress site and iOS CDN resilience, and are being phased out in favor of Supabase-backed endpoints.

## Additional docs
- `docs/ARCHITECTURE.md` — system map + data flows
- `docs/ENVIRONMENT_VARIABLES.md` — env var reference
- `docs/TROUBLESHOOTING.md` — common fixes
- `docs/OPEN_QUESTIONS.md` — unknowns to resolve
