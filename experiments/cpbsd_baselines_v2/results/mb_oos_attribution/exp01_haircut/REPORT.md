# Experiment 01: Size-4/5 Margin Haircut

## Setting

- Fixed setting: `N=5`, `K=50`, `normal`, `rho=0.0`, `full`, `hvhm`.
- Base policy: cached `baseline_v2` MB full bundle price table.
- Experiment theory: Large bundles carry the biggest revenue-loss contribution in the attribution report. A margin haircut should reduce how often they sit exactly on the purchase boundary and therefore lower OOS substitution/outside drift.
- Model selection rule: Global 5-fold validation over the 5 baseline instances; one shared gamma is selected for all instances.
- Selected setting: `1.0`

## Aggregate Result

| method | mean_revenue_in | mean_revenue_out | mean_drop_pct | mean_ratio_in_to_bsp | mean_ratio_out_to_bsp |
| --- | --- | --- | --- | --- | --- |
| Baseline MB | 1.6120 | 1.1598 | 27.83% | 1.3431 | 1.0597 |
| Size-4/5 Margin Haircut | 1.6120 | 1.1598 | 27.83% | 1.3431 | 1.0597 |

- Mean OOS revenue delta vs baseline MB: `+0.0000`.
- Mean drop delta vs baseline MB: `+0.00%`.

## Per-Instance Result

| instance | method | param | revenue_in | revenue_out | drop_pct | ratio_in_to_bsp | ratio_out_to_bsp |
| --- | --- | --- | --- | --- | --- | --- | --- |
| inst001 | Baseline MB | baseline | 1.77688 | 1.136169 | 36.058248 | 1.321609 | 1.091967 |
| inst002 | Baseline MB | baseline | 1.575781 | 1.118545 | 29.016428 | 1.450956 | 1.014374 |
| inst003 | Baseline MB | baseline | 1.624647 | 1.223328 | 24.701899 | 1.221518 | 1.062829 |
| inst004 | Baseline MB | baseline | 1.517831 | 1.144405 | 24.602611 | 1.363815 | 1.003838 |
| inst005 | Baseline MB | baseline | 1.564739 | 1.176785 | 24.793492 | 1.357452 | 1.125634 |
| inst001 | Size-4/5 Margin Haircut | 1.0 | 1.77688 | 1.136169 | 36.058248 | 1.321609 | 1.091967 |
| inst002 | Size-4/5 Margin Haircut | 1.0 | 1.575781 | 1.118545 | 29.016428 | 1.450956 | 1.014374 |
| inst003 | Size-4/5 Margin Haircut | 1.0 | 1.624647 | 1.223328 | 24.701899 | 1.221518 | 1.062829 |
| inst004 | Size-4/5 Margin Haircut | 1.0 | 1.517831 | 1.144405 | 24.602611 | 1.363815 | 1.003838 |
| inst005 | Size-4/5 Margin Haircut | 1.0 | 1.564739 | 1.176785 | 24.793492 | 1.357452 | 1.125634 |

## Selection Detail

| instance | selected_param | baseline_out_revenue | variant_out_revenue | delta_out_revenue |
| --- | --- | --- | --- | --- |
| inst001 | 1.0 | 1.136169 | 1.136169 | 0.0 |
| inst002 | 1.0 | 1.118545 | 1.118545 | 0.0 |
| inst003 | 1.0 | 1.223328 | 1.223328 | 0.0 |
| inst004 | 1.0 | 1.144405 | 1.144405 | 0.0 |
| inst005 | 1.0 | 1.176785 | 1.176785 | 0.0 |

## Plots

- `boxplot_ratio_vs_bsp_n5.png`: same ratio-vs-BSP perspective as baseline v2.
- `paired_revenue_bars.png`: per-instance in/out revenue bars for baseline MB vs this experiment.

## Candidate Sweep / CV Trace

| param | mean_cv_revenue | mean_out_revenue |
| --- | --- | --- |
| 1.0 | 1.6119754173856975 | 1.159846393510846 |
| 0.95 | 1.5684710930740235 | 1.1862573359009652 |
| 0.9 | 1.5261372101363935 | 1.2069626422273785 |
| 0.85 | 1.4843457547845296 | 1.218506395644607 |
| 0.8 | 1.4251250322183406 | 1.2223414454400516 |
| 0.75 | 1.3576379936174756 | 1.2136501072711472 |
| 0.7 | 1.2968232041894612 | 1.1963954004045898 |
