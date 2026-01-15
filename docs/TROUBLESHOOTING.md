# Troubleshooting

## Backend auth errors (401)
**Symptoms**: `Missing or invalid Authorization header` or `Invalid bearer token`.
**Fixes**:
- Ensure `Authorization: Bearer <token>` is set.
- For dev flows, set `DEV_BEARER` and pass `X-Dev-UserId`.
- For Supabase JWTs, ensure `SUPABASE_JWT_SECRET` is configured.

## Supabase connection failures
**Symptoms**: API responds with `db_unavailable` or pool timeouts.
**Fixes**:
- Verify `DATABASE_URL` and optional `DIRECT_URL`.
- Check `/v1/db/ping` for connectivity.
- Inspect pool logs; failover should switch to `DIRECT_URL` if configured.

## Symptom endpoints failing
**Symptoms**: `unknown symptom_code` or invalid event inserts.
**Fixes**:
- Confirm symptom code list in `dim.symptom_codes`.
- Refresh marts via `scripts/refresh_symptom_marts.py` if daily views are stale.

## CORS issues
**Symptoms**: browser errors for blocked requests.
**Fixes**:
- Confirm `CORS_ORIGINS` is set appropriately.
- The backend uses permissive `allow_origins=["*"]` by default; validate if a proxy is overriding.

## Space visuals missing
**Symptoms**: /v1/space/visuals returns empty or missing assets.
**Fixes**:
- Confirm `VISUALS_MEDIA_BASE_URL`, `MEDIA_BASE_URL`, or `GAIA_MEDIA_BASE` is configured.
- Verify uploads to Supabase Storage (bucket `space-visuals`).

## WordPress API fallback only
**Symptoms**: WP uses JSON and ignores API.
**Fixes**:
- Ensure `GAIAEYES_API_BASE` and `GAIAEYES_API_BEARER` are present in the WP environment.
- Confirm `gaiaeyes-api-helpers.php` is loaded (mu-plugins).

## Render deploy failures
**Symptoms**: Render build fails or service doesn’t start.
**Fixes**:
- Confirm `Dockerfile` and/or `Procfile` matches the service type in Render.
- Check `runtime.txt` for Python version alignment.
- Verify required env vars are set in Render.

## iOS build issues
**Symptoms**: HealthKit or BLE build failures.
**Fixes**:
- Build on a real device for HealthKit.
- Reset SwiftPM caches if dependencies fail to resolve.
- Ensure HealthKit entitlements are present in the Xcode project.

## WordPress plugin/theme conflicts
**Symptoms**: Shortcodes not rendering.
**Fixes**:
- Confirm mu-plugins are loaded (must-use plugins are always active).
- Validate shortcodes are present in the active theme or content.

