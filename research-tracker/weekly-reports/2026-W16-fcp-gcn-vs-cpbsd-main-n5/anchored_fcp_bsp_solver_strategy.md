# Anchored FCP+BSP 二阶段 Solver 策略

## 1. 方法直觉

Anchored FCP+BSP 的核心思想是：先让 FCP 独立完成自己的 bundle 定价优化，然后把这个 FCP 结果当成固定 anchor，再只用 BSP 去补充 size-tier 覆盖。

这不是重新联合优化 FCP 和 BSP，而是一个真正的 two-stage 策略：

1. Stage 1 独立求解 FCP。
2. 固定 Stage 1 得到的 FCP bundle prices。
3. Stage 2 只优化 BSP size-tier prices \(q_s\)。

最终菜单是：

$$
\text{Fixed FCP bundles}+\text{BSP size options}+\text{outside option}.
$$

它要解决的问题是：保留 FCP 的独立最优性，同时让 BSP 提供一些 FCP 没覆盖到的选择空间。比如 FCP 可能对某些客户没有合适 bundle，导致他们选择 outside；BSP size option 理论上可以补充捕捉这些 outsider customers。

## 2. 与 Phase 3 的区别

这个方法不是 Phase 3 的 full bundle completion。

Phase 3 的问题是：给所有 missing concrete bundles 都用 size price 补价。也就是如果某个具体 bundle 没有 FCP 价格，就强行赋：

$$
p_A=q_{|A|}.
$$

这会把整个 \(2^N\) bundle space 都补满，导致一个 \(q_s\) 要同时代表大量不同具体 bundle。FCP anchors 诱导出的 subadditivity / anti-arbitrage 约束会在 full space 里形成冲突，容易出现 infeasibility 或过强约束。

Anchored FCP+BSP 不这样做。它不创建所有 missing bundle 的价格变量，也不要求所有 concrete bundle 都可购买。BSP 只是一个独立的 size channel：客户选择 size \(s\) 时，拿到自己 valuation 排名前 \(s\) 的商品。

因此最终菜单只有：

$$
\left\{(A_i,p_i^\star):i\in\mathcal{I}^{\star}\right\}
\cup
\left\{\text{BSP top-}s\text{ option priced at }q_s:s=1,\ldots,N\right\}
\cup
\{\text{outside option}\}.
$$

## 3. 二阶段求解流程

Stage 1：

- 独立运行 FCP solver。
- 得到 FCP anchor bundles \(A_i\)。
- 得到固定价格 \(p_i^\star\)。
- 得到每个 in-sample customer 在 Stage 1 的 FCP choice，用于可选的 FCP sales protection。

Stage 2：

- 固定所有 \(p_i^\star\)，不再优化 FCP 价格。
- 新增 BSP size prices \(q_s\)。
- 在 fixed FCP menu + BSP size menu 上重新建 combined choice / IC 模型。
- 加 BSP 内部价格约束和 cross-menu anti-arbitrage 约束。
- 默认加入严格的 in-sample FCP sales protection，避免 BSP 在 Stage 2 中 cannibalize Stage-1 FCP buyers。

Public API：

```python
solve_anchored_fcp_bsp(
    v_kn,
    c_n,
    assortments,
    fcp_bundle_prices,
    fcp_chosen_bundle_idx_by_customer=None,
    time_limit=600.0,
    mip_gap=1e-2,
    output_flag=0,
    threads=0,
    protect_fcp_sales=True,
    strict_fcp_sales_protection=True,
) -> dict
```

这里 `fcp_bundle_prices` 使用 FCP result 的 `bundle_prices_full`。这些价格在 Stage 2 中作为参数进入模型，不是变量。

## 4. 完整数学 Formulation

这一节记录 `solve_anchored_fcp_bsp.py` 中实现的 anchored second-stage MILP。

### 4.1 集合与菜单

令 in-sample customer 集合为：

$$
\mathcal{K}=\{1,\ldots,K\}.
$$

令商品集合为：

$$
\mathcal{N}=\{1,\ldots,N\}.
$$

固定 FCP anchor menu 为：

