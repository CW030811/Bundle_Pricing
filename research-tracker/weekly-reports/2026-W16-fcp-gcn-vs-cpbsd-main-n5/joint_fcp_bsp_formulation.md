# Joint FCP+BSP MILP Formulation


A：FCP 和 BSP 价格之间需要约束进行联合求解，可能出现以下套利场景：
B：分开求解然后拼接Price——大概率Subadd Violation

**场景 1: Same-size 套利**

FCP 为 bundle $A$ (size 3) 定价 $p_A = 20$，但 BSP 的 $q_3 = 15$。理性客户一定选 BSP（获得自己 top-3 items，更便宜），FCP bundle $A$ 无人购买。
#### C12设计
$q_s \geq \max_{i: \lvert S_i \rvert=s} p_i$（BSP ≥ 最贵的同 size FCP），即把 BSP 价格**拉高**到 FCP 水平。

等价改写: 对每个 size $s$，$q_s \geq p_i, \; \forall i \in \mathcal{F}: \lvert S_i \rvert = s$

**预期**:
- BSP 价格被拉高 → BSP 吸引力下降 → 更多客户留在 FCP（高利润）

**场景 2: Split 套利**

**场景 2a: FCP+BSP 拆分替代 FCP**

FCP 为 bundle $A = \{1,2,3,4,5\}$ (size 5) 定价 $p_A = 40$。FCP 也有 sub-bundle $B = \{1,2,3\}$ (size 3) 定价 $p_B = 18$。BSP 为 size-2 定价 $q_2 = 12$。

客户可以购买 FCP bundle $B$ + BSP size-2 (自选 items 4,5) = $18 + 12 = 30 < 40 = p_A$。

> **防护**: **C13** 保证价格一致性: $p_A \leq p_B + q_{|S_A|-|S_B|}$，强制大 bundle 价格不超过 sub-bundle + BSP 补差之和。

**场景 2b: 纯 BSP 拆分替代 FCP**

FCP 为 bundle $A$ (size 5) 定价 $p_A = 40$。BSP $q_3 = 16$, $q_2 = 12$。客户买 BSP size-3 + BSP size-2 = $16+12=28 < 40$。

> **防护**: (1) **C12** 禁止客户直接买 BSP size-5 at $q_5 < p_A$。(2) q_s \leq q_s1 + q_s2防止被BSP拆分替代

### 1.3 Joint 优化
1. **统一目标函数**：同时优化 FCP + BSP 价格，最大化联合菜单的总 profit
2. **Single-choice 约束 (C3)**：每个 customer 只能从 FCP 或 BSP 中选一个
3. **Cross-menu subadditivity (C12, C13)**：约束 FCP 和 BSP 价格的相对关系，防止定价不一致

---

## 2. Mathematical Formulation

### 2.1 Sets

| Symbol | Definition |
|--------|-----------|
| $K$ | Customers, $k = 1 \ldots K$ |
| $N$ | Products |
| $\mathcal{F}$ | FCP anchor bundle indices $(1 \ldots B-1)$, $0$ = empty bundle |
| $\mathcal{S}$ | BSP size tiers $\{1, \ldots, N\}$ |

### 2.2 Parameters

| Symbol | Definition |
|--------|-----------|
| $v_{ki}$ | Customer $k$'s valuation for FCP bundle $i$: $\mathbf{v}_k^\top \mathbf{a}_i$ |
| $c_i$ | Production cost of FCP bundle $i$: $\mathbf{a}_i^\top \mathbf{c}$ |
| $v_{ks}$ | Customer $k$'s top-$s$ items total valuation |
| $c_{ks}$ | Customer $k$'s top-$s$ items total cost |
| $\lvert S_i \rvert$ | Size of FCP bundle $i$ |
| $M$ | Big-M constant |

### 2.3 Decision Variables

