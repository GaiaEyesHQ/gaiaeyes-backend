# Environment Variables

> **Do not commit real secrets.** Use placeholders and rotate any leaked tokens.

## Backend (FastAPI)
| Variable | Purpose | Example placeholder | Where used |
| --- | --- | --- | --- |
| `DATABASE_URL` | Supabase Postgres connection | `postgresql://postgres:***@db.<project>.supabase.co:5432/postgres` | `app/db/__init__.py` |
| `DIRECT_URL` | Optional direct Postgres fallback | `postgresql://postgres:***@db.<project>.supabase.co:5432/postgres` | `app/db/__init__.py` |
| `SUPABASE_DB_URL` | Supabase pooled Postgres connection (scripts/bots) | `postgresql://postgres:***@db.<project>.supabase.co:6543/postgres` | `services/db.py` |
| `SUPABASE_JWT_SECRET` | Validate Supabase JWTs | `supabase-jwt-secret` | `app/utils/auth.py` |
| `SUPABASE_URL` | Supabase REST/Storage base URL | `https://<project>.supabase.co` | `app/utils/supabase_storage.py` |
| `SUPABASE_SERVICE_ROLE_KEY` | Storage uploads | `service-role-key` | `app/utils/supabase_storage.py` |
| `BUCKET` | Storage bucket name | `space-visuals` | `app/utils/supabase_storage.py` |
| `READ_TOKENS` | Comma-separated read tokens | `token1,token2` | `app/security/auth.py` |
| `WRITE_TOKENS` | Comma-separated write tokens | `token1,token2` | `app/security/auth.py` |
| `DEV_BEARER` | Dev bearer token | `devtoken123` | `app/security/auth.py`, `app/db/__init__.py` |
| `PUBLIC_READ_ENABLED` | Enable public read allowlist | `1` | `app/security/auth.py` |
| `PUBLIC_READ_PATHS` | CSV allowlist of public GET paths | `/health,/v1/space/visuals` | `app/security/auth.py` |
| `AIRNOW_API_KEY` | AirNow API access key | `airnow-key` | `services/external/airnow.py` |
| `WEATHER_UA` | NWS user agent string | `(gaiaeyes.com, gaiaeyes7.83@gmail.com)` | `services/external/nws.py` |
| `GAIA_LOG_LEVEL` | Logging level for bots | `INFO` | `bots/local_health_poll.py` |
| `LOCAL_SIGNALS_TTL_MINUTES` | Local signals cache TTL | `60` | `services/local_signals/cache.py` |
| `LOCAL_SIGNALS_AIRNOW_RADIUS_MI` | AirNow search radius in miles | `25` | `services/external/airnow.py` |
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
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook signing secret | `whsec_...` | `app/api/webhooks.py` |
| `STRIPE_API_KEY` | Stripe secret key (server checkout) | `sk_live_...` | `app/routers/billing.py` |
| `CHECKOUT_SUCCESS_URL` | Stripe Checkout success redirect | `https://gaiaeyes.com/account?success=1` | `app/routers/billing.py` |
| `CHECKOUT_CANCEL_URL` | Stripe Checkout cancel redirect | `https://gaiaeyes.com/subscribe?canceled=1` | `app/routers/billing.py` |
| `STRIPE_PRICE_PLUS_MONTHLY` | Stripe price id for Plus monthly | `price_...` | `app/routers/billing.py` |
| `STRIPE_PRICE_PLUS_YEARLY` | Stripe price id for Plus yearly | `price_...` | `app/routers/billing.py` |
| `STRIPE_PRICE_PRO_MONTHLY` | Stripe price id for Pro monthly | `price_...` | `app/routers/billing.py` |
| `STRIPE_PRICE_PRO_YEARLY` | Stripe price id for Pro yearly | `price_...` | `app/routers/billing.py` |

## iOS (runtime/in-app)
| Variable | Purpose | Where set |
| --- | --- | --- |
| `API Base URL` | Backend base URL | In-app settings (stored in `UserDefaults`) |
| `Bearer Token` | Backend bearer token | In-app settings |
| `User UUID` | Supabase user id | In-app settings |
| `MEDIA_BASE_URL` | CDN fallback base URL | Process env (if set) |
| `SUPABASE_URL` | Supabase auth base | `Info.plist` |
| `SUPABASE_ANON_KEY` | Supabase anon key | `Info.plist` |
| `GAIA_API_BASE` | Backend base for billing flows | `Info.plist` |
| `GAIA_BILLING_PORTAL_URL` | Stripe customer portal (optional) | `Info.plist` |
| `GAIA_MAGICLINK_REDIRECT` | Magic link redirect URL (optional) | `Info.plist` |

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
| `GAIA_IOS_TEAM_ID` | Apple Team ID for AASA | `ABCDE12345` | `wp-content/mu-plugins/gaiaeyes-aasa.php` |
| `GAIA_IOS_BUNDLE_ID` | iOS bundle identifier for AASA | `com.gaiaexporter` | `wp-content/mu-plugins/gaiaeyes-aasa.php` |
| `SUPABASE_URL` | Supabase project URL (client auth) | `https://<project>.supabase.co` | `wp-content/mu-plugins/ge-checkout.php` |
| `SUPABASE_ANON_KEY` | Supabase anon key (client auth) | `anon-key` | `wp-content/mu-plugins/ge-checkout.php` |

## Render
Render-specific env vars are likely set in the dashboard (see `docs/OPEN_QUESTIONS.md`).
