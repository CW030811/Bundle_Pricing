# Phase 2 Dominance Summary

## Verification Snapshot

Verified against:

- [phase2_n10_n30_master.log](/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/fcp_mb_phase2_selected_n10_n30_5inst/phase2_n10_n30_master.log)
- [fcp_mb_phase2_selected_n10_n30_5inst](/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/fcp_mb_phase2_selected_n10_n30_5inst)

Checks completed:

- batch finished at `2026-04-14 01:02:46`
- `8/8` `aggregate_metrics.json` files exist
- `8/8` `comparison_summary_all.csv` files exist
- each executed method has `count = 5` in every aggregate file
- matched seed policy is frozen by script as `20260413` to `20260417`

Executed method scope:

- `BSP`
- `CPBSD-A`
- `FCP-pruned-MB`

Important gap:

- the original weekly Phase 2 spec asked for `CPBSD` as well, but this batch did not run `CPBSD` / `CPBSD-MILP`

## Acceptance Verdict

Current verdict: `PARTIAL ACCEPT`

What passes:

- the planned `N=10/30` batch finished cleanly
- all `8` executed setting-size pairs have matched `5`-instance averages
- the average table is reproducible from result files
- the dominance conclusion is clear: no full-dominance case was found

What is still missing relative to the original README target:

- no `CPBSD` baseline in this batch
- spread statistics are not yet rolled into the weekly folder
- Phase 2 therefore closes as a strong three-method result, not yet the full four-method acceptance target

## Dominance Read By Setting

| N | Setting | FCP vs BSP | FCP vs CPBSD-A | Read |
| ---: | --- | --- | --- | --- |
| 10 | `logit_rho0.0_full_hvhm` | wins in-sample, loses OOS and runtime | wins in-sample and runtime, loses OOS | not a showcase |
| 10 | `normal_rho0.0_full_hvhm` | wins in-sample, loses OOS and runtime | wins in-sample and runtime, loses OOS | OOS blocker is already visible |
| 10 | `normal_rho0.0_full_zero` | wins in-sample, loses OOS and runtime | wins in-sample, loses OOS and runtime | clean zero-cost setting still does not clear OOS |
| 10 | `normal_rho0.5_full_hvhm` | wins in-sample, loses OOS and runtime | wins in-sample and runtime, loses OOS | same pattern as other `N=10` costed runs |
| 30 | `logit_rho0.0_full_hvhm` | wins in-sample, loses OOS and runtime | wins in-sample and runtime, loses OOS | runtime gain over `CPBSD-A` is too small to offset OOS loss |
| 30 | `normal_rho0.0_full_hvhm` | wins in-sample and runtime, loses OOS | wins in-sample and runtime, loses OOS | strongest speedup, but severe OOS collapse |
| 30 | `normal_rho0.0_full_zero` | loses all three metrics | wins runtime only, loses both revenue metrics | reject as showcase candidate |
| 30 | `normal_rho0.5_full_hvhm` | wins in-sample and runtime, loses OOS | wins in-sample and runtime, loses OOS | closest trade-off candidate |

## Closest Candidate

The closest current candidate is `N=30, normal_rho0.5_full_hvhm`.

Why it is closest:

- against `BSP`, `FCP-pruned-MB` is `+2.1235` on in-sample revenue and `-288.1668s` on runtime, but `-1.3567` on OOS
- against `CPBSD-A`, `FCP-pruned-MB` is `+1.1320` on in-sample revenue and `-564.8385s` on runtime, but `-2.9625` on OOS
- this is a one-metric blocker case rather than a two-metric failure

The second-best candidate is `N=30, normal_rho0.0_full_hvhm`.

Its profile is similar, but the OOS gap is larger:

- `-3.1383` versus `BSP`
- `-5.0016` versus `CPBSD-A`

## Current Recommendation

- If the story needs a clean full-dominance claim, Phase 2 does not support it.
- If the story can present a trade-off result, use `N=30, normal_rho0.5_full_hvhm` as the lead candidate and state explicitly that the blocker is `Revenue OOS`.
- For the narrative bridge into Phase 3, emphasize that the main failure mode is not in-sample quality or runtime, but OOS menu incompleteness after pruning.
