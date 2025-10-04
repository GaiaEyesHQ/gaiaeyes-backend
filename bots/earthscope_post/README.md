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

Gaia Eyes is an iOS app (SwiftUI) that combines **health metrics**, **space weather**, and **Earthscope insights** into a comprehensive daily dashboard with enhanced visualizations and detailed insights.

---

## Features

### Sleep
- Displays total sleep in hours and minutes (e.g. `7h 9m total`).
- Detailed stage breakdowns including REM, Core, Deep, and In Bed times.
- Auto-sync fallback: if today’s sleep equals 0, triggers a 2-day sleep sync and refetch.

### Health Stats
- Shows Steps, Heart Rate minimum and maximum, HRV, SpO₂, and average Blood Pressure.
- Color-coded cues for quick assessment:
  - Steps ≥ 8000 → green
  - Heart Rate min ≤ 50 → blue
  - Heart Rate max ≥ 120 → red
  - HRV ≥ 80 → green
  - SpO₂ < 95% → red
  - Blood Pressure averages outside normal range → yellow/red as appropriate

### Space Weather
- Organized into clear sections with compact **StatPills** for readability:
  - Kp index: current and maximum values
  - Bz component: current and minimum values
  - Solar Wind speed: average and current
  - Flares and CMEs counts
  - Schumann resonance frequencies f0 through f4

### Earthscope
- **Card view**:
  - Uses a daily random square background image selected from `/backgrounds/square/manifest.json`.
  - Background blur set to 8 with opacity 0.45 for subtle visual effect.
  - “Read more” link is larger, bold, and spaced below content for better accessibility.
  - Thumbnails have added padding for improved breathing room.
- **Detail (Read More) view**:
  - Displays a daily random tall background from `/backgrounds/tall/manifest.json` with a fallback image `earth_space_tall.jpg`.
  - Background blur set to 2 with opacity 0.70 and a subtle vignette overlay.
  - Body text softened with rgba(220,220,235,0.88) and line height of 1.6 for comfortable reading.
  - Markdown content is converted to HTML with enhanced styling:
    - Headings: `##` → `<h2>`, `###` → `<h3>`
    - Lists:
      - Numbered (`1.`) → `<ol>`
      - Dashed (`- item`) and asterisk (`* item`) → `<ul>`
  - All hashtags are stripped from the detail view content for clarity.

### Space Alerts
- Small card displays warnings prominently when solar flares count is greater than 0 or Kp index is 5 or higher, alerting users to significant space weather events.

### Weekly Trends
- Provides graphical representations of key metrics over the past week:
  - Heart Rate timeseries with min/max and average lines
  - Kp index trends
  - Bz component trends
  - Schumann resonance frequency f0 trends
- Includes legends, counts, and indicators of improvements or declines for easy interpretation.

### Debug / Status
- The Status card has been removed from the main view for a cleaner interface.
- Now accessible under the Debug panel within a DisclosureGroup labeled "Status".
- Debug panel also contains Logs and manual sync buttons for developer use.

---

## Fonts
Custom fonts are loaded via `/fonts/` (hosted on GitHub Pages):
- AbrilFatface-Regular.ttf
- BebasNeue.ttf
- ChangaOne-Regular.ttf
- Oswald-VariableFont_wght.ttf
- **Poppins-Regular.ttf** (corrected from previous typo with extra `t` in the filename)

---

## Dev Notes
- Background images rotate daily using `manifest.json` files.
- Earthscope card backgrounds use square images; the Read More detail view uses tall images.
- Markdown parsing has been improved for better HTML conversion and styling.
- When starting a new ChatGPT conversation, include this README at the top to maintain context.

---

## Roadmap / Next
- [ ] Sync square and tall backgrounds by matching names (e.g. `aurora_square` → `aurora_tall`).
- [ ] Improve Markdown parser or migrate to server-side HTML generation for enhanced formatting.
- [ ] Add pinch-zoom functionality for the Earthscope image viewer.
- [ ] Display updated timestamps on cards to indicate data freshness.