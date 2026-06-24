# Smoke Subset N=5 Boxplot 异常分析

对应图表：`boxplot_ratio_vs_bsp_n5_mb_subadd_fix.png`

实验设置：N=5, K=50, dist=normal, rho=0.0, heterogeneity=full, cost=hvhm, 5 instances

---

## Q1: 为什么 MB 的 In-sample 箱线图没有上下影线？

**结论：5 个数据点中 2 个被判定为 outlier，剩余 3 个恰好落在 Q1–Q3 区间内，导致影线长度为 0。**

MB in-sample 的 5 个 ratio 值：

| Instance | Ratio vs BSP |
|---|---|
| inst003 | 1.2215 |
| inst001 | 1.3216 |
| inst005 | 1.3575 |
| inst004 | 1.3638 |
| inst002 | 1.4510 |

箱线图统计量：
- Q1 = 1.3216, Q3 = 1.3638, IQR = 0.0422
- 影线范围 = [Q1 − 1.5×IQR, Q3 + 1.5×IQR] = [1.2583, 1.4271]
- 1.2215 < 1.2583 → 低位 outlier（被 `showfliers=False` 隐藏）
- 1.4510 > 1.4271 → 高位 outlier（被 `showfliers=False` 隐藏）
- 剩余 3 个点 (1.3216, 1.3575, 1.3638) 的最小值 = Q1、最大值 = Q3，影线端点与 box 端点重合

这不是 bug，是样本量过小 (n=5) 加上数据分布集中在中部的自然结果。

---

## Q2: 为什么 MB 的 In-sample 与 Out-of-sample 数值差异如此巨大？

**结论：MB 的 2^N 个自由定价变量导致严重过拟合。**

各方法 in-sample → out-of-sample 的绝对收入下降幅度：

| Instance | MB 下降 | CPBSD-MILP 下降 | BSP 下降 |
|---|---|---|---|
| inst001 | 36.1% | 22.3% | 22.6% |
| inst002 | 29.0% | 8.1% | -1.5% |
| inst003 | 24.7% | 12.1% | 13.5% |
| inst004 | 24.6% | 7.2% | -2.4% |
| inst005 | 24.8% | 11.5% | 9.3% |

根本原因在于决策变量数量的差异：

| Method | 定价参数量 | 过拟合程度 |
|---|---|---|
| MB | 2^N = 32 个 bundle 价格 | 高 |
| CPBSD-MILP | 2N = 10 个 (5 prices + 5 discounts) | 中 |
| BSP | N = 5 个 size 价格 | 低 |

MB 为每个 bundle 单独定价，能精确适配 K=50 个训练样本的消费行为，但这些价格对新客户高度不稳定。CPBSD 的结构化约束（component price + size discount）起到了天然的正则化效果，限制了过拟合空间。

这与 CPBSD 论文 Section 6.1 (p.26) 的发现一致：

> "CPBSD and PBDC perform comparably and both outperform MB [out-of-sample], largely due to the **overfitting** of in-sample valuations under MB."

---

## Q3: 为什么 CPBSD-A 的 Out-of-sample ratio 比 In-sample 更高？

**结论：这是 ratio（CPBSD-A / BSP）的现象，非绝对值现象。BSP 的 out-of-sample 收入下降比 CPBSD-A 更快，导致比值反升。**

绝对值层面，CPBSD-A 的 out-of-sample 收入始终低于 in-sample：

| Instance | CPBSD-A in | CPBSD-A out | 下降 |
|---|---|---|---|
| inst001 | 1.5585 | 1.2575 | -19.3% |
| inst002 | 1.3508 | 1.2792 | -5.3% |
| inst003 | 1.4553 | 1.2884 | -11.5% |
| inst004 | 1.2621 | 1.2437 | -1.5% |
| inst005 | 1.3013 | 1.2529 | -3.7% |

但作为分母的 BSP 下降更多：

| Instance | BSP in | BSP out | 下降 | CPBSD-A ratio in | CPBSD-A ratio out |
|---|---|---|---|---|---|
| inst001 | 1.3445 | 1.0405 | -22.6% | 1.1592 | **1.2085** |
| inst003 | 1.3300 | 1.1510 | -13.5% | 1.0942 | **1.1193** |
| inst005 | 1.1527 | 1.0454 | -9.3% | 1.1289 | **1.1984** |

在 3/5 的实例中 out-of-sample ratio > in-sample ratio，因为 BSP 的收入衰减比例大于 CPBSD-A。本质上是 CPBSD-A 的泛化能力优于 BSP —— 在 full heterogeneity + HVHM 条件下，CPBSD 的 component pricing 能更好地适应新客户的异质偏好，而 BSP 只有 size-level 的价格粒度，对异质产品的适应力较弱。

这与论文 Table 3 在 full heterogeneity + positive cost (HVHM) 条件下的发现一致：CPBSD-A 的 out-of-sample 优势 (1.10) 大于 in-sample 优势 (1.06)。
