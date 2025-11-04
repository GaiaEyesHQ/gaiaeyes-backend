# Gaia Eyes Backend (FastAPI)

## Quickstart
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # then edit values
uvicorn app.main:app --reload

## Symptoms pipeline

The `/v1/symptoms` FastAPI routes expose the complete symptom logging workflow.
Clients can POST new events, fetch the current day's entries, and retrieve
aggregated daily counts. A nightly Render cron (or equivalent scheduler) should
invoke `scripts/refresh_symptom_marts.py` to refresh the Supabase marts backing
the analytics endpoints.

## Tooling

- [GitHub Actions audit playbook](./docs/github-actions-audit.md)
- [Web site overview & maintenance guide](./docs/web/SITE_OVERVIEW.md)
- [Supabase Migration Guide](./supabase/README.md)

### GitHub Actions audit helpers

- `scripts/audit_workflows.py` – Query the GitHub API for workflow health
  across GaiaEyes repositories, gather failure summaries, and produce a
  Markdown report with referenced secrets and variables.
- `scripts/scan-secrets.sh` – Quickly list `${{ secrets.* }}` and `${{ vars.* }}`
  usages within the repository to keep `REQUIRED_SECRETS.md` accurate.

Run these tools whenever workflows are updated or new repositories are
added to GaiaEyesHQ to maintain an up-to-date inventory of required
secrets and configuration knobs.
