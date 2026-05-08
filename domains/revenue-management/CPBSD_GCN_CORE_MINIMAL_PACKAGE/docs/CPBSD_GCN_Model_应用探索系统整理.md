# CPBSD 方向 GCN Model 应用探索系统整理

整理日期：2026-05-08  
整理范围：本域 `revenue-management` 项目目录内的现有代码、实验产物、报告与本域历史记录。  
操作边界：本文件为新增汇总索引，未删除或改动既有文件。

## 0. 一页结论

到目前为止，CPBSD 方向上的 GCN 探索已经从“复现 CPBSD/MB/BSP 基线”推进到“用 GCN 生成候选 bundle，再做 restricted MB/FCP 定价，并围绕 OOS 失效机制做修复探索”。

核心结论可以压缩为四点：

1. **复现阶段已经形成稳定基线**：`CPBSD-MILP / CPBSD-A / BSP / MB` 的 smoke subset 结果、统一日志、N=5 full-grid MB/BSP 聚合诊断都已具备。`normal_rho0.0_full_hvhm` 是一个明确的 stress setting，MB 在该 setting 下有明显 OOS drop。
2. **GCN 训练链路已经跑通**：已有 `N=5,K=50,normal,rho0,full,hvhm` 单 setting 的 5000 实例训练集，以及 `random_ind/random_corr` 两类 random cost 专用训练集。模型用 edge-level supervision 学习 MB 最优选择矩阵 `x_kn`。
3. **FCP/GCN 候选筛选有效但 OOS 是主短板**：FCP-pruned-MB 经常赢 in-sample revenue 和 runtime，但在 hvhm setting 下 OOS revenue 不稳定，Phase 2 的 8 个 N10/N30 setting-size 对中，FCP 的 OOS 没有赢过 BSP/CPBSD-A。
4. **问题根因已较清楚**：FCP 的高利润来自少量显式 bundle 的高质量定价，但 OOS 只 replay restricted explicit menu，覆盖不足导致更多 customer 走 outside option。单纯用 BSP size price 补全 full bundle space 会 infeasible 或效果差；更有希望的是 `FCP + targeted extended menu / GCN-PCP candidate expansion`。

## 1. 当前代码与目录边界

### 1.1 Canonical active code

当前活跃代码主线以 `code_submission` 为准：

- `project-root/code_submission_project/code_submission/src/data/`
  - CPBSD 数据生成、baseline solver、MB/BSP solver、label generation、GCN training、FCP comparison、Phase 3 probes。
- `project-root/code_submission_project/code_submission/src/analyze/`
  - 早期 MBPP/local-search/LP-MILP 相关分析脚本。
- `project-root/code_submission_project/code_submission/models_cpbsd_mb_x*/`
  - 已训练 GCN 模型、训练指标、loss CSV。
- `experiments/`
  - 当前实验输出、日志、manifest、JSON/CSV 结果、probe summary。
- `research-tracker/weekly-reports/2026-W16-fcp-gcn-vs-cpbsd-main-n5/`
  - Phase 1/2/3 的周报式决策记录和分析文档。

### 1.2 Legacy/reference code

早期迁移/参考快照：

- `project-root/CPBSD_GCN_acceleration_experiment/`
  - `mac/` 与 `windows/` 两套早期核心代码副本。
  - 现作为历史参考，不作为默认活跃执行目录。

该目录中记录的核心迁移文件包括：

- `mac/src/data/generate_data_MB.py`
- `mac/src/data/generate_data_BSP.py`
- `mac/src/train/Training_edge-final.py`
- `mac/src/test/test_FCP.py`
- `mac/src/test/test_PCP.py`
- `mac/src/test/test_FCP_LS.py`
- `mac/src/report/generate_final_report.py`

参考索引：

- `project-root/CPBSD_GCN_acceleration_experiment/CORE_FILES_MANIFEST.md`
- `project-root/CPBSD_GCN_acceleration_experiment/CPBSD_GCN_ACCELERATION_STATUS.md`
- `project-root/CPBSD_GCN_acceleration_experiment/README.md`

## 2. 阶段一：CPBSD 复现与 Data Setup 生成

### 2.1 论文 setup 维度与 repo 命名

CPBSD paper-style full grid：

- `N in {5,10,30}`
- 5 个 marginal distributions：`exponential / logit / lognormal / normal / uniform`
- 3 个 correlation settings：`rho in {-0.5, 0.0, 0.5}`
- 3 个 heterogeneity settings：`none / partial / full`
- 3 个 cost scenarios：`zero / hvhm / hvlm`

总计：

- full paper-style grid = `3 x 5 x 3 x 3 x 3 = 405`
- `N=5` active screen space = `5 x 3 x 3 x 3 = 135`

主要文件：

- `project-root/code_submission_project/code_submission/src/data/generate_data_CPBSD.py`
- `research-tracker/weekly-reports/2026-W16-fcp-gcn-vs-cpbsd-main-n5/setup_inventory.md`
- `research-tracker/weekly-reports/2026-W16-fcp-gcn-vs-cpbsd-main-n5/setup_shortlist.md`
- `research-tracker/weekly-reports/2026-W16-fcp-gcn-vs-cpbsd-main-n5/paper_repo_naming_map.md`

canonical setting key：

```text
{dist}_rho{rho}_{heterogeneity}_{cost}
```

例子：

- `normal_rho0.0_full_zero`
- `normal_rho0.0_full_hvhm`
- `logit_rho0.0_full_hvhm`

### 2.2 复现入口代码

当前 baseline 与复现相关入口：

- `project-root/code_submission_project/code_submission/src/data/run_cpbsd_baselines_v2.py`
  - 当前 smoke subset v2 主入口。
  - N=5 跑 `CPBSD-MILP / CPBSD-A / BSP / MB`。
  - N=10 跑 `CPBSD-A / BSP`。
  - 输出统一 `unified_log.csv/json`。
