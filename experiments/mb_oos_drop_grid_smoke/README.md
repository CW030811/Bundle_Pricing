# MB Out-of-Sample Drop Grid Scan

- Scope: `mb_oos_drop_grid_n5_n10_v1`
- N values: `5`
- Instance per setting: `001`
- In-sample K: `50`
- Out-of-sample K: `5000`
- Time limit: `5.0s`
- MIP gap target: `0.01`
- Workers: `1`

## N=5

| Dist | rho | Hetero | Cost | Status | Runtime Mean (s) | Out/In Ratio | Drop |
| --- | ---: | --- | --- | --- | ---: | ---: | ---: |
| normal | 0.0 | full | hvhm | TIME_LIMIT:1 | 5.01 | 0.7394 | 0.2606 |
| normal | 0.0 | full | zero | OPTIMAL:1 | 0.76 | 0.9633 | 0.0367 |
