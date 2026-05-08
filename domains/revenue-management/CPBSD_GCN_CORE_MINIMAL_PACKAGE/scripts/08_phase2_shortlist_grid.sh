#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="/Users/sensen/.openclaw/workspace/domains/revenue-management"
PYTHON_BIN="$ROOT_DIR/project-root/code_submission_project/code_submission/.venv/bin/python"
RUNNER="$ROOT_DIR/project-root/code_submission_project/code_submission/src/data/run_cpbsd_fcp_pruned_mb_compare_parallel.py"
OUT_BASE="$ROOT_DIR/experiments/fcp_mb_phase2_shortlist_n5_5inst"
MASTER_LOG="$OUT_BASE/phase2_master.log"

mkdir -p "$OUT_BASE"

exec > >(tee -a "$MASTER_LOG") 2>&1

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Phase 2 batch start"
echo "Output root: $OUT_BASE"
echo "Runner: $RUNNER"
echo "Python: $PYTHON_BIN"

run_setting() {
  local setting_name="$1"
  local dist="$2"
  local rho="$3"
  local hetero="$4"
  local cost="$5"

  local setting_root="$OUT_BASE/$setting_name"

  echo
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] START $setting_name"

  "$PYTHON_BIN" "$RUNNER" \
    --base-root "$setting_root" \
    --instances 5 \
    --workers 3 \
    --base-seed 20260413 \
    --N 5 \
    --K 50 \
    --dist "$dist" \
    --rho "$rho" \
    --hetero "$hetero" \
    --cost "$cost" \
    --device auto \
    --threshold 0.5 \
    --time-limit-fcp-mb 300 \
    --time-limit-bsp 300 \
    --time-limit-cpbsd-a 300 \
    --mip-gap 1e-3 \
    --output-flag 0

  echo "[$(date '+%Y-%m-%d %H:%M:%S')] DONE $setting_name"
}

run_setting "normal_rho0.0_full_zero" "normal" "0.0" "full" "zero"
run_setting "normal_rho0.0_full_hvhm" "normal" "0.0" "full" "hvhm"
run_setting "logit_rho0.0_full_zero" "logit" "0.0" "full" "zero"
run_setting "logit_rho0.0_full_hvhm" "logit" "0.0" "full" "hvhm"
run_setting "normal_rho0.5_full_zero" "normal" "0.5" "full" "zero"
run_setting "normal_rho-0.5_full_zero" "normal" "-0.5" "full" "zero"

echo
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Phase 2 batch finished"
