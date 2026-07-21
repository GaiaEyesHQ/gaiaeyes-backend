# Gaia Eyes Health Snapshot

This pipeline builds a broad public report. It does not read user locations, symptoms, wearables, or personal patterns.

## Public flow

1. Regional Watch
2. Space Watch
3. Earth Signal
4. Major Events, only when selected events qualify

The collector supports two editions from the same global observation set:

- `Gaia Eyes U.S. Health Snapshot` includes the 14 U.S. regions. Foreign hazards are excluded unless structured country metadata explicitly marks U.S. impact.
- `Gaia Eyes Global Health Snapshot` keeps the full 40-region view, including Asia, South America, Australia, and the Philippines.

The U.S. edition does not infer cross-border impact from a title or location string. Canada or Mexico should enter U.S. public copy only after the source provides structured evidence that the condition affects the United States. Existing `earthscope` code, API fields, and publishing workflows remain unchanged during shadow review.

## Publishing lanes

This report is additive. Promotion must create a separate Regional Watch post and schedule; it must not replace, rename, or absorb the existing daily space-weather Signal Watch post. The two public posts should run several hours apart so each has its own audience and distribution window. Exact timing remains a review decision and is not configured by the shadow runner.

## Inputs

- 120 fixed public anchors: three anchors across each of 40 broad regions.
- OpenWeather current weather and air pollution.
- Google Pollen when configured and supported.
- `marts.space_weather_daily`.
- Latest usable `marts.schumann_daily_v2` harmonics, falling back to the latest valid station-average from `marts.schumann_daily`.
- `marts.ulf_context_5m`.
- `ext.global_hazards`, which already combines GDACS/USGS-style hazard ingestion.

Regional copy requires at least two anchors in the same region to support the same driver. A single sample does not qualify a region. Major Events excludes informational alerts and is capped after severity sorting and deduplication.

## Shadow command

The command below reads providers and the database, calls the configured public OpenAI writer, and writes a local review artifact. It does not write to Supabase content tables or publish to Meta.

```bash
venv/bin/python -m bots.public_signal_report.shadow --date YYYY-MM-DD
```

Generate the U.S. edition from the same global collection and context:

```bash
venv/bin/python -m bots.public_signal_report.shadow \
  --date YYYY-MM-DD \
  --edition us
```

For shadow-only model comparisons, pass `--model MODEL_NAME`. This overrides the configured public writer only for that artifact and does not change production environment settings.

For fixture-only verification without OpenAI:

```bash
venv/bin/python -m bots.public_signal_report.shadow \
  --date YYYY-MM-DD \
  --observations-fixture path/to/observations.json \
  --context-fixture path/to/context.json \
  --no-writer
```

Global artifacts default to `tmp/public_signal_report/<day>.json`; U.S. artifacts default to `tmp/public_signal_report/<day>-us.json`. Both retain every collected observation under `review_inputs`, while the report and writer facts contain only edition-qualified regions and events. Artifacts always contain `auto_publish: false`.

The writer uses a strict JSON schema and validates platform word ranges. It also returns a five-beat reel story: body-first hook, strongest regions, supported drivers, supported effects, and summary. Non-hook slides must be complete sentences, and near-duplicate slides are rejected. A draft that misses those requirements receives one complete model revision; a second failure is stored as `invalid` with no platform copy applied to the report. The runner never repairs copy with phrase replacements.

## U.S. reel preview and visual preflight

Render the five U.S. slides, a silent-audio MP4 preview, sampled video frames, and a fail-closed preflight manifest:

```bash
venv/bin/python -m bots.public_signal_report.reel_renderer \
  --input tmp/public_signal_report/YYYY-MM-DD-us.json \
  --output-dir tmp/public_signal_report/YYYY-MM-DD-us-reel
```

The renderer prefers blank local assets named `health_snapshot_1` through `health_snapshot_5` when `--background-dir DIR` is supplied. It accepts `.jpg`, `.jpeg`, `.png`, and `.webp`. Each slide must resolve to a different source. Finished EarthScope cards are not background candidates. When custom assets are unavailable, the renderer uses five distinct Social Alerts bootstrap backgrounds.

The visual preflight checks:

- exactly five 1080x1920 slides;
- every source word preserved after wrapping;
- text bounding boxes inside the Meta-safe area;
- distinct background sources and nonblank slide pixels;
- one 1080x1920 H.264 video stream and one AAC audio stream;
- minimum reel duration and five nonblank, visually distinct sampled frames.

The MP4 contains a silent audio placeholder for visual review. VO and music remain a separate promotion step. The command exits nonzero when preflight fails and always keeps publishing disconnected.

## Promotion boundary

Do not connect this report to `content.daily_posts`, `/v1/features/today`, the website, reel rendering, or Meta publishing until at least seven shadow reports have been reviewed. Promotion must use a new post identity and schedule, preserve the existing space-weather Daily Signal post unchanged, and keep any structured report data separate from the current EarthScope fields.
