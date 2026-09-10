# Open Questions

## Reconciled September 2026 questions

Use [HUMAN_INPUT_NEEDED.md](recovery/HUMAN_INPUT_NEEDED.md) for the prioritized current questions, why they matter, who can answer, and work that can continue. In particular: production access-control approval, signed-in Render/provider evidence, historical credential-remediation status, privacy/store review, device acceptance, and organization account actions. [RECOVERY_AUDIT.md](recovery/RECOVERY_AUDIT.md) records what was verified. The historical list below is preserved for context; several entries (including absence of Render cron configuration and Android migration status elsewhere) have been superseded and must be checked against current source before action.

1. **Render services + cron jobs**
   - **Why needed**: backend + scheduled ingest jobs are not defined in repo (`render.yaml` missing).
   - **Where to fill**: Render dashboard (service list, cron schedules, env vars).

2. **Supabase dashboard-only settings**
   - **Why needed**: RLS policies beyond migrations, storage bucket ACLs, and auth settings may exist only in the dashboard.
   - **Where to fill**: Supabase dashboard → Auth / Storage / Database policies.

3. **JSON pipelines still required**
   - **Why needed**: WordPress and iOS still rely on gaiaeyes-media JSON fallbacks; it’s unclear which pipelines are still scheduled and which are deprecated.
   - **Where to fill**: Ops runbooks or Render/cron job configs.

4. **Space visuals media hosting**
   - **Why needed**: Visuals can be served from Supabase storage or legacy CDN; the current authoritative source isn’t explicit.
   - **Where to fill**: Backend env vars (`VISUALS_MEDIA_BASE_URL`, `MEDIA_BASE_URL`, `GAIA_MEDIA_BASE`) and storage bucket configuration.

5. **Backend webhook consumers**
   - **Why needed**: `/hooks/*` endpoints are stubs with TODOs and may need downstream integrations.
   - **Where to fill**: Product/ops decision on desired webhook side effects.

6. **Schumann latest endpoint source**
   - **Why needed**: `/v1/earth/schumann/latest` reads `marts.daily_features` columns (`f0..f5`) that are not present in the migration schema.
   - **Where to fill**: Confirm intended data source (marts.schumann_daily vs daily_features) and update schema or endpoint accordingly.

7. **Website sections still JSON-only (News / Compare / Pulse)**
   - **Why needed**: The WordPress site relies on `gaiaeyes-media` JSON for News, Compare, and Pulse, but the iOS app needs an API-first source to mirror these sections.
   - **Where to fill**: Decide whether to (a) keep using the existing JSON snapshots in-app as a temporary source, or (b) add Supabase-backed tables + new backend endpoints.

8. **Schumann series endpoint mismatch with WP**
   - **Why needed**: WP calls `/v1/earth/schumann/series?hours=24&station=...`, but the backend endpoint currently accepts `limit` and `cols` only.
   - **Where to fill**: Confirm expected query parameters and update the backend or WP/clients to match.

9. **iOS Supabase project values**
   - **Why needed**: iOS billing auth now reads `SUPABASE_URL` + `SUPABASE_ANON_KEY` from `Info.plist`, but the concrete values must be filled in.
   - **Where to fill**: Supabase dashboard → Project settings → API.

10. **Magic link redirect URL + Associated Domains**
   - **Why needed**: iOS Supabase magic links need a redirect target that reopens the app (universal link or custom scheme). The app now supports an optional `GAIA_MAGICLINK_REDIRECT` but the exact URL + associated-domain setup is still a human config.
   - **Where to fill**: Apple Developer → Associated Domains + Supabase Auth redirect settings.

11. **RPC signatures for dashboard + local signals**
   - **Why needed**: The backend calls `app.get_local_signals_for_user` and `app.get_dashboard_payload`; it is unclear whether these require a `user_id` argument or rely on JWT context.
   - **Where to fill**: Supabase SQL definitions for the RPCs (or runbook notes).

12. **Public support contact details for App Store submission**
    - **Why needed**: Apple’s Support URL guidance expects real contact information on the support site, and the current public support page clearly exposes the support email but may still need a business mailing address and/or phone number depending on legal/jurisdiction requirements.
    - **Where to fill**: Product/legal/ops decision for what public contact details Gaia Eyes should publish on `https://gaiaeyes.com/support/`.

