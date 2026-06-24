# Cutoff Sensitivity 实验报告

> 注：本文件记录的是历史实验报告。文中的 `pyg311` 与 Windows 命令片段属于旧工作流回溯，不再代表当前默认运行方式。

## 一、实验背景与目标

### 1.1 研究问题

在 FCP (Fixed Choice Prediction) 和 PCP (Progressive Choice Prediction) 策略中，Cutoff=0.5 作为默认阈值用于将 GCN 输出的概率转换为二分类预测。本实验旨在：

1. **验证 Cutoff=0.5 的合理性**：通过敏感性测试评估不同阈值对策略性能的影响
2. **探索最优阈值**：识别在 Revenue Ratio、Time Ratio 和 Bundle 预测准确性之间的最佳权衡点
3. **对比 FCP 与 PCP**：比较两种策略在不同阈值下的表现差异

### 1.2 实验日期

2025-02-05

---

## 二、实验设计

### 2.1 策略概述

#### FCP (Fixed Choice Prediction)
- **流程**：GCN 推理 → Logits → Sigmoid 概率 → Threshold (cutoff) → `pred_assort` (m×n) → MILP 求解
- **Bundle 生成**：直接基于阈值：`pred_assort[k,j] = 1 if sigmoid(logit[k,j]) >= cutoff`
- **特点**：简单直接，每个 segment 独立预测产品组合

#### PCP (Progressive Choice Prediction)
- **流程**：GCN 推理 → Logits → Sigmoid 概率 → Top-M 选择 (threshold=cutoff) → Progressive Bundles → MILP 求解
- **Bundle 生成**：
  1. `top_m_selection(sigmoid_output, m=n, threshold=cutoff)` 选择每个 segment 的 top M 产品（M=n，但只保留 prob >= cutoff）
  2. `generate_progressive_bundles` 生成链式 bundle：{p1}, {p1,p2}, ..., {p1,p2,...,pM}
- **特点**：利用 progressive bundle 结构，减少 MILP 约束数量

### 2.2 Cutoff 取值

测试 9 个阈值：**0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9**

对于 EdgeScoringGCN 的 logits：
- `sigmoid(logit) >= cutoff` 等价于 `logit >= log(cutoff/(1-cutoff))`
- 例如：cutoff=0.5 → logit >= 0；cutoff=0.1 → logit >= -2.197

### 2.3 测试数据集

| 数据集 | 样本数 (FCP) | 样本数 (PCP) | 说明 |
|--------|--------------|--------------|------|
| `test_m10n10_1e_3` | 30 | 10 | m=10 segments, n=10 products |
| `test_m20n10_1e_3` | 30 | 10 | m=20 segments, n=10 products |
| `test_m30n10_1e_3` | 30 | 10 | m=30 segments, n=10 products |
| **总计** | **90** | **30** | 固定随机种子 `np.random.seed(42)` 保证可复现 |

数据来源：`dataset2_4_2026` 目录

---

## 三、实验配置

### 3.1 模型与数据路径

- **模型**：`models_multi_layer_edge_update/model_edge_4layer_seed1.pt` (4-layer EdgeScoringGCN)
- **数据集**：`dataset2_4_2026/test_m10n10_1e_3`, `test_m20n10_1e_3`, `test_m30n10_1e_3`
- **环境**：Conda `pyg311` (Python 3.11), Windows 编码 `chcp 65001`

### 3.2 评估指标

#### 3.2.1 Revenue & Time Metrics
- **Revenue Ratio**：`MILP_obj / opt_rev`（预测策略的 revenue 与最优解的比值）
- **Time Ratio**：`(GCN_time + MILP_time) / running_time`（策略总时间与 baseline 求解时间的比值）

#### 3.2.2 Bundle 预测指标（基于 Optimal Bundle）

将每个 (segment, product) 对视为二分类预测：

| 指标 | 公式 | 含义 |
|------|------|------|
| **Accuracy** | (TP + TN) / total | 整体预测准确率 |
| **Precision** | TP / (TP + FP) | 预测为正例中实际为正例的比例 |
| **Recall** | TP / (TP + FN) | 实际正例中被正确预测的比例 |
| **TPR** | Recall | True Positive Rate（与 Recall 相同） |
| **TNR** | TN / (TN + FP) | True Negative Rate |
| **FPR** | FP / (FP + TN) | False Positive Rate（误选率） |
| **FNR** | FN / (FN + TP) | False Negative Rate（漏选率） |
| **Error Rate** | (FP + FN) / total | 错误预测比例 |

