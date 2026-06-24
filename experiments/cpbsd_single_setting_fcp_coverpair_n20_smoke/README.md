# CPBSD Single-Setting MB-Reference Matrix

- Scope: `single_setting_mb_ref_matrix_v1`
- Setting: `dist=normal`, `rho=0.0`, `heterogeneity=full`, `cost=zero`
- N values: `20`
- In-sample K: `50`
- Out-of-sample K: `5000`
- Instances per N: `1`
- Time limits: `N<=10 -> 5.0s`, `N>=20 -> 5.0s`
- FCP threshold: `0.5`
- Full MB skip threshold: `N >= 20`

## Aggregate Summary

| N | Method | Instances | Status Counts | Runtime Mean (s) | Runtime Median (s) | Rev In Mean | Rev Out Mean | Ratio In vs MB | Ratio Out vs MB |
| --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 20 | CPBSD-A | 1 | TIME_LIMIT:1 | 5.00 | 5.00 | 104.7420 | 103.3701 | - | - |
| 20 | CPBSD | 1 | TIME_LIMIT:1 | 5.01 | 5.01 | 0.0000 | 0.2768 | - | - |
| 20 | FCP-MB | 1 | TIME_LIMIT:1 | 5.01 | 5.01 | 105.3401 | 101.6292 | - | - |
| 20 | MB | 1 | SKIPPED_INTRACTABLE:1 | - | - | - | - | - | - |

## Plots

- `/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/cpbsd_single_setting_fcp_coverpair_n20_smoke/plots/normal_rho0.0_full_zero/boxplot_ratio_vs_mb_n20.png`

## Notes

Full MB is intentionally skipped for larger N once the full bundle-space formulation becomes intractable.
For skipped settings, MB-reference ratios are unavailable and the corresponding plot is a diagnostic placeholder.
