# Social Alerts Shadow Review

- Mode: `shadow`
- Auto publish: `False`
- Generated at: `2026-06-08T04:57:20Z`
- Draft count: `3`

## 1. Wired but tired?

- Category: `schumann`
- Severity: `high`
- Review status: `needs_human_review`
- As of: `2026-06-08T12:00:00Z`

Post caption copy:

```text
Wired but tired?

The Schumann signal is elevated compared with its recent baseline. Some people like to watch these windows alongside sleep quality, HRV dips, brain fog, headaches, and nerve-pain flares.

Gaia Eyes is built for that comparison: not diagnosis, not doom, just pattern tracking across body, space, and Earth signals.

#GaiaEyes #SchumannResonance #BodyPatterns #HRV
```

Metrics:
- `zscore_30d`: `3.2`
- `value_hz`: `7.91`

Background candidates:
- `social/share/backgrounds/schumann.jpg`
- `social/share/backgrounds/earthscope.jpg`
- `schumann/latest/tomsk_share_latest.jpg`
- `social/earthscope/latest/tomsk_share_latest.jpg`

Background keywords:
- `schumann`
- `earthscope`

Still candidates:
- `schumann/latest/tomsk_share_latest.jpg`
- `social/earthscope/latest/tomsk_share_latest.jpg`

Reel video candidates:
- `none`: `--`

Visual style:
- Layout: `trust_first_alert_card`
- Notes: Use a dark navy/black gradient, subtle spectrogram texture, small Gaia Eyes branding, one glass text panel, up to eight context chips, and no more than two metrics.

Sources:
- Tomsk/Cumiana Schumann: `schumann`
- Schumann active state: `active_states.schumann.variability_24h`

## 2. X-class solar flare watch

- Category: `solar_flare`
- Severity: `high`
- Review status: `needs_human_review`
- As of: `2026-06-08T12:00:00Z`

Post caption copy:

```text
X-class solar flare watch. The flare signal is notable; review the live solar context before posting. Open Gaia Eyes for the full signal read.

#GaiaEyes #SpaceWeather #EarthSignals
```

Metrics:
- `xray_max_class`: `X1.2`

Background candidates:
- `social/share/backgrounds/solar_flare.jpg`
- `social/share/backgrounds/space_weather.jpg`
- `nasa/ccor1/latest.jpg`
- `nasa/enlil/latest.jpg`

Background keywords:
- `solar_flare`
- `space_weather`

Still candidates:
- `nasa/ccor1/latest.jpg`
- `nasa/enlil/latest.jpg`
- `nasa/aia_304/latest.jpg`

Reel video candidates:
- `nasa/ccor1/latest.mp4`
- `nasa/enlil/latest.mp4`

Visual style:
- Layout: `trust_first_alert_card`
- Notes: Use a dark navy/black gradient, subtle spectrogram texture, small Gaia Eyes branding, one glass text panel, up to eight context chips, and no more than two metrics.

Sources:
- GOES X-ray: `space_weather.xray_max_class`
- SWPC flare feed: `GOES_XRS_URL`

## 3. CME activity is on the board

- Category: `cme`
- Severity: `watch`
- Review status: `needs_human_review`
- As of: `2026-06-08T12:00:00Z`

Post caption copy:

```text
CME activity is on the board. Review coronagraph and ENLIL context before sharing. Open Gaia Eyes for the full signal read.

#GaiaEyes #SpaceWeather #EarthSignals
```

Metrics:
- `cmes_count`: `1.0`
- `cmes_max_speed_kms`: `720.0`

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
- Layout: `trust_first_alert_card`
- Notes: Use a dark navy/black gradient, subtle spectrogram texture, small Gaia Eyes branding, one glass text panel, up to eight context chips, and no more than two metrics.

Sources:
- CCOR-1: `nasa/ccor1/latest.mp4`
- ENLIL: `nasa/enlil/latest.mp4`
