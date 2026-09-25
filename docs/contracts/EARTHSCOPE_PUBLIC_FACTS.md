# EarthScope public-facts qualification

G046 compatibility foundation with G053 bounded public-copy context, September 24, 2026 (G044 wire contract preserved). Local, default-off preparation for the existing
`gaia-draft-worker-v1-r1` contract. This qualifies inputs; it does not certify
copy quality, medical/scientific conclusions, renderer compatibility or a
production takeover. The separate default-off consumer is documented in [EARTHSCOPE_LOCAL_PRIMARY.md](EARTHSCOPE_LOCAL_PRIMARY.md).

## Traceable parity matrix

The source of truth for active inputs is `bots/earthscope_post/earthscope_generate.py`
`main()` (4154 onward), its fetch helpers and the current outlook response in
`app/routers/space.py`. A function's existence alone does not prove it is called.

| Active legacy input | Shadow mapping | Provenance and difference |
|---|---|---|
| `fetch_space_weather_from_marts`: daily `kp_max`, `bz_min`, flare/CME counts | Existing `kp_max_24h`, `bz_min`, `flares_24h`, `cmes_24h` | Selected daily projection and hash; `updated_at` remains the aggregate time. Rollup groups by UTC date, so wire names ending `24h` mean calendar-day aggregates here. A missing count stays null instead of legacy coercion to zero. Counts do not establish CME direction/arrival. |
| Daily `sw_speed_now_kms` / `sw_speed_now`, then `sw_speed_avg` | Existing `solar_wind_kms` | Same preference when a same-day shared `now_ts` exists; invalid/out-of-range or undated current value falls back to valid 100–2000 km/s daily mean. Ledger names the exact selected column. Shared `now_ts` is not a wind-specific timestamp. |
| `fetch_kp_now_from_marts`: latest `marts.kp_obs` | Existing `kp_now` | Keep `kp_time` and hash. Same UTC day, no future time and at most 12 hours old; unlike legacy, no unbounded latest-overall stale fallback. |
| Outlook API `kp.now` fallback | Daily `kp_now`, then timestamped `ext.space_weather.kp_index`, then `ext.magnetosphere_pulse.kp_latest` | Reuse the route's existing public sources/precedence through explicit read-only projections. Apply same-day/12-hour qualification. Daily value has a shared timestamp, not a precise Kp sample timestamp. Never invoke the route's forecast materialization or external GOES work. |
| Outlook `kp.last_24h_max` fallback | Already the same daily `kp_max` | No independent measurement is created. If the canonical aggregate is absent, preparation fails rather than inventing a request-time date. |
| Writer requests outlook root `bz_now`, `sw_speed_now_kms`, `earth_directed_cme_count_24h` or singular `cme` | Unavailable in inspected actual response | Current response returns none of those keys. It returns plural `cmes` with different semantics. Do not infer wind/Bz or relabel 72-hour/directional counts as daily totals. This is an existing producer/consumer mismatch, not adapter parity success. |
| `fetch_schumann_from_marts`: Tomsk/Cumiana f0 group means, else available stations | Existing `schumann_value_hz` | Derive station/day/f0/`last_fundamental_ts` directly from `ext.schumann` fundamental samples, with explicit UTC bounds and UTC grouping; label that actual source in the manifest/ledger. The existing hosted `marts.schumann_daily` view has no sample-time column and remains unchanged. Average only same-day rows with nonfuture dated fundamental samples. Preserve equal weighting of the available Tomsk/Cumiana group means; fallback to other valid stations if both unavailable. Do not mix previous-day fallback rows into today. Station measurements are not global personal exposure. |
| Schumann harmonic dictionary and note | Not added to wire | Main does not send harmonics in `_build_facts`; they are rendered/exported context, not required facts for the new copy contract. f0 provenance/meaning is supplied. No unused schema fields added. |
| Outlook aurora impact, then main's Kp-derived replacement when Kp ≥5 | Existing `aurora_headline`, `aurora_window` | Same G1/G2/G3+ threshold text from daily maximum, else Kp now. At lower/unknown Kp, headline stays null. Legacy can retain “Next 72h” or set “Next 24h” despite deriving the headline from an observed maximum. Shadow explicitly says observed UTC-day Kp context, not a forecast or local visibility prediction. |
| Recent default captions/openers; IG/FB variants; titles | `recent_public_copy` | Filtered public default rows, at most 21 previous calendar days; latest five caption sets and 21 titles. Include IG/FB captions stored in canonical `metrics_json.social_variants`. Text limited to 2048 characters, titles 160. G053 adds the latest three sets of snapshot/affects/playbook/voiceover (768 characters each) and five reel beats (256 each), as named public text excerpts. No arbitrary JSON or member-body access. Avoid duplicate data sources and member/user rows. Older standalone IG/FB platform rows and legacy `lead` fallback are deliberately excluded; this is a bounded canonical-copy qualification, not exhaustive historical repetition proof. |
| `_recent_signal_history`: three prior post metric snapshots | `facts.recent_signal_history` | At most the preceding three calendar days; dates, source IDs and source-update timestamps remain attached. Stored public metrics are historical context, not newly observed measurements or health-causation evidence. Older posts may inform repetition, never recent carryover. |
| Pulse, `space_weather.json`, consolidated `earthscope.json` helpers | No loader, no new provider | AST/source trace finds their definitions but no calls in the current generator. Therefore `quakes_count` and `severe_summary` remain null. Unknown local conditions are not zero events or calm weather. |
| Tone, bands, hook-lane/template selection, first-person setting, brand/editorial brief | Existing Local AI editorial layer | These are derived/editorial controls, not new observations. `sample_kind` retains existing core quiet/active/missing-data classification. This adapter does not import or modify the production generator or freeze editorial wording into a facts field. |

