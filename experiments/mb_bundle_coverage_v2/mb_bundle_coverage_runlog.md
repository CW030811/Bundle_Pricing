# MB Bundle Coverage Run Log

Run time: 2026-03-16T18:18:57.986827
Result directory: /Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/mb_bundle_coverage_v2/results
Output directory: /Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/mb_bundle_coverage_v2
MB result files found: 27

OK [direct]: cpbsd_instance_001_N5_K50_exponential_rho-0.5_full_hvhm__mb.json  K=50  unique_bundles=20
OK [direct]: cpbsd_instance_001_N5_K50_exponential_rho-0.5_full_hvlm__mb.json  K=50  unique_bundles=13
OK [direct]: cpbsd_instance_001_N5_K50_exponential_rho-0.5_full_zero__mb.json  K=50  unique_bundles=9
OK [direct]: cpbsd_instance_001_N5_K50_exponential_rho-0.5_none_hvhm__mb.json  K=50  unique_bundles=20
OK [direct]: cpbsd_instance_001_N5_K50_exponential_rho-0.5_none_hvlm__mb.json  K=50  unique_bundles=15
OK [direct]: cpbsd_instance_001_N5_K50_exponential_rho-0.5_none_zero__mb.json  K=50  unique_bundles=12
OK [direct]: cpbsd_instance_001_N5_K50_exponential_rho-0.5_partial_hvhm__mb.json  K=50  unique_bundles=17
OK [direct]: cpbsd_instance_001_N5_K50_exponential_rho-0.5_partial_hvlm__mb.json  K=50  unique_bundles=13
OK [direct]: cpbsd_instance_001_N5_K50_exponential_rho-0.5_partial_zero__mb.json  K=50  unique_bundles=5
OK [direct]: cpbsd_instance_001_N5_K50_exponential_rho0.0_full_hvhm__mb.json  K=50  unique_bundles=18
OK [direct]: cpbsd_instance_001_N5_K50_exponential_rho0.0_full_hvlm__mb.json  K=50  unique_bundles=13
OK [direct]: cpbsd_instance_001_N5_K50_exponential_rho0.0_full_zero__mb.json  K=50  unique_bundles=10
OK [direct]: cpbsd_instance_001_N5_K50_exponential_rho0.0_none_hvhm__mb.json  K=50  unique_bundles=23
OK [direct]: cpbsd_instance_001_N5_K50_exponential_rho0.0_none_hvlm__mb.json  K=50  unique_bundles=16
OK [direct]: cpbsd_instance_001_N5_K50_exponential_rho0.0_none_zero__mb.json  K=50  unique_bundles=8
OK [direct]: cpbsd_instance_001_N5_K50_exponential_rho0.0_partial_hvhm__mb.json  K=50  unique_bundles=17
OK [direct]: cpbsd_instance_001_N5_K50_exponential_rho0.0_partial_hvlm__mb.json  K=50  unique_bundles=16
OK [direct]: cpbsd_instance_001_N5_K50_exponential_rho0.0_partial_zero__mb.json  K=50  unique_bundles=14
OK [direct]: cpbsd_instance_001_N5_K50_exponential_rho0.5_full_hvhm__mb.json  K=50  unique_bundles=15
OK [direct]: cpbsd_instance_001_N5_K50_exponential_rho0.5_full_hvlm__mb.json  K=50  unique_bundles=14
OK [direct]: cpbsd_instance_001_N5_K50_exponential_rho0.5_full_zero__mb.json  K=50  unique_bundles=11
OK [direct]: cpbsd_instance_001_N5_K50_exponential_rho0.5_none_hvhm__mb.json  K=50  unique_bundles=13
OK [direct]: cpbsd_instance_001_N5_K50_exponential_rho0.5_none_hvlm__mb.json  K=50  unique_bundles=12
OK [direct]: cpbsd_instance_001_N5_K50_exponential_rho0.5_none_zero__mb.json  K=50  unique_bundles=10
OK [direct]: cpbsd_instance_001_N5_K50_exponential_rho0.5_partial_hvhm__mb.json  K=50  unique_bundles=16
OK [direct]: cpbsd_instance_001_N5_K50_exponential_rho0.5_partial_hvlm__mb.json  K=50  unique_bundles=11
OK [direct]: cpbsd_instance_001_N5_K50_exponential_rho0.5_partial_zero__mb.json  K=50  unique_bundles=13

Processed: 27, Skipped: 0
Total customers pooled: 1350

## Validation Checks

1. Sum of selected_customer_weight: 1.000000 (expected ~1.0) PASS
2. Sum of customer_share: 1.000000 (expected ~1.0) PASS
3. cumulative_customer_share monotonically non-decreasing: PASS
4. Final cumulative_customer_share: 1.000000 (expected ~1.0) PASS

## Top-N Cumulative Coverage

Top-1: 0.3644 (36.44%)
Top-5: 0.6074 (60.74%)
Top-10: 0.7415 (74.15%)
Top-20: 0.9030 (90.30%)
Top-50: N/A (only 32 bundles)

## Bundles Needed for Coverage Thresholds

50% coverage: 3 bundles
80% coverage: 13 bundles
90% coverage: 20 bundles
95% coverage: 25 bundles
99% coverage: 30 bundles

CSV saved: /Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/mb_bundle_coverage_v2/mb_bundle_coverage_details.csv
Bar chart saved: /Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/mb_bundle_coverage_v2/mb_bundle_coverage_bar.png
Cumulative chart saved: /Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/mb_bundle_coverage_v2/mb_bundle_topN_cumulative.png
Experiment report saved: /Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/mb_bundle_coverage_v2/mb_bundle_coverage_experiment.md
