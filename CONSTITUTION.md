# Gaia Eyes Project Constitution

This document is enforceable and applies to every change in this repository.

## Components & Languages
- **Backend**: Python (FastAPI), PostgreSQL (Supabase) — `/app`, `/api`, `/scripts`, `/workers`.
- **iOS App**: Swift/SwiftUI — `/gaiaeyes-ios/ios`.
- **WordPress**: PHP (mu-plugins + theme) — `/wp-content`.
- **Data layer**: Supabase Postgres + Supabase Storage — `/supabase` (migrations, config).

## Directory ownership
- **Backend API** lives in `/app` and `/api` only.
- **Schema changes** live in `/supabase/migrations` only.
- **iOS** changes live in `/gaiaeyes-ios/ios` only.
- **WordPress** changes live in `/wp-content` only.
- **Docs** live in `/docs` and root Markdown files only.

## Do / Don’t Rules (non-negotiable)
**Do**
- Follow existing API routes and auth patterns.
- Keep Supabase as the source of truth; add endpoints before adding new JSON pipelines.
- Document every non-trivial behavior change.
- Prefer minimal diffs; avoid refactors unless requested.

**Don’t**
- Don’t invent new naming conventions for tables, env vars, or endpoints.
- Don’t bypass Supabase auth rules or store secrets in the repo.
- Don’t add dependencies or new services without explicit approval.
- Don’t delete existing features unless a task explicitly requires it.

## Patterns to copy (canonical examples)
- **Auth + user context**: `app/security/auth.py` (bearer + dev headers + Supabase JWT).
- **DB access**: `app/db/__init__.py` (connection pool + failover + timeouts).
- **Endpoint structure**: `app/routers/summary.py` (read-only aggregation) and `app/routers/ingest.py` (write ingest).
- **iOS API usage**: `gaiaeyes-ios/ios/GaiaExporter/Services/APIClient.swift`.
- **WP API helper**: `wp-content/mu-plugins/gaiaeyes-api-helpers.php`.

## Error handling + logging
- Backend endpoints return safe JSON envelopes (`{"ok": false, ...}`) on failure.
- All DB operations should guard with timeouts and log failures; avoid silent exceptions.
- Client-side code (iOS/WP) should log and fall back without crashing.

## Data access rules
- Supabase is the **universal truth**.
- Backend owns writes to Supabase; clients should prefer backend endpoints.
- JSON files are **legacy fallback** only; create/extend endpoints before adding new JSON.

## Definition of done (per change)
- Lint/test/build commands for the touched component run (or are documented as not runnable here).
- Docs updated if behavior, env vars, or endpoints change.
- No secrets added, no unexplained deletions.

## PR checklist
- [ ] Updated docs for the change.
- [ ] Confirmed Supabase schema + RLS impact (if applicable).
- [ ] Included migration file for DB schema changes.
- [ ] Ran or documented tests.
- [ ] Noted any remaining TODOs in `docs/OPEN_QUESTIONS.md`.

## Review checklist
- [ ] Changes align with existing patterns (no new conventions).
- [ ] Supabase remains the source of truth.
- [ ] API/auth compatibility preserved.
- [ ] WordPress/iOS fallbacks still safe.
