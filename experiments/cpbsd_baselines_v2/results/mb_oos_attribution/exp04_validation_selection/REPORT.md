# Experiment 04: Validation-Based Candidate Selection

## Setting

- Fixed setting: `N=5`, `K=50`, `normal`, `rho=0.0`, `full`, `hvhm`.
- Base policy: cached `baseline_v2` MB full bundle price table.
- Experiment theory: Rather than commit to one transform family ex ante, let a validation layer choose the most stable candidate policy for each instance from the candidate library.
- Model selection rule: Per-instance 5-fold validation picks the best candidate from baseline, haircut, shrinkage, support smoothing, and margin buffer libraries.
- Selected setting: `per-instance CV`

## Aggregate Result

| method | mean_revenue_in | mean_revenue_out | mean_drop_pct | mean_ratio_in_to_bsp | mean_ratio_out_to_bsp |
| --- | --- | --- | --- | --- | --- |
| Baseline MB | 1.6120 | 1.1598 | 27.83% | 1.3431 | 1.0597 |
| Validation-Based Candidate Selection | 1.6120 | 1.1598 | 27.83% | 1.3431 | 1.0597 |

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
| inst001 | Validation-Based Candidate Selection | baseline | 1.77688 | 1.136169 | 36.058248 | 1.321609 | 1.091967 |
| inst002 | Validation-Based Candidate Selection | baseline | 1.575781 | 1.118545 | 29.016428 | 1.450956 | 1.014374 |
| inst003 | Validation-Based Candidate Selection | baseline | 1.624647 | 1.223328 | 24.701899 | 1.221518 | 1.062829 |
| inst004 | Validation-Based Candidate Selection | baseline | 1.517831 | 1.144405 | 24.602611 | 1.363815 | 1.003838 |
| inst005 | Validation-Based Candidate Selection | baseline | 1.564739 | 1.176785 | 24.793492 | 1.357452 | 1.125634 |

## Selection Detail

| instance | selected_candidate | baseline_out_revenue | variant_out_revenue | delta_out_revenue |
| --- | --- | --- | --- | --- |
| inst001 | baseline | 1.136169 | 1.136169 | 0.0 |
| inst002 | baseline | 1.118545 | 1.118545 | 0.0 |
| inst003 | baseline | 1.223328 | 1.223328 | 0.0 |
| inst004 | baseline | 1.144405 | 1.144405 | 0.0 |
| inst005 | baseline | 1.176785 | 1.176785 | 0.0 |

## Plots

- `boxplot_ratio_vs_bsp_n5.png`: same ratio-vs-BSP perspective as baseline v2.
- `paired_revenue_bars.png`: per-instance in/out revenue bars for baseline MB vs this experiment.

## Candidate Sweep / CV Trace

| instance | candidate | mean_cv_revenue |
| --- | --- | --- |
| inst001 | baseline | 1.77688 |
| inst001 | haircut:1.00 | 1.77688 |
| inst001 | haircut:0.95 | 1.732731 |
| inst001 | haircut:0.90 | 1.674695 |
| inst001 | haircut:0.85 | 1.612018 |
| inst001 | haircut:0.80 | 1.551405 |
| inst001 | haircut:0.75 | 1.48166 |
| inst001 | haircut:0.70 | 1.399219 |
| inst001 | shrinkage:1.00 | 1.77688 |
| inst001 | shrinkage:0.75 | 1.260433 |
| inst001 | shrinkage:0.50 | 1.278687 |
| inst001 | shrinkage:0.25 | 1.304074 |
| inst001 | shrinkage:0.00 | 1.41396 |
| inst001 | support:0 | 1.77688 |
| inst001 | support:1 | 1.635983 |
| inst001 | support:2 | 1.620996 |
| inst001 | support:3 | 1.509496 |
| inst001 | margin:0.00 | 1.77688 |
| inst001 | margin:0.05 | 1.628389 |
| inst001 | margin:0.10 | 1.572432 |
