# CPBSD 研究进展与实验复现汇报（面向导师）

> 范围：CPBSD 论文机制梳理 + 复现进展 + GCN 加速方向设想
> 
> 备注：本报告面向科研汇报，强调“机制逻辑—实验设置—当前复现状态—后续方向”。
>
> 状态说明：本文件保留了阶段性汇报口径。若与当前工作区实际目录不一致，以 `code_submission/.venv`、`run_cpbsd_baselines_v2.py` 与 `domains/revenue-management/experiments/` 下现存目录为准。

---

## 1. 深度挖掘 CPBSD Paper

### 1.1 Formulation（CPBSD‑MILP & CPBSD‑A）
- **CPBSD‑MILP（精确模型）**
  - 采用 component price + size discount 的结构化价格机制：
    \(\text{Pay}(S)=\sum_{n\in S}p_n-|S|d_{|S|}\)
  - 通过 BCS → LP Relax → Dual，将顾客自选择约束编译进单层 MILP（论文 (9)–(23)）。
  - 目标采用 SAA：\(\max \frac{1}{K}\sum_{k=1}^K \text{Profit}_k\)。

- **CPBSD‑A（近似算法）**
  - 工程实现采用按 \(v_n^k-c_n\) 排序的 preference ranking，并在此基础上构造 \((p,d)\)。
  - 用于避免 MILP 随 \(N,K\) 增大带来的不可解问题。

- **当前仍需明确的疑问**
  1) **CPBSD‑MILP 的 Big‑M 设置是否最紧**（当前已加安全上界，但是否过保守需评估）
  2) **CPBSD‑A 的具体建模细节**（论文未给完整算法细节，工程版本仍需验证合理性）

---

### 1.2 CPBSD 相对 BSP / MB 的优势
- **相对 BSP**：
  - BSP 只有一个 size‑based price；CPBSD 同时有 \(p_n\) 与 \(d_s\)，能为每个产品赋予不同的价值/成本权重。
  - 机制表达力更高，允许“同 size 不同组合”的收益差异。

- **相对 MB**：
  - MB 为每个 bundle 单独定价，决策空间 \(2^N\)；
  - CPBSD 用 \((p,d)\) 结构化压缩价格空间 → tractable。

---

### 1.3 论文主实验设置（Section 6）
- **规模**：\(N\in\{5,10,30\}\)
- **样本量**：\(K=50\)（N=5），\(K=100\)（N≥10）
- **分布与结构**：
  - 5 边际分布：exponential / logit / lognormal / normal / uniform
  - 相关结构：\(\rho\in\{-0.5,0,0.5\}\)（Gaussian copula）
  - 3 级异质性：none / partial / full
  - 3 成本场景：zero / HVHM / HVLM
- **实例规模**：405 setups × 5 实例 = 2,025 实例（每个 N 下 675）
- **评估**：对每实例再抽取 5,000 个估值样本做 out‑of‑sample

---

### 1.4 GCN 加速 CPBSD 的两条路径
- **方向 1（不合理）**：直接用 GCN 预测每个 bundle 价格
  - 违背 CPBSD 机制结构（\(p_n,d_s\)）
  - 预测维度爆炸，退化为 MB

- **方向 2（可行设想）**：用 GCN 加速 **BCS / 结构选择 / 或 warm‑start**
  - 用 GCN 预测顾客偏好排序或关键产品集
  - 作为 CPBSD‑A 的结构性先验 / warm‑start
  - 保留 CPBSD 机制结构，降低求解规模

---

## 2. 复现进展（N=5 实验）

### 2.1 已完成（Smoke Subset）
- 完成 CPBSD‑MILP / MB / BSP / CPBSD‑A 的 smoke subset 复现。
- 已生成统一日志与箱线图（BSP ratio 口径）。

### 2.2 正在进行（全网格 N=5）
- 已启动全网格 N=5 主实验（405 setups × 5 实例）。
- 当前进程持续运行中（含 MILP/MB/BSP 的完整求解）。

---

## 3. 后续方向（聚焦 GCN 加速）

### 3.1 短期（复现收敛）
- 完成 N=5 全网格主实验
- 输出 Figure 6 口径的 in/out ratio 箱线图
- 对比论文结论（均值、分位数趋势）

### 3.2 中期（机制 + 加速）
- 明确 CPBSD‑A 的算法细节与合理性
- Big‑M 设定敏感性分析（收敛质量 vs. 速度）

### 3.3 长期（GCN）
- 建立 GCN 预测的“结构性先验”
  - 产品排序 / bundle size / 高价值子集
- 将 GCN 输出作为 CPBSD‑A / MILP 的 warm‑start
- 在主实验设置下验证性能与加速比

---

## 4. 产出与路径（供汇报附录）

- 代码入口与实验脚本：
  - `domains/revenue-management/project-root/code_submission_project/code_submission/src/data/run_cpbsd_baselines.py`
  - `domains/revenue-management/project-root/code_submission_project/code_submission/src/data/run_cpbsd_main_n5.py`

- 结果目录：
  - `domains/revenue-management/experiments/cpbsd_baselines/`（历史目录，现已移出工作区备份）
  - `domains/revenue-management/experiments/cpbsd_main_n5/`（正在生成）

---
