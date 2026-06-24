# Research Direction

## 基本信息

- Direction ID：`mb-optimize-acceleration`
- 标题：`MB / CPBSD 的求解加速与 formulate-safe reduction`
- 状态：`running`
- 负责人：`shared`
- 创建日期：`2026-03-31`
- 来源会议：`research-tracker/meetings/2026-03-29_weekly-sync.md`

## 核心研究问题

`在不破坏目标或可行域的前提下，能否显著降低 MB / CPBSD 的求解时间。`

## 假设

- `真正的瓶颈在 optimize，而不是构模`
- `部分 exact-safe 的 constraint reduction 或 self-envy 移除可以改善求解`
- `CPU threads 和 candidate restriction 可能比单纯重写变量更有效`

## 为什么这个方向重要

- `加速是当前研究线最明确的应用目标之一`
- `如果能同时保持 revenue 并降低 runtime，汇报价值很高`

## 成功标准

- `得到一组可复现的加速证据，并说明速度提升来自哪里`
- `明确哪些 reduction 是安全有效的，哪些只是看起来更小但不更快`

## 当前实验设计

- 自变量：`variant formulation / self-envy removal / thread count / candidate restriction`
- 控制变量：`instance, time limit, mip gap, objective`
- 评价指标：`runtime, mip gap, objective delta, node count, optimize share`
- 参考脚本 / 路径：`experiments/MB Acceleration/optimize_strategy_exploration/`

## 最新结论

- 日期：`2026-03-31`
- 结论摘要：`已知 MB 的时间几乎都耗在 optimize 阶段。lean formulation 虽然减少了变量和约束，但并不保证更快；去掉 self-envy 在部分 restricted-candidate 场景上有帮助，但在 full MB hard-tail case 上没有形成稳定胜势。已有线程实验显示某些实例可获得约 1.65x 到 1.77x 的加速，但 large-instance 结果仍不完整，不能当作最终结论。`

## 已完成实验记录

- `experiments/MB Acceleration/optimize_strategy_exploration/STRATEGY_EXPLORATION_REPORT.md`
- `experiments/MB Acceleration/optimize_strategy_exploration/monitoring/LARGE_INSTANCE_RUN_INCOMPLETE.md`
- `/Users/sensen/Desktop/Meeting Note/060329Note.md`

## 当前判断

- `继续推进`

## 下一步决策点

- `补齐 large-instance 缺失 raw outputs，拿到完整 verdict`
- `把 CPU parallel comparison 扩展到 BSP / CPBSD-A / MB`
- `测试 Hanson-style reduction 与 IC constraint 调整是否能形成更稳定的加速`

## 相关产物路径

- 代码：`project-root/code_submission_project/code_submission/src/data/`
- 输出目录：`experiments/MB Acceleration/optimize_strategy_exploration/`
- 图表 / 报告：`experiments/MB Acceleration/optimize_strategy_exploration/STRATEGY_EXPLORATION_REPORT.md`
