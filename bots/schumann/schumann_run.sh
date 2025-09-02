#!/usr/bin/env bash
set -euo pipefail

# --- Config (edit as needed) ---
PY="${PYTHON:-python}"                 # or absolute path to your venv python
OUT="${OUT:-runs/schumann_now.json}"
OVERLAY="${OVERLAY:-runs/schumann_overlay.png}"
HISTORY_DIR="${HISTORY_DIR:-runs/history}"

#Ensure we always apply the 60min bias to Tomsk
: "${TOMSK_TIME_BIAS_MINUTES:=-65}"
export TOMSK_TIME_BIAS_MINUTES

# Orchestrator preferences
PREFER="${PREFER:-tomsk,cumiana}"      # e.g. "cumiana,tomsk" while Tomsk is stale
INSECURE="${INSECURE:-1}"              # 1 → pass --insecure to extractors
VERBOSE="${VERBOSE:-1}"                # 1 → --verbose

# Validator knobs
MAX_AGE_HOURS="${MAX_AGE_HOURS:-6}"
HIST_WINDOW="${HIST_WINDOW:-12}"
DELTA_F1="${DELTA_F1:-2.5}"
DELTA_HARM="${DELTA_HARM:-4.0}"
Z_THRESH="${Z_THRESH:-3.5}"
REQUIRE_OVERLAY="${REQUIRE_OVERLAY:-1}"  # 1 → require overlay
STRICT="${STRICT:-0}"                     # 1 → warnings cause failure

# --- Derived flags ---
orch_flags=()
[[ "${INSECURE}" == "1" ]] && orch_flags+=("--insecure")
[[ "${VERBOSE}"  == "1" ]] && orch_flags+=("--verbose")
orch_flags+=("--prefer" "${PREFER}")
orch_flags+=("--out" "${OUT}" "--overlay" "${OVERLAY}")

val_flags=(
  "--in" "${OUT}"
  "--history-dir" "${HISTORY_DIR}"
  "--history-window" "${HIST_WINDOW}"
  "--delta-threshold-f1" "${DELTA_F1}"
  "--delta-threshold-harm" "${DELTA_HARM}"
  "--z-threshold" "${Z_THRESH}"
  "--max-age-hours" "${MAX_AGE_HOURS}"
)
[[ "${REQUIRE_OVERLAY}" == "1" ]] && val_flags+=("--require-overlay")
[[ "${STRICT}" == "1" ]] && val_flags+=("--strict")

# --- Ensure dirs ---
mkdir -p "$(dirname "${OUT}")" "$(dirname "${OVERLAY}")" "${HISTORY_DIR}"

echo "== [1/3] Orchestrate (${PREFER}) =="
set -x
${PY} schumann_multi.py "${orch_flags[@]}"
set +x

echo "== [2/3] Validate feed =="
set -x
${PY} validate_feed.py "${val_flags[@]}"
code=$?
set +x

if [[ $code -ne 0 && $code -ne 2 ]]; then
  # FAIL (3) → stop pipeline. WARN (2) allowed unless STRICT=1.
  echo "Validation failed (exit ${code}). Aborting rotate."
  exit $code
fi

# If STRICT=1, validator would already return 3 on warnings.
echo "== [3/3] Rotate into history =="
ts=$(date -u +"%Y%m%d_%H%M%SZ")
set -x
${PY} rotate_history.py \
  --in "${OUT}" \
  --overlay "${OVERLAY}" \
  --history-dir "${HISTORY_DIR}" \
  --keep 200
set +x

echo "Done."
