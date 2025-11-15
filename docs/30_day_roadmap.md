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
   - Add any new environment variables to `env.production`, staging, and deployment environments. Update onboarding docs so future engineers know how to configure them.
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

#### Step 2 Execution Assignments

**Codex Assignment (copy/paste this into a new Codex request)**

> **Project**: Gaia Eyes – Interactive NASA Overlays & Custom Charts (Step 2)
>
> **Repository**: `gaiaeyes-backend`
>
> **Goal**: Deliver synchronized imagery + telemetry overlays across web and iOS by persisting cleaned series in Supabase and exposing them through a new `/v1/space/visuals` API consumed by WordPress mu-plugins and the mobile client.
>
> **Scope & Deliverables**
> 1. Extend existing ingestion scripts (e.g., `scripts/space_visuals_ingest.py`) to store normalized telemetry arrays (GOES X-ray, proton, electron, aurora power) in Supabase alongside image metadata.
> 2. Implement the `/v1/space/visuals` FastAPI endpoint returning:
>    - Image metadata (URL, capture time, instrument).
>    - Matching telemetry series (timestamp/value pairs) suitable for overlays.
>    - Feature flags for available overlays (flare markers, aurora probability, etc.).
> 3. Update `wp-content/mu-plugins/gaiaeyes-space-visuals.php` to request the new endpoint and render toggleable overlays with Chart.js (or existing `GaiaSpark` helpers) layered on NASA imagery.
> 4. Add or update shared frontend utilities to support responsive overlays (tooltips, legend toggles, accessible colors).
> 5. Surface the same endpoint in the iOS module (Swift/React Native files already in repo) so mobile charts mirror web overlays.
> 6. Write documentation updates summarizing the endpoint payload and any required front-end hooks.
>
> **Technical Notes**
> - Reuse the caching/helpers in `GaiaSpark` to maintain consistency with existing sparkline rendering.
> - Ensure Supabase writes are idempotent; avoid duplicate rows when ingestion reruns within the same hour.
> - Respect image licensing metadata (retain NASA credit strings in API responses).
> - Maintain TypeScript/JS linting standards (`npm run lint` or documented equivalents) for WordPress assets.
>
> **Testing Expectations**
> - Add backend tests covering `/v1/space/visuals` serialization and error handling.
> - Provide manual validation steps (e.g., `poetry run python scripts/space_visuals_ingest.py --days 1`).
> - Capture screenshots/gifs of the updated overlay UI for design review.
>
> **Definition of Done**
> - Supabase contains the new telemetry rows tied to imagery IDs.
> - Web and iOS clients render overlays without regressions to existing imagery displays.
> - Documentation and release notes communicate the new overlay capabilities.

**Human Owner Checklist (complete outside of Codex)**

1. **Asset & License Review**
   - Confirm all NASA imagery used in overlays carries the correct credit text; provide copy to marketing for social usage.
   - Verify any third-party chart libraries introduced by Codex meet licensing requirements for commercial use.

2. **Environment Preparation**
   - Ensure Supabase has the necessary storage/indexes for telemetry arrays (adjust retention policies if needed).
   - Coordinate with the mobile team to expose staging credentials/API base URLs for testing the new endpoint.

3. **QA & UX Validation**
   - Test overlay toggles on multiple browsers/devices, including responsive breakpoints and accessibility (screen readers, contrast).
   - Collect stakeholder feedback on overlay clarity, tooltip language, and loading performance before approving release.

4. **Deployment & Monitoring**
   - Schedule ingestion cron updates to populate telemetry before enabling the frontend toggle in production.
   - Add monitoring alerts for `/v1/space/visuals` latency and Supabase write failures.

5. **Communication**
   - Announce the overlay launch to the team with usage tips and note any user-facing documentation or tutorials to publish.

### 3. Compare 2.0 with Lagged Correlations
Deliver a powerful explorer for discovering cross-domain patterns.

