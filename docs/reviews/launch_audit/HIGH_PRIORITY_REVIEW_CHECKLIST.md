# High-Priority Review Checklist

Use this as the launch-prep punch list.

## Guide

- [ ] Review Guide Hub helper cards and fallback guidance. Where: `gaiaeyes-ios/ios/GaiaExporter/Views/Guide/GuideHubView.swift`. Why: this is the top-level orientation surface and much of its copy is local to one view. Type: `copy`
- [ ] Review scientific vs mystical naming consistency across guide and home surfaces. Where: `gaiaeyes-ios/ios/GaiaExporter/Models/CopyVocabulary.swift`, `gaiaeyes-ios/ios/GaiaExporter/Views/ContentView.swift`, `GuideHubView.swift`. Why: inconsistent vocabulary will make the product feel less intentional. Type: `both`
- [ ] Review guide asset fallback behavior. Where: `GuideAssetResolver.swift`, guide asset catalog. Why: guide identity is part of the presentation layer and some paths still appear fallback-based. Type: `logic`

## Drivers

- [ ] Review the top driver ranking for a few real days. Where: `services/patterns/personal_relevance.py`, `services/drivers/all_drivers.py`, `app/routers/dashboard.py`. Why: the product's "what matters now" trust depends on this ranking. Type: `logic`
- [ ] Review driver short reason, personal reason, and science note for duplication. Where: `services/drivers/all_drivers.py`, `services/mc_modals/modal_builder.py`. Why: repeated explanations make the app feel robotic and overly certain. Type: `copy`
- [ ] Review the All Drivers wrappers and empty states. Where: `gaiaeyes-ios/ios/GaiaExporter/Views/AllDriversView.swift`. Why: screen-level framing affects how backend explanations land. Type: `copy`

## Symptoms

- [ ] Review active, improving, and resolved symptom messaging. Where: `app/db/symptoms.py`, `app/routers/symptoms.py`, `gaiaeyes-ios/ios/GaiaExporter/Views/CurrentSymptomsView.swift`. Why: symptom-state wording and gauge behavior are tightly linked. Type: `both`
- [ ] Review symptom severity handling and same-day gauge effects. Where: `bots/gauges/gauge_scorer.py`. Why: this can materially change current-state outputs. Type: `logic`
- [ ] Review note/journal placeholders, follow-up prompts, and context lines. Where: `CurrentSymptomsView.swift`, `DailyCheckInView.swift`, `GuideHubView.swift`. Why: this is repeated-use copy in a trust-sensitive flow. Type: `copy`

## Patterns

- [ ] Review evidence thresholds and confidence framing. Where: `bots/patterns/pattern_engine_job.py`, `app/routers/patterns.py`. Why: pattern language should feel grounded, not overstated. Type: `both`
- [ ] Review pattern wording across all surfaces on the same day. Where: `services/patterns/personal_relevance.py`, `ContentView.swift`, driver/detail surfaces. Why: the same pattern can currently echo through multiple layers. Type: `copy`

## EarthScope

- [ ] Verify public website EarthScope home banner no longer collapses to "API payload missing" when the API-backed payload is absent. Where: `wp-content/themes/neve/functions.php`, homepage shortcode config, `wp-content/mu-plugins/gaia-dashboard.js`. Why: push notices can route users to the website, and a broken top-of-page EarthScope card is a launch first-impression risk. Type: `logic`
- [ ] Review home EarthScope summary, full EarthScope, and social/share wording together. Where: `services/mc_modals/modal_builder.py`, `bots/earthscope_post/member_earthscope_generate.py`, `bots/earthscope_post/earthscope_generate.py`, `ShareCaptionEngine.swift`. Why: this is the highest-risk brand-voice layer. Type: `copy`
- [ ] Review iOS and WordPress EarthScope fallback behavior. Where: `gaiaeyes-ios/ios/GaiaExporter/Views/ContentView.swift`, `wp-content/mu-plugins/gaia-dashboard.js`. Why: fallback text can drift from backend-generated content. Type: `both`
- [ ] Review whether daily EarthScope and multi-day outlook feel like the same product voice. Where: `services/forecast_outlook.py`, `app/routers/outlook.py`, EarthScope writer files. Why: daily vs forecast split is a likely launch inconsistency. Type: `copy`

## Data Layers

- [ ] Review local weather thresholds and message snippets. Where: `services/local_signals/aggregator.py`, `services/external/nws.py`, `app/routers/local.py`. Why: pressure/temp framing affects both logic and user interpretation. Type: `both`
- [ ] Review AQI and allergen state wording. Where: `services/external/airnow.py`, `services/external/pollen.py`, `services/local_signals/aggregator.py`. Why: threshold categories should read consistently across app and web. Type: `both`
- [ ] Review Schumann state labels and threshold parity. Where: `gaiaeyes-ios/ios/GaiaExporter/Views/SchumannDashboardView.swift`, `wp-content/mu-plugins/gaiaeyes-schumann-dashboard.js`, `services/geomagnetic_context.py`. Why: this is a specialized logic island with parallel implementations. Type: `both`
- [ ] Review space-weather detail wording. Where: `app/routers/space_forecasts.py`, `services/forecast_outlook.py`, `wp-content/mu-plugins/gaiaeyes-space-weather-detail.php`. Why: app and web copy should not imply different certainty levels. Type: `copy`

## Paywall / Onboarding / Permissions

- [ ] Review onboarding permissions and alert wording. Where: `gaiaeyes-ios/ios/GaiaExporter/Views/OnboardingFlowView.swift`. Why: first-run tone and trust are set here. Type: `copy`
- [ ] Review HealthKit authorization and import status messaging. Where: `gaiaeyes-ios/ios/GaiaExporter/HealthKitManager.swift`, `Services/HealthKitBackgroundSync.swift`. Why: permission and import friction should read clearly. Type: `both`
- [ ] Review app and web plan descriptions side by side. Where: `gaiaeyes-ios/ios/GaiaExporter/Views/SubscribeView.swift`, `wp-content/mu-plugins/ge-checkout.php`. Why: plan positioning currently lives in two different copy sources. Type: `copy`
- [ ] Review checkout config and entitlement assumptions. Where: `app/routers/billing.py`, `gaiaeyes-ios/ios/GaiaExporter/Services/Billing/CheckoutService.swift`. Why: purchase logic is stable enough to audit now and safer to verify before launch. Type: `logic`
