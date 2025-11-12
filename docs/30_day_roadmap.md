# Gaia Eyes 30-Day Launch Plan (Web + App)

## Objectives
- Deliver interactive, data-rich dashboards on web and iOS that rival SpaceWeatherLive/SolarHam while expressing the Gaia Eyes health-centric voice.
- Complete ingestion coverage for predictive space-weather datasets (WSA–Enlil, SEP/radiation metrics, auroral power, etc.) so insights are backed by the database for app, web, and automation.
- Prepare the iOS app for external TestFlight testing with a feedback loop and automation for social growth.
- Establish revenue pathways beyond the mobile subscription that can be phased in after testing.

---

## Workstreams & Tasks

### 1. Predictive Data Coverage Expansion
Close ingestion gaps so Supabase becomes the single source for all predictive feeds competitors surface.

**Implementation Tasks**
1. **WSA–Enlil propagation**  
   a. Extend `ingest_nasa_donki.py` (or ship `ingest_enlil_forecast.py`) to call the DONKI `WSAEnlilSimulations` endpoint.  
   b. Persist arrival predictions, shock speeds, and modeled Kp ranges into `ext.enlil_forecast` with a mart `marts.cme_arrivals`.  
   c. Expose the summarized forecasts via `/v1/space/forecast/outlook` for dashboards, app, and bot use.
2. **Solar energetic particle & radiation storms**  
   a. Create an ingestion job for GOES proton flux (1-day & 7-day JSON) and SWPC S-scale alerts.  
   b. Store results inside `ext.sep_flux` with derived columns for S-level thresholds.  
   c. Add Supabase triggers or workers to raise notifications for Earthscope automation when thresholds are exceeded.
3. **Relativistic electron flux / radiation belts**  
   a. Pull GOES >2 MeV electron flux and SWPC radiation belt forecasts into `ext.radiation_belts`.  
   b. Calculate rolling averages and exposure flags inside `marts.radiation_belts_daily` for health narratives.  
   c. Update API responses (Space Weather detail) to surface the new indicators.
4. **Auroral power & Wing Kp forecasts**  
   a. Ingest OVATION Prime hemispheric power and Wing Kp forecast JSON into `ext.aurora_power`.  
   b. Generate predictive aurora probability bands (`marts.aurora_outlook`) for 3- and 7-day views.  
   c. Feed the aurora outlooks to the app dashboards and social automation templates.
5. **Coronal hole & CME scoreboard arrivals**  
   a. Persist SWPC coronal hole HSS forecasts and DONKI CME Scoreboard entries into `ext.ch_forecast` and `ext.cme_scoreboard`.  
   b. Compute arrival windows and confidence scores for inclusion in the predictive outlooks.  
   c. Surface major arrivals within navigation callouts and Earthscope posts.
6. **D-RAP absorption indices**  
   a. Schedule hourly pulls of NOAA SWPC D-RAP summaries, storing latitudinal absorption indices in `ext.drap_absorption`.  
   b. Aggregate to daily peaks (`marts.drap_absorption_daily`) for aviation/HF comms alerts.  
   c. Integrate absorption insights into the health guidance copy and automation triggers.
7. **Solar cycle predictions**  
   a. Ingest SWPC sunspot/F10.7 projections into `ext.solar_cycle_forecast`.  
   b. Build comparative views versus historical data in `marts.solar_cycle_progress`.  
   c. Display cycle context on Earthquake and Space Weather dashboards for long-range planning.
8. **Regional magnetometer indices**  
   a. Capture AE/AL/PC chain data (SWPC AE index feed or SuperMAG API) into `ext.magnetometer_chain`.  
   b. Normalize to regional stress indicators within `marts.magnetometer_regional`.  
   c. Highlight regional spikes in web/app dashboards and social alerts.  
9. **Documentation & schema**
   a. Update Supabase migrations for each new `ext`/`marts` table.
   b. Refresh `docs/SCRIPTS_GUIDE.md` with usage, scheduling, and troubleshooting notes.
   c. Add observability checks (Grafana or scripted Slack pings) to ensure each ingestion pipeline stays healthy.

#### Step 1 Execution Assignments

**Codex Assignment (copy/paste this into a new Codex request)**

