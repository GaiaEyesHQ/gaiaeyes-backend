# W005 — local-weather freshness diagnosis

Recorded 2026-09-13T15:44:20.725576+00:00. All sample times below are UTC. **MEDIUM intermittent freshness breaches; the latest observed public sample recovered.** First precisely timed breach in this assignment: **2026-09-13 05:59:27**. No continuous outage or code defect was established. **No backend patch, threshold change or deployment is proposed from this evidence.**

## Finding and evidence

Regular cache refreshes preserve observations that may already be more than20 minutes old. Their age can cross the unchanged30-minute watch threshold before the following15-minute refresh. This explains the two assigned samples arithmetically and is consistent with the later direct provider comparison. The evidence supports a provider/cadence limitation; it does not prove historical station availability.

| Evidence surface | Sample / event | Observation or result |
|---|---|---|
| Existing production watch | 05:59:27 | 05:25 weather, age34.45min; breach |
| Existing watch recovery | 08:03:16 | 07:35 weather, age28.27min; sampled recovery |
| Root follow-up | 09:15:34.960 | 08:40 weather, age35.58min; breach |
| W005 database history read | 10:19:30 | 24 ZIP78754 rows from04:31:22–10:16:14; write intervals14.38–15.45min, median14.97min |
| Later existing watch | 13:56:34 →14:17:13 | 13:25 weather at31.57min, then14:00 weather at17.22min |
| W005 latest cache read | 15:35:11 | Cache written15:31:16.784; embedded weather15:15 |
| W005 public API | 15:35:51.944 | HTTP200; weather15:15, age20.87min; seven forecast days; request2.801s |
| W005 liveness/readiness | 15:35:50.88 | Both HTTP200; ok/live/db true as applicable; ingest queue/backlog0 |

[Original root receipt](gaia-freshness-followup.json), [existing-watch excerpts](existing-watch-excerpts.md), [cache analysis](cache-analysis.json), [public samples](public-probe-summary.json). These timestamps are discrete observations. A long active-task label or elapsed tool-return gap is not evidence of continuous work or monitoring.

The captured history maps the assigned breaches directly:

| Public sample | Observation age at cache write | Cache age at public sample | Total observation age | Next natural cache write / observation |
|---|---:|---:|---:|---|
| 05:59:27 | 21.35min at05:46:21 | 13.10min | 34.45min | 06:01:03 /05:40 |
| 09:15:34.960 | 21.73min at09:01:43 | 13.85min | 35.58min | 09:16:06 /09:00 |

All24 captured observations were11.01–26.73 minutes old when written. `cache.asof` is a write timestamp here; the payload’s `asof` and `weather.obs_time` retain the observation timestamp. A fresh database row therefore does not guarantee a sub30-minute weather observation throughout its lifetime. The60-minute cache expiry is separate from both the15-minute refresh cadence and30-minute warning threshold.

## Provider and source selection

Direct official NWS requests at15:37:22 returned the five stations in NWS order:

| Station | Latest observation | Age at request |
|---|---|---:|
| KATT | 14:51 | 46.37min |
| KEDC | 15:15 | 22.37min |
| KAUS | 15:15 | 22.37min |
| KT74 | 15:15 | 22.37min |
| KRYW | 05:55 | 582.37min |

