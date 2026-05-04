# Social Alerts Shadow Review

- Mode: `shadow`
- Auto publish: `False`
- Generated at: `2026-05-03T21:39:15Z`
- Draft count: `2`

## 1. Global hazards are active

- Category: `global_hazard`
- Severity: `high`
- Review status: `needs_human_review`
- As of: `2026-05-03T21:39:15Z`

Caption:

```text
Global hazards are active. Share only verified location and advisory context from official feeds. Open Gaia Eyes for the full signal read.

#GaiaEyes #SpaceWeather #EarthSignals
```

Metrics:
- `notable_count`: `10`
- `high_count`: `2`

Background candidates:
- `social/share/backgrounds/hazards.jpg`
- `social/share/backgrounds/earthscope.jpg`

Background keywords:
- `hazards`
- `earthscope`

Still candidates:
- `none`: `--`

Reel video candidates:
- `none`: `--`

Visual style:
- Layout: `background_image_with_flowing_pill_blocks`
- Notes: Use a dark, cinematic background with translucent rounded metric pills and small glass blocks that match the Gaia Eyes app style.

Sources:
- Global hazards brief: `/v1/hazards/brief`
- GDACS hazards: `/v1/hazards/gdacs/full`

## 2. CME activity is on the board

- Category: `cme`
- Severity: `watch`
- Review status: `needs_human_review`
- As of: `2026-05-03T21:39:15Z`

Caption:

```text
CME activity is on the board. Review coronagraph and ENLIL context before sharing. Open Gaia Eyes for the full signal read.

#GaiaEyes #SpaceWeather #EarthSignals
```

Metrics:
- `cmes_count`: `1.0`
- `cmes_max_speed_kms`: `None`

Background candidates:
- `social/share/backgrounds/cme.jpg`
- `social/share/backgrounds/space_weather.jpg`
- `social/share/backgrounds/solar_wind.jpg`
- `nasa/ccor1/latest.jpg`

Background keywords:
- `cme`
- `space_weather`
- `solar_wind`

Still candidates:
- `nasa/ccor1/latest.jpg`
- `nasa/enlil/latest.jpg`

Reel video candidates:
- `nasa/ccor1/latest.mp4`
- `nasa/enlil/latest.mp4`

Visual style:
- Layout: `background_image_with_flowing_pill_blocks`
- Notes: Use a dark, cinematic background with translucent rounded metric pills and small glass blocks that match the Gaia Eyes app style.

Sources:
- CCOR-1: `nasa/ccor1/latest.mp4`
- ENLIL: `nasa/enlil/latest.mp4`
