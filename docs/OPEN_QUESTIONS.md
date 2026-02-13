# Open Questions

1. **Render services + cron jobs**
   - **Why needed**: backend + scheduled ingest jobs are not defined in repo (`render.yaml` missing).
   - **Where to fill**: Render dashboard (service list, cron schedules, env vars).

2. **Supabase dashboard-only settings**
   - **Why needed**: RLS policies beyond migrations, storage bucket ACLs, and auth settings may exist only in the dashboard.
   - **Where to fill**: Supabase dashboard → Auth / Storage / Database policies.

3. **JSON pipelines still required**
   - **Why needed**: WordPress and iOS still rely on gaiaeyes-media JSON fallbacks; it’s unclear which pipelines are still scheduled and which are deprecated.
   - **Where to fill**: Ops runbooks or Render/cron job configs.

4. **Space visuals media hosting**
   - **Why needed**: Visuals can be served from Supabase storage or legacy CDN; the current authoritative source isn’t explicit.
   - **Where to fill**: Backend env vars (`VISUALS_MEDIA_BASE_URL`, `MEDIA_BASE_URL`, `GAIA_MEDIA_BASE`) and storage bucket configuration.

5. **Backend webhook consumers**
   - **Why needed**: `/hooks/*` endpoints are stubs with TODOs and may need downstream integrations.
   - **Where to fill**: Product/ops decision on desired webhook side effects.

6. **Schumann latest endpoint source**
   - **Why needed**: `/v1/earth/schumann/latest` reads `marts.daily_features` columns (`f0..f5`) that are not present in the migration schema.
   - **Where to fill**: Confirm intended data source (marts.schumann_daily vs daily_features) and update schema or endpoint accordingly.

7. **Website sections still JSON-only (News / Compare / Pulse)**
   - **Why needed**: The WordPress site relies on `gaiaeyes-media` JSON for News, Compare, and Pulse, but the iOS app needs an API-first source to mirror these sections.
   - **Where to fill**: Decide whether to (a) keep using the existing JSON snapshots in-app as a temporary source, or (b) add Supabase-backed tables + new backend endpoints.

8. **Schumann series endpoint mismatch with WP**
   - **Why needed**: WP calls `/v1/earth/schumann/series?hours=24&station=...`, but the backend endpoint currently accepts `limit` and `cols` only.
   - **Where to fill**: Confirm expected query parameters and update the backend or WP/clients to match.

9. **iOS Supabase project values**
   - **Why needed**: iOS billing auth now reads `SUPABASE_URL` + `SUPABASE_ANON_KEY` from `Info.plist`, but the concrete values must be filled in.
   - **Where to fill**: Supabase dashboard → Project settings → API.

10. **Magic link redirect URL + Associated Domains**
   - **Why needed**: iOS Supabase magic links need a redirect target that reopens the app (universal link or custom scheme). The app now supports an optional `GAIA_MAGICLINK_REDIRECT` but the exact URL + associated-domain setup is still a human config.
   - **Where to fill**: Apple Developer → Associated Domains + Supabase Auth redirect settings.

11. **RPC signatures for dashboard + local signals**
    - **Why needed**: The backend calls `app.get_local_signals_for_user` and `app.get_dashboard_payload`; it is unclear whether these require a `user_id` argument or rely on JWT context.
    - **Where to fill**: Supabase SQL definitions for the RPCs (or runbook notes).