- `project-root/code_submission_project/code_submission/src/data/run_cpbsd_main_n5.py`
- `project-root/code_submission_project/code_submission/src/data/run_cpbsd_main_n5_v2.py`
  - N=5 main/full-grid 相关入口。
- `project-root/code_submission_project/code_submission/src/data/solve_cpbsd_milp.py`
- `project-root/code_submission_project/code_submission/src/data/solve_cpbsd_a.py`
- `project-root/code_submission_project/code_submission/src/data/solve_mb_bsp_on_cpbsd_v2.py`

### 2.3 复现输出与主要结果

Smoke baseline v2：

- 结果根目录：`experiments/cpbsd_baselines_v2/`
- 统一日志：
  - `experiments/cpbsd_baselines_v2/unified_log.csv`
  - `experiments/cpbsd_baselines_v2/unified_log.json`
- 结果报告：
  - `experiments/cpbsd_baselines_v2/results/Baseline_V2_Results_Summary.md`
  - `experiments/cpbsd_baselines_v2/results/MB_Generalization_Diagnostic_Report.md`
  - `experiments/cpbsd_baselines_v2/results/FULL_GRID_GENERALIZATION_VALIDATION_REPORT.md`
- per-instance JSON：
  - `experiments/cpbsd_baselines_v2/results/baseline_cpbsd_milp_n5_inst001.json` 等。
  - `baseline_cpbsd_a_*`
  - `baseline_bsp_*`
  - `baseline_mb_*`

关键 smoke 结果，setting 为 `N=5,K=50,normal,rho0.0,full,hvhm`：

| Method | Mean Rev-In/BSP | Mean Rev-Out/BSP | Mean Drop | Mean Runtime |
| --- | ---: | ---: | ---: | ---: |
| CPBSD-MILP | 1.167 | 1.121 | 12.2% | 300.0s |
| CPBSD-A | 1.152 | 1.155 | 8.9% | 16.4s |
| BSP | 1.000 | 1.000 | 8.3% | 1.0s |
| MB | 1.343 | 1.060 | 27.8% | 258.3s |

N=10 smoke：

- `CPBSD-A` 平均 Rev-Out/BSP = `1.170`。
- `BSP` 平均 runtime 约 `178.4s`。
- 该 smoke 不含 `CPBSD-MILP` 与 `MB`，原因是规模/时间限制不适合直接求完整模型。

N=5 full-grid MB/BSP validation：

- 结果来源：`experiments/cpbsd_baselines_v2/results/FULL_GRID_GENERALIZATION_VALIDATION_REPORT.md`
- full-grid scope：`135` settings x `3` instances = `405` instances。
- rows：`810`，methods：`BSP`, `MB`。
- MB status counts：`337 OPTIMAL`, `68 TIME_LIMIT`。
- Full-grid MB 平均 drop = `16.14%`，低于 smoke stress setting 的 `27.83%`。
- 结论：smoke setting 是困难切片，full-grid 聚合后 MB OOS edge 只剩约 `1.005x` BSP OOS。

### 2.4 复现阶段识别的问题

主要诊断记录：

- `project-root/CPBSD_GCN_acceleration_experiment/CPBSD_MILP_DIAG_NOTES.md`
- `project-root/CPBSD_GCN_acceleration_experiment/CPBSD_MILP_vs_BCS_Revenue_Mismatch_Diagnosis.md`
- `experiments/cpbsd_baselines_v2/results/MB_Generalization_Diagnostic_Report.md`

已识别问题与结论：

| 问题 | 当前判断 |
| --- | --- |
| MILP ObjVal 曾出现低于 BSP | 主要是对比口径错误。应区分 MILP objective 与后验 replay revenue。 |
| ObjVal 与后验 revenue 不一致 | 多数来自 tie-breaking。MILP 体现 optimistic tie-breaking，BCS evaluator 可能偏 pessimistic outside option。 |
| BCS tightness | surplus 一致性检查未发现客户选择了严格更差 bundle 的证据。 |
| Big-M 安全性 | 已引入 `p_ub/d_ub` 和更安全的 `big_M`，但保守程度仍可做敏感性分析。 |
| CPBSD-A 算法细节 | 当前工程实现基于 `v_n^k-c_n` 排序，是工程补全，论文未给完整细节。 |
| MB OOS drop | 在 hard setting 下真实存在，主要来自 2^N price table 在小 K 下过拟合，不是 phantom bundle 或低于成本定价导致。 |

## 3. 阶段二：GCN Training Data 生成与模型训练

### 3.1 GCN 训练目标

当前 GCN 不是直接预测 CPBSD 的 `p_n,d_s`，也不是直接预测 full bundle price。

训练目标是 edge-level binary supervision：

```text
x_kn = 1 iff product n belongs to the MB-optimal bundle chosen by customer k
```

对应训练脚本：

- `project-root/code_submission_project/code_submission/src/data/Training_multi_layer_cpbsd_mb_x.py`

模型结构：

- `EdgeScoringGCN`
- `GENConv`
- 2 layers
- hidden channels = 128
- edge head 输出每条 customer-product edge 的 logit

主要输入特征：

- Product node：`[c_n, mean_k(v_kn), 0, 0]`
- Customer node：`[0, 0, K, rho_k]`
- Edge feature：`[v_kn]`
- Label：MB solution 中的 `chosen_product_matrix`

### 3.2 单 setting 训练数据生成

数据生成脚本：

- `project-root/code_submission_project/code_submission/src/data/prepare_cpbsd_single_setting_gcn_dataset.py`

数据目录：

- `experiments/cpbsd_gcn_single_setting_n5_normal_rho0_full_hvhm/`

配置：

| 字段 | 值 |
| --- | --- |
| N | 5 |
| K | 50 |
| dist | normal |
| rho | 0.0 |
| heterogeneity | full |
| cost | hvhm |
| seed | 20260310 |
| instances_total | 5000 |
| train/eval/test | 4000 / 500 / 500 |

