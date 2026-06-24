# Setup Inventory

## Scope

This note freezes the setup inventory used for `cpbsd_main_n5` Phase 1 screening.

The original CPBSD-style full grid contains `405` cases:

- `3` product counts: `N in {5, 10, 30}`
- `5` marginal distributions
- `3` correlation settings
- `3` heterogeneity settings
- `3` cost scenarios

So:

- full paper-style grid = `3 x 5 x 3 x 3 x 3 = 405`
- `cpbsd_main_n5` active screen space = `5 x 3 x 3 x 3 = 135`

## Source Of Truth

Repository implementation source:

- [generate_data_CPBSD.py](/Users/sensen/.openclaw/workspace/domains/revenue-management/project-root/code_submission_project/code_submission/src/data/generate_data_CPBSD.py:14)

Confirmed implemented setup dimensions:

| Dimension | Paper values | Repo values | Availability |
| --- | --- | --- | --- |
| `dist_family` | `exponential`, `logit`, `lognormal`, `normal`, `uniform` | same | implemented |
| `rho` | `-0.5`, `0.0`, `0.5` | same | implemented |
| `heterogeneity` | `none`, `partial`, `full` | same | implemented |
| `cost_scenario` | `zero`, `HVHM`, `HVLM` | `zero`, `hvhm`, `hvlm` | implemented |
| `N` | `5`, `10`, `30` in paper grid | script supports any `N >= 2` | implemented |

## Canonical Naming

For `cpbsd_main_n5`, use the canonical setting key:

`{dist}_rho{rho}_{heterogeneity}_{cost}`

Examples:

- `normal_rho0.0_full_zero`
- `logit_rho0.0_full_hvhm`
- `normal_rho-0.5_full_zero`

## Phase 1 Selection Rule

The shortlist is not meant to be statistically exhaustive. It is meant to support a one-week showcase search.

Use these filters:

- keep `full` heterogeneity as the default because it is the most informative and closest to the hard cases where method differences matter
- prioritize `normal` and `logit` as the main distribution families
- include `rho = 0.0` as the baseline and use `rho = +/-0.5` as robustness checks
- use `zero` for the clean benchmark and `hvhm` for the realistic positive-cost benchmark
- keep the final shortlist small enough for matched multi-instance runs this week

## Inventory Freeze

Phase 1 freeze decision for this week:

- screen space acknowledged: `135` settings at `N=5`
- execution shortlist frozen separately in [setup_shortlist.md](/Users/sensen/.openclaw/workspace/domains/revenue-management/research-tracker/weekly-reports/2026-W16-fcp-gcn-vs-cpbsd-main-n5/setup_shortlist.md)
