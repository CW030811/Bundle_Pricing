# Ablation Results

## Scope

- Compared `5` MB variants on `5` representative instances.
- Solve time limit per variant: `60.0` seconds.
- Out-of-sample evaluation size: `1000` customers per instance.

## Summary by Variant

| variant_key | variant_name | instances | mean_revenue_in_sample | mean_revenue_out_sample | mean_delta_in_vs_current | mean_delta_out_vs_current | mean_price_l1_vs_current | optimal_count | time_limit_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| current | Current solver | 5 | 5.5675808167866645 | 4.702706475927094 | 0.0 | 0.0 | 0.0 | 0 | 5 |
| outside_only | Paper outside option | 5 | 5.559900820385428 | 4.600242997915759 | -0.007679996401237244 | -0.10246347801133653 | 119.26665077957509 | 0 | 5 |
| envy_only | Paper envy indexing | 5 | 5.553898658054897 | 4.617449272336189 | -0.013682158731767568 | -0.08525720359090574 | 128.43310769331205 | 0 | 5 |
| subadd_only | Full partition subadditivity | 5 | 5.561997731494172 | 4.736298288873152 | -0.005583085292492429 | 0.03359181294605702 | 77.45905879175561 | 0 | 5 |
| all_paper_switches | All Appendix C switches | 5 | 5.561997731494117 | 4.623888191062077 | -0.005583085292548385 | -0.07881828486501688 | 118.82123999457262 | 0 | 5 |

## Per-Instance Rows