关键文件：

- `experiments/cpbsd_gcn_single_setting_n5_normal_rho0_full_hvhm/dataset_summary.json`
- `train_manifest.csv/json`
- `eval_manifest.csv/json`
- `test_manifest.csv/json`
- `all_instances/*.msgpack`

### 3.3 Manifest 分块与 MB 标签生成

分块脚本：

- `project-root/code_submission_project/code_submission/src/data/split_cpbsd_manifests_into_chunks.py`

分块输出：

- `experiments/cpbsd_gcn_single_setting_n5_normal_rho0_full_hvhm_chunked_manifests/`
- `chunk_summary.json`

分块设置：

- chunk size = `200`
- train chunks = `20`
- eval chunks = `3`
- test chunks = `3`

MB 标签生成脚本：

- `project-root/code_submission_project/code_submission/src/data/label_cpbsd_mb_from_manifest.py`
- `project-root/code_submission_project/code_submission/src/data/run_cpbsd_mb_chunk_queue.py`
- `project-root/code_submission_project/code_submission/src/data/run_cpbsd_mb_full_queue.py`
- `project-root/code_submission_project/code_submission/src/data/merge_cpbsd_mb_chunk_results.py`

标签输出目录：

- `experiments/cpbsd_mb_labels_chunked_run1/`

关键 merged manifests：

- `experiments/cpbsd_mb_labels_chunked_run1/train__mb_results_merged.csv`
- `experiments/cpbsd_mb_labels_chunked_run1/eval__mb_results_merged.csv`
- `experiments/cpbsd_mb_labels_chunked_run1/test__mb_results_merged.csv`
- smoke variants：`*_smoke64.csv`

MB label 求解配置：

- time limit = `300s`
- mip gap = `0.01`
- output flag = `0`

标签状态统计：

| Split | Rows | OPTIMAL(status=2) | TIME_LIMIT(status=9) | has_solution |
| --- | ---: | ---: | ---: | ---: |
| train | 4000 | 3242 | 758 | 4000 |
| eval | 500 | 406 | 94 | 500 |
| test | 500 | 425 | 75 | 500 |

训练 pipeline：

- `project-root/code_submission_project/code_submission/src/data/run_cpbsd_mb_training_pipeline.py`
- log：`project-root/code_submission_project/code_submission/log_cpbsd_mb_x/tmux_train_run.log`

### 3.4 主 GCN 模型训练结果

模型目录：

- `project-root/code_submission_project/code_submission/models_cpbsd_mb_x/`

关键文件：

- `best_model_edge_cpbsd_mb_x_2layer_seed42.pt`
- `model_edge_cpbsd_mb_x_2layer_seed42.pt`
- `metrics_edge_cpbsd_mb_x_2layer_seed42.json`
- `train_loss_edge_cpbsd_mb_x_2layer_seed42.csv`
- `val_loss_edge_cpbsd_mb_x_2layer_seed42.csv`

训练配置：

- train/eval/test = `4000/500/500`
- epochs max = `200`
- batch size = `32`
- learning rate = `0.001`
- hidden = `128`
- layers = `2`
- seed = `42`
- device = `mps`
- early stopping patience = `30`

主结果：

| Split | Loss | Accuracy | Precision | Recall | F1 |
| --- | ---: | ---: | ---: | ---: | ---: |
| train | 0.2720 | 0.8539 | 0.9034 | 0.8353 | 0.8680 |
| eval | 0.2730 | 0.8518 | 0.9041 | 0.8295 | 0.8651 |
| test | 0.2737 | 0.8528 | 0.9042 | 0.8336 | 0.8674 |

训练过程要点：

- smoke64 先跑通。
- full training 在 MPS batch size 32 成功。
- best validation 出现在早期 epoch，随后 early stopping。

### 3.5 Random cost 专用 GCN 训练

记录文档：

- `research-tracker/weekly-reports/2026-W16-fcp-gcn-vs-cpbsd-main-n5/phase3_random_cost_gcn_training.md`

pipeline：

- `project-root/code_submission_project/code_submission/src/data/run_random_cost_gcn_pipeline.py`

数据/标签目录：

- `experiments/cpbsd_random_ind_n5/`
- `experiments/cpbsd_random_corr_n5/`

模型目录：

- `project-root/code_submission_project/code_submission/models_cpbsd_mb_x_random_ind/`
- `project-root/code_submission_project/code_submission/models_cpbsd_mb_x_random_corr/`

配置：

| 字段 | 值 |
| --- | --- |
| N | 5 |
| K | 50 |
| dist/rho/hetero | normal / 0.0 / full |
| instances per scenario | 4000 |
| train/val/test | 3000 / 600 / 400 |
| seed | 1000 |
| model | EdgeScoringGCN, 2 layers, hidden=128 |

Random_ind 结果：

| Split | Loss | Accuracy | F1 |
| --- | ---: | ---: | ---: |
| train | 0.1435 | 0.9414 | 0.9444 |
| eval | 0.1504 | 0.9374 | 0.9397 |
| test | 0.1425 | 0.9415 | 0.9431 |

Random_corr 结果：

| Split | Loss | Accuracy | F1 |
| --- | ---: | ---: | ---: |
| train | 0.1376 | 0.7359 | 0.8174 |
| eval | 0.1407 | 0.7321 | 0.8141 |
| test | 0.1386 | 0.7337 | 0.8151 |

解读：

- `random_ind` 正边比例约 `50.9%`，训练效果强。
- `random_corr` 正边比例约 `84.6%`，类别高度不平衡，precision 高但 recall 偏低。

## 4. 阶段三：GCN/FCP 效果实验

### 4.1 FCP-pruned-MB 单实例探索

入口脚本：

- `project-root/code_submission_project/code_submission/src/data/run_cpbsd_fcp_pruned_mb_compare.py`

