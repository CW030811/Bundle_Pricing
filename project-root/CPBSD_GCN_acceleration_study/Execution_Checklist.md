# Execution Checklist (v2) — CPBSD + GCN Experiments

> Scope: Follow direction-2 only (GCN + Reduced CPBSD-MILP), with simplified execution constraints.

---

## 0. 目标与冻结
- [ ] 冻结主线：方向2（GCN + Reduced CPBSD-MILP）
- [ ] 冻结对比组：CPBSD-MILP（n=5）、CPBSD-A（n=10,30）、GCN-Prune
- [ ] 冻结核心指标：in/out revenue、wall-clock、B&B nodes

## 1. 数据与基线准备
- [ ] 复现 CPBSD 实例生成器（N/K/F/相关/成本/异质性）
- [ ] 生成训练/验证/测试集（按实例划分，避免泄漏）
- [ ] 跑通 CPBSD-MILP（n=5）并保存 oracle 结果
- [ ] 跑通 CPBSD-A（n=10,30）并保存 baseline 结果
- [ ] 统一日志格式（json/csv）：实例ID、seed、time、revenue、nodes

## 2. 训练前思考：GCN结构与训练是否要微调（优先不改）
- [ ] 审核现有 GCN 输入/输出是否直接适配 CPBSD 标签任务
- [ ] 制定原则：优先不改网络结构与训练流程
- [ ] 仅在必要时做最小改动（如输出头维度/损失权重）
- [ ] 记录“改动前后”差异，避免实验复杂度失控

## 3. 标签定义与特征工程
- [ ] 明确 GCN 监督目标（先做 per-k 产品打分）
- [ ] 从 oracle 解提取 label（产品是否进入关键选择）
- [ ] 构建节点特征（估值统计、成本、v-c、频次）
- [ ] 构建边特征（共选关系/相似度）
- [ ] 完成 train/val/test 的标准化与缓存

## 4. GCN 训练（第一版）
- [ ] 训练 per-k Top-M 排序模型
- [ ] 记录 Recall@M、Precision@M
- [ ] 做最小消融：无边图 / 仅节点 / 完整图
- [ ] 选定 checkpoint（Recall@M优先）

## 5. Pruning 与 Reduced CPBSD-MILP 接入
- [ ] 实现 Top-M 裁剪（不含安全补集）
- [ ] 生成候选集并统计 N→M 的压缩比例
- [ ] 在裁剪空间求解 Reduced CPBSD-MILP
- [ ] 校验可行性（机制约束不变）
- [ ] 在 n=5 跑通闭环：训练→裁剪→MILP

## 6. 主实验（按规模）
### n=5（精确对齐）
- [ ] CPBSD-MILP vs GCN-Prune-MILP
- [ ] 报告 revenue loss / speedup / nodes 变化

### n=10,30（现实规模）
- [ ] CPBSD-A vs GCN-Prune-MILP
- [ ] 报告 in/out revenue、time、nodes
- [ ] 分分布/相关结构做稳健性汇总

## 7. 超参数扫描
- [ ] 扫描 M：如 {5, 8, 12, 16, 20}
- [ ] 产出 Pareto：Time vs Revenue
- [ ] 选定默认部署参数（速度-收益平衡点）

## 8. 稳定性与复现
- [ ] 多随机种子复验（3~5 seeds）
- [ ] 汇总均值/方差
- [ ] 固化配置：seed、时限、硬件、求解器版本

## 9. 结果交付物
- [ ] 主表：各方法 in/out revenue、time、nodes
- [ ] 图1：Pareto 曲线（M）
- [ ] 图2：分布/相关结构分组表现
- [ ] 图3：n=5 相对 oracle gap 分布
- [ ] 附录：可复现实验配置清单