其中：
- **TP**：pred=1, opt=1（正确预测包含）
- **FN**：pred=0, opt=1（漏选）
- **FP**：pred=1, opt=0（误选）
- **TN**：pred=0, opt=0（正确预测不包含）

---

## 四、实验流程

### 4.1 FCP 实验流程

```mermaid
flowchart LR
    A[Load 90 samples] --> B[GCN Inference]
    B --> C[Logits n×m]
    C --> D[For each cutoff]
    D --> E["Threshold: sigmoid(logit) >= cutoff"]
    E --> F[pred_assort m×n]
    F --> G[MILP Solve]
    G --> H[Revenue Ratio + Metrics]
    H --> I[Next cutoff]
    I --> D
```

**脚本**：`sensitivity_cutoff_FCP.py`

**关键代码**：
```python
# Threshold on logits
thresh = logit_threshold(cutoff)  # log(c/(1-c))
pred_assort = (logits_nm.T >= thresh).astype(int)  # (m, n)

# MILP solve
rev_ratio, milp_time = revenue_ratio(n, m, ..., pred_assort)
```

### 4.2 PCP 实验流程

```mermaid
flowchart LR
    A[Load 30 samples] --> B[GCN Inference]
    B --> C[Logits n×m]
    C --> D[Sigmoid: prob = sigmoid(logit)]
    D --> E[For each cutoff]
    E --> F["top_m_selection(prob, m=n, threshold=cutoff)"]
    F --> G[selected_products per segment]
    G --> H[generate_progressive_bundles]
    H --> I[feasible_bundles set]
    I --> J[MILP Solve]
    J --> K[Revenue Ratio + Metrics]
    K --> L[Next cutoff]
    L --> E
```

**脚本**：`sensitivity_cutoff_PCP.py`

**关键代码**：
```python
# Top-M selection with threshold
sigmoid_output = 1.0 / (1.0 + np.exp(-logits_nm))
selected_products = top_m_selection(sigmoid_output, m=n, threshold=cutoff)

# Generate progressive bundles
feasible_bundles = generate_progressive_bundles(selected_products, n)

# MILP solve
rev_ratio, milp_time = revenue_ratio(n, m, ..., feasible_bundles, selected_products, ...)
```

### 4.3 合并对比分析

**脚本**：`compare_FCP_PCP_cutoff.py`

- 读取 FCP 和 PCP 的 CSV 结果
- 按 cutoff 和 strategy 聚合计算平均值和标准差
- 生成对比图表（Revenue, Time, Metrics, Pareto）
- 输出合并 CSV 和汇总统计表

---

## 五、实验结果

### 5.1 FCP 策略结果摘要

| Cutoff | Revenue Ratio | Time Ratio | Error Rate | FNR |
|--------|---------------|------------|------------|-----|
| 0.1 | 0.8504±0.044 | 0.0095 | 0.278 | 0.002 |
| 0.2 | 0.8885±0.035 | 0.0093 | 0.237 | 0.006 |
| 0.3 | 0.9077±0.032 | 0.0095 | 0.210 | 0.011 |
| 0.4 | 0.9257±0.031 | 0.0091 | 0.184 | 0.016 |
| **0.5** | **0.9372±0.029** | **0.0089** | **0.166** | **0.023** |
| 0.6 | 0.9479±0.025 | 0.0087 | 0.146 | 0.034 |
| 0.7 | 0.9554±0.024 | 0.0085 | 0.130 | 0.050 |
| **0.8** | **0.9634±0.019** | **0.0081** | **0.121** | **0.079** |
| 0.9 | 0.9598±0.024 | 0.0082 | 0.124 | 0.141 |

**主要发现**：
- Revenue Ratio 在 Cutoff=0.8 时达到最高（0.9634）
- Cutoff=0.5 在 Revenue 和 FNR 之间取得较好平衡
- Time Ratio 非常低（~0.009），说明 FCP 相比 baseline 快约 100 倍

### 5.2 PCP 策略结果摘要

| Cutoff | Revenue Ratio | Time Ratio | Error Rate | FNR |
|--------|---------------|------------|------------|-----|
| 0.1 | 0.9924±0.003 | 0.5340 | - | - |
| 0.2 | 0.9925±0.003 | 0.4100 | - | - |
| 0.3 | 0.9923±0.004 | 0.3475 | - | - |
| 0.4 | 0.9921±0.004 | 0.3003 | - | - |
| **0.5** | **0.9915±0.005** | **0.2538** | - | - |
| 0.6 | 0.9907±0.005 | 0.1985 | - | - |
| 0.7 | 0.9894±0.005 | 0.1294 | - | - |
| 0.8 | 0.9866±0.007 | 0.0969 | - | - |
| 0.9 | 0.9763±0.010 | 0.0700 | - | - |