实验目录：

- `experiments/cpbsd_fcp_pruned_mb_compare_n10k50_strict300/`

固定实例：

- `cpbsd_instance_001_N10_K50_normal_rho0.0_full_hvhm.msgpack`

核心结果：

| Method | Rev In | Rev OOS | Runtime |
| --- | ---: | ---: | ---: |
| FCP-pruned-MB | 3.5619 | 2.3990 | 90.2s |
| BSP | 3.0667 | 2.4505 | 3.7s |
| CPBSD-A | 3.4348 | 2.8593 | 300.1s |

FCP menu：

- bundle space size = `37`
- full bundle space size = `1024`
- bundle space fraction = `3.61%`
- GCN threshold = `0.5`

结论：

- FCP 在 in-sample revenue 上超过 BSP/CPBSD-A。
- FCP OOS 低于 BSP/CPBSD-A。
- 第一次明确暴露：候选筛选给了高 in-sample 质量，但 OOS menu coverage 有风险。

### 4.2 10-instance aggregate

实验目录：

- `experiments/cpbsd_fcp_pruned_mb_compare_n10k50_10inst_strict300/`

关键文件：

- `aggregate_metrics.json`
- `comparison_summary_all.csv/json`
- `logs/seed_20260321.log` 到 `seed_20260330.log`

平均结果：

| Method | Count | Avg Rev In | Avg Rev OOS | Avg Runtime |
| --- | ---: | ---: | ---: | ---: |
| BSP | 10 | 2.7260 | 2.3029 | 12.1s |
| CPBSD-A | 10 | 3.0934 | 2.8191 | 300.2s |
| FCP-pruned-MB | 10 | 3.2073 | 2.3590 | 188.6s |

结论：

- FCP 继续保持 in-sample revenue 优势。
- OOS 仍明显低于 CPBSD-A，只略高于 BSP。

### 4.3 LS / Global Top-K 尝试

实验目录：

- `experiments/cpbsd_fcp_ls_global_topk_compare_n10k50_strict300/`

关键文件：

- `comparison_summary.json`
- `results/*__fcp_ls_global_topk_mb.json`
- `results/*__fcp_ls_global_topk_search.json`

结果：

- `FCP+LS-GlobalTopK-MB` 与原 FCP-pruned-MB 的 revenue 相同。
- search iterations = `1`
- improvements = `0`
- final bundle space size 仍为 `37`

结论：

- Global Top-K LS 在该实例上没有改善候选空间或收益。

### 4.4 Phase 2 N10/N30 shortlisted setup 对比

主周报目录：

- `research-tracker/weekly-reports/2026-W16-fcp-gcn-vs-cpbsd-main-n5/`

实验目录：

- `experiments/fcp_mb_phase2_selected_n10_n30_5inst/`

关键文件：

- `phase2_n10_n30_master.log`
- 每个 setting-size 子目录下的：
  - `aggregate_metrics.json`
  - `comparison_summary_all.csv`
  - `logs/seed_20260413.log` 到 `seed_20260417.log`

报告：

- `comparison_avg.md`
- `comparison_avg.csv`
- `dominance_summary.md`

批次范围：

- methods：`BSP`, `CPBSD-A`, `FCP-pruned-MB`
- matched seeds：`20260413` 到 `20260417`
- setting-size pairs：`8`
- 注意：此批次未包含 `CPBSD / CPBSD-MILP`

结论摘要：

- `8/8` setting-size pairs 产出 `aggregate_metrics.json` 与 `comparison_summary_all.csv`。
- FCP-pruned-MB 赢 average in-sample revenue：`7/8`。
- FCP-pruned-MB 赢 average OOS revenue：`0/8`。
- FCP-pruned-MB full dominance：`0/8`。
- 阻塞指标稳定是 `Revenue OOS`。

最强 trade-off setting：

| N | Setting | FCP Rev In | FCP Rev OOS | FCP Runtime | 读法 |
| ---: | --- | ---: | ---: | ---: | --- |
| 30 | `normal_rho0.5_full_hvhm` | 10.5253 | 5.6190 | 35.7s | in-sample/runtime 很强，OOS 输 BSP/CPBSD-A |
| 30 | `normal_rho0.0_full_hvhm` | 11.9822 | 4.9082 | 6.6s | runtime 极强，OOS collapse 更重 |

### 4.5 N5 shortlist batch

实验目录：

- `experiments/fcp_mb_phase2_shortlist_n5_5inst/`

覆盖 setting：

- `logit_rho0.0_full_hvhm`
- `logit_rho0.0_full_zero`
- `normal_rho-0.5_full_hvhm`
- `normal_rho-0.5_full_zero`
- `normal_rho0.0_full_hvhm`
- `normal_rho0.0_full_zero`
- `normal_rho0.5_full_hvhm`
- `normal_rho0.5_full_zero`

每个 setting 有：

- `aggregate_metrics.json`
- `comparison_summary_all.csv/json`
- `logs/seed_20260413.log` 到 `seed_20260417.log`

### 4.6 Random cost GCN/FCP 评估

评估输出目录：

- `experiments/fcp_random_cost_eval_n5_random_ind/`
- `experiments/fcp_random_cost_eval_n10_random_ind/`
- `experiments/fcp_random_cost_eval_n30_random_ind/`
- `experiments/fcp_random_cost_eval_n5_random_corr/`
- `experiments/fcp_random_cost_eval_n10_random_corr/`
- `experiments/fcp_random_cost_eval_n30_random_corr/`

每个目录有：

- `comparison_summary.json`
- `comparison_summary.csv`
- `instances/`
- `results/`

Random_ind 5-instance average：