The five `/observations/latest` requests each returned HTTP200 in0.26–0.40s. Responses advertised server/shared caching up to300 seconds; that header is not the observation’s age or proof of when NWS first received it. [Provider timestamps and headers](provider-summary.json), [official KEDC endpoint](https://api.weather.gov/stations/KEDC/observations/latest).

One offline replay of the actual current `services/external/nws.py`, using only these captured JSON responses and their fixed sampling time, selected **KEDC**. Temperature30.6C, humidity66.701834456934%, pressure1018hPa and observation15:15 exactly match the public payload. Network access was disabled for the replay. [Replay result](selection-replay-result.json), [replay script](replay_captured_selection.py). This confirms the current selection behavior on the captured provider set; station identity is inferred from the matching fields because the current cached payload does not record it. It cannot retrospectively prove which readings were available at the two earlier breaches.

## Natural job and implicated paths

Signed-in Render showed the15:15 critical run succeeded in4m16s and15:30 succeeded in5m12s. The15:15 log recorded ZIP78754 caching at15:15:53, local_current37/37 locations updated with0 failures, the local step145.3s, and lane completion at15:19:14.448. The initial15:30 row was still running; it was only classified complete after the later Runs view showed success. [Exact log evidence](render-evidence.json).

Render’s deployed critical-service commit matched local HEAD `9d7fcd2a6ec256d711f0931d0d5b22630ddada5a`. Source inspected without edits:

- [render-crons.yaml](/Users/gennwu/Documents/GitHub/gaiaeyes-backend/render-crons.yaml:9) and [critical runner](/Users/gennwu/Documents/GitHub/gaiaeyes-backend/scripts/run_render_cron.py:87): natural15-minute schedule and current-location step.
- [local poll](/Users/gennwu/Documents/GitHub/gaiaeyes-backend/bots/local_health_poll.py:237) and [cache writer](/Users/gennwu/Documents/GitHub/gaiaeyes-backend/services/local_signals/cache.py:39): assemble, then write with the current timestamp. [Cache reader](/Users/gennwu/Documents/GitHub/gaiaeyes-backend/services/local_signals/cache.py:73) selects the newest unexpired row.
- [NWS selector](/Users/gennwu/Documents/GitHub/gaiaeyes-backend/services/external/nws.py:224): prefer a fresh nearest station; otherwise compare up to five nearby unfiltered latest observations and retain the freshest usable reading.
- [Aggregator](/Users/gennwu/Documents/GitHub/gaiaeyes-backend/services/local_signals/aggregator.py:359) preserves the weather observation timestamp; [local endpoint](/Users/gennwu/Documents/GitHub/gaiaeyes-backend/app/routers/local.py:199) uses cached data and attaches forecast rows; [monitor](/Users/gennwu/Documents/GitHub/gaiaeyes-backend/scripts/post_launch_monitor.py:269) checks observation age against the existing threshold.

## Verification, limits and next action

Only three bounded SELECT queries were used: cache schema,24 weather rows for one ZIP, and one latest row. Public probes made one request per URL without retry. No raw health samples or individual patient records were queried. No broad watch/test suite was rerun. The one captured-data replay passed; `git diff --check` passed. [Queries and exact replay command](queries-and-checks.json), [source hashes](source-evidence-manifest.json).

The repository was initially clean. A concurrent stability-task update to `docs/OPEN_QUESTIONS.md` appeared later and was preserved. It independently recorded15:31:14 weather age31min followed by15:35:28 recovery, corroborating the same natural refresh. This overlapping read activity was discovered in the later file diff; no additional public/cache probes followed. The only active task returned by the earlier task listing was W005, so that listing was not proof of complete cross-task coverage. [Concurrent change preservation](concurrent-work-preservation.json).

The latest healthy sample is recovery evidence, not a sustained-reliability guarantee. Earlier20-second endpoint timeouts remain unconfirmed in cause; the current request succeeded in2.801s. Do not conflate request latency, cache write age, weather observation age and provider HTTP caching.

**Safest next action:** root reviews this complete diagnosis; continue the existing watch with the30-minute threshold unchanged. If stronger attribution is needed, pair the exact provider set with a future naturally observed breach. There is no demonstrated defect requiring a local repair, production retry or deployment. A future change intended to guarantee sub30-minute data would need an explicit provider/acquisition design; changing the timestamp or threshold would not make the observation fresher.

G016/H13 remains unchanged. Its report/handoff were preserved under `preserved-g016/` before W005/running was published. No native/iOS diagnostic, Terminal workaround, new runner, notification, monitor, account action, portfolio-register edit or human-queue edit occurred. No new Jennifer question is required by this diagnosis.