**Implementation Tasks**
1. Extend `build_space_history.py` and `build_compare_series.py` to include new predictive datasets and user-configurable lags.  
2. Store outputs in `marts.compare_daily` with metadata for lag offsets and normalization.  
3. Expose `/v1/compare/series?lag_days=` supporting multi-axis chart requests and CSV export.  
4. Enhance `gaiaeyes-compare-detail.php` with lag sliders, preset templates (e.g., “M6+ vs Kp lag 8”), and explanatory tooltips.  
5. Add corresponding controls in the iOS compare view, including saved preset management.


#### Step 3 Execution Assignments

**Codex Assignment (copy/paste this into a new Codex request)**

> **Project**: Gaia Eyes – Compare 2.0 with Lagged Correlations (Step 3)
>
> **Repository**: `gaiaeyes-backend`
>
> **Goal**: Transform the Compare experience into a database-backed, lag-aware explorer with presets and CSV export supporting both web and mobile clients.
>
> **Scope & Deliverables**
> 1. Expand `scripts/build_space_history.py` and `scripts/build_compare_series.py` (or create new helpers) to:
>    - Include enriched predictive datasets from Step 1 (aurora, radiation, magnetosphere, etc.).
>    - Support configurable lag offsets per metric, storing metadata about applied lag.
> 2. Create/extend Supabase tables (`marts.compare_daily`, `marts.compare_presets`) capturing normalized series, lag metadata, and display units.
> 3. Implement a `/v1/compare/series` endpoint that accepts query params such as `metrics[]`, `lag_days`, `normalize` and returns chart-ready JSON plus CSV download links.
> 4. Update `wp-content/mu-plugins/gaiaeyes-compare-detail.php` to:
>    - Render lag sliders, multi-axis toggles, normalization options, and preset selection.
>    - Provide CSV export and shareable permalink functionality.
>    - Display explanatory tooltips sourced from guidance copy.
> 5. Align the iOS compare module with equivalent controls, reusing the backend endpoint and preserving state for saved comparisons.
> 6. Document preset definitions and configuration guidance in `docs/compare_presets.md` (create if absent).
>
> **Technical Notes**
> - Follow existing chart helper patterns to keep styling consistent.
> - Ensure endpoint pagination/limits prevent oversized responses when many metrics are selected.
> - Consider caching expensive lag computations if they depend on large historical windows.
>
> **Testing Expectations**
> - Add tests verifying lag calculations and normalization behaviors.
> - Provide sample CSV output fixtures for QA.
> - Run frontend integration tests or provide manual QA steps covering preset loading and exports.
>
> **Definition of Done**
> - Supabase contains lagged comparison data accessible via the new endpoint.
> - Web and mobile clients allow users to configure, save, and export comparisons without errors.
> - Documentation enumerates available metrics, lags, and presets.

**Human Owner Checklist (complete outside of Codex)**

1. **Metric Governance**
   - Approve the list of default presets and ensure descriptions use plain-language explanations for marketing.
   - Decide retention windows for historical data (e.g., 10-year vs. full history) and communicate compliance requirements.

2. **Legal & Privacy Review**
   - Confirm user-generated overlays (when personal data is included) comply with privacy policy and Terms of Service.
   - Draft disclaimers for correlation vs. causation to display near the compare charts.

3. **QA Validation**
   - Perform manual checks on high-interest presets (e.g., KP vs earthquakes) to verify lag alignment and narrative accuracy.
   - Gather beta user feedback on usability and adjust copy/tooltips accordingly.

4. **Launch Enablement**
   - Coordinate with marketing for announcement assets showcasing new compare capabilities.
   - Update support documentation/FAQ with instructions for using lag sliders and exports.
### 4. 10-Year Earthquake Analytics Hub
Tie seismic trends to solar cycles and seasonal patterns.

**Implementation Tasks**
1. Modify `ingest_usgs_history.py` to populate `marts.quakes_monthly` and seasonal aggregates across the 10-year history.  
2. Join quake marts with solar cycle projections in `/v1/earthquakes/history`.  
3. Expand the WordPress Earthquake dashboard with decade selectors, solar maximum shading, and downloadable summaries.  
4. Ship matching trends to the iOS Earthscope/Weekly modules with contextual health copy.


#### Step 4 Execution Assignments

**Codex Assignment (copy/paste this into a new Codex request)**

