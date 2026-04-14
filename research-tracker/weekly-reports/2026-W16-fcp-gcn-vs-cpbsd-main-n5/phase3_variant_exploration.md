# Phase 3 Variant Exploration

## Scope

这页记录的是 `Phase 3` 的第一轮 `OOS repair` 探索，约束边界先固定：

- 不改 `FCP-MB` 的 `In Sample` 求解逻辑
- 不改 `FCP` 已经定价的 anchor bundles
- 只在 `OOS evaluation` 前补齐 `full bundle space` 里原本未定价的 bundles

当前的核心问题已经确认：  
现有 `FCP-MB` 的 `OOS` 评估仍然只在 `pruned bundle space` 上 replay，没有恢复到 full bundle space。见 [phase3_oos_logic_note.md](/Users/sensen/.openclaw/workspace/domains/revenue-management/research-tracker/weekly-reports/2026-W16-fcp-gcn-vs-cpbsd-main-n5/phase3_oos_logic_note.md)。

## Fixed Probe Setup

- 主诊断实例：
  [cpbsd_instance_001_N10_K50_normal_rho0.0_full_hvhm.msgpack](/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/cpbsd_fcp_pruned_mb_compare_n10k50_strict300/instances/cpbsd_instance_001_N10_K50_normal_rho0.0_full_hvhm.msgpack)
- 对应 `FCP-MB` 结果：
  [cpbsd_instance_001_N10_K50_normal_rho0.0_full_hvhm__fcp_pruned_mb.json](/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/cpbsd_fcp_pruned_mb_compare_n10k50_strict300/results/cpbsd_instance_001_N10_K50_normal_rho0.0_full_hvhm__fcp_pruned_mb.json)
- 严格 `BSP`-based completion probe：
  [run_phase3_oos_bsp_completion_probe.py](/Users/sensen/.openclaw/workspace/domains/revenue-management/project-root/code_submission_project/code_submission/src/data/run_phase3_oos_bsp_completion_probe.py:47)
- infeasibility diagnosis：
  [diagnose_phase3_oos_bsp_completion_infeasibility.py](/Users/sensen/.openclaw/workspace/domains/revenue-management/project-root/code_submission_project/code_submission/src/data/diagnose_phase3_oos_bsp_completion_infeasibility.py:113)
- probe summary：
  [probe_summary.md](/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/phase3_oos_bsp_completion_probe_n10_normal_rho0.0_full_hvhm_inst001/probe_summary.md)
- diagnosis summary：
  [diagnosis_summary.json](/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/phase3_oos_bsp_completion_infeasibility_diag_n10_normal_rho0.0_full_hvhm_inst001/diagnosis_summary.json)

baseline 数值：

- restricted `FCP-MB` in-sample revenue = `3.561872`
- restricted `FCP-MB` OOS revenue = `2.399032`

## Notation

- `B = {0,1}^n`：full bundle space
- `A_F subset B`：`FCP-MB` in-sample 选出的 pruned anchor bundles
- `P_F(S)`：anchor bundle `S in A_F` 的固定价格
- `|S|`：bundle size
- `q_s`：`BSP` 风格的 size price，`s = 0,1,...,n`
- `q_s^BSP`：直接在完整 in-sample valuation 上求出的 `BSP` baseline size price

completion 后的 full menu 记为 `P(S)`。

## Step 0: 先求一个 BSP Size Scaffold

两个 variant 都先调用标准 `BSP` 压缩模型，先得到一个全 size 的 baseline scaffold `q^BSP`。对应实现见：

- `v_ks / c_ks` prefix-sum 压缩：[run_phase3_oos_bsp_completion_probe.py](/Users/sensen/.openclaw/workspace/domains/revenue-management/project-root/code_submission_project/code_submission/src/data/run_phase3_oos_bsp_completion_probe.py:61)
- `BSP` MILP 主体：[run_phase3_oos_bsp_completion_probe.py](/Users/sensen/.openclaw/workspace/domains/revenue-management/project-root/code_submission_project/code_submission/src/data/run_phase3_oos_bsp_completion_probe.py:70)

核心代码是：

```python
v_ks[k, 1:] = np.cumsum(ordered_vals)
c_ks[k, 1:] = np.cumsum(ordered_costs)

model.addConstr(p[size1 + size2] <= p[size1] + p[size2], name=f"subadd_{size1}_{size2}")
model.addConstr(p[size + 1] >= p[size], name=f"monotone_{size}")
```

这里保留了 `BSP` 的核心压缩逻辑：  
客户对所有 size-`s` bundle 的最优选择，被压缩成按 valuation 排序后的前 `s` 个商品的 prefix sum，而不是显式枚举 `2^n` 个 bundles。

## Anchor Mapping

