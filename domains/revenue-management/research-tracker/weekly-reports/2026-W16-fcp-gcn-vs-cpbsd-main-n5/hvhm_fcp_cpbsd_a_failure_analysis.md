Stage 1：

- 独立运行 FCP solver。
- 得到 FCP anchor bundles \(A_i\)。
- 得到固定价格 \(p_i^\star\)。
- 得到每个 in-sample customer 在 Stage 1 的 FCP choice，用于FCP sales protection。

Stage 2：

- 固定所有 \(p_i^\star\)，不再优化 FCP 价格。
- 新增 BSP size prices \(q_s\)。
- 在 fixed FCP menu + BSP size menu 上重新建 combined choice / IC 模型。
- 加 BSP 内部价格约束和 cross-menu anti-arbitrage 约束。
- 加入in-sample FCP sales protection，避免 BSP 在 Stage 2 中 影响 Stage-1 FCP buyers。
$$
V^F_{k,i(k)}-p_{i(k)}^\star
\ge
V^B_{ks}-q_s
\qquad \forall k\in\mathcal{G},\ s\in\mathcal{S}.
$$

| N | FCP | BSP | CPBSD-A | Anchored strict | Anchored-FCP | Anchored-BSP | Anchored-CPBSD-A |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | 2.278263 | 2.346959 | 2.847968 | 2.278263 | +0.000000 | -0.068696 | -0.569705 |
| 30 | 4.908230 | 8.046570 | 9.909867 | 4.908214 | -0.000016 | -3.138356 | -5.001653 |

# N=10 hvhm 


| N | seed | FCP OOS | Anchored FCP+BSP OOS | CPBSD-A OOS | FCP+CPBSD-A OOS | hybrid - CPBSD-A |
| --- | --- | --- | --- | --- | --- | --- |
| 10 | 20260413 | 2.200928 | 2.200928 | 2.809203 | 2.739936 | -0.069267 |


1. **FCP+BSP 的 BSP 二阶段价格高**：`c10_same_size` 和 `c11_cross_split` 把 `q_s` 拉的过高。
2. **hvhm天然适合 CPBSD-A**：hvhm 的 cost 与 valuation mean 强相关，CPBSD-A 的 component prices 学成近似 `c_n + constant margin`


### FCP Stage-1 Solution


Top in-sample FCP bundles by buyer count:

| bundle idx | size | price | cost | margin | in buyers | priced | bitmask |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 20 | 8 | 47.9751 | 44.6222 | 3.3528 | 13 | yes | 0111101111 |
| 30 | 8 | 46.3144 | 42.7111 | 3.6032 | 5 | yes | 1110011111 |
| 21 | 9 | 54.4063 | 50.2000 | 4.2063 | 3 | yes | 0111111111 |
| 28 | 9 | 53.0668 | 48.2889 | 4.7780 | 3 | yes | 1101111111 |
| 6 | 8 | 51.7192 | 47.4889 | 4.2303 | 3 | yes | 0101111111 |
| 3 | 7 | 47.6976 | 43.8222 | 3.8754 | 2 | yes | 0100111111 |
| 33 | 10 | 55.7619 | 51.0000 | 4.7619 | 2 | yes | 1111111111 |
| 15 | 8 | 50.6769 | 46.5333 | 4.1435 | 1 | yes | 0110111111 |
| 31 | 9 | 51.8209 | 47.3333 | 4.4876 | 1 | yes | 1110111111 |
| 32 | 8 | 43.3315 | 38.8889 | 4.4426 | 1 | yes | 1111100111 |
| 17 | 4 | 18.8876 | 16.5778 | 2.3098 | 1 | yes | 0111000010 |
| 14 | 7 | 44.6049 | 40.9556 | 3.6493 | 1 | yes | 0110101111 |

FCP in-sample profit by channel:

| channel | count | share | avg profit | profit/K | p25 | p50 | p75 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| fcp | 45 | 0.9000 | 3.6061 | 3.2455 | 3.3528 | 3.6032 | 4.2063 |
| outside | 5 | 0.1000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |

FCP OOS profit by channel:

| channel | count | share | avg profit | profit/K | p25 | p50 | p75 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| fcp | 3557 | 0.7114 | 3.0938 | 2.2009 | 3.3528 | 3.3528 | 3.6032 |
| outside | 1443 | 0.2886 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |

### Stage-2 BSP / Anchored BSP Solution

