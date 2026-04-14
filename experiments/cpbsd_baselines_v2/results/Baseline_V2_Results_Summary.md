# CPBSD Baselines V2 — 求解结果汇总

**实验范围**: smoke_subset_v2
**参数设置**: normal distribution, rho=0.0, full heterogeneity, hvhm cost
**Out-of-sample K**: 5000 (seed+99991)

---

## 表1: 简明表 (Revenue Ratio vs BSP + Running Time)

### N=5 (K=50, time_limit=300s, 4个求解器)

| Instance | Method | Rev-In/BSP | Rev-Out/BSP | Drop% | Runtime(s) | Status |
|----------|--------|-----------|-------------|-------|------------|--------|
| inst001 | CPBSD-MILP | 1.145 | 1.150 | 22.3% | 300.0 | TIME_LIMIT |
| inst001 | CPBSD-A | 1.159 | 1.209 | 19.3% | 24.9 | OPTIMAL |
| inst001 | BSP | 1.000 | 1.000 | 22.6% | 0.7 | OPTIMAL |
| inst001 | MB | 1.322 | 1.092 | 36.1% | 245.6 | OPTIMAL |
| | | | | | | |
| inst002 | CPBSD-MILP | 1.228 | 1.112 | 8.1% | 300.0 | TIME_LIMIT |
| inst002 | CPBSD-A | 1.244 | 1.160 | 5.3% | 7.8 | OPTIMAL |
| inst002 | BSP | 1.000 | 1.000 | -1.5% | 1.0 | OPTIMAL |
| inst002 | MB | 1.451 | 1.014 | 29.0% | 231.5 | OPTIMAL |
| | | | | | | |
| inst003 | CPBSD-MILP | 1.100 | 1.118 | 12.1% | 300.0 | TIME_LIMIT |
| inst003 | CPBSD-A | 1.094 | 1.119 | 11.5% | 8.2 | OPTIMAL |
| inst003 | BSP | 1.000 | 1.000 | 13.5% | 1.0 | OPTIMAL |
| inst003 | MB | 1.222 | 1.063 | 24.7% | 214.2 | OPTIMAL |
| | | | | | | |
| inst004 | CPBSD-MILP | 1.159 | 1.050 | 7.2% | 300.0 | TIME_LIMIT |
| inst004 | CPBSD-A | 1.134 | 1.091 | 4.8% | 15.0 | OPTIMAL |
| inst004 | BSP | 1.000 | 1.000 | -2.4% | 0.9 | OPTIMAL |
| inst004 | MB | 1.364 | 1.004 | 24.6% | 300.0 | TIME_LIMIT |
| | | | | | | |
| inst005 | CPBSD-MILP | 1.205 | 1.175 | 11.5% | 300.0 | TIME_LIMIT |
| inst005 | CPBSD-A | 1.129 | 1.198 | 3.7% | 26.2 | OPTIMAL |
| inst005 | BSP | 1.000 | 1.000 | 9.3% | 1.3 | OPTIMAL |
| inst005 | MB | 1.357 | 1.126 | 24.8% | 300.1 | TIME_LIMIT |

**N=5 均值汇总:**

| Method | Mean Rev-In/BSP | Mean Rev-Out/BSP | Mean Drop% | Mean Runtime(s) |
|--------|----------------|-----------------|------------|-----------------|
| CPBSD-MILP | 1.167 | 1.121 | 12.2% | 300.0 |
| CPBSD-A | 1.152 | 1.155 | 8.9% | 16.4 |
| BSP | 1.000 | 1.000 | 8.3% | 1.0 |
| MB | 1.343 | 1.060 | 27.8% | 258.3 |

### N=10 (K=100, time_limit=300s, 2个求解器)

| Instance | Method | Rev-In/BSP | Rev-Out/BSP | Drop% | Runtime(s) | Status |
|----------|--------|-----------|-------------|-------|------------|--------|
| inst001 | CPBSD-A | 1.131 | 1.233 | 8.9% | 300.0 | TIME_LIMIT |
| inst001 | BSP | 1.000 | 1.000 | 16.4% | 192.2 | OPTIMAL |
| | | | | | | |
| inst002 | CPBSD-A | 1.192 | 1.206 | 2.9% | 300.0 | TIME_LIMIT |
| inst002 | BSP | 1.000 | 1.000 | 4.1% | 198.5 | OPTIMAL |
| | | | | | | |
| inst003 | CPBSD-A | 1.059 | 1.030 | 10.5% | 300.0 | TIME_LIMIT |
| inst003 | BSP | 1.000 | 1.000 | 7.9% | 143.4 | OPTIMAL |
| | | | | | | |
| inst004 | CPBSD-A | 1.082 | 1.183 | 2.3% | 300.0 | TIME_LIMIT |
| inst004 | BSP | 1.000 | 1.000 | 10.6% | 141.5 | OPTIMAL |
| | | | | | | |
| inst005 | CPBSD-A | 1.219 | 1.196 | 6.1% | 300.0 | TIME_LIMIT |
| inst005 | BSP | 1.000 | 1.000 | 4.4% | 216.2 | OPTIMAL |

