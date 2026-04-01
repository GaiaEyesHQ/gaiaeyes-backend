# Logic Map By Layer

This file maps where key product logic appears to live. It is a pointer map, not a rewrite.

## Guide Layer

- Experience mode, guide choice, and tone selection live in `gaiaeyes-ios/ios/GaiaExporter/Models/UserExperienceProfile.swift`.
- Scientific vs mystical label switching and copy post-processing live in `gaiaeyes-ios/ios/GaiaExporter/Models/CopyVocabulary.swift`.
- Guide asset routing and fallbacks live in `gaiaeyes-ios/ios/GaiaExporter/Views/Guide/GuideAssetResolver.swift`.
- Guide Hub presentation logic lives in `gaiaeyes-ios/ios/GaiaExporter/Views/Guide/GuideHubView.swift`.

What to inspect:

- whether all guide-facing surfaces are actually using shared mode/tone vocabulary
- whether dog/robot guide paths are fully real or still effectively cat fallbacks

Tags: `logic-fallback` `safe-for-later`

## Drivers Layer

- Driver ranking and personal weighting live primarily in `services/patterns/personal_relevance.py`.
- Driver payload composition for the All Drivers surface lives in `services/drivers/all_drivers.py`.
- Dashboard driver assembly and client payload exposure live in `app/routers/dashboard.py`.
- Driver modal explanations and explanation-bullet deduping live in `services/mc_modals/modal_builder.py`.
- Signal-bar derived labels and modal support live in `services/signal_bar.py`.

Key heuristics / config touchpoints:

- personal weighting and override logic in `services/patterns/personal_relevance.py`
- setup-hint routing in `services/drivers/all_drivers.py`
- leading vs supporting driver presentation in `app/routers/dashboard.py`

Backend dependency points:

- `/v1/dashboard`
- `/v1/drivers`

Tags: `logic-weighting` `launch-critical`

## Symptoms Layer

- Symptom event persistence, current episode state, and timeline retrieval live in `app/db/symptoms.py`.
- Symptom API shaping, current symptom payloads, and follow-up-related fields live in `app/routers/symptoms.py`.
- Same-day symptom effects on gauges live in `bots/gauges/gauge_scorer.py`.

Key weighting sources in `bots/gauges/gauge_scorer.py`:

- `_SYMPTOM_GAUGE_EFFECTS`
- gauge caps per domain
- severity tiers
- recency multipliers
- state multipliers for active/improving/resolved episodes
- cluster bonus / health-status contribution

Key product implication:

- symptom logs are not just stored history; they can immediately alter current gauges and daily interpretation

Backend dependency points:

- `/v1/symptoms`
- current-episode update routes under `/v1/symptoms/current/...`

Tags: `logic-weighting` `launch-critical`

## Patterns Layer

- Canonical pattern derivation lives in `bots/patterns/pattern_engine_job.py`.
- Pattern narrative and anchor selection live in `services/patterns/personal_relevance.py`.
- Pattern API exposure and explanation text live in `app/routers/patterns.py`.

Important threshold / evidence gates in `bots/patterns/pattern_engine_job.py`:

- exposed sample minimum: `exposed_n >= 6`
- unexposed sample minimum: `unexposed_n >= 6`
- exposed outcome minimum: `exposed_outcome_n >= 3`
- relative lift minimum: `>= 1.4`
- absolute rate difference minimum: `>= 0.10`
- lags checked: `0h`, `12h`, `24h`, `48h`

Important exposure thresholds observed:

- pressure swing: `abs >= 6 hPa`
- temperature swing: `abs >= 6 C`
- AQI moderate plus: `>= 50`
- AQI unhealthy plus: `>= 100`
- geomagnetic Kp G1 plus: `>= 5`
- southward Bz: `<= -8`
- solar wind: `>= 550`
- Schumann exposure: rolling station percentile logic

Backend dependency points:

- `/v1/patterns`
- pattern references consumed again by dashboard and outlook logic

Tags: `logic-threshold` `logic-weighting` `launch-critical`

## Gauge Layer

- Base gauge definitions, zone labels, alert thresholds, writer outputs, and signal-to-gauge mappings live in `bots/definitions/gauge_logic_base_v1.json`.
- Zone label resolution lives in `services/gauges/zones.py`.
- Live signal scoring and threshold application live in `bots/gauges/signal_resolver.py`.
- Final scoring adjustments, symptom boosts, recovery effects, and domain combination logic live in `bots/gauges/gauge_scorer.py`.
- Signal bar presentation support lives in `services/signal_bar.py`.

Observed gauge domains:

- `pain`
- `focus`
- `heart`
- `stamina`
- `energy`
- `sleep`
- `mood`

Important note:

- user-facing review should treat `sleep` plus recovery-like health-status messaging together, because both influence the perceived "recovery" story even when the underlying gauge keys differ

Tags: `logic-threshold` `logic-weighting` `launch-critical`

## EarthScope Layer