两个 variant 都先把 restricted `FCP` 结果映射回 full bundle index。对应实现见 [run_phase3_oos_bsp_completion_probe.py](/Users/sensen/.openclaw/workspace/domains/revenue-management/project-root/code_submission_project/code_submission/src/data/run_phase3_oos_bsp_completion_probe.py:129)。

核心代码是：

```python
restricted_assortments = np.asarray(fcp_result["assortments"], dtype=int)
restricted_prices = normalize_numeric_keys(fcp_result.get("bundle_prices_full") or {})
full_lookup = {tuple(row.tolist()): idx for idx, row in enumerate(full_assortments)}

for ridx, bundle in enumerate(restricted_assortments):
    price = restricted_prices.get(ridx)
    full_idx = full_lookup[tuple(bundle.tolist())]
    anchor_prices[full_idx] = float(price)
```

输出是一个 `anchor_prices: full_bundle_idx -> fixed_price` 的字典。

## Variant A: Anchored BSP Projection

### Completion Rule

`Variant A` 的定义最直接：

- 若 `S in A_F`，则 `P(S) = P_F(S)`
- 若 `S notin A_F`，则 `P(S) = q_|S|`

也就是：  
所有未定价 bundles 完全由单一 `size price` 补齐，anchor bundles 一律不动。

### Mathematical Formulation

变量：

- `q_s >= 0`
- `d_s >= 0`

目标：

```text
min  sum_{s=0}^n d_s
```

其中 `d_s` 表示 completion scaffold `q_s` 与 `BSP` baseline `q_s^BSP` 的偏离。

约束：

```text
q_0 = 0
q_{s+1} >= q_s                             for s = 0,...,n-1
q_{a+b} <= q_a + q_b                       for all a,b with a+b <= n

d_s >= q_s - q_s^BSP
d_s >= q_s^BSP - q_s                       for s = 0,...,n

P(S) = P_F(S)                              for S in A_F
P(S) = q_|S|                               for S notin A_F

P(S union T) <= P(S) + P(T)                for all S,T in B
```

最后一组约束是 full bundle space 上的全局 subadditivity。

### Code Path

- solver 定义：[run_phase3_oos_bsp_completion_probe.py](/Users/sensen/.openclaw/workspace/domains/revenue-management/project-root/code_submission_project/code_submission/src/data/run_phase3_oos_bsp_completion_probe.py:163)
- diagnostic 版本：[diagnose_phase3_oos_bsp_completion_infeasibility.py](/Users/sensen/.openclaw/workspace/domains/revenue-management/project-root/code_submission_project/code_submission/src/data/diagnose_phase3_oos_bsp_completion_infeasibility.py:113)

核心代码是：

```python
for i in range(bundle_count):
    for j in range(i, bundle_count):
        union_idx = union_index[tuple(np.maximum(bundle_i, bundle_j).tolist())]
        lhs = price_expr_for_idx(union_idx, anchor_prices, bundle_sizes, q)
        rhs = price_expr_for_idx(i, anchor_prices, bundle_sizes, q) + price_expr_for_idx(j, anchor_prices, bundle_sizes, q)
        model.addConstr(lhs <= rhs, name=f"global_subadd_{i}_{j}")
```

这个版本最严格，因为它要求 completed menu 在 full bundle space 上显式满足全局 subadditivity。

## Variant B: Reduced-Coupling Anchored BSP Projection

### Completion Rule

`Variant B` 仍然保留同样的 completed menu 结构：

- 若 `S in A_F`，则 `P(S) = P_F(S)`
- 若 `S notin A_F`，则 `P(S) = q_|S|`

但它不再对 full bundle space 上所有 pair 都显式加约束，而是只保留 anchor-induced 的耦合约束。

### Mathematical Formulation

变量和目标与 `Variant A` 相同：

```text
min  sum_{s=0}^n d_s
```

基础 size scaffold 约束也相同：

```text
q_0 = 0
q_{s+1} >= q_s
q_{a+b} <= q_a + q_b
d_s >= q_s - q_s^BSP
d_s >= q_s^BSP - q_s
```

不同的是它只保留三类 anchor-induced constraints。

1. anchor-pair coupling

对任意两个 anchor bundles `U,V in A_F`：

```text
P(U union V) <= P_F(U) + P_F(V)
```

如果 `U union V` 也是 anchor，就用它的固定 price。  
如果 `U union V` 不是 anchor，就退化成 `q_|U union V|`。

2. anchor-size envelope

对任意 anchor `U in A_F` 和任意 size `b`：

```text
q_t <= P_F(U) + q_b
for all t in [max(|U|, b), min(n, |U| + b)]
```

这组约束表达的是：  
“某个 size-`t` 的 missing bundle，不应该比 `anchor U + 一个 size-b scaffold` 更贵。”

3. subset-anchor coupling

对任意 anchors `A subset U`：

