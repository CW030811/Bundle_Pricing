# 2026-W16 FCP-GCN vs CPBSD `cpbsd_main_n5` Weekly Execution Checklist

## 1. Weekly Goal

This week's target is to produce a defensible "best strategy showcase" for the `cpbsd_main_n5` main experiment, centered on the comparison between `FCP-GCN` and `CPBSD`.

The work must answer three concrete questions:

1. Which sample settings among the 405 setups are common enough to be used as the main showcase settings?
2. On those selected setups, can `FCP-GCN` dominate `BSP`, `CPBSD`, and `CPBSD-A` on `Revenue In Sample`, `Revenue OOS`, and `Running Time` after averaging over 5 instances?
3. If `FCP-GCN` suffers an OOS revenue drop, can we repair the missing bundle prices on top of the in-sample pruned bundle space without breaking required pricing constraints?

## 2. Scope And Ground Rules

- Main reference experiment: `experiments/cpbsd_main_n5`
- OOS-drop reference experiment: `experiments/mb_oos_drop_grid_n5_n10_t300`
- Comparison methods: `BSP`, `CPBSD`, `CPBSD-A`, `FCP-GCN`
- Core metrics:
  - `Revenue In Sample`
  - `Revenue OOS`
  - `Running Time`
- Setup definition:
  - marginal distribution
  - correlation structure
  - heterogeneity
  - cost scenario

Before Phase 2 starts, freeze the exact naming map between paper terminology and repository terminology. In particular, explicitly document which repo runner/result name corresponds to `CPBSD-A` and which one corresponds to `FCP-GCN`.

## 3. Success Definition

### 3.1 Dominance Rule

For one selected setup, `FCP-GCN` is counted as dominating a baseline method if, on the 5-instance average:

- `Revenue In Sample(FCP-GCN) >= Revenue In Sample(baseline)`
- `Revenue OOS(FCP-GCN) >= Revenue OOS(baseline)`
- `Running Time(FCP-GCN) <= Running Time(baseline)`
- At least one of the three comparisons is strictly better

If the team wants to use a numerical tolerance, define it once before batch evaluation and write it into the result table header. Do not change the tolerance after seeing the results.

### 3.2 Weekly Acceptable Outcome

This week's work is accepted if all of the following are true:

- A shortlist of "common" setups is frozen with written rationale.
- Every shortlisted setup has a 5-instance averaged comparison table for all four methods, or a clear failure log explaining why not.
- A dominance conclusion is written for each shortlisted setup.
- The OOS-drop hypothesis is tested with at least one repair strategy.
- The final output clearly states one of the following:
  - a setup where `FCP-GCN` dominates on all three target metrics
  - no full-dominance setup was found, but the best trade-off setup is identified and justified

## 4. Work Breakdown

### Phase 1. Screen The 405 Setups And Freeze A Shortlist

**Objective**

Reduce the full CPBSD setup space to a small, defensible set of common settings for the main comparison.

**Checklist**

- [x] Enumerate the 405 setups into a structured inventory.
- [x] Normalize the four setup dimensions into a single naming convention.
- [x] Mark which setup names are actually available in the current repository and experiment scripts.
- [x] Define the selection rule for "common" setups.
- [x] Produce a shortlist with priority levels such as `P0` and `P1`.
- [x] For each selected setup, write one-line justification.
- [x] Freeze the shortlist before starting large-scale averaging runs.

**Required Outputs**

- `setup_inventory.md`
- `setup_shortlist.md`
- `paper_repo_naming_map.md`

**Acceptance Standard**

- Every shortlisted setup includes exact values for all four dimensions.
- Every shortlisted setup has a rationale, not just a name.
- The shortlist is small enough to run this week and broad enough to support a main-story comparison.
- Any candidate such as `normal` or `logit` must use the actual repo/script naming as the source of truth.

### Phase 2. Run 5-Instance Average Comparisons On The Shortlist

**Objective**

Build a clean, apples-to-apples comparison of `BSP`, `CPBSD`, `CPBSD-A`, and `FCP-GCN` on revenue and runtime.

