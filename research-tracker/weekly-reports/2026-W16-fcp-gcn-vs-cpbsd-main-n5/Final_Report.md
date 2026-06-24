20260419

# Ins & OOS 在不同Sample Setup的表现对比

## 在以下Setup下，N=10 OOS表现接近（仍弱于CPBSD-A），N=30严重比不过CPBSD-A

| N | Setting | Method | Instances | Avg Rev In | Avg Rev OOS | Avg Runtime (s) |
| ---: | --- | --- | ---: | ---: | ---: | ---: |
| 10 | `logit_rho0.0_full_hvhm` | `BSP` | 5 | 2.8427 | 2.5334 | 7.5905 |
| 10 | `logit_rho0.0_full_hvhm` | `CPBSD-A` | 5 | 2.8405 | 2.5961 | 300.1702 |
| 10 | `logit_rho0.0_full_hvhm` | `FCP-pruned-MB` | 5 | 2.8795 | 2.5234 | 164.8764 |
| 10 | `normal_rho0.0_full_hvhm` | `BSP` | 5 | 2.7211 | 2.3470 | 10.7462 |
| 10 | `normal_rho0.0_full_hvhm` | `CPBSD-A` | 5 | 3.2091 | 2.8480 | 300.1895 |
| 10 | `normal_rho0.0_full_hvhm` | `FCP-pruned-MB` | 5 | 3.2555 | 2.2783 | 239.9668 |
| 10 | `normal_rho0.0_full_zero` | `BSP` | 5 | 51.9965 | 50.0813 | 0.7184 |
| 10 | `normal_rho0.0_full_zero` | `CPBSD-A` | 5 | 52.0094 | 50.0095 | 2.0483 |
| 10 | `normal_rho0.0_full_zero` | `FCP-pruned-MB` | 5 | 52.0524 | 49.7242 | 2.6281 |
| 10 | `normal_rho0.5_full_hvhm` | `BSP` | 5 | 2.7057 | 2.1384 | 6.9547 |
| 10 | `normal_rho0.5_full_hvhm` | `CPBSD-A` | 5 | 2.8665 | 2.3487 | 300.2002 |
| 10 | `normal_rho0.5_full_hvhm` | `FCP-pruned-MB` | 5 | 3.0857 | 2.0751 | 117.1857 |
| 30 | `logit_rho0.0_full_hvhm` | `BSP` | 5 | 9.5068 | 8.6014 | 51.6979 |
| 30 | `logit_rho0.0_full_hvhm` | `CPBSD-A` | 5 | 9.5632 | 9.0021 | 600.5983 |
| 30 | `logit_rho0.0_full_hvhm` | `FCP-pruned-MB` | 5 | 9.5949 | 7.8169 | 580.6219 |
| 30 | `normal_rho0.0_full_hvhm` | `BSP` | 5 | 9.2395 | 8.0466 | 208.0632 |
| 30 | `normal_rho0.0_full_hvhm` | `CPBSD-A` | 5 | 10.6736 | 9.9099 | 600.4776 |
| 30 | `normal_rho0.0_full_hvhm` | `FCP-pruned-MB` | 5 | 11.9822 | 4.9082 | 6.6362 |
| 30 | `normal_rho0.0_full_zero` | `BSP` | 5 | 159.0085 | 156.2822 | 1.7222 |
| 30 | `normal_rho0.0_full_zero` | `CPBSD-A` | 5 | 159.0511 | 154.9680 | 600.2432 |
| 30 | `normal_rho0.0_full_zero` | `FCP-pruned-MB` | 5 | 157.0804 | 148.9471 | 14.6219 |
| 30 | `normal_rho0.5_full_hvhm` | `BSP` | 5 | 8.4018 | 6.9757 | 323.8681 |
| 30 | `normal_rho0.5_full_hvhm` | `CPBSD-A` | 5 | 9.3932 | 8.5814 | 600.5398 |
| 30 | `normal_rho0.5_full_hvhm` | `FCP-pruned-MB` | 5 | 10.5253 | 5.6190 | 35.7013 |

---

# OOS 表现差于 CPBSD-A 和 BSP 分析

## 定价策略差异对比

三种方法在 In-Sample 定价和 OOS 覆盖上存在本质差异：

| | BSP | CPBSD-A | FCP-pruned-MB |
| --- | --- | --- | --- |
| **定价参数** | N+1 个 size prices | 2N 个 (p_n, d_s) | Per-bundle 独立定价 |
| **OOS 覆盖** | 每个 customer 的 top-s prefix bundle（customer-specific） | 全 2^N bundles（通过 component pricing 公式） | 仅 in-sample 定价的 bundles |
| **OOS bundle 生成** | 隐式：每个 OOS customer 自己的 top-s items | 隐式：任意 bundle 都有定义价格 | 显式：固定 menu |

## 单实例 OOS 诊断

### N=10 `normal_rho0.0_full_hvhm` seed_20260413 (K_out=5000)

| Method | Bundle 空间 | Outside Option | Buyers | Avg Rev/Buyer | OOS Revenue |
| --- | ---: | ---: | ---: | ---: | ---: |
| `FCP` | 34 | 1443 | 3557 | 3.094 | 2.201 |
| `BSP` | 11 sizes | 1250 | 3750 | 3.070 | 2.302 |
| `CPBSD-A` | 2^10=1024 | 1106 | 3894 | 3.607 | **2.809** |

### N=30 `normal_rho0.0_full_hvhm` seed_20260413 (K_out=5000)