```text
P_F(U) <= P_F(A) + q_|U \ A|
```

这组约束要求 larger anchor bundle 仍然能被 smaller anchor 加上一段 size scaffold 解释。

### Code Path

- solver 定义：[run_phase3_oos_bsp_completion_probe.py](/Users/sensen/.openclaw/workspace/domains/revenue-management/project-root/code_submission_project/code_submission/src/data/run_phase3_oos_bsp_completion_probe.py:219)
- diagnostic 版本：[diagnose_phase3_oos_bsp_completion_infeasibility.py](/Users/sensen/.openclaw/workspace/domains/revenue-management/project-root/code_submission_project/code_submission/src/data/diagnose_phase3_oos_bsp_completion_infeasibility.py:153)

核心代码是：

```python
model.addConstr(lhs <= price_i + float(anchor_prices[j]), name=f"anchor_pair_{i}_{j}")
model.addConstr(q[union_size] <= price_i + q[b], name=f"anchor_size_{i}_{b}_{union_size}")
model.addConstr(price_u <= float(anchor_prices[a]) + q[rem], name=f"subset_anchor_{u}_{a}")
```

`Variant B` 比 `Variant A` 稍弱，但仍然坚持 `size-only scaffold`，所以它本质上还是把所有 unpriced bundles 折叠到了 `q_s` 这一层。

## Why Both Variants Became Infeasible

理论上，根因不是 anchor bundles 彼此直接打架。  
在主诊断实例上，已经检查过 `37` 个 anchor bundles 之间没有 `anchor-anchor` 的直接全局 subadditivity 冲突。

真正的问题是：

- `FCP` anchor prices 带有 bundle identity information
- `Variant A/B` 都把所有 unpriced bundles 压缩成同一个 `q_s`
- 不同 anchors 会对同一个 `q_s` 施加互相矛盾的上下界

换句话说：

```text
同样 size 的 missing bundles，在 FCP anchor 的诱导下其实应该有明显不同的价格。
一旦强行共享同一个 q_s，就可能出现无解。
```

## Fully Diagnosed Infeasible Instance

主诊断实例：

- [cpbsd_instance_001_N10_K50_normal_rho0.0_full_hvhm.msgpack](/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/cpbsd_fcp_pruned_mb_compare_n10k50_strict300/instances/cpbsd_instance_001_N10_K50_normal_rho0.0_full_hvhm.msgpack)
- Gurobi log:
  [variant_a_gurobi.log](/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/phase3_oos_bsp_completion_infeasibility_diag_n10_normal_rho0.0_full_hvhm_inst001/variant_a_gurobi.log)
  [variant_b_gurobi.log](/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/phase3_oos_bsp_completion_infeasibility_diag_n10_normal_rho0.0_full_hvhm_inst001/variant_b_gurobi.log)
- IIS dumps:
  [variant_a_iis.ilp](/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/phase3_oos_bsp_completion_infeasibility_diag_n10_normal_rho0.0_full_hvhm_inst001/variant_a_iis.ilp)
  [variant_b_iis.ilp](/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/phase3_oos_bsp_completion_infeasibility_diag_n10_normal_rho0.0_full_hvhm_inst001/variant_b_iis.ilp)

### Variant A IIS

IIS 只抓到了两条约束：

- `global_subadd_67_256`
- `global_subadd_129_256`

把它们翻译成 bundle/price 后，冲突是：

- bundle `256`：size `1`，anchor price = `2.5293`
- bundle `129`：size `2`，anchor price = `14.9209`
- bundle `323`：anchor price = `26.8569`
- bundle `67`：missing，size `3`，价格只能是 `q_3`
- bundle `385`：missing，size `3`，价格也只能是 `q_3`

于是：

```text
P(323) <= P(67) + P(256)    => 26.8569 <= q_3 + 2.5293   => q_3 >= 24.3276
P(385) <= P(129) + P(256)   => q_3 <= 14.9209 + 2.5293   => q_3 <= 17.4502
```

所以 `Variant A` 要求同时满足：

```text
q_3 >= 24.3276
q_3 <= 17.4502
```

直接无解。

### Variant B IIS

IIS 只抓到了两条约束：

- `anchor_pair_129_256`
- `subset_anchor_131_0`

翻译后：

```text
subset_anchor_131_0   => 22.5228 <= q_3
anchor_pair_129_256   => q_3 <= 14.9209 + 2.5293 = 17.4502
```

所以 `Variant B` 需要同时满足：

```text
q_3 >= 22.5228
q_3 <= 17.4502
```

也直接无解。

## Infeasible Instances Scanned So Far

除了上面的主诊断实例，我又扫了一轮已经跑完的 `N=10 / normal_rho0.0_full_hvhm` 五个 seed。当前扫到的情况是：这五个 seed 上，`Variant A` 和 `Variant B` 都直接 infeasible。