- Home EarthScope summary construction lives in `services/mc_modals/modal_builder.py` via the daily summary builder.
- Member EarthScope longform generation lives in `bots/earthscope_post/member_earthscope_generate.py`.
- Public/social EarthScope generation lives in `bots/earthscope_post/earthscope_generate.py`.
- Feature exposure for `post_title`, `post_caption`, `post_body`, and related media metadata lives in `app/routers/summary.py`.
- Dashboard exposure of EarthScope summary/member/public posts lives in `app/routers/dashboard.py`.
- iOS parsing, cleanup, default-title handling, and fallback display logic live in `gaiaeyes-ios/ios/GaiaExporter/Views/ContentView.swift`.
- WordPress parsing and fallback presentation live in `wp-content/mu-plugins/gaia-dashboard.js`.

Config / heuristic / fallback touchpoints:

- deterministic sentence rotation in member/public EarthScope writers
- fallback section parsing in iOS and WordPress
- separate share caption tone system in `gaiaeyes-ios/ios/GaiaExporter/Services/ShareCaptionEngine.swift`

Risk:

- EarthScope logic and EarthScope wording are intertwined in several files, so copy cleanup and logic cleanup cannot be fully separated later

Tags: `copy-generated` `logic-fallback` `repetitive-risk` `robotic-risk` `launch-critical`

## Forecast Layer

- User outlook assembly lives in `services/forecast_outlook.py`.
- Authenticated user outlook route lives in `app/routers/outlook.py`.
- Space forecast and overview endpoints live in `app/routers/space_forecasts.py`.

Key forecast logic sources in `services/forecast_outlook.py`:

- domain mapping: outcome -> domain -> gauge
- driver ordering and severity weighting
- pollen forecast inclusion
- SWPC parsing for geomagnetic and space-weather forecast interpretation
- local forecast refresh windows

Likely review points:

- consistency between EarthScope daily language and outlook multi-day language
- severity labels for local pressure/temp/AQI/allergens vs space-driver labels

Tags: `logic-threshold` `logic-weighting` `launch-critical`

## Local Weather / AQI / Allergen Layer

- `/v1/local/check` is exposed by `app/routers/local.py`.
- Local snapshot assembly lives in `services/local_signals/aggregator.py`.
- NWS fetch and observation/gridpoint normalization live in `services/external/nws.py`.
- AirNow fetch lives in `services/external/airnow.py`.
- Google Pollen normalization and state labels live in `services/external/pollen.py`.

Observed thresholds / heuristics:

- short-term trend tolerance: about `1.5` for pressure and temperature trend classification
- rapid pressure drop message threshold: `<= -3.0 hPa` over short window
- big temperature shift threshold: `>= 8.0 C` over 24h
- AQI buckets: good / moderate / usg / unhealthy / very_unhealthy / hazardous
- pollen state labels: quiet / moderate / elevated / high

Tags: `logic-threshold` `launch-critical`

## Schumann / ULF / Geomagnetic Context

- ULF context label normalization and confidence labeling live in `services/geomagnetic_context.py`.
- iOS Schumann state presentation and helper copy live in `gaiaeyes-ios/ios/GaiaExporter/Views/SchumannDashboardView.swift`.
- WordPress Schumann state presentation mirrors that logic in `wp-content/mu-plugins/gaiaeyes-schumann-dashboard.js`.

Important note:

- `docs/SCHUMANN_UI.md` explicitly describes Schumann thresholds as centralized in the iOS view (`SchumannTuning`) and mirrored in WP JS (`STATE_LEVELS`), not backend-defined

That means Schumann state wording and Schumann thresholds are currently a UI-owned logic island.

Tags: `logic-threshold` `launch-critical`

## Health / HealthKit Layer

- Initial authorization request flow lives in `gaiaeyes-ios/ios/GaiaExporter/HealthKitManager.swift`.
- Background delivery, observer registration, import/backfill state, and refresh triggers live in `gaiaeyes-ios/ios/GaiaExporter/Services/HealthKitBackgroundSync.swift`.
- Sleep and vitals export helpers live in:
  - `gaiaeyes-ios/ios/GaiaExporter/Services/HealthKitSleepExporter.swift`
  - `gaiaeyes-ios/ios/GaiaExporter/Services/HealthKitVitalsExporter.swift`
  - `gaiaeyes-ios/ios/GaiaExporter/Services/HealthKitVitalsExporter+Sync.swift`

Key product implication:

- health ingestion is not only a background sync concern; it also changes pattern relevance and driver ranking downstream

Tags: `logic-weighting` `launch-critical`

## Billing / Membership Layer

- Billing API and Stripe checkout creation live in `app/routers/billing.py`.
- iOS checkout orchestration lives in `gaiaeyes-ios/ios/GaiaExporter/Services/Billing/CheckoutService.swift`.
- iOS membership surface lives in `gaiaeyes-ios/ios/GaiaExporter/Views/SubscribeView.swift`.
- WordPress checkout and pricing blocks live in `wp-content/mu-plugins/ge-checkout.php`.

Config touchpoints:

- `PRICE_MAP` and Stripe env vars in `app/routers/billing.py`
- success/cancel URLs in backend env config
- app `GAIA_API_BASE` and billing portal URL in Info.plist-backed settings

Tags: `logic-fallback` `safe-for-later`
