"""Backup of the pre-Appendix MB formulation.

This module preserves the legacy MB solve path used before the Appendix C
alignment:
  - explicit empty bundle / equality one-choice
  - envy-like constraints including j = k
  - pairwise 2-way subadditivity

Use this only for diagnostics or historical reproduction. Active
experiments should import `solve_mb_bsp_on_cpbsd.py` or
`solve_mb_bsp_on_cpbsd_v2.py`.
"""

import argparse
import json
import time
from pathlib import Path
from typing import Dict

import gurobipy as gp
import numpy as np
from gurobipy import GRB

from solve_mb_bsp_on_cpbsd_v2 import (
    MB_FORMULATION_VERSION,
    _disjoint_partition_pairs,
    build_assortments,
    eval_bsp_policy,
    eval_mb_policy,
    json_default,
    load_instance,
    normalize_numeric_keys,
    solve_bsp as _solve_bsp_appendix,
)


LEGACY_MB_FORMULATION_TAG = "explicit_empty+include_self_envy+pairwise"


def solve_mb(v_kn: np.ndarray, c_n: np.ndarray, time_limit: float = 300.0, mip_gap: float = 1e-2, output_flag: int = 0):
    k_count, n_products = v_kn.shape
    assortments = build_assortments(n_products)
    bundle_count = assortments.shape[0]
    revenues = v_kn @ assortments.T
    bundle_cost = assortments @ c_n
    revenue_ub = float(np.max(revenues))
    weights = np.ones((k_count, 1), dtype=float) / k_count
    active_idx = list(range(bundle_count))

    model = gp.Model("Bundle_MILP_legacy_current")
    p = model.addVars(active_idx, vtype=GRB.CONTINUOUS, lb=0.0, name="p")
    theta = model.addVars(k_count, active_idx, vtype=GRB.BINARY, name="theta")
    surplus = model.addVars(k_count, vtype=GRB.CONTINUOUS, name="w")
    s_terms = model.addVars(k_count, active_idx, vtype=GRB.CONTINUOUS, name="S")
    profit = model.addVars(k_count, active_idx, vtype=GRB.CONTINUOUS, name="Z")
    payment = model.addVars(k_count, active_idx, vtype=GRB.CONTINUOUS, lb=0.0, name="q")

    model.setObjective(
        gp.quicksum(weights[k, 0] * profit[k, i] for k in range(k_count) for i in active_idx),
        GRB.MAXIMIZE,
    )

    model.addConstrs(
        (surplus[k] >= float(revenues[k, i]) - p[i] for k in range(k_count) for i in active_idx),
        name="surplus_lb",
    )
    for i in active_idx:
        if i == 0:
            continue
        for pair_idx, (m1, m2) in enumerate(_disjoint_partition_pairs(assortments[i])):
            model.addConstr(p[i] <= p[m1] + p[m2], name=f"subadd_pair_{i}_{pair_idx}")
    model.addConstrs(
        (payment[k, i] >= p[i] - revenue_ub * (1 - theta[k, i]) for k in range(k_count) for i in active_idx),
        name="payment_lb",
    )
    model.addConstrs(
        (payment[k, i] <= p[i] for k in range(k_count) for i in active_idx),
        name="payment_ub",
    )
    model.addConstrs(
        (profit[k, i] == payment[k, i] - float(bundle_cost[i]) * theta[k, i] for k in range(k_count) for i in active_idx),
        name="profit",
    )
    model.addConstrs(
        (s_terms[k, i] == float(revenues[k, i]) * theta[k, i] - payment[k, i] for k in range(k_count) for i in active_idx),
        name="surplus_term",
    )
    model.addConstrs(
        (surplus[k] == gp.quicksum(s_terms[k, i] for i in active_idx) for k in range(k_count)),
        name="surplus_sum",
    )
    model.addConstrs(
        (gp.quicksum(theta[k, i] for i in active_idx) == 1 for k in range(k_count)),
        name="one_choice",
    )
    model.addConstrs((s_terms[k, 0] == 0 for k in range(k_count)), name="empty_bundle")
    model.addConstrs(
        (
            surplus[k] >= gp.quicksum(float(revenues[k, i]) * theta[j, i] - payment[j, i] for i in active_idx)
            for k in range(k_count)
            for j in range(k_count)
        ),
        name="envy_include_self",
    )

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
        "mb_formulation_version": MB_FORMULATION_VERSION,
        "mb_formulation_tag": LEGACY_MB_FORMULATION_TAG,
        "runtime": model.Runtime,
        "wall_time": t1 - t0,
        "mip_gap": float(model.MIPGap) if model.SolCount > 0 else None,
        "objective": float(model.ObjVal) if model.SolCount > 0 else None,
        "revenue_in_sample": None,
        "model_num_vars": int(model.NumVars),
        "model_num_binvars": int(model.NumBinVars),
        "model_num_constrs": int(model.NumConstrs),
        "bundle_prices": None,
        "bundle_prices_full": None,
        "bundle_prices_selected": None,
        "chosen_bundle_idx_by_customer": None,
        "assortments": assortments,
    }
    if model.SolCount > 0:
        bundle_prices_full = {0: 0.0}
        bundle_prices_selected = {}
        chosen = []
        for i in active_idx:
            bundle_prices_full[i] = float(p[i].X)
        for k in range(k_count):
            chosen_i = 0
            for i in active_idx:
                if theta[k, i].X >= 1 - 1e-2:
                    chosen_i = int(i)
                    break
            chosen.append(chosen_i)
        for i in active_idx:
            if any(choice == i for choice in chosen):
                bundle_prices_selected[i] = float(p[i].X)
        result["bundle_prices"] = bundle_prices_full
        result["bundle_prices_full"] = bundle_prices_full
        result["bundle_prices_selected"] = bundle_prices_selected
        result["chosen_bundle_idx_by_customer"] = chosen
        result["revenue_in_sample"] = float(eval_mb_policy(v_kn, c_n, bundle_prices_full, assortments))
    return result


