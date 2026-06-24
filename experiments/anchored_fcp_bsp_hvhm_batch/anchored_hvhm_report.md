# Anchored FCP+BSP hvhm Batch Report

## Aggregate OOS

| N | FCP | BSP | CPBSD-A | Anchored | Anchored-FCP | Anchored-BSP | Anchored-CPBSD-A |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | 2.278263 | 2.346959 | 2.847968 | 2.278263 | +0.000000 | -0.068696 | -0.569705 |
| 30 | 4.908230 | 8.046570 | 9.909867 | 4.908214 | -0.000016 | -3.138356 | -5.001653 |

## Per-Seed OOS

| N | Seed | FCP | BSP | CPBSD-A | Anchored | A-FCP | A-BSP | A-CPBSD-A | Anchored choice |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 10 | 20260413 | 2.200928 | 2.302281 | 2.809203 | 2.200928 | +0.000000 | -0.101353 | -0.608275 | fcp=3557 bsp=0 out=1443 |
| 10 | 20260414 | 2.349143 | 2.333674 | 2.830079 | 2.349143 | +0.000000 | +0.015470 | -0.480936 | fcp=3504 bsp=0 out=1496 |
| 10 | 20260415 | 2.203012 | 2.290547 | 2.910397 | 2.203012 | -0.000000 | -0.087535 | -0.707385 | fcp=3239 bsp=0 out=1761 |
| 10 | 20260416 | 2.326662 | 2.443840 | 2.863939 | 2.326662 | -0.000000 | -0.117177 | -0.537276 | fcp=3749 bsp=0 out=1251 |
| 10 | 20260417 | 2.311569 | 2.364456 | 2.826222 | 2.311569 | +0.000000 | -0.052886 | -0.514652 | fcp=3176 bsp=0 out=1824 |
| 30 | 20260413 | 5.776708 | 8.210544 | 10.017221 | 5.776627 | -0.000081 | -2.433917 | -4.240594 | fcp=3081 bsp=22 out=1897 |
| 30 | 20260414 | 4.756441 | 7.720661 | 9.819442 | 4.756441 | -0.000000 | -2.964219 | -5.063001 | fcp=2272 bsp=0 out=2728 |
| 30 | 20260415 | 4.832086 | 8.163392 | 9.676923 | 4.832086 | -0.000000 | -3.331306 | -4.844838 | fcp=2387 bsp=0 out=2613 |
| 30 | 20260416 | 5.022253 | 8.163436 | 10.095986 | 5.022253 | -0.000000 | -3.141183 | -5.073733 | fcp=2817 bsp=0 out=2183 |
| 30 | 20260417 | 4.153660 | 7.974817 | 9.939760 | 4.153660 | -0.000000 | -3.821157 | -5.786100 | fcp=2087 bsp=0 out=2913 |

## Diagnostic Seeds

### N=10 seed=20260415

- FCP outside but CPBSD-A buys: `972`
- Anchored captures among those customers: `0`
- Anchored outside among those customers: `972`
- Avg CPBSD-A profit on those customers: `3.331665`
- Avg Anchored best-BSP surplus on those customers: `0.000000`

### N=10 seed=20260413

- FCP outside but CPBSD-A buys: `614`
- Anchored captures among those customers: `0`
- Anchored outside among those customers: `614`
- Avg CPBSD-A profit on those customers: `3.112486`
- Avg Anchored best-BSP surplus on those customers: `0.000000`

### N=30 seed=20260417

- FCP outside but CPBSD-A buys: `2568`
- Anchored captures among those customers: `0`
- Anchored outside among those customers: `2568`
- Avg CPBSD-A profit on those customers: `10.313376`
- Avg Anchored best-BSP surplus on those customers: `0.000000`

### N=30 seed=20260416

- FCP outside but CPBSD-A buys: `1799`
- Anchored captures among those customers: `0`
- Anchored outside among those customers: `1799`
- Avg CPBSD-A profit on those customers: `10.489051`
- Avg Anchored best-BSP surplus on those customers: `0.000000`

