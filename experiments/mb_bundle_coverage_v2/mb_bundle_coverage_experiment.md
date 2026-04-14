# MB Bundle Customer Coverage Experiment

## Objective

Analyze the distribution of customer demand across bundles in MB (Mixed Bundling)
solver optimal solutions. Determine whether a small number of bundles covers
most customer demand.

## Data Source

- Result directory: `/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/mb_bundle_coverage_v2/results`
- Instances processed: 27
- Instances skipped: 0
- Products per instance (N): 5
- Total bundle space: 2^5 = 32 bundles
- Total customers pooled: 1350

## Coverage Definition

- **Customer coverage** = proportion of customers (across all pooled instances)
  who chose a given bundle in the MB optimal solution.
- The MB solver uses **uniform customer weights** (1/K per customer),
  so count-based proportion equals the Ns-weighted version.
  (See `solve_mb_bsp_on_cpbsd_v2.py` line 182: `weights = np.ones(...) / k_count`)
- Bundles are ranked by coverage in descending order.
- `cumulative_customer_share` = running sum of `customer_share` in rank order.

## Key Results

- Unique bundles selected (across all instances): 32
- Bundle space utilization: 32/32 (100.0%)

### Top-N Cumulative Coverage

| Top-N | Cumulative Coverage |
|-------|-------------------|
| 1 | 36.44% |
| 2 | 49.26% |
| 3 | 53.41% |
| 5 | 60.74% |
| 10 | 74.15% |
| 15 | 83.41% |
| 20 | 90.30% |
| 25 | 95.33% |
| 30 | 99.04% |

### Coverage Thresholds

| Coverage | Bundles Needed |
|----------|---------------|
| 50% | 3 |
| 80% | 13 |
| 90% | 20 |
| 95% | 25 |
| 99% | 30 |
| 100% | 32 |

## Top-20 Bundles Detail

| Rank | Bundle ID | Binary | Size | Count | Share | Cumulative | Avg Price |
|------|-----------|--------|------|-------|-------|------------|-----------|
| 1 | 0 | 00000 | 0 | 492 | 36.44% | 36.44% | 0.00 |
| 2 | 31 | 11111 | 5 | 173 | 12.81% | 49.26% | 23.18 |
| 3 | 16 | 10000 | 1 | 56 | 4.15% | 53.41% | 2.17 |
| 4 | 24 | 11000 | 2 | 55 | 4.07% | 57.48% | 5.71 |
| 5 | 27 | 11011 | 4 | 44 | 3.26% | 60.74% | 21.04 |
| 6 | 20 | 10100 | 2 | 44 | 3.26% | 64.00% | 10.00 |
| 7 | 19 | 10011 | 3 | 36 | 2.67% | 66.67% | 19.71 |
| 8 | 26 | 11010 | 3 | 36 | 2.67% | 69.33% | 13.77 |
| 9 | 28 | 11100 | 3 | 35 | 2.59% | 71.93% | 12.69 |
| 10 | 30 | 11110 | 4 | 30 | 2.22% | 74.15% | 20.13 |
| 11 | 8 | 01000 | 1 | 30 | 2.22% | 76.37% | 2.75 |
| 12 | 29 | 11101 | 4 | 26 | 1.93% | 78.30% | 18.60 |
| 13 | 17 | 10001 | 2 | 24 | 1.78% | 80.07% | 10.66 |
| 14 | 25 | 11001 | 3 | 23 | 1.70% | 81.78% | 16.27 |
| 15 | 21 | 10101 | 3 | 22 | 1.63% | 83.41% | 22.45 |
| 16 | 1 | 00001 | 1 | 21 | 1.56% | 84.96% | 8.83 |
| 17 | 18 | 10010 | 2 | 19 | 1.41% | 86.37% | 8.42 |
| 18 | 10 | 01010 | 2 | 19 | 1.41% | 87.78% | 13.91 |
| 19 | 2 | 00010 | 1 | 17 | 1.26% | 89.04% | 8.01 |
| 20 | 5 | 00101 | 2 | 17 | 1.26% | 90.30% | 16.04 |

## Conclusion

**Coverage is relatively dispersed.**
13 bundles are needed for 80% coverage,
and 20 for 90%.
Top-20 bundles cover 90.30% of total customer demand.

This analysis pooled 1350 customer-level choices from 27 MB solver instances.