**Execution Rules**

- Use the same 5 instances for all four methods under the same setup.
- Keep hardware, timeout policy, and seed policy fixed across methods.
- Record raw values first, then compute averages.
- Keep failed runs in the table; do not silently drop them.

**Checklist**

- [x] Freeze the exact 5 instance IDs for each selected setup.
- [x] Run `BSP` on all selected setup-instance pairs.
- [ ] Run `CPBSD` on all selected setup-instance pairs.
- [x] Run `CPBSD-A` on all selected setup-instance pairs.
- [x] Run `FCP-GCN` on all selected setup-instance pairs.
- [x] Collect raw `Revenue In Sample`, `Revenue OOS`, and `Running Time`.
- [ ] Compute per-setup mean and spread statistics.
- [x] Mark dominance outcome against each baseline.
- [x] Rank shortlisted setups by showcase value.

**Required Outputs**

- `comparison_raw.(csv|json)`
- `comparison_avg.(csv|md)`
- `dominance_summary.md`

**Acceptance Standard**

- Each selected setup has 5 matched instances across all four methods, or every missing run is explicitly explained.
- The averaging table includes all three target metrics.
- The dominance judgment is reproducible from the recorded table.
- If no setup achieves full dominance, the report must still identify:
  - the closest candidate
  - the blocking metric
  - whether the blocker is `OOS`, runtime, or in-sample revenue

### Phase 3. Repair The OOS Drop For FCP-GCN

**Objective**

Test whether the OOS revenue drop comes from passing only the pruned bundle space from in-sample to OOS, and whether missing bundle prices can be repaired in a principled way.

**Current Working Hypothesis**

`FCP-GCN` prunes bundles and prices only the pruned bundle space in-sample. When this solution is transferred to OOS, some new customers cannot find bundles satisfying their IC constraints in the reduced priced bundle space, which leads to OOS revenue loss relative to a fuller bundle space.

**Repair Direction**

Start from the in-sample FCP-pruned bundle space, then use a `CPBSD`-style or `BSP`-style completion rule to price previously unpriced bundles for OOS evaluation while keeping required pricing constraints.

**Checklist**

- [ ] Quantify the OOS drop on the shortlisted setups before repair.
- [x] Confirm which bundles are unpriced after the in-sample prune-and-price step.
- [x] Design at least one bundle-space completion rule for OOS.
- [x] Verify the repaired prices respect required conditions such as price feasibility and subadditivity.
- [x] Re-run OOS evaluation with the repaired bundle space.
- [x] Compare pre-repair vs post-repair revenue and runtime overhead.
- [ ] Decide whether the repair is suitable for the final showcase.

**Required Outputs**

- `oos_drop_hypothesis.md`
- `oos_repair_design.md`
- `oos_repair_results.(csv|md)`

**Acceptance Standard**

- The repair logic is documented well enough to reproduce.
- Constraint checks are written down and actually applied.
- The before/after comparison is reported on the same shortlisted setups.
- If OOS improves but runtime worsens, the trade-off is stated explicitly.
- If the repair fails, the failure mode is documented and the baseline showcase decision is still made.

## 4.4 Current Acceptance Snapshot

Snapshot date: `2026-04-14`

Verified Phase 2 facts:

- batch root: [fcp_mb_phase2_selected_n10_n30_5inst](/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/fcp_mb_phase2_selected_n10_n30_5inst)
- batch finished at `2026-04-14 01:02:46`
- `8/8` setting-size pairs produced `aggregate_metrics.json`
- `8/8` setting-size pairs produced `comparison_summary_all.csv`
- matched seed policy is frozen by script as `20260413` to `20260417`

Current document set:

- [comparison_avg.md](/Users/sensen/.openclaw/workspace/domains/revenue-management/research-tracker/weekly-reports/2026-W16-fcp-gcn-vs-cpbsd-main-n5/comparison_avg.md)
- [comparison_avg.csv](/Users/sensen/.openclaw/workspace/domains/revenue-management/research-tracker/weekly-reports/2026-W16-fcp-gcn-vs-cpbsd-main-n5/comparison_avg.csv)
- [dominance_summary.md](/Users/sensen/.openclaw/workspace/domains/revenue-management/research-tracker/weekly-reports/2026-W16-fcp-gcn-vs-cpbsd-main-n5/dominance_summary.md)
- [phase3_oos_logic_note.md](/Users/sensen/.openclaw/workspace/domains/revenue-management/research-tracker/weekly-reports/2026-W16-fcp-gcn-vs-cpbsd-main-n5/phase3_oos_logic_note.md)
- [phase3_probe_results.md](/Users/sensen/.openclaw/workspace/domains/revenue-management/research-tracker/weekly-reports/2026-W16-fcp-gcn-vs-cpbsd-main-n5/phase3_probe_results.md)
- [phase3_variant_exploration.md](/Users/sensen/.openclaw/workspace/domains/revenue-management/research-tracker/weekly-reports/2026-W16-fcp-gcn-vs-cpbsd-main-n5/phase3_variant_exploration.md)

Current verdict:

- `Phase 2` is a verified three-method result for `BSP`, `CPBSD-A`, and `FCP-pruned-MB`
- no full-dominance setup was found
- the closest trade-off candidates are `N=30, normal_rho0.5_full_hvhm` and `N=30, normal_rho0.0_full_hvhm`
- the blocking metric is consistently `Revenue OOS`
- weekly acceptance is still `PARTIAL` against the original README target because `CPBSD` was not included in this batch and spread statistics are not yet summarized here
- `Phase 3` probe work is also `PARTIAL`: the OOS-drop mechanism is validated and first repair variants were tested, but the current probes are still on a fixed diagnostic instance rather than the full shortlisted batch

## 5. Progress Board

Update this section whenever a batch finishes.

| Module | Status | Owner | Next Action | Output Needed |
| --- | --- | --- | --- | --- |
| Phase 1 setup screening | `DONE` | `shared` | use frozen shortlist for Phase 2 matched runs | shortlist + rationale |
| Phase 2 batch comparison | `PARTIAL` | `shared` | decide whether to add `CPBSD` / spread stats or freeze scope as a 3-method result | average table + dominance summary |
| Phase 3 OOS repair | `PARTIAL` | `shared` | test the next repair candidate on shortlisted settings or explicitly close as negative evidence | before/after table |
| Final showcase packaging | `IN_PROGRESS` | `shared` | package the trade-off story around the OOS blocker | weekly summary artifacts |

## 6. End-Of-Week Deliverables

By the end of the week, the folder should support a final presentation with:

- one frozen shortlist of showcase-worthy setups
- one averaged comparison table across `BSP`, `CPBSD`, `CPBSD-A`, `FCP-GCN`
- one clear statement on whether full dominance exists
- one written conclusion on the OOS-drop repair attempt
- one final recommended setup for "best strategy showcase"

## 7. Decision Rules

- If Phase 1 cannot justify too many setups, reduce scope and prioritize story clarity over coverage.
- If Phase 2 finds no full-dominance setup, do not force a win claim; present the strongest trade-off case instead.
- If Phase 3 improves OOS but destroys runtime advantage, classify it as a trade-off result rather than a clean fix.
- If repository naming and paper naming conflict, the repo naming used in executed experiments is the source of truth, and the mapping must be written down.

## 8. Suggested Files To Maintain In This Folder

Recommended structure for follow-up updates:

- `README.md`: master checklist and acceptance criteria
- `setup_shortlist.md`: frozen shortlist and rationale
- `setup_inventory.md`: inventory definition and canonical naming
- `paper_repo_naming_map.md`: paper term <-> repo term mapping
- `comparison_avg.csv`: averaged comparison table
- `dominance_summary.md`: per-setup dominance conclusions
- `oos_repair_design.md`: repair method description
- `oos_repair_results.md`: before/after repair summary
