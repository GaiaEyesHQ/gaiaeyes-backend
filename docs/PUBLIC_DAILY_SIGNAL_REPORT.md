# Gaia Eyes Daily Signal Report

This pipeline builds a broad public report. It does not read user locations, symptoms, wearables, or personal patterns.

## Public flow

1. Regional Watch
2. Space Watch
3. Earth Signal
4. Major Events, only when selected events qualify

The public name is `Gaia Eyes Daily Signal Report`. Existing `earthscope` code, API fields, and publishing workflows remain unchanged during shadow review.

## Inputs

- 120 fixed public anchors: three anchors across each of 40 broad regions.
- OpenWeather current weather and air pollution.
- Google Pollen when configured and supported.
- `marts.space_weather_daily`.
- `marts.schumann_daily_v2` or `marts.schumann_daily`.
- `marts.ulf_context_5m`.
- `ext.global_hazards`, which already combines GDACS/USGS-style hazard ingestion.

Regional copy requires at least two anchors in the same region to support the same driver. A single sample does not qualify a region. Major Events excludes informational alerts and is capped after severity sorting and deduplication.

## Shadow command

The command below reads providers and the database, calls the configured public OpenAI writer, and writes a local review artifact. It does not write to Supabase content tables or publish to Meta.

```bash
venv/bin/python -m bots.public_signal_report.shadow --date YYYY-MM-DD
```

For fixture-only verification without OpenAI:

```bash
venv/bin/python -m bots.public_signal_report.shadow \
  --date YYYY-MM-DD \
  --observations-fixture path/to/observations.json \
  --context-fixture path/to/context.json \
  --no-writer
```

Artifacts default to `tmp/public_signal_report/<day>.json` and always contain `auto_publish: false`.

The writer uses a strict JSON schema and validates platform word ranges. A draft that misses those ranges receives one complete model revision; a second failure is stored as `invalid` with no platform copy applied to the report. The runner never repairs copy with phrase replacements.

## Promotion boundary

Do not connect this report to `content.daily_posts`, `/v1/features/today`, the website, reel rendering, or Meta publishing until at least seven shadow reports have been reviewed. Promotion should preserve the existing caption and section fields while adding the structured report under `metrics_json.sections.daily_signal_report`.
