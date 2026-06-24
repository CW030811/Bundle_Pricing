# Phase 3 Probe Results

## Scope

Fixed probe instance:

- instance: `cpbsd_instance_001_N10_K50_normal_rho0.0_full_hvhm`
- setup: `N=10`, `normal`, `rho=0.0`, `full`, `hvhm`

Baseline:

- restricted `FCP-MB` in-sample revenue: `3.561872`
- restricted `FCP-MB` OOS revenue: `2.399032`

## 1. Strict BSP-Compressed Completion

Reference files:

- [probe_summary.md](/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/phase3_oos_bsp_completion_probe_n10_normal_rho0.0_full_hvhm_inst001/probe_summary.md)
- [diagnosis_summary.json](/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/phase3_oos_bsp_completion_infeasibility_diag_n10_normal_rho0.0_full_hvhm_inst001/diagnosis_summary.json)

Result:

- `Variant A: Anchored BSP Projection` is infeasible
- `Variant B: Reduced-Coupling BSP Projection` is infeasible

IIS summary:

- `Variant A`: `global_subadd` conflicts
- `Variant B`: `anchor_pair` + `subset_anchor` conflicts

Interpretation:

- fixed `FCP` anchor prices are not compatible with a single size-only `BSP` scaffold on this instance

## 2. Coarse Same-Size Price Propagation

Reference file:

- [heuristic_probe_summary.md](/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/phase3_oos_heuristic_completion_probe_n10_normal_rho0.0_full_hvhm_inst001/heuristic_probe_summary.md)

Direct same-size propagation without cost floor performs extremely badly.

Best of the direct heuristics:

- `same_size_anchor_max`
- OOS revenue: `-6.154703`
- delta vs restricted OOS: `-8.553735`

Interpretation:

- copying same-size prices to all missing bundles creates many loss-making bundles and heavily breaks global price coherence

## 3. Coarse Same-Size Propagation With Cost Floor

For missing bundles only, replace

- `price = copied_size_price`

with

- `price = max(copied_size_price, bundle_cost)`

This avoids obviously loss-making missing bundles, but still performs very poorly.

| Variant | In-Sample Revenue | OOS Revenue | Delta vs Restricted OOS |
| --- | ---: | ---: | ---: |
| `same_size_anchor_median_cost_floor` | 0.023883 | 0.066332 | -2.332700 |
| `same_size_anchor_mean_cost_floor` | 0.011614 | 0.028641 | -2.370391 |
| `same_size_anchor_min_cost_floor` | 0.008106 | 0.023661 | -2.375371 |
| `same_size_anchor_max_cost_floor` | 0.050751 | 0.022735 | -2.376297 |

Interpretation:

- cost floor avoids catastrophic negative profit
- but the repaired full menu is still much worse than the original restricted `FCP-MB` OOS replay
- same-size propagation is too coarse because bundles with the same size have very different implied economic roles under the fixed `FCP` anchors

## 4. Current Takeaway

The first Phase 3 probe suggests:

- strict `BSP`-compressed completion is too rigid and becomes infeasible
- coarse same-size copying is feasible but economically poor

So the next candidate repair should likely be:

- more structured than pure `BSP` size pricing
- but still much cheaper than full `2^N` bundle-price completion