> **Project**: Gaia Eyes – 10-Year Earthquake Analytics Hub (Step 4)
>
> **Repository**: `gaiaeyes-backend`
>
> **Goal**: Provide decade-scale earthquake analytics connected to solar-cycle context across web and mobile experiences.
>
> **Scope & Deliverables**
> 1. Update `scripts/ingest_usgs_history.py` to compute and store:
>    - Monthly/seasonal aggregates across 10+ years (`marts.quakes_monthly`).
>    - Magnitude buckets and cumulative counts.
> 2. Join quake marts with solar-cycle projections (from Step 1) within a new `/v1/earthquakes/history` endpoint returning:
>    - Time-series data (monthly totals, magnitude breakdowns).
>    - Solar-cycle markers (max/min periods, forecast bands).
> 3. Enhance `wp-content/mu-plugins/gaiaeyes-earthquake-detail.php` to include decade selectors, solar maximum shading, download buttons, and contextual tooltips.
> 4. Update iOS Earthscope/Weekly modules to consume the new endpoint and present comparable visualizations with health guidance copy.
> 5. Document data interpretation notes (e.g., how solar-cycle overlays align with quake trends) for internal and user-facing education.
>
> **Technical Notes**
> - Ensure historical backfills run efficiently; consider batching to avoid API rate limits.
> - Use consistent color palettes for solar-cycle overlays across web and mobile.
> - Keep download formats (CSV/PDF) lightweight to avoid server strain.
>
> **Testing Expectations**
> - Add unit/integration tests for aggregation logic and the new endpoint.
> - Provide manual QA steps verifying decade selector behavior and solar overlay alignment.
> - Validate downloads (CSV/PDF) open correctly and include descriptive headers.
>
> **Definition of Done**
> - Supabase stores 10-year quake analytics with solar-cycle context.
> - Web and mobile dashboards display the enhanced analytics without performance degradation.
> - Documentation and tooltips explain insights in plain language.

**Human Owner Checklist (complete outside of Codex)**

1. **Historical Data Audit**
   - Confirm USGS data coverage for the desired timeframe; request backfills if gaps are detected.
   - Approve the presentation format for magnitude buckets and ensure alignment with scientific communication standards.

2. **Stakeholder Review**
   - Share prototype charts with subject-matter advisors to verify interpretations before public release.
   - Collect feedback from holistic health coaches to ensure mitigation tips feel actionable.

3. **Operational Prep**
   - Plan a content campaign highlighting insights discovered through the new analytics (blog, newsletter, social).
   - Update customer support scripts to address questions about historical comparisons.
### 5. Multi-Day Predictive Dashboards
Provide actionable 3- and 7-day outlooks.

**Implementation Tasks**
1. Use the enriched marts to train heuristic/ML ensembles predicting flare, geomagnetic, aurora, radiation, and seismic risk levels.  
2. Publish structured results via `/v1/space/forecast/outlook` (probabilities, confidence, contributing drivers).  
3. Add “Next 3 Days” and “Next 7 Days” tabs/cards to Space Weather, Aurora, and Earthquake experiences (web + app).  
4. Pair each risk tier with mitigation guidance drawn from the guidance hub.


#### Step 5 Execution Assignments

**Codex Assignment (copy/paste this into a new Codex request)**