| Run Seed | Instance Path | Anchor Count | Variant A | Variant B |
| --- | --- | ---: | --- | --- |
| `seed_20260413` | [cpbsd_instance_001_N10_K50_normal_rho0.0_full_hvhm.msgpack](/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/fcp_mb_phase2_selected_n10_n30_5inst/n10/normal_rho0.0_full_hvhm/runs/seed_20260413/instances/cpbsd_instance_001_N10_K50_normal_rho0.0_full_hvhm.msgpack) | `34` | `status=3, infeasible` | `status=3, infeasible` |
| `seed_20260414` | [cpbsd_instance_001_N10_K50_normal_rho0.0_full_hvhm.msgpack](/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/fcp_mb_phase2_selected_n10_n30_5inst/n10/normal_rho0.0_full_hvhm/runs/seed_20260414/instances/cpbsd_instance_001_N10_K50_normal_rho0.0_full_hvhm.msgpack) | `38` | `status=3, infeasible` | `status=3, infeasible` |
| `seed_20260415` | [cpbsd_instance_001_N10_K50_normal_rho0.0_full_hvhm.msgpack](/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/fcp_mb_phase2_selected_n10_n30_5inst/n10/normal_rho0.0_full_hvhm/runs/seed_20260415/instances/cpbsd_instance_001_N10_K50_normal_rho0.0_full_hvhm.msgpack) | `38` | `status=3, infeasible` | `status=3, infeasible` |
| `seed_20260416` | [cpbsd_instance_001_N10_K50_normal_rho0.0_full_hvhm.msgpack](/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/fcp_mb_phase2_selected_n10_n30_5inst/n10/normal_rho0.0_full_hvhm/runs/seed_20260416/instances/cpbsd_instance_001_N10_K50_normal_rho0.0_full_hvhm.msgpack) | `32` | `status=3, infeasible` | `status=3, infeasible` |
| `seed_20260417` | [cpbsd_instance_001_N10_K50_normal_rho0.0_full_hvhm.msgpack](/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/fcp_mb_phase2_selected_n10_n30_5inst/n10/normal_rho0.0_full_hvhm/runs/seed_20260417/instances/cpbsd_instance_001_N10_K50_normal_rho0.0_full_hvhm.msgpack) | `36` | `status=3, infeasible` | `status=3, infeasible` |

这里的结论已经比较稳：

- 这不是单个 instance 的偶然现象
- 至少在当前 `N=10 / normal_rho0.0_full_hvhm` 这组 5-instance 样本上，`size-only BSP scaffold` 无法承接 `FCP` anchor prices

## Additional Coarse Repairs Already Tried

为了确认问题不只是“约束太硬”，还额外试了几种更粗暴的 same-size completion：

- `same_size_anchor_min`
- `same_size_anchor_mean`
- `same_size_anchor_median`
- `same_size_anchor_max`
- `bsp_clipped_to_anchor_range`

代码见：

- heuristic probe：[run_phase3_oos_heuristic_completion_probe.py](/Users/sensen/.openclaw/workspace/domains/revenue-management/project-root/code_submission_project/code_submission/src/data/run_phase3_oos_heuristic_completion_probe.py:119)
- summary：
  [heuristic_probe_summary.md](/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/phase3_oos_heuristic_completion_probe_n10_normal_rho0.0_full_hvhm_inst001/heuristic_probe_summary.md)

这些粗暴方法虽然能补出 full menu，但结果很差：

- 最好的直接 heuristic 是 `same_size_anchor_max`
- repaired OOS revenue = `-6.154703`
- 相比 restricted baseline `2.399032` 反而大幅变差

加上 `cost floor` 后，负利润现象减轻了，但 OOS 仍然远低于 baseline。当前最佳的 `cost-floor` 版本是：

- `same_size_anchor_median_cost_floor`
- repaired OOS revenue = `0.066332`

这说明：

- strict `BSP` compression 太硬，会直接 infeasible
- same-size 粗暴补价太粗，虽然 feasible，但 menu 质量非常差

## Current Takeaway

这轮探索给出的结论已经足够明确：

- `Phase 3` 的问题不是“只要把 missing bundles 补个 size price 就行”
- 失败根因是：`FCP` anchor price structure 含有 bundle identity 信息，而单一 `q_s` 会把这种差异压扁
- 下一版 repair 如果还想保留压缩，就需要比 `pure size` 更细，但又不能回到 full `2^n` bundle variables

当前最自然的下一步不是继续调 `q_s`，而是设计一个比 `BSP` 稍细的 compressed scaffold，例如：

- `size + anchor neighborhood`
- `size + representative pattern class`
- 或只给“和 anchor 足够接近”的 missing bundles 共享同一个 completion block