| N | Method | InS | OOS | Runtime |
| ---: | --- | ---: | ---: | ---: |
| 5 | FCP-pruned-MB | 9.804 | 9.493 | 0.08s |
| 5 | BSP | 8.707 | 8.382 | 0.26s |
| 5 | CPBSD-A | 9.825 | 9.186 | 0.46s |
| 10 | FCP-pruned-MB | 17.051 | 16.380 | 0.12s |
| 10 | BSP | 14.795 | 13.988 | 0.94s |
| 10 | CPBSD-A | 13.740 | 13.166 | 7.15s |
| 30 | FCP-pruned-MB | 57.020 | 54.592 | 0.70s |
| 30 | BSP | 45.607 | 43.117 | 147.43s |
| 30 | CPBSD-A | 27.522 | 26.578 | 243.46s |

Random_corr 5-instance average：

| N | Method | InS | OOS | Runtime |
| ---: | --- | ---: | ---: | ---: |
| 5 | FCP-pruned-MB | 10.540 | 9.728 | 0.45s |
| 5 | BSP | 10.575 | 9.789 | 0.40s |
| 5 | CPBSD-A | 10.602 | 9.905 | 1.03s |
| 10 | FCP-pruned-MB | 20.510 | 18.830 | 1.02s |
| 10 | BSP | 20.309 | 18.974 | 0.70s |
| 10 | CPBSD-A | 20.258 | 18.942 | 110.30s |
| 30 | FCP-pruned-MB | 64.357 | 59.042 | 6.43s |
| 30 | BSP | 65.693 | 62.988 | 2.57s |
| 30 | CPBSD-A | 56.968 | 54.733 | 600.22s |

解读：

- `random_ind` 是 FCP 的强优势场景，FCP 在 N=5/10/30 的 OOS 均为最高。
- `random_corr` 下三方接近，BSP 在 N=10/30 OOS 更强，FCP 仍有明显 runtime 优势。
- random cost 专用 GCN 从 N=5 训练后迁移到 N=10/30 可用。

## 5. 阶段四：问题识别与 OOS 修复探索

### 5.1 FCP OOS 失效机制

关键文档：

- `research-tracker/weekly-reports/2026-W16-fcp-gcn-vs-cpbsd-main-n5/bsp_vs_fcp_oos_instance001_report.md`
- `research-tracker/weekly-reports/2026-W16-fcp-gcn-vs-cpbsd-main-n5/phase3_oos_logic_note.md`

核心判断：

- BSP 稀疏在 size 维度，但每个 OOS customer 会根据自身 valuation 得到 top-s exact bundle。
- FCP 稀疏在 explicit bundle identity 维度。OOS replay 只在 in-sample restricted assortment 上做选择。
- 因此 FCP 的问题不是“服务到的客户利润低”，而是“没有覆盖到足够多 OOS 客户”。

主诊断实例：

- `cpbsd_instance_001_N10_K50_normal_rho0.0_full_hvhm`

OOS 现象：

- BSP OOS average profit = `2.4505`
- FCP OOS average profit = `2.3990`
- BSP outside count = `1210/5000`
- FCP outside count = `1544/5000`
- FCP 比 BSP 多 `334` 个 outside-option customers。
- 在 FCP 购买者中，FCP 的 conditional profit 通常高于 BSP。

简化结论：

```text
BSP wins coverage.
FCP wins conditional profit quality.
FCP aggregate OOS loses because explicit menu coverage is too narrow.
```

### 5.2 Strict BSP-compressed completion 失败

目标：

- 固定 FCP anchor prices。
- 对 missing bundles 用 BSP-style size price `q_s` 补全。
- OOS 时在 completed full bundle space 上 replay。

相关脚本：

- `project-root/code_submission_project/code_submission/src/data/run_phase3_oos_bsp_completion_probe.py`
- `project-root/code_submission_project/code_submission/src/data/diagnose_phase3_oos_bsp_completion_infeasibility.py`

实验目录：

- `experiments/phase3_oos_bsp_completion_probe_n10_normal_rho0.0_full_hvhm_inst001/`
- `experiments/phase3_oos_bsp_completion_infeasibility_diag_n10_normal_rho0.0_full_hvhm_inst001/`

关键文件：

- `probe_summary.md/json`
- `diagnosis_summary.json`
- `variant_a_gurobi.log`
- `variant_b_gurobi.log`
- `variant_a_iis.ilp`
- `variant_b_iis.ilp`

结果：

- Variant A Anchored BSP Projection：infeasible。
- Variant B Reduced-Coupling BSP Projection：infeasible。

根因：

- FCP anchor prices 带有 bundle identity 信息。
- 单一 `q_s` 把所有同 size missing bundles 压成一个价格。
- 不同 anchors 对同一个 `q_s` 施加互相矛盾的上下界。

### 5.3 Heuristic same-size completion 失败

脚本：

- `project-root/code_submission_project/code_submission/src/data/run_phase3_oos_heuristic_completion_probe.py`

实验目录：

- `experiments/phase3_oos_heuristic_completion_probe_n10_normal_rho0.0_full_hvhm_inst001/`

结果文件：

- `heuristic_probe_summary.md/json`

结论：

- 直接 same-size propagation 可行但经济效果很差。
- best direct heuristic `same_size_anchor_max` 的 OOS revenue = `-6.1547`，比 restricted FCP OOS `2.3990` 差很多。
- 加 cost floor 后避免负利润，但 OOS 仍远低于 restricted baseline。

### 5.4 Variant C hybrid customer-choice completion 仍 infeasible

脚本：

- `project-root/code_submission_project/code_submission/src/data/run_phase3_oos_variant_c_probe.py`

实验目录：

- `experiments/phase3_oos_variant_c_probe_n10_normal_rho0.0_full_hvhm_inst001/`

关键文件：

- `variant_c_probe_summary.md/json`
- `variant_c_iis.ilp`

结果：

- solver status = `3` infeasible。
- 根因仍是 size-only non-anchor price 与 fixed high-price anchors 之间的 subadditivity chain 冲突。

相关设计文档：

