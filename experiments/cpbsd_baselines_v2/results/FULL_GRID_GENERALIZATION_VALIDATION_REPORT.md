# MB/BSP Full-Grid Generalization Validation Report

**Date**: 2026-03-29
**Scope**: compare the completed 405-instance full-grid MB/BSP run against the earlier smoke baseline (`smoke_subset_v2`)

## Source note

- Smoke baseline metrics in this report are recomputed from [unified_log.csv](/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/cpbsd_baselines_v2/unified_log.csv).
- Full-grid metrics come from the completed 405-instance run summary that was observed during acceptance:
  - instances: `405`
  - rows: `810`
  - methods: `BSP`, `MB`
  - MB status counts: `337 OPTIMAL`, `68 TIME_LIMIT`
- The original full-grid artifact directory is not present in the current worktree anymore, so this report uses the captured aggregate summary values rather than re-reading the vanished `comparison_details.json`.

## Experiment scopes

### Smoke baseline

- Root: [cpbsd_baselines_v2](/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/cpbsd_baselines_v2)
- Setting: `N=5`, `K=50`, `normal`, `rho=0.0`, `full`, `hvhm`
- Instances: `5`

### Full-grid run

- Completed scope: `135` settings = `5 distributions x 3 rho x 3 heterogeneity x 3 cost`
- Setting size: `N=5`, `K=50`
- Instances per setting: `3`
- Total instances: `405`

## Aggregate comparison

| Scope | Method | Instances | Status | Avg Rev-In | Avg Rev-Out | Avg Runtime (s) | Avg In-Sample Ratio to BSP | OOS Revenue / BSP OOS | Generalization Drop |
| --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Smoke | BSP | 5 | OPTIMAL 5 | 1.3077 | 1.0989 | 0.94 | 1.0000 | 1.0000 | 15.42% |
| Smoke | MB | 5 | OPTIMAL 3, TIME_LIMIT 2 | 1.6120 | 1.1598 | 258.28 | 1.2355 | 1.0570 | 27.83% |
| Full-grid | BSP | 405 | OPTIMAL 405 | 5.2159 | 4.7517 | 0.73 | 1.0000 | 1.0000 | 8.90% |
| Full-grid | MB | 405 | OPTIMAL 337, TIME_LIMIT 68 | 5.6942 | 4.7752 | 91.08 | 1.3462 | 1.0050 | 16.14% |

## What changed relative to smoke

### 1. MB generalization improved materially

- Smoke MB drop: `27.83%`
- Full-grid MB drop: `16.14%`
- Improvement: `-11.70 pct`

Interpretation:
- The earlier smoke result was a single hard setting (`normal`, `rho=0.0`, `full`, `hvhm`).
- Once we average over the paper-style 135 settings, MB still overfits, but the gap is much smaller.

### 2. MB's out-of-sample advantage over BSP nearly disappears after aggregation

- Smoke MB vs BSP on OOS revenue: `1.0570x`
- Full-grid MB vs BSP on OOS revenue: `1.0050x`

Interpretation:
- In the smoke setting, MB kept a visible OOS edge over BSP.
- In the full-grid aggregate, MB's OOS edge is almost flat.
- This suggests the paper-style aggregate is much less favorable to strong MB OOS dominance than the smoke subset initially implied.

### 3. Full-grid MB is much cheaper to solve on average than the smoke slice

- Smoke MB runtime: `258.28s`
- Full-grid MB runtime: `91.08s`

Interpretation:
- The smoke slice is not only harder to generalize on; it is also much harder to solve.
- The full-grid mix evidently contains many easier parameter settings.

### 4. BSP also generalizes better in the full-grid aggregate

- Smoke BSP drop: `15.42%`
- Full-grid BSP drop: `8.90%`

Interpretation:
- The smoke slice is a pessimistic view for both MB and BSP, not just MB.
- This reinforces the point that the smoke version should be treated as a stress case, not as a representative average over the paper grid.

## Validation takeaways

1. The smoke version was directionally useful as a stress test, but it overstated the average MB generalization problem versus the 405-instance paper-style aggregate.
2. The full-grid aggregate supports a more nuanced conclusion: MB still has noticeable in-sample fitting power, but its out-of-sample edge over BSP is very small once all paper settings are pooled.
3. If we care about worst-case or hard-setting behavior, the smoke slice remains important.
4. If we care about paper-style average behavior, the 405-instance full-grid run is the better reference.

## Recommendation

- Use the smoke version when discussing failure mode intensity and overfitting risk under difficult settings.
- Use the 405-instance full-grid result when discussing paper-style average generalization.
- Do not mix the two without explicitly labeling the scope, because they tell different stories.
