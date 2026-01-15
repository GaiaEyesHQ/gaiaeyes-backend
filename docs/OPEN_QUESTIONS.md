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