## Freshness and provenance

`services/earthscope_public_facts.py` is the shared adapter used by the default-off
shadow CLI. Production requires requested day = aggregate day = aggregate update
UTC date = current UTC date. An explicitly conflicting/future shared observation
timestamp aborts preparation. Missing core values produce `missing_data`, never
an assumed quiet day. Numeric bounds/finite checks preserve valid zeros.

The existing manifest's exact four fields remain unchanged. Each entry hashes
the selected normalized public projection; no additional source schema is sent
over the wire. The companion qualification ledger contains those projections,
field meanings, aggregate/observation distinctions, rejected station rows and
copy omissions. `facts_as_of` is never reset to request time. The geographic
scope text carries key timestamp and interpretation limits into the writer.
Missing optional tables/privileges abort through the controlled storage-error
receipt rather than silently asserting an empty successful read.

`synthetic=True` exists only as an explicit pure-function fixture choice. The
configured producer never supplies it. Fixtures retain synthetic classification
and cannot become current-condition evidence. A dated artifact is not a queued,
claimed, generated or delivered job.

## Least-privilege history access

Migration `20260921225050_qualify_earthscope_public_facts.sql` follows the G043
queue migration and its original public-mart grants. It adds a security-barrier,
owner-checked view that filters `content.daily_posts.user_id IS NULL` and
`platform='default'`, matching the existing public-row classification. It
projects only bounded public text and three environmental metrics. This is a
deliberate restricted-view boundary: making it invoker-checked would require
the preparer to receive underlying mixed-table access, which is not granted.
There is no SECURITY DEFINER function, mixed-content RLS change, login, credential,
public/client grant or write permission. Verify actual view ownership and
effective target grants before any deployment.

