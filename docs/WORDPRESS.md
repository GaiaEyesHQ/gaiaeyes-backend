# WordPress (wp-content)

## Structure
- `wp-content/mu-plugins/` contains most Gaia Eyes data-fetching shortcodes and UI blocks.
- `wp-content/themes/neve/` includes theme overrides and additional shortcodes.

## Data access strategy
- Primary mode: fetch backend APIs when `GAIAEYES_API_BASE` is configured.
- Fallback mode: fetch JSON snapshots from `gaiaeyes-media` (GitHub Pages/jsDelivr) or NOAA endpoints.

## Key mu-plugins + shortcodes
- **Checkout (signed-in Stripe)** (`ge-checkout.php` + `ge-checkout.js`): shortcode `[ge_checkout plan="plus"]` or `[ge_checkout plan="pro"]` renders monthly + yearly buttons using plan keys (backend expects plan keys, not Stripe price IDs). You can also use a single plan key like `plan="plus_monthly"`.
- **Pricing table (legacy backup)** (`gaia-subscriptions.php`): shortcode `[ge_pricing_table]` for Stripe’s hosted pricing table (kept as fallback).
- **AASA (Universal Links)** (`gaiaeyes-aasa.php`): serves Apple App Site Association JSON at `/.well-known/apple-app-site-association` and `/apple-app-site-association`.
- **Space visuals** (`gaiaeyes-space-visuals.php`): uses backend API when configured, else `space_live.json`.
- **Space weather detail** (`gaiaeyes-space-weather-detail.php`): API-first (features + forecast + history + flares), falls back to `space_weather.json` + `flares_cmes.json`.
- **Magnetosphere card** (`gaiaeyes-magnetosphere.php`): API-first (`/v1/space/magnetosphere`), fallback `magnetosphere_latest.json`.
- **Schumann detail** (`gaiaeyes-schumann-detail.php`): JSON-only (`schumann_latest.json`, `schumann_combined.json`).
- **Quakes detail** (`gaiaeyes-earthquake-detail.php`): API-first (`/v1/quakes/*`).
- **News** (`gaiaeyes-news.php`): JSON-only (`news_latest.json`).
- **Compare detail** (`gaiaeyes-compare-detail.php`): JSON-only (`compare_series.json`, `quakes_history.json`, `space_history.json`).

## Theme shortcodes (Neve)
- `gaia_space_weather_bar`: JSON + API fallback (space weather + flares).
- `gaia_earthscope_banner`: JSON-only (`earthscope_daily.json`, `earthscope.json`).
- `gaia_pulse` + `gaia_pulse_detail`: JSON-only (`pulse.json`).
- `gaia_alert_banner`: JSON-only (`space_weather.json`, `quakes_latest.json`).

## JSON datasets still in use (and endpoint parity)
| JSON dataset | Used in WP | Backend endpoint exists? | Notes |
| --- | --- | --- | --- |
| `space_live.json` | Space visuals | **Yes** (`/v1/space/visuals`) | API preferred; JSON fallback remains. |
| `space_weather.json` | Space weather bar/detail, alert banner | **Partial** | API uses `/v1/space/forecast/*` + `/v1/space/history` + `/v1/features/today`; no 1:1 replacement. |
| `flares_cmes.json` | Space weather bar/detail | **Partial** | `/v1/space/flares` + forecast outlook; no direct CMEs JSON equivalent. |
| `magnetosphere_latest.json` | Magnetosphere card | **Yes** (`/v1/space/magnetosphere`) | API preferred. |
| `schumann_latest.json` | Schumann detail | **Partial** | `/v1/earth/schumann/latest` exists but shape differs. |
| `schumann_combined.json` | Schumann detail | **No** | Combined dataset only exists as JSON. |
| `quakes_latest.json` | Alert banner | **Yes** (`/v1/quakes/latest`) | Banner still uses JSON. |
| `quakes_history.json` | Compare detail | **Yes** (`/v1/quakes/history`) | Compare still uses JSON. |
| `space_history.json` | Compare detail | **Partial** | `/v1/space/history` exists; compare dataset still JSON. |
| `compare_series.json` | Compare detail | **No** | JSON-only. |
| `earthscope_daily.json` | Earthscope banner | **No** | JSON-only. |
| `earthscope.json` | Earthscope banner | **No** | JSON-only. |
| `pulse.json` | Pulse cards | **No** | JSON-only. |
| `news_latest.json` | News | **No** | JSON-only. |

## Environment variables (WP)
See `docs/ENVIRONMENT_VARIABLES.md` for required env vars like `GAIAEYES_API_BASE`, `GAIAEYES_API_BEARER`, `GAIA_MEDIA_BASE`, and space visuals overrides.
The signed-in checkout flow also requires `SUPABASE_URL` + `SUPABASE_ANON_KEY` for Supabase auth on the Subscribe page.
Universal links require `GAIA_IOS_TEAM_ID` + `GAIA_IOS_BUNDLE_ID` so the AASA file matches the iOS app.
