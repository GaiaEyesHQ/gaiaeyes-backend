# Render Deployment

## What is hosted on Render
- **Backend API**: FastAPI (`app.main:app`) built as a web service.
- **Cron jobs / workers**: not defined in repo, but implied by scripts/ and workers/ (see `docs/OPEN_QUESTIONS.md`).

## Build + start commands (in repo)
- **Dockerfile** builds a Python 3.11 image and runs `uvicorn app.main:app --host 0.0.0.0 --port 8080`.
- **Procfile** defines `web: uvicorn app:app --host 0.0.0.0 --port=${PORT:-8000}` for non-Docker deployments.
- **runtime.txt** specifies `python-3.11.9`.

## Deploy pipeline
- There is no `render.yaml` in the repo, so the Render dashboard likely defines services, env vars, and cron schedules manually.
- Most scheduled ingestion and publishing runs via GitHub Actions workflows; see `docs/GITHUB_ACTIONS.md`.

## Environment variables
See `docs/ENVIRONMENT_VARIABLES.md` for required env vars (DATABASE_URL, SUPABASE_JWT_SECRET, etc).

## Missing Render details
See `docs/OPEN_QUESTIONS.md` for gaps that must be confirmed in the Render dashboard (service names, build settings, cron jobs, etc.).
