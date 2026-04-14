# Experiment 05: Minimum Surplus Margin Buffer

## Setting

- Fixed setting: `N=5`, `K=50`, `normal`, `rho=0.0`, `full`, `hvhm`.
- Base policy: cached `baseline_v2` MB full bundle price table.
- Experiment theory: The attribution report shows many in-sample sales occur at tiny positive surplus. Enforcing a minimum surplus buffer lowers prices just enough to move those knife-edge sales away from zero.
- Model selection rule: Global 5-fold validation over the 5 baseline instances; one shared tau is selected for all instances.
- Selected setting: `0.0`

## Aggregate Result

| method | mean_revenue_in | mean_revenue_out | mean_drop_pct | mean_ratio_in_to_bsp | mean_ratio_out_to_bsp |
| --- | --- | --- | --- | --- | --- |
| Baseline MB | 1.6120 | 1.1598 | 27.83% | 1.3431 | 1.0597 |
| Minimum Surplus Margin Buffer | 1.6100 | 1.1598 | 27.74% | 1.3416 | 1.0597 |

- Mean OOS revenue delta vs baseline MB: `-0.0000`.
- Mean drop delta vs baseline MB: `-0.09%`.

## Per-Instance Result

| instance | method | param | revenue_in | revenue_out | drop_pct | ratio_in_to_bsp | ratio_out_to_bsp |
| --- | --- | --- | --- | --- | --- | --- | --- |
| inst001 | Baseline MB | baseline | 1.77688 | 1.136169 | 36.058248 | 1.321609 | 1.091967 |
| inst002 | Baseline MB | baseline | 1.575781 | 1.118545 | 29.016428 | 1.450956 | 1.014374 |
| inst003 | Baseline MB | baseline | 1.624647 | 1.223328 | 24.701899 | 1.221518 | 1.062829 |
| inst004 | Baseline MB | baseline | 1.517831 | 1.144405 | 24.602611 | 1.363815 | 1.003838 |
| inst005 | Baseline MB | baseline | 1.564739 | 1.176785 | 24.793492 | 1.357452 | 1.125634 |
| inst001 | Minimum Surplus Margin Buffer | 0.0 | 1.77688 | 1.136169 | 36.058248 | 1.321609 | 1.091967 |
| inst002 | Minimum Surplus Margin Buffer | 0.0 | 1.575781 | 1.118545 | 29.016428 | 1.450956 | 1.014374 |
| inst003 | Minimum Surplus Margin Buffer | 0.0 | 1.614798 | 1.223321 | 24.243079 | 1.214113 | 1.062822 |
| inst004 | Minimum Surplus Margin Buffer | 0.0 | 1.517831 | 1.144405 | 24.602611 | 1.363815 | 1.003838 |
| inst005 | Minimum Surplus Margin Buffer | 0.0 | 1.564739 | 1.176785 | 24.793492 | 1.357452 | 1.125634 |

## Selection Detail

| instance | selected_param | baseline_out_revenue | variant_out_revenue | delta_out_revenue |
| --- | --- | --- | --- | --- |
| inst001 | 0.0 | 1.136169 | 1.136169 | 0.0 |
| inst002 | 0.0 | 1.118545 | 1.118545 | 0.0 |
| inst003 | 0.0 | 1.223328 | 1.223321 | -7e-06 |
| inst004 | 0.0 | 1.144405 | 1.144405 | 0.0 |
| inst005 | 0.0 | 1.176785 | 1.176785 | -0.0 |

## Plots

- `boxplot_ratio_vs_bsp_n5.png`: same ratio-vs-BSP perspective as baseline v2.
- `paired_revenue_bars.png`: per-instance in/out revenue bars for baseline MB vs this experiment.

## Candidate Sweep / CV Trace

| param | mean_cv_revenue | mean_out_revenue |
| --- | --- | --- |
| 0.0 | 1.6100055901924726 | 1.1598449536086564 |
| 0.05 | 1.4402619202135614 | 1.1471294360642377 |
| 0.1 | 1.3789398862920248 | 1.1330645608262075 |
| 0.2 | 1.2830322376360648 | 1.0984582795247624 |
| 0.3 | 1.1904545235752744 | 1.052510893494537 |
