# MB Out-of-Sample 表现研究报告

## 1. 研究目标

本报告总结本次会话中围绕 `experiments/cpbsd_baselines_v2` 的 MB (Mixed Bundling) 基线所做的复现、诊断、归因与改良实验，回答两个核心问题：

1. 为什么 MB 在当前 `N=5, K=50, normal, rho=0.0, full, hvhm` 设置下出现严重的 out-of-sample revenue drop？
2. 在保持 `N=5, K=50` 不变的前提下，我们尝试了哪些改良方案，它们是否有效？

---

## 2. 结论摘要

本次研究的核心结论如下：

1. **MB 的 out-of-sample 表现差是真实现象，不是 replay/缓存/phantom-bundle 的实现 bug。**
2. **主因是小样本下的高自由度价格表过拟合。** 在 `N=5` 时，MB 需要为 `2^5 = 32` 个 bundle 定价，而训练样本只有 `K=50`，等于每个价格参数只有 `1.6` 个样本支撑。
3. **过拟合的具体表现是：训练集里大量高利润 bundle 被定在“刚好能成交”的边界上。** 换到 out-of-sample 后，许多客户不再购买这些高利润 bundle，而是转去更便宜的 bundle，或者直接回到 outside option。
4. **在保持 `N=5, K=50` 不变时，本次尝试的 5 组改良方案在“诚实的 5-fold validation 选择”口径下都没有稳定优于 baseline MB。**
5. **但存在一个重要信号：若允许 ex post 以 out-of-sample 为准看参数，保守的 haircut 确实能提升 OOS revenue。** 问题不是“没有更好价格”，而是“用 50 个样本的内部 validation 很难可靠地把它选出来”。

---

## 3. 基线现象：MB 的 OOS Drop 明显高于其他方法

基线复现结果见：

- `Baseline_V2_Results_Summary.md`

在 `N=5, K=50` 的 5 个 instance 上：

- MB 的 mean `Rev-In/BSP = 1.343`
- MB 的 mean `Rev-Out/BSP = 1.060`
- MB 的 mean `Drop = 27.8%`

对比：

- CPBSD-MILP: `12.2%`
- CPBSD-A: `8.9%`
- BSP: `8.3%`

而且即使只看求解为 `OPTIMAL` 的 MB 实例，drop 仍然很高：

- `inst001`: `36.1%`
- `inst002`: `29.0%`
- `inst003`: `24.7%`

这说明问题不是由 `TIME_LIMIT` 主导的，而是更深层的泛化问题。

---

## 4. 第一层证据：这不是评估语义 bug

本会话对 MB 的求解/评估语义做了代码审计和数值复算，结论是：

1. 当前 `v2` 评估使用的是 **完整 32-bundle price table**，不是只用 selected bundles。
2. 当前 replay 在 equal-surplus tie 时会偏向 **更高 firm profit** 的 bundle，而不是保守地强制 outside option。
3. 复算后，MB 的 `objective` 与 `revenue_in_sample` 平均差距只有 **0.1038%**。

这意味着：

- 当前结果并不是“求解器内部认为能卖，外部 replay 却不认”的语义错配；
- severe drop 主要不是评估 bug，而是价格表本身对训练样本过拟合。

---

## 5. 第二层证据：phantom bundle 和低于成本定价不是主因

在 `MB_Generalization_Diagnostic_Report.md` 中，我们做了两组零成本诊断：

1. **MB-full**: 用全部 32 个 bundle price
2. **MB-sel**: 只保留训练集中被买过的 bundle 价格
3. **MB-floor**: 把价格 clip 到 `max(price, bundle_cost)`

结果：

- `MB-floor = MB-full`
- `MB-sel` 比 `MB-full` 还略差

因此可以排除：

- “因为有 bundle 低于成本卖，所以 OOS 崩了”
- “因为 phantom bundle 太多，所以 OOS 崩了”

剩下最直接的解释就是：**价格调优本身过拟合了训练样本。**

---

## 6. 第三层证据：K-Scaling 直接说明问题是 sample complexity

在同一份诊断报告中，还做了固定设置下的 K-scaling：

| K | Samples/Param | MB Mean Drop% |
|---|---:|---:|
| 50  | 1.6 | 27.8% |
| 100 | 3.1 | 20.6% |
| 200 | 6.2 | 10.7% |

这条趋势非常关键：