| Variable | Type | Meaning |
|----------|------|---------|
| $p_i \geq 0$ | Continuous | FCP anchor $i$ price |
| $q_s \geq 0$ | Continuous | BSP size $s$ price ($q_0 = 0$) |
| $\theta^f_{k,i} \in \{0,1\}$ | Binary | Customer $k$ chooses FCP bundle $i$ |
| $\theta^b_{k,s} \in \{0,1\}$ | Binary | Customer $k$ chooses BSP size $s$ |
| $u_k \geq 0$ | Continuous | Customer $k$ surplus |
| $\text{pay}^f_{k,i} \geq 0$ | Continuous | FCP payment linearization |
| $\text{pay}^b_{k,s} \geq 0$ | Continuous | BSP payment linearization |
| $\pi^f_{k,i}$ | Continuous | FCP profit term |
| $\pi^b_{k,s}$ | Continuous | BSP profit term |

### 2.4 Objective

$$\max \quad \frac{1}{K} \sum_{k=1}^{K} \left[ \sum_{i \in \mathcal{F}} \pi^f_{k,i} + \sum_{s \in \mathcal{S}} \pi^b_{k,s} \right]$$

### 2.5 Constraints

#### (C1) Surplus lower bound — FCP

$$u_k \geq v_{ki} - p_i, \quad \forall k,\; \forall i \in \mathcal{F}$$

#### (C2) Surplus lower bound — BSP

$$u_k \geq v_{ks} - q_s, \quad \forall k,\; \forall s \in \mathcal{S}$$

#### (C3) Single choice (combined menu)

$$\sum_{i \in \mathcal{F}} \theta^f_{k,i} + \sum_{s \in \mathcal{S}} \theta^b_{k,s} \leq 1, \quad \forall k$$

#### (C4) Payment linearization — FCP

$$\text{pay}^f_{k,i} \geq p_i - M(1 - \theta^f_{k,i})$$
$$\text{pay}^f_{k,i} \leq p_i$$

#### (C5) Payment linearization — BSP

$$\text{pay}^b_{k,s} \geq q_s - M(1 - \theta^b_{k,s})$$
$$\text{pay}^b_{k,s} \leq q_s$$

#### (C6) Surplus decomposition

$$s^f_{k,i} = v_{ki} \cdot \theta^f_{k,i} - \text{pay}^f_{k,i}$$
$$s^b_{k,s} = v_{ks} \cdot \theta^b_{k,s} - \text{pay}^b_{k,s}$$
$$u_k = \sum_{i \in \mathcal{F}} s^f_{k,i} + \sum_{s \in \mathcal{S}} s^b_{k,s}$$

#### (C7) IC across customers

$$u_k \geq \sum_{i \in \mathcal{F}} \left( v_{ki} \cdot \theta^f_{j,i} - \text{pay}^f_{j,i} \right) + \sum_{s \in \mathcal{S}} \left( v_{ks} \cdot \theta^b_{j,s} - \text{pay}^b_{j,s} \right), \quad \forall k,\; \forall j \neq k$$

#### (C8) Profit terms

$$\pi^f_{k,i} = \text{pay}^f_{k,i} - c_i \cdot \theta^f_{k,i}$$
$$\pi^b_{k,s} = \text{pay}^b_{k,s} - c_{ks} \cdot \theta^b_{k,s}$$

#### (C9) FCP internal subadditivity

$$p_i \leq \sum_{j \in \mathcal{P}} p_j, \quad \forall \text{ partition } \mathcal{P} \text{ of bundle } i$$

Uses `_restricted_full_partition_families()` for bundles with $\lvert S_i \rvert \leq 10$; falls back to pairwise disjoint partitions for larger bundles.

#### (C10) BSP internal subadditivity

$$q_{s_1 + s_2} \leq q_{s_1} + q_{s_2}, \quad \forall s_1, s_2 : s_1 + s_2 \leq N$$

#### (C11) BSP monotonicity

$$q_{s+1} \geq q_s$$

