#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$REPO_ROOT"

if ! command -v rg >/dev/null 2>&1; then
  echo "ripgrep (rg) is required to scan for secrets references." >&2
  exit 1
fi

pattern='\$\{\{\s*(secrets|vars)\.[^}]+\}\}'

target_paths=("$@")
if [ ${#target_paths[@]} -eq 0 ]; then
  if [ -d .github/workflows ]; then
    target_paths=(".github/workflows")
  else
    target_paths=(".")
  fi
fi

rg --no-heading --line-number --color=never "$pattern" "${target_paths[@]}"