| Method | Bundle 空间 | Outside Option | Buyers | Avg Rev/Buyer | OOS Revenue |
| --- | ---: | ---: | ---: | ---: | ---: |
| `FCP` | 51 | 1915 | 3085 | 9.363 | 5.777 |
| `BSP` | 11 sizes | 625 | 4375 | 9.384 | 8.211 |
| `CPBSD-A` | 2^30≈10^9 | 327 | 4673 | 10.718 | **10.017** |

- **N 越大差距越大**：N=30 时 FCP outside option 1915 vs CPBSD-A 327，差距从 N=10 的 337 扩大到 1588。

---

# FCP 在 OOS 上的优化 Heuristic 探索报告

## Round 1: Size-Only Completion (BSP) — 失败

**逻辑**：用 BSP 风格的 size price `q_s` 补全所有 missing bundles：`P(S) = q_{|S|}`。

**结果**：5/5 seeds 全部 **INFEASIBLE**。

**原因**：同 size 不同 bundles 被迫共价，而 FCP anchor prices 带有 bundle identity 信息，对同一个 `q_s` 施加互相矛盾的上下界。例如 `q_3 >= 24.33` 且 `q_3 <= 17.45`。

【这里添加一个具体例子】


## Round 2: Extended Menu + Per-Bundle Pricing

**逻辑**：不补全 full 2^N，只选择性添加 in-sample customers 的 top-s prefix bundles 作为候选。每个候选独立定价，FCP anchors 通过等式约束固定，subadditivity 只在 extended menu 内 enforce。

**实现**：
1. 候选生成：`for k in K_in: for s in 1..N: candidate = top-s items of customer k by v_kn`
2. Extended menu = FCP anchors + 去重候选（~16 new bundles for N=10）
3. `solve_extended_mb()`：与 `solve_mb_restricted` 相同 MILP + `p[anchor] == P_F(anchor)` 等式约束

**N=10 5-seed 结果** (`normal_rho0.0_full_hvhm`)：

| Method | InS Mean | OOS Mean | Runtime |
| --- | ---: | ---: | ---: |
| `FCP-pruned-MB` | 3.256 | 2.278 | 239.4s |
| `FCP+ExtMenu` | **3.299** | **2.339** | 239.8s (+0.4) |
| `CPBSD-A` | 3.209 | **2.848** | 300.0s |

OOS +0.061 vs FCP（5/5 seeds 全部改善），但仍低于 CPBSD-A 0.509。

## Round 4: GCN-PCP Progressive Chain — 进一步改善

**逻辑**：利用 GCN 预测概率排序（而非 valuation 排序）生成 PCP 风格 progressive chain。

**实现**：
1. GCN 推理 → per-customer per-product 概率 `P[k,n]`
2. 对每个 customer，筛选 `P[k,n] >= 0.2`，按概率降序生成 progressive chain
3. 候选数 ~170（vs Round 3 的 ~16），menu ~206
4. 同样的 `solve_extended_mb()` + anchor fixing

**N=10 5-seed 结果**：

| Method | InS Mean | OOS Mean | Runtime |
| --- | ---: | ---: | ---: |
| `FCP-pruned-MB` | 3.256 | 2.278 | 239.4s |
| `FCP+GCN-PCP(t=0.2)` | **3.532** | **2.450** | 256.8s (+17.5) |
| `CPBSD-A` | 3.209 | **2.848** | 300.0s |

OOS +0.172 vs FCP，超过 BSP（2.347），但仍低于 CPBSD-A 0.398。

**N=30 限制**：1241 bundles 的 MILP + subadditivity partition 枚举计算不可行。

## Round 5: CPBSD-GCN (GCN 概率替换 net-value 排序)

**逻辑**：在 CPBSD-A 的 MILP 中，将 `build_rankings` 从 `argsort(-(v-c))` 改成 `argsort(-prob)`。

**结果**：
- 但 OOS 2.422（低于 CPBSD-A 2.848），Runtime 300s（无加速优势）。

## Round 6: FCP + CPBSD-A Hybrid (Greedy Safe Max) — 持平

**逻辑**：以 CPBSD-A 的 component pricing 为底层全覆盖定价，在 FCP price > CPBSD-A price 的 anchor bundles 上替换。

**结果**：

| Instance | Method | OOS |
| --- | --- | ---: |
| N=10 seed_20260413 | CPBSD-A | 2.809 |
| N=10 seed_20260413 | Hybrid (safe max) | 2.803 (−0.006) |
| N=30 seed_20260413 | CPBSD-A | 10.017 |
| N=30 seed_20260413 | Hybrid (safe max) | 10.017 (+0.000) |

**根因**：在 full 2^N coverage 的 component pricing 基础上提高部分 bundle 价格，会降低 customer surplus → customer 转向其他便宜 bundle 或不变。

---

# 总结

- **优势**：In-sample revenue 最高（per-bundle 独立定价的表达力），GCN 加速下 runtime 极快（N=30 仅 2.8s vs CPBSD-A 600s）
- **劣势**：OOS coverage 严重不足（34-51 bundles vs 2^N），且无法通过 post-hoc repair 弥补

## 所有 OOS 修复策略的结论

| 策略 | 能否改善 FCP OOS | 能否超越 CPBSD-A OOS |
| --- | --- | --- |
| Size-only completion | ✗ INFEASIBLE | — |
| Component pricing completion | ✗ Cannibalize | — |
| Extended menu (top-s) | ✓ +0.061 | ✗ 差 0.509 |
| GCN-PCP (t=0.2) | ✓ +0.172 | ✗ 差 0.398 |
| CPBSD-GCN (替换排序) | ✓ +0.144 | ✗ 差 0.426 |
| CPBSD-A + FCP hybrid | — | ✗ 持平 |

