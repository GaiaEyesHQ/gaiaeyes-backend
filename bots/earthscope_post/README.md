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