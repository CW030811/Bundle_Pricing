# Research Direction

## 基本信息

- Direction ID：`mb-oos-generalization`
- 标题：`MB 的 OOS Generalization 与小样本过拟合`
- 状态：`running`
- 负责人：`shared`
- 创建日期：`2026-03-31`
- 来源会议：`research-tracker/meetings/2026-03-29_weekly-sync.md`

## 核心研究问题

`为什么 MB 在部分 setting 下出现明显的 out-of-sample revenue drop，以及如何稳定降低这个 drop。`

## 假设

- `MB 在 K=50 时对 32 个 bundle price 参数发生了过拟合`
- `hard setting 会显著放大这种过拟合`
- `增加 training size 或引入更稳健的价格选择规则能改善 OOS 表现`

## 为什么这个方向重要

- `如果 MB baseline 本身不稳，后续加速结果就缺少说服力`
- `这是当前 Bundle Pricing 线里最清晰、最可汇报的问题之一`

## 成功标准

- `能用实验说明 OOS gap 的主要来源，并给出稳定有效的缓解方案`
- `或至少明确在什么 setting 下 MB 的 OOS 问题最严重、什么 setting 下可接受`

## 当前实验设计

- 自变量：`K / setting / price regularization or validation rule`
- 控制变量：`N=5 基线口径、统一 OOS 评估方式`
- 评价指标：`Rev-In/BSP, Rev-Out/BSP, Drop%, runtime`
- 参考脚本 / 路径：`experiments/cpbsd_baselines_v2/results/`

## 最新结论

- 日期：`2026-03-31`
- 结论摘要：`在 normal, rho=0.0, full, hvhm 这个困难 setting 下，MB 的约 27.8% drop 是真实且可复现的。customer-level attribution 支持“边界定价导致 OOS 流失”的机制解释。把 K 提高到 200 能把 drop 压到约 10.7%，但在 K=50 下，haircut/shrinkage/support-smoothing/validation 等改良尚未在诚实选择口径下稳定胜出。`

## 已完成实验记录

- `experiments/cpbsd_baselines_v2/results/Baseline_V2_Results_Summary.md`
- `experiments/cpbsd_baselines_v2/results/MB_Generalization_Diagnostic_Report.md`
- `experiments/cpbsd_baselines_v2/results/FULL_GRID_GENERALIZATION_VALIDATION_REPORT.md`
- `experiments/cpbsd_baselines_v2/results/mb_oos_attribution/MB_OOS_Research_Report.md`
- `experiments/cpbsd_baselines_v2/results/mb_oos_attribution/MB_OOS_Attribution_Report.md`

## 当前判断

- `继续推进`

## 下一步决策点

- `锁定 common benchmark setting，明确之后汇报到底采用 hard setting 还是 average setting`
- `把 training-size-scaling 变成正式固定实验线`
- `继续比较 honest validation 与更保守价格规则之间的取舍`
- `把“如何 ex ante 选出更稳健 price table”单独抽成 risk-aware selection 问题`

## 相关产物路径

- 代码：`project-root/code_submission_project/code_submission/src/data/`
- 输出目录：`experiments/cpbsd_baselines_v2/results/`
- 图表 / 报告：`experiments/cpbsd_baselines_v2/results/mb_oos_attribution/`