> **Project**: Gaia Eyes – Multi-Day Predictive Dashboards (Step 5)
>
> **Repository**: `gaiaeyes-backend`
>
> **Goal**: Generate and surface structured 3- and 7-day outlooks for solar, aurora, radiation, and seismic activity with health-oriented explanations.
>
> **Scope & Deliverables**
> 1. Develop predictive models or heuristic ensembles using enriched marts (space weather, aurora, radiation, quake data).
> 2. Extend `/v1/space/forecast/outlook` (or create dedicated endpoints) to return:
>    - Daily probabilities/indices for key risks (R/S/G-levels, aurora visibility, seismic upticks).
>    - Confidence scores and contributing drivers (e.g., Enlil arrival, Wing Kp forecast).
>    - Suggested mitigation tags for frontend display.
> 3. Update web components (Space Weather, Aurora, Earthquake pages) to include “Next 3 Days” and “Next 7 Days” tabs/cards with charts and plain-language summaries.
> 4. Mirror the outlook UI in the iOS app, ensuring offline caching and accessibility compliance.
> 5. Document modeling assumptions, feature inputs, and validation metrics for transparency.
>
> **Technical Notes**
> - Choose modeling approaches that can be maintained by the team (clear heuristics or interpretable models).
> - Store forecast outputs in Supabase with timestamps and versioning for auditability.
> - Ensure mitigation tags map directly to guidance hub content IDs for cross-linking.
>
> **Testing Expectations**
> - Provide backtesting results or evaluation metrics demonstrating model performance.
> - Add API tests covering new forecast fields and error handling.
> - Document manual QA steps to verify frontend rendering and navigation between outlook tabs.
>
> **Definition of Done**
> - Forecast endpoints deliver multi-day outlooks with confidence and mitigation info.
> - Web and mobile UIs present the forecasts clearly without breaking existing layouts.
> - Modeling documentation is stored in the repo (e.g., `docs/predictive_models.md`).

**Human Owner Checklist (complete outside of Codex)**

1. **Model Governance**
   - Approve modeling approaches and ensure they align with ethical guidelines (no medical claims).
   - Define thresholds for public alerting vs. internal monitoring.

2. **Content Coordination**
   - Craft plain-language copy for each risk tier and ensure translations are planned if needed.
   - Update guidance hub entries referenced by mitigation tags.

3. **Launch Plan**
   - Prepare announcement materials explaining the new multi-day outlooks and how to interpret them.
   - Train support/community teams to answer questions about forecast methodology and confidence.
### 6. Personalized Health-Space Overlays
Let users see personal data against planetary drivers.

**Implementation Tasks**
1. Audit all JSON-only feeds; ensure Supabase ingestion for Earthscope, hazards, and guidance metrics.  
2. Extend `/v1/features/today` and `/v1/space/series` to join authenticated user metrics (HRV, sleep, mood, BP).  
3. Enable logged-in overlays in `gaiaeyes-compare-detail.php` and iOS compare screens with configurable lags.  
4. Provide export/share features so users can generate reports or send data to practitioners.


#### Step 6 Execution Assignments

**Codex Assignment (copy/paste this into a new Codex request)**

> **Project**: Gaia Eyes – Personalized Health-Space Overlays (Step 6)
>
> **Repository**: `gaiaeyes-backend`
>
> **Goal**: Integrate authenticated user metrics with planetary datasets so users can visualize personal responses against space-weather drivers.
>
> **Scope & Deliverables**
> 1. Audit and ensure ingestion of all environmental feeds into Supabase (Earthscope daily, hazards, guidance metrics) replacing JSON-only storage.
> 2. Enhance `/v1/features/today`, `/v1/space/series`, and related endpoints to:
>    - Accept authenticated user context.
>    - Return joined data combining user metrics (HRV, sleep, mood, BP) with planetary series and optional lag suggestions.
> 3. Update `gaiaeyes-compare-detail.php` and mobile compare screens to allow:
>    - Selection of personal metrics and comparison metrics.
>    - Lag adjustments and normalization options.
>    - Export/share features (CSV, PDF, share links).
> 4. Implement privacy safeguards (scope tokens, PII scrubbing) and audit logging for personalized comparisons.
> 5. Document user-facing instructions and consent requirements for enabling overlays.
>
> **Technical Notes**
> - Follow existing auth patterns for Supabase and app tokens; avoid exposing PHI.
> - Ensure exports exclude sensitive identifiers and include disclaimers.
> - Cache repeated comparisons to improve performance without leaking user data.
>
> **Testing Expectations**
> - Write tests for authenticated endpoints verifying authorization and data joins.
> - Provide QA scripts for manual testing with seed users (see `example_users.json`).
> - Validate exports download correctly and respect access controls.
>
> **Definition of Done**
> - Authenticated users can overlay their metrics with planetary data on web and mobile.
> - Privacy and security controls are documented and validated.
> - Export features work and include appropriate disclaimers.

