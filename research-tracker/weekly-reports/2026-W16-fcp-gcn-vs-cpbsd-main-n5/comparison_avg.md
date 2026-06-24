# Phase 2 Average Comparison

Scope:

- batch: `fcp_mb_phase2_selected_n10_n30_5inst`
- methods: `BSP`, `CPBSD-A`, `FCP-pruned-MB`
- matched seeds: `20260413` to `20260417`
- setting-size pairs: `8`
- result root: [fcp_mb_phase2_selected_n10_n30_5inst](/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/fcp_mb_phase2_selected_n10_n30_5inst)
- verified finish time: `2026-04-14 01:02:46`

Important scope note:

- this batch did **not** include `CPBSD` / `CPBSD-MILP`

## Detailed Average Table

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

## Metric Winners By Setting

| N | Setting | Best Rev In | Best Rev OOS | Best Runtime | FCP Verdict |
| ---: | --- | --- | --- | --- | --- |
| 10 | `logit_rho0.0_full_hvhm` | `FCP-pruned-MB` | `CPBSD-A` | `BSP` | in-sample win only |
| 10 | `normal_rho0.0_full_hvhm` | `FCP-pruned-MB` | `CPBSD-A` | `BSP` | in-sample win only |
| 10 | `normal_rho0.0_full_zero` | `FCP-pruned-MB` | `BSP` | `BSP` | in-sample win only |
| 10 | `normal_rho0.5_full_hvhm` | `FCP-pruned-MB` | `CPBSD-A` | `BSP` | in-sample win only |
| 30 | `logit_rho0.0_full_hvhm` | `FCP-pruned-MB` | `CPBSD-A` | `BSP` | in-sample win only |
| 30 | `normal_rho0.0_full_hvhm` | `FCP-pruned-MB` | `CPBSD-A` | `FCP-pruned-MB` | revenue/runtime trade-off, OOS blocker |
| 30 | `normal_rho0.0_full_zero` | `CPBSD-A` | `BSP` | `BSP` | loses both revenue metrics |
| 30 | `normal_rho0.5_full_hvhm` | `FCP-pruned-MB` | `CPBSD-A` | `FCP-pruned-MB` | revenue/runtime trade-off, OOS blocker |

## Quick Read

- No `N x setting` pair gives `FCP-pruned-MB` full three-metric dominance over both baselines.
- `FCP-pruned-MB` wins average in-sample revenue in `7/8` executed pairs and loses only at `N=30, normal_rho0.0_full_zero`.
- `FCP-pruned-MB` wins average OOS revenue in `0/8` executed pairs. The blocker is consistently `Revenue OOS`.
- The strongest showcase candidates are `N=30, normal_rho0.5_full_hvhm` and `N=30, normal_rho0.0_full_hvhm`: both give `FCP-pruned-MB` the best in-sample revenue and the best runtime, but OOS remains materially below both `BSP` and `CPBSD-A`.
