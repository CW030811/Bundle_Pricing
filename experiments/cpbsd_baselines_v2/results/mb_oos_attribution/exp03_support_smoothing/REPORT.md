# Experiment 03: Support-Aware Price Smoothing

## Setting

- Fixed setting: `N=5`, `K=50`, `normal`, `rho=0.0`, `full`, `hvhm`.
- Base policy: cached `baseline_v2` MB full bundle price table.
- Experiment theory: Bundles with only a handful of in-sample buyers should not get fully trusted custom prices. Replacing low-support bundles with BSP size prices trades some fit for lower variance.
- Model selection rule: Global 5-fold validation over the 5 baseline instances; one shared support threshold is selected for all instances.
- Selected setting: `0`

## Aggregate Result

| method | mean_revenue_in | mean_revenue_out | mean_drop_pct | mean_ratio_in_to_bsp | mean_ratio_out_to_bsp |
| --- | --- | --- | --- | --- | --- |
| Baseline MB | 1.6120 | 1.1598 | 27.83% | 1.3431 | 1.0597 |
| Support-Aware Price Smoothing | 1.6037 | 1.1503 | 28.04% | 1.3359 | 1.0509 |

- Mean OOS revenue delta vs baseline MB: `-0.0095`.
- Mean drop delta vs baseline MB: `+0.21%`.

## Per-Instance Result

| instance | method | param | revenue_in | revenue_out | drop_pct | ratio_in_to_bsp | ratio_out_to_bsp |
| --- | --- | --- | --- | --- | --- | --- | --- |
| inst001 | Baseline MB | baseline | 1.77688 | 1.136169 | 36.058248 | 1.321609 | 1.091967 |
| inst002 | Baseline MB | baseline | 1.575781 | 1.118545 | 29.016428 | 1.450956 | 1.014374 |
| inst003 | Baseline MB | baseline | 1.624647 | 1.223328 | 24.701899 | 1.221518 | 1.062829 |
| inst004 | Baseline MB | baseline | 1.517831 | 1.144405 | 24.602611 | 1.363815 | 1.003838 |
| inst005 | Baseline MB | baseline | 1.564739 | 1.176785 | 24.793492 | 1.357452 | 1.125634 |
| inst001 | Support-Aware Price Smoothing | 0 | 1.77688 | 1.136169 | 36.058248 | 1.321609 | 1.091967 |
| inst002 | Support-Aware Price Smoothing | 0 | 1.575781 | 1.111413 | 29.469066 | 1.450956 | 1.007906 |
| inst003 | Support-Aware Price Smoothing | 0 | 1.624647 | 1.216291 | 25.135046 | 1.221518 | 1.056715 |
| inst004 | Support-Aware Price Smoothing | 0 | 1.517831 | 1.136856 | 25.099946 | 1.363815 | 0.997216 |
| inst005 | Support-Aware Price Smoothing | 0 | 1.523374 | 1.150765 | 24.459483 | 1.321567 | 1.100744 |

## Selection Detail

| instance | selected_param | baseline_out_revenue | variant_out_revenue | delta_out_revenue |
| --- | --- | --- | --- | --- |
| inst001 | 0 | 1.136169 | 1.136169 | 0.0 |
| inst002 | 0 | 1.118545 | 1.111413 | -0.007133 |
| inst003 | 0 | 1.223328 | 1.216291 | -0.007037 |
| inst004 | 0 | 1.144405 | 1.136856 | -0.007549 |
| inst005 | 0 | 1.176785 | 1.150765 | -0.026021 |

## Plots

- `boxplot_ratio_vs_bsp_n5.png`: same ratio-vs-BSP perspective as baseline v2.
- `paired_revenue_bars.png`: per-instance in/out revenue bars for baseline MB vs this experiment.

## Candidate Sweep / CV Trace

| param | mean_cv_revenue | mean_out_revenue |
| --- | --- | --- |
| 0 | 1.6037024736729422 | 1.1502985661683698 |
| 1 | 1.4852413110386185 | 1.1285085344866996 |
| 2 | 1.3542516612204578 | 1.092296186583999 |
| 3 | 1.316935260487377 | 1.0919391888178929 |
