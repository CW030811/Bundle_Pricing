# Core Code Roadmap for Next Experiments (CPBSD + GCN)

目标：基于你现有 paper 与 `CPBSD_GCN_acceleration_study`，明确“接下来必须复用/改造/新建”的核心代码。

---

## A. 现有可直接复用的核心代码

## 1) MB 求解（Mixed Bundling）
- `code_submission_project/code_submission/src/data/generate_data_MB.py`
  - 关键函数：`solve_bundle_MILP(...)`
  - 用途：作为 MB 基线求解器与数据生成参考

## 2) BSP 求解（Bundle Size Pricing）
- `code_submission_project/code_submission/src/data/generate_data_BSP.py`
  - 关键函数：`solve_bundle_size_pricing_MILP(...)`
  - 用途：作为 size-pricing 参考基线
- `code_submission_project/code_submission/src/test/test_BSP.py`
  - 用途：BSP测试与评估入口

## 3) GCN 训练
- `code_submission_project/code_submission/src/train/Training_edge-final.py`
  - 模型：`EdgeScoringGCN`
  - 当前训练范式：edge-scoring + BCEWithLogits
  - 用途：方向2先“最小改动复用”训练管线

## 4) FCP / PCP 策略代码
- `code_submission_project/code_submission/src/test/test_FCP.py`
- `code_submission_project/code_submission/src/test/test_PCP.py`
  - 用途：作为“GCN预测 + 优化求解”范式现成模板

## 5) Local Search（可选增强）
- `code_submission_project/code_submission/src/test/test_FCP_LS.py`
- `code_submission_project/code_submission/src/test/LS_Path_Test.py`
  - 用途：后续若做二阶段 refinement，可作为候选

---

## B. 为 CPBSD_GCN_acceleration_study 必须新增/改造的代码

## 1) 新建：CPBSD 数据生成器（核心）
建议新建：
- `CPBSD_GCN_acceleration_study/code/src/data/generate_data_CPBSD.py`

职责：
- 按 CPBSD 论文设置生成样本（N/K/F/相关结构/成本场景）
- 输出统一数据格式（建议 msgpack）
- 提供 in-sample / out-of-sample 切分

## 2) 新建：CPBSD-MILP 求解器（核心）
建议新建：
- `CPBSD_GCN_acceleration_study/code/src/solver/solve_CPBSD_MILP.py`

职责：
- 实现 CPBSD 机制变量 `(p,d)`
- 实现 BCS-Dual 融合后的单层 MILP（你已在文档整理好）
- 支持 n=5 oracle 模式

## 3) 新建：CPBSD-A 近似求解接口
建议新建：
- `CPBSD_GCN_acceleration_study/code/src/solver/solve_CPBSD_A.py`

职责：
- 实现/复现 CPBSD-A 近似策略
- 支持 n=10,30 大规模基线

## 4) 改造：GCN训练脚本（尽量最小改动）
建议从现有脚本复制并改名：
- from `Training_edge-final.py`
- to `CPBSD_GCN_acceleration_study/code/src/train/train_gcn_cpbsd.py`

最小改动点：
- 数据读取路径切到 CPBSD 数据
- label 改为 CPBSD 场景下的“候选产品重要性/入选标签”
- 保持模型主体与训练流程不变（符合你“最好不用大改”）

## 5) 新建：Prune + Reduced CPBSD-MILP 桥接器（方向2主角）
建议新建：
- `CPBSD_GCN_acceleration_study/code/src/pipeline/run_cpbsd_gcn_prune.py`

职责：
- 读取 GCN 打分
- 执行 Top-M 裁剪（当前不含安全补集）
- 调用 Reduced CPBSD-MILP
- 输出 revenue/time/nodes

## 6) 新建：统一评估脚本
建议新建：
- `CPBSD_GCN_acceleration_study/code/src/eval/eval_all_methods.py`

职责：
- 统一对比组：CPBSD-MILP(n=5), CPBSD-A(n=10,30), CPBSD-MILP+GCN-Prune
- 统一导出结果到 `results/csv`
- 可直接接 `results/figures` 报表脚本

---

## C. 接下来“最小可跑”执行顺序（强建议）

1. 先完成 `generate_data_CPBSD.py`
2. 再完成 `solve_CPBSD_MILP.py`（先 n=5 跑通）
3. 复制改造 `train_gcn_cpbsd.py`
4. 实现 `run_cpbsd_gcn_prune.py`（Top-M）
5. 跑第一版对比：
   - n=5: CPBSD-MILP vs CPBSD-MILP+GCN-Prune
6. 扩展到 n=10,30：
   - CPBSD-A vs CPBSD-MILP+GCN-Prune

---

## D. 结论（你现在真正要抓的核心代码）

最关键的“6件套”是：
1. `generate_data_CPBSD.py`
2. `solve_CPBSD_MILP.py`
3. `solve_CPBSD_A.py`
4. `train_gcn_cpbsd.py`（基于 `Training_edge-final.py`）
5. `run_cpbsd_gcn_prune.py`
6. `eval_all_methods.py`

现有 `MB/BSP/GCN/FCP/PCP` 代码不是废弃，而是：
- 作为参考实现、模板与基线工具链。
