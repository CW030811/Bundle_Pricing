# CPBSD GCN Core Minimal Package Manifest

Generated on 2026-05-08 from the local `revenue-management` domain. This manifest records source paths and the selection rationale for the distilled package.

## Scripts

| Package path | Source path | Why selected |
| --- | --- | --- |
| `scripts/01_original_gcn_reproduction_report.py` | `project-root/CPBSD_GCN_acceleration_experiment/mac/src/report/generate_final_report.py` | Original GCN reproduction/report aggregation entry. |
| `scripts/02_cpbsd_baselines_v2_driver.py` | `project-root/code_submission_project/code_submission/src/data/run_cpbsd_baselines_v2.py` | Unified CPBSD baseline/data setup and solver runner. |
| `scripts/03_gcn_dataset_setup.py` | `project-root/code_submission_project/code_submission/src/data/prepare_cpbsd_single_setting_gcn_dataset.py` | Minimal CPBSD instance generation and train/eval/test split script. |
| `scripts/04_mb_label_chunk_queue.py` | `project-root/code_submission_project/code_submission/src/data/run_cpbsd_mb_chunk_queue.py` | Reusable chunk queue for MB label generation. |
| `scripts/05_gcn_mb_training_pipeline.py` | `project-root/code_submission_project/code_submission/src/data/run_cpbsd_mb_training_pipeline.py` | Training pipeline wrapper with smoke/full train and device fallback. |
| `scripts/06_gcn_fcp_pruned_mb_compare.py` | `project-root/code_submission_project/code_submission/src/data/run_cpbsd_fcp_pruned_mb_compare.py` | Core GCN effect evaluation against BSP/CPBSD-A using FCP candidate pruning. |
| `scripts/07_random_cost_gcn_pipeline.py` | `project-root/code_submission_project/code_submission/src/data/run_random_cost_gcn_pipeline.py` | End-to-end random-cost data, label, train, and evaluation pipeline. |
| `scripts/08_phase2_shortlist_grid.sh` | `research-tracker/weekly-reports/2026-W16-fcp-gcn-vs-cpbsd-main-n5/run_phase2_fcp_mb_shortlist.sh` | Phase 2 N=5 setting grid batch driver. |
| `scripts/09_phase2_n10_n30_scaling.sh` | `research-tracker/weekly-reports/2026-W16-fcp-gcn-vs-cpbsd-main-n5/run_phase2_fcp_mb_n10_n30_selected.sh` | Phase 2 N10/N30 selected scaling batch driver. |
| `scripts/10_phase3_oos_bsp_completion_probe.py` | `project-root/code_submission_project/code_submission/src/data/run_phase3_oos_bsp_completion_probe.py` | Phase 3 OOS infeasibility/problem-identification probe. |
| `scripts/11_phase3_variant_c_probe.py` | `project-root/code_submission_project/code_submission/src/data/run_phase3_oos_variant_c_probe.py` | Variant C repair probe for the Phase 3 issue. |
| `scripts/12_hvhm_failure_analysis.py` | `research-tracker/weekly-reports/2026-W16-fcp-gcn-vs-cpbsd-main-n5/analyze_hvhm_fcp_cpbsd_a_failure.py` | Focused HVHM failure diagnosis script. |

## Results And Logs

