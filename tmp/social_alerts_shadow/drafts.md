# Social Alerts Shadow Review

- Mode: `shadow`
- Auto publish: `False`
- Generated at: `2026-07-02T19:58:50Z`
- Draft count: `2`

## 1. Solar motion watch

- Category: `cme`
- Severity: `watch`
- Review status: `needs_human_review`
- As of: `2026-07-01 15:09:32.083131+00:00`

Post caption copy:

```text
Solar motion watch. CME activity is present; review coronagraph context and compare body-pattern notes before posting. Compare this with sleep, HRV, symptoms, and exposures in Gaia Eyes.

#GaiaEyes #SpaceWeather #EarthSignals
```

Metrics:
- `cmes_count`: `1.0`
- `cmes_max_speed_kms`: `None`

Background candidates:
- `social/share/backgrounds/cme.jpg`
- `social/share/backgrounds/space_weather.jpg`
- `social/share/backgrounds/solar_wind.jpg`
- `bootstrap:social_alerts/cme_wave`
- `bootstrap:social_alerts/solar_aurora`
- `bootstrap:social_alerts/earthscope_cosmic`
- `nasa/ccor1/latest.jpg`
- `nasa/enlil/latest.jpg`

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

## 2. Geomagnetic pattern watch

- Category: `geomagnetic`
- Severity: `watch`
- Review status: `needs_human_review`
- As of: `2026-07-01 15:09:32.083131+00:00`

Post caption copy:

```text
Geomagnetic pattern watch. Kp/Bz and solar wind are active enough to compare with body-pattern notes before posting. Compare this with sleep, HRV, symptoms, and exposures in Gaia Eyes.

#GaiaEyes #SpaceWeather #EarthSignals
```

Metrics:
- `kp`: `2.0`
- `kp_max_24h`: `4.67`
- `bz_nt`: `3.9`
- `solar_wind_kms`: `430.0`

Background candidates:
- `social/share/backgrounds/space_weather.jpg`
- `social/share/backgrounds/kp.jpg`
- `social/share/backgrounds/bz.jpg`
- `social/share/backgrounds/solar_wind.jpg`
- `bootstrap:social_alerts/solar_aurora`
- `bootstrap:social_alerts/cme_wave`
- `bootstrap:social_alerts/earthscope_cosmic`
- `nasa/geospace_3h/latest.jpg`
- `+2 more in overlay_spec`

Background keywords:
- `space_weather`
- `kp`
- `bz`
- `solar_wind`

Still candidates:
- `none`: `--`

Reel video candidates:
- `none`: `--`

Visual style:
- Layout: `trust_first_alert_card`
- Notes: Use a dark navy/black gradient, subtle spectrogram texture, small Gaia Eyes branding, one glass text panel, up to eight context chips, and no more than two metrics.

Sources:
- SWPC space weather: `space_weather.now`
- Space daily mart: `marts.space_weather_daily`
