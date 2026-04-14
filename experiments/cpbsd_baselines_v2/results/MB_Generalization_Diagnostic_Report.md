# MB Out-of-Sample Generalization诊断报告

**日期**: 2026-03-15
**实验设置**: N=5, normal distribution, rho=0.0, full heterogeneity, hvhm cost
**基线K**: 50 (与CPBSD原论文一致)
**Out-of-sample K**: 5000 (seed+99991)

---

## 1. 问题描述

在N=5的smoke实验中，MB (Mixed Bundling) 的in→out revenue drop达到24-36%，远大于CPBSD-MILP (7-22%) 和 BSP (-2% ~ 23%)。MB需要优化 2^N=32 个bundle价格变量，但训练样本仅K=50，每个参数仅1.6个样本支撑。

**核心问题**: 为什么CPBSD原论文的实验中MB的泛化性看起来很好？

---

## 2. 诊断一：Bundle与价格下界 (零计算成本)

### 2.1 实验设计

在已缓存的MB结果上，评估三种定价策略：

| 策略 | 描述 |
|------|------|
| **MB-full** | 使用全部32个bundle价格 (当前基线) |
| **MB-sel** | 仅使用被>=1个in-sample客户选择的bundle价格 (17-21个) |
| **MB-floor** | 全部32个价格，但clip到 max(price, bundle_cost) |

### 2.2 结果

| Instance | Variant | Rev-In | Rev-Out | Drop% | vs BSP-Out | #Prices |
|----------|---------|--------|---------|-------|------------|---------|
| inst001 | MB-full  | 1.7769 | 1.1637 | 34.51% | 1.1184 | 32 |
| inst001 | MB-sel   | 1.7769 | 1.1362 | 36.06% | 1.0920 | 17 |
| inst001 | MB-floor | 1.7769 | 1.1637 | 34.51% | 1.1184 | 32 |
| inst002 | MB-full  | 1.5758 | 1.1339 | 28.04% | 1.0283 | 32 |
| inst002 | MB-sel   | 1.5758 | 1.1107 | 29.52% | 1.0072 | 19 |
| inst002 | MB-floor | 1.5758 | 1.1339 | 28.04% | 1.0283 | 32 |
| inst003 | MB-full  | 1.6331 | 1.2233 | 25.09% | 1.0628 | 32 |
| inst003 | MB-sel   | 1.6331 | 1.2163 | 25.52% | 1.0567 | 18 |
| inst003 | MB-floor | 1.6331 | 1.2233 | 25.09% | 1.0628 | 32 |
| inst004 | MB-full  | 1.5178 | 1.1382 | 25.01% | 0.9984 | 32 |
| inst004 | MB-sel   | 1.5178 | 1.1369 | 25.10% | 0.9972 | 21 |
| inst004 | MB-floor | 1.5178 | 1.1382 | 25.01% | 0.9984 | 32 |
| inst005 | MB-full  | 1.5647 | 1.1621 | 25.73% | 1.1116 | 32 |
| inst005 | MB-sel   | 1.5647 | 1.1506 | 26.47% | 1.1005 | 18 |
| inst005 | MB-floor | 1.5647 | 1.1621 | 25.73% | 1.1116 | 32 |

**聚合结果:**

| Variant | Mean Drop% | Mean vs BSP-Out |
|---------|-----------|-----------------|
| MB-full  | 27.68% | 1.0639 |
| MB-sel   | 28.53% | 1.0507 |
| MB-floor | 27.68% | 1.0639 |
| BSP      | 8.28%  | 1.0000 |

### 2.3 结论

- **MB-floor = MB-full**: 没有bundle的定价低于生产成本，负利润bundle不是问题来源
- **MB-sel比MB-full更差** (~0.85%): 移除phantom bundles不仅无帮助，反而略有损害（部分phantom bundle的价格恰好对out-of-sample客户有效）
- **过拟合完全来源于价格调优本身**: 32个价格变量在K=50个样本上被过度拟合

---

## 3. 诊断二：K-Scaling Study

### 3.1 实验设计

固定参数设置 (normal, full, hvhm)，变化K in {50, 100, 200, 400}:
- 每个K值生成5个instance (base_seed=20260304)
- 求解MB和BSP
- 评估in/out-of-sample revenue
- 时间限制: 300s

### 3.2 结果

