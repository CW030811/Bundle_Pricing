# Paper To Repo Naming Map

## Setup Terms

| Paper term | Repo term | Note |
| --- | --- | --- |
| `exponential` | `exponential` | exact match |
| `logit` | `logit` | implemented as Gumbel family in code |
| `lognormal` | `lognormal` | exact match |
| `normal` | `normal` | exact match |
| `uniform` | `uniform` | exact match |
| `rho in {-0.5, 0, 0.5}` | `rho=-0.5, 0.0, 0.5` | use decimal form in repo result names |
| `none` | `none` | exact match |
| `partial` | `partial` | exact match |
| `full` | `full` | exact match |
| `zero` | `zero` | exact match |
| `HVHM` | `hvhm` | repo uses lowercase |
| `HVLM` | `hvlm` | repo uses lowercase |

## Method Terms

| Discussion term | Repo-facing term | Note |
| --- | --- | --- |
| `BSP` | `BSP` | exact match |
| `CPBSD` | `CPBSD` or `CPBSD-MILP` | reports may use `CPBSD-MILP` |
| `CPBSD-A` | `CPBSD-A` | exact match |
| `FCP-MB` | `FCP-pruned-MB` or `FCP-MB` | reports often shorten the label |
| `FCP-GCN` | must be frozen per runner/result folder before Phase 2 | not standardized in this folder yet |

## Naming Rule For This Week

When writing shortlist and result tables:

- use repo setup names as source of truth
- keep cost labels lowercase: `zero`, `hvhm`, `hvlm`
- keep rho labels explicit: `rho0.0`, `rho0.5`, `rho-0.5`
- if a report uses `FCP-pruned-MB`, treat it as the canonical executable method name for the current MB acceleration line
