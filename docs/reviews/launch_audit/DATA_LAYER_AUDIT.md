# Data Layer Audit

This file answers "what data powers what?" and "where is it surfaced?"

## Space Weather

Primary files:

- `app/routers/space_forecasts.py`
- `services/forecast_outlook.py`
- `app/routers/dashboard.py`
- `app/routers/summary.py`
- `wp-content/mu-plugins/gaiaeyes-space-weather-detail.php`
- `wp-content/mu-plugins/gaiaeyes-magnetosphere.php`
- `gaiaeyes-ios/ios/GaiaExporter/Views/ContentView.swift`

Source dependencies observed:

- daily space-weather marts and ext tables accessed through backend routes
- SWPC parsing inside `services/forecast_outlook.py`
- aurora, SEP, solar wind, CME, radiation-belt, and DRAP endpoints in `app/routers/space_forecasts.py`

User-facing screens:

- Home / Explore space-weather sections in iOS
- Outlook
- WordPress space-weather detail and magnetosphere pages
- EarthScope and related daily summaries

Copy points:

- route payload labels in `app/routers/space_forecasts.py`
- forecast interpretation in `services/forecast_outlook.py`
- view and plugin wrappers in app/web surfaces

Calculation / aggregation points:

- `services/forecast_outlook.py` for forecast severity and domain mapping
- database-backed aggregations exposed via `app/routers/space_forecasts.py`

Audit note:

- this layer is data-rich but copy-fragmented

Tags: `logic-threshold` `copy-generated` `launch-critical`

## Local Weather

Primary files:

- `app/routers/local.py`
- `services/local_signals/aggregator.py`
- `services/external/nws.py`
- `gaiaeyes-ios/ios/GaiaExporter/Views/ContentView.swift`
- `wp-content/mu-plugins/gaiaeyes-local-check.php`

Source dependencies observed:

- NWS `api.weather.gov`
- ZIP -> lat/lon lookup
- local cache for prior snapshots and delta calculations

User-facing screens:

- local conditions card(s) in app
- local conditions page in WordPress
- related influence in outlook and daily summaries

Temperature display / units:

- weather data is kept internally in Celsius in onboarding copy
- `services/forecast_outlook.py` and `services/external/nws.py` include temperature coercion/conversion logic
- unit preference messaging is surfaced in `OnboardingFlowView.swift`

Copy points:

- message snippets in `services/local_signals/aggregator.py`
- labels and wrappers in `ContentView.swift` and `gaiaeyes-local-check.php`

Calculation / aggregation points:

- 24h temperature and barometric deltas in `services/local_signals/aggregator.py`
- short-term trend classification in `services/local_signals/aggregator.py`
- observation + forecast fallback logic in `services/external/nws.py`

Tags: `logic-threshold` `copy-generated` `launch-critical`

## Air Quality / Allergens

Primary files:

- `services/external/airnow.py`
- `services/external/pollen.py`
- `services/local_signals/aggregator.py`
- app local conditions views
- `wp-content/mu-plugins/gaiaeyes-local-check.php`

Source dependencies observed:

- AirNow current observations by ZIP
- Google Pollen forecast by lat/lon

User-facing screens:

- local conditions app/web surfaces
- outlook / daily summaries when those signals are relevant

Copy points:

- AQI bucket naming in `services/local_signals/aggregator.py`
- pollen labels and state labels in `services/external/pollen.py`

Thresholds / visible states:

- AQI bucket thresholds: good, moderate, USG, unhealthy, very unhealthy, hazardous
- pollen levels normalized to low / moderate / high / very_high and displayed as quiet / moderate / elevated / high

Audit note:

- AQI/allergen wording is reasonably grounded, but still enters the UI through multiple wrappers

Tags: `logic-threshold` `copy-generated`

## Health / HealthKit

Primary files:

- `gaiaeyes-ios/ios/GaiaExporter/HealthKitManager.swift`
- `gaiaeyes-ios/ios/GaiaExporter/Services/HealthKitBackgroundSync.swift`
- `gaiaeyes-ios/ios/GaiaExporter/Services/HealthKitSleepExporter.swift`
- `gaiaeyes-ios/ios/GaiaExporter/Services/HealthKitVitalsExporter.swift`
- `gaiaeyes-ios/ios/GaiaExporter/Services/HealthKitVitalsExporter+Sync.swift`
- `gaiaeyes-ios/ios/GaiaExporter/Views/OnboardingFlowView.swift`
- `docs/app-overview.md`
- `docs/ARCHITECTURE.md`

Ingestion points:

- HealthKit authorization request in `HealthKitManager.swift`
- background observers, backfill, and uploads in `HealthKitBackgroundSync.swift`
- sleep and vitals exporters in dedicated exporter files

