# CPBSD‑GCN‑Acceleration 实验进展总览（截至目前）

更新：2026-03-05

> 注：本文件记录的是较早一轮 CPBSD baseline 复现实验状态，涉及的 `run_cpbsd_baselines.py` 与 `experiments/cpbsd_baselines/` 现已不作为当前工作区默认主线；当前活跃 smoke 入口是 `run_cpbsd_baselines_v2.py`，而旧结果已移出工作区备份。

---

## ✅ 已实现内容（代码 + 位置）

### 1) 数据生成
- **脚本**：`src/data/generate_data_CPBSD.py`
- **功能**：按论文口径生成实例（分布/相关/异质/成本）

### 2) CPBSD‑MILP
- **脚本**：`src/data/solve_cpbsd_milp.py`
- **功能**：严格按论文(9)-(23)求解
- **改动**：加入安全 `p_ub/d_ub` 与可配置 `big_M`，记录到日志

### 3) CPBSD‑A（近似）
- **脚本**：`src/data/solve_cpbsd_a.py`
- **功能**：基于 `v-c` 排序的预设偏好（工程补全）

### 4) MB / BSP 在 CPBSD instance 上求解
- **脚本**：`src/data/solve_mb_bsp_on_cpbsd.py`
- **功能**：MB/BSP baseline 计算 + out‑of‑sample eval

### 5) 一键跑实验 + 统一日志
- **脚本**：`src/data/run_cpbsd_baselines.py`
- **功能**：
  - n=5: MILP + BSP + MB
  - n=10: CPBSD‑A + BSP
  - 统一生成 `unified_log.csv/json`

### 6) BCS 紧性诊断
- **脚本**：`src/data/diagnose_bcs_tightness.py`
- **功能**：输出每个 sample 的 MILP/BCS 选择、surplus、revenue、q/beta 矩阵
- **历史结果文件**：`domains/revenue-management/experiments/cpbsd_baselines/diagnostics/bcs_tightness_N5K10_seed901.txt`

### 7) 说明文档
- `CPBSD_REPRO_IMPLEMENTATION_NOTES.md`
  → smoke subset / full grid / CPBSD‑A 工程补全说明
- `CPBSD_MILP_DIAG_NOTES.md`
  → Q1/Q2/Q3 诊断过程与结论

---

## ✅ 已发现问题 & 排查结论

### 问题1：MILP ObjVal < BSP（此前出现）
- **原因**：对比口径不一致（用后验 revenue）
- **修复**：统一用 **ObjVal** 作为 in‑sample，后验仅作诊断
- **结果**：MILP ObjVal ≥ BSP 成立

### 问题2：ObjVal ≠ 后验 revenue
- **原因**：BCS tie（多解）导致选择不同
- **诊断**：
  - 用 surplus 一致性检查：N=5 K=10 / K=30 → mismatch=0
- **结论**：BCS 约束紧；差异来自 tie

### 问题3：N=30 CPBSD‑A revenue 异常≈0
- **原因**：time‑limit 下退化为“全不买”
- **修复尝试**：warm‑start（p=c+ε）→ rev_in≈0.03
- **结论**：改善有限，仍存疑

### 问题4：big‑M 设定不安全
- **原因**：初始用 max(v)+1 有削可行性风险
- **修复**：加入 p/d 上界 + big‑M 设安全上界
- **结论**：已修复，但 big‑M 仍需敏感性评估

---

## ⚠️ 仍存疑设定（需后续排查）

1) **CPBSD‑A 近似设定是否合理**
   - 当前实现基于 `v-c` 排序（工程补全）
   - 论文未给完整算法细节

2) **MILP ObjVal 与后验 revenue 差距**
   - tie 情况解释目前成立
   - 需更多实例验证 surplus 一致性

3) **N=30 下 CPBSD‑A 表现异常**
   - warm‑start 仅小幅改善
   - 可能与近似策略 / 时限有关

4) **big‑M 设定**
   - 已改成安全上界
   - 是否过保守影响性能仍需评估

---

## 📦 当前结果文件

历史路径：`domains/revenue-management/experiments/cpbsd_baselines/`

包含：
- `instances/`
- `results/`
- `unified_log.csv/json`
- `diagnostics/bcs_tightness_N5K10_seed901.txt`