- `research-tracker/weekly-reports/2026-W16-fcp-gcn-vs-cpbsd-main-n5/Phase3_VariantC.md`
- `research-tracker/weekly-reports/2026-W16-fcp-gcn-vs-cpbsd-main-n5/phase3_variant_exploration.md`

### 5.5 Component pricing completion 未形成有效修复

脚本：

- `project-root/code_submission_project/code_submission/src/data/run_phase3_oos_component_pricing_probe.py`

实验目录：

- `experiments/phase3_oos_component_pricing_probe_n10_normal_rho0.0_full_hvhm_inst001/`

结果文件：

- `component_pricing_probe_summary.md/json`

当前 artifact 中的 summary：

- anchor count = `36`
- full bundle count = `1024`
- restricted FCP OOS = `2.3990`
- BSP OOS = `2.3147`
- component pricing LP solver status = `5`
- feasible = `False`

周报中的更宽泛结论是：即便 component-pricing 类压缩能比 pure size 更细，也容易产生低价 non-anchor bundle 对 anchor sales 的 cannibalization，未能形成稳定正向 OOS 修复。

### 5.6 Extended Menu + per-bundle pricing 成功

脚本：

- `project-root/code_submission_project/code_submission/src/data/run_phase3_oos_extended_menu_probe.py`

实验目录：

- `experiments/phase3_oos_extended_menu_probe_n10_normal_rho0.0_full_hvhm_inst001/`

结果文件：

- `extended_menu_probe_summary.json`

方法：

- 不追求补全 full `2^N`。
- 从 in-sample customers 的 top-s prefix bundles 中生成候选。
- 与 FCP anchor menu 合并成 extended menu。
- anchor prices 固定。
- 新 candidates 用 per-bundle pricing。
- subadditivity 只在 offered menu 内 enforce。

单实例结果：

| Metric | Restricted FCP | Extended Menu |
| --- | ---: | ---: |
| In-sample revenue | 3.5619 | 3.5619 |
| OOS revenue | 2.3990 | 2.4622 |
| Menu size | 37 | 53 |
| New candidates | 0 | 16 |
| Extension runtime | - | 0.34s |
| Anchor preserved | - | true |

5-instance validation，`N=10 / normal_rho0.0_full_hvhm`：

| Method | InS Mean | OOS Mean | Runtime |
| --- | ---: | ---: | ---: |
| BSP | 2.7211 | 2.3470 | 10.5s |
| CPBSD-A | 3.2091 | 2.8480 | 300.0s |
| FCP-pruned-MB | 3.2555 | 2.2783 | 239.4s |
| FCP+ExtMenu | 3.2991 | 2.3392 | 239.8s |

结论：

- 5/5 seeds OOS 全部改善。
- 改善幅度平均 `+0.061`。
- 与 BSP 几乎持平，但仍低于 CPBSD-A。

### 5.7 GCN-PCP progressive chain candidate generation 更强

记录位置：

- `research-tracker/weekly-reports/2026-W16-fcp-gcn-vs-cpbsd-main-n5/phase3_variant_exploration.md`

方法：

- 使用 GCN per-customer per-product probability。
- 对每个 customer 选 `P[k,n] >= threshold` 的商品。
- 按概率降序生成 progressive bundle chain。
- 相当于 PCP-style candidate generation，但排序依据来自 GCN probability。

单实例 threshold 对比，主诊断实例 `seed_20260413`：

| Strategy | New candidates | Menu | OOS | Delta vs FCP | Runtime |
| --- | ---: | ---: | ---: | ---: | ---: |
| FCP baseline | 0 | 34 | 2.201 | - | - |
| top-s prefix | 16 | 50 | 2.260 | +0.059 | 0.2s |
| GCN-PCP t=0.5 | 147 | 181 | 2.347 | +0.146 | 11s |
| GCN-PCP t=0.3 | 165 | 199 | 2.372 | +0.171 | 20s |
| GCN-PCP t=0.2 | 172 | 206 | 2.405 | +0.204 | 19s |
| GCN-PCP t=0.1 | 180 | 214 | 2.374 | +0.173 | 23s |

5-instance validation：

| Method | InS Mean | OOS Mean | Runtime | OOS vs FCP |
| --- | ---: | ---: | ---: | ---: |
| BSP | 2.7211 | 2.3470 | 10.5s | +0.069 |
| CPBSD-A | 3.2091 | 2.8480 | 300.0s | +0.570 |
| FCP-pruned-MB | 3.2555 | 2.2783 | 239.4s | 0.000 |
| FCP+GCN-PCP t=0.2 | 3.5317 | 2.4501 | 256.8s | +0.172 |

结论：

- 5/5 seeds OOS 全部改善。
- OOS 超过 BSP：`2.4501 > 2.3470`。
- 仍低于 CPBSD-A：`2.4501 < 2.8480`。
- extension overhead 约 `+17.5s`，低于 FCP 本体 runtime 的 8%。

### 5.8 Anchored / Joint FCP+BSP 尝试

文档：

- `research-tracker/weekly-reports/2026-W16-fcp-gcn-vs-cpbsd-main-n5/anchored_fcp_bsp_solver_strategy.md`
- `research-tracker/weekly-reports/2026-W16-fcp-gcn-vs-cpbsd-main-n5/joint_fcp_bsp_formulation.md`

代码：

- `project-root/code_submission_project/code_submission/src/data/solve_anchored_fcp_bsp.py`
- `project-root/code_submission_project/code_submission/src/data/eval_bsp_fcp_hybrid_oos.py`
- `project-root/code_submission_project/code_submission/src/data/run_anchored_fcp_bsp_hvhm_batch.py`
- `project-root/code_submission_project/code_submission/src/data/run_joint_fcp_bsp_experiment.py`
- `project-root/code_submission_project/code_submission/src/data/run_joint_clean_rerun.py`

输出：