Background delivery points:

- `HealthKitBackgroundSync.shared.registerBGTask()`
- `registerProcessingTask()`
- `scheduleRefresh()`
- `scheduleProcessing()`
- observer registration path documented in `docs/app-overview.md`

Copy surfaces:

- onboarding health-permission explanations in `OnboardingFlowView.swift`
- import status / backfill messages in `HealthKitBackgroundSync.swift`
- Settings and debug controls in app shell

Permissions text locations:

- `gaiaeyes-ios/ios/GaiaExporter/Views/OnboardingFlowView.swift`
- `gaiaeyes-ios/ios/GaiaExporter/HealthKitManager.swift` is more logic than explanatory copy

Sleep / HRV / heart-rate use in app logic:

- background sync feeds backend data
- downstream patterns, drivers, and gauges use health context indirectly through ranked relevance and gauge scoring paths

Audit note:

- ingestion seems technically clear; the main cleanup issue is making permission/import wording easier to maintain

Tags: `logic-weighting` `copy-hardcoded` `launch-critical`

## Sleep / HRV / Body Signals

Primary files:

- `gaiaeyes-ios/ios/GaiaExporter/Services/HealthKitBackgroundSync.swift`
- exporter files under `gaiaeyes-ios/ios/GaiaExporter/Services/`
- `bots/gauges/gauge_scorer.py`
- `services/patterns/personal_relevance.py`
- `services/forecast_outlook.py`

What they power:

- sleep and recovery-related gauges
- pattern relevance
- body-state interpretation
- daily and forecast narrative emphasis

Audit note:

- this is not a separate copy layer; it is a hidden logic input layer that strongly affects visible ranking

Tags: `logic-weighting` `launch-critical`

## Schumann / ULF / Related Signal Sources

Primary files:

- `gaiaeyes-ios/ios/GaiaExporter/Views/SchumannDashboardView.swift`
- `services/geomagnetic_context.py`
- `wp-content/mu-plugins/gaiaeyes-schumann-dashboard.php`
- `wp-content/mu-plugins/gaiaeyes-schumann-dashboard.js`
- `wp-content/mu-plugins/gaiaeyes-schumann-detail.php`
- `docs/SCHUMANN_UI.md`
- `docs/SCHUMANN_UX_MERGED.md`

How it is surfaced:

- dedicated Schumann page in iOS
- dedicated Schumann dashboard/detail pages in WordPress
- related signal use inside broader daily context

How it is described:

- Schumann has its own "how to read this" help text and band-label system
- ULF context labels are normalized in backend (`Quiet`, `Active`, `Elevated`, `Strong` mapped/cleaned in `services/geomagnetic_context.py`)

Where thresholds appear to be defined:

- iOS `SchumannDashboardView.swift` via `SchumannTuning`
- mirrored WP JS `STATE_LEVELS`
- ULF confidence labels in `services/geomagnetic_context.py`

Audit note:

- wording here can feel exploratory, but it is relatively specialized and self-contained
- the main risk is inconsistency between app and web tuning, not just tone

Tags: `logic-threshold` `copy-hardcoded` `launch-critical`

## Community / Research / About Pages

Primary files:

- `gaiaeyes-ios/ios/GaiaExporter/Models/UnderstandingGaiaEyesContent.swift`
- `gaiaeyes-ios/ios/GaiaExporter/Views/Guide/UnderstandingGaiaEyesView.swift`
- `docs/IOS_NAVIGATION_SHELL.md`

How it is surfaced:

- Guide Hub
- Insights / Understanding Gaia Eyes card
- Settings -> About Gaia Eyes path

Audit note:

- this is one of the cleanest current content layers and should probably become the reference style for trust-sensitive wording elsewhere

Tags: `copy-centralized` `safe-for-later`

## Membership / Subscription Layer

Primary files:

- `gaiaeyes-ios/ios/GaiaExporter/Views/SubscribeView.swift`
- `gaiaeyes-ios/ios/GaiaExporter/Views/Auth/LoginView.swift`
- `gaiaeyes-ios/ios/GaiaExporter/Services/Billing/CheckoutService.swift`
- `app/routers/billing.py`
- `wp-content/mu-plugins/ge-checkout.php`
- `wp-content/mu-plugins/ge-checkout.js`
- `wp-content/mu-plugins/gaia-subscriptions.php`

What it powers:

- account status and plan display in app
- Stripe checkout launch in app and web
- plan descriptions and CTA text

Audit note:

- product language for plans is duplicated between app and WordPress
- backend billing route is structurally clean, but the plan-positioning language is not centralized

Tags: `copy-hardcoded` `safe-for-later`