**N=10 均值汇总:**

| Method | Mean Rev-In/BSP | Mean Rev-Out/BSP | Mean Drop% | Mean Runtime(s) |
|--------|----------------|-----------------|------------|-----------------|
| CPBSD-A | 1.137 | 1.170 | 6.1% | 300.0 |
| BSP | 1.000 | 1.000 | 8.7% | 178.4 |

---

## 表2: 完整表 (所有字段)

### N=5 (K=50, time_limit=300s)

| Instance | Seed | Method | Status | MIP Gap | Obj Raw | Rev-In | Rev-Out | Rev-In/BSP | Rev-Out/BSP | Drop% | Runtime(s) | Wall(s) | Nodes | Policy Scope | #Price Full | #Price Sel | Cache |
|----------|------|--------|--------|---------|---------|--------|---------|-----------|-------------|-------|------------|---------|-------|-------------|-------------|------------|-------|
| inst001 | 20260304 | CPBSD-MILP | TIME_LIMIT | 9.60% | 1.6528 | 1.5395 | 1.1969 | 1.145 | 1.150 | 22.3% | 300.05 | 300.07 | 32606 | — | — | — | Yes |
| inst001 | 20260304 | CPBSD-A | OPTIMAL | 0.00% | 1.6037 | 1.5585 | 1.2575 | 1.159 | 1.209 | 19.3% | 24.89 | 24.89 | 70097 | — | — | — | Yes |
| inst001 | 20260304 | BSP | OPTIMAL | 0.37% | 1.4371 | 1.3445 | 1.0405 | 1.000 | 1.000 | 22.6% | 0.70 | 0.71 | — | — | — | — | Yes |
| inst001 | 20260304 | MB | OPTIMAL | 0.97% | 1.7769 | 1.7769 | 1.1362 | 1.322 | 1.092 | 36.1% | 245.65 | 245.65 | — | full_bundle_prices | 32 | 17 | No |
| inst002 | 20260305 | CPBSD-MILP | TIME_LIMIT | 8.43% | 1.4751 | 1.3341 | 1.2264 | 1.228 | 1.112 | 8.1% | 300.02 | 300.02 | 33233 | — | — | — | Yes |
| inst002 | 20260305 | CPBSD-A | OPTIMAL | 0.00% | 1.4061 | 1.3508 | 1.2792 | 1.244 | 1.160 | 5.3% | 7.84 | 7.84 | 14794 | — | — | — | Yes |
| inst002 | 20260305 | BSP | OPTIMAL | 0.83% | 1.1784 | 1.0860 | 1.1027 | 1.000 | 1.000 | -1.5% | 1.00 | 1.00 | — | — | — | — | Yes |
| inst002 | 20260305 | MB | OPTIMAL | 1.00% | 1.5758 | 1.5758 | 1.1185 | 1.451 | 1.014 | 29.0% | 231.48 | 231.48 | — | full_bundle_prices | 32 | 19 | No |
| inst003 | 20260306 | CPBSD-MILP | TIME_LIMIT | 6.48% | 1.5421 | 1.4627 | 1.2863 | 1.100 | 1.118 | 12.1% | 300.01 | 300.01 | 33410 | — | — | — | Yes |
| inst003 | 20260306 | CPBSD-A | OPTIMAL | 0.00% | 1.5259 | 1.4553 | 1.2884 | 1.094 | 1.119 | 11.5% | 8.20 | 8.20 | 22580 | — | — | — | Yes |
| inst003 | 20260306 | BSP | OPTIMAL | 0.98% | 1.3972 | 1.3300 | 1.1510 | 1.000 | 1.000 | 13.5% | 0.99 | 0.99 | — | — | — | — | Yes |
| inst003 | 20260306 | MB | OPTIMAL | 0.93% | 1.6331 | 1.6246 | 1.2233 | 1.222 | 1.063 | 24.7% | 214.20 | 214.20 | — | full_bundle_prices | 32 | 18 | No |
| inst004 | 20260307 | CPBSD-MILP | TIME_LIMIT | 7.09% | 1.4429 | 1.2904 | 1.1977 | 1.159 | 1.050 | 7.2% | 300.02 | 300.02 | 33307 | — | — | — | Yes |
| inst004 | 20260307 | CPBSD-A | OPTIMAL | 0.00% | 1.3628 | 1.2621 | 1.2437 | 1.134 | 1.091 | 4.8% | 15.04 | 15.04 | 37308 | — | — | — | Yes |
| inst004 | 20260307 | BSP | OPTIMAL | 0.98% | 1.2332 | 1.1129 | 1.1400 | 1.000 | 1.000 | -2.4% | 0.87 | 0.87 | — | — | — | — | Yes |
| inst004 | 20260307 | MB | TIME_LIMIT | 1.06% | 1.5178 | 1.5178 | 1.1444 | 1.364 | 1.004 | 24.6% | 300.02 | 300.02 | — | full_bundle_prices | 32 | 21 | No |
| inst005 | 20260308 | CPBSD-MILP | TIME_LIMIT | 13.73% | 1.4431 | 1.3885 | 1.2285 | 1.205 | 1.175 | 11.5% | 300.02 | 300.02 | 33030 | — | — | — | Yes |
| inst005 | 20260308 | CPBSD-A | OPTIMAL | 0.79% | 1.3928 | 1.3013 | 1.2529 | 1.129 | 1.198 | 3.7% | 26.23 | 26.23 | 71466 | — | — | — | Yes |
| inst005 | 20260308 | BSP | OPTIMAL | 0.73% | 1.2927 | 1.1527 | 1.0454 | 1.000 | 1.000 | 9.3% | 1.28 | 1.28 | — | — | — | — | Yes |
| inst005 | 20260308 | MB | TIME_LIMIT | 3.77% | 1.5647 | 1.5647 | 1.1768 | 1.357 | 1.126 | 24.8% | 300.07 | 300.07 | — | full_bundle_prices | 32 | 18 | No |

