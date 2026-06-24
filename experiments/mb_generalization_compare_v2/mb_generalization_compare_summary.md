# MB Generalization Compare v2

- Setup: N=5, dist=normal, rho=0.0, heterogeneity=full, cost=hvhm
- Time limit: 300.0s
- Tie-breaking: equal surplus -> choose higher firm profit bundle

## Aggregate Summary

| K in-sample | Instances | Status | Runtime Mean (s) | Runtime Median (s) | Revenue In Mean | Revenue Out K=2000 Mean | Revenue Out K=5000 Mean | Gen Ratio 2000/In | Gen Ratio 5000/In |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 50 | 5 | OPTIMAL:4, TIME_LIMIT:1 | 116.59 | 76.31 | 1.6511 | 1.1430 | 1.1401 | 0.6962 | 0.6943 |
| 100 | 5 | TIME_LIMIT:5 | 300.03 | 300.02 | 1.4647 | 1.2161 | 1.2111 | 0.8327 | 0.8291 |
