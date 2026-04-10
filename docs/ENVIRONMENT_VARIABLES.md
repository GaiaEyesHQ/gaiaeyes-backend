# Environment Variables

> **Do not commit real secrets.** Use placeholders and rotate any leaked tokens.

## Backend (FastAPI)
| Variable | Purpose | Example placeholder | Where used |
| --- | --- | --- | --- |
| `DATABASE_URL` | Supabase Postgres connection | `postgresql://postgres:***@db.<project>.supabase.co:5432/postgres` | `app/db/__init__.py` |
| `DIRECT_URL` | Optional direct Postgres fallback | `postgresql://postgres:***@db.<project>.supabase.co:5432/postgres` | `app/db/__init__.py` |
| `SUPABASE_DB_URL` | Supabase pooled Postgres connection (scripts/bots) | `postgresql://postgres:***@db.<project>.supabase.co:6543/postgres` | `services/db.py` |
| `SUPABASE_JWT_SECRET` | Validate Supabase JWTs | `supabase-jwt-secret` | `app/utils/auth.py` |
| `SUPABASE_URL` | Supabase REST/Auth/Storage base URL | `https://<project>.supabase.co` | `app/utils/supabase_storage.py`, `app/routers/profile.py` |
| `SUPABASE_SERVICE_ROLE_KEY` | Preferred service-role key for storage uploads and authenticated account deletion | `service-role-key` | `app/utils/supabase_storage.py`, `app/routers/profile.py` |
| `SUPABASE_SERVICE_KEY` | Legacy service-key alias accepted by account-deletion preflight/delete and some scripts | `service-key` | `app/routers/profile.py`, various scripts |
| `BUG_REPORT_ALERT_WEBHOOK_URL` | Optional webhook notified when a new in-app bug report is submitted | `https://hooks.example.com/...` | `app/routers/profile.py` |
| `BUCKET` | Storage bucket name | `space-visuals` | `app/utils/supabase_storage.py` |
| `READ_TOKENS` | Comma-separated read tokens | `token1,token2` | `app/security/auth.py` |
| `WRITE_TOKENS` | Comma-separated write tokens | `token1,token2` | `app/security/auth.py` |
| `DEV_BEARER` | Dev bearer token | `devtoken123` | `app/security/auth.py`, `app/db/__init__.py` |
| `PUBLIC_READ_ENABLED` | Enable public read allowlist | `1` | `app/security/auth.py` |
| `PUBLIC_READ_PATHS` | CSV allowlist additions for public GET paths; built-in defaults remain public | `/health,/v1/space/visuals` | `app/security/auth.py` |
| `AIRNOW_API_KEY` | AirNow API access key | `airnow-key` | `services/external/airnow.py` |
| `GOOGLE_POLLEN_API_KEY` | Google Pollen API key for current + 3-day allergen context | `google-pollen-key` | `services/external/pollen.py` |
| `WEATHER_UA` | NWS user agent string | `(gaiaeyes.com, help@gaiaeyes.com)` | `services/external/nws.py` |
| `GAIA_LOG_LEVEL` | Logging level for bots | `INFO` | `bots/local_health_poll.py` |
| `LOCAL_SIGNALS_TTL_MINUTES` | Local signals cache TTL | `60` | `services/local_signals/cache.py` |
| `LOCAL_SIGNALS_AIRNOW_RADIUS_MI` | AirNow search radius in miles | `25` | `services/external/airnow.py` |
| `CORS_ORIGINS` | CORS origin list | `*` | `app/db/__init__.py` |
| `REDIS_URL` | Optional caching/queues | `redis://...` | `app/db/__init__.py` |
| `FEATURES_CACHE_TTL_SECONDS` | Features cache TTL | `300` | `app/db/__init__.py` |
| `SCHUMANN_FUSE_TOMSK` | Enable Tomsk display fusion in Schumann latest/dashboard payloads | `true` | `app/db/__init__.py`, `app/routers/earth.py` |
| `SCHUMANN_TOMSK_MIN_QUALITY_SCORE` | Minimum Tomsk quality score required for fusion | `0.55` | `app/db/__init__.py`, `app/routers/schumann_tomsk_params.py` |
| `MEDIA_BASE_URL` | Default CDN base for visuals | `https://.../gaiaeyes-media` | `app/routers/summary.py` |
| `GAIA_MEDIA_BASE` | Alternate CDN base | `https://.../gaiaeyes-media` | `app/routers/summary.py` |
| `VISUALS_MEDIA_BASE_URL` | Visuals-specific CDN base | `https://.../gaiaeyes-media` | `app/routers/space_visuals.py` |
| `GOES_XRS_URL` | Space flares data source | `https://services.swpc.noaa.gov/...` | `app/routers/space.py` |
| `ULF_STATIONS` | CSV list of USGS observatories used for derived ULF context | `BOU,CMO` | `bots/geomag_ulf/ingest_ulf.py` |
| `ULF_FETCH_MINUTES` | Trailing minute window fetched from USGS on each ULF run | `180` | `bots/geomag_ulf/ingest_ulf.py` |
| `ULF_WINDOW_SECONDS` | Derived ULF bucket size in seconds | `300` | `bots/geomag_ulf/ingest_ulf.py` |
| `ULF_CONTEXT_MODE` | Reserved ULF aggregation mode flag | `context` | `bots/geomag_ulf/ingest_ulf.py` |
| `ULF_ENABLE_LOCALTIME_PERCENTILE` | Enable optional hour-bucket ULF percentile normalization | `false` | `bots/geomag_ulf/ingest_ulf.py` |
| `ULF_MIN_HISTORY_ROWS` | Minimum prior rows before station percentile normalization is emitted | `72` | `bots/geomag_ulf/ingest_ulf.py` |
| `ULF_BOOTSTRAP_MIN_ROWS` | Minimum rows needed for the sparse-history bootstrap percentile fallback | `12` | `bots/geomag_ulf/ingest_ulf.py` |
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
| `APNS_TEAM_ID` | Apple Developer Team ID for APNs auth | `ABCDE12345` | `bots/notifications/send_push_notifications.py` |
| `APNS_KEY_ID` | APNs auth key id (`.p8`) | `1A2BC3D4E5` | `bots/notifications/send_push_notifications.py` |
| `APNS_BUNDLE_ID` | iOS app bundle id / APNs topic (intentionally unchanged during the Gaia Eyes rename) | `com.gaiaeyes.GaiaExporter` | `bots/notifications/send_push_notifications.py` |
| `APNS_PRIVATE_KEY` | APNs auth key PEM contents | `-----BEGIN PRIVATE KEY-----...` | `bots/notifications/send_push_notifications.py` |

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