### N=10 (K=100, time_limit=300s)

| Instance | Seed | Method | Status | MIP Gap | Obj Raw | Rev-In | Rev-Out | Rev-In/BSP | Rev-Out/BSP | Drop% | Runtime(s) | Wall(s) | Nodes |
|----------|------|--------|--------|---------|---------|--------|---------|-----------|-------------|-------|------------|---------|-------|
| inst001 | 20261310 | CPBSD-A | TIME_LIMIT | 27.05% | 3.2097 | 3.1742 | 2.8910 | 1.131 | 1.233 | 8.9% | 300.01 | 300.01 | 59157 |
| inst001 | 20261310 | BSP | OPTIMAL | 0.86% | 2.8899 | 2.8061 | 2.3446 | 1.000 | 1.000 | 16.4% | 192.21 | 192.21 | — |
| inst002 | 20261311 | CPBSD-A | TIME_LIMIT | 41.39% | 2.9433 | 2.9370 | 2.8510 | 1.192 | 1.206 | 2.9% | 300.01 | 300.01 | 55974 |
| inst002 | 20261311 | BSP | OPTIMAL | 0.95% | 2.5913 | 2.4642 | 2.3641 | 1.000 | 1.000 | 4.1% | 198.50 | 198.51 | — |
| inst003 | 20261312 | CPBSD-A | TIME_LIMIT | 39.48% | 2.9091 | 2.7492 | 2.4618 | 1.059 | 1.030 | 10.5% | 300.01 | 300.01 | 41244 |
| inst003 | 20261312 | BSP | OPTIMAL | 0.80% | 2.7229 | 2.5951 | 2.3899 | 1.000 | 1.000 | 7.9% | 143.43 | 143.44 | — |
| inst004 | 20261313 | CPBSD-A | TIME_LIMIT | 37.12% | 2.9497 | 2.7894 | 2.7261 | 1.082 | 1.183 | 2.3% | 300.02 | 300.02 | 55645 |
| inst004 | 20261313 | BSP | OPTIMAL | 0.91% | 2.6961 | 2.5772 | 2.3049 | 1.000 | 1.000 | 10.6% | 141.53 | 141.53 | — |
| inst005 | 20261314 | CPBSD-A | TIME_LIMIT | 32.76% | 3.0553 | 3.0498 | 2.8626 | 1.219 | 1.196 | 6.1% | 300.01 | 300.01 | 44506 |
| inst005 | 20261314 | BSP | OPTIMAL | 0.89% | 2.6406 | 2.5021 | 2.3931 | 1.000 | 1.000 | 4.4% | 216.15 | 216.15 | — |

---

## 结果文件路径

```
experiments/cpbsd_baselines_v2/results/
├── baseline_cpbsd_milp_n5_inst001.json ... inst005.json   (5 files)
├── baseline_cpbsd_a_n5_inst001.json    ... inst005.json   (5 files)
├── baseline_cpbsd_a_n10_inst001.json   ... inst005.json   (5 files)
├── baseline_bsp_n5_inst001.json        ... inst005.json   (5 files)
├── baseline_bsp_n10_inst001.json       ... inst005.json   (5 files)
└── baseline_mb_n5_inst001.json         ... inst005.json   (5 files)
                                                     共 30 个 JSON 文件
```

## 注释

- **Drop%** = `100 × (1 - Rev-Out / Rev-In)`, 衡量in→out过拟合程度
- **Rev-In/BSP**, **Rev-Out/BSP**: 以同instance BSP revenue为分母的比值
- **Status**: OPTIMAL=在gap内求解完成, TIME_LIMIT=达到时间上限后返回最优可行解
- **MIP Gap**: 最优解与best bound的相对差距, 越小越好
- **#Price Full / #Price Sel**: 仅MB有, full=所有2^N个bundle, sel=被选择的bundle数
- **Cache**: Yes=使用缓存结果, No=本次新求解
- **N=10不含CPBSD-MILP和MB**: MILP随N指数增长不可行, MB的2^10=1024变量在300s内无法求解
