# Dashboard Gauges + Member EarthScope

This document describes the backend groundwork for the predictive gauges and the paid member EarthScope writer.

## Definition Base (JSON v1)
- File: `bots/definitions/gauge_logic_base_v1.json`
- Loader: `bots/definitions/load_definition_base.py`
- Required keys:
  - `version`
  - `global_disclaimer`
  - `confidence_multiplier`
  - `gauges`
  - `effect_tags`
  - `scoring_model`
  - `signal_definitions`
  - `alert_pills`
  - `writer_outputs`

The loader validates these keys and returns `(definition_obj, version)` for downstream jobs.

## Location Context Snapshot Job
- Script: `bots/gauges/location_context_job.py`
- Source: `app.user_locations` (primary row if present)
- Target: `marts.user_location_context_day`
- Upsert key: `(user_id, day)`
- Behavior:
  - If a primary row exists, store `zip`, `lat`, `lon`, `source='primary'`
  - If no primary row, upsert `source='none'` with empty location fields

## Signal Resolver
- Module: `bots/gauges/signal_resolver.py`
- Core signals detected:
  - Pressure swing (12h preferred, 24h fallback)
  - Temperature swing (24h)
  - AQI bucket (moderate/usg/unhealthy)
  - Kp (now or 24h max)
  - Bz coupling (active/strong)
  - Schumann variability (24h stddev, threshold-controlled)
  - Full moon window (≤2 days)

Notes:
- `SCHUMANN_STDDEV_THRESHOLD` can be set to enable the Schumann variability trigger if the definition JSON does not include a numeric threshold.
- If local payloads do not expose 12h deltas, the resolver uses 24h pressure deltas as a fallback.

## Gauge Scorer
- Module: `bots/gauges/gauge_scorer.py`
- Job runner: `bots/gauges/gauge_scoring_job.py`
- Target: `marts.user_gauges_day`
- Upsert key: `(user_id, day)`
- Stored columns (expected):
  - `pain`, `focus`, `heart`, `stamina`, `energy`, `sleep`, `mood`, `health_status`
  - `trend_json`, `alerts_json`, `inputs_hash`, `model_version`

Scoring rules:
- Base score + per-signal weights
- Confidence multiplier applied per signal
- Cap per signal (from definition JSON)
- Clamp to 0–100

Idempotency:
- `inputs_hash = sha256(json.dumps(inputs_snapshot, sort_keys=True))`
- If the stored hash matches, updates are skipped unless `force=true`.

## Health Status Gauge (v1.1)
- Baseline window: 30 days (excluding current day), minimum 14 usable days.
- Metrics: sleep minutes/efficiency/deep, SpO2, hr_max, steps, optional BP + HRV.
- Z-score per metric, clamp to [-3, 3], convert to “bad” direction, then weighted sum.
- `health_status = min(100, round(load_raw * 30, 0))`
- Symptom overlay: add `min(15, max_severity * 1.5)` when present.
- If baseline is insufficient, `health_status = null` and an alert pill is added:
  - `alert.health_calibrating` (severity `info`)
- HRV auto-upgrades when data appears (from `marts.daily_features.hrv_avg`, or fallback `gaia.daily_summary` / `gaia.samples` if present).

## Member EarthScope Writer
- Script: `bots/earthscope_post/member_earthscope_generate.py`
- Output table: `content.daily_posts_user`
- Upsert key: `(user_id, day, platform='member')`
- Uses OpenAI if `OPENAI_API_KEY` is set; otherwise falls back to a deterministic template.
- Inputs:
  - Gauge row (`marts.user_gauges_day`)
  - Active states (signal resolver)
  - Local payload (`app.get_local_signals_for_user`)
  - User tags + symptom summary

Environment:
- `SUPABASE_DB_URL` (required)
- `OPENAI_API_KEY` (optional)
- `OPENAI_MODEL_MEMBER_WRITER` (optional)
- `OPENAI_MODEL_PUBLIC_WRITER` (optional)
- `OPENAI_MODEL_DEFAULT` (optional fallback)
- `OPENAI_MODEL` / `GAIA_OPENAI_MODEL` (legacy fallback)
- `ENTITLEMENT_KEYS` (optional, default `plus,pro`)

## Hybrid Triggers (Alerts + Member Updates)
- Trigger engine: `bots/triggers/run_trigger_engine.py`
- Source: `marts.user_gauges_day.alerts_json` + `health_status`
- State table: `app.user_trigger_state` (cooldown + escalation)
- Default cooldowns:
  - info: 12h
  - watch: 6h
  - high: 3h
- Escalation-only: triggers fire immediately if severity increases

When trigger events are detected for paid users, the engine appends a “Triggered Advisory” section to the member EarthScope post for that day.

## FastAPI Endpoints
- `GET /v1/dashboard`
  - Uses `app.get_dashboard_payload(day)` RPC
  - Requires read auth and a valid `user_id` in request context
- `GET /v1/earthscope/member`
  - Returns member EarthScope for the authenticated user + day
- `POST /v1/earthscope/member/regenerate`
  - Recomputes gauges + member post for the authenticated user
  - Requires write auth and active entitlements

## GitHub Actions
Workflow: `.github/workflows/gauges_and_member_writer_daily.yml`

Runs daily:
1) `python bots/gauges/location_context_job.py`
2) `python bots/gauges/gauge_scoring_job.py`
3) `python bots/earthscope_post/member_earthscope_generate.py`

Manual trigger is available via `workflow_dispatch`.

## Local Test Checklist
1) `python bots/gauges/location_context_job.py`
2) `python bots/gauges/gauge_scoring_job.py --user-id <uuid>`
3) `python bots/earthscope_post/member_earthscope_generate.py --user-id <uuid>`
4) `curl -H "Authorization: Bearer <token>" -H "X-Dev-UserId: <uuid>" "$BASE/v1/dashboard"`
5) `curl -H "Authorization: Bearer <token>" -H "X-Dev-UserId: <uuid>" "$BASE/v1/earthscope/member"`