**主要发现**：
- PCP 的 Revenue Ratio 显著高于 FCP（~0.99 vs ~0.94-0.96）
- Time Ratio 较高（0.07-0.53），但仍远低于 baseline（<1.0）
- Revenue Ratio 随 cutoff 升高略有下降，但整体稳定在 0.98-0.99

### 5.3 FCP vs PCP 对比

| Cutoff | FCP Revenue | PCP Revenue | Diff (PCP-FCP) | FCP Time | PCP Time | Diff (PCP-FCP) |
|--------|------------|-------------|----------------|----------|----------|----------------|
| 0.1 | 0.8504 | 0.9924 | +0.1420 | 0.0095 | 0.5340 | +0.5245 |
| 0.2 | 0.8885 | 0.9925 | +0.1040 | 0.0093 | 0.4100 | +0.4006 |
| 0.3 | 0.9077 | 0.9923 | +0.0846 | 0.0095 | 0.3475 | +0.3380 |
| 0.4 | 0.9257 | 0.9921 | +0.0664 | 0.0091 | 0.3003 | +0.2912 |
| **0.5** | **0.9372** | **0.9915** | **+0.0542** | **0.0089** | **0.2538** | **+0.2449** |
| 0.6 | 0.9479 | 0.9907 | +0.0428 | 0.0087 | 0.1985 | +0.1899 |
| 0.7 | 0.9554 | 0.9894 | +0.0340 | 0.0085 | 0.1294 | +0.1209 |
| 0.8 | 0.9634 | 0.9866 | +0.0231 | 0.0081 | 0.0969 | +0.0888 |
| 0.9 | 0.9598 | 0.9763 | +0.0165 | 0.0082 | 0.0700 | +0.0618 |

**关键观察**：
1. **Revenue 优势**：PCP 在所有 cutoff 下均优于 FCP（+0.016 到 +0.142）
2. **Time 成本**：PCP 的 Time Ratio 显著高于 FCP（约 8-60 倍），但仍远低于 baseline
3. **Cutoff 影响**：
   - FCP：Revenue 随 cutoff 升高而提升（0.85 → 0.96），在 0.8 达到峰值
   - PCP：Revenue 相对稳定（~0.99），随 cutoff 升高略有下降
4. **合并平均值**：FCP+PCP 平均 Revenue Ratio 在 0.92-0.98 之间，介于两者之间

---

## 六、生成文件清单

### 6.1 FCP 实验输出

| 文件 | 说明 |
|------|------|
| `cutoff_sensitivity_results.csv` | FCP 逐样本结果（810 行：90 样本 × 9 cutoff） |
| `cutoff_sensitivity_revenue.png` | Revenue Ratio vs Cutoff（含误差带） |
| `cutoff_sensitivity_revenue_by_dataset.png` | 按数据集分组的 Revenue Ratio |
| `cutoff_sensitivity_metrics.png` | Error Rate 和 FNR vs Cutoff |
| `cutoff_sensitivity_pareto.png` | Revenue vs Time Pareto 图 |

### 6.2 PCP 实验输出

| 文件 | 说明 |
|------|------|
| `cutoff_sensitivity_PCP_results.csv` | PCP 逐样本结果（270 行：30 样本 × 9 cutoff） |
| `cutoff_sensitivity_PCP_revenue.png` | Revenue Ratio vs Cutoff |
| `cutoff_sensitivity_PCP_revenue_by_dataset.png` | 按数据集分组的 Revenue Ratio |
| `cutoff_sensitivity_PCP_metrics.png` | Bundle 预测指标对比 |
| `cutoff_sensitivity_PCP_pareto.png` | Revenue vs Time Pareto 图 |

### 6.3 对比分析输出

| 文件 | 说明 |
|------|------|
| `cutoff_sensitivity_FCP_PCP_combined.csv` | 合并数据（1080 行：810 FCP + 270 PCP） |
| `cutoff_comparison_FCP_PCP_revenue.png` | FCP vs PCP Revenue 对比（含合并平均值） |
| `cutoff_comparison_FCP_PCP_time.png` | FCP vs PCP Time Ratio 对比 |
| `cutoff_comparison_FCP_PCP_metrics.png` | Bundle 预测指标对比（Accuracy, Precision, Recall, FNR） |
| `cutoff_comparison_FCP_PCP_pareto.png` | FCP 和 PCP 的 Pareto 对比图 |
| **`cutoff_comparison_FCP_PCP_combined.png`** | **综合对比图（3×2 布局）：(a) Revenue, (b) Time, (c-d) Metrics 2×2** |