| instance_id | variant_key | status_text | delta_in_vs_current | delta_out_vs_current | price_l1_vs_current | price_linf_vs_current |
| --- | --- | --- | --- | --- | --- | --- |
| cpbsd_instance_001_N5_K50_normal_rho0.0_full_hvhm | current | TIME_LIMIT | 0.0 | 0.0 | 0.0 | 0.0 |
| cpbsd_instance_001_N5_K50_normal_rho0.0_full_hvhm | outside_only | TIME_LIMIT | 0.0015163529628259287 | -0.009103433571458375 | 72.35018032305807 | 12.325523294338096 |
| cpbsd_instance_001_N5_K50_normal_rho0.0_full_hvhm | envy_only | TIME_LIMIT | 0.0015163529622375105 | -0.00018178671169399863 | 76.39189035791858 | 17.127534500343614 |
| cpbsd_instance_001_N5_K50_normal_rho0.0_full_hvhm | subadd_only | TIME_LIMIT | 0.0015163529618542615 | 0.005628179215348306 | 66.23513421989358 | 17.127534500347465 |
| cpbsd_instance_001_N5_K50_normal_rho0.0_full_hvhm | all_paper_switches | TIME_LIMIT | 0.0015163529618495986 | 0.004447180381363047 | 75.70958046162113 | 16.252726706749222 |
| cpbsd_instance_002_N5_K50_normal_rho0.0_full_hvhm | current | TIME_LIMIT | 0.0 | 0.0 | 0.0 | 0.0 |
| cpbsd_instance_002_N5_K50_normal_rho0.0_full_hvhm | outside_only | TIME_LIMIT | 1.5987211554602254e-14 | 0.0018769017520825493 | 7.655934293232157 | 4.929125096678437 |
| cpbsd_instance_002_N5_K50_normal_rho0.0_full_hvhm | envy_only | TIME_LIMIT | -0.043201632184272976 | 0.004924042833054365 | 58.35092202539336 | 20.714046332797384 |
| cpbsd_instance_002_N5_K50_normal_rho0.0_full_hvhm | subadd_only | TIME_LIMIT | 2.90878432451791e-13 | -0.0026075661651507875 | 41.06282301188174 | 20.49389668507285 |
| cpbsd_instance_002_N5_K50_normal_rho0.0_full_hvhm | all_paper_switches | TIME_LIMIT | 1.199040866595169e-14 | 0.004261243851541696 | 34.749445034468515 | 13.288242722891805 |
| cpbsd_instance_003_N5_K50_normal_rho0.0_full_hvhm | current | TIME_LIMIT | 0.0 | 0.0 | 0.0 | 0.0 |
| cpbsd_instance_003_N5_K50_normal_rho0.0_full_hvhm | outside_only | TIME_LIMIT | -2.4424906541753444e-15 | 0.00966445091755408 | 68.02503626483414 | 18.515350198676643 |
| cpbsd_instance_003_N5_K50_normal_rho0.0_full_hvhm | envy_only | TIME_LIMIT | 1.3447021274259896e-12 | 0.0029401647598308323 | 69.00038755513464 | 13.522351123367129 |
| cpbsd_instance_003_N5_K50_normal_rho0.0_full_hvhm | subadd_only | TIME_LIMIT | 7.149836278586008e-14 | -0.0026734102069536636 | 87.98713485760453 | 15.950356249389563 |
| cpbsd_instance_003_N5_K50_normal_rho0.0_full_hvhm | all_paper_switches | TIME_LIMIT | 9.00390872971002e-13 | -0.007785213753162434 | 87.9741296831734 | 17.52889605367423 |
| cpbsd_instance_001_N5_K50_exponential_rho-0.5_none_zero | current | TIME_LIMIT | 0.0 | 0.0 | 0.0 | 0.0 |
| cpbsd_instance_001_N5_K50_exponential_rho-0.5_none_zero | outside_only | TIME_LIMIT | -0.03991633496932767 | -0.13925468465291502 | 84.9755006249201 | 10.695985383562908 |
| cpbsd_instance_001_N5_K50_exponential_rho-0.5_none_zero | envy_only | TIME_LIMIT | -0.026725514438076026 | -0.0017302185539307402 | 83.26285683792503 | 11.729040762965296 |
| cpbsd_instance_001_N5_K50_exponential_rho-0.5_none_zero | subadd_only | TIME_LIMIT | -0.029431779424710758 | 0.1030717677313775 | 79.8807159637838 | 9.458370697034406 |
| cpbsd_instance_001_N5_K50_exponential_rho-0.5_none_zero | all_paper_switches | TIME_LIMIT | -0.02943177942548969 | 0.13727401962194508 | 93.71557758246084 | 11.898334123474537 |
| cpbsd_instance_001_N5_K50_lognormal_rho-0.5_full_zero | current | TIME_LIMIT | 0.0 | 0.0 | 0.0 | 0.0 |
| cpbsd_instance_001_N5_K50_lognormal_rho-0.5_full_zero | outside_only | TIME_LIMIT | 3.019806626980426e-13 | -0.3755006245019459 | 363.32660239183093 | 32.17288343025963 |
| cpbsd_instance_001_N5_K50_lognormal_rho-0.5_full_zero | envy_only | TIME_LIMIT | -7.105427357601002e-14 | -0.43223822028178915 | 355.15948169018867 | 27.797774460757275 |
| cpbsd_instance_001_N5_K50_lognormal_rho-0.5_full_zero | subadd_only | TIME_LIMIT | 3.197442310920451e-14 | 0.06454009415566375 | 112.12948590561444 | 14.71353811227528 |
| cpbsd_instance_001_N5_K50_lognormal_rho-0.5_full_zero | all_paper_switches | TIME_LIMIT | -1.4210854715202004e-14 | -0.5322886544267718 | 301.9574672111392 | 36.65108011987385 |

## Interpretation

- On this first ablation batch, the strongest positive contributor is `subadd_only`, i.e. replacing the current pairwise disjoint-partition subadditivity family with the fuller Appendix C style partition family while keeping the rest of the current solver structure unchanged.
- `subadd_only` is the only single-switch variant with a positive mean OOS delta versus current: `+0.0336`.
- The paper-style outside option by itself (`outside_only`) is harmful on average in this batch: mean OOS delta `-0.1025`.
- Excluding `j = k` from the envy-like family (`envy_only`) is also harmful on average in this batch: mean OOS delta `-0.0853`.
- Turning on all paper switches together does not improve average OOS performance on this batch: mean OOS delta `-0.0788`.
- Taken together, these ablations suggest that if there is a meaningful formulation-level gap worth pursuing, the most plausible source is the subadditivity constraint family rather than the outside-option treatment or the `j != k` indexing detail.

## Practical Takeaway

- The current evidence still does not support the claim that "our MB reproduction misses the paper mainly because we are not using the literal Appendix C MB formulation."
- The evidence does support a narrower claim: the fuller partition subadditivity family can materially change the price table and sometimes improve OOS performance, so it is the one Appendix-C-related modeling choice most worth deeper follow-up.
