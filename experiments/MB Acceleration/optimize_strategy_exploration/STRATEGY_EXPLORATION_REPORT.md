# Exact-Safe Optimize Strategy Exploration

This report compares current MB against exact-equivalent lean variants that aim to reduce the burden on `model.optimize()` without changing the objective or feasible region.

Variant definitions:

- `current`: current canonical restricted MB formulation.
- `current_no_self_envy`: current formulation with the `j = k` envy-like constraints removed.
- `lean_no_aux`: exact-equivalent lean formulation that removes `profit` and `s_terms` auxiliaries, replaces them with direct payment/value constraints, and keeps self-envy.
- `lean_no_aux_no_self_envy`: the same lean formulation, plus removal of self-envy constraints.

## original_mb_full

- Instance: `/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/cpbsd_baselines_v2/instances/n5/cpbsd_instance_001_N5_K50_normal_rho0.0_full_hvhm.msgpack`
- Metadata: `{"bundle_space_size": 32}`

| variant_key | status_code | runtime | runtime_ratio_vs_current | wall_time | objective | objective_delta_vs_current | mip_gap | node_count | num_vars | num_constrs | var_reduction_vs_current_pct | constr_reduction_vs_current_pct | optimize_seconds | optimize_share_pct | largest_non_opt_step |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| current | 9 | 120.024683 | 1.000000 | 120.023194 | 1.776880 | 0.000000 | 0.011446 | 33427.000000 | 6482 | 10765 | 0.000000 | 0.000000 | 120.023194 | 99.623448 | constraint_envy_like |
| current_no_self_envy | 9 | 120.013337 | 0.999905 | 120.012865 | 1.776880 | 0.000000 | 0.011165 | 35124.000000 | 6482 | 10715 | 0.000000 | 0.464468 | 120.012865 | 99.576987 | constraint_envy_like |
| lean_no_aux | 9 | 120.008229 | 0.999863 | 120.007956 | 1.776880 | -0.000000 | 0.012928 | 22053.000000 | 3282 | 9116 | 49.367479 | 15.318161 | 120.007956 | 99.631584 | constraint_envy_like |
| lean_no_aux_no_self_envy | 2 | 95.172481 | 0.792941 | 95.172241 | 1.776880 | 0.000000 | 0.009631 | 19919.000000 | 3282 | 9066 | 49.367479 | 15.782629 | 95.172241 | 99.549995 | constraint_envy_like |

## original_mb_full_hard_tail

- Instance: `/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/cpbsd_baselines_v2/instances/n5/cpbsd_instance_005_N5_K50_normal_rho0.0_full_hvhm.msgpack`
- Metadata: `{"bundle_space_size": 32}`

| variant_key | status_code | runtime | runtime_ratio_vs_current | wall_time | objective | objective_delta_vs_current | mip_gap | node_count | num_vars | num_constrs | var_reduction_vs_current_pct | constr_reduction_vs_current_pct | optimize_seconds | optimize_share_pct | largest_non_opt_step |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| current | 9 | 120.035014 | 1.000000 | 120.034792 | 1.564739 | 0.000000 | 0.041440 | 21126.000000 | 6482 | 10765 | 0.000000 | 0.000000 | 120.034792 | 99.622281 | constraint_envy_like |
| current_no_self_envy | 9 | 120.005952 | 0.999758 | 120.005643 | 1.564577 | -0.000162 | 0.036796 | 24609.000000 | 6482 | 10715 | 0.000000 | 0.464468 | 120.005643 | 99.628442 | constraint_envy_like |
| lean_no_aux | 9 | 120.016377 | 0.999845 | 120.016071 | 1.564739 | -0.000000 | 0.040753 | 15447.000000 | 3282 | 9116 | 49.367479 | 15.318161 | 120.016071 | 99.631335 | constraint_envy_like |
| lean_no_aux_no_self_envy | 9 | 120.009226 | 0.999785 | 120.008926 | 1.564739 | 0.000000 | 0.039024 | 16811.000000 | 3282 | 9066 | 49.367479 | 15.782629 | 120.008926 | 99.570201 | constraint_envy_like |

## gcn_candidate_restricted_mb

- Instance: `/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/cpbsd_fcp_pruned_mb_compare_n10k50_strict300/instances/cpbsd_instance_001_N10_K50_normal_rho0.0_full_hvhm.msgpack`
- Metadata: `{"bundle_space_size": 37, "full_bundle_space_size": 1024, "raw_customer_bundle_count": 50, "threshold": 0.5, "setup": {"n_products": 10, "k_samples": 50, "dist_family": "normal", "rho": 0.0, "heterogeneity": "full", "cost_scenario": "hvhm", "seed": 20260321}}`

| variant_key | status_code | runtime | runtime_ratio_vs_current | wall_time | objective | objective_delta_vs_current | mip_gap | node_count | num_vars | num_constrs | var_reduction_vs_current_pct | constr_reduction_vs_current_pct | optimize_seconds | optimize_share_pct | largest_non_opt_step |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| current | 2 | 51.186788 | 1.000000 | 51.186669 | 3.561872 | 0.000000 | 0.009999 | 5043.000000 | 7487 | 11902 | 0.000000 | 0.000000 | 51.186669 | 98.973671 | constraint_envy_like |
| current_no_self_envy | 2 | 43.869024 | 0.857038 | 43.868923 | 3.561872 | -0.000000 | 0.009371 | 3989.000000 | 7487 | 11852 | 0.000000 | 0.420097 | 43.868923 | 98.827610 | constraint_envy_like |
| lean_no_aux | 2 | 69.619666 | 1.360110 | 69.619560 | 3.561872 | 0.000000 | 0.009570 | 4096.000000 | 3787 | 10003 | 49.418993 | 15.955302 | 69.619560 | 99.255891 | constraint_envy_like |
| lean_no_aux_no_self_envy | 2 | 76.393602 | 1.492448 | 76.393411 | 3.561872 | 0.000000 | 0.009425 | 4151.000000 | 3787 | 9953 | 49.418993 | 16.375399 | 76.393411 | 99.325006 | constraint_envy_like |

