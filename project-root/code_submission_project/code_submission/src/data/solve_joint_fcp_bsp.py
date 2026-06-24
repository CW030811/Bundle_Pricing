"""
Joint FCP+BSP MILP solver.

Simultaneously optimizes FCP anchor bundle prices and BSP size-tier prices
with cross-menu anti-arbitrage constraints. See plan for full formulation (C1-C14).
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Dict, List, Tuple

if not os.environ.get("GRB_LICENSE_FILE") and Path.home().joinpath(".gurobi", "gurobi.lic").exists():
    os.environ["GRB_LICENSE_FILE"] = str(Path.home().joinpath(".gurobi", "gurobi.lic"))

import gurobipy as gp
import numpy as np
from gurobipy import GRB

from solve_mb_bsp_on_cpbsd_v2 import (
    build_assortments,
    ensure_empty_bundle,
    normalize_numeric_keys,
)


def _cross_menu_fcp_splits(
    assortments: np.ndarray, active_idx: List[int]
) -> List[Tuple[int, int, int]]:
    """For each (parent, child) pair in active_idx where child ⊂ parent,
    yield (parent_idx, child_idx, size_difference)."""
    bundle_sets = {i: set(np.where(assortments[i])[0]) for i in active_idx}
    splits = []
    for i in active_idx:
        si = bundle_sets[i]
        for j in active_idx:
            if j == i:
                continue
            sj = bundle_sets[j]
            if sj < si:  # strict subset
                splits.append((i, j, len(si) - len(sj)))
    return splits


def solve_joint_fcp_bsp(
    v_kn: np.ndarray,
    c_n: np.ndarray,
    assortments: np.ndarray,
    time_limit: float = 600.0,
    mip_gap: float = 1e-2,
    output_flag: int = 0,
    threads: int = 0,
    cross_mode: str = "fcp_le_bsp",
) -> dict:
    k_count, n_products = v_kn.shape
    max_size = n_products

    # --- Precompute FCP data ---
    assortments = ensure_empty_bundle(assortments, n_products)
    assortments = np.unique(assortments.astype(int), axis=0)
    bundle_count = assortments.shape[0]
    bundle_sizes = assortments.sum(axis=1).astype(int)

    v_ki = v_kn @ assortments.T  # (K, B)
    c_i = assortments @ c_n  # (B,)

    active_idx = list(range(1, bundle_count))
    segment_idx = range(k_count)

    # --- Precompute BSP data ---
    size_idx = range(max_size + 1)  # 0..N
    bsp_active = range(1, max_size + 1)  # 1..N
    v_ks = np.zeros((k_count, max_size + 1), dtype=float)
    c_ks = np.zeros((k_count, max_size + 1), dtype=float)
    for k in range(k_count):
        order = np.argsort(-v_kn[k])
        pv, pc = 0.0, 0.0
        for s in range(1, max_size + 1):
            idx = order[s - 1]
            pv += v_kn[k, idx]
            pc += c_n[idx]
            v_ks[k, s] = pv
            c_ks[k, s] = pc

    # --- Cross-menu split pairs ---
    cross_splits = _cross_menu_fcp_splits(assortments, active_idx)

    # --- Big-M ---
    revenue_ub = max(float(np.max(v_ki)), float(np.max(v_ks[:, -1]))) + 1.0
    weights = np.ones((k_count, 1), dtype=float) / k_count

    # ===================================================================
    # Build Gurobi model
    # ===================================================================
    model = gp.Model("Joint_FCP_BSP")

    # Decision variables
    p_fcp = model.addVars(active_idx, vtype=GRB.CONTINUOUS, lb=0.0, name="p_fcp")
    q_bsp = model.addVars(size_idx, vtype=GRB.CONTINUOUS, lb=0.0, name="q_bsp")

    tf = model.addVars(k_count, active_idx, vtype=GRB.BINARY, name="tf")
    tb = model.addVars(k_count, bsp_active, vtype=GRB.BINARY, name="tb")

    u = model.addVars(k_count, vtype=GRB.CONTINUOUS, lb=0.0, name="u")

    pf = model.addVars(k_count, active_idx, vtype=GRB.CONTINUOUS, lb=0.0, name="pf")
    pb = model.addVars(k_count, bsp_active, vtype=GRB.CONTINUOUS, lb=0.0, name="pb")

    sf = model.addVars(k_count, active_idx, vtype=GRB.CONTINUOUS, name="sf")
    sb = model.addVars(k_count, bsp_active, vtype=GRB.CONTINUOUS, name="sb")

    zf = model.addVars(k_count, active_idx, vtype=GRB.CONTINUOUS, name="zf")
    zb = model.addVars(k_count, bsp_active, vtype=GRB.CONTINUOUS, name="zb")

    # Objective
    model.setObjective(
        gp.quicksum(
            weights[k, 0] * (
                gp.quicksum(zf[k, i] for i in active_idx)
                + gp.quicksum(zb[k, s] for s in bsp_active)
            )
            for k in segment_idx
        ),
        GRB.MAXIMIZE,
    )

    # (C1) Surplus LB — FCP
    model.addConstrs(
        (u[k] >= v_ki[k, i] - p_fcp[i] for k in segment_idx for i in active_idx),
        name="c1_surplus_fcp",
    )

    # (C2) Surplus LB — BSP
    model.addConstrs(
        (u[k] >= v_ks[k, s] - q_bsp[s] for k in segment_idx for s in bsp_active),
        name="c2_surplus_bsp",
    )

    # (C3) Single choice across combined menu
    model.addConstrs(
        (
            gp.quicksum(tf[k, i] for i in active_idx)
            + gp.quicksum(tb[k, s] for s in bsp_active)
            <= 1
            for k in segment_idx
        ),
        name="c3_one_choice",
    )

    # (C4) Payment linearization — FCP
    model.addConstrs(
        (pf[k, i] >= p_fcp[i] - revenue_ub * (1 - tf[k, i]) for k in segment_idx for i in active_idx),
        name="c4_pay_fcp_lb",
    )
    model.addConstrs(
        (pf[k, i] <= p_fcp[i] for k in segment_idx for i in active_idx),
        name="c4_pay_fcp_ub",
    )

    # (C5) Payment linearization — BSP
    model.addConstrs(
        (pb[k, s] >= q_bsp[s] - revenue_ub * (1 - tb[k, s]) for k in segment_idx for s in bsp_active),
        name="c5_pay_bsp_lb",
    )
    model.addConstrs(
        (pb[k, s] <= q_bsp[s] for k in segment_idx for s in bsp_active),
        name="c5_pay_bsp_ub",
    )

    # (C6) Surplus decomposition
    model.addConstrs(
        (sf[k, i] == v_ki[k, i] * tf[k, i] - pf[k, i] for k in segment_idx for i in active_idx),
        name="c6_sf",
    )
    model.addConstrs(
        (sb[k, s] == v_ks[k, s] * tb[k, s] - pb[k, s] for k in segment_idx for s in bsp_active),
        name="c6_sb",
    )
    model.addConstrs(
        (
            u[k] == gp.quicksum(sf[k, i] for i in active_idx)
            + gp.quicksum(sb[k, s] for s in bsp_active)
            for k in segment_idx
        ),
        name="c6_surplus_sum",
    )

    # (C7) Envy-free (IC)
    model.addConstrs(
        (
            u[k] >= gp.quicksum(v_ki[k, i] * tf[j, i] - pf[j, i] for i in active_idx)
            + gp.quicksum(v_ks[k, s] * tb[j, s] - pb[j, s] for s in bsp_active)
            for k in segment_idx
            for j in segment_idx
            if j != k
        ),
        name="c7_envy",
    )

    # (C8) Profit terms
    model.addConstrs(
        (zf[k, i] == pf[k, i] - c_i[i] * tf[k, i] for k in segment_idx for i in active_idx),
        name="c8_profit_fcp",
    )
    model.addConstrs(
        (zb[k, s] == pb[k, s] - c_ks[k, s] * tb[k, s] for k in segment_idx for s in bsp_active),
        name="c8_profit_bsp",
    )

    # (C9) FCP internal subadditivity — bundle-space pairwise cover
    # For each bundle i, find all pairs (j1, j2) in the provided bundle space
    # such that S_i ⊆ S_j1 ∪ S_j2, and add p_i <= p_j1 + p_j2.
    # This is O(B^3) — tractable for any N.
    from solve_mb_bsp_on_cpbsd_v2 import _restricted_cover_pair_families
    for i in active_idx:
        for pair_no, (j1, j2) in enumerate(
            _restricted_cover_pair_families(i, assortments)
        ):
            model.addConstr(
                p_fcp[i] <= p_fcp[j1] + p_fcp[j2],
                name=f"c9_subadd_fcp_{i}_{pair_no}",
            )

    # (C10) BSP internal subadditivity
    for s1 in range(1, max_size + 1):
        for s2 in range(s1, max_size + 1):
            if s1 + s2 <= max_size:
                model.addConstr(
                    q_bsp[s1 + s2] <= q_bsp[s1] + q_bsp[s2],
                    name=f"c10_subadd_bsp_{s1}_{s2}",
                )

    # (C11) BSP monotonicity
    for s in range(max_size):
        model.addConstr(q_bsp[s + 1] >= q_bsp[s], name=f"c11_mono_{s}")

    # (C12) Cross-menu: FCP vs BSP same-size (controlled by cross_mode)
    if cross_mode == "fcp_le_bsp":
        # Original C12: p_i <= q_{|S_i|}
        for i in active_idx:
            sz = int(bundle_sizes[i])
            if sz >= 1:
                model.addConstr(p_fcp[i] <= q_bsp[sz], name=f"c12_cross_sz_{i}")
    elif cross_mode == "bsp_ge_fcp":
        # C12-rev: q_s >= p_i for all i with |S_i| = s
        for i in active_idx:
            sz = int(bundle_sizes[i])
            if sz >= 1:
                model.addConstr(q_bsp[sz] >= p_fcp[i], name=f"c12rev_cross_sz_{i}")
    # cross_mode == "none": no C12 constraint

    # (C13) Cross-menu: FCP split anti-arbitrage
    for parent_i, child_j, size_diff in cross_splits:
        if size_diff >= 1:
            model.addConstr(
                p_fcp[parent_i] <= p_fcp[child_j] + q_bsp[size_diff],
                name=f"c13_cross_split_{parent_i}_{child_j}",
            )

    # (C14) Boundary
    model.addConstr(q_bsp[0] == 0.0, name="c14_q0")

    # --- Solver params ---
    model.setParam("OutputFlag", output_flag)
    model.setParam("MIPGap", mip_gap)
    model.setParam("TimeLimit", time_limit)
    if int(threads) > 0:
        model.setParam("Threads", int(threads))
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
        "bundle_prices": None,
        "bundle_prices_full": None,
        "size_prices": None,
        "assortments": assortments.tolist(),
        "bundle_count": bundle_count,
        "n_products": n_products,
        "k_count": k_count,
        "cross_split_count": len(cross_splits),
        "model_num_vars": model.NumVars,
        "model_num_constrs": model.NumConstrs,
        "model_num_binvars": model.NumBinVars,
    }

    if model.SolCount > 0:
        # Extract FCP prices
        bundle_prices_full = {0: 0.0}
        bundle_prices_selected = {}
        for i in active_idx:
            price = float(p_fcp[i].X)
            bundle_prices_full[i] = price
            chosen_any = any(tf[k, i].X >= 1 - 1e-2 for k in segment_idx)
            if chosen_any:
                bundle_prices_selected[i] = price

        # Extract BSP prices
        size_prices = {}
        for s in size_idx:
            price = float(q_bsp[s].X)
            size_prices[s] = price

        # Extract customer choices
        chosen = []
        for k in segment_idx:
            choice = ("outside", -1)
            for i in active_idx:
                if tf[k, i].X >= 1 - 1e-2:
                    choice = ("fcp", i)
                    break
            else:
                for s in bsp_active:
                    if tb[k, s].X >= 1 - 1e-2:
                        choice = ("bsp", s)
                        break
            chosen.append(choice)

        fcp_count = sum(1 for c in chosen if c[0] == "fcp")
        bsp_count = sum(1 for c in chosen if c[0] == "bsp")
        outside_count = sum(1 for c in chosen if c[0] == "outside")

        result["bundle_prices"] = bundle_prices_selected
        result["bundle_prices_full"] = bundle_prices_full
        result["size_prices"] = size_prices
        result["chosen_option_by_customer"] = chosen
        result["choice_summary"] = {
            "fcp": fcp_count,
            "bsp": bsp_count,
            "outside": outside_count,
        }

    return result
