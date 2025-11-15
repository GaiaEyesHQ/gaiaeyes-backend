# Required secrets and variables

This document tracks GitHub Actions secrets and variables referenced by
this repository as well as the GaiaEyes repos covered by the audit
scripts.

## gaiaeyes-backend (this repo)

The GitHub Actions workflows reference the following secrets. Non-
sensitive entries (if any) should move to repository variables.

| Name | Purpose | Source of truth |
| ---- | ------- | ---------------- |
| `EARTHSCOPE_USER_ID` | Earthscope integration user identifier | GitHub org secret |
| `EARTHSCOPE_WEBHOOK_URL` | Earthscope webhook endpoint | GitHub org secret |
| `FB_ACCESS_TOKEN` | Facebook Graph API token | GitHub org secret |
| `FB_PAGE_ID` | Facebook page identifier | GitHub org secret |
| `GAIAEYES_MEDIA_SSH_KEY` | Deploy key for media repository | GitHub org secret |
| `GAIAEYES_MEDIA_TOKEN` | Token for accessing private media repo | GitHub org secret |
| `GAIA_TIMEZONE` | Canonical timezone value | Consider moving to repository variable |
| `GEOSPACE_FRAME_URL` | External data endpoint | Consider moving to repository variable |
| `GITHUB_TOKEN` | GitHub-provided token (auto) | Actions default |
| `IG_USER_ID` | Instagram account identifier | GitHub org secret |
| `MEDIA_CDN_BASE` | CDN root for published assets | Consider moving to repository variable |
| `MEDIA_REPO_NAME` | Media repository name | Consider moving to repository variable |
| `MEDIA_REPO_OWNER` | Media repository owner | Consider moving to repository variable |
| `MEDIA_ROOT` | Filesystem root for media sync | GitHub org secret |
| `NASA_API_KEY` | NASA APIs | GitHub org secret |
| `OPENAI_API_KEY` | OpenAI access key | GitHub org secret |
| `SOCIAL_WEBHOOK_URL` | Social automation webhook | GitHub org secret |
| `SUPABASE_DB_URL` | Supabase pooled database URL | GitHub org secret |
| `SUPERMAG_USERNAME` | Registered username required for SuperMAG ingest | GitHub org secret |
| `SUPABASE_REST_URL` | Supabase REST endpoint | Consider moving to repository variable |
| `SUPABASE_SERVICE_KEY` | Supabase service role key | GitHub org secret |
| `SUPABASE_SERVICE_ROLE` | Supabase service role secret | GitHub org secret |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key (duplicate) | GitHub org secret |
| `SUPABASE_URL` | Supabase project URL | Consider moving to repository variable |
| `SYMH_URL` | External SYMH data source | Consider moving to repository variable |
| `WEBHOOK_SECRET` | Shared secret for webhook verification | GitHub org secret |
| `WP_ALT_USERNAME` | Alternate WordPress account | GitHub org secret |
| `WP_APP_PASSWORD` | WordPress application password | GitHub org secret |
| `WP_BASE_URL` | WordPress base URL | Consider moving to repository variable |
| `WP_CATEGORY_ID` | WordPress category id(s) | Consider moving to repository variable |
| `WP_CTA_HTML` | CTA markup for posts | Consider moving to repository variable |
| `WP_TAG_IDS` | WordPress tag ids | Consider moving to repository variable |
| `WP_USERNAME` | WordPress username | GitHub org secret |

Run `./scripts/scan-secrets.sh` after any workflow change to keep this
section up to date.

## GaiaEyesHQ/gaiaeyes-ios
- _Populate after running_ `./scripts/audit_workflows.py GaiaEyesHQ/gaiaeyes-ios`

## GaiaEyesHQ/DataExport
- _Populate after running_ `./scripts/audit_workflows.py GaiaEyesHQ/DataExport`

## GaiaEyesHQ/gaiaeyes-wp
- _Populate after running_ `./scripts/audit_workflows.py GaiaEyesHQ/gaiaeyes-wp`

For each secret or variable, document:

| Name | Type | Purpose | Source of truth |
| ---- | ---- | ------- | ---------------- |
| e.g. `GAIAEYES_MEDIA_TOKEN` | Secret | Access private media repo | GitHub org secret |

Non-sensitive constants should be stored as repository variables instead
of secrets.