Pure BSP size prices:

| size | q_s |
| --- | --- |
| 0 | 0.0000 |
| 1 | 10.0614 |
| 2 | 19.7136 |
| 3 | 27.4761 |
| 4 | 34.5331 |
| 5 | 40.3916 |
| 6 | 45.4772 |
| 7 | 49.1914 |
| 8 | 52.2797 |
| 9 | 53.9664 |
| 10 | 54.9925 |

Anchored FCP+BSP strict size prices:

| size | q_s |
| --- | --- |
| 0 | 0.0000 |
| 1 | 29.0463 |
| 2 | 29.9215 |
| 3 | 46.8449 |
| 4 | 46.8449 |
| 5 | 54.4063 |
| 6 | 54.4063 |
| 7 | 55.7619 |
| 8 | 58.0927 |
| 9 | 84.2056 |
| 10 | 85.6833 |

Anchored price lower-bound diagnosis:


| s | actual q_s | min feasible q_s | dominant hard source | exact witness |
| --- | --- | --- | --- | --- |
| 1 | 29.0463 | 28.4438 | c11_cross_split | parent 24 price 32.1615 - child 23 price 3.7177 |
| 2 | 29.9215 | 29.9215 | c11_cross_split | parent 24 price 32.1615 - child 1 price 2.2400 |
| 3 | 46.8449 | 40.9513 | c11_cross_split | parent 10 price 46.8449 - child 7 price 5.8936 |
| 4 | 46.8449 | 44.6049 | c11_cross_split | parent 10 price 46.8449 - child 1 price 2.2400 |
| 5 | 54.4063 | 46.8449 | c10_same_size | bundle 10 size 5 price 46.8449 |
| 6 | 54.4063 | 51.7192 | c11_cross_split | parent 5 price 53.9592 - child 1 price 2.2400 |
| 7 | 55.7619 | 53.9592 | c10_same_size | bundle 5 size 7 price 53.9592 |
| 8 | 58.0927 | 53.9592 | c8_monotonicity | q_8 >= q_7; inherited from c10_same_size |
| 9 | 84.2056 | 54.4063 | c10_same_size | bundle 21 size 9 price 54.4063 |
| 10 | 85.6833 | 55.7619 | c10_same_size | bundle 33 size 10 price 55.7619 |

Anchored FCP+BSP OOS profit by channel:

| channel | count | share | avg profit | profit/K | p25 | p50 | p75 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| fcp | 3557 | 0.7114 | 3.0938 | 2.2009 | 3.3528 | 3.3528 | 3.6032 |
| outside | 1443 | 0.2886 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |

### CPBSD-A Solution

**component prices p_n**

```text
0:2.0402, 1:3.0006, 2:3.9581, 3:4.9147, 4:5.8713, 5:6.8252, 6:7.7779, 7:8.7358, 8:9.7164, 9:10.6546
```
**size discounts d_s**

```text
0:0.0000, 1:0.0000, 2:0.1636, 3:0.3008, 4:0.4661, 5:0.5387, 6:0.6104, 7:0.6909, 8:0.7331, 9:0.8263
10:0.8439
```

CPBSD-A OOS profit by channel:

| channel | count | share | avg profit | profit/K | p25 | p50 | p75 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| cpbsd_a | 3894 | 0.7788 | 3.6071 | 2.8092 | 3.8032 | 3.8107 | 3.8175 |
| outside | 1106 | 0.2212 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |

### hvhm Cost-Structure Diagnosis

In this setup, product cost is strongly aligned with valuation means. CPBSD-A 的定价几乎是一个固定的profit结构 `p_n - c_n`

| product | cost c_n | valuation mean | CPBSD-A raw margin p_n-c_n |
| --- | --- | --- | --- |
| 0 | 0.8000 | 1.0000 | 1.2402 |
| 1 | 1.7556 | 2.0000 | 1.2450 |
| 2 | 2.7111 | 3.0000 | 1.2470 |
| 3 | 3.6667 | 4.0000 | 1.2480 |
| 4 | 4.6222 | 5.0000 | 1.2491 |
| 5 | 5.5778 | 6.0000 | 1.2474 |
| 6 | 6.5333 | 7.0000 | 1.2445 |
| 7 | 7.4889 | 8.0000 | 1.2469 |
| 8 | 8.4444 | 9.0000 | 1.2720 |
| 9 | 9.4000 | 10.0000 | 1.2546 |