> **Project**: Gaia Eyes – Predictive Data Coverage Expansion (Step 1 of the 30-day roadmap)
>
> **Repository**: `gaiaeyes-backend`
>
> **Goal**: Implement all ingestion, storage, and API changes described in Step 1 so Supabase becomes the single source of truth for WSA–Enlil, SEP/radiation, auroral power, coronal-hole arrivals, D-RAP absorption, solar-cycle forecasts, and regional magnetometer indices.
>
> **Scope & Deliverables**
> 1. Add or extend ingestion scripts to collect:
>    - DONKI `WSAEnlilSimulations` (store in `ext.enlil_forecast`, roll up to `marts.cme_arrivals`).
>    - GOES proton flux + SWPC S-scale alerts (`ext.sep_flux`, derived S-level columns).
>    - GOES >2 MeV electron flux & radiation belt forecasts (`ext.radiation_belts`, `marts.radiation_belts_daily`).
>    - OVATION hemispheric power and Wing Kp forecasts (`ext.aurora_power`, `marts.aurora_outlook`).
>    - Coronal-hole high-speed stream forecasts + DONKI CME Scoreboard (`ext.ch_forecast`, `ext.cme_scoreboard`).
>    - D-RAP absorption indices (`ext.drap_absorption`, `marts.drap_absorption_daily`).
>    - SWPC solar-cycle predictions (sunspot/F10.7) (`ext.solar_cycle_forecast`, `marts.solar_cycle_progress`).
>    - AE/AL/PC magnetometer indices (`ext.magnetometer_chain`, `marts.magnetometer_regional`).
> 2. Create Supabase migrations for all new `ext.*` and `marts.*` tables, with indexes/constraints appropriate for time-series queries.
> 3. Update FastAPI services so `/v1/space/forecast/outlook` and related endpoints surface the new data where applicable.
> 4. Document every new dataset and cron entry inside `docs/SCRIPTS_GUIDE.md`.
>
> **Technical Notes**
> - Reuse existing ingestion patterns (see `scripts/ingest_nasa_donki.py`, `scripts/ingest_space_weather_swpc.py`).
> - Follow project linting/typing standards (`black`, `ruff`, `mypy` as configured).
> - Ensure secrets/keys are pulled from environment variables—do not hardcode credentials. The existing `NASA_API` variable should be used for DONKI/WSA–Enlil requests; NOAA feeds do not require keys; SuperMAG endpoints are open but the attribution guidelines in their API docs must be respected when surfacing data.
>
> **Testing Expectations**
> - Add or update unit/integration tests for new scripts/utilities.
> - Provide sample command invocations for manual verification (e.g., `poetry run python scripts/ingest_enlil_forecast.py --days 3`).
> - Confirm Supabase migrations apply cleanly via `supabase db push` or the repository’s migration tooling.
>
> **Definition of Done**
> - All new datasets populate correctly in local/staging environments with at least one successful ingestion run per feed.
> - API endpoints expose the enriched data without breaking existing clients.
> - Documentation reflects scheduling, dependencies, and troubleshooting tips.

**Human Owner Checklist (complete outside of Codex)**

1. **Credential & Access Preparation**
   - Confirm the `NASA_API` key in the secrets manager is valid for DONKI/WSA–Enlil calls; NOAA SWPC endpoints remain keyless, and SuperMAG access relies on following their credit requirements rather than credentials.
   - Verify Supabase service-role credentials have insert/update privileges for the new schemas.

2. **Environment Configuration**
   - Add any new environment variables (e.g., `SUPERMAG_API_KEY`, `SWPC_API_EMAIL`) to `env.production`, staging, and deployment environments. Update onboarding docs so future engineers know how to configure them.
   - Confirm cron/worker infrastructure (Heroku Scheduler, GitHub Actions, etc.) has available capacity for the additional ingestion jobs.

3. **Data Source Validation**
   - Manually test each external API endpoint via `curl` or Postman to confirm connectivity from your network and note any rate limits or required parameters. Capture example responses for QA reference.
   - For D-RAP netCDF feeds, verify you can download and parse the files locally (install `netcdf4`/`xarray` if needed) before Codex automates the pipeline.
   - Review the SuperMAG API usage terms and document the required credit line or citation for any charts, social content, or dashboards that display their data.