- 当 `K` 从 `50 -> 100 -> 200` 增长时，MB 的泛化 gap 单调收敛；
- 这强烈支持“MB 在当前设置下的主要问题是样本不足以支撑 32 维 bundle price table”；
- 如果这是纯实现 bug，通常不会随着 `K` 增长出现如此规则的改善。

---

## 7. 第四层证据：客户层面确实存在大量“边界成交”

为了看清楚过拟合发生在什么位置，本次额外对 `inst001` 和 `inst005` 做了 bundle/customer 级归因，结果见：

- `MB_OOS_Attribution_Report.md`

### 7.1 整体行为变化

我们复算得到 MB 的平均行为变化：

- MB buy rate: `0.8400 -> 0.6926`
- MB outside rate: `0.1600 -> 0.3074`
- MB bundle-31 share: `0.1600 -> 0.0794`

对比 BSP：

- BSP buy rate: `0.6480 -> 0.5988`

这说明 MB 的主要损失不是“单笔利润先变差”，而是 **高利润 bundle 在 OOS 上大量失去成交**。

### 7.2 inst005 的最典型例子

在 `inst005` 中，bundle `31 (11111)`：

- in-sample share: `0.2400`
- out-of-sample share: `0.0910`
- 单独贡献 revenue drop: `-0.3743 / customer`

更关键的是其边界客户：

- `customer 17`: surplus 只有 `+0.0218`
- `customer 19`: surplus 只有 `+0.0954`

这意味着模型确实在通过“把 full bundle 的价格顶到刚好还能成交”的位置来获取高利润。

到了 out-of-sample：

- 在 `[-0.10, 0)` 这个 near-miss 区间里，bundle `31` 有 `167` 个客户
- 其中 `163` 个改买了别的 bundle
- `4` 个直接转到了 outside option

这正是“训练集边界成交 -> OOS 大量流失”的直接证据。

### 7.3 inst001 的同类现象

在 `inst001` 中，bundle `31/29/27` 是三个最大的 revenue-loss source：

- bundle `31`: `-0.1899 / customer`
- bundle `29`: `-0.1628 / customer`
- bundle `27`: `-0.1241 / customer`

而这些 bundle 的 OOS near misses 分别达到：

- `146`
- `163`
- `172`

并且大多数客户不是“完全不买”，而是 **转去利润更低的 bundle**。这说明 MB 的局部价格面过于陡峭，OOS 轻微波动就会把客户从高利润 bundle 推到更便宜的替代 bundle。

---

## 8. 根因综合判断

基于以上四层证据，可以把 MB OOS 表现差的原因归纳为下面这条链：

1. 当前设置 `normal + full + hvhm` 本身难度高，产品均值和成本都跨度很大；
2. MB 在 `N=5` 时有 `32` 个 bundle 价格，自由度远高于 BSP/CPBSD-A；
3. `K=50` 只能给每个价格参数提供 `1.6` 个样本支撑；
4. 最终学出的价格表会把不少高利润 bundle 放在“刚好还能卖”的边界；
5. OOS 中客户 valuation 轻微变化后，这些 bundle 的 share 大幅下滑；
6. 客户要么转到更便宜的 bundle，要么直接 outside；
7. 因而 revenue 出现显著 drop。

一句话概括：

> MB 在当前 setting 下不是“不够能拟合”，而是“拟合得太自由，在 50 个样本上把 bundle-level 局部结构学得过细”。

---

## 9. 为什么论文里 MB 看起来没这么差

`MB_Generalization_Diagnostic_Report.md` 里给出的解释是成立的：

- 论文 boxplot 是 **135 种参数组合的聚合**
- 其中不少设置对 MB 更友好，例如：
  - `none heterogeneity`
  - `zero cost`
  - `uniform`

而我们当前看的这组：

- `normal`
- `full heterogeneity`
- `hvhm`

属于更容易让 MB 暴露过拟合的一档。因此，论文中 MB 的中位表现并不能代表当前这组困难 setting。

---

## 10. 在 N=5, K=50 不变时尝试过的改良方案

本次会话又进一步做了 5 组改良实验，统一放在：

- `results/mb_oos_attribution/exp01_* ... exp05_*`

所有实验都遵循同一口径：

- 固定 `N=5, K=50`
- 复用 baseline_v2 的 5 个 instance
- 复用同样的 OOS 评估
- 每组实验都有 `REPORT.md`、对比图、CSV

### 10.1 Experiment 01: Size-4/5 Margin Haircut

思路：

- 只对 size `4/5` 的 bundle margin 做 haircut