- `experiments/anchored_fcp_bsp_hvhm_batch/`
- `experiments/anchored_fcp_bsp_hvhm_batch_smoke/`
- `experiments/joint_fcp_bsp_n5/`

当前理解：

- Anchored FCP+BSP 不是 full bundle completion，而是 fixed FCP menu + BSP size channel。
- 在 hvhm 中，严格保护 FCP sales 会把 BSP size prices 拉得很高，往往不能新增有效 OOS coverage。
- 在 random_ind 中，BSP channel 容易 cannibalize FCP 高利润 bundle，Hybrid 有害。
- 在 random_corr 中，BSP+FCP Hybrid 反而最优，因为产品趋同，BSP 覆盖广，FCP 少量高价值 bundle 仍有贡献。

## 6. 分析脚本与诊断工具索引

### 6.1 CPBSD/MB baseline 诊断

- `project-root/code_submission_project/code_submission/src/data/diagnose_bcs_tightness.py`
  - 诊断 MILP 解与 BCS evaluator 的 surplus/choice 是否一致。
- `project-root/code_submission_project/code_submission/src/data/analyze_mb_oos_attribution.py`
  - MB OOS drop customer-level attribution。
- `project-root/code_submission_project/code_submission/src/data/analyze_mb_bundle_coverage.py`
  - CPBSD setting 下 MB bundle coverage。
- `project-root/code_submission_project/code_submission/src/data/analyze_mb_native_bundle_coverage.py`
  - 原生 MB setting 下 bundle coverage。
- `project-root/code_submission_project/code_submission/src/data/compare_mb_appendix_c_literal.py`
  - Appendix C literal formulation 对比。
- `project-root/code_submission_project/code_submission/src/data/run_mb_generalization_compare_v2.py`
- `project-root/code_submission_project/code_submission/src/data/run_mb_oos_drop_grid_n5_n10.py`
- `project-root/code_submission_project/code_submission/src/data/run_mb_k_scaling_study.py`

### 6.2 GCN/FCP 训练和评估

- `project-root/code_submission_project/code_submission/src/data/Training_multi_layer_cpbsd_mb_x.py`
- `project-root/code_submission_project/code_submission/src/data/prepare_cpbsd_single_setting_gcn_dataset.py`
- `project-root/code_submission_project/code_submission/src/data/label_cpbsd_mb_from_manifest.py`
- `project-root/code_submission_project/code_submission/src/data/run_cpbsd_mb_training_pipeline.py`
- `project-root/code_submission_project/code_submission/src/data/run_random_cost_gcn_pipeline.py`
- `project-root/code_submission_project/code_submission/src/data/run_cpbsd_fcp_pruned_mb_compare.py`
- `project-root/code_submission_project/code_submission/src/data/run_cpbsd_fcp_pruned_mb_compare_parallel.py`
- `project-root/code_submission_project/code_submission/src/data/run_cpbsd_fcp_ls_global_topk_compare.py`

### 6.3 Phase 3 OOS 修复 probes

- `project-root/code_submission_project/code_submission/src/data/run_phase3_oos_bsp_completion_probe.py`
- `project-root/code_submission_project/code_submission/src/data/diagnose_phase3_oos_bsp_completion_infeasibility.py`
- `project-root/code_submission_project/code_submission/src/data/run_phase3_oos_heuristic_completion_probe.py`
- `project-root/code_submission_project/code_submission/src/data/run_phase3_oos_variant_c_probe.py`
- `project-root/code_submission_project/code_submission/src/data/run_phase3_oos_component_pricing_probe.py`
- `project-root/code_submission_project/code_submission/src/data/run_phase3_oos_extended_menu_probe.py`

### 6.4 周报侧分析脚本

- `research-tracker/weekly-reports/2026-W16-fcp-gcn-vs-cpbsd-main-n5/analyze_bsp_vs_fcp_instance001.py`
- `research-tracker/weekly-reports/2026-W16-fcp-gcn-vs-cpbsd-main-n5/analyze_hvhm_fcp_cpbsd_a_failure.py`
- `research-tracker/weekly-reports/2026-W16-fcp-gcn-vs-cpbsd-main-n5/run_phase2_fcp_mb_shortlist.sh`
- `research-tracker/weekly-reports/2026-W16-fcp-gcn-vs-cpbsd-main-n5/run_phase2_fcp_mb_n10_n30_selected.sh`

## 7. 实验目录索引

### 7.1 复现与 baseline

- `experiments/cpbsd_baselines_v2/`
  - smoke subset v2 baseline，含 unified logs、plots、per-instance JSON、summary reports。
- `experiments/cpbsd_main_n5/`
  - N=5 main/full-grid run snapshot，部分结果。
- `experiments/mb_oos_drop_grid_n5_n10_t300/`
  - OOS drop grid，含 N=5/N=10 多 setting MB/BSP 结果与 solver logs。
- `experiments/mb_generalization_compare_v2/`
- `experiments/mb_generalization_compare_v2_t600/`
- `experiments/mb_generalization_n5_all_settings/`
- `experiments/mb_bundle_coverage_v2/`
- `experiments/mb_native_bundle_coverage/`
- `experiments/mb_literal_appendix_c_check/`

### 7.2 GCN 训练数据与标签

- `experiments/cpbsd_gcn_single_setting_n5_normal_rho0_full_hvhm/`
  - 5000 CPBSD instances 与 train/eval/test manifests。
- `experiments/cpbsd_gcn_single_setting_n5_normal_rho0_full_hvhm_chunked_manifests/`
  - chunked manifests。
- `experiments/cpbsd_mb_labels_chunked_run1/`
  - MB labels，chunk summaries，merged manifests。
- `experiments/cpbsd_random_ind_n5/`
  - random_ind 训练数据与 MB labels。
- `experiments/cpbsd_random_corr_n5/`
  - random_corr 训练数据与 MB labels。

### 7.3 GCN/FCP effect experiments