4. **Deployment Oversight**
   - After Codex delivers the implementation, run migrations on staging, execute each ingestion script once, and validate that data appears in Supabase tables (spot-check timestamps, units, and derived columns).
   - Schedule the new ingestion jobs in production cron once staging verification is complete.

5. **Monitoring & Alerts**
   - Set up or extend Grafana/Slack alerts for the new tables (missing data, stale timestamps, API failures) so issues surface quickly.
   - Document runbooks for on-call responders covering how to re-run scripts, rotate API keys, or backfill data gaps.

6. **Sign-off & Communication**
   - Announce completion of Step 1 to the team, including a summary of newly available datasets and how they feed downstream features (app dashboards, Earthscope bot, analytics).
   - Update the 30-day roadmap tracker or project board to mark Step 1 as delivered before moving Codex onto Step 2.

### 2. Interactive NASA Overlays & Custom Charts
Make imagery interactive with first-party data overlays.

**Implementation Tasks**
1. Persist cleaned telemetry arrays (GOES X-ray, proton, electron, aurora) in Supabase alongside imagery metadata.  
2. Launch `/v1/space/visuals` returning synchronized imagery + time series for overlay use.  
3. Update `gaiaeyes-space-visuals.php` to render toggleable overlays using Chart.js/Canvas stacked over NASA assets.  
4. Mirror overlay rendering inside the iOS Space Weather module for parity.

### 3. Compare 2.0 with Lagged Correlations
Deliver a powerful explorer for discovering cross-domain patterns.

**Implementation Tasks**
1. Extend `build_space_history.py` and `build_compare_series.py` to include new predictive datasets and user-configurable lags.  
2. Store outputs in `marts.compare_daily` with metadata for lag offsets and normalization.  
3. Expose `/v1/compare/series?lag_days=` supporting multi-axis chart requests and CSV export.  
4. Enhance `gaiaeyes-compare-detail.php` with lag sliders, preset templates (e.g., “M6+ vs Kp lag 8”), and explanatory tooltips.  
5. Add corresponding controls in the iOS compare view, including saved preset management.

### 4. 10-Year Earthquake Analytics Hub
Tie seismic trends to solar cycles and seasonal patterns.

**Implementation Tasks**
1. Modify `ingest_usgs_history.py` to populate `marts.quakes_monthly` and seasonal aggregates across the 10-year history.  
2. Join quake marts with solar cycle projections in `/v1/earthquakes/history`.  
3. Expand the WordPress Earthquake dashboard with decade selectors, solar maximum shading, and downloadable summaries.  
4. Ship matching trends to the iOS Earthscope/Weekly modules with contextual health copy.

### 5. Multi-Day Predictive Dashboards
Provide actionable 3- and 7-day outlooks.

**Implementation Tasks**
1. Use the enriched marts to train heuristic/ML ensembles predicting flare, geomagnetic, aurora, radiation, and seismic risk levels.  
2. Publish structured results via `/v1/space/forecast/outlook` (probabilities, confidence, contributing drivers).  
3. Add “Next 3 Days” and “Next 7 Days” tabs/cards to Space Weather, Aurora, and Earthquake experiences (web + app).  
4. Pair each risk tier with mitigation guidance drawn from the guidance hub.

### 6. Personalized Health-Space Overlays
Let users see personal data against planetary drivers.

**Implementation Tasks**
1. Audit all JSON-only feeds; ensure Supabase ingestion for Earthscope, hazards, and guidance metrics.  
2. Extend `/v1/features/today` and `/v1/space/series` to join authenticated user metrics (HRV, sleep, mood, BP).  
3. Enable logged-in overlays in `gaiaeyes-compare-detail.php` and iOS compare screens with configurable lags.  
4. Provide export/share features so users can generate reports or send data to practitioners.

### 7. Navigation, Tooltips & Accessibility
Create a cohesive, educational experience.

**Implementation Tasks**
1. Build a reusable mu-plugin global navigation with quick links to Space, Aurora, Magnetosphere, Compare, Earthquakes, Guidance.  
2. Write plain-language tooltip copy explaining each metric, lag concept, and health implication; inject into web cards.  
3. Sync tooltip copy into iOS via info buttons and accessible VoiceOver labels.  
4. Conduct accessibility review (color contrast, keyboard navigation) before release.

