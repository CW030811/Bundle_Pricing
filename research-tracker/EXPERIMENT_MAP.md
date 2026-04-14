# Existing Experiment Map

这份文档用于把当前工作区里已经存在的实验记录压缩成一张“研究地图”，方便后续周报、会后复盘和方向追踪直接引用。

## 已读取的主要来源

- 会议笔记：`/Users/sensen/Desktop/Meeting Note/060329Note.md`
- `experiments/cpbsd_baselines_v2/results/Baseline_V2_Results_Summary.md`
- `experiments/cpbsd_baselines_v2/results/MB_Generalization_Diagnostic_Report.md`
- `experiments/cpbsd_baselines_v2/results/FULL_GRID_GENERALIZATION_VALIDATION_REPORT.md`
- `experiments/cpbsd_baselines_v2/results/mb_oos_attribution/MB_OOS_Research_Report.md`
- `experiments/cpbsd_baselines_v2/results/mb_oos_attribution/MB_OOS_Attribution_Report.md`
- `experiments/mb_bundle_coverage_v2/mb_bundle_coverage_experiment.md`
- `experiments/mb_bundle_coverage_v2/mb_bundle_coverage_runlog.md`
- `experiments/mb_native_bundle_coverage/mb_native_bundle_coverage_experiment.md`
- `experiments/mb_generalization_compare_v2/mb_generalization_compare_summary.md`
- `experiments/MB Acceleration/optimize_strategy_exploration/STRATEGY_EXPLORATION_REPORT.md`
- `experiments/MB Acceleration/optimize_strategy_exploration/monitoring/LARGE_INSTANCE_RUN_INCOMPLETE.md`

## 研究主线 1：MB 的 OOS Generalization 问题

### 这个方向在研究什么

解释为什么 MB 在部分 setting 下 in-sample 收益高，但 out-of-sample revenue drop 明显，并寻找能稳定降低 drop 的方法。

### 当前最重要的已知结论

- 在 stress setting `N=5, K=50, normal, rho=0.0, full, hvhm` 下，MB 的 mean drop 约 `27.8%`，显著高于 CPBSD-A 和 BSP。
- 这个问题不是 replay bug，也不是 phantom bundle 或低于成本定价导致的假象。
- 更直接的解释是：`2^N` 级 bundle price table 在小样本下发生了价格过拟合。
- `K` 从 `50 -> 100 -> 200` 时，drop 从 `27.8% -> 20.6% -> 10.7%`，说明 sample complexity 是关键变量。
- 在 paper-style 的 `405` 个 full-grid setting 聚合后，MB 平均 drop 降到 `16.14%`，说明之前的 smoke slice 是困难 setting，不代表整体均值。
- customer-level attribution 显示，高利润大 bundle 被定价在“刚好成交”的边界上，OOS 时很多客户会转向更便宜 bundle 或 outside option。

### 这条线当前最值得继续的问题

- 如何在不显著损失 revenue 的前提下，让 MB 在小样本 setting 下更稳健
- 应该把 `normal, rho=0.0, full, zero` 还是 `normal, rho=0.0, full, hvhm` 作为后续公共 benchmark
- holdout / validation / haircut / shrinkage 哪种选择机制最可靠
- training size 是否应该成为之后汇报中的主变量

### 对应 tracker direction

- `research-tracker/directions/mb-oos-generalization.md`

## 研究主线 2：Bundle Coverage 与 Candidate Space

### 这个方向在研究什么

研究“少量 bundle 能否覆盖大部分需求”，以及这件事对 GCN / PCP / FCP / candidate pruning 策略意味着什么。

### 当前最重要的已知结论

- 在 CPBSD setting (`N=5`) 下，bundle 覆盖相对集中：
  - Top-1 覆盖 `36.44%`
  - Top-20 覆盖 `90.30%`
  - 达到 `80%` 覆盖需要 `13` 个 bundle