G045 metadata established that this migration version has never been applied to
the primary hosted target. G046 revises that unapplied file in place: do not run
the frozen G044 migration before the revision, and do not rewrite applied history.
The preparer gets only the additional named source columns and SELECT on this
view. Its Schumann grant covers only `station_id,ts_utc,channel,value_num` on the
existing raw public observation table. No new Schumann view or parallel feed is
created. A migration guard requires `ts_utc` to be `timestamptz`; raw types were
not directly inspected by G045 and remain a target preflight prerequisite.

Two SELECT-only policies on the existing RLS-enabled `marts.kp_obs` and
`ext.magnetosphere_pulse` target only `gaia_earthscope_writer_preparer`. Existing
policies and RLS flags remain unchanged. The role gets no anon/service membership,
BYPASSRLS, superuser, write access or blanket source-table grant. Role membership
for an actual login is a separate provisioning step; CREATEROLE alone is not
proof that SET ROLE is permitted.

The raw Schumann query uses UTC-aware `[day, day+1)` parameters, groups with
`AT TIME ZONE 'UTC'`, and computes the mean plus maximum actual timestamp from
finite, nonnegative `fundamental_hz` samples. Null/other-day timestamps and
invalid values are excluded; a future latest sample makes that station
unavailable, even if earlier samples exist. Same-day eligibility has no invented
sub-day freshness guarantee. Harmonic timestamps never refresh the fundamental.
The v2 ledger describes this derivation and hashes the selected normalized
projection. Original mart view columns, date semantics and other consumers stay
unchanged. The exact four-field wire manifest and required fact keys stay intact.

 Anonymous, authenticated, service-role and backend roles cannot select
the new view in local permission checks. The preparer cannot select the original
posts table/private canary or update the non-updatable view. No schema was
applied to a hosted database.

## Local verification and remaining acceptance

`venv/bin/python -m pytest -q tests/api/test_earthscope_public_facts.py` exercises
synthetic current/stale/missing/conflicting-day inputs, source/field selection,
timezone stability, exact input policy, historical separation, bounded text,
and real PostgreSQL projection/role denial. The shared G043 setup supplies the raw Schumann table required by the corrected
collector; accepted G043 delivery tests are not replayed. The separate
`tests/api/test_earthscope_hosted_compatibility.py` suite reproduces G045's view,
policies and default ACLs with synthetic rows and a NOSUPERUSER migration owner.
It reproduces both original failures and checks restricted-role collection,
UTC/Honolulu/Tokyo equivalence, invalid/stale/future samples, member/write denial,
existing consumers and permission deactivation/restoration. The recovery SQL
fixtures are exact counterparts of the prepared G046 packet templates; no
production connection is accepted by these fixtures.

Review the dated synthetic job with its fixture clock, source qualification and
unchanged wire hash. Next acceptance requires separately selected target schema
and role verification, source deployment with flags off, a real dated draft-only
exchange, and complete copy/editorial/renderer acceptance. No inference about
present source coverage follows from synthetic fixtures. Product/research work
continues alongside acquisition-system work; this is an input-integrity step,
not a profitability gate.

## Relevant guidance

The distinction between column grants and row policies follows [PostgreSQL 17 row
security](https://www.postgresql.org/docs/17/ddl-rowsecurity.html). Explicit UTC
conversion follows [PostgreSQL date/time operators](https://www.postgresql.org/docs/17/functions-datetime.html).
The Supabase changelog was reviewed for this local SQL change; no relevant
breaking change to these PostgreSQL primitives was identified. No extension,
Data API, Realtime or authentication change is part of G046.

## G053 additive history and publication boundary

Migration `20260924145345_earthscope_complete_public_copy_history.sql` follows the unchanged queue migration and revised G046 migration. Its history-view addition preserves the fixed public/default filter and only appends named text columns. New consumers fail if that projection is not installed; they do not silently return empty repetition context. Existing stored queue facts remain immutable and are reused by version on retry. The same migration adds a separate cloud-only Meta delivery-intent table, never readable/writable by the Mac or queue roles; see the local-primary contract for its at-most-one automatic attempt behavior. This table does not expand preparer privileges.
