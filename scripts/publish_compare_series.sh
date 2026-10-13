#!/usr/bin/env bash
# Publish only the three generated JSON files; preserve other media changes.
set -euo pipefail

cd "${1:?Usage: publish_compare_series.sh MEDIA_DIR}"
files=(data/quakes_history.json data/space_history.json data/compare_series.json)
expected=()
for file in "${files[@]}"; do
  expected+=("$(git hash-object -- "$file")")
done

verify_files() {
  local ref="$1" actual i
  for i in "${!files[@]}"; do
    actual=$(git rev-parse "$ref:${files[$i]}") || return 1
    if [[ "$actual" != "${expected[$i]}" ]]; then
      echo "ERROR: $ref does not contain the generated ${files[$i]}." >&2
      return 1
    fi
  done
}

git config user.name "github-actions[bot]"
git config user.email "github-actions[bot]@users.noreply.github.com"
git add -- "${files[@]}"
if ! git diff --cached --quiet -- "${files[@]}"; then
  git commit --only -m "chore: update histories and compare_series [skip ci]" \
    -- "${files[@]}"
fi

for attempt in 1 2 3; do
  git fetch origin main
  if ! git rebase origin/main; then
    echo "ERROR: Media rebase failed; no push attempted after the failure." >&2
    exit 1
  fi
  verify_files HEAD
  published_commit=$(git rev-parse HEAD)
  if git push origin HEAD:main; then
    git fetch origin main
    if ! git merge-base --is-ancestor "$published_commit" origin/main; then
      echo "ERROR: Published commit is missing from remote main." >&2
      exit 1
    fi
    verify_files origin/main
    echo "[compare_series] published commit=$published_commit verified_files=3"
    exit 0
  fi
  if [[ "$attempt" -lt 3 ]]; then
    echo "Push failed on attempt $attempt; fetching and rebasing before retry."
    sleep "$attempt"
  fi
done
echo "ERROR: Could not publish comparison after 3 attempts." >&2
exit 1
