# MB Literal Appendix C Check

## Goal

This experiment checks whether the current MB solver implementation matches the Mixed Bundling (MB) MILP written in Appendix C of:

- [Component Pricing_Bundle Size Discount:Component Pricing with a Bundle Size Discount.pdf](/Users/sensen/.openclaw/workspace/domains/revenue-management/project-root/参考文献目录/Bundle Pricing/Component Pricing_Bundle Size Discount:Component Pricing with a Bundle Size Discount.pdf)

The immediate questions are:

1. Is our current MB solver formulation materially different from the paper's Appendix C formulation?
2. If we write a literal-transcription solver from Appendix C, does it produce different objectives, prices, or revenues?
3. If differences exist, are they large enough to plausibly explain why our MB reproduction differs from the paper?

## Scope

This folder is only for the Appendix C MB check. It explicitly excludes:

- pooled-setting SAA experiments
- heuristic MB post-processing experiments
- CPBSD solver modifications

## Hypothesis

Working hypothesis before testing:

- The current solver in [solve_mb_bsp_on_cpbsd_v2.py](/Users/sensen/.openclaw/workspace/domains/revenue-management/project-root/code_submission_project/code_submission/src/data/solve_mb_bsp_on_cpbsd_v2.py) is close to the Appendix C / Hanson-Martin formulation.
- Any mismatch, if present, is more likely to come from implementation details than from using a fundamentally different MB model.

The main candidate differences to isolate are:

1. `sum_l y_kl <= 1` in the paper versus `empty bundle + sum_i theta_ki == 1` in our implementation.
2. `j != k` in the paper's envy-like constraints versus including `j = k` in our implementation.
3. Full partition/cover subadditivity in the paper versus pairwise disjoint partition constraints in our implementation.
4. Solver and replay semantics: full price table, tie breaking, and zero-surplus handling.

## Experiment Plan

### Phase 1: Literal Solver Construction

Write a separate solver that follows Appendix C as literally as possible:

- non-empty bundle index set only
- variables: `p_l`, `y_kl`, `q_kl`, `w_k`
- objective and constraints copied directly from Appendix C
- outside option represented by `sum_l y_kl <= 1`
- `j != k` only in envy-like constraints
- subadditivity generated from literal bundle partitions rather than the current engineering simplification

Deliverable:

- `solve_mb_appendix_c_literal.py`

### Phase 2: Solver-to-Solver Comparison

Run the literal solver and the current solver on representative `N=5, K=50` instances and compare:

- solver status
- objective
- in-sample replay revenue
- out-of-sample replay revenue
- selected bundle counts
- bundle-price table distance

Deliverables:

- `comparison_rows.csv`
- `comparison_summary.csv`
- `RESULTS.md`

### Phase 3: Difference Attribution

If the literal solver and current solver differ materially, run ablations to localize the cause:

1. literal outside-option handling versus explicit empty bundle
2. literal envy-like indexing versus current indexing
3. literal subadditivity family versus current pairwise partition family

## Success Criteria

The current implementation will be considered formulation-consistent with Appendix C if, on the tested instances:

- objectives are numerically close after accounting for time limits
- replay revenues are nearly identical
- no systematic price-pattern gap appears

The current implementation will be considered materially different if:

- the literal solver repeatedly finds materially higher or lower in-sample revenue under similar solve budgets
- price tables differ in structured ways across many instances
- the gap persists after controlling for solver time and warm start

## Folder Structure

- `README.md`: experiment design and criteria
- `RESULTS.md`: running notes and conclusions
- `comparison_rows.csv`: per-instance comparison output
- `comparison_summary.csv`: aggregate comparison output

## Notes

- We will start with a small representative instance set before attempting any broader paper-level reproduction.
- The objective of this experiment is diagnosis, not immediate large-scale reruns.
