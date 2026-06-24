# BSP vs FCP OOS Behavior on `cpbsd_instance_001_N10_K50_normal_rho0.0_full_hvhm`

## Scope

This note answers four concrete questions:

1. How `BSP` and `FCP-MB` differ in `In Sample` solve space, exported policy, and `OOS` evaluation space.
2. Why `BSP` performs much better than `FCP-MB` on `OOS`, using `cpbsd_instance_001_N10_K50_normal_rho0.0_full_hvhm.msgpack`.
3. For customers who do purchase under `FCP` in `OOS`, how `FCP` profit quality compares with `BSP`.
4. What `no purchase` means in practice, using `customer 0` as a concrete menu-level example.

Supporting outputs:

- Instance comparison summary: [summary.md](/Users/sensen/.openclaw/workspace/domains/revenue-management/research-tracker/weekly-reports/2026-W16-fcp-gcn-vs-cpbsd-main-n5/instance001_bsp_fcp_compare/summary.md)
- Raw summary: [summary.json](/Users/sensen/.openclaw/workspace/domains/revenue-management/research-tracker/weekly-reports/2026-W16-fcp-gcn-vs-cpbsd-main-n5/instance001_bsp_fcp_compare/summary.json)
- In-sample customer-level comparison: [customer_comparison_in_sample.csv](/Users/sensen/.openclaw/workspace/domains/revenue-management/research-tracker/weekly-reports/2026-W16-fcp-gcn-vs-cpbsd-main-n5/instance001_bsp_fcp_compare/customer_comparison_in_sample.csv)
- OOS customer-level comparison: [customer_comparison_oos.csv](/Users/sensen/.openclaw/workspace/domains/revenue-management/research-tracker/weekly-reports/2026-W16-fcp-gcn-vs-cpbsd-main-n5/instance001_bsp_fcp_compare/customer_comparison_oos.csv)

## 1. In-Sample and OOS Computation Mechanisms

### BSP

`In Sample` solve space:

- `BSP` does not solve over explicit `2^N` bundle identities.
- It solves over `size` prices `p[s]` for `s = 0, 1, ..., N`.
- Under additive valuations, for each customer and each size `s`, the relevant candidate bundle is that customer's own top-`s` prefix bundle.
- This is the core compression used by the Appendix-C-aligned implementation in [solve_mb_bsp_on_cpbsd_v2.py](/Users/sensen/.openclaw/workspace/domains/revenue-management/project-root/code_submission_project/code_submission/src/data/solve_mb_bsp_on_cpbsd_v2.py:413).

`In Sample` export:

- The solver creates variables for all sizes `0..N`.
- But when exporting the policy, it keeps only sizes that were actually chosen by at least one in-sample customer.
- This sparse export is implemented here: [solve_mb_bsp_on_cpbsd_v2.py](/Users/sensen/.openclaw/workspace/domains/revenue-management/project-root/code_submission_project/code_submission/src/data/solve_mb_bsp_on_cpbsd_v2.py:492).

`OOS` evaluation space:

- `OOS` uses only the exported size-price map.
- For each customer, it recomputes that customer's own top-`s` prefix bundles and evaluates only sizes that exist in the exported map.
- This logic is implemented in [solve_mb_bsp_on_cpbsd_v2.py](/Users/sensen/.openclaw/workspace/domains/revenue-management/project-root/code_submission_project/code_submission/src/data/solve_mb_bsp_on_cpbsd_v2.py:236).

Interpretation:

- `BSP` is sparse in `size`, but not sparse in customer-specific bundle identity.
- A single exported size still implicitly offers a different exact bundle to different customers.

### FCP-MB

`In Sample` solve space:

- `FCP-MB` first uses the GCN output thresholding rule to generate candidate bundles.
- Those bundles form a restricted explicit assortment matrix.
- The downstream `MB` pricing solve is then run only on that pruned bundle set.
- The candidate bundle generation and restricted `MB` solve are in [run_cpbsd_fcp_pruned_mb_compare.py](/Users/sensen/.openclaw/workspace/domains/revenue-management/project-root/code_submission_project/code_submission/src/data/run_cpbsd_fcp_pruned_mb_compare.py:118) and [run_cpbsd_fcp_pruned_mb_compare.py](/Users/sensen/.openclaw/workspace/domains/revenue-management/project-root/code_submission_project/code_submission/src/data/run_cpbsd_fcp_pruned_mb_compare.py:266).

`In Sample` export:

- The exported result contains prices for all bundles in the restricted assortment matrix.
- In this instance, that means `37` explicitly priced bundles.

`OOS` evaluation space:

- `OOS` does not recover the full `2^N` bundle space.
- It reuses the in-sample exported restricted assortment matrix and its prices.
- This is visible in [run_cpbsd_fcp_pruned_mb_compare.py](/Users/sensen/.openclaw/workspace/domains/revenue-management/project-root/code_submission_project/code_submission/src/data/run_cpbsd_fcp_pruned_mb_compare.py:280) and the evaluator [solve_mb_bsp_on_cpbsd_v2.py](/Users/sensen/.openclaw/workspace/domains/revenue-management/project-root/code_submission_project/code_submission/src/data/solve_mb_bsp_on_cpbsd_v2.py:73).

Interpretation:

- `FCP-MB` is sparse in explicit bundle identity.
- If a bundle is not in the pruned menu, `OOS` customers cannot choose it.

### Key Difference

Both methods export an `in-sample chosen only` sparse policy, but the sparsity is structurally different:

- `BSP`: sparse in `size`, still rich in customer-specific exact bundle choice.
- `FCP-MB`: sparse in explicit bundle identity, which causes hard menu-coverage loss in `OOS`.

## 2. Why BSP OOS Is Better Than FCP on This Instance

Instance:

- `cpbsd_instance_001_N10_K50_normal_rho0.0_full_hvhm.msgpack`
- setup:
  - `N = 10`
  - `K = 50`
  - `dist_family = normal`
  - `rho = 0.0`
  - `heterogeneity = full`
  - `cost_scenario = hvhm`

### Exported policy structure

`BSP` exported sizes:

- `[0, 2, 3, 4, 5, 6, 7, 8, 9, 10]`

So on this instance, `BSP` only drops `size = 1`.

`FCP-MB` exported menu:

- `37` explicit bundles
- size support present in the menu:
  - `[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]`

So `FCP` covers all sizes, but only a very small subset of bundle identities.

### Aggregate OOS result

From [summary.json](/Users/sensen/.openclaw/workspace/domains/revenue-management/research-tracker/weekly-reports/2026-W16-fcp-gcn-vs-cpbsd-main-n5/instance001_bsp_fcp_compare/summary.json):

- `BSP` OOS average profit: `2.4505`
- `FCP` OOS average profit: `2.3990`

### Outside-option counts

`In Sample` with `50` customers:

- `BSP` outside option count: `6`
- `FCP` outside option count: `3`

`OOS` with `5000` customers:

- `BSP` outside option count: `1210`
- `FCP` outside option count: `1544`

So in `OOS`, `FCP` sends `334` more customers to outside option than `BSP`.

### Conversion asymmetry

`OOS` customer comparison:

- `BSP` purchases and `FCP` does not: `533`
- `FCP` purchases and `BSP` does not: `199`

This is the main reason `BSP` beats `FCP` in `OOS` average profit on this instance.

### Why this happens

For the `533` customers where `BSP` purchases and `FCP` does not:

- In `331` cases, the exact `BSP` chosen bundle is not in the `FCP` menu at all.
- In the remaining cases, the bundle may be present, but `FCP` still fails to provide a positive-surplus option.

So the main mechanism is:

- `BSP` wins on menu coverage.
- `FCP` loses customers because its restricted explicit menu does not generalize well enough to `OOS`.

This does not mean `BSP` is always better customer-by-customer. It means `BSP` preserves a broader feasible choice set after export.