结果：

- 5-fold validation 选中了 `gamma = 1.0`
- 即：**诚实选择最终回到了 baseline**

但这组实验也给了一个很重要的额外信号：

- 若只看 candidate sweep，`gamma = 0.80` 的 mean OOS revenue 达到 **1.2223**
- 明显高于 baseline 的 **1.1598**

这说明 haircut **不是没潜力**，而是 `K=50` 下 validation 无法可靠地识别它。

### 10.2 Experiment 02: MB-to-BSP Price Shrinkage

思路：

- 用 `p'_S = alpha * p_MB(S) + (1-alpha) * p_BSP(|S|)` 把 MB 价格向 BSP size-price 收缩

结果：

- 5-fold validation 选中了 `alpha = 1.0`
- 即：**不 shrink**

候选 sweep 里没有出现比 haircut 更明显的 OOS 改善，因此这个方向在当前设计下不如 haircut promising。

### 10.3 Experiment 03: Support-Aware Price Smoothing

思路：

- 对低 support bundle 用 BSP size-price 做替换

结果：

- 选中的 threshold 为 `0`
- mean OOS revenue 从 `1.1598` 降到 `1.1503`

说明简单的 support smoothing 会直接损伤有用的 bundle 区分能力。

### 10.4 Experiment 04: Validation-Based Candidate Selection

思路：

- 不预设 transform family，而是让 validation 在 candidate library 中选最稳的 policy

结果：

- 5 个 instance 全部都选回 `baseline`

这再次说明：**不是 candidate library 完全没有 better-OOS policy，而是当前 validation 信号过弱，无法把它稳定选出来。**

### 10.5 Experiment 05: Minimum Surplus Margin Buffer

思路：

- 对被买中的 bundle 引入最小 surplus buffer，试图把 knife-edge sale 往安全区域推开

结果：

- 选中 `tau = 0.0`
- 与 baseline 基本相同

说明在当前 post-hoc 形式下，margin buffer 也没能被 validation 支持。

---

## 11. 对改良实验的总体评价

这 5 组实验的总体结论不是“所有改良方向都无效”，而是更精确的一句：

> 在 `K=50` 这个小样本 regime 下，**存在能提高 OOS 的保守价格策略，但常规 mean-validation 无法稳定把它们选出来**。

其中最典型的例子就是：

- `exp01_haircut`
- `gamma = 0.80`
- OOS 明显更高
- 但 CV revenue 大幅下降
- 因此 honest selector 拒绝它

这说明下一步真正该改的，不只是 transform family，而是 **selection criterion**。

---

## 12. 最终结论与建议

### 12.1 关于“原因”

MB OOS 表现差的主要原因已经比较明确：

- 不是 replay bug
- 不是 phantom bundle
- 不是低于成本定价
- 不是 time limit 主导

而是：

- `K=50` 太小
- `32` 个 bundle price 太自由
- 在困难 setting 下学出了大量边界成交
- OOS 中客户轻微漂移就会转单或流失

### 12.2 关于“改良”

在 `N=5, K=50` 不变前提下，本次尝试的 5 组改良方案在 honest validation 口径下都没有稳定优于 baseline。

但最值得继续推进的，不是放弃，而是转向下面两条线：

1. **Risk-aware selector**
   - 不再用 mean validation revenue 选
   - 改用 lower-quantile / worst-fold / `mean - lambda * std`

2. **Trade-off frontier**
   - 特别是对 haircut 这类明显存在 OOS 潜力的方向
   - 直接画出 `in-sample loss -> out-of-sample gain` 前沿
   - 把问题从“选不选得出来”转成“愿不愿意接受多少 train-side sacrifice”

### 12.3 如果允许改变 K

如果不强行固定 `K=50`，当前所有证据都指向同一个最有效方案：

- **增加 K**

已有证据显示：

- `K=50 -> 100 -> 200`
- MB mean drop `27.8% -> 20.6% -> 10.7%`

这是到目前为止最直接、最可靠的改善路径。

---

## 13. 相关文件

- `Baseline_V2_Results_Summary.md`
- `MB_Generalization_Diagnostic_Report.md`
- `MB_OOS_Attribution_Report.md`
- `experiment_suite_summary.csv`
- `exp01_haircut/REPORT.md`
- `exp02_shrinkage/REPORT.md`
- `exp03_support_smoothing/REPORT.md`
- `exp04_validation_selection/REPORT.md`
- `exp05_margin_buffer/REPORT.md`