---

## 七、实验脚本

### 7.1 主要脚本

1. **`sensitivity_cutoff_FCP.py`**
   - FCP 策略的 Cutoff 敏感性测试
   - 90 个样本（每数据集 30 个）
   - 输出：CSV + 4 张图表

2. **`sensitivity_cutoff_PCP.py`**
   - PCP 策略的 Cutoff 敏感性测试
   - 30 个样本（每数据集 10 个）
   - 输出：CSV + 4 张图表

3. **`compare_FCP_PCP_cutoff.py`**
   - FCP 和 PCP 结果合并与对比
   - 生成对比图表和汇总统计

### 7.2 运行顺序

```bash
# 1. 激活环境
chcp 65001
conda activate pyg311

# 2. 运行 FCP 实验（约 8 分钟）
python sensitivity_cutoff_FCP.py

# 3. 运行 PCP 实验（约 3 分钟）
python sensitivity_cutoff_PCP.py

# 4. 生成对比分析（秒级）
python compare_FCP_PCP_cutoff.py
```

---

## 八、可复现性

### 8.1 随机种子

- **FCP**：`np.random.seed(42)`（样本抽样）
- **PCP**：`np.random.seed(42)`（样本抽样）
- **Torch**：`torch.manual_seed(42)`（如使用）

### 8.2 固定配置

- **模型**：`model_edge_4layer_seed1.pt`（4-layer EdgeScoringGCN）
- **数据集路径**：`dataset2_4_2026/test_m10n10_1e_3`, `test_m20n10_1e_3`, `test_m30n10_1e_3`
- **Cutoff 列表**：`[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]`
- **MILP 参数**：MIPGap=1e-2, TimeLimit=600s

### 8.3 样本选择

- **FCP**：每个数据集固定选择 30 个样本（使用 `np.random.default_rng(42).choice()`）
- **PCP**：每个数据集固定选择 10 个样本（使用 `np.random.default_rng(42).choice()`）

---

## 九、主要结论

### 9.1 Cutoff=0.5 的合理性

1. **FCP**：
   - Cutoff=0.5 时 Revenue Ratio = 0.9372，接近最优（0.8 时为 0.9634）
   - 在 Revenue 和 FNR 之间取得良好平衡（FNR=0.023，相对较低）
   - **结论**：Cutoff=0.5 是合理的默认选择，但 Cutoff=0.8 可获得更高 Revenue

2. **PCP**：
   - Cutoff=0.5 时 Revenue Ratio = 0.9915，接近最高值（0.1-0.4 时 ~0.992）
   - Revenue 对 cutoff 变化不敏感（0.98-0.99 之间）
   - **结论**：Cutoff=0.5 是合理选择，且对阈值变化鲁棒

### 9.2 FCP vs PCP 权衡

- **Revenue**：PCP 显著优于 FCP（+0.016 到 +0.142）
- **Time**：FCP 显著快于 PCP（Time Ratio 约 8-60 倍差异）
- **Trade-off**：PCP 以更高的计算成本换取更高的 Revenue

### 9.3 推荐

- **追求 Revenue**：选择 PCP + Cutoff=0.1-0.4（Revenue ~0.992）
- **追求速度**：选择 FCP + Cutoff=0.5-0.8（Time Ratio ~0.009，Revenue ~0.94-0.96）
- **平衡选择**：FCP + Cutoff=0.5（Revenue=0.937，Time Ratio=0.009）

---

## 十、后续工作建议

1. **扩展数据集**：在更多 m×n 组合上测试（如 m40n10, m10n20）
2. **细化分析**：按数据集大小（m）分组分析 cutoff 敏感性
3. **时间分解**：分析 GCN 推理时间 vs MILP 求解时间在不同 cutoff 下的变化
4. **Bundle 数量分析**：统计不同 cutoff 下预测的 bundle 数量分布

---

## 附录：相关文件

- `test_FCP.py` - FCP 主策略脚本
- `test_PCP.py` - PCP 主策略脚本
- `sensitivity_cutoff_FCP.py` - FCP Cutoff 敏感性实验
- `sensitivity_cutoff_PCP.py` - PCP Cutoff 敏感性实验
- `compare_FCP_PCP_cutoff.py` - FCP vs PCP 对比分析
- `FCP_策略日志.md` - FCP 策略修改日志
- `PCP_策略日志.md` - PCP 策略修改日志