- 但在原生 MB setting (`n=10`) 下，覆盖极度分散：
  - Top-20 只能覆盖约 `21% - 25%`
  - 达到 `80%` 覆盖需要 `198 - 295` 个 bundle
- 原生 MB 的 top bundles 大多是 size `8 - 10` 的大 bundle，说明 bundle size 结构可能比 exact bundle identity 更容易预测。
- 这意味着：在 CPBSD 小规模 setting 里，high-recall 候选筛选比较可行；在原生 MB setting 里，简单阈值型 candidate pruning 很可能不够。

### 这条线当前最值得继续的问题

- candidate pruning 是否应该变成 size-aware / hierarchical
- PCP 是否应该建立在 FCP 基础上做 nested progressive prediction
- 覆盖分析是否要扩展到 `N=20/30` 或更多 setting
- common setting 下 candidate recall 和 revenue 之间如何取舍

### 对应 tracker direction

- `research-tracker/directions/mb-bundle-coverage-and-candidate-space.md`

## 研究主线 3：MB / CPBSD 的加速与求解器瓶颈

### 这个方向在研究什么

寻找不改变目标或可行域前提下的安全加速方法，并识别最值得继续投入的加速杠杆。

### 当前最重要的已知结论

- MB 时间几乎都耗在 `model.optimize()`，构模耗时可以忽略，求解器才是主瓶颈。
- exact-safe 变体里，删除 self-envy 在部分 restricted candidate case 上有帮助，但在 full MB hard-tail case 上没有稳定收益。
- lean formulation 虽然减少了变量和约束，但并不自动带来速度提升。
- 有一组 large-instance 原始输出缺失，目前只能视为“不完整 run”，不能当作最终证据。
- CPU threads 在已有 `N=5` 对照里出现过约 `1.65x - 1.77x` 的加速，且目标值一致，这个方向值得继续系统比较。

### 这条线当前最值得继续的问题

- 补齐 incomplete raw outputs，得到完整的大规模 verdict
- 系统比较 threads 对 MB / BSP / CPBSD-A 的影响
- Hanson-style constraint reduction 是否能迁移到当前 formulation
- 是否要把“精确保真加速”和“允许轻微近似的加速”分成两条线

### 对应 tracker direction

- `research-tracker/directions/mb-optimize-acceleration.md`

## 研究主线 4：Formulation 等价性与 Subadditivity Family

### 这个方向在研究什么

检查当前 solver 与论文 Appendix C 的 literal formulation 是否存在本质偏差，以及哪些 constraint family 真正值得继续保留或加强。

### 当前最重要的已知结论

- literal solver 与 current solver 的 objective 往往很接近，但 price table 可以差很多，说明“价格表不同”不等于“目标质量不同”。
- literal solver 并没有系统性地带来更好的 OOS 表现，因此“没有逐字照抄 Appendix C”不是当前复现偏差的主要解释。
- 在 ablation 结果里，`subadd_only` 是唯一平均 OOS 为正的单开关，说明 subadditivity family 比 outside/envy 的 literal 追随更值得继续。
- 这条线和会议里的 `subadditive counterexample`、`IC constraint`、`theory` 方向可以自然接起来。

### 这条线当前最值得继续的问题

- `subadditivity` 约束到底该保留到什么粒度
- 为什么 objective 接近但 price table 差异很大
- tie-breaking / replay semantics / degeneracy 在这里分别扮演什么角色
- 这一条线应如何和理论写作结合

### 对应 tracker direction

- `research-tracker/directions/subadditivity-family-design.md`

## 会议驱动的新待探索方向

根据 `060329Note.md`，接下来还应持续跟踪这些方向：

- IC constraint 修改
- 补 `N=30` 实验
- 比较 BSP / CPBSD 的 CPU 并行效果
- 固定一个 common setting 做对照实验
- Hanson formulation 风格的 constraint 缩减
- subadditive remark 的反例
- PCP 建立在 FCP 基础上的 nested 设计
- training size 变化

这些方向里，已经有实验基础的优先纳入 `directions/`；其余可在下一次会后转成正式 direction 文件。
