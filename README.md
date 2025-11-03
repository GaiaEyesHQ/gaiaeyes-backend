# Gaia Eyes Backend (FastAPI)

## Quickstart
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # then edit values
uvicorn app.main:app --reload

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
