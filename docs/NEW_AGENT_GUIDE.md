# New Agent Guide (Single-Doc Canonical)

This document is the one-stop reference for new agents working in this repo. It summarizes the architecture, conventions, and safe workflows so changes do not introduce naming drift or delete useful code.

## 1) What you are working on
Gaia Eyes combines a FastAPI backend, a Swift iOS app, and a WordPress front-end. Supabase (Postgres + Auth + Storage) is the universal source of truth. JSON snapshots from `gaiaeyes-media` still exist as legacy fallbacks and are being phased out in favor of Supabase-backed endpoints.

## 2) Component map (where to change what)
- **Backend API**: `/app` and `/api`
- **Supabase schema**: `/supabase/migrations`
- **iOS app**: `/gaiaeyes-ios/ios`
- **WordPress (site)**: `/wp-content`
- **Docs**: `/docs` and root Markdown files
- **Earthscope writer**: `/bots/earthscope_post` (daily_posts copy + card JSON)

## 3) Hard rules (do not violate)
- Do **not** change naming conventions for tables, routes, env vars, or data keys.
- Do **not** add new JSON pipelines; prefer Supabase + backend endpoints.
- Do **not** refactor unrelated code or delete features without explicit request.
- Do **not** commit secrets. Use placeholders and add a rotation note if you find real secrets.

## 4) Auth & data access conventions
**Backend auth**
- Read endpoints can be allowlisted (`PUBLIC_READ_ENABLED`, `PUBLIC_READ_PATHS`) but otherwise require bearer auth.
- Write endpoints require bearer auth; tokens can be either pre-shared (`READ_TOKENS`, `WRITE_TOKENS`) or Supabase JWTs.
- Dev flows use `DEV_BEARER` plus `X-Dev-UserId`.

**Supabase access**
- Backend writes directly to Supabase. Clients should prefer backend endpoints, not direct DB access.
- Storage uploads use `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`.

**Earthscope writer inputs**
- Primary data source: `GAIA_BACKEND_BASE/v1/space/forecast/outlook` (fallbacks to marts + legacy JSON when missing).
- Style/correlation guides live in `bots/earthscope_post/style_rules.json` and `bots/earthscope_post/symptom_guides.json`.
- Key env toggles: `GAIA_BACKEND_BASE`, `STYLE_RULES_PATH`, `SYMPTOM_GUIDES_PATH`, `WRITER_LENS`, `WRITER_HUMOR`, `WRITER_TEMP`, `FORCE_PRESSURE_NOTE`, `OPENAI_WRITER_MODEL`.

## 5) API routing conventions (backend)
Backend routes are grouped by domain under `app/routers/` and registered in `app/main.py`.
- Space/visuals: `/v1/space/*` and `/v1/space/visuals`
- Quakes: `/v1/quakes/*`
- Earth/Schumann: `/v1/earth/schumann/latest`
- Local health: `/v1/local/*`
- Features: `/v1/features/today`
- Symptoms: `/v1/symptoms/*`
- Ingest: `/v1/samples/batch`

Do not add routes in random files. Keep them in `app/routers/*` and include them in `app/main.py`.

## 6) iOS conventions
- `AppState` is the central ObservableObject.
- `APIClient` handles retries, tolerant decoding, and CDN fallback.
- The app expects `Authorization: Bearer <token>` + optional `X-Dev-UserId`.

## 7) WordPress conventions
- Use mu-plugins for data shortcodes and API calls.
- Use `gaiaeyes-api-helpers.php` for API fetch + caching.
- Prefer backend API where available; fallback to JSON is legacy-only.

## 8) Known inconsistencies to avoid worsening
- `/v1/earth/schumann/latest` reads columns (`f0..f5`) that are not defined in `marts.daily_features` migration.
- `/hooks/*` endpoints are placeholders with TODOs only.
- Multiple media base env vars (`VISUALS_MEDIA_BASE_URL`, `MEDIA_BASE_URL`, `GAIA_MEDIA_BASE`) can conflict; keep them aligned.

## 9) Required workflow for every task
1. Read relevant files + docs.
2. Propose a short plan.
3. Implement the **smallest** viable diff.
4. Run or document checks (tests/builds).
5. Update docs for any changes to routes, env vars, data formats.

## 10) When you are unsure
Add a question to `docs/OPEN_QUESTIONS.md` instead of guessing. Include:
- What is unknown
- Why it matters
- Where a human can confirm it
