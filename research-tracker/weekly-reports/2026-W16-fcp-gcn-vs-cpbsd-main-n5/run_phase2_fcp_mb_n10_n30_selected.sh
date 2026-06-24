#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="/Users/sensen/.openclaw/workspace/domains/revenue-management"
PYTHON_BIN="$ROOT_DIR/project-root/code_submission_project/code_submission/.venv/bin/python"
RUNNER="$ROOT_DIR/project-root/code_submission_project/code_submission/src/data/run_cpbsd_fcp_pruned_mb_compare_parallel.py"
OUT_BASE="$ROOT_DIR/experiments/fcp_mb_phase2_selected_n10_n30_5inst"
MASTER_LOG="$OUT_BASE/phase2_n10_n30_master.log"

mkdir -p "$OUT_BASE"
exec > >(tee -a "$MASTER_LOG") 2>&1

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Phase 2 N10/N30 batch start"
echo "Output root: $OUT_BASE"
echo "Runner: $RUNNER"
echo "Python: $PYTHON_BIN"

run_setting() {
  local n="$1"
  local setting_name="$2"
  local dist="$3"
  local rho="$4"
  local hetero="$5"
  local cost="$6"

  local workers="3"
  local tl="300"
  if [[ "$n" == "30" ]]; then
    workers="2"
    tl="600"
  fi

  local setting_root="$OUT_BASE/n${n}/${setting_name}"
  mkdir -p "$setting_root"

  echo
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] START n=${n} setting=${setting_name}"

  "$PYTHON_BIN" "$RUNNER" \
    --base-root "$setting_root" \
    --instances 5 \
    --workers "$workers" \
    --base-seed 20260413 \
    --N "$n" \
    --K 50 \
    --dist "$dist" \
    --rho "$rho" \
    --hetero "$hetero" \
    --cost "$cost" \
    --device auto \
    --threshold 0.5 \
    --time-limit-fcp-mb "$tl" \
    --time-limit-bsp "$tl" \
    --time-limit-cpbsd-a "$tl" \
    --mip-gap 1e-3 \
    --output-flag 0

  echo "[$(date '+%Y-%m-%d %H:%M:%S')] DONE n=${n} setting=${setting_name}"
}

for n in 10 30; do
  run_setting "$n" "normal_rho0.0_full_zero" "normal" "0.0" "full" "zero"
  run_setting "$n" "normal_rho0.0_full_hvhm" "normal" "0.0" "full" "hvhm"
  run_setting "$n" "logit_rho0.0_full_hvhm" "logit" "0.0" "full" "hvhm"
  run_setting "$n" "normal_rho0.5_full_hvhm" "normal" "0.5" "full" "hvhm"
done

echo
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Phase 2 N10/N30 batch finished"