| Package path | Source path | Why selected |
| --- | --- | --- |
| `results/01_original_reproduction/CPBSD_GCN_ACCELERATION_STATUS.md` | `project-root/CPBSD_GCN_acceleration_experiment/CPBSD_GCN_ACCELERATION_STATUS.md` | Compact status/results note for original reproduction stage. |
| `results/02_cpbsd_baselines/unified_log.csv` | `experiments/cpbsd_baselines_v2/unified_log.csv` | Unified baseline experiment log. |
| `results/02_cpbsd_baselines/Baseline_V2_Results_Summary.md` | `experiments/cpbsd_baselines_v2/results/Baseline_V2_Results_Summary.md` | Human-readable baseline summary. |
| `results/03_gcn_dataset_setup/dataset_summary.json` | `experiments/cpbsd_gcn_single_setting_n5_normal_rho0_full_hvhm/dataset_summary.json` | Dataset generation/split proof. |
| `results/04_mb_label_generation/full_queue_status.json` | `experiments/cpbsd_mb_labels_chunked_run1/full_queue_status.json` | Label queue completion status. |
| `results/04_mb_label_generation/cpbsd_mb_labels_q.log` | `experiments/cpbsd_mb_labels_chunked_run1/logs/cpbsd_mb_labels_q.log` | Label-generation execution log. |
| `results/05_gcn_training/tmux_train_run.log` | `project-root/code_submission_project/code_submission/log_cpbsd_mb_x/tmux_train_run.log` | GCN training run log. |
| `results/05_gcn_training/metrics_edge_cpbsd_mb_x_2layer_seed42.json` | `project-root/code_submission_project/code_submission/models_cpbsd_mb_x/metrics_edge_cpbsd_mb_x_2layer_seed42.json` | Main GCN training metrics. |
| `results/06_gcn_effect_eval/aggregate_metrics.json` | `experiments/cpbsd_fcp_pruned_mb_compare_n10k50_10inst_strict300/aggregate_metrics.json` | Aggregate GCN effect metrics. |
| `results/06_gcn_effect_eval/comparison_summary_all.csv` | `experiments/cpbsd_fcp_pruned_mb_compare_n10k50_10inst_strict300/comparison_summary_all.csv` | Per-seed comparison summary for GCN effect evaluation. |
| `results/07_random_cost_generalization/random_ind_comparison_summary.json` | `experiments/fcp_random_cost_eval_n10_random_ind/comparison_summary.json` | Random independent cost comparison result. |
| `results/07_random_cost_generalization/random_corr_comparison_summary.json` | `experiments/fcp_random_cost_eval_n10_random_corr/comparison_summary.json` | Random correlated cost comparison result. |
| `results/07_random_cost_generalization/random_ind_training_metrics.json` | `project-root/code_submission_project/code_submission/models_cpbsd_mb_x_random_ind/metrics_edge_cpbsd_mb_x_2layer_seed1000.json` | Random independent cost GCN training metrics. |
| `results/07_random_cost_generalization/random_corr_training_metrics.json` | `project-root/code_submission_project/code_submission/models_cpbsd_mb_x_random_corr/metrics_edge_cpbsd_mb_x_2layer_seed1000.json` | Random correlated cost GCN training metrics. |
| `results/08_phase2_shortlist_grid/phase2_master.log` | `experiments/fcp_mb_phase2_shortlist_n5_5inst/phase2_master.log` | Phase 2 N=5 grid master log. |
| `results/08_phase2_shortlist_grid/normal_rho0.0_full_hvhm_aggregate_metrics.json` | `experiments/fcp_mb_phase2_shortlist_n5_5inst/normal_rho0.0_full_hvhm/aggregate_metrics.json` | Representative Phase 2 setting result. |
| `results/09_phase2_n10_n30_scaling/phase2_n10_n30_master.log` | `experiments/fcp_mb_phase2_selected_n10_n30_5inst/phase2_n10_n30_master.log` | Phase 2 larger-N scaling master log. |
| `results/10_phase3_oos_probe/probe_summary.md` | `experiments/phase3_oos_bsp_completion_probe_n10_normal_rho0.0_full_hvhm_inst001/probe_summary.md` | Phase 3 OOS probe summary. |
| `results/10_phase3_oos_probe/probe_summary.json` | `experiments/phase3_oos_bsp_completion_probe_n10_normal_rho0.0_full_hvhm_inst001/probe_summary.json` | Machine-readable Phase 3 OOS probe result. |
| `results/11_phase3_variant_c/variant_c_probe_summary.md` | `experiments/phase3_oos_variant_c_probe_n10_normal_rho0.0_full_hvhm_inst001/variant_c_probe_summary.md` | Variant C repair summary. |
| `results/11_phase3_variant_c/variant_c_probe_summary.json` | `experiments/phase3_oos_variant_c_probe_n10_normal_rho0.0_full_hvhm_inst001/variant_c_probe_summary.json` | Machine-readable Variant C result. |
| `results/12_hvhm_failure_analysis/hvhm_fcp_cpbsd_a_failure_analysis.md` | `research-tracker/weekly-reports/2026-W16-fcp-gcn-vs-cpbsd-main-n5/hvhm_fcp_cpbsd_a_failure_analysis.md` | Focused HVHM failure analysis output. |
| `docs/CPBSD_GCN_Model_应用探索系统整理.md` | `Report/CPBSD_GCN_Model_应用探索系统整理.md` | Full context index for the distilled package. |

## Runtime Dependencies Not Copied Into The Minimal Package

These drivers intentionally rely on the original project layout for helper imports. The most important dependency families are:

- `generate_data_CPBSD.py`
- `solve_cpbsd_milp.py`
- `solve_cpbsd_a.py`
- `solve_mb_bsp_on_cpbsd_v2.py`
- `Training_multi_layer_cpbsd_mb_x.py`
- `run_cpbsd_fcp_pruned_mb_compare_parallel.py`
- `run_phase3_oos_bsp_completion_probe.py` for Variant C helper imports

The package is therefore a curated artifact bundle and driver index, not a fully vendored standalone repository.