$$
\mathcal{I}^{\star}
=
\{i:\ A_i\subseteq\mathcal{N},\ |A_i|>0,\ p_i^\star\text{ is available from Stage 1 FCP}\}.
$$

其中 \(A_i\) 是 FCP anchor bundle，\(p_i^\star\) 是 Stage 1 FCP 得到的固定价格。注意 \(p_i^\star\) 是参数，不是 Stage 2 的决策变量。

BSP size menu 为：

$$
\mathcal{S}=\{1,\ldots,N\},\qquad
\mathcal{S}_0=\{0,\ldots,N\}.
$$

对 customer \(k\) 和 size \(s\)，令 \(B_{ks}\) 表示 customer \(k\) 按 valuation 排序后的 top-\(s\) 商品集合。outside option 由“不选择任何 FCP anchor，也不选择任何 BSP size”表示。

### 4.2 参数

Customer-item valuation 和 item cost：

$$
v_{kn}\ge 0,\qquad c_n\ge 0.
$$

FCP anchor value 和 cost：

$$
V^F_{ki}=\sum_{n\in A_i}v_{kn},\qquad
C^F_i=\sum_{n\in A_i}c_n.
$$

BSP top-\(s\) value 和 cost：

$$
V^B_{ks}=\sum_{n\in B_{ks}}v_{kn},\qquad
C^B_{ks}=\sum_{n\in B_{ks}}c_n.
$$

Bundle size：

$$
\ell_i=|A_i|.
$$

Big-\(M\) price upper bound：

$$
M=
\max_{i\in\mathcal{I}^{\star}}p_i^\star
+
\max\left\{\max_{k,i}V^F_{ki},\ \max_k V^B_{kN}\right\}
+1.
$$

如果 `protect_fcp_sales=True` 且提供 Stage-1 choices，定义 protected FCP customer set：

$$
\mathcal{G}
=
\{k\in\mathcal{K}:\ \text{customer }k\text{ selected an active FCP anchor }i(k)\text{ in Stage 1}\}.
$$

### 4.3 决策变量

BSP size prices：

$$
q_s\in[0,M]\qquad \forall s\in\mathcal{S}_0.
$$

Hybrid-menu choice variables：

$$
\theta^F_{ki}\in\{0,1\}
\qquad \forall k\in\mathcal{K},\ i\in\mathcal{I}^{\star},
$$

$$
\theta^B_{ks}\in\{0,1\}
\qquad \forall k\in\mathcal{K},\ s\in\mathcal{S}.
$$

Customer surplus variable：

$$
u_k\ge 0\qquad \forall k\in\mathcal{K}.
$$

BSP realized payment linearization variable：

$$
r_{ks}\in[0,M]\qquad \forall k\in\mathcal{K},\ s\in\mathcal{S}.
$$

其含义是：

$$
r_{ks}=q_s\theta^B_{ks}.
$$

### 4.4 目标函数

最大化 combined menu 的平均 in-sample profit：

$$
\max\ \frac{1}{K}\sum_{k\in\mathcal{K}}
\left[
\sum_{i\in\mathcal{I}^{\star}}
\left(p_i^\star-C^F_i\right)\theta^F_{ki}
+
\sum_{s\in\mathcal{S}}
\left(r_{ks}-C^B_{ks}\theta^B_{ks}\right)
\right].
$$

### 4.5 Single Choice 与 Utility Maximization

每个 customer 最多选择一个 option：一个 fixed FCP bundle、一个 BSP size，或者 outside option。

$$
\sum_{i\in\mathcal{I}^{\star}}\theta^F_{ki}
+
\sum_{s\in\mathcal{S}}\theta^B_{ks}
\le 1
\qquad \forall k\in\mathcal{K}.
$$

Customer 的 selected surplus 必须不低于任何 fixed FCP option：

$$
u_k\ge V^F_{ki}-p_i^\star
\qquad \forall k\in\mathcal{K},\ i\in\mathcal{I}^{\star}.
$$

也必须不低于任何 BSP size option：

$$
u_k\ge V^B_{ks}-q_s
\qquad \forall k\in\mathcal{K},\ s\in\mathcal{S}.
$$

