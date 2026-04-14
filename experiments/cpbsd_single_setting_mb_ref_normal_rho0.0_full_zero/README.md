# CPBSD Single-Setting BSP-Reference Matrix

- Scope: `single_setting_mb_ref_matrix_v1`
- Setting: `dist=normal`, `rho=0.0`, `heterogeneity=full`, `cost=zero`
- N values: `5,10,20,30`
- In-sample K: `50`
- Out-of-sample K: `5000`
- Instances per N: `3`
- Time limits: `N<=10 -> 300.0s`, `N>=20 -> 600.0s`
- FCP threshold: `0.5`
- Full MB skip threshold: `N >= 20`

## Aggregate Summary

| N | Method | Instances | Status Counts | Runtime Mean (s) | Runtime Median (s) | Rev In Mean | Rev Out Mean | Ratio In vs BSP | Ratio Out vs BSP |
| --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 5 | BSP | 3 | OPTIMAL:3 | 0.17 | 0.19 | 25.0478 | 24.0889 | 1.0000 | 1.0000 |
| 5 | CPBSD-A | 3 | OPTIMAL:3 | 0.24 | 0.21 | 24.9356 | 24.0240 | 0.9956 | 0.9974 |
| 5 | CPBSD | 3 | OPTIMAL:3 | 2.21 | 2.03 | 25.0525 | 23.9143 | 1.0002 | 0.9931 |
| 5 | FCP-MB | 3 | OPTIMAL:3 | 0.22 | 0.20 | 25.3633 | 24.0557 | 1.0126 | 0.9988 |
| 5 | MB | 3 | OPTIMAL:3 | 1.07 | 1.04 | 25.4532 | 23.0404 | 1.0163 | 0.9560 |
| 10 | BSP | 3 | OPTIMAL:3 | 0.40 | 0.21 | 51.0995 | 48.7689 | 1.0000 | 1.0000 |
| 10 | CPBSD-A | 3 | OPTIMAL:3 | 2.97 | 0.37 | 50.6361 | 48.6758 | 0.9910 | 0.9981 |
| 10 | CPBSD | 3 | OPTIMAL:2, TIME_LIMIT:1 | 117.24 | 46.95 | 50.0215 | 47.8107 | 0.9792 | 0.9805 |
| 10 | FCP-MB | 3 | OPTIMAL:3 | 0.76 | 0.81 | 52.2537 | 48.4659 | 1.0226 | 0.9939 |
| 10 | MB | 3 | OPTIMAL:2, TIME_LIMIT:1 | 225.97 | 199.61 | 52.3237 | 46.5268 | 1.0240 | 0.9542 |
| 20 | BSP | 3 | OPTIMAL:3 | 0.72 | 0.52 | 102.2663 | 103.4272 | 1.0000 | 1.0000 |
| 20 | CPBSD-A | 3 | OPTIMAL:3 | 57.49 | 38.83 | 103.5943 | 103.2802 | 1.0131 | 0.9986 |
| 20 | CPBSD | 3 | TIME_LIMIT:3 | 600.04 | 600.05 | 101.6116 | 100.5762 | 0.9935 | 0.9725 |
| 20 | FCP-MB | 3 | OPTIMAL:3 | 8.55 | 6.40 | 105.2816 | 101.8030 | 1.0296 | 0.9843 |
| 20 | MB | 3 | SKIPPED_INTRACTABLE:3 | - | - | - | - | - | - |
| 30 | BSP | 3 | OPTIMAL:3 | 0.82 | 0.77 | 157.0940 | 152.8268 | 1.0000 | 1.0000 |
| 30 | CPBSD-A | 3 | OPTIMAL:3 | 51.40 | 54.37 | 158.9040 | 152.5125 | 1.0115 | 0.9979 |
| 30 | CPBSD | 3 | TIME_LIMIT:3 | 600.06 | 600.05 | 53.2865 | 56.2313 | 0.3406 | 0.3624 |
| 30 | FCP-MB | 3 | OPTIMAL:3 | 2.32 | 1.91 | 160.1016 | 151.1978 | 1.0191 | 0.9894 |
| 30 | MB | 3 | SKIPPED_INTRACTABLE:3 | - | - | - | - | - | - |

## Plots

- `/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/cpbsd_single_setting_mb_ref_normal_rho0.0_full_zero/plots/normal_rho0.0_full_zero/boxplot_ratio_vs_bsp_n5.png`
- `/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/cpbsd_single_setting_mb_ref_normal_rho0.0_full_zero/plots/normal_rho0.0_full_zero/boxplot_ratio_vs_bsp_n10.png`
- `/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/cpbsd_single_setting_mb_ref_normal_rho0.0_full_zero/plots/normal_rho0.0_full_zero/boxplot_ratio_vs_bsp_n20.png`
- `/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/cpbsd_single_setting_mb_ref_normal_rho0.0_full_zero/plots/normal_rho0.0_full_zero/boxplot_ratio_vs_bsp_n30.png`

## Notes

Full MB is intentionally skipped for larger N once the full bundle-space formulation becomes intractable.
For skipped settings, full MB revenue is unavailable, but BSP-reference ratios remain available for the other methods.
