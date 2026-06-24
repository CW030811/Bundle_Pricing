# CPBSD Single-Setting MB-Reference Matrix

- Scope: `single_setting_mb_ref_matrix_v1`
- Setting: `dist=normal`, `rho=0.0`, `heterogeneity=full`, `cost=zero`
- N values: `5`
- In-sample K: `50`
- Out-of-sample K: `5000`
- Instances per N: `1`
- Time limits: `N<=10 -> 20.0s`, `N>=20 -> 20.0s`
- FCP threshold: `0.5`

## Aggregate Summary

| N | Method | Instances | Status Counts | Runtime Mean (s) | Runtime Median (s) | Rev In Mean | Rev Out Mean | Ratio In vs MB | Ratio Out vs MB |
| --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 5 | CPBSD-A | 1 | OPTIMAL:1 | 0.39 | 0.39 | 25.5998 | 23.1012 | 0.9892 | 1.0782 |
| 5 | CPBSD | 1 | OPTIMAL:1 | 2.05 | 2.05 | 25.5171 | 23.1983 | 0.9860 | 1.0827 |
| 5 | FCP-MB | 1 | OPTIMAL:1 | 0.17 | 0.17 | 25.8797 | 23.2094 | 1.0000 | 1.0833 |
| 5 | MB | 1 | OPTIMAL:1 | 1.01 | 1.01 | 25.8797 | 21.4255 | 1.0000 | 1.0000 |

## Plots

- `/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/cpbsd_single_setting_mb_ref_normal_rho0.0_full_zero_smoke/plots/normal_rho0.0_full_zero/boxplot_ratio_vs_mb_n5.png`