Customer surplus 必须等于实际被选择 option 的 utility：

$$
u_k=
\sum_{i\in\mathcal{I}^{\star}}
\left(V^F_{ki}-p_i^\star\right)\theta^F_{ki}
+
\sum_{s\in\mathcal{S}}
\left(V^B_{ks}\theta^B_{ks}-r_{ks}\right)
\qquad \forall k\in\mathcal{K}.
$$

如果所有 choice variables 都为 0，则 \(u_k=0\)，表示 customer 选择 outside option。

### 4.6 BSP Payment Linearization

对每个 customer 和 BSP size：

$$
r_{ks}\ge q_s-M(1-\theta^B_{ks})
\qquad \forall k\in\mathcal{K},\ s\in\mathcal{S},
$$

$$
r_{ks}\le q_s
\qquad \forall k\in\mathcal{K},\ s\in\mathcal{S},
$$

$$
r_{ks}\le M\theta^B_{ks}
\qquad \forall k\in\mathcal{K},\ s\in\mathcal{S}.
$$

结合 nonnegativity，这些约束确保：

$$
r_{ks}
=
\begin{cases}
q_s, & \theta^B_{ks}=1,\\
0, & \theta^B_{ks}=0.
\end{cases}
$$

### 4.7 Combined Envy-Style IC Constraints

对任意 \(k\ne j\)，customer \(k\) 自己的 assigned surplus 必须不低于 customer \(k\) 模仿 customer \(j\) 的 assigned option 和 payment 时得到的 utility：

$$
u_k
\ge
\sum_{i\in\mathcal{I}^{\star}}
\left(V^F_{ki}-p_i^\star\right)\theta^F_{ji}
+
\sum_{s\in\mathcal{S}}
\left(V^B_{ks}\theta^B_{js}-r_{js}\right)
\qquad
\forall k,j\in\mathcal{K},\ k\ne j.
$$

这和 Joint solver 的 hybrid-menu IC 思路一致；区别是这里 FCP prices 已固定，Stage 2 只优化 BSP size prices。

### 4.8 BSP 内部价格约束

Zero-size price：

$$
q_0=0.
$$

Monotonicity：

$$
q_{s+1}\ge q_s
\qquad s=0,\ldots,N-1.
$$

Subadditivity：

$$
q_{a+b}\le q_a+q_b
\qquad \forall a,b\in\mathcal{S},\ a+b\le N.
$$

### 4.9 Cross-Menu Anti-Arbitrage Constraints

Same-size FCP anchor lower bound：

$$
q_{\ell_i}\ge p_i^\star
\qquad \forall i\in\mathcal{I}^{\star}.
$$

Subset split constraint for FCP anchors：

$$
p_i^\star\le p_j^\star+q_{\ell_i-\ell_j}
\qquad
\forall i,j\in\mathcal{I}^{\star}\ \text{such that}\ A_j\subset A_i.
$$

这些约束的作用是防止 BSP size menu 给出明显更便宜的套利分解，从而破坏 fixed FCP anchor prices。

### 4.10 实验性 FCP Sales Protection

当前默认使用：

```python
protect_fcp_sales=True
strict_fcp_sales_protection=True
```

如果 protection 可用且开启，那么每个 protected Stage-1 FCP customer 首先必须弱偏好自己的原始 FCP choice，而不是任何 BSP size：

$$
V^F_{k,i(k)}-p_{i(k)}^\star
\ge
V^B_{ks}-q_s
\qquad \forall k\in\mathcal{G},\ s\in\mathcal{S}.
$$

同时，当前默认加入严格选择保护，直接禁止这些 protected customers 在 Stage 2 被分配到 BSP：

$$
\theta^B_{ks}=0
\qquad \forall k\in\mathcal{G},\ s\in\mathcal{S}.
$$

这些约束的目的，是避免 BSP 在 Stage 2 里 cannibalize Stage-1 in-sample FCP sales，从而保持“FCP 独立求解，BSP 只是补充”的解释。

重要备注：