#### (C12) Cross-menu: BSP ≥ FCP same-size *(optional, controlled by `cross_mode`)*

$$q_{\lvert S_i \rvert} \geq p_i, \quad \forall i \in \mathcal{F}$$

强制 BSP 价格不低于同 size 的 FCP anchor 价格。防止 BSP 低价蚕食 FCP 客户 (场景 1)。

#### (C13) Cross-menu: FCP split anti-arbitrage

$$p_i \leq p_j + q_{\lvert S_i \rvert - \lvert S_j \rvert}, \quad \forall (i, j) : S_j \subset S_i,\; j \in \mathcal{F}$$

Prevents customers from arbitraging via FCP sub-bundle + BSP complement (场景 2).

#### (C14) Boundary

$$q_0 = 0$$

---
## 3. 实验结果展示

### Zero Cost Case

#### N=5 / normal_rho0.0_full_zero（5-seed 平均, seeds=20260425-29）

| Method | InS | OOS |
| --- | ---: | ---: |
| **CPBSD-A** | 25.28 | **24.03** |
| BSP | 25.26 | 24.00 |
| FCP | 25.38 | 23.71 |
| Joint-noC12 | 25.37 | 23.66 |
| Joint | 25.36 | 23.46 |

#### N=10 / normal_rho0.0_full_zero（5-seed 平均, seeds=20260413-17, phase2 instances）

| Method | InS | OOS |
| --- | ---: | ---: |
| **BSP** | 52.00 | **50.08** |
| CPBSD-A | 52.01 | 50.01 |
| FCP | 52.05 | 49.72 |
| Joint-noC12 | 51.94 | 49.36 |
| Joint | 51.97 | 49.26 |

#### N=30 / normal_rho0.0_full_zero（5-seed 平均, seeds=20260413-17, phase2 instances）

| Method | InS | OOS |
| --- | ---: | ---: |
| **BSP** | 159.01 | **156.28** |
| CPBSD-A | 159.05 | 154.97 |
| Joint | 158.96 | 152.53 |
| Joint-noC12 | 159.39 | 150.80 |
| FCP | 157.08 | 148.95 |

---

### Rand_Ind Cost Case
c_n = rng.uniform(0.0, 10.0, size=N)

#### N=5 / normal_rho0.0_full_random_ind（5-seed 平均）

| Method | InS | OOS |
| --- | ---: | ---: |
| **FCP** | 9.90 | **9.37** |
| CPBSD-A | 9.82 | 9.19 |
| Joint-noC12 | 9.91 | 9.05 |
| Joint | 9.91 | 9.04 |
| BSP | 8.71 | 8.38 |

> N=5 baselines from `joint_fcp_bsp_comparison.json` (clean_rerun 平均)

#### N=10 / normal_rho0.0_full_random_ind（5-seed 平均）

| Method | InS | OOS |
| --- | ---: | ---: |
| **FCP** | 17.04 | **16.37** |
| Joint | 17.11 | 15.94 |
| Joint-noC12 | 17.10 | 15.73 |
| BSP | 14.79 | 13.99 |
| CPBSD-A | 13.74 | 13.17 |

#### N=30 / normal_rho0.0_full_random_ind（5-seed 平均）

| Method | InS | OOS |
| --- | ---: | ---: |
| **FCP** | 57.02 | **54.59** |
| Joint | 57.27 | 52.37 |
| Joint-noC12 | 57.30 | 51.88 |
| BSP | 45.61 | 43.12 |
| CPBSD-A | 27.52 | 26.58 |

---

### Rand_Corr Cost Case
  means = valuation_means(N, heterogeneity)   # [1, 2, ..., 10]
  ratio = rng.uniform(0.3, 0.9, size=N)       # 每个产品一个随机比例
  noise = rng.normal(0, 0.5, size=N)           # 高斯噪声
  c_n = max(means * ratio + noise, 0.0)


