# Large-Instance Run Incomplete

- Detection time: `2026-03-28T14:35:17.086844+08:00`
- Output root: `/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/MB Acceleration/optimize_strategy_exploration`
- Process pattern: `explore_mb_optimize_equivalent_variants.py --time-limit 120 --mip-gap 1e-2`
- Summary file exists: `True`
- Report file exists: `True`
- Raw outputs complete: `False`

The target exploration process is no longer running, but the expected raw result set is incomplete. Per the monitoring rule, this run is treated as incomplete rather than complete.

| scenario_key | existing_variants | missing_variants | complete |
| --- | --- | --- | --- |
| original_mb_full | (none) | current, current_no_self_envy, lean_no_aux, lean_no_aux_no_self_envy | false |
| original_mb_full_hard_tail | (none) | current, current_no_self_envy, lean_no_aux, lean_no_aux_no_self_envy | false |
| gcn_candidate_restricted_mb | lean_no_aux, lean_no_aux_no_self_envy | current, current_no_self_envy | false |

## Interpretation

- Do not treat the current summary files as a completed large-instance verdict.
- The missing raw files must be regenerated before the run can be considered complete.
- If needed, rerun the exploration or investigate why raw outputs disappeared while top-level summary files remained.