- 该保护只针对 in-sample Stage-1 FCP customers。
- 该保护不约束 OOS customers。
- OOS customers 仍然按照 hybrid menu 的最大 surplus 选择 FCP、BSP 或 outside。
- OOS 中出现 FCP-to-BSP migration 不再被视作 solver constraint violation，而是泛化阶段的 cannibalization 现象。

### 4.11 非决策组件

Anchored solver 不优化 FCP prices：

$$
p_i=p_i^\star
\qquad \forall i\in\mathcal{I}^{\star}.
$$

Anchored solver 也不为所有 missing concrete bundles 创建价格变量：

$$
\text{No variable }p_A\text{ is created for }A\subseteq\mathcal{N},\
A\notin\{A_i:i\in\mathcal{I}^{\star}\}.
$$

这正是它和 Phase 3 full bundle completion 的关键区别。

## 5. Smoke 实验结果

### 5.1 N=10 zero / seed 20260413

实验设置：

- 复用已有 phase2 `N=10 zero` instance。
- 使用已有 FCP result 的 `bundle_prices_full` 作为 fixed FCP anchors。
- 只补跑 Anchored FCP+BSP solver。
- 使用 `protect_fcp_sales=True`。

MILP 结果：

| 指标 | 数值 |
| --- | ---: |
| solver status | 2 |
| feasible | True |
| in-sample objective | 51.91159475890626 |
| in-sample FCP choices | 50 |
| in-sample BSP choices | 0 |
| in-sample outside choices | 0 |
| protected customers | 50 |
| protection constraints | 500 |
| strict protection constraints | 500 |
| protected BSP choices | 0 |
| fixed FCP prices preserved | 26 |

约束检查：

- \(q_{\ell_i}\ge p_i^\star\) checked。
- \(p_i^\star\le p_j^\star+q_{\ell_i-\ell_j}\) checked，共 103 个 subset split constraints。
- protected FCP customers 的 weak protection checked，共 500 个 protection constraints。
- protected FCP customers 的 strict selection protection checked，共 500 个 \(\theta^B_{ks}=0\) constraints。

OOS 平均 profit：

| 方法 | OOS avg profit |
| --- | ---: |
| FCP-only | 50.522468 |
| BSP-only | 50.549145 |
| full Joint | 50.344348 |
| Anchored FCP+BSP strict | 50.522468 |

OOS choice / migration 观察：

- FCP-only served 4888，outside 112。
- BSP-only served 4873，outside 127。
- Anchored strict channel assignment：FCP 4888，BSP 0，outside 112。
- 严格保护修复后，之前 weak version 中出现的 OOS FCP-to-BSP cannibalization 不再发生在这个 smoke replay 上。

结论：strict protection 修复了保护语义，但这个 seed 上 Anchored strict 的 OOS 等同 FCP-only，没有额外 coverage gain。

### 5.2 N=10 hvhm / seed 20260413

实验设置：

- 复用 phase3 相关 `N=10 hvhm` seed。
- 复用已有 CPBSD-A、FCP、BSP 结果。
- 只补跑 Anchored FCP+BSP solver。
- 使用 `protect_fcp_sales=True`。

MILP 结果：

| 指标 | 数值 |
| --- | ---: |
| solver status | 2 |
| feasible | True |
| in-sample objective | 3.2455122984617657 |
| in-sample FCP choices | 45 |
| in-sample BSP choices | 0 |
| in-sample outside choices | 5 |
| protected customers | 45 |
| protection constraints | 450 |
| strict protection constraints | 450 |
| protected BSP choices | 0 |
| model constraints | 7384 |
| same-size constraints | 33 |
| subset split constraints | 215 |

OOS 平均 profit：

| 方法 | OOS avg profit |
| --- | ---: |
| FCP-pruned-MB | 2.200927661817421 |
| BSP-only | 2.3022805249552394 |
| CPBSD-A | 2.8092028620405576 |
| Anchored FCP+BSP | 2.200927661817421 |

OOS choice / migration 观察：

- FCP-only served 3557，outside 1443。
- BSP-only served 3750，outside 1250。
- Anchored served 3557，outside 1443。
- Anchored strict channel assignment：FCP 3557，BSP 0，outside 1443。
- 相对 FCP-only，Anchored 没有捕捉新的 outside customers。

