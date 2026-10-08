#!/usr/bin/env bash
# Section 7 rehearsal (issue #56): run the brief's reproducibility commands word for word
# on a clean clone and record every output and exit code.
#
#   bash prototyping/dhruvi/rehearsal.sh [WORKDIR] [LOG]
#
# Deviation from the brief, recorded in the log: `python -m venv` uses $PYTHON (default
# python3.11), because on macOS a bare `python` may not exist; graders use Linux Python 3.11.
set -u
REPO="https://github.com/BigDataIA-Fall-26-Team-2/DAMG-7245-Project-Lantern-Team-2.git"
WORK="${1:-/tmp/lantern_rehearsal}"
LOG="${2:-$PWD/prototyping/dhruvi/rehearsal_raw.log}"
PY="${PYTHON:-python3.11}"
SUMMARY=""

mkdir -p "$(dirname "$LOG")"
: > "$LOG"
{
  echo "# Section 7 rehearsal, $(date '+%Y-%m-%d %H:%M %Z')"
  echo "# host: $(uname -sm), python: $($PY --version 2>&1), git: $(git --version)"
  echo "# deviation: 'python -m venv' run as '$PY -m venv'"
} >> "$LOG"

step() {  # step "<command as written in the brief>" <command to run...>
  local shown="$1"; shift
  echo "=== \$ $shown" | tee -a "$LOG"
  local t0=$SECONDS
  "$@" >> "$LOG" 2>&1
  local rc=$?
  local dt=$(( SECONDS - t0 ))
  echo "--- exit $rc after ${dt}s" | tee -a "$LOG"
  SUMMARY="${SUMMARY}$(printf '%-52s %s  %4ss' "$shown" "$([ $rc -eq 0 ] && echo PASS || echo "FAIL($rc)")" "$dt")\n"
  return 0
}

rm -rf "$WORK"
step "git clone <your-repo> lantern" git clone -q "$REPO" "$WORK"
cd "$WORK" || { echo "clone failed; stopping" | tee -a "$LOG"; exit 1; }
step "git checkout submission" git checkout -q submission
step "python -m venv .venv" "$PY" -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
echo "# venv python: $(python --version 2>&1) at $(command -v python)" >> "$LOG"
step "pip install -r requirements.txt" pip install -q -r requirements.txt
step "dvc pull" dvc pull
step "dvc repro" dvc repro
step "dvc metrics show" dvc metrics show
step "pytest -q" pytest -q
deactivate 2>/dev/null

echo
echo "================ SUMMARY (main at $(git -C "$WORK" log -1 --format='%h %s' | cut -c1-60))"
printf "%b" "$SUMMARY" | tee -a "$LOG"
echo "full log: $LOG"
