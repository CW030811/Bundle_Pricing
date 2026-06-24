from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Tuple

import gurobipy as gp
import msgpack
import msgpack_numpy as mnp
import numpy as np
from gurobipy import GRB

from solve_mb_bsp_on_cpbsd_v2 import build_assortments, normalize_numeric_keys


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def load_msgpack_with_setup(path: Path) -> Tuple[Dict, np.ndarray, np.ndarray]:
    with path.open("rb") as f:
        obj = msgpack.load(f, object_hook=mnp.decode, strict_map_key=False)
    return obj, np.asarray(obj["valuation_samples_V"], dtype=float), np.asarray(obj["production_cost_c"], dtype=float)


def load_json(path: Path) -> Dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_anchor_prices(fcp_result: Dict, full_assortments: np.ndarray) -> Dict[int, float]:
    restricted_assortments = np.asarray(fcp_result["assortments"], dtype=int)
    restricted_prices = normalize_numeric_keys(fcp_result.get("bundle_prices_full") or {})
    full_lookup = {tuple(row.tolist()): idx for idx, row in enumerate(full_assortments)}
    anchor_prices: Dict[int, float] = {}
    for ridx, bundle in enumerate(restricted_assortments):
        price = restricted_prices.get(ridx)
        if price is None:
            continue
        full_idx = full_lookup[tuple(bundle.tolist())]
        anchor_prices[full_idx] = float(price)
    return anchor_prices


def solve_bsp_all_prices(
    v_kn: np.ndarray,
    c_n: np.ndarray,
    time_limit: float = 300.0,
    mip_gap: float = 1e-3,
    output_flag: int = 0,
) -> Dict[int, float]:
    k_count, n_products = v_kn.shape
    max_size = n_products
    size_idx = range(max_size + 1)
    segment_idx = range(k_count)
    revenue_ub = float(np.max(np.sum(np.sort(v_kn, axis=1)[:, ::-1], axis=1)))
    weights = np.ones((k_count, 1), dtype=float) / k_count

    v_ks = np.zeros((k_count, max_size + 1), dtype=float)
    c_ks = np.zeros((k_count, max_size + 1), dtype=float)
    for k in segment_idx:
        order = np.argsort(-v_kn[k])
        ordered_vals = v_kn[k, order]
        ordered_costs = c_n[order]
        v_ks[k, 1:] = np.cumsum(ordered_vals)
        c_ks[k, 1:] = np.cumsum(ordered_costs)

    model = gp.Model("Phase3_BSP_All_Prices_Diagnostic")
    p = model.addVars(max_size + 1, vtype=GRB.CONTINUOUS, lb=0.0, name="p")
    theta = model.addVars(k_count, max_size + 1, vtype=GRB.BINARY, name="theta")
    payment = model.addVars(k_count, max_size + 1, vtype=GRB.CONTINUOUS, lb=0.0, name="P")
    surplus_term = model.addVars(k_count, max_size + 1, vtype=GRB.CONTINUOUS, lb=0.0, name="S")
    profit = model.addVars(k_count, max_size + 1, vtype=GRB.CONTINUOUS, name="Z")
    surplus = model.addVars(k_count, vtype=GRB.CONTINUOUS, name="surplus")

    model.setObjective(
        gp.quicksum(weights[k, 0] * profit[k, size] for k in segment_idx for size in size_idx),
        GRB.MAXIMIZE,
    )
    model.addConstrs((surplus[k] >= v_ks[k, size] - p[size] for k in segment_idx for size in size_idx), name="surplus_lb")
    model.addConstrs((gp.quicksum(theta[k, size] for size in size_idx) == 1 for k in segment_idx), name="one_choice")
    model.addConstrs((payment[k, size] >= p[size] - revenue_ub * (1 - theta[k, size]) for k in segment_idx for size in size_idx), name="payment_lb")
    model.addConstrs((payment[k, size] <= p[size] for k in segment_idx for size in size_idx), name="payment_ub")
    model.addConstrs((surplus_term[k, size] == v_ks[k, size] * theta[k, size] - payment[k, size] for k in segment_idx for size in size_idx), name="surplus_term")
    model.addConstrs((surplus[k] == gp.quicksum(surplus_term[k, size] for size in size_idx) for k in segment_idx), name="surplus_sum")
    model.addConstrs(
        (
            surplus[k] >= gp.quicksum(v_ks[k, size] * theta[j, size] - payment[j, size] for size in size_idx)
            for k in segment_idx
            for j in segment_idx
            if j != k
        ),
        name="envy_like",
    )
    model.addConstrs((profit[k, size] == payment[k, size] - c_ks[k, size] * theta[k, size] for k in segment_idx for size in size_idx), name="profit")
    for size1 in size_idx:
        for size2 in size_idx:
            if size1 + size2 <= max_size:
                model.addConstr(p[size1 + size2] <= p[size1] + p[size2], name=f"subadd_{size1}_{size2}")
    for size in range(max_size):
        model.addConstr(p[size + 1] >= p[size], name=f"monotone_{size}")
    model.addConstrs((surplus_term[k, 0] == 0 for k in segment_idx), name="empty_bundle")
    model.addConstr(p[0] == 0.0, name="anchor_zero")
    model.setParam("OutputFlag", output_flag)
    model.setParam("MIPGap", mip_gap)
    model.setParam("TimeLimit", time_limit)
    model.optimize()
    if model.SolCount <= 0:
        raise RuntimeError("BSP baseline for diagnostics did not solve.")
    return {size: float(p[size].X) for size in size_idx}


