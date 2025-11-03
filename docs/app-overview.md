🌍 Gaia Eyes App Overview

🧩 Architecture
	•	Frontend: SwiftUI iOS app (GaiaExporter)
	•	Uses modular Views (Sleep, Health, Space Weather, Weekly Trends, Earthscope, Tools).
	•	Integrates with Apple HealthKit and the Polar H10 BLE sensor.
	•	Fetches external geomagnetic and space-weather data via REST endpoints hosted on Render.
	•	Backend: Python/FastAPI (gaiaeyes-backend)
	•	Hosted on Render (https://gaiaeyes-backend.onrender.com).
	•	Aggregates live feeds from NOAA SWPC, Tomsk Schumann, and other scientific APIs.
	•	Exposes routes:
	•	/v1/features/today → combined health/space/weather snapshot.
	•	/v1/space/series → 30-day trends (Kp, Bz, SW, Schumann, HRV).
	•	/v1/space/forecast/summary → 3-day human-readable forecast.
	•	Writes JSONs (e.g., earthscope_daily.json, flares_cmes.json) to gaiaeyes-media/data and publishes to jsDelivr CDN for app + web use.
	•	Media Repo: gaiaeyes-media
	•	Stores static backgrounds, daily charts, and “Earthscope” composite images.
	•	Automatically updated by GitHub Actions every ~15 mins.

⸻

📱 Core App Features

1. Features Today Card
	•	Displays Sleep, HRV, HR, SpO₂, BP, Schumann, Kp, Bz, Solar Wind.
	•	Data source: /v1/features/today.
	•	Fallbacks:
	•	Retries twice on failure (1s apart).
	•	Falls back to last-known and persisted cache.
	•	Now keeps lastKnownFeatures even when the server sends nulls.
	•	Prevents “blank card” flickers via guard logic in ContentView.swift.

2. Weekly Trends
	•	Visualizes 30 days of space and HRV data (sparklines for Kp, Bz, Schumann f0, HR).
	•	Data source: /v1/space/series.
	•	Added series cache (@AppStorage("series_cache_json")) and fallback logic.
	•	Empty responses no longer overwrite existing charts.

3. Earthscope Daily Card
	•	Uses daily earthscope_daily.json for title, summary, and image quartet:
	•	daily_caption.jpg
	•	daily_stats.jpg
	•	daily_affects.jpg
	•	daily_playbook.jpg
	•	Background pulled from gaiaeyes-media/backgrounds/square.
	•	Fixed layout alignment, dark overlay, and margin bleeding.
	•	Card supports deep tap → opens full Earthscope view.

4. Space Alerts Card
	•	Uses flare_alert, kp_alert flags.
	•	Fixed missing SF Symbol by replacing "bolt.triangle.fill" → "bolt.triangle" (universal symbol).

5. Sleep / Health Stats / Space Weather Cards
	•	Now resilient to null feature payloads:
	•	features ?? lastKnownFeatures ensures continuity.
	•	Cards never drop out on refresh.
	•	Sleep data aggregated by day; HRV and HR synced via HealthKitBackgroundSync.

6. Background Ingestion
	•	Implemented in HealthKitBackgroundSync.swift.
	•	Uses:
	•	HKObserverQuery for HR, HRV, SpO₂, BP, Sleep, Steps.
	•	Anchored queries with persisted anchors for efficient deltas.
	•	BGAppRefreshTask (every 30 min) and BGProcessingTask (every 2 hr).
	•	Logging shows [HK] bg delivery <metric>: enabled for each type.
	•	Added AppDelegate-equivalent setup in GaiaExporterApp.swift:

HealthKitBackgroundSync.shared.registerBGTask()
HealthKitBackgroundSync.shared.registerProcessingTask()
HealthKitBackgroundSync.shared.scheduleRefresh()
HealthKitBackgroundSync.shared.scheduleProcessing()
try? HealthKitBackgroundSync.shared.registerObservers()

	•	Tasks now run even after reboot, ensuring daily ingestion + uploads.

⸻

⚙️ Backend Improvements
	•	/v1/space/series: Added fallback caching, now tolerant to empty API windows.
	•	/v1/features/today: Rebalanced retries and diagnostics logging.
	•	/summary.py: Updated media URLs for CDN consistency (single @main).
	•	/main.py: Health route simplified and diagnostics added.
	•	Render deployment fixed after moving repos under GaiaEyesHQ.

Caching + Fallback Summary
Data Type
Source
Fallback
Cache
Features
/v1/features/today
Last-known + persisted snapshot
@AppStorage("features_cache_json")
Series
/v1/space/series
Last-known + persisted
@AppStorage("series_cache_json")
Earthscope
CDN JSON/images
N/A
via jsDelivr
HealthKit
Local HKAnchors
Persistent via UserDefaults

🧠 Intelligence Layer (Codex)
	•	Codex linked to GitHub repos for continuous auditing.
	•	Can read all code under:
	•	gaiaeyes-backend
	•	gaiaeyes-media
	•	gaiaeyes-ios
	•	Tasks created:
	•	Audit workflow reliability
	•	Inspect failed pushes (rebase + retry logic)
	•	Generate complete website docs
	•	Next up: Crawl staging website and produce SITE_OVERVIEW.md (with spark chart hardening, axis headers, and asset inventory).

⸻

🧮 Upcoming Enhancements
	1.	Spark Chart Hardening
	•	Add axes, labels, and consistent scaling.
	•	Shared helper function:
renderSpark(data, { xLabel, yLabel, units, color })
	2.	Feature Caching Expansion
	•	Store both today + yesterday snapshots to detect staleness.
	3.	Nightly Asset Validation
	•	New GitHub workflow: HEAD-checks all CDN and NOAA assets nightly.
	4.	Silent Push Triggers
	•	Plan to wake app when backend posts a new daily Earthscope.
	5.	Web Docs PR
	•	Codex crawl of staging2.gaiaeyes.com → build full guide (SITE_OVERVIEW.md) for all detail pages.

⸻

✅ State of the App
	•	All core cards render stably.
	•	Background ingestion confirmed via logs.
	•	Charts cached locally and reloaded on boot.
	•	Earthscope visuals aligned and readable.
	•	Render + GitHub Actions working after organization migration.
	•	Only transient flicker left: backend null windows (handled by fallbacks).
