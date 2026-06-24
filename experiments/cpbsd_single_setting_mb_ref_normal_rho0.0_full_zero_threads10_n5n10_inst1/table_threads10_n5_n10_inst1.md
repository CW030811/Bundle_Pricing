# Baseline Revenue and Runtime Tables

- Scope: `single_setting_mb_ref_matrix_v1`
- Setting: `dist=normal`, `rho=0.0`, `heterogeneity=full`, `cost=zero`
- Slice: `N = 5, 10`, `instance = 1`
- Gurobi setting: `Threads = 10`
- Source: `runtime_summary.csv`
- Aggregation: mean over 1 instance for each `N` and baseline
- Bold indicates the best baseline in that column: highest `Revenue In`, highest `Revenue Out`, or shortest `Runtime Mean (s)`

## N = 5

| Baseline | Revenue In | Revenue Out | Runtime Mean (s) |
| --- | ---: | ---: | ---: |
| BSP | 25.5998 | 23.0337 | 1.03 |
| CPBSD-A | 25.5998 | 23.1012 | 2.26 |
| CPBSD | 25.5171 | 23.1983 | 9.29 |
| FCP-MB | 25.8797 | **23.2094** | **0.72** |
| MB | **25.8797** | 21.4255 | 5.81 |

## N = 10

| Baseline | Revenue In | Revenue Out | Runtime Mean (s) |
| --- | ---: | ---: | ---: |
| BSP | 51.5974 | **49.1775** | **0.70** |
| CPBSD-A | 50.2080 | 48.8659 | 1.56 |
| CPBSD | 47.9360 | 46.3746 | 221.93 |
| FCP-MB | **52.8006** | 46.6375 | 4.17 |
| MB | 1.1940 | 0.1194 | 300.87 |

## Note

`N = 10` 下 `MB` 命中 `TIME_LIMIT`，因此虽然表格仍按同一口径展示其 revenue / runtime，但该行结果应按超时解理解。