def build_variant_a_model(
    full_assortments: np.ndarray,
    anchor_prices: Dict[int, float],
    bsp_size_prices: Dict[int, float],
) -> gp.Model:
    n_products = int(full_assortments.shape[1])
    bundle_sizes = np.asarray(full_assortments.sum(axis=1), dtype=int)
    bundle_count = full_assortments.shape[0]
    union_index = {tuple(row.tolist()): idx for idx, row in enumerate(full_assortments)}

    model = gp.Model("Phase3_Anchored_BSP_Projection_A_Diagnostic")
    q = model.addVars(n_products + 1, vtype=GRB.CONTINUOUS, lb=0.0, name="q")
    dev = model.addVars(n_products + 1, vtype=GRB.CONTINUOUS, lb=0.0, name="dev")
    model.setObjective(gp.quicksum(dev[s] for s in range(n_products + 1)), GRB.MINIMIZE)

    model.addConstr(q[0] == 0.0, name="q_zero")
    for s in range(n_products):
        model.addConstr(q[s + 1] >= q[s], name=f"mono_{s}")
    for a in range(n_products + 1):
        for b in range(n_products + 1):
            if a + b <= n_products:
                model.addConstr(q[a + b] <= q[a] + q[b], name=f"size_subadd_{a}_{b}")
    for s in range(n_products + 1):
        target = float(bsp_size_prices[s])
        model.addConstr(dev[s] >= q[s] - target, name=f"dev_pos_{s}")
        model.addConstr(dev[s] >= target - q[s], name=f"dev_neg_{s}")

    def expr(idx: int):
        if idx in anchor_prices:
            return float(anchor_prices[idx])
        return q[int(bundle_sizes[idx])]

    for i in range(bundle_count):
        bundle_i = full_assortments[i]
        for j in range(i, bundle_count):
            union_idx = union_index[tuple(np.maximum(bundle_i, full_assortments[j]).tolist())]
            model.addConstr(expr(union_idx) <= expr(i) + expr(j), name=f"global_subadd_{i}_{j}")
    return model


def build_variant_b_model(
    full_assortments: np.ndarray,
    anchor_prices: Dict[int, float],
    bsp_size_prices: Dict[int, float],
) -> gp.Model:
    n_products = int(full_assortments.shape[1])
    anchor_idx = sorted(anchor_prices.keys())
    anchor_sets = {idx: set(np.where(full_assortments[idx] == 1)[0].tolist()) for idx in anchor_idx}

    model = gp.Model("Phase3_Anchored_BSP_Projection_B_Diagnostic")
    q = model.addVars(n_products + 1, vtype=GRB.CONTINUOUS, lb=0.0, name="q")
    dev = model.addVars(n_products + 1, vtype=GRB.CONTINUOUS, lb=0.0, name="dev")
    model.setObjective(gp.quicksum(dev[s] for s in range(n_products + 1)), GRB.MINIMIZE)

    model.addConstr(q[0] == 0.0, name="q_zero")
    for s in range(n_products):
        model.addConstr(q[s + 1] >= q[s], name=f"mono_{s}")
    for a in range(n_products + 1):
        for b in range(n_products + 1):
            if a + b <= n_products:
                model.addConstr(q[a + b] <= q[a] + q[b], name=f"size_subadd_{a}_{b}")
    for s in range(n_products + 1):
        target = float(bsp_size_prices[s])
        model.addConstr(dev[s] >= q[s] - target, name=f"dev_pos_{s}")
        model.addConstr(dev[s] >= target - q[s], name=f"dev_neg_{s}")

    for idx_i, i in enumerate(anchor_idx):
        set_i = anchor_sets[i]
        size_i = len(set_i)
        price_i = float(anchor_prices[i])
        for j in anchor_idx[idx_i:]:
            set_j = anchor_sets[j]
            union_size = len(set_i.union(set_j))
            union_tuple = tuple(np.maximum(full_assortments[i], full_assortments[j]).tolist())
            union_full_idx = int(np.where((full_assortments == np.asarray(union_tuple, dtype=int)).all(axis=1))[0][0])
            lhs = float(anchor_prices[union_full_idx]) if union_full_idx in anchor_prices else q[union_size]
            model.addConstr(lhs <= price_i + float(anchor_prices[j]), name=f"anchor_pair_{i}_{j}")
        for b in range(n_products + 1):
            for union_size in range(max(size_i, b), min(n_products, size_i + b) + 1):
                model.addConstr(q[union_size] <= price_i + q[b], name=f"anchor_size_{i}_{b}_{union_size}")

    for u in anchor_idx:
        set_u = anchor_sets[u]
        price_u = float(anchor_prices[u])
        for a in anchor_idx:
            set_a = anchor_sets[a]
            if not set_a.issubset(set_u):
                continue
            rem = len(set_u.difference(set_a))
            model.addConstr(price_u <= float(anchor_prices[a]) + q[rem], name=f"subset_anchor_{u}_{a}")
    return model


