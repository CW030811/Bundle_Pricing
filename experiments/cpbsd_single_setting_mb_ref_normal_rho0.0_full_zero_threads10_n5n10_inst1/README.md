# CPBSD Single-Setting BSP-Reference Matrix

- Scope: `single_setting_mb_ref_matrix_v1`
- Setting: `dist=normal`, `rho=0.0`, `heterogeneity=full`, `cost=zero`
- N values: `5,10`
- In-sample K: `50`
- Out-of-sample K: `5000`
- Instances per N: `1`
- Time limits: `N<=10 -> 300.0s`, `N>=20 -> 600.0s`
- FCP threshold: `0.5`
- Full MB skip threshold: `N >= 20`

## Aggregate Summary

| N | Method | Instances | Status Counts | Runtime Mean (s) | Runtime Median (s) | Rev In Mean | Rev Out Mean | Ratio In vs BSP | Ratio Out vs BSP |
| --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 5 | BSP | 1 | OPTIMAL:1 | 1.03 | 1.03 | 25.5998 | 23.0337 | 1.0000 | 1.0000 |
| 5 | CPBSD-A | 1 | OPTIMAL:1 | 2.26 | 2.26 | 25.5998 | 23.1012 | 1.0000 | 1.0029 |
| 5 | CPBSD | 1 | OPTIMAL:1 | 9.29 | 9.29 | 25.5171 | 23.1983 | 0.9968 | 1.0071 |
| 5 | FCP-MB | 1 | OPTIMAL:1 | 0.72 | 0.72 | 25.8797 | 23.2094 | 1.0109 | 1.0076 |
| 5 | MB | 1 | OPTIMAL:1 | 5.81 | 5.81 | 25.8797 | 21.4255 | 1.0109 | 0.9302 |
| 10 | BSP | 1 | OPTIMAL:1 | 0.70 | 0.70 | 51.5974 | 49.1775 | 1.0000 | 1.0000 |
| 10 | CPBSD-A | 1 | OPTIMAL:1 | 1.56 | 1.56 | 50.2080 | 48.8659 | 0.9731 | 0.9937 |
| 10 | CPBSD | 1 | OPTIMAL:1 | 221.93 | 221.93 | 47.9360 | 46.3746 | 0.9290 | 0.9430 |
| 10 | FCP-MB | 1 | OPTIMAL:1 | 4.17 | 4.17 | 52.8006 | 46.6375 | 1.0233 | 0.9483 |
| 10 | MB | 1 | TIME_LIMIT:1 | 300.87 | 300.87 | 1.1940 | 0.1194 | 0.0231 | 0.0024 |

## Plots

- `/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/cpbsd_single_setting_mb_ref_normal_rho0.0_full_zero_threads10_n5n10_inst1/plots/normal_rho0.0_full_zero/boxplot_ratio_vs_bsp_n5.png`
- `/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/cpbsd_single_setting_mb_ref_normal_rho0.0_full_zero_threads10_n5n10_inst1/plots/normal_rho0.0_full_zero/boxplot_ratio_vs_bsp_n10.png`
