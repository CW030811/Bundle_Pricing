# Phase 3 OOS Logic Note

## 1. Purpose

This note freezes the current understanding of `FCP-MB` out-of-sample evaluation logic and defines the Phase 3 repair direction.

The practical question is:

`Does current FCP-MB OOS evaluation keep only the in-sample pruned bundle space, and if so, how should we repair the missing bundle prices without destroying the value of the FCP candidate filter?`

## 2. Current Conclusion

### 2.1 Bottom Line

Yes. The current `FCP-MB` OOS logic still evaluates only on the pruned bundle space.

More precisely:

- `FCP-MB` first uses the GCN/FCP pipeline to generate a restricted candidate assortment set
- the restricted MB solver prices bundles only on that candidate assortment set
- OOS revenue is then replayed only on that restricted assortment table
- bundles pruned out in-sample remain unavailable in OOS

So the current implementation does **not** restore the full `2^N` bundle space before OOS revenue is computed.

### 2.2 Code Evidence

Active OOS evaluation path:

- [run_cpbsd_fcp_pruned_mb_compare.py](/Users/sensen/.openclaw/workspace/domains/revenue-management/project-root/code_submission_project/code_submission/src/data/run_cpbsd_fcp_pruned_mb_compare.py:280)
- [run_cpbsd_single_setting_mb_ref_matrix.py](/Users/sensen/.openclaw/workspace/domains/revenue-management/project-root/code_submission_project/code_submission/src/data/run_cpbsd_single_setting_mb_ref_matrix.py:1030)
- [solve_mb_bsp_on_cpbsd_v2.py](/Users/sensen/.openclaw/workspace/domains/revenue-management/project-root/code_submission_project/code_submission/src/data/solve_mb_bsp_on_cpbsd_v2.py:73)

What these paths do:

- OOS evaluation calls `eval_mb_policy(v_out, c_n, bundle_prices, assortments)`
- `eval_mb_policy` loops only over the provided `assortments`
- `assortments` comes from the restricted candidate set produced by `solve_mb_restricted`

Restricted-solve output path:

- [solve_mb_bsp_on_cpbsd_v2.py](/Users/sensen/.openclaw/workspace/domains/revenue-management/project-root/code_submission_project/code_submission/src/data/solve_mb_bsp_on_cpbsd_v2.py:285)

Important clarification:

- the field `bundle_prices_full` in the restricted solver means “full prices over the current restricted assortment index set”
- it does **not** mean “prices for the global full bundle space”

This naming is easy to misread, so Phase 3 should treat it carefully.

## 3. Problem Statement For Phase 3

Current working hypothesis:

- `FCP-MB` gets a high-quality in-sample candidate bundle space
- after solving on that reduced space, many bundles outside the pruned set remain unpriced
- in OOS, some customers would prefer bundles outside the pruned set, but these bundles are absent from evaluation
- this creates avoidable OOS revenue loss and may also distort incentive structure relative to a fuller bundle space

Phase 3 therefore targets:

`Keep the in-sample value of FCP pruning, but repair OOS by completing prices on the missing bundle space in a principled way.`

## 4. Phase 3 Goal

### 4.1 Main Goal

Start from the in-sample `FCP` pruned bundle space and the bundle prices already solved there.

Then:

- complete prices for bundles in the full bundle space that are currently unpriced
- do not change bundle prices already set by `FCP-MB`
- preserve the core economic consistency of the final full bundle price table
- re-evaluate OOS revenue on the completed full bundle space

### 4.2 Success Standard

Phase 3 is useful if at least one repair rule can do all of the following:

- keep existing `FCP` priced bundles fixed
- produce a valid completed price table on the full bundle space
- improve `Revenue OOS` relative to the current restricted-space replay
- add only moderate runtime overhead compared with the current `FCP-MB`

## 5. Design Principle

The design should separate the problem into two layers.

Layer 1:

- `FCP` is responsible for identifying a high-quality in-sample candidate bundle space
- this is the main acceleration and signal-extraction step

Layer 2:

- a completion rule is responsible for filling missing prices outside the pruned set
- this is the OOS stabilization step

This means Phase 3 should not “undo” FCP. It should **couple** FCP with a conservative completion mechanism.

## 6. Proposed Repair Direction

### 6.1 Core Idea

Use the in-sample `FCP` solution as an anchor, then borrow the pricing structure idea of `BSP` to complete missing bundles in the full bundle space.

Intuition:

- `FCP` gives bundle-specific high-value signals on a small subset
- `BSP` gives a simple and globally defined size-based pricing scaffold

So the repair should combine:

- `FCP` for trusted anchor prices on selected bundles
- `BSP` for extrapolation or completion on unpriced bundles

### 6.2 Non-Negotiable Constraints

Any completion rule must satisfy:

- already-priced `FCP` bundles remain unchanged
- the completed full bundle space remains economically meaningful
- the replay rule in OOS still corresponds to valid surplus maximization over the now-completed bundle menu

At minimum, the final completed menu should respect:

- `Surplus Maximization`
- `Subadditivity`

Depending on formulation choice, we may also need:

- bundle price nonnegativity
- empty bundle price fixed at `0`
- bundle prices not below cost, if we want explicit feasibility floors

## 7. Mathematical Formulation Sketch

Let:

- `A_F` be the pruned bundle set selected by `FCP`
- `P_F(S)` be the fixed in-sample price for every `S in A_F`
- `A_full` be the full bundle space
- `P(S)` be the completed price table on `A_full`

We want:

- `P(S) = P_F(S)` for all `S in A_F`
- choose `P(S)` for all `S in A_full \\ A_F`

### 7.1 Hard Anchor Constraints

For all `S in A_F`:

- `P(S) = P_F(S)`

This is the key coupling requirement. Phase 3 must not reoptimize away the FCP prices.

### 7.2 BSP-Style Completion Scaffold

Introduce size-based auxiliary variables:

- `q_s` for bundle size `s = 0, 1, ..., N`

A minimal BSP-style completion rule for missing bundles can start from:

- `P(S) = q_|S|` for bundles outside `A_F`

while keeping:

- `P(S) = P_F(S)` for bundles inside `A_F`

This creates a hybrid menu:

- anchored bundle-specific prices on `A_F`
- size-based fallback prices on unselected bundles

### 7.3 Subadditivity Constraint

For all bundles `S, T`:

- `P(S ∪ T) <= P(S) + P(T)`

This is important because once we complete the full bundle space, prices across selected and unselected bundles must remain jointly coherent.

In the hybrid formulation, these constraints now couple:

- anchored `FCP` prices
- unknown BSP-style fallback prices

This is exactly where the formulation work is nontrivial.

### 7.4 Surplus-Maximization Semantics

Strictly speaking, surplus maximization is the downstream customer choice rule, not a linear constraint on prices by itself.

What we need operationally is:

- a completed bundle menu such that OOS customers can choose the highest-surplus bundle from the full menu
- this replay should be run on the completed full bundle space, not the restricted one

So the implementation change is:

- today: `eval_mb_policy(..., restricted_assortments)`
- target: `eval_mb_policy(..., full_assortments_completed)`

## 8. Candidate Repair Variants

The Phase 3 scope is now explicitly restricted to:

- do **not** modify the current `FCP-MB` in-sample solve
- do **not** replace `FCP` with a new hybrid mechanism
- do **not** use hand-crafted fallback pricing

The repair must be:

- post-solve
- post-hoc
- OOS-only
- based on the compressed `BSP` structure rather than full `2^N` reoptimization

### Variant A: Anchored BSP Projection

Definition:

- keep all `FCP` bundle prices fixed on the selected set `A_F`
- introduce size-price variables `q_s` for `s = 0, ..., N`
- for every missing bundle `S notin A_F`, set completed price `P(S) = q_|S|`
- compute `q_s` by solving a projection problem onto the `BSP` price family