### 8. Guidance & Research Hub
Offer holistic support backed by evidence.

**Implementation Tasks**
1. Launch `gaiaeyes-guidance.php` covering breathing, grounding, hydration, frequency/biofeedback, and “not medical advice” framing.  
2. Stand up `dim.research_sources` in Supabase; ingest curated studies with metadata (type, outcomes, citation links).  
3. Cross-link guidance cards from relevant dashboards and the mobile Tools section.  
4. Plan periodic content refresh cycles (e.g., monthly) and assign owners for ongoing research curation.

### 9. App Testing & Release Pipeline
Get external testers productive quickly.

**Implementation Tasks**
1. Lock feature freeze by end of Week 3; tag backend/API versions consumed by the app build.  
2. Configure CI (GitHub Actions) to produce signed TestFlight builds per push to `release/*`, with environment toggles for staging/prod APIs.  
3. Draft tester onboarding packets (feature highlights, feedback form, bug template, Slack/TestFlight groups).  
4. Schedule weekly triage calls during Week 4 for feedback review and hotfix prioritization.  
5. Track tester metrics (retention, feature usage) via analytics dashboards.

### 10. Earthscope Bot & Social Automation
Automate alerts, reels, and stories using enriched data.

**Implementation Tasks**
1. Enhance the bot to monitor new predictive datasets (Enlil arrivals, SEP levels, aurora outlooks, D-RAP spikes).  
2. Generate templated vertical videos using FFmpeg/Canva scripts with dynamic overlays and captions.  
3. Integrate scheduling/queueing for Instagram, TikTok, Facebook, and X; include fallbacks for API limits.  
4. Capture engagement metrics and conversion tracking to feed growth analytics.  
5. Develop a weekly social editorial calendar aligning with forecast cycles.

### 11. Revenue & Monetization Phasing
Lay groundwork for diversified revenue once testing completes.

**Implementation Tasks**
1. During testing: emphasize app subscription value, build newsletter and waitlist funnels within dashboards.  
2. Define premium web tier requirements (advanced compare presets, personal overlays, downloadable reports) and map Stripe/Supabase auth integration.  
3. Create sponsor/partner media kits leveraging predictive dashboards and Earthscope reach.  
4. Outline B2B licensing packages (clinics, wellness coaches) with API access controls and support plans.  
5. Prototype affiliate placements within guidance pages (grounding tools, HRV devices) with tracked links and disclosure standards.

---

## 30-Day Timeline

| Week | Focus | Key Deliverables |
| --- | --- | --- |
| **Week 1** | Predictive data ingestion foundation | Supabase tables & scripts for Enlil, SEP/radiation, aurora power, coronal hole forecasts, D-RAP, solar cycle, magnetometer indices; documentation refreshed. |
| **Week 2** | Analytics & automation enablement | Compare 2.0 marts, earthquake aggregates, predictive-model prototypes, `/v1/space/visuals`, Earthscope bot signal detection upgrades. |
| **Week 3** | Front-end & app integration | Overlay UI, navigation/tooltips, guidance hub draft, personalized overlays, TestFlight-ready CI pipeline, feature freeze tagged. |
| **Week 4** | Testing, social rollout & monetization prep | External tester onboarding + triage cadence, automated social content runs (stories/reels, forecast posts), premium web tier specification, revenue roadmap refinement. |

---

## Dependencies & Risks
- Timely access to SWPC/NOAA/DONKI feeds—implement retry/backoff to handle outages.
- Supabase schema migrations must be coordinated with ingestion scripts to avoid ingest failures.
- Predictive model validation requires historical datasets; ensure new marts backfill where possible.
- Social automation APIs (Instagram/TikTok) impose rate limits; plan for manual fallback when automation is blocked.
- Premium web features require authentication & billing integration (Stripe) after testing phase.

## Success Indicators
- All targeted predictive datasets available in Supabase and surfaced via API/web/app by Week 3.
- TestFlight build delivered to external testers with onboarding materials before end of Week 4.
- Earthscope bot publishing automated alerts (posts + stories/reels) using new datasets.
- Monetization brief finalized outlining premium web tier, partnerships, B2B licensing, and affiliate options for post-testing rollout.