13. **RevenueCat launch product configuration**
   - **Why needed**: The app now reads RevenueCat API/product values from `Info.plist` build settings, but the real RevenueCat Apple SDK key, App Store product identifiers, entitlement ids, and webhook Authorization value must match the RevenueCat dashboard before TestFlight purchase testing.
   - **Where to fill**: RevenueCat dashboard, App Store Connect subscriptions, Xcode build settings / xcconfig, and backend environment variable `REVENUECAT_WEBHOOK_AUTHORIZATION`.

14. **iOS heart-rate raw ingest gap vs statistics repair**
   - **Why needed**: `hr_min` and `hr_max` only populate when same-day `heart_rate` rows land in `gaia.samples`, but the test account showed `resting_heart_rate` continuing while raw `heart_rate` stopped after April 22, 2026. A short statistics-based repair now mitigates the gap, but the original reason raw `heart_rate` observer/delta ingest missed April 23, 2026 is still unknown.
   - **Where to fill**: Inspect iOS HealthKit observer execution, anchors, and same-day `HKQuantitySample` availability for `.heartRate` on device logs vs `gaia.samples` writes.

15. **HRV baseline contract for Body and recovery-oriented gauges**
   - **Why needed**: The Body page currently receives `hrv_avg` but no user-baseline delta, while HRV contributes internally to Health Status only. Product intent is for a below-usual HRV day to inform Heart, Energy, and Recovery Load, but the bounded weights and minimum baseline requirements are not yet defined. Adding those score effects without an explicit rule would turn a historical association into an unreviewed causal adjustment.
   - **Where to fill**: Product/science decision in `bots/definitions/gauge_logic_base_v1.json`, followed by a shared baseline field in `/v1/features/today`, focused scorer tests, and matching iOS Body copy.

16. **Historical import sample formats and legal review**
   - **Why needed**: The retention and user-deletion defaults are now recorded, but adapters still require real redacted exports, field/version mapping, provider permitted-use review, and confirmation that the raw-file recovery window and archival policy meet privacy obligations.
   - **Where to fill**: Collect samples from Migraine Buddy, Bearable, MigraInsight, HeadShot, and Prevent Headache; record findings in the canonical import specification; obtain privacy/legal review before storing production import files.

17. **Community consent legal review and published-snapshot withdrawal**
   - **Why needed**: Minimum cohort and geographic suppression defaults are recorded, but counsel still needs to approve the consent text and decide how a later withdrawal affects an aggregate snapshot that users have already seen.
   - **Where to fill**: Privacy/legal/research review before community data collection or aggregate display.

18. **Geoelectric and land-surface-temperature provider hypotheses**
   - **Why needed**: The roadmap now distinguishes regional geoelectric field/ground conductivity from TEC and separates health-oriented land-surface temperature from volcano monitoring. Gaia Eyes still needs a specific user question, provider, spatial resolution, historical coverage, and evidence boundary for each.
   - **Where to fill**: Product/research spike before provider integration or ingestion work.

19. **Condition-specific product/science advisory panel**
   - **Why needed**: Predictive notices and community evidence claims need headache/autonomic clinical review, longitudinal-statistics review, health-literacy review, and compensated patient input. No reviewers or sign-off process have been selected yet.
   - **Where to fill**: Recruit through recognized specialty directories and academic programs; record credentials, conflicts, scope, compensation, and versioned sign-off in the research framework.

20. **AI Guide privacy and evidence contract**
   - **Why needed**: An AI Guide could receive sensitive health context and produce unsupported medical-sounding claims unless retrieval sources, data minimization, retention, refusal behavior, and deterministic fallback are defined first.
   - **Where to fill**: Privacy/legal/product/engineering review after deterministic Guide evidence objects and help content are stable.

21. **Gaia Home Rev A hardware reviewer**
   - **Why needed**: Flux can assist with the schematic and layout, but a named reviewer still needs to approve the power budget, protection, footprints, antenna keep-out, airflow, thermals, test access, and manufacturing package before boards are ordered.
   - **Where to fill**: Confirm the engineer responsible for the schematic gate and layout/manufacturing gate in `docs/gaia-home/FLUX_HANDOFF.md`.

22. **Gaia Home assembler and design rules**
   - **Why needed**: PCB stack-up, trace/spacing limits, available parts, customer-supplied SEN66 handling, connector assembly, test services, duties, and minimum economical quantity depend on the selected assembler.
   - **Where to fill**: Obtain prototype quotes for two populated units plus spare bare boards, then attach the selected assembler's current rules to the Flux project.