#### N=5 / normal_rho0.0_full_random_corr（5-seed 平均）

| Method | InS | OOS |
| --- | ---: | ---: |
| **CPBSD-A** | 10.60 | **9.90** |
| BSP | 10.57 | 9.79 |
| Joint | 10.77 | 9.73 |
| Joint-noC12 | 10.77 | 9.70 |
| FCP | 10.76 | 9.57 |

> N=5 baselines from `joint_fcp_bsp_comparison.json` (clean_rerun 平均)

#### N=10 / normal_rho0.0_full_random_corr（5-seed 平均）

| Method | InS | OOS |
| --- | ---: | ---: |
| BSP | 20.31 | **18.97** |
| CPBSD-A | 20.26 | 18.94 |
| Joint | 20.62 | 18.91 |
| Joint-noC12 | 20.61 | 18.90 |
| FCP | 20.50 | 18.84 |

#### N=30 / normal_rho0.0_full_random_corr（5-seed 平均）

| Method | InS | OOS |
| --- | ---: | ---: |
| **BSP** | 65.69 | **62.99** |
| Joint-noC12 | 66.14 | 61.74 |
| Joint | 66.18 | 61.39 |
| FCP | 64.36 | 59.04 |
| CPBSD-A | 56.97 | 54.73 |

---

### OOS 

| Setup | BSP | CPBSD-A | FCP | Joint | Joint-noC12 |
| --- | ---: | ---: | ---: | ---: | ---: |
| N=5 zero | 24.00 | **24.03** | 23.71 | 23.46 | 23.66 |
| N=10 zero | **50.08** | 50.01 | 49.72 | 49.26 | 49.36 |
| N=30 zero | **156.28** | 154.97 | 148.95 | 152.53 | 150.80 |
| N=5 rand_ind | 8.38 | 9.19 | **9.37** | 9.04 | 9.05 |
| N=10 rand_ind | 13.99 | 13.17 | **16.37** | 15.94 | 15.73 |
| N=30 rand_ind | 43.12 | 26.58 | **54.59** | 52.37 | 51.88 |
| N=5 rand_corr | 9.79 | **9.90** | 9.57 | 9.73 | 9.70 |
| N=10 rand_corr | **18.97** | 18.94 | 18.84 | 18.91 | 18.90 |
| N=30 rand_corr | **62.99** | 54.73 | 59.04 | 61.39 | 61.74 |

### 关键发现

1. **Zero cost & Rand_Corr: BSP/CPBSD-A 最优**。Joint OOS 泛化差于 BSP/CPBSD-A，但优于 FCP（N=30: 152.53 vs 148.95）。
2. **Random_ind: FCP 全面领先**。独立随机 cost 下 bundle-specific pricing 优势明显。Joint 次之，但 OOS gap 随 N 增大。


## 6. Case Study: N=10 Zero-Cost Single Instance 深度分析

### 6.1 四种方法 OOS 总览

| Method | InS | OOS | OOS/InS | Served | Outside |
| --- | ---: | ---: | ---: | ---: | ---: |
| BSP | 51.93 | **50.55** | 97.3% | 4873 | 127 |
| CPBSD-A | 51.98 | 50.53 | 97.2% | 4868 | 132 |
| FCP | 51.91 | 50.52 | 97.3% | 4888 | 112 |
| Joint | 51.93 | 50.34 | 96.9% | 4877 | 123 |

四种方法 OOS 极其接近（spread=0.21），但定价机制完全不同。

### 6.2 BSP 

BSP solver size1-7高价，顾客只买 size 8/9/10：
| Size | BSP standalone | 
| ---: | ---: |
| 1-2 | 25.04 | 
| 3 | 50.09 | 
| 4 | 50.09 | 
| 5 | 50.09 |
| 6 | **50.09** | 
| 7 | **50.09** | 
| 8 | 50.09 | 
| 9 | 51.43 |
| 10 | 52.08 |


