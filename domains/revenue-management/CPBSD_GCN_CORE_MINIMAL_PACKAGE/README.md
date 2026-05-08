# CPBSD GCN Core Minimal Package

This directory is a distilled GitHub package for the CPBSD-GCN exploration track. It keeps one reusable entry script per experimental phase plus the smallest representative result log or summary needed to audit the phase.

## Selection Rule

- One phase, one reusable driver script.
- Keep representative logs/summaries, not raw generated instance dumps.
- Prefer pipeline scripts over low-level helper modules.
- Preserve original source files elsewhere in the project; files here are copied snapshots.
- Keep enough evidence to cover the full research path: reproduction, CPBSD data setup, MB label generation, GCN training, GCN effect evaluation, random-cost generalization, Phase 2 grid/scaling checks, Phase 3 OOS probes, and HVHM failure analysis.

## Phase Map

| Phase | Reusable script | Representative results |
| --- | --- | --- |
| 01 Original GCN reproduction/reporting | `scripts/01_original_gcn_reproduction_report.py` | `results/01_original_reproduction/CPBSD_GCN_ACCELERATION_STATUS.md` |
| 02 CPBSD baseline/data setup | `scripts/02_cpbsd_baselines_v2_driver.py` | `results/02_cpbsd_baselines/unified_log.csv`, `Baseline_V2_Results_Summary.md` |
| 03 GCN dataset setup | `scripts/03_gcn_dataset_setup.py` | `results/03_gcn_dataset_setup/dataset_summary.json` |
| 04 MB label generation | `scripts/04_mb_label_chunk_queue.py` | `results/04_mb_label_generation/full_queue_status.json`, `cpbsd_mb_labels_q.log` |
| 05 GCN model training | `scripts/05_gcn_mb_training_pipeline.py` | `results/05_gcn_training/tmux_train_run.log`, `metrics_edge_cpbsd_mb_x_2layer_seed42.json` |
| 06 GCN effect evaluation | `scripts/06_gcn_fcp_pruned_mb_compare.py` | `results/06_gcn_effect_eval/aggregate_metrics.json`, `comparison_summary_all.csv` |
| 07 Random-cost generalization | `scripts/07_random_cost_gcn_pipeline.py` | `results/07_random_cost_generalization/*` |
| 08 Phase 2 N=5 shortlist grid | `scripts/08_phase2_shortlist_grid.sh` | `results/08_phase2_shortlist_grid/*` |
| 09 Phase 2 N10/N30 scaling | `scripts/09_phase2_n10_n30_scaling.sh` | `results/09_phase2_n10_n30_scaling/phase2_n10_n30_master.log` |
| 10 Phase 3 OOS infeasibility probe | `scripts/10_phase3_oos_bsp_completion_probe.py` | `results/10_phase3_oos_probe/*` |
| 11 Phase 3 Variant C repair probe | `scripts/11_phase3_variant_c_probe.py` | `results/11_phase3_variant_c/*` |
| 12 HVHM failure analysis | `scripts/12_hvhm_failure_analysis.py` | `results/12_hvhm_failure_analysis/hvhm_fcp_cpbsd_a_failure_analysis.md` |

## How To Reuse

These scripts are selected as reusable entry points. Several of them import helper modules from the original project tree, especially solver and data-generation modules under:

- `project-root/code_submission_project/code_submission/src/data/`
- `project-root/CPBSD_GCN_acceleration_experiment/mac/src/`

For a fully standalone extraction, copy the helper modules listed in `MANIFEST.md` dependencies or run these scripts inside the original repository layout.

## What Is Intentionally Excluded

- Raw `.msgpack` generated instances.
- Per-instance solver JSON dumps except compact summaries.
- PNG plots and chart artifacts.
- Duplicate helper scripts when a higher-level driver already covers the phase.
- Full chunked train/eval/test manifests and all per-chunk MB labels.

## Included Long-Form Context

The detailed system index is kept at:

- `docs/CPBSD_GCN_Model_应用探索系统整理.md`

