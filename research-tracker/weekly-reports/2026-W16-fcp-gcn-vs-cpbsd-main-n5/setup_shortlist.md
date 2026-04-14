# Setup Shortlist

## Freeze Statement

This file freezes the Phase 1 shortlist for the current week.

Target use:

- identify settings most suitable for showcasing `FCP-MB`
- retain a small set that is still defensible as common or important CPBSD-style settings

## Shortlist Table

| Priority | Setting | Exact Values | Role | Why Selected | Expected Best Comparison Target | FCP-MB Acceptance Standard |
| --- | --- | --- | --- | --- | --- | --- |
| `P0` | `normal_rho0.0_full_zero` | `dist=normal`, `rho=0.0`, `heterogeneity=full`, `cost=zero` | clean main showcase | easiest to explain, already has positive evidence in repo, good for showing acceleration without cost confounds | `MB` runtime, `CPBSD-A` runtime, `BSP` revenue | worth showcasing if `Rev-In >= BSP`, `Rev-Out` stays close to `BSP`, and runtime is clearly below `MB` and preferably below `CPBSD-A` |
| `P0` | `normal_rho0.0_full_hvhm` | `dist=normal`, `rho=0.0`, `heterogeneity=full`, `cost=hvhm` | realistic main showcase | keeps the same baseline structure but adds realistic positive costs; good bridge to harder cases | `CPBSD-A` runtime, `BSP` revenue | worth showcasing if it keeps clear runtime gain and avoids severe OOS collapse; full OOS dominance is not required |
| `P1` | `logit_rho0.0_full_zero` | `dist=logit`, `rho=0.0`, `heterogeneity=full`, `cost=zero` | distribution robustness | checks whether the story survives outside `normal`; `logit` is a representative paper family | `MB` runtime, `BSP` revenue | worth keeping if candidate pruning remains effective and `Rev-In` stays above `BSP` with stable runtime |
| `P1` | `logit_rho0.0_full_hvhm` | `dist=logit`, `rho=0.0`, `heterogeneity=full`, `cost=hvhm` | realistic distribution robustness | combines distribution shift with positive cost; stronger evidence if it still works | `CPBSD-A` runtime, `BSP` revenue | worth keeping if it remains materially faster than `CPBSD-A` without a large extra OOS penalty |
| `P2` | `normal_rho0.5_full_zero` | `dist=normal`, `rho=0.5`, `heterogeneity=full`, `cost=zero` | positive-correlation stress test | tests whether more jointly-liked products make bundle coverage easier and pruning more reliable | `MB` runtime, `BSP` revenue | worth keeping if candidate space stays small and OOS remains near `BSP` |
| `P2` | `normal_rho-0.5_full_zero` | `dist=normal`, `rho=-0.5`, `heterogeneity=full`, `cost=zero` | negative-correlation stress test | tests the harder substitution-like case where pruning can fail if support spreads | `MB` runtime, robustness boundary | worth keeping if it still preserves meaningful revenue while showing where FCP-MB starts to break |

## Ranking By Showcase Value

Current ranking for execution:

1. `normal_rho0.0_full_zero`
2. `normal_rho0.0_full_hvhm`
3. `logit_rho0.0_full_zero`
4. `logit_rho0.0_full_hvhm`
5. `normal_rho0.5_full_zero`
6. `normal_rho-0.5_full_zero`

## Current Evidence Status

| Setting | Evidence Status | Current Read |
| --- | --- | --- |
| `normal_rho0.0_full_zero` | strong existing evidence | best current candidate for a clean `FCP-MB` showcase |
| `normal_rho0.0_full_hvhm` | partial existing evidence | likely useful, but OOS risk must be checked carefully |
| `logit_rho0.0_full_zero` | not yet batch-validated | high-priority robustness run |
| `logit_rho0.0_full_hvhm` | not yet batch-validated | useful but harder; run after P0 |
| `normal_rho0.5_full_zero` | not yet batch-validated | robustness candidate |
| `normal_rho-0.5_full_zero` | not yet batch-validated | boundary-case robustness candidate |

## Practical Phase 2 Recommendation

Run order for the next batch:

1. finish `P0` first
2. if `P0` looks promising, run `P1`
3. use `P2` to decide the outer boundary of the claim

Claim discipline:

- if only `P0` looks strong, frame `FCP-MB` as a clean-baseline acceleration method
- if `P1` also works, claim family robustness
- if `P2` also works, claim structural robustness across correlation patterns
