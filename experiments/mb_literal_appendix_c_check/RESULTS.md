# Results

## Scope

- Compared current MB solver against a literal-transcription Appendix C solver on `5` instances.
- Solve time limit per solver: `120.0` seconds.
- Out-of-sample evaluation size: `2000` customers per instance.

## Summary

| instances | mean_delta_in_sample | mean_delta_out_sample | mean_objective_delta | mean_price_l1_distance | mean_price_linf_distance | literal_better_in_count | literal_better_out_count | same_status_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 5 | -0.01848336220260629 | -0.05649067942595809 | -0.005886694320961139 | 153.8455236587276 | 21.26864449560421 | 0 | 2 | 2 |

## Per-Instance Comparison

| instance_id | dist_family | rho | heterogeneity | cost_scenario | current_status | literal_status | delta_in_sample | delta_out_sample | objective_delta_literal_minus_current | price_l1_distance | price_linf_distance |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cpbsd_instance_001_N5_K50_normal_rho0.0_full_hvhm | normal | 0.0 | full | hvhm | TIME_LIMIT | TIME_LIMIT | 2.674749310926927e-12 | -0.010327649977908582 | 2.97983859809392e-12 | 165.48891818638862 | 18.51256526897143 |
| cpbsd_instance_002_N5_K50_normal_rho0.0_full_hvhm | normal | 0.0 | full | hvhm | TIME_LIMIT | OPTIMAL | 2.580158309228864e-13 | -0.002677381855648031 | 1.6253665080512292e-13 | 66.63039310100798 | 20.468784085847297 |
| cpbsd_instance_003_N5_K50_normal_rho0.0_full_hvhm | normal | 0.0 | full | hvhm | OPTIMAL | TIME_LIMIT | -0.06298503159056956 | 0.011980250986174834 | -1.6921825312099514e-06 | 101.40095280702731 | 19.604107357953723 |
| cpbsd_instance_001_N5_K50_exponential_rho-0.5_none_zero | exponential | -0.5 | none | zero | TIME_LIMIT | TIME_LIMIT | -0.029431779425394655 | 0.011223881945777503 | -0.029431779425438176 | 92.50881036689624 | 11.67733064767149 |
| cpbsd_instance_001_N5_K50_lognormal_rho-0.5_full_zero | lognormal | -0.5 | full | zero | TIME_LIMIT | OPTIMAL | 0.0 | -0.2926524982281862 | 2.1316282072803006e-14 | 343.1985438323179 | 36.08043511757711 |

## Preliminary Interpretation

- This file only answers whether the literal Appendix C transcription behaves differently from the current implementation on a small representative set.
- It does not yet constitute a full paper-level reproduction.

## Phase 1 Findings

- The literal solver is operational and produces feasible MB solutions directly from the Appendix C variable/constraint set.
- The current solver and the literal solver do not always return the same price table. The price gaps are often large in level terms, with mean `L1` distance about `153.85`.
- Despite that, the objective values are usually extremely close on the tested instances. In three of five instances, the objective gap is numerically negligible. This suggests the two formulations are often landing on near-equivalent incumbents even when the price vectors differ.
- Solve status differs across formulations. On the tested set:
  - literal reached `OPTIMAL` in two instances where the current solver was `TIME_LIMIT`
  - current reached `OPTIMAL` in one instance where the literal solver was `TIME_LIMIT`
- The literal solver does not show a clear advantage in out-of-sample revenue on this first batch. It improved OOS revenue in two instances and worsened it in three instances, with mean OOS delta `-0.0565`.
- The strongest evidence against a simple formulation-mismatch explanation is that the literal Appendix C solver does not systematically recover better OOS MB performance on these representative instances.

## What This Means

- There is implementation-level non-equivalence between the two solvers, or at least they expose the solver to different search paths and different incumbents.
- However, the current evidence does not support the claim that "using a non-literal Hanson-style formulation is the main reason our MB reproduction misses the paper."
- The next useful step is not a full rerun. It is an ablation study that isolates which modeling change is responsible for the observed price-table divergence:
  1. explicit empty bundle versus paper-style outside option
  2. pairwise subadditivity versus literal full partition family
  3. `j != k` versus including `j = k` in the envy-like constraints
