# Research Direction

## 基本信息

- Direction ID：`mb-bundle-coverage-and-candidate-space`
- 标题：`Bundle Coverage、Candidate Space 与 GCN/PCP/FCP 设计`
- 状态：`running`
- 负责人：`shared`
- 创建日期：`2026-03-31`
- 来源会议：`research-tracker/meetings/2026-03-29_weekly-sync.md`

## 核心研究问题

`最优 bundle 需求到底有多集中，以及这种覆盖结构对 candidate pruning 和 GCN 设计意味着什么。`

## 假设

- `CPBSD 小规模 setting 下存在相对集中的高覆盖 bundle，因此候选筛选更容易成功`
- `原生 MB setting 的覆盖显著更分散，简单阈值型 FCP 可能不足`
- `size-aware 或 hierarchical 预测可能比直接预测 exact bundle 更稳`

## 为什么这个方向重要

- `这决定 GCN / PCP / FCP 到底应该如何设计候选空间`
- `如果覆盖本身很分散，单纯靠少量 top bundles 做近似可能很不稳`

## 成功标准

- `明确不同 setting 下 coverage 集中度差异`
- `把 coverage 结论转化成 candidate strategy 的具体设计原则`

## 当前实验设计

- 自变量：`problem setting, bundle space size, candidate strategy`
- 控制变量：`coverage 统计口径、实例来源`
- 评价指标：`Top-N coverage, bundles needed for 80/90/95% coverage, candidate count`
- 参考脚本 / 路径：`experiments/mb_bundle_coverage_v2/`, `experiments/mb_native_bundle_coverage/`

## 最新结论

- 日期：`2026-03-31`
- 结论摘要：`在 CPBSD N=5 setting 下，Top-20 bundle 已覆盖约 90.3% 的需求；但在原生 MB n=10 setting 下，Top-20 只能覆盖约 21% 到 25%。这说明 candidate pruning 在 CPBSD setting 里更有希望，而在原生 MB setting 里需要更结构化的预测策略。native MB 的 top bundles 多为 size 8 到 10 的大 bundle，也提示“先预测 size 再预测组合”的方案值得认真测试。`

## 已完成实验记录

- `experiments/mb_bundle_coverage_v2/mb_bundle_coverage_experiment.md`
- `experiments/mb_bundle_coverage_v2/mb_bundle_coverage_runlog.md`
- `experiments/mb_native_bundle_coverage/mb_native_bundle_coverage_experiment.md`
- `experiments/mb_native_bundle_coverage/mb_native_bundle_coverage_runlog.md`

## 当前判断

- `继续推进`

## 下一步决策点

- `把 coverage 结果转成 PCP/FCP 的具体候选生成规则`
- `验证 common setting 与更大 N 下 coverage 是否仍有相同形态`
- `比较 exact bundle prediction 与 size-aware prediction 的信息增益`

## 相关产物路径

- 代码：`project-root/code_submission_project/code_submission/src/data/`
- 输出目录：`experiments/mb_bundle_coverage_v2/`, `experiments/mb_native_bundle_coverage/`
- 图表 / 报告：`experiments/mb_bundle_coverage_v2/mb_bundle_topN_cumulative.png`
