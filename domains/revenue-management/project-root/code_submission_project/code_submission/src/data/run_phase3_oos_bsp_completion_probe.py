from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Dict, List, Tuple

import gurobipy as gp
import msgpack
import msgpack_numpy as mnp
import numpy as np
from gurobipy import GRB

from generate_data_CPBSD import sample_valuations, valuation_means
from solve_mb_bsp_on_cpbsd_v2 import build_assortments, eval_mb_policy, json_default, normalize_numeric_keys


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def load_msgpack_with_setup(path: Path) -> Tuple[Dict, np.ndarray, np.ndarray]:
    with path.open("rb") as f:
        obj = msgpack.load(f, object_hook=mnp.decode, strict_map_key=False)
    v_kn = np.asarray(obj["valuation_samples_V"], dtype=float)
    c_n = np.asarray(obj["production_cost_c"], dtype=float)
    return obj, v_kn, c_n


def load_json(path: Path) -> Dict:
    return json.loads(path.read_text(encoding="utf-8"))


def generate_v_out(setup: Dict, k_out: int) -> np.ndarray:
    rng = np.random.default_rng(int(setup["seed"]) + 99991)
    means = valuation_means(int(setup["n_products"]), setup["heterogeneity"])
    return sample_valuations(
        k=k_out,
        means=means,
        family=setup["dist_family"],
        rho=float(setup["rho"]),
        rng=rng,
    )


def solve_bsp_all_prices(
    v_kn: np.ndarray,
    c_n: np.ndarray,
    time_limit: float = 300.0,
    mip_gap: float = 1e-3,
    output_flag: int = 0,
) -> Dict:
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

    model = gp.Model("Phase3_BSP_All_Prices")
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

    t0 = time.time()
    model.optimize()
    t1 = time.time()

    result = {
        "solver_status": int(model.Status),
        "feasible": model.SolCount > 0,
        "runtime": model.Runtime,
        "wall_time": t1 - t0,
        "objective": float(model.ObjVal) if model.SolCount > 0 else None,
        "size_prices_all": None,
    }
    if model.SolCount > 0:
        result["size_prices_all"] = {size: float(p[size].X) for size in size_idx}
    return result


def build_anchor_prices(
    fcp_result: Dict,
    full_assortments: np.ndarray,
) -> Dict[int, float]:
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


def price_expr_for_idx(idx: int, anchor_prices: Dict[int, float], bundle_sizes: np.ndarray, q_vars) -> gp.LinExpr | float:
    if idx in anchor_prices:
        return float(anchor_prices[idx])
    return q_vars[int(bundle_sizes[idx])]


def build_completed_prices(full_assortments: np.ndarray, anchor_prices: Dict[int, float], size_prices: Dict[int, float]) -> Dict[int, float]:
    bundle_sizes = np.asarray(full_assortments.sum(axis=1), dtype=int)
    completed = {}
    for idx in range(full_assortments.shape[0]):
        if idx in anchor_prices:
            completed[idx] = float(anchor_prices[idx])
        else:
            completed[idx] = float(size_prices[int(bundle_sizes[idx])])
    return completed


def solve_variant_a(
    full_assortments: np.ndarray,
    anchor_prices: Dict[int, float],
    bsp_size_prices: Dict[int, float],
    output_flag: int = 0,
) -> Dict:
    n_products = int(full_assortments.shape[1])
    bundle_sizes = np.asarray(full_assortments.sum(axis=1), dtype=int)
    bundle_count = full_assortments.shape[0]
    union_index = {tuple(row.tolist()): idx for idx, row in enumerate(full_assortments)}

    model = gp.Model("Phase3_Anchored_BSP_Projection_A")
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

    for i in range(bundle_count):
        bundle_i = full_assortments[i]
        for j in range(i, bundle_count):
            bundle_j = full_assortments[j]
            union_idx = union_index[tuple(np.maximum(bundle_i, bundle_j).tolist())]
            lhs = price_expr_for_idx(union_idx, anchor_prices, bundle_sizes, q)
            rhs = price_expr_for_idx(i, anchor_prices, bundle_sizes, q) + price_expr_for_idx(j, anchor_prices, bundle_sizes, q)
            model.addConstr(lhs <= rhs, name=f"global_subadd_{i}_{j}")

    model.setParam("OutputFlag", output_flag)
    t0 = time.time()
    model.optimize()
    t1 = time.time()

    result = {
        "variant": "A",
        "solver_status": int(model.Status),
        "feasible": model.SolCount > 0,
        "runtime": model.Runtime,
        "wall_time": t1 - t0,
        "objective": float(model.ObjVal) if model.SolCount > 0 else None,
        "size_prices": None,
    }
    if model.SolCount > 0:
        result["size_prices"] = {s: float(q[s].X) for s in range(n_products + 1)}
    return result


