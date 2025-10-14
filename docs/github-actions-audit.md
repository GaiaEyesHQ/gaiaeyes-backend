# GitHub Actions audit playbook

This repository now includes tooling to audit the GaiaEyes GitHub
organization for failing workflows and missing secrets.

## 1. Generate an audit report

```bash
export GITHUB_TOKEN=<token with repo+workflow scope>
./scripts/audit_workflows.py \
  GaiaEyesHQ/gaiaeyes-ios \
  GaiaEyesHQ/DataExport \
  GaiaEyesHQ/gaiaeyes-wp \
  --output report.md
```

The script will download workflow metadata, capture the latest run
status, and enumerate every `${{ secrets.* }}` and `${{ vars.* }}`
reference. The generated Markdown file is ready to paste into an audit
issue or pull request description.

> **Tip:** Re-run the script after applying fixes to attach links to the
> most recent green runs.

## 2. List referenced secrets in the current repo

```bash
./scripts/scan-secrets.sh
```

The helper script relies on `rg`/`ripgrep` and prints every secret or
variable reference along with its file and line number. Use it to keep
`REQUIRED_SECRETS.md` up to date.

## 3. Recommended follow-up actions

1. **Document secrets** – update `REQUIRED_SECRETS.md` (or per-repo
   README) with the names, purpose, and system of record for each secret
   or variable.
2. **Verify repository settings** – confirm that workflow permissions are
   set to **Read and write** and that organization secrets/variables are
   inherited where appropriate.
3. **Review failures** – for each workflow flagged in the report, drill
   into the failing step to determine whether the cause is missing
   configuration (secrets, variables, or permissions), outdated runtime
   requirements, or broken scripts. Capture the fix in a pull request and
   re-run the workflow to validate.
4. **Prefer variables for non-sensitive data** – constants that are not
   sensitive should move from `${{ secrets.* }}` to `${{ vars.* }}`.

Keeping these steps in the project workflow ensures GaiaEyes repos stay
healthy and actionable.
