# Social Alerts Asset Bootstrap Pack

This pack keeps Social Alerts moving when custom Photoshop backgrounds are not ready yet. The goal is simple: every reviewable alert draft can render a usable square, feed, and story/reel frame with no uploaded background assets.

## What It Does

- Keeps existing Supabase background paths first, so custom art still wins when uploaded.
- Adds deterministic generated backgrounds under `bootstrap:social_alerts/{name}`.
- Uses category-aware palettes for Schumann, solar, CME, geomagnetic, weather, migraine/head pressure, air quality, and exposure-style alerts.
- Adds prompt notes to each overlay spec so future hand-made or AI-generated backgrounds can follow the same visual direction.
- Does not auto-publish. Social Alerts remain shadow/review mode.

## Bootstrap Backgrounds

| Candidate | Best for |
| --- | --- |
| `bootstrap:social_alerts/resonance_field` | Schumann, resonance, ULF, frequency alerts |
| `bootstrap:social_alerts/nervous_system_static` | HRV, sleep, focus, restlessness, nervous-system hooks |
| `bootstrap:social_alerts/migraine_pressure` | Migraine, headache, sinus pressure, pressure swings |
| `bootstrap:social_alerts/solar_aurora` | Kp, Bz, solar wind, geomagnetic activity |
| `bootstrap:social_alerts/solar_heat` | Solar flare / X-ray activity |
| `bootstrap:social_alerts/cme_wave` | CME and solar-wind movement |
| `bootstrap:social_alerts/air_quality_haze` | AQI, smoke, haze |
| `bootstrap:social_alerts/weather_pressure` | Humidity, temperature, local weather pressure |
| `bootstrap:social_alerts/exposure_indoor` | Exposure diary / indoor trigger themes |
| `bootstrap:social_alerts/earthscope_cosmic` | General Gaia Eyes / EarthScope pattern posts |

## Lookup Order

Social Alerts now prefer backgrounds in this order:

1. `social/share/backgrounds/{keyword}.jpg` in the `space-visuals` bucket.
2. `bootstrap:social_alerts/{name}` generated backgrounds.
3. Local media repo backgrounds from `gaiaeyes-media/backgrounds/{square,tall}`.
4. Live/still fallback candidates such as NASA or Schumann latest images.
5. Generic generated gradient fallback if everything else fails.

The app share resolver already supports `.jpg`, `.png`, `.jpeg`, and `.webp` for Supabase share backgrounds. The Social Alerts local media picker currently checks `.jpg`, `.jpeg`, and `.png`.

## Preview Locally

Generate shadow drafts from an existing snapshot:

```bash
python -m bots.social_alerts.shadow_drafts \
  --input tmp/social_alerts_shadow/latest-snapshot.json \
  --output tmp/social_alerts_shadow/drafts.json \
  --review-output auto
```

Render previews:

```bash
python -m bots.social_alerts.preview_renderer \
  --input tmp/social_alerts_shadow/drafts.json \
  --output-dir tmp/social_alerts_shadow/previews
```

Rendered files land in `tmp/social_alerts_shadow/previews/` with a `preview-manifest.json`.

## Uploading Custom Art Later

When you are ready to replace generated backgrounds, upload images to:

```text
space-visuals/social/share/backgrounds/{keyword}.jpg
```

Recommended first uploads:

```text
schumann.jpg
earthscope.jpg
space_weather.jpg
solar_flare.jpg
cme.jpg
pressure.jpg
humidity.jpg
aqi.jpg
migraine.jpg
exposure.jpg
```

Keep text, dates, stats, and logos out of the uploaded background. The renderer owns those overlays.