**Human Owner Checklist (complete outside of Codex)**

1. **Privacy & Compliance**
   - Consult legal/compliance advisors to ensure data handling aligns with applicable standards.
   - Update Terms of Service and Privacy Policy to describe personalized overlays and data usage.

2. **User Consent Flow**
   - Design/update UI copy for opt-in consent (web and app) before personal data is displayed.
   - Prepare email templates or in-app messaging explaining the benefits and safeguards.

3. **Support Readiness**
   - Train support staff on troubleshooting overlay issues and handling data deletion requests.
   - Set up a process for users to export or delete their data upon request.
### 7. Navigation, Tooltips & Accessibility
Create a cohesive, educational experience.

**Implementation Tasks**
1. Build a reusable mu-plugin global navigation with quick links to Space, Aurora, Magnetosphere, Compare, Earthquakes, Guidance.  
2. Write plain-language tooltip copy explaining each metric, lag concept, and health implication; inject into web cards.  
3. Sync tooltip copy into iOS via info buttons and accessible VoiceOver labels.  
4. Conduct accessibility review (color contrast, keyboard navigation) before release.


#### Step 7 Execution Assignments

**Codex Assignment (copy/paste this into a new Codex request)**

> **Project**: Gaia Eyes – Navigation, Tooltips & Accessibility (Step 7)
>
> **Repository**: `gaiaeyes-backend`
>
> **Goal**: Implement a unified navigation system and accessibility-compliant tooltip education across web and mobile interfaces.
>
> **Scope & Deliverables**
> 1. Build a reusable WordPress mu-plugin component for global navigation (top bar) linking Space, Aurora, Magnetosphere, Compare, Earthquakes, Guidance, and future sections.
> 2. Refactor existing pages to include the new navigation component without breaking styling or responsiveness.
> 3. Create tooltip content modules with accessible markup (ARIA labels, keyboard focus) injected into dashboard cards and charts.
> 4. Update mobile components to add matching info buttons/tooltips, ensuring VoiceOver compatibility.
> 5. Add automated accessibility checks (e.g., axe-core, lint rules) to the frontend build pipeline if not already present.
> 6. Document navigation structure, tooltip guidelines, and accessibility best practices for future contributors.
>
> **Technical Notes**
> - Follow existing CSS/SCSS conventions within `wp-content` and mobile styling.
> - Ensure navigation is configurable (order/labels) via a central config file.
> - Avoid introducing blocking scripts that slow down page loads.
>
> **Testing Expectations**
> - Run accessibility audits (Lighthouse/axe) and share reports.
> - Provide cross-browser testing notes for navigation behavior.
> - Verify mobile info buttons pass VoiceOver/read-aloud checks.
>
> **Definition of Done**
> - Global navigation renders consistently across pages and devices.
> - Tooltips deliver educational copy with full accessibility support.
> - Documentation captures implementation patterns and QA results.

**Human Owner Checklist (complete outside of Codex)**

1. **Content Approval**
   - Review and approve tooltip copy to ensure tone aligns with Gaia Eyes’ voice.
   - Plan translations/localizations if needed for global users.

2. **Accessibility Governance**
   - Engage an accessibility consultant or power users to validate experiences beyond automated tooling.
   - Update the website accessibility statement to reflect improvements.

3. **Change Management**
   - Notify users about navigation updates (banner, release notes) to minimize confusion.
   - Monitor analytics for navigation engagement and adjust ordering if needed.
### 8. Guidance & Research Hub
Offer holistic support backed by evidence.

**Implementation Tasks**
1. Launch `gaiaeyes-guidance.php` covering breathing, grounding, hydration, frequency/biofeedback, and “not medical advice” framing.  
2. Stand up `dim.research_sources` in Supabase; ingest curated studies with metadata (type, outcomes, citation links).  
3. Cross-link guidance cards from relevant dashboards and the mobile Tools section.  
4. Plan periodic content refresh cycles (e.g., monthly) and assign owners for ongoing research curation.


#### Step 8 Execution Assignments

**Codex Assignment (copy/paste this into a new Codex request)**

