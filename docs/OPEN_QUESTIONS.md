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


## September 10, 2026 stability follow-up

- **Weather evidence:** ZIP 78754 served 14:35 UTC observations at 15:14–15:15 UTC (40–41 minutes old), with a 15:01:50 cache write. Render critical completed successfully at 15:05:07, updating all 37 locations without failures. At 15:15:24, a direct five-station check found KAUS at 15:00 while KEDC/KT74 remained 14:35. **Unknown:** when the newer KAUS reading became available to the production fetch. **Why it matters:** source publication and cron cadence can explain transient staleness without a DB defect; a persistent post-cycle mismatch needs deployed-fetch investigation. **Who/where:** technical lead, next critical log/cache comparison; daily report records closeout.
- **Staging hosting question persists:** Aurora run `34462329243`, job `102822802076`, returned SiteGround `sgcaptcha` HTML for collectors/nowcast and failed JSON assertions at 09:45 UTC; later run `34485141585` succeeded. Jennifer/hosting administrator can identify the triggering rule in access/security logs before any approved hosting change.
- **Unknown:** why today's WP publisher and hosted post-launch monitor runs were still absent at 15:14 UTC despite 14:20/14:15 schedules. **Why it matters:** today's WP delivery and hosted monitoring remain unverified, although EarthScope media/member generation succeeded (`34492360299`, `34492626696`). **Who/where:** technical lead should check subsequent scheduled runs; Jennifer can approve a recovery dispatch only if necessary after duplicate checks.

- **Weather closeout:** at 15:17:20 UTC the public observation advanced to 14:50 (27.3 minutes), following cache write 15:16:10. Warning cleared without intervention; core health remained good. No direct code fix established.


## September 11, 2026 stability follow-up

- **Recovered publishing incident / local patch:** space-weather job `103249245262` (run `34595205663`) exhausted USGS BOU/CMO fetch retries with ReadTimeout, then skipped JSON publication despite successful ingestion/rollup. Public JSON remained September 10 23:19 at September 11 14:50. A small unstaged workflow/test patch publishes JSON before independent ULF; four tests pass and the original workflow fails the regression case. Later run `34614790310` recovered production without this patch; final JSON September 11 15:07. **Unknown:** whether runner-specific USGS reachability caused the earlier timeouts. **Why it matters:** repeated ULF outages must not stale unrelated public data. **Who/where:** technical lead, GitHub logs and signed-in Render when Mac is unlocked; Jennifer reviews publishing the local patch.
- **Staging:** Aurora `34604737606` / job `103280294631` failed with curl (28) connection timeouts to staging2.gaiaeyes.com:443, not a confirmed captcha response in this run. **Unknown:** exact network/hosting cause. **Why it matters:** staging verification skipped downstream reads. **Who/where:** Jennifer/hosting administrator, connection and security logs around 13:31–13:38 UTC.
- **Closeout:** 15:39 UTC core healthy, waiting/queue zero, weather observation 15:10; final monitor five PASS/admin SKIP. Daily/member `34613141817`/`34613674280` succeeded with image/reel outcome checks. Yesterday's WP/monitor completed later; today's completion remains unverified. Render access blocked by locked Mac.


## September 12, 2026 stability follow-up

- **Staging hosting recurrence:** Aurora run `34678241245`, job `103511877379`, returned SiteGround `sgcaptcha` HTML for collectors/nowcast at 06:29 UTC and failed JSON assertions. Later runs `34690138640` and `34698199514` succeeded. **Unknown:** which hosting rule intermittently challenges GitHub runner traffic. **Why it matters:** staging validation fails despite healthy production DB/app freshness. **Who/where:** Jennifer or hosting administrator, SiteGround access/security logs around 06:29:10–06:29:23 UTC; any configuration remedy needs approval.

## September 13, 2026 stability follow-up

- **Public space media delay:** At 15:32 UTC, `gaiaeyes-media/data/space_weather.json` still carried `timestamp_utc=2026-09-13T12:14:00Z`, while the backend Kp timestamp was 15:23. Latest inspected space-weather run `34756686784` at 12:17 succeeded, including JSON publication before ULF; a second runs collection query found no later run. **Unknown:** why the quarter-hour workflow has not produced a newer visible run; workflow-state API inspection was unavailable through the connector. **Why it matters:** public media can lag while backend data is current. **Who/where:** technical lead, GitHub Actions schedule/workflow state and next natural run. Do not infer an emitter defect or dispatch automatically.
- **Idle transaction ownership:** Read-only activity samples at 15:32–15:35 UTC found 4–8 idle transactions; oldest reached 11m19s. Four sampled statements were schema introspection (`information_schema.columns`, `pg_class`, `pg_namespace`) through Supavisor, waiting on ClientRead. No blocking was observed in the bounded 15:34 check; API pool waiting and ingest backlog remained zero. **Unknown:** which client owns these open transactions and whether they persist after inspection ends. **Why it matters:** retained transactions can consume connections despite current healthy readiness. **Who/where:** technical lead/client owner, bounded activity checks and client transaction lifecycle; no session termination authorized or performed.
- **Staging hosting recurrence:** Aurora `34764460355`, job `103742847011`, received HTTP 202 SiteGround `sgcaptcha` responses for collectors and both nowcasts at 15:03:44–15:03:58 UTC, then failed assertions. **Unknown:** exact hosting rule. **Who/where:** Jennifer/SiteGround administrator, corresponding security logs; any hosting remedy needs approval.
- **Weather recovered sample:** At 15:31:14 UTC ZIP78754 returned observation 15:00 (31m); cache write 15:31:16 carried 15:15, and public closeout 15:35:28 returned 15:15 (20.5m). Render's natural 15:30 critical run succeeded, with 37/37 locations updated and zero failures. This supports cadence/provider-age investigation, not a proven source-selection defect or sustained reliability claim. Existing W-005 investigation remains separate and untouched.