23. **Gaia Home device authentication and claiming**
   - **Why needed**: Each unit needs a unique revocable credential and secure account-claiming flow without embedding a shared production secret. The exact certificate/key injection and recovery process is not selected.
   - **Where to fill**: Backend, firmware, and manufacturing security design before implementing the ingest endpoint or ordering a pilot build.

24. **Gaia Home sampling and offline-retention targets**
   - **Why needed**: The initial proposal uses one-minute analysis records, but native sensor cadence, flash endurance, batch size, retry behavior, and required offline days must be fixed together.
   - **Where to fill**: Firmware and data review using the current SEN66 cadence and expected Gaia Eyes database volume.

25. **Gaia Home enclosure and product-cost target**
   - **Why needed**: Airflow, temperature bias, bedroom noise, antenna performance, mechanical stability, manufacturing method, landed cost, and retail margin depend on an enclosure concept developed with the PCB. A small glanceable display is still under consideration, but touch logging and on-device voice are not Rev A requirements.
   - **Where to fill**: Industrial design and mechanical review before PCB placement is frozen. Decide whether Rev A populates a display, reserves a connector and power budget, or omits it; preserve separate Rev A validation and later retail targets.

26. **Gaia Eyes phone voice-assistant entry contract**
   - **Why needed**: Siri/Google-style symptom and exposure entry is preferable to an always-listening Gaia Home microphone, but the supported commands, authentication behavior, confirmation, undo, failure handling, follow-up timing, privacy copy, and iOS/Android parity are not yet defined.
   - **Where to fill**: iOS/Android product and privacy design using the existing canonical symptom/exposure APIs before advertising hands-free logging.

## September 7, 2026 stability follow-up

- **Unknown:** Which SiteGround control is challenging authenticated WordPress publishing, and what supported configuration restores access? September 6 publisher run `34047437381`, job `101524948761`, returned HTTP 202 `sgcaptcha` HTML for media and posts; public latest EarthScope remains September 4. **Why it matters:** publication is blocked; the secondary `NoneType` exception is not the cause. **Who/where:** Jennifer or the SiteGround administrator should inspect hosting security/access logs and record the approved remedy here. Check existing posts before any approved retry.
- **Unknown:** Why September 7 Daily Pipeline and member-writer runs were absent from GitHub at 15:02 UTC despite active schedules. **Why it matters:** public EarthScope is still September 6; eight September 7 member rows exist, but scheduled member coverage is unverified. **Who/where:** technical lead can inspect subsequent GitHub run timestamps and outcomes; Jennifer can authorize recovery dispatch if the scheduled lane remains missing.

## September 8, 2026 stability follow-up

- **New evidence for the SiteGround question above:** September 7 WP run `34152816928`, job `101838477095`, again returned HTTP 202 `sgcaptcha` for auth/media/posts. September 8 staging Aurora run `34233103563`, job `102083894960`, received the same challenge for collector and nowcast routes, then failed JSON assertions. **Unknown:** which hosting rule affects these GitHub runner requests and whether production/staging share its configuration. **Why it matters:** public WP EarthScope remains September 4; staging collector verification is intermittent. **Who/where:** Jennifer/SiteGround administrator should inspect access/security logs and record a supported remedy before any approved recovery dispatch.
- **Scheduling follow-up:** September 7 Daily Pipeline/member runs later succeeded (`34142963056`, `34143341026`). September 8 runs also succeeded (`34242090972`, `34242650878`) after delayed starts at 15:01/15:06 UTC; public JSON is now September 8. Delay recovered; no dispatch needed. Exact scheduler cause remains unverified.


## September 9, 2026 stability follow-up

- **WordPress recovery:** September 8/9 publisher runs `34259995251` and `34385341473` succeeded; public REST now shows September 9 EarthScope at 17:51:00. No recovery dispatch needed. Staging Aurora job `102417179414` still showed HTTP 202 `sgcaptcha` at 09:46 UTC before a later successful run `34360738009`. The exact SiteGround control and lasting remedy remain unknown; Jennifer/hosting administrator can identify it in security/access logs.
- **Unknown:** Why ZIP 78754 still served 20:25 UTC observations at 21:03–21:05 UTC (38–40 minutes), despite a 20:46 cache write and a successful critical-lane completion at 20:49:30 UTC. **Why it matters:** app weather exceeds the 30-minute freshness threshold while DB/queue and actionable gauge checks are healthy. **Who/where:** technical lead should inspect the subsequent critical local_current step and provider/station observations before proposing a direct fix. Signed-in Render worked; daily and event lanes showed successful September 9 runs.