def solve_variant_b(
    full_assortments: np.ndarray,
    anchor_prices: Dict[int, float],
    bsp_size_prices: Dict[int, float],
    output_flag: int = 0,
) -> Dict:
    n_products = int(full_assortments.shape[1])
    bundle_sizes = np.asarray(full_assortments.sum(axis=1), dtype=int)
    anchor_idx = sorted(anchor_prices.keys())
    anchor_sets = {idx: set(np.where(full_assortments[idx] == 1)[0].tolist()) for idx in anchor_idx}

    model = gp.Model("Phase3_Anchored_BSP_Projection_B")
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
            if j in anchor_prices:
                # anchor-anchor exact coupling through union size scaffold or anchor union if present
                union_tuple = tuple(np.maximum(full_assortments[i], full_assortments[j]).tolist())
                union_full_idx = int(np.where((full_assortments == np.asarray(union_tuple, dtype=int)).all(axis=1))[0][0])
                lhs = float(anchor_prices[union_full_idx]) if union_full_idx in anchor_prices else q[union_size]
                model.addConstr(lhs <= price_i + float(anchor_prices[j]), name=f"anchor_pair_{i}_{j}")

        # anchor to size-envelope coupling
        for b in range(n_products + 1):
            for union_size in range(max(size_i, b), min(n_products, size_i + b) + 1):
                model.addConstr(q[union_size] <= price_i + q[b], name=f"anchor_size_{i}_{b}_{union_size}")

    # subset/superset anchor coupling
    for u in anchor_idx:
        set_u = anchor_sets[u]
        price_u = float(anchor_prices[u])
        for a in anchor_idx:
            set_a = anchor_sets[a]
            if not set_a.issubset(set_u):
                continue
            rem = len(set_u.difference(set_a))
            model.addConstr(price_u <= float(anchor_prices[a]) + q[rem], name=f"subset_anchor_{u}_{a}")

    model.setParam("OutputFlag", output_flag)
    t0 = time.time()
    model.optimize()
    t1 = time.time()

    result = {
        "variant": "B",
        "solver_status": int(model.Status),
        "feasible": model.SolCount > 0,
        "runtime": model.Runtime,
        "wall_time": t1 - t0,
        "objective": float(model.ObjVal) if model.SolCount > 0 else None,
        "size_prices": None,
    }
    if model.SolCount > 0:
        result["size_prices"] = {s: float(q[s].X) for s in range(n_products + 1)}
    return result


def check_anchor_preservation(completed_prices: Dict[int, float], anchor_prices: Dict[int, float], tol: float = 1e-8) -> bool:
    for idx, price in anchor_prices.items():
        if abs(float(completed_prices[idx]) - float(price)) > tol:
            return False
    return True


def check_global_subadditivity(full_assortments: np.ndarray, completed_prices: Dict[int, float], tol: float = 1e-8) -> Dict:
    bundle_count = full_assortments.shape[0]
    union_index = {tuple(row.tolist()): idx for idx, row in enumerate(full_assortments)}
    max_violation = 0.0
    violation_count = 0
    for i in range(bundle_count):
        bundle_i = full_assortments[i]
        price_i = float(completed_prices[i])
        for j in range(i, bundle_count):
            union_idx = union_index[tuple(np.maximum(bundle_i, full_assortments[j]).tolist())]
            lhs = float(completed_prices[union_idx])
            rhs = price_i + float(completed_prices[j])
            violation = lhs - rhs
            if violation > tol:
                violation_count += 1
                if violation > max_violation:
                    max_violation = violation
    return {
        "violation_count": int(violation_count),
        "max_violation": float(max_violation),
    }