> **Project**: Gaia Eyes – Guidance & Research Hub (Step 8)
>
> **Repository**: `gaiaeyes-backend`
>
> **Goal**: Launch a holistic guidance hub with evidence-backed articles and cross-link it across web and mobile experiences.
>
> **Scope & Deliverables**
> 1. Create the `gaiaeyes-guidance.php` mu-plugin rendering sections on breathing, grounding, hydration, frequency/biofeedback, and mitigation tactics with “not medical advice” framing.
> 2. Design frontend components for guidance cards, expandable tips, and CTA links to related dashboards.
> 3. Define Supabase schema `dim.research_sources` (plus join tables if needed) and build ingestion scripts to populate curated studies with metadata (title, authors, summary, citation URL, tags).
> 4. Add backend endpoints (e.g., `/v1/guidance/resources`) exposing guidance content and related research for web/app consumption.
> 5. Integrate guidance cards into relevant dashboards and iOS Tools/Earthscope modules with deep links.
> 6. Document content management workflows for adding/updating guidance and research entries.
>
> **Technical Notes**
> - Ensure guidance content supports Markdown/HTML safely (sanitize inputs).
> - Provide localization hooks for future translations.
> - Include citation data to satisfy SuperMAG/NASA attribution where applicable.
>
> **Testing Expectations**
> - Add tests for guidance endpoints and content rendering utilities.
> - Provide QA scripts for verifying search/filter (if included) and link integrity.
> - Capture screenshots of guidance sections for stakeholder review.
>
> **Definition of Done**
> - Guidance hub accessible via navigation with fully populated content and citations.
> - Research sources stored in Supabase and displayed alongside guidance tips.
> - Documentation covers content workflows and maintenance schedules.

**Human Owner Checklist (complete outside of Codex)**

1. **Content Creation**
   - Draft and approve holistic guidance copy, ensuring scientific references are accurate.
   - Curate and vet research articles; secure permissions where necessary.

2. **Editorial Workflow**
   - Establish review cadence (e.g., quarterly) for refreshing guidance content and verifying citations.
   - Assign owners for ongoing research ingestion and quality assurance.

3. **Marketing & Community**
   - Plan launch content (blog, newsletter, social) introducing the guidance hub.
   - Encourage community feedback to prioritize future topics.
### 9. App Testing & Release Pipeline
Get external testers productive quickly.

**Implementation Tasks**
1. Lock feature freeze by end of Week 3; tag backend/API versions consumed by the app build.  
2. Configure CI (GitHub Actions) to produce signed TestFlight builds per push to `release/*`, with environment toggles for staging/prod APIs.  
3. Draft tester onboarding packets (feature highlights, feedback form, bug template, Slack/TestFlight groups).  
4. Schedule weekly triage calls during Week 4 for feedback review and hotfix prioritization.  
5. Track tester metrics (retention, feature usage) via analytics dashboards.


#### Step 9 Execution Assignments

**Codex Assignment (copy/paste this into a new Codex request)**

> **Project**: Gaia Eyes – App Testing & Release Pipeline (Step 9)
>
> **Repository**: `gaiaeyes-backend`
>
> **Goal**: Establish a reliable TestFlight pipeline with documentation and analytics to support external tester onboarding and feedback loops.
>
> **Scope & Deliverables**
> 1. Configure CI (GitHub Actions or existing tooling) to build, sign, and upload TestFlight builds when `release/*` branches update.
> 2. Automate environment configuration for staging vs. production API endpoints within the app.
> 3. Generate tester onboarding materials stored in the repo (e.g., `docs/tester_guide.md`) covering features to test, feedback channels, and troubleshooting.
> 4. Instrument analytics hooks (if not already) to track tester engagement metrics and export dashboards/screenshots for the team.
> 5. Document release management procedures (feature freeze, build promotion, hotfix flow).
>
> **Technical Notes**
> - Coordinate with Apple Developer account settings; ensure provisioning profiles/certificates are current.
> - Store sensitive credentials in GitHub Actions secrets or the designated CI secret manager.
> - Include build versioning aligned with semantic version strategy.
>
> **Testing Expectations**
> - Provide evidence of a successful CI build uploading to TestFlight (logs/screenshots).
> - Run automated unit/UI tests as part of the pipeline and capture results.
> - Validate that staging and production configurations resolve to the correct backend endpoints.
>
> **Definition of Done**
> - External testers receive TestFlight builds with minimal manual intervention.
> - Documentation enables quick onboarding and consistent release practices.
> - Analytics dashboards/reporting capture tester engagement for weekly triage.