| Size | Price | Customers | % | Avg Profit |
| ---: | ---: | ---: | ---: | ---: |
| 8 | 50.09 | 178 | 3.6% | 50.09 |
| 9 | 51.43 | 1076 | 21.5% | 51.43 |
| 10 | 52.08 | 3619 | 72.4% | 52.08 |
| outside | — | 127 | 2.5% | 0.00 |

不提供小 size 防止低价分流。72% 客户买全选 bundle (size-10)。定价结构极简（3 个参数），天然避免小 size 蚕食。

### 6.3 FCP — 25 个 per-bundle 差异化定价

GCN prune 后 25 个 non-empty bundles，每个独立定价。高流量 bundles：

| Bundle | Size | Price | Customers | % | Products |
| ---: | ---: | ---: | ---: | ---: | --- |
| 25 | 10 | 51.95 | 4151 | 83.0% | [0-9] (全选) |
| 14 | 9 | 51.50 | 576 | 11.5% | [1-9] |
| 9 | 7 | 41.69 | 52 | 1.0% | [1,2,3,6,7,8,9] |
| 12 | 8 | 46.30 | 49 | 1.0% | [1,2,3,4,6,7,8,9] |
| outside | — | — | 112 | 2.2% | — |

83% 客户集中在 full bundle，per-bundle 差异化在 zero-cost 下作用不大。Outside 最少（112），说明 FCP 的 bundle 覆盖面最广。

### 6.4 CPBSD-A — 组件定价退化为大 size 定价

Component prices $p_n \approx 11.16$（几乎均一），size discount $d_s$ 只在 size 8-10 激活：

| Size | Price 公式 | Effective Price | Customers | % |
| ---: | --- | ---: | ---: | ---: |
| 1-7 | $\sum p_n - s \cdot 0 = 11.16s$ | 11.16 ~ 78.12 | 0 | 0% |
| 8 | $\sum p_n - 8 \times 4.90$ | 50.09 | 195 | 3.9% |
| 9 | $\sum p_n - 9 \times 5.44$ | 51.50 | 850 | 17.0% |
| 10 | $\sum p_n - 10 \times 5.95$ | 52.09 | 3823 | 76.5% |
| outside | — | — | 132 | 2.6% |

**策略本质**：$d_1..d_7 = 0$ 意味着 size<8 定价过高（如 top-5 = $55.82$），无人购买。CPBSD-A 实际退化为只卖 size 8-10，与 BSP 效果等价。

### 6.5 Joint — Unchosen size 定价的 underdetermined 问题

#### FCP 价格对比
部分 FCP bundle 价格比 FCP-only 的最优值压低：

| Bundle | Size | FCP Price | Joint Price | Δ | Products |
| ---: | ---: | ---: | ---: | ---: | --- |
| 4 | 6 | 51.49 | 44.25 | **-7.23** | [1,2,6,7,8,9] |
| 8 | 6 | 45.63 | 37.95 | **-7.68** | [1,2,3,7,8,9] |
| 6 | 7 | 55.78 | 45.67 | **-10.11** | [1,2,4,6,7,8,9] |
| 20 | 7 | 49.92 | 38.46 | **-11.46** | [0,1,2,3,7,8,9] |
| 17 | 8 | 56.08 | 45.69 | **-10.39** | [0,1,2,5,6,7,8,9] |
| 23 | 8 | 56.08 | 43.38 | **-12.70** | [0,1,2,3,4,7,8,9] |
| 25 | 10 | 51.95 | 52.09 | +0.14 | [0-9] |

#### BSP 价格：Joint 定低价？