The key point is that this variant uses the actual `BSP` compression idea:

- under additive valuations, `BSP` only needs one price per bundle size
- therefore the completion layer has only `N+1` pricing variables, not `2^N`

Suggested objective:

- fit `q_s` as closely as possible to the `BSP` size prices obtained on the same in-sample instance

Hard constraints:

- anchor preservation: `P(S) = P_F(S)` for all `S in A_F`
- `q_0 = 0`
- monotonicity of `q_s`
- size-subadditivity of `q_s`
- global subadditivity coupling between anchor bundles and missing bundles

Pros:

- cleanest first principled repair
- uses the same compression property that makes `BSP` computationally attractive

Risks:

- the hard anchor prices may be incompatible with any globally valid size-price scaffold
- the projection problem can become infeasible

### Variant B: Anchored BSP Projection With Relaxed Coupling

Definition:

- keep the same post-hoc OOS-only structure as Variant A
- still use only size-price variables `q_s`
- still keep `FCP` anchor bundle prices fixed
- but replace the most expensive full pairwise coupling layer with a reduced or relaxed coupling system derived from anchor bundles and size relations

This variant still uses the `BSP` compression property:

- the completion variables remain `q_s`
- the difference lies only in how strongly the scaffold is coupled to the fixed anchor bundles

Possible reduced coupling rules include:

- anchor-to-size envelope constraints
- subset/superset anchor coupling constraints
- compressed size-level consistency conditions implied by anchor bundles

Pros:

- still compressed
- easier to solve than a fully coupled projection
- may be more robust when Variant A is too rigid

Risks:

- may fail to enforce global subadditivity on the full bundle space
- must be validated by an explicit post-check on the completed menu

## 9. Recommended Implementation Order

### Step 1

Freeze the exact current logic and terminology.

Deliverable:

- this note

### Step 2

Implement the smallest repairable OOS evaluator.

Meaning:

- keep current `FCP-MB` restricted solve unchanged
- after solve, build the full bundle space
- solve a compressed `BSP`-style completion layer for missing bundles
- replay OOS on the completed full bundle space

### Step 3

Start with the strictest compressed repair that still matches the current scope.

Recommendation:

- begin with `Variant A`
- if `Variant A` is infeasible or too brittle, test `Variant B`
- in both variants, keep all FCP-selected bundle prices fixed
- in both variants, preserve the current in-sample logic exactly

### Step 4

Only after the minimal test shows signal, decide whether the compressed coupling needs refinement.

That refinement should still remain:

- post-hoc
- OOS-only
- anchored on the existing FCP solution
- compressed in the style of `BSP`

## 10. Minimal Validation Plan

Before doing a large batch, run one minimal honest test.

Suggested first test:

- setting: `normal_rho0.0_full_hvhm`
- scale: `N=10`, `K=50`
- one existing seed from the current Phase 2 experiment line

Compare:

- current restricted OOS replay
- completed full-space OOS replay with `Variant A`
- completed full-space OOS replay with `Variant B`

Record:

- `Revenue In Sample`
- `Revenue OOS`
- runtime overhead of completion
- number of missing bundles completed
- whether anchor prices stayed unchanged
- whether any subadditivity check failed

### Minimum Acceptance For The First Test

The first prototype is worth extending if:

- OOS improves on the same fixed instance
- the repaired menu keeps all FCP-priced bundles unchanged
- no obvious consistency violation appears in the completed menu

## 11. Immediate Next Engineering Task

The next implementation task should be:

`Create a repair-only evaluator that takes an existing FCP result, reconstructs the full bundle space, solves compressed BSP-style completion variants for missing bundles, checks anchor preservation and subadditivity, and compares repaired vs unrepaired OOS revenue on one fixed instance.`

That is the right smallest test because it isolates the OOS-completion hypothesis before we redesign the whole solver.