Anchored size prices 明显高于 standalone BSP 的小 size prices。例如：

| size | Anchored \(q_s\) | Standalone BSP \(q_s\) |
| ---: | ---: | ---: |
| 1 | 29.0463 | 10.0614 |
| 2 | 29.9215 | 19.7136 |
| 3 | 46.8449 | 27.4761 |
| 4 | 46.8449 | 34.5331 |
| 5 | 54.4063 | 40.3916 |
| 10 | 85.6833 | 54.9925 |

结论：这个 hvhm seed 上 Anchored strict 是 feasible 的，但非常保守。Cross-menu anti-arbitrage 和严格 FCP sales protection 抬高了 BSP size prices，尤其是小 size prices，因此 BSP 失去了 standalone BSP 的低价覆盖能力。最终 OOS 表现等同于 FCP-only，没有获得 CPBSD-A 或 BSP 的 coverage benefit。

### 5.3 hvhm 五 seed batch

运行脚本：

```bash
python project-root/code_submission_project/code_submission/src/data/run_anchored_fcp_bsp_hvhm_batch.py
```

输出目录：

```text
experiments/anchored_fcp_bsp_hvhm_batch/
```

Aggregate OOS：

| N | FCP | BSP | CPBSD-A | Anchored strict | Anchored-FCP | Anchored-BSP | Anchored-CPBSD-A |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | 2.278263 | 2.346959 | 2.847968 | 2.278263 | +0.000000 | -0.068696 | -0.569705 |
| 30 | 4.908230 | 8.046570 | 9.909867 | 4.908214 | -0.000016 | -3.138356 | -5.001653 |

Per-seed 结果显示，Anchored strict 在 10 个 seed 上都没有高于 FCP。`protected_bsp_choice_count` 全部为 0，说明严格 in-sample protection 已生效。

自动诊断选出的失败 seed 中，FCP outside 但 CPBSD-A buys 的客户完全没有被 Anchored 捕捉：

| N | Seed | FCP outside but CPBSD-A buys | Anchored captures | Avg CPBSD-A profit | Avg Anchored best-BSP surplus |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | 20260415 | 972 | 0 | 3.331665 | 0.000000 |
| 10 | 20260413 | 614 | 0 | 3.112486 | 0.000000 |
| 30 | 20260417 | 2568 | 0 | 10.313376 | 0.000000 |
| 30 | 20260416 | 1799 | 0 | 10.489051 | 0.000000 |

诊断显示主要问题不是 OOS customer 不存在，而是 Anchored BSP \(q_s\) 被抬得太高，导致这些 FCP outside customers 对所有 BSP size 的 best surplus 都不为正。对比 CPBSD-A，CPBSD-A 可以通过 item-level component prices 和 size discount 给出更低的 customer-specific effective bundle price。

## 6. 当前判断

Anchored FCP+BSP 的优点是 formulation 清晰、可行，并且保留了 FCP 独立定价的解释。它也明确避开了 Phase 3 full bundle completion 在 \(2^N\) 空间里遇到的 infeasibility 问题。

但目前 strict smoke 和 hvhm batch 结果显示它过于保守：

- 严格 in-sample protection 修复了 Stage-2 protected customers 被 BSP tie 分配的问题。
- 在 zero seed 上，strict Anchored OOS 等同 FCP-only，没有 cannibalization，也没有新增 coverage。
- 在 hvhm 五 seed batch 上，Anchored strict 的 OOS 基本等同 FCP，并显著低于 BSP / CPBSD-A。
- 失败诊断显示，BSP 二阶段补价没有捕捉到 FCP outside customers，因为 \(q_s\) lower bounds 过高，使这些客户的 BSP surplus 为 0。

因此下一步更值得测的是约束 ablation，而不是直接大规模跑全量：

- `protect_fcp_sales=True` vs `False`。
- 保留 strict in-sample protection，但放松 cross-menu anti-arbitrage。
- 保留 \(q_{\ell_i}\ge p_i^\star\)，但放松 subset split constraints。
- 或者只对部分 high-confidence FCP anchors 施加 cross-menu anti-arbitrage。