| Size | BSP standalone | Joint BSP | Joint-noC12 BSP |
| ---: | ---: | ---: | ---: |
| 1-2 | 25.04 | 24.51 | 28.62 |
| 3 | 50.09 | 28.33 | 28.62 |
| 4 | 50.09 | 36.17 | 33.81 |
| 5 | 50.09 | 39.60 | 39.60 |
| 6 | **50.09** | **44.25** | **50.09** |
| 7 | **50.09** | **47.90** | **50.09** |
| 8 | 50.09 | 50.09 | 50.09 |
| 9 | 51.43 | 51.50 | 51.50 |
| 10 | 52.08 | 52.09 | 52.09 |

**关键发现：In-sample 50 个客户中，没有任何人选 BSP size 1-7**。25 个 BSP 客户全部选 size 8/9/10。因此 **q_1 到 q_7 的值对 in-sample objective 完全无影响**——solver 对它们不在意。

#### BSP 设了高价

BSP standalone 的 q_3=50.09 不是被约束"强制"的，而是 **solver 的退化解选择**：

- Subadditivity + monotonicity 只要求 `q_6 >= 25.05`
- Surplus LB 只要求 `q_6 >= 44.25`（临界值，使 size-6 LB 不比 size-10 LB 更紧）
- `q_6` 的可行域是 `[44.25, ∞)`

BSP solver 碰巧选了 q_3=50.09 这个退化解，monotonicity 链传导 `q_4 >= q_3, q_5 >= q_4, ...` 把 q_4-q_7 全拉到 50.09。这个"碰巧的高价"在 OOS 中是安全的——没有客户会选 size<8（因为 size 8 同价但产品更多）。

#### Joint 设了低价

Joint solver 选了另一个退化解：q_6=44.25（刚好在 surplus LB 临界点）。这同样满足所有约束，同样不影响 in-sample objective。差异纯粹是 **Gurobi 在 MIP gap 内选择了不同的退化解**。

但 OOS 评估时，44.25 的 BSP size-6 变成了一个真实的低价菜单选项，吸引了降级客户。


**Joint OOS channel split**:

| Channel | Customers | % | Avg Profit |
| --- | ---: | ---: | ---: |
| FCP | 4646 | 92.9% | 51.77 |
| BSP | 231 | 4.6% | 48.55 |
| Outside | 123 | 2.5% | 0.00 |

### 6.6 Joint vs FCP: Customer Migration 分析

逐客户追踪 FCP-only → Joint hybrid 的迁移：

| 迁移类型 | 人数 | % | 人均 Δprofit | 总 Δprofit |
| --- | ---: | ---: | ---: | ---: |
| fcp→fcp（留在 FCP） | 4645 | 92.9% | +0.08 | +378.91 |
| **fcp→bsp（转向 BSP）** | **224** | **4.5%** | **-2.95** | **-660.03** |
| **served→outside（流失）** | **19** | **0.4%** | **-51.41** | **-976.72** |
| outside→served（新增） | 8 | 0.2% | +45.91 | +367.24 |
| **净效果** | | | **-0.18** | **-890.60** |

224 个 fcp→bsp 客户中：
- **68% (153人)** 是因为 Joint 提高了他们原 FCP bundle 价格（如 full bundle +$0.14），surplus 减少后 BSP 更优
- **32% (71人)** 是 FCP 价格不变，但 BSP 提供了更优的 smaller size 选项

### 6.7 Root Cause: Formulation Gap

**Joint 比 FCP 差 0.18 的根因是 unchosen size/bundle 定价的 underdetermined 问题**：

1. **In-sample 50 个客户集中在 size 8-10**：size 1-7 的 BSP 价格和大量 FCP bundle 价格对 in-sample objective 无影响。
2. **Solver 对这些价格不在意**：它们是约束可行域中的任意点，不是利润最优点。Gurobi 在 MIP gap 内停在哪个退化解取决于搜索路径。
3. **BSP standalone 碰巧选了安全的退化解**（高价），**Joint 碰巧选了危险的退化解**（低价）。
4. **OOS 评估把低价暴露给 5000 个客户**：224 人利用了低价 BSP size 5-8 降级，19 人因 FCP 提价流失。
