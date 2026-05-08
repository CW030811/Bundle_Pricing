"""
Anchored FCP+BSP MILP solver.

Stage 1 FCP prices are fixed outside this solver. This second-stage solver
optimizes only BSP size-tier prices beside the fixed FCP menu, with combined
choice/IC constraints and cross-menu anti-arbitrage.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

if not os.environ.get("GRB_LICENSE_FILE") and Path.home().joinpath(".gurobi", "gurobi.lic").exists():
    os.environ["GRB_LICENSE_FILE"] = str(Path.home().joinpath(".gurobi", "gurobi.lic"))

import gurobipy as gp
import numpy as np
from gurobipy import GRB

from solve_mb_bsp_on_cpbsd_v2 import ensure_empty_bundle, normalize_numeric_keys

ANCHORED_FCP_BSP_VERSION = 2


def _bundle_key(row: np.ndarray) -> Tuple[int, ...]:
    return tuple(np.asarray(row, dtype=int).tolist())


def _normalize_assortments_and_prices(
    assortments: np.ndarray,
    fcp_bundle_prices: Dict,
    n_products: int,
) -> Tuple[np.ndarray, Dict[int, float], Dict[int, int]]:
    original = ensure_empty_bundle(np.asarray(assortments, dtype=int), n_products)
    prices = normalize_numeric_keys(fcp_bundle_prices or {})
    if not prices:
        raise ValueError("fcp_bundle_prices must contain fixed FCP prices.")

    price_by_bundle: Dict[Tuple[int, ...], float] = {_bundle_key(np.zeros(n_products, dtype=int)): 0.0}
    for idx, price in prices.items():
        if not isinstance(idx, int):
            continue
        if idx < 0 or idx >= original.shape[0]:
            continue
        price_by_bundle[_bundle_key(original[idx])] = float(price)

    unique = np.unique(original.astype(int), axis=0)
    index_by_bundle = {_bundle_key(row): idx for idx, row in enumerate(unique)}
    old_to_new = {
        old_idx: index_by_bundle[_bundle_key(original[old_idx])]
        for old_idx in range(original.shape[0])
    }

    fixed_prices: Dict[int, float] = {}
    for bundle, price in price_by_bundle.items():
        idx = index_by_bundle.get(bundle)
        if idx is not None:
            fixed_prices[int(idx)] = float(price)
    fixed_prices[index_by_bundle[_bundle_key(np.zeros(n_products, dtype=int))]] = 0.0
    return unique, fixed_prices, old_to_new


def _cross_menu_fcp_splits(
    assortments: np.ndarray,
    active_idx: Iterable[int],
) -> List[Tuple[int, int, int]]:
    active = list(active_idx)
    bundle_sets = {i: set(np.where(assortments[i] == 1)[0].tolist()) for i in active}
    splits: List[Tuple[int, int, int]] = []
    for parent in active:
        parent_set = bundle_sets[parent]
        for child in active:
            if child == parent:
                continue
            child_set = bundle_sets[child]
            if child_set < parent_set:
                splits.append((parent, child, len(parent_set) - len(child_set)))
    return splits


def _bsp_prefix_values_and_costs(v_kn: np.ndarray, c_n: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    k_count, n_products = v_kn.shape
    v_ks = np.zeros((k_count, n_products + 1), dtype=float)
    c_ks = np.zeros((k_count, n_products + 1), dtype=float)
    for k in range(k_count):
        order = np.argsort(-v_kn[k])
        ordered_vals = v_kn[k, order]
        ordered_costs = c_n[order]
        v_ks[k, 1:] = np.cumsum(ordered_vals)
        c_ks[k, 1:] = np.cumsum(ordered_costs)
    return v_ks, c_ks


def solve_anchored_fcp_bsp(
    v_kn: np.ndarray,
    c_n: np.ndarray,
    assortments: np.ndarray,
    fcp_bundle_prices: Dict,
    fcp_chosen_bundle_idx_by_customer=None,
    time_limit: float = 600.0,
    mip_gap: float = 1e-2,
    output_flag: int = 0,
    threads: int = 0,
    protect_fcp_sales: bool = True,
    strict_fcp_sales_protection: bool = True,
) -> dict:
    """Optimize BSP size prices beside fixed FCP bundle prices."""
    v_kn = np.asarray(v_kn, dtype=float)
    c_n = np.asarray(c_n, dtype=float)
    k_count, n_products = v_kn.shape
    max_size = n_products

    assortments, fixed_prices, old_to_new = _normalize_assortments_and_prices(
        assortments=assortments,
        fcp_bundle_prices=fcp_bundle_prices,
        n_products=n_products,
    )
    bundle_count = int(assortments.shape[0])
    bundle_sizes = assortments.sum(axis=1).astype(int)
    v_ki = v_kn @ assortments.T
    c_i = assortments @ c_n

    fcp_active = sorted(
        idx for idx, price in fixed_prices.items()
        if idx != 0 and int(bundle_sizes[idx]) > 0 and price is not None
    )
    if not fcp_active:
        raise ValueError("No non-empty fixed FCP bundle prices were provided.")

    size_idx = range(max_size + 1)
    bsp_active = range(1, max_size + 1)
    segment_idx = range(k_count)
    v_ks, c_ks = _bsp_prefix_values_and_costs(v_kn, c_n)
    cross_splits = _cross_menu_fcp_splits(assortments, fcp_active)

    max_fixed_price = max(float(fixed_prices[i]) for i in fcp_active)
    max_value = max(float(np.max(v_ki[:, fcp_active])), float(np.max(v_ks[:, -1])))
    price_ub = max_fixed_price + max_value + 1.0
    weights = np.ones((k_count, 1), dtype=float) / float(k_count)

    protected_choices: Dict[int, int] = {}
    if protect_fcp_sales and fcp_chosen_bundle_idx_by_customer is not None:
        if len(fcp_chosen_bundle_idx_by_customer) != k_count:
            raise ValueError(
                "fcp_chosen_bundle_idx_by_customer length must match number of customers."
            )
        for k, old_idx in enumerate(fcp_chosen_bundle_idx_by_customer):
            try:
                old_idx_int = int(old_idx)
            except (TypeError, ValueError):
                continue
            new_idx = old_to_new.get(old_idx_int)
            if new_idx in fcp_active:
                protected_choices[k] = int(new_idx)

    model = gp.Model("Anchored_FCP_BSP")
    q_bsp = model.addVars(size_idx, vtype=GRB.CONTINUOUS, lb=0.0, ub=price_ub, name="q_bsp")
    tf = model.addVars(k_count, fcp_active, vtype=GRB.BINARY, name="tf")
    tb = model.addVars(k_count, bsp_active, vtype=GRB.BINARY, name="tb")
    u = model.addVars(k_count, vtype=GRB.CONTINUOUS, lb=0.0, name="u")
    pb = model.addVars(k_count, bsp_active, vtype=GRB.CONTINUOUS, lb=0.0, ub=price_ub, name="pb")

    model.setObjective(
        gp.quicksum(
            weights[k, 0] * (
                gp.quicksum((float(fixed_prices[i]) - float(c_i[i])) * tf[k, i] for i in fcp_active)
                + gp.quicksum(pb[k, s] - float(c_ks[k, s]) * tb[k, s] for s in bsp_active)
            )
            for k in segment_idx
        ),
        GRB.MAXIMIZE,
    )

    model.addConstrs(
        (u[k] >= float(v_ki[k, i]) - float(fixed_prices[i]) for k in segment_idx for i in fcp_active),
        name="c1_surplus_fcp_fixed",
    )
    model.addConstrs(
        (u[k] >= float(v_ks[k, s]) - q_bsp[s] for k in segment_idx for s in bsp_active),
        name="c2_surplus_bsp",
    )
    model.addConstrs(
        (
            gp.quicksum(tf[k, i] for i in fcp_active)
            + gp.quicksum(tb[k, s] for s in bsp_active)
            <= 1
            for k in segment_idx
        ),
        name="c3_one_choice",
    )

    model.addConstrs(
        (pb[k, s] >= q_bsp[s] - price_ub * (1 - tb[k, s]) for k in segment_idx for s in bsp_active),
        name="c4_pay_bsp_lb",
    )
    model.addConstrs(
        (pb[k, s] <= q_bsp[s] for k in segment_idx for s in bsp_active),
        name="c4_pay_bsp_price_ub",
    )
    model.addConstrs(
        (pb[k, s] <= price_ub * tb[k, s] for k in segment_idx for s in bsp_active),
        name="c4_pay_bsp_choice_ub",
    )

    model.addConstrs(
        (
            u[k]
            == gp.quicksum((float(v_ki[k, i]) - float(fixed_prices[i])) * tf[k, i] for i in fcp_active)
            + gp.quicksum(float(v_ks[k, s]) * tb[k, s] - pb[k, s] for s in bsp_active)
            for k in segment_idx
        ),
        name="c5_surplus_sum",
    )

    model.addConstrs(
        (
            u[k]
            >= gp.quicksum((float(v_ki[k, i]) - float(fixed_prices[i])) * tf[j, i] for i in fcp_active)
            + gp.quicksum(float(v_ks[k, s]) * tb[j, s] - pb[j, s] for s in bsp_active)
            for k in segment_idx
            for j in segment_idx
            if j != k
        ),
        name="c6_envy",
    )

    bsp_subadd_count = 0
    for s1 in range(1, max_size + 1):
        for s2 in range(s1, max_size + 1):
            if s1 + s2 <= max_size:
                model.addConstr(q_bsp[s1 + s2] <= q_bsp[s1] + q_bsp[s2], name=f"c7_subadd_bsp_{s1}_{s2}")
                bsp_subadd_count += 1

    for s in range(max_size):
        model.addConstr(q_bsp[s + 1] >= q_bsp[s], name=f"c8_mono_{s}")
    model.addConstr(q_bsp[0] == 0.0, name="c9_q0")

    same_size_count = 0
    for i in fcp_active:
        sz = int(bundle_sizes[i])
        if sz >= 1:
            model.addConstr(q_bsp[sz] >= float(fixed_prices[i]), name=f"c10_same_size_{i}")
            same_size_count += 1

    split_count = 0
    for parent_i, child_j, size_diff in cross_splits:
        if size_diff >= 1:
            model.addConstr(
                float(fixed_prices[parent_i]) <= float(fixed_prices[child_j]) + q_bsp[size_diff],
                name=f"c11_cross_split_{parent_i}_{child_j}",
            )
            split_count += 1

    protection_count = 0
    strict_protection_count = 0
    for k, fcp_idx in protected_choices.items():
        fcp_surplus = float(v_ki[k, fcp_idx]) - float(fixed_prices[fcp_idx])
        for s in bsp_active:
            model.addConstr(
                fcp_surplus >= float(v_ks[k, s]) - q_bsp[s],
                name=f"c12_protect_fcp_{k}_{s}",
            )
            protection_count += 1
            if strict_fcp_sales_protection:
                model.addConstr(tb[k, s] == 0, name=f"c13_strict_protect_fcp_{k}_{s}")
                strict_protection_count += 1

    model.setParam("OutputFlag", output_flag)
    model.setParam("MIPGap", mip_gap)
    model.setParam("TimeLimit", time_limit)
    if int(threads) > 0:
        model.setParam("Threads", int(threads))
    model.update()

    t0 = time.time()
    model.optimize()
    t1 = time.time()

    fixed_prices_out = {int(i): float(p) for i, p in sorted(fixed_prices.items())}
    result = {
        "anchored_fcp_bsp_version": ANCHORED_FCP_BSP_VERSION,
        "solver_status": int(model.Status),
        "feasible": model.SolCount > 0,
        "runtime": float(model.Runtime),
        "wall_time": float(t1 - t0),
        "mip_gap": float(model.MIPGap) if model.SolCount > 0 else None,
        "objective": float(model.ObjVal) if model.SolCount > 0 else None,
        "bundle_prices": None,
        "bundle_prices_full": fixed_prices_out,
        "size_prices": None,
        "assortments": assortments.tolist(),
        "bundle_count": bundle_count,
        "fixed_fcp_bundle_count": len(fcp_active),
        "n_products": n_products,
        "k_count": k_count,
        "price_upper_bound": float(price_ub),
        "same_size_constraint_count": int(same_size_count),
        "cross_split_count": int(split_count),
        "bsp_subadditivity_constraint_count": int(bsp_subadd_count),
        "protect_fcp_sales_requested": bool(protect_fcp_sales),
        "protect_fcp_sales_applied": bool(protection_count > 0),
        "strict_fcp_sales_protection": bool(strict_fcp_sales_protection),
        "strict_protection_constraint_count": int(strict_protection_count),
        "protected_customer_count": int(len(protected_choices)),
        "protection_constraint_count": int(protection_count),
        "protected_bsp_choice_count": None,
        "model_num_vars": int(model.NumVars),
        "model_num_constrs": int(model.NumConstrs),
        "model_num_binvars": int(model.NumBinVars),
        "chosen_option_by_customer": None,
        "choice_summary": None,
    }

    if model.SolCount > 0:
        size_prices = {int(s): float(q_bsp[s].X) for s in size_idx}
        selected_fcp_prices: Dict[int, float] = {}
        chosen = []
        for k in segment_idx:
            choice = ("outside", -1)
            for i in fcp_active:
                if tf[k, i].X >= 1 - 1e-2:
                    choice = ("fcp", int(i))
                    selected_fcp_prices[int(i)] = float(fixed_prices[i])
                    break
            else:
                for s in bsp_active:
                    if tb[k, s].X >= 1 - 1e-2:
                        choice = ("bsp", int(s))
                        break
            chosen.append(choice)

        result["bundle_prices"] = selected_fcp_prices
        result["size_prices"] = size_prices
        result["chosen_option_by_customer"] = chosen
        result["protected_bsp_choice_count"] = int(
            sum(1 for k in protected_choices if chosen[k][0] == "bsp")
        )
        result["choice_summary"] = {
            "fcp": int(sum(1 for c in chosen if c[0] == "fcp")),
            "bsp": int(sum(1 for c in chosen if c[0] == "bsp")),
            "outside": int(sum(1 for c in chosen if c[0] == "outside")),
        }

    return result
