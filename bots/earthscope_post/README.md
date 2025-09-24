# Earthscope Post Bot (LLM)

- Reads `marts.space_weather_daily` (+ optional `ext.donki_event`)
- Fetches 2–3 trending references (SolarHam, SpaceWeather, NASA, HeartMath)
- Calls OpenAI to generate rich Daily Earthscope (sections + hashtags)
- Upserts into `content.daily_posts` (idempotent)
- Dry run: set `DRY_RUN=true`

## Env
- `SUPABASE_DB_URL` (pooled, ssl)
- `OPENAI_API_KEY`
- `OPENAI_MODEL` (default `gpt-4o-mini`)
- `PLATFORM` (default `instagram`)
- `USER_ID` (optional UUID; empty = global)
- (optional) `TREND_*` URLs to override default sources

# Gaia Eyes App

**Decode the unseen.**

Gaia Eyes is an iOS app (SwiftUI) that combines **health metrics**, **space weather**, and **Earthscope insights** into a daily dashboard.

---

## Features

### Sleep
- Sleep card shows **total sleep in hours + minutes** (e.g. `7h 9m total`).
- Stage breakdowns (REM / Core / Deep / In Bed) in minutes.
- Auto-sync fallback: if today’s sleep = 0, trigger a 2-day sleep sync and refetch.

### Health Stats
- Displays Steps, HR min, HRV, SpO₂.
- Color cues:
  - Steps ≥ 8000 → green
  - HR min ≤ 50 → blue
  - HRV ≥ 80 → green
  - SpO₂ < 95% → red

### Space Weather
- Split into three rows for clarity:
  - Row 1: Kp, Bz, Solar Wind speed
  - Row 2: Flares, CMEs
  - Row 3: Schumann station + f0/f1/f2
- Compact **StatPills** with scaling to avoid overflow.

### Earthscope
- **Card**:
  - Daily random **square background** from `/backgrounds/square/manifest.json`.
  - Background blur: 8, opacity: 0.45.
  - “Read more” link larger, bold, with spacing below.
  - Thumbnails padded down for breathing room.
- **Detail (Read More)**:
  - Daily random **tall background** from `/backgrounds/tall/manifest.json`; fallback = `earth_space_tall.jpg`.
  - Background blur: 2, opacity: 0.70, with subtle vignette.
  - Body text softened (rgba 220,220,235,0.88), line height 1.6.
  - Markdown → HTML:
    - Headings: `##` → `<h2>`, `###` → `<h3>`
    - Lists:
      - Numbered (`1.`) → `<ol>`
      - Dashed (`- item`) → `<ul>`
      - Asterisk (`* item`) → `<ul>`
  - Hashtags stripped everywhere.

### Debug / Status
- Status card removed from main view.
- Now shown under Debug panel → DisclosureGroup("Status").
- Debug panel also includes Logs + manual sync buttons.

---

## Fonts
Custom fonts loaded via `/fonts/` (GitHub Pages):
- AbrilFatface-Regular.ttf
- BebasNeue.ttf
- ChangaOne-Regular.ttf
- Oswald-VariableFont_wght.ttf
- **Poppins-Regular.tttf** (note extra `t` in filename; fix later to `.ttf`)

---

## Dev Notes
- Backgrounds rotate daily using `manifest.json`.
- Earthscope card = square backgrounds; Read More = tall backgrounds.
- When starting a new ChatGPT conversation, paste this README at the top so context isn’t lost.

---

## Roadmap / Next
- [ ] Format stage breakdowns (REM/Core/Deep) as `Xh Ym` when >60m.
- [ ] Sync square/tall backgrounds by name (e.g. `aurora_square` → `aurora_tall`).
- [ ] Add pinch-zoom for Earthscope image viewer.
- [ ] Improve Markdown parser or move to server-side HTML generation.