## EarthScope Meta posting (GitHub Actions / bots)
| Variable | Purpose | Example placeholder | Where used |
| --- | --- | --- | --- |
| `FB_ACCESS_TOKEN` | Facebook Page access token for Graph publish calls | `EAAB...` | `.github/workflows/gaia_eyes_daily.yml`, `bots/earthscope_post/meta_poster.py` |
| `FB_PAGE_ID` | Facebook Page id for photo/feed/video publishing | `1234567890` | `.github/workflows/gaia_eyes_daily.yml`, `bots/earthscope_post/meta_poster.py` |
| `IG_USER_ID` | Instagram professional account id | `1784...` | `.github/workflows/gaia_eyes_daily.yml`, `bots/earthscope_post/meta_poster.py` |
| `META_GRAPH_VERSION` | Shared Graph API version for EarthScope posting | `v24.0` | `.github/workflows/gaia_eyes_daily.yml`, `bots/earthscope_post/meta_poster.py` |
| `META_CREATE_RETRY_ATTEMPTS` | Retries for Meta create/stage calls | `4` | `bots/earthscope_post/meta_poster.py` |
| `META_PUBLISH_RETRY_ATTEMPTS` | Retries for Meta publish calls on explicit transient responses | `2` | `bots/earthscope_post/meta_poster.py` |
| `META_POLL_TIMEOUT_SEC` | Maximum IG container processing window | `300` | `bots/earthscope_post/meta_poster.py` |
| `META_POLL_INTERVAL_SEC` | Initial delay between IG status polls | `15` | `bots/earthscope_post/meta_poster.py` |
| `META_POLL_MAX_INTERVAL_SEC` | Maximum delay between IG status polls | `60` | `bots/earthscope_post/meta_poster.py` |
| `IG_CAROUSEL_CHILD_PACING_SEC` | Delay between IG carousel child container creates | `1.5` | `bots/earthscope_post/meta_poster.py` |
| `IG_CAROUSEL_SINGLE_IMAGE_FALLBACK` | Allow IG carousel downgrade to a single-image post after retries fail | `true` | `bots/earthscope_post/meta_poster.py` |
| `IG_REEL_CREATE_CYCLES` | Number of full reel container recreate cycles before giving up | `2` | `bots/earthscope_post/meta_poster.py` |