## 3. Profit Quality on Customers Who Do Buy Under FCP in OOS

This is the key nuance.

If we condition only on customers who actually buy under `FCP` in `OOS`, then `FCP` has higher profit quality than `BSP`.

Among `FCP` buyers in `OOS`:

- `FCP` buyer count: `3456`
- `FCP` average profit on those buyers: `3.4708`
- `BSP` average profit on those same buyers: `3.0857`

Among customers where both methods buy:

- count: `3257`
- `FCP` average profit: `3.5802`
- `BSP` average profit: `3.2742`

Customer-level win count on the set of `FCP` buyers:

- `FCP profit > BSP profit`: `2584`
- `BSP profit > FCP profit`: `872`

Interpretation:

- `FCP` is not weak because it extracts low profit from served customers.
- On customers it can serve, `FCP` is usually better monetized than `BSP`.
- `FCP` loses in aggregate `OOS` because it fails to serve enough customers, not because its conditional pricing quality is poor.

So the clean summary is:

- `BSP` wins on `coverage`.
- `FCP` wins on `conditional profit quality`.

## 4. Customer 0: Why No Purchase Happens Under FCP

The important clarification is:

- Even if the `BSP`-chosen bundle is not in the `FCP` menu, the customer still considers every bundle that `FCP` does provide.
- `FCP no purchase` means that every nonempty bundle in the exported `FCP` menu has non-positive surplus, so outside option `q0` wins.

### Customer 0 under BSP

From [customer_comparison_oos.csv](/Users/sensen/.openclaw/workspace/domains/revenue-management/research-tracker/weekly-reports/2026-W16-fcp-gcn-vs-cpbsd-main-n5/instance001_bsp_fcp_compare/customer_comparison_oos.csv):

- `BSP` chosen bundle: `0000000111`
- size: `3`
- value: `27.514632`
- price: `27.322819`
- surplus: `0.191813`
- profit: `1.989485`
- this exact bundle is not in the `FCP` menu

### Customer 0 under FCP

For `customer 0`, the exported `FCP` menu has `37` bundles. The menu-level evaluation result is:

- positive-surplus bundle count: `0`
- nonnegative-surplus bundle count: `1`
- the only nonnegative-surplus option is outside option:
  - `0000000000`
  - surplus `0.0`

Top `FCP` menu options for `customer 0`:

```text
1. 0000000000  size=0   value=0.000000   price=0.000000   surplus= 0.000000   profit=0.000000
2. 0010000011  size=3   value=22.503186  price=22.522814  surplus=-0.019628   profit=1.967259
3. 0010011111  size=6   value=43.283719  price=43.361902  surplus=-0.078183   profit=3.206347
4. 1110011111  size=8   value=46.103035  price=46.544311  surplus=-0.441275   profit=3.833200
5. 1110111111  size=9   value=50.357724  price=51.124353  surplus=-0.766628   profit=3.791020
6. 0100000000  size=1   value= 1.746620  price= 2.529293  surplus=-0.782673   profit=0.773737
```

Interpretation:

- `BSP`'s preferred exact bundle is missing from the `FCP` menu.
- But the deeper reason for `FCP no purchase` is stronger:
  - even after considering all `37` available `FCP` bundles,
  - the best nonempty option still has negative surplus,
  - so outside option remains optimal.

## Final Takeaway

This instance shows that `BSP` and `FCP-MB` both export sparse policies, but the sparsity is not equally damaging in `OOS`.

- `BSP` exports a sparse size scaffold, which still lets each customer access a personalized top-`s` bundle.
- `FCP-MB` exports a sparse explicit bundle menu, which causes hard identity-level menu loss.

On this instance:

- `FCP` is stronger in `In Sample`
- `FCP` has higher profit quality on customers it does serve in `OOS`
- `BSP` wins overall in `OOS` because it leaves fewer customers with no viable purchase option

That is the main practical diagnosis behind the `OOS drop`.
