"""Phase 3 OOS Repair — Path B: Per-bundle pricing on extended menu.

Strategy:
  1. Generate candidate bundles from in-sample customers' top-s prefix bundles.
  2. Build extended menu = FCP anchors + candidates.
  3. Solve MB restricted MILP on extended menu with FCP anchor prices FIXED.
  4. Subadditivity is automatically restricted to the offered menu via
     _restricted_full_partition_families.
  5. Evaluate OOS on the extended menu.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Dict, List, Set, Tuple

import gurobipy as gp
import msgpack
import msgpack_numpy as mnp
import numpy as np
from gurobipy import GRB

from generate_data_CPBSD import sample_valuations, valuation_means
from solve_mb_bsp_on_cpbsd_v2 import (
    _restricted_cover_pair_families,
    _restricted_full_partition_families,
    build_assortments,
    ensure_empty_bundle,
    eval_bsp_policy,
    eval_mb_policy,
    json_default,
    normalize_numeric_keys,
)


# ---------------------------------------------------------------------------
# IO helpers
# ---------------------------------------------------------------------------

def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)

def load_msgpack_with_setup(path: Path):
    with path.open("rb") as f:
        obj = msgpack.load(f, object_hook=mnp.decode, strict_map_key=False)
    v = np.asarray(obj["valuation_samples_V"], dtype=float)
    c = np.asarray(obj["production_cost_c"], dtype=float)
    return obj, v, c

def load_json(path: Path) -> Dict:
    return json.loads(path.read_text(encoding="utf-8"))

def generate_v_out(setup: Dict, k_out: int) -> np.ndarray:
    rng = np.random.default_rng(int(setup["seed"]) + 99991)
    means = valuation_means(int(setup["n_products"]), setup["heterogeneity"])
    return sample_valuations(k=k_out, means=means, family=setup["dist_family"],
                             rho=float(setup["rho"]), rng=rng)


# ---------------------------------------------------------------------------
# Candidate bundle generation
# ---------------------------------------------------------------------------

def generate_top_s_candidates(v_kn: np.ndarray, n_products: int) -> np.ndarray:
    """For each customer and each size s, collect top-s prefix bundle."""
    k_count = v_kn.shape[0]
    candidates: Set[Tuple[int, ...]] = set()
    for k in range(k_count):
        order = np.argsort(-v_kn[k])  # descending by valuation
        bundle = np.zeros(n_products, dtype=int)
        for s in range(1, n_products + 1):
            bundle[order[s - 1]] = 1
            candidates.add(tuple(bundle.tolist()))
    return np.array(sorted(candidates), dtype=int)


# ---------------------------------------------------------------------------
# Extended MB solve with anchor fixing
# ---------------------------------------------------------------------------

def solve_extended_mb(
    v_kn: np.ndarray,
    c_n: np.ndarray,
    assortments: np.ndarray,
    fixed_prices: Dict[int, float],
    time_limit: float = 300.0,
    mip_gap: float = 1e-2,
    output_flag: int = 0,
    subadditivity_mode: str = "full_partition",
) -> Dict:
    """solve_mb_restricted with anchor price equality constraints.

    Args:
        fixed_prices: mapping from ROW INDEX in assortments → price.
            These bundles get p[i] == fixed_price.
    """
    k_count, n_products = v_kn.shape
    assortments = ensure_empty_bundle(assortments, n_products)
    unique_rows = np.unique(assortments.astype(int), axis=0)
    assortments = unique_rows
    bundle_count = assortments.shape[0]
    bundle_cost = (assortments @ c_n).reshape(1, -1)
    costs = np.repeat(bundle_cost, k_count, axis=0)
    revenues = v_kn @ assortments.T
    revenue_ub = float(np.max(revenues))
    weights = np.ones((k_count, 1), dtype=float) / k_count
    active_idx = list(range(1, bundle_count))
    segment_idx = range(k_count)

    bundle_to_index = {tuple(row.tolist()): idx for idx, row in enumerate(assortments)}

    # Reindex fixed_prices to match deduplicated assortments
    fixed_reindexed: Dict[int, float] = {}
    for orig_idx, price in fixed_prices.items():
        key = tuple(assortments[orig_idx].tolist()) if orig_idx < assortments.shape[0] else None
        if key is not None and key in bundle_to_index:
            new_idx = bundle_to_index[key]
            fixed_reindexed[new_idx] = price

    model = gp.Model("ExtendedMB_AnchorFixed")
    p = model.addVars(active_idx, vtype=GRB.CONTINUOUS, lb=0.0, name="p")
    theta = model.addVars(k_count, active_idx, vtype=GRB.BINARY, name="theta")
    surplus = model.addVars(k_count, vtype=GRB.CONTINUOUS, lb=0.0, name="w")
    s_terms = model.addVars(k_count, active_idx, vtype=GRB.CONTINUOUS, name="S")
    profit = model.addVars(k_count, active_idx, vtype=GRB.CONTINUOUS, name="Z")
    payment = model.addVars(k_count, active_idx, vtype=GRB.CONTINUOUS, lb=0.0, name="q")

    model.setObjective(
        gp.quicksum(weights[k, 0] * profit[k, i] for k in segment_idx for i in active_idx),
        GRB.MAXIMIZE,
    )

    # Surplus lower bound
    model.addConstrs(
        (surplus[k] >= revenues[k, i] - p[i] for i in active_idx for k in segment_idx),
        name="surplus_lb",
    )

    # Restricted subadditivity (within offered menu only)
    if subadditivity_mode == "full_partition":
        for i in active_idx:
            for part_no, family in enumerate(
                _restricted_full_partition_families(assortments[i], bundle_to_index)
            ):
                model.addConstr(
                    p[i] <= gp.quicksum(p[j] for j in family),
                    name=f"subadd_{i}_{part_no}",
                )
    elif subadditivity_mode == "predicted_cover_pairwise":
        for i in active_idx:
            for pair_no, family in enumerate(
                _restricted_cover_pair_families(i, assortments)
            ):
                model.addConstr(
                    p[i] <= gp.quicksum(p[j] for j in family),
                    name=f"subadd_cover_{i}_{pair_no}",
                )
    else:
        raise ValueError(f"Unknown subadditivity_mode: {subadditivity_mode}")

    # === Anchor price fixing ===
    for idx, price in fixed_reindexed.items():
        if idx in p:
            model.addConstr(p[idx] == price, name=f"fix_anchor_{idx}")

    # Payment, envy, profit, surplus (same as solve_mb_restricted)
    model.addConstrs(
        (payment[k, i] >= p[i] - revenue_ub * (1 - theta[k, i])
         for i in active_idx for k in segment_idx), name="payment_lb")
    model.addConstrs(
        (payment[k, i] <= p[i] for i in active_idx for k in segment_idx), name="payment_ub")
    model.addConstrs(
        (surplus[k] >= gp.quicksum(revenues[k, i] * theta[j, i] - payment[j, i] for i in active_idx)
         for k in segment_idx for j in segment_idx if j != k), name="envy_like")
    model.addConstrs(
        (profit[k, i] == payment[k, i] - costs[k, i] * theta[k, i]
         for i in active_idx for k in segment_idx), name="profit")
    model.addConstrs(
        (s_terms[k, i] == revenues[k, i] * theta[k, i] - payment[k, i]
         for i in active_idx for k in segment_idx), name="surplus_term")
    model.addConstrs(
        (surplus[k] == gp.quicksum(s_terms[k, i] for i in active_idx)
         for k in segment_idx), name="surplus_sum")
    model.addConstrs(
        (gp.quicksum(theta[k, i] for i in active_idx) <= 1
         for k in segment_idx), name="at_most_one")

    model.setParam("OutputFlag", output_flag)
    model.setParam("MIPGap", mip_gap)
    model.setParam("TimeLimit", time_limit)
    model.update()

    t0 = time.time()
    model.optimize()
    t1 = time.time()

    result = {
        "solver_status": int(model.Status),
        "feasible": model.SolCount > 0,
        "runtime": model.Runtime,
        "wall_time": t1 - t0,
        "mip_gap": float(model.MIPGap) if model.SolCount > 0 else None,
        "objective": float(model.ObjVal) if model.SolCount > 0 else None,
        "model_num_vars": int(model.NumVars),
        "model_num_binvars": int(model.NumBinVars),
        "model_num_constrs": int(model.NumConstrs),
        "bundle_count": bundle_count,
        "anchor_fixed_count": len(fixed_reindexed),
        "candidate_count": bundle_count - 1 - len(fixed_reindexed),
        "assortments": assortments,
        "bundle_prices_full": None,
    }
    if model.SolCount > 0:
        bp = {0: 0.0}
        for i in active_idx:
            bp[i] = float(p[i].X)
        result["bundle_prices_full"] = bp
    return result


# ---------------------------------------------------------------------------
# CLI + main
# ---------------------------------------------------------------------------

def parse_args():
    pa = argparse.ArgumentParser(description="Phase 3 Path B: Extended menu probe.")
    pa.add_argument("--instance-path", type=Path,
        default=Path("/Users/sensen/.openclaw/workspace/domains/revenue-management/"
                      "experiments/cpbsd_fcp_pruned_mb_compare_n10k50_strict300/instances/"
                      "cpbsd_instance_001_N10_K50_normal_rho0.0_full_hvhm.msgpack"))
    pa.add_argument("--fcp-result-path", type=Path,
        default=Path("/Users/sensen/.openclaw/workspace/domains/revenue-management/"
                      "experiments/cpbsd_fcp_pruned_mb_compare_n10k50_strict300/results/"
                      "cpbsd_instance_001_N10_K50_normal_rho0.0_full_hvhm__fcp_pruned_mb.json"))
    pa.add_argument("--bsp-result-path", type=Path,
        default=Path("/Users/sensen/.openclaw/workspace/domains/revenue-management/"
                      "experiments/fcp_mb_phase2_selected_n10_n30_5inst/n10/"
                      "normal_rho0.0_full_hvhm/runs/seed_20260413/results/"
                      "cpbsd_instance_001_N10_K50_normal_rho0.0_full_hvhm__bsp.json"))
    pa.add_argument("--output-root", type=Path,
        default=Path("/Users/sensen/.openclaw/workspace/domains/revenue-management/"
                      "experiments/phase3_oos_extended_menu_probe_n10_normal_rho0.0_full_hvhm_inst001"))
    pa.add_argument("--k-out", type=int, default=5000)
    pa.add_argument("--time-limit", type=float, default=300.0)
    pa.add_argument("--mip-gap", type=float, default=1e-2)
    pa.add_argument("--output-flag", type=int, default=1)
    return pa.parse_args()


def main():
    args = parse_args()
    ensure_dir(args.output_root)
    print("=== Phase 3 Path B: Extended Menu Probe ===")

    # --- Load data ---
    obj, v_kn, c_n = load_msgpack_with_setup(args.instance_path)
    setup = obj["setup"]
    N = int(setup["n_products"])
    fcp_result = load_json(args.fcp_result_path)
    full_assortments = build_assortments(N)
    v_out = generate_v_out(setup, args.k_out)

    # --- Build anchor map (restricted_idx → price) ---
    restricted_assortments = np.asarray(fcp_result["assortments"], dtype=int)
    restricted_prices = normalize_numeric_keys(fcp_result["bundle_prices_full"])

    # --- Baselines ---
    baseline_fcp_oos = float(eval_mb_policy(v_out, c_n, restricted_prices, restricted_assortments))
    baseline_fcp_ins = float(fcp_result["objective"])
    bsp_result = load_json(args.bsp_result_path)
    bsp_oos = float(eval_bsp_policy(v_out, c_n, bsp_result["size_prices"]))

    print(f"N={N}, K_in={v_kn.shape[0]}, K_out={v_out.shape[0]}")
    print(f"FCP anchor count: {restricted_assortments.shape[0]}")
    print(f"Baseline FCP InS:  {baseline_fcp_ins:.6f}")
    print(f"Baseline FCP OOS:  {baseline_fcp_oos:.6f}")
    print(f"BSP OOS:           {bsp_oos:.6f}")

    # --- Generate candidate bundles ---
    all_candidates = generate_top_s_candidates(v_kn, N)
    print(f"\nCandidate bundles from in-sample top-s: {all_candidates.shape[0]}")

    # Build extended assortments: anchor bundles first, then new candidates
    anchor_set: Set[Tuple[int, ...]] = set()
    for row in restricted_assortments:
        anchor_set.add(tuple(row.tolist()))

    new_candidates = []
    for row in all_candidates:
        key = tuple(row.tolist())
        if key not in anchor_set and any(row):  # not anchor, not empty
            new_candidates.append(row)
    new_candidates = np.array(new_candidates, dtype=int) if new_candidates else np.zeros((0, N), dtype=int)
    print(f"New candidates (after removing anchors): {new_candidates.shape[0]}")

    # Extended assortments: anchors + new candidates
    extended = np.vstack([restricted_assortments, new_candidates])
    extended = ensure_empty_bundle(extended, N)
    # Deduplicate
    extended = np.unique(extended.astype(int), axis=0)
    print(f"Extended menu size (after dedup): {extended.shape[0]}")

    # Map anchor bundles to their row index in extended assortments
    ext_lookup = {tuple(row.tolist()): idx for idx, row in enumerate(extended)}
    fixed_prices: Dict[int, float] = {}
    for ridx, row in enumerate(restricted_assortments):
        price = restricted_prices.get(ridx)
        if price is None:
            continue
        key = tuple(row.tolist())
        ext_idx = ext_lookup.get(key)
        if ext_idx is not None and ext_idx != 0:  # skip empty bundle
            fixed_prices[ext_idx] = float(price)

    print(f"Anchor prices to fix: {len(fixed_prices)}")

    # --- Solve extended MB ---
    print("\n--- Solving Extended MB MILP ---")
    solve_result = solve_extended_mb(
        v_kn=v_kn,
        c_n=c_n,
        assortments=extended,
        fixed_prices=fixed_prices,
        time_limit=args.time_limit,
        mip_gap=args.mip_gap,
        output_flag=args.output_flag,
    )

    print(f"\nStatus: {solve_result['solver_status']}, Feasible: {solve_result['feasible']}")
    print(f"Bundles: {solve_result['bundle_count']} (anchors fixed: {solve_result['anchor_fixed_count']}, "
          f"candidates: {solve_result['candidate_count']})")

    payload = {
        "instance_id": args.instance_path.stem,
        "n_products": N,
        "baseline": {"fcp_ins": baseline_fcp_ins, "fcp_oos": baseline_fcp_oos, "bsp_oos": bsp_oos},
        "extended_menu_size": solve_result["bundle_count"],
        "anchor_fixed_count": solve_result["anchor_fixed_count"],
        "candidate_count": solve_result["candidate_count"],
        "solver": {k: solve_result[k] for k in
                   ["solver_status", "feasible", "runtime", "wall_time", "mip_gap",
                    "objective", "model_num_vars", "model_num_binvars", "model_num_constrs"]},
    }

    if solve_result["feasible"]:
        ext_assort = solve_result["assortments"]
        ext_prices = solve_result["bundle_prices_full"]
        ext_ins = float(solve_result["objective"])
        ext_oos = float(eval_mb_policy(v_out, c_n, ext_prices, ext_assort))

        print(f"\n=== RESULTS ===")
        print(f"Extended InS:  {ext_ins:.6f}  (baseline FCP: {baseline_fcp_ins:.6f})")
        print(f"Extended OOS:  {ext_oos:.6f}  (baseline FCP: {baseline_fcp_oos:.6f}, BSP: {bsp_oos:.6f})")
        print(f"OOS delta vs FCP: {ext_oos - baseline_fcp_oos:+.6f}")
        print(f"OOS delta vs BSP: {ext_oos - bsp_oos:+.6f}")

        # Check anchor preservation
        anchor_ok = True
        for ext_idx, fixed_p in fixed_prices.items():
            solved_p = ext_prices.get(ext_idx)
            if solved_p is not None and abs(solved_p - fixed_p) > 1e-6:
                anchor_ok = False
                break
        print(f"Anchor preserved: {anchor_ok}")
        print(f"Solver runtime: {solve_result['runtime']:.2f}s")

        payload["extended_ins"] = ext_ins
        payload["extended_oos"] = ext_oos
        payload["anchor_preserved"] = anchor_ok
    else:
        print("\n*** SOLVER FAILED ***")

    # Write output
    out_path = args.output_root / "extended_menu_probe_summary.json"
    out_path.write_text(json.dumps(payload, indent=2, default=json_default), encoding="utf-8")
    print(f"\nSummary: {out_path}")


if __name__ == "__main__":
    main()