## September 14, 2026 stability follow-up

- **P2 publishing schedule gap:** At 16:36 UTC public EarthScope remained September13 and space JSON13:35, although DB/app readiness and natural Render critical refreshes were healthy. Workflow-specific queries still showed latest daily34773442742/member34764036459/WP34771509824/monitor34771484942 from September13; space34850677295 succeeded13:41 today. All workflows are active. **Unknown:** why new scheduled runs are not visible beyond the morning window. **Why it matters:** public/member/social delivery remains incomplete despite healthy ingestion. **Who/where:** technical lead, GitHub scheduler/run history and next natural execution; refresh published state before any Jennifer-approved recovery dispatch.
- **Staging hosting recurrence:** Aurora34808768825/job103865749952 returned sgcaptcha HTML at05:12 and failed JSON assertions; later34834031087 succeeded. **Unknown:** exact SiteGround security rule. **Why it matters:** recurring staging validation failures. **Who/where:** Jennifer/hosting administrator, security logs around05:12UTC; hosting changes remain approval-gated.
- **Current closeout:** Weather recovered16:36 to16:15 observation; DB waiting/queue zero. At16:51–16:52,34 gauges,7 age-stale,2 non-calibrating,0 newer-input candidates. Idle transactions absent. Event Render lane remains unverified after browser disconnection; daily and critical lanes directly verified successful.


## September 15, 2026 stability follow-up

- **WP hosting recurrence:** September14 run34886550403/job104118615180 at19:23:45 returned202 sgcaptcha for auth/media and400 with sgcaptcha HTML for posts; public latest remains September13. **Unknown:** exact hosting rule and supported remedy. **Why it matters:** publishing remains blocked despite healthy backend. **Who/where:** Jennifer/hosting administrator, SiteGround security logs; refresh existing posts before any approved retry.
- **Publishing cadence:** At15:28–15:29 September15, latest Daily34906939201 remained September14, public EarthScopeSeptember14, spaceJSON11:09/latest space34961972445 at11:11. All workflows active; today's final Daily slot15:35 is still pending. **Unknown:** why scheduled runs are delayed. **Why it matters:** public/member/social freshness cannot be inferred from healthy Render-backed DB data. **Who/where:** technical lead, next natural GitHub runs and public timestamps. Render logs unavailable at login page.
- **Confirmed race, local patch:** Yesterday Daily34871536122/job104068778473 failed JSON push with fetch-first rejection; later34906939201 recovered all social outcome checks. Unstaged bounded normal-push/rebase fix passes local concurrent-writer and conflict integration tests. Deployment requires Jennifer review; conflicts intentionally remain failures.


## September 16, 2026 stability follow-up

- **WP hosting blocker:** Sept15 run35006047032/job104506022331 returned HTTP202 sgcaptcha for auth/media/posts at18:13:36; public EarthScope remainsSept13 atSept16 17:44. Staging Aurora35041401435/job104621836036 also challenged00:46, later recovered35111837654. **Unknown:** exact SiteGround rule and supported remedy. **Why:** publication remains blocked. **Who/where:** Jennifer/hosting administrator, security logs; configuration changes and any duplicate-checked recovery dispatch require approval.
- **Public space scheduling:** At17:44, space JSON remained14:53 while DB Kp reached17:40 (verified17:54). Latest visible space35112178876 succeeded14:58; workflow active. Today's WP/hosted monitor runs not visible17:44. **Unknown:** scheduler/run-visibility cause. **Why:** healthy ingestion does not establish public publication freshness. **Who/where:** technical lead, subsequent natural runs/public timestamps; Render currently login-only.
- **Core closeout:**17:44 dbtrue/waiting0/queue0; weather17:15 recovered below30min; final monitor5PASS/adminSKIP.35 Chicago-day gauges,7 age-stale,0 noncal newer-summary/features candidates. EarthScopeSept16 plus21 member rows; Daily/member35114966199/35115201947 successful. No direct code fix established; existing work preserved.


