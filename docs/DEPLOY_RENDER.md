# Render Deployment

## What is hosted on Render
- **Backend API**: FastAPI (`app.main:app`) built as a web service.
- **Ingest queue worker**: optional worker service for Redis-backed health ingest overflow (`python workers/ingest_queue_worker.py`).
- **Other cron jobs / workers**: implied by scripts/ and workers/ (see `docs/OPEN_QUESTIONS.md`).

## Build + start commands (in repo)
- **Dockerfile** builds a Python 3.11 image and runs `uvicorn app.main:app --host 0.0.0.0 --port 8080`.
- **Procfile** defines `web: uvicorn app:app --host 0.0.0.0 --port=${PORT:-8000}` for non-Docker deployments.
- **runtime.txt** specifies `python-3.11.9`.

## Deploy pipeline
- There is no `render.yaml` in the repo, so the Render dashboard likely defines services, env vars, and cron schedules manually.
- Most scheduled ingestion and publishing runs via GitHub Actions workflows; see `docs/GITHUB_ACTIONS.md`.

## Environment variables
See `docs/ENVIRONMENT_VARIABLES.md` for required env vars (DATABASE_URL, SUPABASE_JWT_SECRET, etc).

For a launch burst, set these on the backend web service:
- `GAIA_INGEST_QUEUE_ENABLED=1`
- `GAIA_INGEST_MAX_ACTIVE_WRITES=4`
- `DB_POOL_MAX_SIZE=8`

To enable the durable queue, create a Render Key Value/Redis service, set `REDIS_URL` on both the
web service and worker, set `GAIA_INGEST_REDIS_QUEUE_ENABLED=1` on the web service, and run the
worker command:
```
python workers/ingest_queue_worker.py
```

## Missing Render details
See `docs/OPEN_QUESTIONS.md` for gaps that must be confirmed in the Render dashboard (service names, build settings, cron jobs, etc.).