def collect_iis_constraints(model: gp.Model) -> List[str]:
    model.computeIIS()
    hits = []
    for constr in model.getConstrs():
        if constr.IISConstr:
            hits.append(constr.ConstrName)
    return hits


def summarize_names(names: List[str]) -> Dict[str, int]:
    buckets: Dict[str, int] = {}
    for name in names:
        prefix = name.split("_")[0]
        if name.startswith("size_subadd"):
            prefix = "size_subadd"
        elif name.startswith("global_subadd"):
            prefix = "global_subadd"
        elif name.startswith("anchor_pair"):
            prefix = "anchor_pair"
        elif name.startswith("anchor_size"):
            prefix = "anchor_size"
        elif name.startswith("subset_anchor"):
            prefix = "subset_anchor"
        elif name.startswith("dev_pos"):
            prefix = "dev_pos"
        elif name.startswith("dev_neg"):
            prefix = "dev_neg"
        elif name.startswith("mono"):
            prefix = "mono"
        buckets[prefix] = buckets.get(prefix, 0) + 1
    return buckets


def diagnose_model(model: gp.Model, log_path: Path, ilp_path: Path) -> Dict:
    model.setParam("OutputFlag", 1)
    model.setParam("LogFile", str(log_path))
    model.optimize()
    status = int(model.Status)
    result = {"solver_status": status, "iis_constraints": [], "iis_summary": {}}
    if status == GRB.INFEASIBLE:
        hits = collect_iis_constraints(model)
        model.write(str(ilp_path))
        result["iis_constraints"] = hits
        result["iis_summary"] = summarize_names(hits)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Diagnose infeasibility for Phase 3 BSP completion variants.")
    parser.add_argument(
        "--instance-path",
        type=Path,
        default=Path("/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/cpbsd_fcp_pruned_mb_compare_n10k50_strict300/instances/cpbsd_instance_001_N10_K50_normal_rho0.0_full_hvhm.msgpack"),
    )
    parser.add_argument(
        "--fcp-result-path",
        type=Path,
        default=Path("/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/cpbsd_fcp_pruned_mb_compare_n10k50_strict300/results/cpbsd_instance_001_N10_K50_normal_rho0.0_full_hvhm__fcp_pruned_mb.json"),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/phase3_oos_bsp_completion_infeasibility_diag_n10_normal_rho0.0_full_hvhm_inst001"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ensure_dir(args.output_root)
    obj, v_kn, c_n = load_msgpack_with_setup(args.instance_path)
    fcp_result = load_json(args.fcp_result_path)
    full_assortments = build_assortments(int(obj["setup"]["n_products"]))
    anchor_prices = build_anchor_prices(fcp_result, full_assortments)
    bsp_size_prices = solve_bsp_all_prices(v_kn, c_n, output_flag=0)

    variant_a_model = build_variant_a_model(full_assortments, anchor_prices, bsp_size_prices)
    variant_b_model = build_variant_b_model(full_assortments, anchor_prices, bsp_size_prices)

    variant_a = diagnose_model(
        variant_a_model,
        args.output_root / "variant_a_gurobi.log",
        args.output_root / "variant_a_iis.ilp",
    )
    variant_b = diagnose_model(
        variant_b_model,
        args.output_root / "variant_b_gurobi.log",
        args.output_root / "variant_b_iis.ilp",
    )

    payload = {
        "instance_id": args.instance_path.stem,
        "variant_a": variant_a,
        "variant_b": variant_b,
    }
    out_json = args.output_root / "diagnosis_summary.json"
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"json": str(out_json), "payload": payload}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
