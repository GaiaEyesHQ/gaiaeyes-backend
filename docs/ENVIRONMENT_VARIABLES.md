# Environment Variables

> **Do not commit real secrets.** Use placeholders and rotate any leaked tokens.

## Backend (FastAPI)
| Variable | Purpose | Example placeholder | Where used |
| --- | --- | --- | --- |
| `DATABASE_URL` | Supabase Postgres connection | `postgresql://postgres:***@db.<project>.supabase.co:5432/postgres` | `app/db/__init__.py` |
| `DIRECT_URL` | Optional direct Postgres fallback | `postgresql://postgres:***@db.<project>.supabase.co:5432/postgres` | `app/db/__init__.py` |
| `SUPABASE_JWT_SECRET` | Validate Supabase JWTs | `supabase-jwt-secret` | `app/utils/auth.py` |
| `SUPABASE_URL` | Supabase REST/Storage base URL | `https://<project>.supabase.co` | `app/utils/supabase_storage.py` |
| `SUPABASE_SERVICE_ROLE_KEY` | Storage uploads | `service-role-key` | `app/utils/supabase_storage.py` |
| `BUCKET` | Storage bucket name | `space-visuals` | `app/utils/supabase_storage.py` |
| `READ_TOKENS` | Comma-separated read tokens | `token1,token2` | `app/security/auth.py` |
| `WRITE_TOKENS` | Comma-separated write tokens | `token1,token2` | `app/security/auth.py` |
| `DEV_BEARER` | Dev bearer token | `devtoken123` | `app/security/auth.py`, `app/db/__init__.py` |
| `PUBLIC_READ_ENABLED` | Enable public read allowlist | `1` | `app/security/auth.py` |
| `PUBLIC_READ_PATHS` | CSV allowlist of public GET paths | `/health,/v1/space/visuals` | `app/security/auth.py` |
| `CORS_ORIGINS` | CORS origin list | `*` | `app/db/__init__.py` |
| `REDIS_URL` | Optional caching/queues | `redis://...` | `app/db/__init__.py` |
| `FEATURES_CACHE_TTL_SECONDS` | Features cache TTL | `300` | `app/db/__init__.py` |
| `MEDIA_BASE_URL` | Default CDN base for visuals | `https://.../gaiaeyes-media` | `app/routers/summary.py` |
| `GAIA_MEDIA_BASE` | Alternate CDN base | `https://.../gaiaeyes-media` | `app/routers/summary.py` |
| `VISUALS_MEDIA_BASE_URL` | Visuals-specific CDN base | `https://.../gaiaeyes-media` | `app/routers/space_visuals.py` |
| `GOES_XRS_URL` | Space flares data source | `https://services.swpc.noaa.gov/...` | `app/routers/space.py` |
| `MART_REFRESH_DISABLE` | Disable mart refresh on ingest | `0` | `app/routers/ingest.py` |
| `DEBUG_FEATURES_DIAG` | Enable features diagnostics | `1` | `app/routers/summary.py` |
| `WEBHOOK_SECRET` | HMAC secret for `/hooks/*` | `webhook-secret` | `api/middleware.py`, `api/webhooks.py` |

## iOS (runtime/in-app)
| Variable | Purpose | Where set |
| --- | --- | --- |
| `API Base URL` | Backend base URL | In-app settings (stored in `UserDefaults`) |
| `Bearer Token` | Backend bearer token | In-app settings |
| `User UUID` | Supabase user id | In-app settings |
| `MEDIA_BASE_URL` | CDN fallback base URL | Process env (if set) |

## WordPress (wp-content)
| Variable | Purpose | Example placeholder | Where used |
| --- | --- | --- | --- |
| `GAIAEYES_API_BASE` | Backend API base URL | `https://gaiaeyes-backend.onrender.com` | `wp-content/mu-plugins/gaiaeyes-space-weather-detail.php` |
| `GAIAEYES_API_BEARER` | Backend bearer token | `devtoken123` | `wp-content/mu-plugins/gaiaeyes-space-weather-detail.php` |
| `GAIAEYES_API_DEV_USERID` | Dev user id for backend | `uuid` | `wp-content/mu-plugins/gaiaeyes-space-weather-detail.php` |
| `GAIAEYES_SPACE_VISUALS_ENDPOINT` | Override space visuals API URL | `https://.../v1/space/visuals` | `wp-content/mu-plugins/gaiaeyes-space-visuals.php` |
| `GAIAEYES_SPACE_VISUALS_BEARER` | Auth for space visuals endpoint | `token` | `wp-content/mu-plugins/gaiaeyes-space-visuals.php` |
| `GAIA_MEDIA_BASE` | Base URL for JSON/media | `https://.../gaiaeyes-media` | `wp-content/mu-plugins/gaiaeyes-space-visuals.php` |
| `GAIA_AURORA_NOWCAST_URL` | Aurora nowcast URL override | `https://services.swpc.noaa.gov/...` | `wp-content/mu-plugins/gaia-aurora.php` |
| `GAIA_AURORA_IMAGE_NORTH` | Aurora image override (north) | `https://.../north.png` | `wp-content/mu-plugins/gaia-aurora.php` |
| `GAIA_AURORA_IMAGE_SOUTH` | Aurora image override (south) | `https://.../south.png` | `wp-content/mu-plugins/gaia-aurora.php` |
| `GAIA_AURORA_CACHE_TTL_SECONDS` | Cache TTL | `600` | `wp-content/mu-plugins/gaia-aurora.php` |
| `GAIA_AURORA_VIEWLINE_P` | Viewline probability | `50` | `wp-content/mu-plugins/gaia-aurora.php` |
| `GAIA_AURORA_VIEWLINE_P_NORTH` | Viewline probability north | `50` | `wp-content/mu-plugins/gaia-aurora.php` |
| `GAIA_AURORA_SMOOTH_WINDOW` | Smoothing window | `5` | `wp-content/mu-plugins/gaia-aurora.php` |
| `GAIA_AURORA_ENABLE_JSON_EXPORT` | Enable JSON export | `0` | `wp-content/mu-plugins/gaia-aurora.php` |

## Render
Render-specific env vars are likely set in the dashboard (see `docs/OPEN_QUESTIONS.md`).