## September 17, 2026 stability follow-up

- **P2 local freshness:** First breach15:10:26UTC, observation14:40; closeout15:13:48 still14:40 (33.8min), cache15:01:29. NWS KAUS15:00 available15:13. **Unknown:** availability during previous production fetch and outcome of next15:15 critical cycle. **Why:** app weather remains behind30min despite dbtrue/waiting0/queue0. **Who/where:** technical lead, next cache/source comparison and signed-in Render critical logs (currently login-only). No source-selection defect proven.
- **Gauge candidate:**35 Chicago-day gauges,7 age-stale,1 noncalibrating/newer-input candidate: gauge08:29:46, summary10:38:50, features10:42:29. **Unknown:** unchanged-hash skip versus eligibility/scoring lag. **Why:** row age alone cannot prove stale score. **Who/where:** technical lead, Render scorer skip logs/input-hash decision; no force/recompute performed.
- **Publishing/hosting:** WP recoveredSept16 18:12:31/run35132880820; today's EarthScope remainsSept16 at15:11 before final15:35 slot. Five checked workflows active; today's daily/member/WP/monitor not yet visible. Aurora35223504042/job105209192730 sgcaptcha12:51 persists in staging. **Unknown:** today's schedule completion and exact hosting rule. **Who/where:** technical lead for next natural runs; Jennifer/hosting administrator for security logs and any approved remedy.


## September 18, 2026 stability follow-up

- **P2 WordPress hosting recurrence:** Sept17 run35257684057/job105325423699 returned202 sgcaptcha for auth/media/posts18:16:01; latest public EarthScope remainsSept16. Aurora35353336900/job105626534742 similarly challengedSept18 13:58. **Unknown:** exact SiteGround rule and supported remedy. **Why:** blocks publication/staging checks. **Who/where:** Jennifer/hosting administrator, security logs; configuration changes and duplicate-checked recovery dispatch need approval.
- **Public space cadence:** At14:04:39UTC Sept18, publicJSON12:59 versus DB13:56; latest space35348305153 succeeded13:07. **Unknown:** why visible scheduled runs miss configured15min cadence. **Why:** public data lags healthy app ingestion. **Who/where:** technical lead, subsequent natural GitHub run and timestamp; Render sign-in needed for lane logs. Today's EarthScope stillSept17 before15:35 morning-window close; not yet a missed-window incident.
- **Core closeout:** Initial37min local warning recovered to13:45 observation/19.7min at14:04:42; dbtrue/waiting0/queue0, no blockers/idle transactions.34 gauges,6 age-stale,0 noncal newer-input candidates. No direct code fix established.


## September 19, 2026 stability follow-up

- **P2 recurrent local freshness:** at16:56:42UTC ZIP78754 weather16:20 was36.7min old; cache16:46:23 still carried16:20. NWS KAUS16:35 available16:57; dbtrue/pool waiting0/queue0. **Unknown:** source availability during production fetch and next natural critical outcome. **Why:** app observation exceeds30min while cache advances. **Who/where:** technical lead, signed-in Render critical logs/provider selection; dashboard currently login-only. W005 cadence diagnosis remains plausible; no direct patch proven.
- **Publishing:** WP35375822885/job105700225815 failedSept18; public latest remainsSept16. Today's EarthScope35448302368/social outcome checks and member35448706703 succeeded. Public space12:26 at15:29 advanced16:00 at16:57; latest space35453765833 success. **Unknown:** exact current WP failure cause and scheduler delay; job-log retrieval timed out, prior SiteGround diagnosis is historical. **Why:** public delivery freshness differs from app ingestion. **Who/where:** Jennifer/hosting administrator for security logs and approval of any remedy/retry; technical lead for natural schedule history. Staging failed again35454922116 at16:25.


## September 20, 2026 stability follow-up

- **P2 local freshness:** at16:00:40UTC ZIP78754 weather15:25 was35.7min old; cache15:46:16 carried15:25. KAUS15:35 available16:00, core dbtrue/waiting0/queue0. **Unknown:** source availability at production fetch and next natural critical outcome. **Why:** observation exceeds30min despite advancing cache. **Who/where:** technical lead, signed-in Render fetch/selection logs (currently login-only). No direct fix proven. Initial Features timeout recovered on second monitor; gauge screen found zero noncalibrating stale/newer-summary-feature candidates.
- **Hosting/publishing:** Aurora35514521731/job106088094717 confirmed202sgcaptcha collectors/nowcast13:47. WP recoveredSeptember19/run35457618420; today's WP/monitor absent final30-run snapshot. Today's Daily35517112820 social outcomes/member35517272834 passed. Public space14:46 at16:00 versus DB15:39/latest space35517818429 success. **Unknown:** exact hosting rule and delayed publication scheduling. **Why:** staging fails and public freshness differs from backend. **Who/where:** Jennifer/hosting administrator for security logs and approved remedy; technical lead for subsequent natural runs. No reruns/deploys performed.
