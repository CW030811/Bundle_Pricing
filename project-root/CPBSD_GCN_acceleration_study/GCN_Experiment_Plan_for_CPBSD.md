# GCN 实验思路与计划（CPBSD 框架）

> 目标：在 **CPBSD 问题定义与机制约束** 下，设计可落地的 GCN 加速实验方案，验证加速效果与收益表现。

---

## 1) 方向1思路介绍及其不考虑原因

## 1.1 思路介绍
方向1的核心是：
- 在 CPBSD 的问题设定下，用 CPBSD-MILP 求得的结果做监督信号（label）去学习“optimal bundle structure”；
- 但推理/求解阶段不走 CPBSD 机制，而是套回 Hanson 的 MB（Mixed Bundling）求解框架；
- 最终与 CPBSD-MILP / CPBSD-A 做 Time 与 Revenue 对比。

## 1.2 暂不作为主线的原因
该方向有两类关键问题：

1) **监督-机制错配，学习有效性不稳定**
- 监督信号来自 CPBSD 机制（\(p_n,d_s\) 结构化定价）。
- 推理却切换到 MB 的 bundle-level 自由定价机制。
- 训练目标与推理机制不一致，模型可能学到“跨机制映射噪声”，实际提升不稳定。

2) **对比公平性不足（对 MB 天生不公平）**
- 当前 CPBSD 设置采用 additive setting（并配套其机制优势），天然更贴合 CPBSD 的设计初衷。
- 在该 setting 下把结果“套回 MB”比较，容易出现“不是 MB 不行，而是实验机制偏置”的争议。
- 因此该方向更适合做补充讨论，不适合作为主贡献主线。

> 结论：方向1不作为主线推进，仅保留为可选补充/消融。

---

## 2) 方向2思路介绍与三层方法

## 2.1 总体思路
在 **不改变 CPBSD 机制本体** 的前提下，只优化求解效率层：

- Layer 1：GCN 预测候选产品重要性
- Layer 2：Safe Pruning 保守裁剪，控制误杀风险
- Layer 3：在裁剪后空间上求解 Reduced CPBSD-MILP

这一范式与此前 MB 加速范式一致（学习→裁剪→精确/近似优化），可解释性与迁移性更强。

## 2.2 三层方法定义

### Layer 1: GCN Scoring
- 输入：产品关系图、估值/成本特征（如 \(v_n^k, c_n\) 相关统计）、历史最优选择信号等。
- 输出：产品级打分 \(s_{k,n}\)（先做 per-k 版本）。
- 作用：给后续 MILP 提供候选集排序依据。
- 问题：GCN的图结构是否需要修改？训练是否需要修改？

### Layer 2: Safe Pruning
- 基于 GCN 打分取 top-\(M\) 产品形成候选集；
- 额外加入安全补集（大小 \(r\)），如基于 \(v_n^k-c_n\) 或全局高潜在盈余产品，降低误剪最优产品风险。
- 输出：压缩后的产品集合 \(\mathcal{N}'_k\)，\(|\mathcal{N}'_k|=M+r\)（或近似）。
- 问题：之前的FCP/PCP Pruning是Bundle维度，现在的Pruning还应该是Bundle维度吗（CPBSD是Product维度），如果我们保留Product，保留的逻辑又应该如何设定？

### Layer 3: Reduced CPBSD-MILP
- 在裁剪后变量空间上构建并求解 CPBSD-MILP；
- 保持 CPBSD 机制变量与约束结构（\(p,d\) 与客户选择一致性）不变，仅缩减候选产品维度；
- 目标：在尽量小 Revenue 损失下显著降低求解时间。

## 2.3 为什么这是主线优选
- 机制一致：不更换 CPBSD 定价机制，避免“跨机制错配”；
- 叙事统一：与既有“学习+优化”加速范式一致；
- 工程可落地：可以先从 per-k 裁剪起步，再升级到 per-(k,s)。

---

## 3) 方向2实验设计细节

## A. 对比组
1. **CPBSD-MILP**（oracle，小规模 \(n=5\)）
2. **CPBSD-A**（\(n=10,30\)）
3. **CPBSD-MILP + GCN-Prune**（本文方法）

> 说明：小规模用 MILP 作为精确参照；大规模用 CPBSD-A 作为现实可解基线。

## B. 指标
- **Revenue**
  - in-sample revenue
  - out-of-sample revenue
- **Time**
  - wall-clock time
  - 求解器节点数（branch-and-bound nodes）

> 报告建议：给出相对提升（vs 基线）与绝对值两套口径。

## C. 关键超参数
1. **\(M\)**（裁剪宽度）
   - 画 Pareto 曲线：Time vs Revenue
2. **\(r\)**（安全补集大小）
   - 观察误剪风险与时间开销的平衡
3. **Top-M 粒度**
   - per-(k,s) vs per-k
   - 建议先从 **per-k** 简化实现，再扩展到 per-(k,s)

---

## 执行优先级建议（简版）

1. 先实现 per-k 的 GCN+Safe Pruning+Reduced MILP 最小可跑版本
2. 在 \(n=5\) 上对齐 oracle（CPBSD-MILP）验证可行性
3. 扩展到 \(n=10,30\) 与 CPBSD-A 比较时间-收益曲线
4. 最后再做 per-(k,s) 精细化版本与消融实验

---

## 一句话总结

主线采用方向2：**在 CPBSD 机制不变的前提下，用 GCN 做安全裁剪并驱动 Reduced CPBSD-MILP，实现“可解释、可复现、可扩展”的求解加速。**