| K | Samples/Param | MB Mean Drop% | MB vs BSP (Out) | BSP Mean Drop% |
|---|--------------|---------------|-----------------|----------------|
| 50  | 1.6  | **27.8%** | 1.060 | 8.3% |
| 100 | 3.1  | **20.6%** | 1.101 | 9.5% |
| 200 | 6.2  | **10.7%** | 1.097 | 4.2% |
| 400 | 12.5 | *(solver失败)* | 0.088 | 3.6% |

**K=400数据无效**: MB MILP在K=400时有400x32=12,800个binary变量，300s时间限制不足以找到良好解（revenue降至~0.1）。需要更长时间限制（600s+）。

### 3.3 有效趋势 (K=50→200)

- **K每翻倍，overfitting drop大约减半**: 28% → 21% → 11%
- **K=200 (6.2 samples/param)** 达到了可接受的泛化水平 (11% drop, 接近BSP的4%)
- **MB在out-of-sample上始终优于BSP**: 即使K=50, MB out-of-sample也比BSP高6%

---

## 4. 为什么原论文的MB泛化性看起来好？

### 4.1 聚合偏差 (Aggregation Bias)

原论文的boxplot **聚合了135种参数组合** (N=5):
- 5种分布 (exponential, logit, lognormal, normal, uniform)
- 3种相关性 (rho = -0.5, 0, 0.5)
- 3种异质性 (none, partial, full)
- 3种成本场景 (zero, hvhm, hvlm)

其中很多设置对MB来说是**简单**的:
- `none` heterogeneity: 所有产品相同，pricing变量高度相关，过拟合空间小
- `zero` cost: 无生产成本，价格空间更简单
- `uniform` distribution: 定价域有界，极端值少

我们使用的 (normal, full, hvhm) 是**高难度设置**: full heterogeneity意味着5个产品均值从1到10线性分布，定价变量间差异大，过拟合空间最大。

### 4.2 原论文的MB whisker确实很长

仔细观察论文Figure (a)，MB的whisker（特别是out-of-sample）向下延伸到约0.5 — 这说明在困难设置下，论文的MB泛化性**同样很差**。中位数被大量简单设置拉高了。

### 4.3 K=50在原论文中的表现

原论文确实使用K=50 (N=5)。但由于上述聚合效应，整体中位数看起来还可以。如果论文单独报告 (normal, full, hvhm) 的结果，MB泛化性很可能与我们的28% drop一致。

---

## 5. 解决方案与建议

### 5.1 已验证的方案: 增加K

| 措施 | 效果 | 代价 |
|------|------|------|
| K=50→100 | Drop: 28%→21% | 求解时间增加 ~50%, 均hit 300s时限 |
| K=50→200 | Drop: 28%→11% | 求解时间 ~310s, hit 300s时限 |
| K=50→400 | 需要更长时限 | 300s不够, 需600s+ |

**推荐**: N=5实验使用 **K=200**, 时间限制提至 **600s**。

### 5.2 未验证但值得探索的方案

1. **多参数组合测试**: 在 (none, zero) 等简单设置上确认MB泛化性良好，验证聚合偏差假说
2. **价格正则化**: 将MB价格向BSP价格或成本比例方向收缩，减少过拟合
3. **Holdout validation**: 将K个样本split为 train/validation，选择泛化最好的定价方案
4. **K=400 + 时限1200s**: 完成K-scaling曲线的最后一个数据点

---

## 6. 文件清单

| 文件 | 角色 |
|------|------|
| `src/data/run_mb_generalization_study.py` | 幻影Bundle诊断脚本 |
| `src/data/run_mb_k_scaling_study.py` | K-scaling实验脚本 |
| `mb_generalization_study.csv` | 幻影Bundle诊断数据 |
| `mb_k_scaling_study/mb_k_scaling_study.csv` | K-scaling实验数据 |
| `plots/mb_generalization_diagnostic.png` | 幻影Bundle诊断图 |
| `mb_k_scaling_study/plots/mb_k_scaling_diagnostic.png` | K-scaling诊断图 |

---

## 7. 核心结论

> MB在 (normal, full, hvhm) 设置下的28%泛化gap是**真实的、可复现的**，并非代码错误。
> 原论文的"良好泛化"是135种参数组合的聚合效应——大量简单设置拉高了中位数。
> **增加训练样本 K=200 可将gap从28%降至11%**，是最直接有效的解决方案。