def write_markdown_summary(path: Path, payload: Dict) -> None:
    lines: List[str] = []
    lines.append("# Phase 3 BSP Completion Probe")
    lines.append("")
    lines.append(f"- Instance: `{payload['instance_id']}`")
    lines.append(f"- Setup: `{payload['setup_key']}`")
    lines.append(f"- Anchor bundle count: `{payload['anchor_bundle_count']}`")
    lines.append(f"- Full bundle count: `{payload['full_bundle_count']}`")
    lines.append("")
    lines.append("## Baseline")
    lines.append("")
    lines.append(f"- Restricted FCP OOS revenue: `{payload['baseline']['restricted_oos_revenue']:.6f}`")
    lines.append(f"- Restricted FCP In-sample revenue: `{payload['baseline']['restricted_in_sample_revenue']:.6f}`")
    lines.append("")
    lines.append("## Variant Results")
    lines.append("")
    lines.append("| Variant | Feasible | OOS Revenue | In-Sample Revenue | Anchor Preserved | Subadd Violations | Max Violation | Runtime (s) |")
    lines.append("| --- | --- | ---: | ---: | --- | ---: | ---: | ---: |")
    for key in ["variant_a", "variant_b"]:
        item = payload[key]
        oos = "NA" if item["repaired_oos_revenue"] is None else f"{item['repaired_oos_revenue']:.6f}"
        ins = "NA" if item["repaired_in_sample_revenue"] is None else f"{item['repaired_in_sample_revenue']:.6f}"
        runtime = "NA" if item["runtime"] is None else f"{item['runtime']:.4f}"
        lines.append(
            f"| `{item['name']}` | `{item['feasible']}` | {oos} | {ins} | `{item['anchor_preserved']}` | `{item['subadditivity']['violation_count']}` | `{item['subadditivity']['max_violation']:.6f}` | {runtime} |"
        )
    lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe post-hoc BSP-style OOS completion variants for FCP-MB.")
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
        default=Path("/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/phase3_oos_bsp_completion_probe_n10_normal_rho0.0_full_hvhm_inst001"),
    )
    parser.add_argument("--k-out", type=int, default=5000)
    parser.add_argument("--time-limit-bsp", type=float, default=300.0)
    parser.add_argument("--mip-gap", type=float, default=1e-3)
    parser.add_argument("--output-flag", type=int, default=0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ensure_dir(args.output_root)

    obj, v_kn, c_n = load_msgpack_with_setup(args.instance_path)
    setup = obj["setup"]
    fcp_result = load_json(args.fcp_result_path)
    full_assortments = build_assortments(int(setup["n_products"]))
    anchor_prices = build_anchor_prices(fcp_result, full_assortments)
    restricted_assortments = np.asarray(fcp_result["assortments"], dtype=int)
    restricted_prices = normalize_numeric_keys(fcp_result["bundle_prices_full"])
    v_out = generate_v_out(setup, args.k_out)

    bsp_full = solve_bsp_all_prices(
        v_kn=v_kn,
        c_n=c_n,
        time_limit=args.time_limit_bsp,
        mip_gap=args.mip_gap,
        output_flag=args.output_flag,
    )
    if not bsp_full.get("feasible"):
        raise RuntimeError("BSP all-prices probe failed to solve.")
    bsp_size_prices = normalize_numeric_keys(bsp_full["size_prices_all"])

    baseline = {
        "restricted_in_sample_revenue": float(fcp_result["objective"]),
        "restricted_oos_revenue": float(eval_mb_policy(v_out, c_n, restricted_prices, restricted_assortments)),
    }

    variant_a_res = solve_variant_a(
        full_assortments=full_assortments,
        anchor_prices=anchor_prices,
        bsp_size_prices=bsp_size_prices,
        output_flag=args.output_flag,
    )
    variant_b_res = solve_variant_b(
        full_assortments=full_assortments,
        anchor_prices=anchor_prices,
        bsp_size_prices=bsp_size_prices,
        output_flag=args.output_flag,
    )

    def package_variant(name: str, res: Dict) -> Dict:
        if not res.get("feasible"):
            return {
                "name": name,
                "feasible": False,
                "runtime": res.get("runtime"),
                "objective": res.get("objective"),
                "size_prices": None,
                "repaired_in_sample_revenue": None,
                "repaired_oos_revenue": None,
                "anchor_preserved": False,
                "subadditivity": {"violation_count": -1, "max_violation": -1.0},
            }
        completed_prices = build_completed_prices(full_assortments, anchor_prices, normalize_numeric_keys(res["size_prices"]))
        return {
            "name": name,
            "feasible": True,
            "runtime": res.get("runtime"),
            "objective": res.get("objective"),
            "size_prices": normalize_numeric_keys(res["size_prices"]),
            "repaired_in_sample_revenue": float(eval_mb_policy(v_kn, c_n, completed_prices, full_assortments)),
            "repaired_oos_revenue": float(eval_mb_policy(v_out, c_n, completed_prices, full_assortments)),
            "anchor_preserved": bool(check_anchor_preservation(completed_prices, anchor_prices)),
            "subadditivity": check_global_subadditivity(full_assortments, completed_prices),
        }

    payload = {
        "instance_id": args.instance_path.stem,
        "setup_key": f"{setup['dist_family']}_rho{setup['rho']}_{setup['heterogeneity']}_{setup['cost_scenario']}",
        "anchor_bundle_count": len(anchor_prices),
        "full_bundle_count": int(full_assortments.shape[0]),
        "baseline": baseline,
        "bsp_all_prices": bsp_full,
        "variant_a": package_variant("Variant-A-Anchored-BSP-Projection", variant_a_res),
        "variant_b": package_variant("Variant-B-Reduced-Coupling-BSP-Projection", variant_b_res),
    }

    json_path = args.output_root / "probe_summary.json"
    md_path = args.output_root / "probe_summary.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")
    write_markdown_summary(md_path, payload)

    print(json.dumps({"json": str(json_path), "markdown": str(md_path), "payload": payload}, ensure_ascii=False, indent=2, default=json_default))


if __name__ == "__main__":
    main()