def solve_bsp(v_kn: np.ndarray, c_n: np.ndarray, time_limit: float = 300.0, mip_gap: float = 1e-2, output_flag: int = 0):
    return _solve_bsp_appendix(v_kn, c_n, time_limit=time_limit, mip_gap=mip_gap, output_flag=output_flag)


def eval_mb_out_of_sample(v_kn: np.ndarray, c_n: np.ndarray, bundle_prices: Dict, assortments: np.ndarray) -> float:
    return eval_mb_policy(v_kn, c_n, bundle_prices, assortments)


def eval_bsp_out_of_sample(v_kn: np.ndarray, c_n: np.ndarray, size_prices: Dict) -> float:
    return eval_bsp_policy(v_kn, c_n, size_prices)


def _json_clean_dict(d: Dict) -> Dict:
    return {str(k): v for k, v in normalize_numeric_keys(d).items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--instance", required=True)
    ap.add_argument("--method", choices=["mb", "bsp"], required=True)
    ap.add_argument("--time-limit", type=float, default=300.0)
    ap.add_argument("--mip-gap", type=float, default=1e-2)
    ap.add_argument("--output-flag", type=int, default=0)
    ap.add_argument("--save-json", type=str, default="")
    args = ap.parse_args()

    v_kn, c_n = load_instance(Path(args.instance))
    if args.method == "mb":
        res = solve_mb(v_kn, c_n, time_limit=args.time_limit, mip_gap=args.mip_gap, output_flag=args.output_flag)
        for key in ("bundle_prices", "bundle_prices_full", "bundle_prices_selected"):
            if isinstance(res.get(key), dict):
                res[key] = _json_clean_dict(res[key])
    else:
        res = solve_bsp(v_kn, c_n, time_limit=args.time_limit, mip_gap=args.mip_gap, output_flag=args.output_flag)
        if isinstance(res.get("size_prices"), dict):
            res["size_prices"] = _json_clean_dict(res["size_prices"])

    text = json.dumps(res, ensure_ascii=False, indent=2, default=json_default)
    print(text)
    if args.save_json:
        Path(args.save_json).write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
