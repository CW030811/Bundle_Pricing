# CPBSD 复现实现说明（可审计）

更新：2026-03-04

本文档用于明确区分：
1) 论文明确给出的建模/实验设定；
2) 当前代码实现细节；
3) 为保证可运行而做的工程补全（非论文原文）。

---

## 1. smoke subset 与 full grid 的区别

### smoke subset（当前默认）
用于快速验证“代码/求解/日志链路是否可用”，不是论文全量实验。

- 分布：`normal`
- 相关：`rho = 0`
- 异质性：`full`
- 成本场景：`hvhm`
- 实例：每个规模 5 个实例
- 规模：
  - CPBSD-MILP：`n=5`
  - CPBSD-A：`n=10,30`

用途：冒烟测试、管线联调、字段校验、快速比较。

### full grid（论文口径）
对应论文 Section 6 的组合实验：

- 5个分布：`exponential/logit/lognormal/normal/uniform`
- 3个相关结构：`rho in {-0.5,0,0.5}`
- 3个估值异质性：`none/partial/full`
- 3个成本场景：`zero/hvhm/hvlm`

组合数：`5 × 3 × 3 × 3 = 135`（每个 N 下）
若每组 5 个实例，则每个 N 为 675 个实例。

---

## 2. CPBSD-MILP 实现是否严格按论文

代码：`src/data/solve_cpbsd_milp.py`

### 2.1 严格对应部分（论文原文）
目标函数与约束集合按照论文 (9)-(23) 建模：
- 变量：`p_n, d_s, x_kns, y_ks, q_kns, w_ks, w_k, alpha_ks, beta_kns`
- 约束：
  - (9)(10)(11) BCS-dual 上界与可行性
  - (12)(13)(14)(15) 购买尺寸/选择一致性
  - (16)(17) q 的 big-M 线性化
  - (18)(19)(20) surplus 与一致性
  - (21) 折扣次可加
  - (22) 非负与 `d1=0`
  - (23) 二元变量

### 2.2 工程补全（非论文显式写出）
以下是实现中为“数值稳定与可复现”做的工程参数化：

1. **变量上界参数**：`p_ub`, `d_ub`
   - 作用：避免无界数值导致 big-M 不安全。
   - 默认：`p_ub = max(v_kn)`，`d_ub = p_ub`。

2. **big-M 设定**：`big_M`
   - 作用：用于 (16) 线性化。
   - 默认：`big_M = p_ub`（安全上界口径），可通过 CLI 覆盖。

3. **求解参数**：`time_limit`, `mip_gap`
   - 论文给了实验时限（N=5/10/30），代码在 runner 中按规模设置。

### 2.3 已移除的额外假设
- 早期测试中曾加入 `p[n] >= d[s]`（不在论文原始约束中）。
- 现已删除，当前模型不包含该额外约束。

---

## 3. CPBSD-A 是怎么实现的？是否完全按论文

代码：`src/data/solve_cpbsd_a.py`

### 3.1 论文可确定部分
论文明确：CPBSD-A 是 CPBSD-MILP 的近似替代，核心思想是使用预设偏好/排序来降低计算复杂度。

### 3.2 当前实现（工程化补全）
论文未给出完整可执行伪代码细节时，当前实现采用以下具体化方案：

1. **预设排序规则（补全项）**
   - 对每个客户 `k`，按 `z_kn = v_kn - c_n` 降序排序。
   - 对每个尺寸 `s`，固定选前 `s` 个产品构成 `xhat[k,:,s]`。

2. **优化变量与目标**
   - 保留 `p,d,y,q,w,alpha,beta`，但 `x` 由 `xhat * y` 替代。
   - 目标仍是平均利润最大化。

3. **线性化与安全参数**
   - 与 MILP 一样使用有界 `p_ub/d_ub` 与安全 `big_M`。

### 3.3 结论
- **不是“论文逐行可还原代码”**（论文未给出完整实现细节）。
- 是**遵循论文近似思想并可运行的一版工程实现**。
- 本文档已把“补全项”明确列出，便于后续替换成你认可的 A-算法细节版本。

---

## 4. 统一日志字段（当前）

由 `run_cpbsd_baselines.py` 输出 `unified_log.json/csv`，关键字段：

- 实验索引：`instance_id, seed, n, k, method`
- 场景标签：`dist_family, rho, heterogeneity, cost_scenario`
- 时间：`time`(wall-clock), `solver_runtime`, `time_limit`
- 收益：`revenue, revenue_in_sample, revenue_out_sample`
- 搜索：`nodes`
- 质量：`status_code, status_text, mip_gap, best_bound, sol_count`
- 线性化：`big_m`
- 追溯：`result_path`
- 范围声明：`experiment_scope`（当前 `smoke_subset`）

---

## 5. 你最关心的“严格性”一句话总结

- **CPBSD-MILP**：约束结构按论文 (9)-(23) 实现；参数化（`M/上界/时限`）为工程补全，已显式记录。
- **CPBSD-A**：论文思想一致，但实现细节（特别是排序规则）有工程补全，已显式记录。
- **实验范围**：当前是 smoke subset，不是 full grid；日志中已显式标注，避免误读为论文全量结果。