**Human Owner Checklist (complete outside of Codex)**

1. **Account & Compliance**
   - Ensure Apple Developer Program membership is active and testers are invited via App Store Connect.
   - Draft NDA or tester agreement if required before distributing builds.

2. **Tester Coordination**
   - Assemble tester roster, contact details, and focus areas; send onboarding materials and timelines.
   - Set up feedback channels (Slack, email, forms) and assign moderators.

3. **Operational Oversight**
   - Monitor TestFlight metrics (crash logs, session counts) and escalate issues to engineering.
   - Plan weekly triage meetings and ensure notes/actions are recorded.
### 10. Earthscope Bot & Social Automation
Automate alerts, reels, and stories using enriched data.

**Implementation Tasks**
1. Enhance the bot to monitor new predictive datasets (Enlil arrivals, SEP levels, aurora outlooks, D-RAP spikes).  
2. Generate templated vertical videos using FFmpeg/Canva scripts with dynamic overlays and captions.  
3. Integrate scheduling/queueing for Instagram, TikTok, Facebook, and X; include fallbacks for API limits.  
4. Capture engagement metrics and conversion tracking to feed growth analytics.  
5. Develop a weekly social editorial calendar aligning with forecast cycles.


#### Step 10 Execution Assignments

**Codex Assignment (copy/paste this into a new Codex request)**

> **Project**: Gaia Eyes – Earthscope Bot & Social Automation (Step 10)
>
> **Repository**: `gaiaeyes-backend`
>
> **Goal**: Expand automation to publish alerts, reels, and stories based on enriched predictive datasets while tracking engagement.
>
> **Scope & Deliverables**
> 1. Update the Earthscope bot to monitor new predictive feeds (Enlil arrivals, SEP levels, aurora outlooks, D-RAP spikes) and trigger content workflows.
> 2. Implement media generation utilities (FFmpeg/Canvas/Canva API) to produce vertical video stories/reels with dynamic chart overlays and captions.
> 3. Integrate social platform connectors (Instagram, TikTok, Facebook, X) with scheduling/queueing and graceful fallbacks when automation limits apply.
> 4. Add analytics instrumentation capturing impressions, clicks, and conversions, storing results in Supabase for reporting.
> 5. Document configuration, rate-limit handling, and content templates for ongoing operations.
>
> **Technical Notes**
> - Respect each platform’s automation policies; use approved APIs or third-party schedulers where necessary.
> - Keep generated media within platform aspect ratios and duration limits.
> - Secure API keys/webhooks in environment variables; never commit secrets.
>
> **Testing Expectations**
> - Provide sample generated media files and logs demonstrating automated posting (use staging accounts if possible).
> - Add unit tests for trigger logic and analytics tracking.
> - Outline manual QA steps for verifying scheduled posts and fallback behavior.
>
> **Definition of Done**
> - Earthscope bot produces and schedules multimedia content based on predictive data without manual intervention for routine alerts.
> - Engagement metrics are collected and reviewable by the growth team.
> - Documentation enables marketing/community teams to adjust templates and schedules.

**Human Owner Checklist (complete outside of Codex)**

1. **Platform Access & Compliance**
   - Secure or verify access to required social platform APIs or approved third-party schedulers.
   - Review each platform’s terms to ensure automation tactics remain compliant; obtain necessary approvals.

2. **Brand & Content Strategy**
   - Approve visual templates, tone, and captions for automated content to maintain brand consistency.
   - Develop a weekly editorial calendar aligning automation with manual posts/campaigns.

3. **Monitoring & Response**
   - Assign team members to monitor social accounts for comments/messages triggered by automated posts.
   - Establish escalation protocols for critical alerts or misinformation concerns.
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
