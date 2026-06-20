# Random-Valuation Pipeline — `Z` lower-bound fix, full re-run (reproduction reference)

This folder is a **self-contained re-run of the random-valuation (additive CPBSD)
experiments with one solver bug fixed**, kept separate from the original scripts so
the two can be compared and so others can reproduce it. **No original file is
modified**; the affected scripts are copied here with a minimal `ZFIX` edit.

Created on the `main` worktree (`/Users/sensen/.openclaw/workspace`, the
revenue-management home). Do **not** confuse with the `baseline/trading-assistant-current`
branch, which belongs to a different project.

---

## 1. The bug

In the mixed-bundling MILP and the bundle-size-pricing MILP, the per-(customer,bundle)
**profit variable `Z` is created without a lower bound**, so Gurobi defaults it to
`lb = 0`:

| Canonical file (unmodified) | Line | Variable |
|---|---|---|
| `src/data/solve_mb_bsp_on_cpbsd_v2.py` | 316 | `profit = addVars(..., name="Z")`  → `solve_mb_restricted` (MB / FCP engine) |
| `src/data/solve_mb_bsp_on_cpbsd_v2.py` | 442 | `profit = addVars(..., name="Z")`  → `solve_bsp` |
| `src/data/generate_data_MB.py` | 27 | `Z = addVars(m, B, ..., name='Z')` (deterministic-MB label gen) |
| `src/data/generate_data_BSP.py` | 94 | same pattern |

With `profit[k,i] == payment[k,i] - cost[k,i]*theta[k,i]` and the chosen bundle
forcing `payment = p[i]`, the default `lb=0` imposes **`p[i] ≥ cost[i]` for every
chosen bundle** — a constraint that is *not* part of the mixed-bundling problem. It
can cut off the true optimum whenever production costs are positive (it is **inert at
zero cost**, where `cost=0` makes `p≥cost` equal to the existing `p≥0`).

`solve_cpbsd_a.py` (CPBSD-A) is **not affected**: its profit is formed directly in the
objective (`q - c·y`), with no clamped `Z` variable.

The `name="S"` / `name="w"` / `name="surplus"` variables with `lb=0` are **intentional**
(individual rationality and zeroing non-chosen payments) and are left unchanged.

### Why it matters for the whole pipeline
`label_cpbsd_mb_from_manifest.py` calls `solve_mb` → `solve_mb_restricted` (the L316
bug), so the **GNN training labels** themselves were produced under the constrained MB.
The main experiment's **FCP** (`solve_mb_restricted`) and **BSP** (`solve_bsp`) columns
are likewise affected; **CPBSD-A is not**.

### Empirical evidence (label generation)
Re-labelling 20 N=5 `random_ind` instances with the fixed solver vs. the original labels:
**8/20 chosen-bundle matrices changed**, objective improved in 7 (max +0.63%, the one
−0.0036 is within the 1e-2 MIP gap). So the fix is real and binds on positive-cost data.

## 2. The fix
Add `lb=-GRB.INFINITY` to the `Z`/`profit` variable in both solvers — see
`code/solve_mb_bsp_on_cpbsd_v2_zfix.py:320` and `:448` (search `ZFIX`).

## 3. Folder layout
```
code/    z-fixed + supporting scripts (copies; originals untouched)
  solve_mb_bsp_on_cpbsd_v2_zfix.py     MB + BSP solver, Z lb fixed
  label_cpbsd_mb_from_manifest_zfix.py label gen, imports the zfix solver
  solve_cpbsd_a.py                     CPBSD-A (unchanged; no bug)
  generate_data_CPBSD.py               instance generator (unchanged)
  Training_multi_layer_cpbsd_mb_x.py   Hanson edge-GCN training (unchanged)
  cpbsd_hanson_gcn_graph.py            label-free Hanson graph builder (inference)
  run_experiment_zfix.py               FCP/BSP/CPBSD-A sweep (added next)
labels/{train,eval,test}/  re-generated MB labels (chosen_product_matrix)
models/                    retrained Hanson checkpoint
results/                   comparison CSV/JSON + before/after report
logs/                      run logs
```

## 4. Reproduction commands
```bash
RM=/Users/sensen/.openclaw/workspace/domains/revenue-management
PY=$RM/.venv-cpbsd-gcn/bin/python            # torch 2.8.0, torch_geometric 2.6.1, gurobipy
cd $RM/random_valuation_zfix_repro_20260619

# (1) Re-generate MB labels with the fixed solver (re-uses the tracked N=5 instances)
$PY code/label_cpbsd_mb_from_manifest_zfix.py \
    --manifest $RM/experiments/cpbsd_random_ind_n5/results/manifest_train__mb_results.csv \
    --out-dir labels/train --mip-gap 0.01 --time-limit 300
#   (eval / test analogously)

# (2) Retrain the Hanson edge-GCN on the fixed labels  -> models/
# (3) Run the FCP / BSP / CPBSD-A sweep (N=10,30 x zero/random_ind/random_corr x 5 seeds) -> results/
```

## 5. Provenance
Scripts copied from the canonical tree
`project-root/code_submission_project/code_submission/src/data/` on `main`.
Original (buggy) Table-5 numbers and the audited invariant runs are the comparison
baseline; CPBSD-A results are reused (provably unaffected by this fix), FCP and BSP are
re-run.
