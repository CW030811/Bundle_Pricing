# 2026-03-04 CPBSD 复现记录（简要）

## 脚本新增/修改
- 新增：`src/data/solve_cpbsd_milp.py`（CPBSD-MILP）
- 新增：`src/data/solve_cpbsd_a.py`（CPBSD-A 近似）
- 新增：`src/data/run_cpbsd_baselines.py`（一键跑基线+统一日志）
- 新增说明：`CPBSD_REPRO_IMPLEMENTATION_NOTES.md`（smoke/full grid、MILP/A 假设说明）
- 生成器：`generate_data_CPBSD.py`

## 关键修复（按用户清单）
- Big-M 安全：加 `p_ub/d_ub` 上界，`M` 可配，日志记录。
- 日志口径：`time=wall_time` + `solver_runtime`，补 `mip_gap/best_bound/sol_count/time_limit`。
- status 统一：`status_code` + `status_text`。
- in/out revenue 字段补齐。
- 移除额外约束 `p>=d`（不在论文原文）。
- time-limit 按论文规模：n=5/10/30 → 300/600/1200s。
- 明确标注 experiment_scope=smoke_subset。

## 实验（smoke subset）
- 组合：normal + rho=0 + full + hvhm；每个 N 5 个实例。
- Oracle：CPBSD-MILP @ n=5；Baseline：CPBSD-A @ n=10,30。
- 结果输出目录：`code_submission/experiments/cpbsd_baselines/`（unified_log.csv/json + results/）。

## 最新结果摘要（均值）
- n=5：rev_in≈1.5089，rev_out≈1.4033，time≈300s，nodes≈27k，gap≈0.0935（全部 TIME_LIMIT）
- n=10：rev_in≈2.2133，rev_out≈1.9808，time≈600s，nodes≈2.8k，gap≈0.7841（全部 TIME_LIMIT）
- n=30：rev_in≈0.0，rev_out≈0.0255，time≈1200s，nodes≈1，gap=inf（疑似过保守，待诊断）
- 异常记录：CPBSD-A 在 n=30 出现“全不买”退化解；已加 warm-start（p=c+ε,d=0）验证可把 rev_in 提升到 ≈0.03，但仍偏低，后续继续诊断。

## GitHub 推送
- 仓库：`CW030811/Bundle_Pricing`
- 分支：`cpbsd-milp-and-docs-clean`
- 已同步最新修复与说明文档。
