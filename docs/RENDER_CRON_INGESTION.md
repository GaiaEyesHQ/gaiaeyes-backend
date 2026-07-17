# Render Cron Ingestion

Gaia Eyes uses three bounded Render cron lanes plus the existing continuous
HealthKit queue worker. The Blueprint is intentionally separate from the
manually managed web service, worker, and Valkey instance:

- Blueprint: `render-crons.yaml`
- Runner: `scripts/run_render_cron.py`

## Cadence

| Service | UTC schedule | Responsibility |
| --- | --- | --- |
| `gaiaeyes-critical-ingestion` | every 15 minutes | Current Kp/wind/Bz/density, live space context, ULF, direct Schumann extraction + DB write, local current conditions, current space rollup, gauge-only scoring |
| `gaiaeyes-event-ingestion` | every 2 hours at minute 13 | Earthquakes, global hazards, flare/CME events |
| `gaiaeyes-daily-derivations` | daily at 10:35 UTC | Local and space forecasts, health reconciliation, daily features, location context, gauges, patterns |
| `gaiaeyes-ingest-worker` | continuous/event-driven | HealthKit sample queue; refreshes the affected user's daily marts and gauges after ingestion |

All Drivers is assembled on request from these current sources. It does not
need its own scheduled writer. Dashboard and Drivers responses retain their
five-minute in-process cache, so a newly ingested global reading can take up to
about five additional minutes to appear in an already-running web instance.

The existing push evaluator/sender schedules remain separate. The member
writer and trigger engine remain in their existing daily workflow; they are not
part of the frequent gauge lane.

## Environment wiring

The Blueprint inherits existing values from the `gaiaeyes-backend` Render web
service. It does not commit credentials. After rotating a referenced Render
secret, sync the Blueprint so the references are refreshed.

The current web service has AirNow, NASA, Supabase, SuperMAG, and weather user
agent variables. `GOOGLE_POLLEN_API_KEY` is optional and is not currently
defined on that service; add it to the critical and daily cron services (or a
shared environment group) if Google Pollen coverage is required.

## Safe cutover

1. Deploy the code and create the Blueprint using `render-crons.yaml` as the
   Blueprint path.
2. Trigger each cron manually once. Confirm each runner step exits zero.
3. Observe at least four critical cycles. Confirm current-source timestamps are
   no more than 15 minutes old and database/pool metrics remain stable.
4. Only then remove the overlapping GitHub `schedule:` triggers while retaining
   `workflow_dispatch` as a manual fallback.
5. Keep the space and Schumann media-publishing workflows if the website/social
   JSON and imagery still depend on `gaiaeyes-media`; switch their database
   writes off rather than removing media publication.

## GitHub schedule cutover

After the first automatic daily run and the post-cutover observation window
completed on 2026-07-13, scheduled execution moved to Render for these
database-only workflows. Each workflow retains `workflow_dispatch` as a manual
fallback:

- `ingest_space_forecasts.yml`
- `quakes_ingest.yml`
- `local_health_signals.yml`
- `health-daily-rollup.yml`
- `daily-features-rollup.yml`
- `space-weather-daily-rollup.yml`

GitHub schedules that still publish media, run monitoring, send notifications,
or generate member/social content remain enabled.

Render guarantees at most one active run for a given cron service. The runner
also executes steps sequentially and reports a non-zero lane exit if any step
fails, while allowing independent later steps to complete.

Gauge scoring remains sequential, but it reuses one bounded database connection
per user. This keeps connection setup from growing with every scoring query
while avoiding a single long-lived connection across the full user batch.

## Dry-run verification

```bash
python scripts/run_render_cron.py critical --dry-run
python scripts/run_render_cron.py events --dry-run
python scripts/run_render_cron.py daily --dry-run
```

The dry run prints command order without fetching upstream data or writing the
database.