- `experiments/cpbsd_fcp_pruned_mb_compare_n10k50_strict300/`
  - 单实例 FCP-pruned-MB vs BSP/CPBSD-A/full MB。
- `experiments/cpbsd_fcp_pruned_mb_compare_n10k50_10inst_strict300/`
  - 10-instance aggregate。
- `experiments/cpbsd_fcp_ls_global_topk_compare_n10k50_strict300/`
  - Global Top-K LS 尝试。
- `experiments/fcp_mb_phase2_shortlist_n5_5inst/`
  - N=5 shortlist 5-seed runs。
- `experiments/fcp_mb_phase2_selected_n10_n30_5inst/`
  - N=10/N=30 selected setups 5-seed runs。
- `experiments/fcp_random_cost_eval_n5_random_ind/`
- `experiments/fcp_random_cost_eval_n10_random_ind/`
- `experiments/fcp_random_cost_eval_n30_random_ind/`
- `experiments/fcp_random_cost_eval_n5_random_corr/`
- `experiments/fcp_random_cost_eval_n10_random_corr/`
- `experiments/fcp_random_cost_eval_n30_random_corr/`

### 7.4 OOS repair / Hybrid experiments

- `experiments/phase3_oos_bsp_completion_probe_n10_normal_rho0.0_full_hvhm_inst001/`
- `experiments/phase3_oos_bsp_completion_infeasibility_diag_n10_normal_rho0.0_full_hvhm_inst001/`
- `experiments/phase3_oos_heuristic_completion_probe_n10_normal_rho0.0_full_hvhm_inst001/`
- `experiments/phase3_oos_variant_c_probe_n10_normal_rho0.0_full_hvhm_inst001/`
- `experiments/phase3_oos_component_pricing_probe_n10_normal_rho0.0_full_hvhm_inst001/`
- `experiments/phase3_oos_extended_menu_probe_n10_normal_rho0.0_full_hvhm_inst001/`
- `experiments/anchored_fcp_bsp_hvhm_batch/`
- `experiments/anchored_fcp_bsp_hvhm_batch_smoke/`
- `experiments/joint_fcp_bsp_n5/`

## 8. 报告与文字产物索引

### 8.1 总览/复现

- `Report/CPBSD_progress_report.md`
- `subprojects/revenue-management-core-experiments/Report/CPBSD_progress_report.md`
- `subprojects/revenue-management-core-experiments/ARTIFACT_INDEX.md`
- `research-tracker/EXPERIMENT_MAP.md`

### 8.2 2026-W16 Phase 1/2/3 主文档

- `research-tracker/weekly-reports/2026-W16-fcp-gcn-vs-cpbsd-main-n5/README.md`
- `setup_inventory.md`
- `setup_shortlist.md`
- `paper_repo_naming_map.md`
- `comparison_avg.md`
- `comparison_avg.csv`
- `dominance_summary.md`
- `phase3_oos_logic_note.md`
- `phase3_probe_results.md`
- `phase3_variant_exploration.md`
- `Phase3_VariantC.md`
- `phase3_random_cost_gcn_training.md`
- `bsp_vs_fcp_oos_instance001_report.md`
- `hvhm_fcp_cpbsd_a_failure_analysis.md`
- `anchored_fcp_bsp_solver_strategy.md`
- `joint_fcp_bsp_formulation.md`

### 8.3 早期项目报告

- `project-root/code_submission_project/code_submission/docs/reports/MB_GCN_训练与接入MB阶段汇报_2026-03-21.md`
- `project-root/code_submission_project/code_submission/docs/reports/dataset_compatibility_analysis.md`
- `project-root/code_submission_project/code_submission/docs/reports/实验框架与统一口径速查.md`
- `project-root/code_submission_project/code_submission/docs/reports/项目架构总结.md`
- `project-root/code_submission_project/code_submission/docs/reports/调用关系图.md`

## 9. 当前开放问题与建议推进线

### 9.1 不建议继续投入的线

1. **Pure size-only BSP completion**
   - Variant A/B/C 均暴露同一结构性问题：同 size missing bundles 被单一 `q_s` 绑定，无法承接 FCP anchor identity。
2. **Coarse same-size propagation**
   - 虽然 feasible，但 OOS 结果显著低于 restricted FCP baseline。
3. **Global Top-K LS**
   - 在已跑实例上没有带来 candidate improvement。

### 9.2 值得继续的线

1. **GCN-PCP progressive candidate generation**
   - 当前在 hvhm N=10 diagnostic batch 中已显著改善 OOS，并超过 BSP。
   - 仍需扩展到 N=30 和更多 setup。
2. **Targeted extended menu**
   - 不补 full space，只补高概率 OOS coverage 缺口。
   - 需要系统比较 candidate size、runtime、OOS gain。
3. **Cost-structure aware strategy selection**
   - random_ind：纯 FCP 强。
   - random_corr：BSP+FCP Hybrid 更合适。
   - hvhm：CPBSD-A 仍强，FCP 需要更好的 OOS candidate expansion。
4. **Spread statistics 与 full four-method comparison**
   - Phase 2 当前是三方法结果，缺 `CPBSD-MILP/CPBSD`。
   - 若汇报要求严格对应原周目标，需要补 spread stats 或明确 scope 是三方法 comparison。

### 9.3 最短下一步建议

下一轮最好只做一个聚焦批次：

```text
N=30, normal_rho0.0_full_hvhm and normal_rho0.5_full_hvhm
methods: BSP / CPBSD-A / FCP-pruned-MB / FCP+GCN-PCP(t=0.2 or tuned)
seeds: 20260413-20260417
metrics: Rev-In, Rev-OOS, runtime, menu size, OOS outside count
```

原因：

- Phase 2 已显示 N=30 是 FCP runtime 最有故事性的场景。
- OOS blocker 在 N=30 最明显。
- GCN-PCP 已在 N=10 证明能修 coverage，最值得看能否迁移到 N=30。

