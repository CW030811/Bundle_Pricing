from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Dict, List, Tuple

import gurobipy as gp
import numpy as np
from gurobipy import GRB

from run_phase3_oos_bsp_completion_probe import (
    build_anchor_prices,
    ensure_dir,
    generate_v_out,
    load_json,
    load_msgpack_with_setup,
)
from solve_mb_bsp_on_cpbsd_v2 import build_assortments, eval_mb_policy, json_default, normalize_numeric_keys


def compute_size_price_ubs(v_kn: np.ndarray) -> Dict[int, float]:
    k_count, n_products = v_kn.shape
    ub = {0: 0.0}
    prefix_best = np.zeros(n_products + 1, dtype=float)
    for k in range(k_count):
        ordered_vals = np.sort(v_kn[k])[::-1]
        prefix = np.zeros(n_products + 1, dtype=float)
        prefix[1:] = np.cumsum(ordered_vals)
        prefix_best = np.maximum(prefix_best, prefix)
    for s in range(1, n_products + 1):
        ub[s] = float(prefix_best[s])
    return ub


def bundle_mask(bundle: np.ndarray) -> int:
    mask = 0
    for bit in bundle.astype(int).tolist():
        mask = (mask << 1) | int(bit)
    return mask


def canonical_mixed_splits(full_assortments: np.ndarray, anchor_idx: set[int]) -> List[Tuple[int, int, int]]:
    masks = [bundle_mask(row) for row in full_assortments]
    mask_to_idx = {mask: idx for idx, mask in enumerate(masks)}
    sizes = [int(row.sum()) for row in full_assortments]
    splits: List[Tuple[int, int, int]] = []

    for parent_idx, parent_mask in enumerate(masks):
        if parent_mask == 0:
            continue
        sub = (parent_mask - 1) & parent_mask
        while sub:
            other = parent_mask ^ sub
            if other:
                size_sub = sizes[mask_to_idx[sub]]
                size_other = sizes[mask_to_idx[other]]
                if size_sub < size_other or (size_sub == size_other and sub < other):
                    left_idx = mask_to_idx[sub]
                    right_idx = mask_to_idx[other]
                    in_f = (
                        (parent_idx in anchor_idx)
                        or (left_idx in anchor_idx)
                        or (right_idx in anchor_idx)
                    )
                    all_f = (
                        (parent_idx in anchor_idx)
                        and (left_idx in anchor_idx)
                        and (right_idx in anchor_idx)
                    )
                    if in_f and not all_f:
                        splits.append((parent_idx, left_idx, right_idx))
            sub = (sub - 1) & parent_mask
    return splits


def solve_variant_c(
    v_kn: np.ndarray,
    c_n: np.ndarray,
    full_assortments: np.ndarray,
    anchor_prices: Dict[int, float],
    time_limit: float = 300.0,
    mip_gap: float = 1e-3,
    output_flag: int = 0,
    dual_reductions: int = 0,
    iis_output_path: Path | None = None,
) -> Dict:
    k_count, n_products = v_kn.shape
    bundle_count = int(full_assortments.shape[0])
    bundle_sizes = np.asarray(full_assortments.sum(axis=1), dtype=int)
    bundle_cost = np.asarray(full_assortments @ c_n, dtype=float)
    v_kb = np.asarray(v_kn @ full_assortments.T, dtype=float)
    size_price_ub = compute_size_price_ubs(v_kn)
    q_bar = {
        b: float(anchor_prices[b]) if b in anchor_prices else float(size_price_ub[int(bundle_sizes[b])])
        for b in range(bundle_count)
    }
    max_q_bar = max(q_bar.values()) if q_bar else 0.0
    big_m = {
        k: float(np.max(v_kb[k]) + max_q_bar + 1.0)
        for k in range(k_count)
    }

    anchor_set = set(anchor_prices.keys())
    mixed_splits = canonical_mixed_splits(full_assortments, anchor_set)

    model = gp.Model("Phase3_Variant_C")
    p = model.addVars(n_products + 1, vtype=GRB.CONTINUOUS, lb=0.0, name="p")
    q = model.addVars(bundle_count, vtype=GRB.CONTINUOUS, lb=0.0, name="q")
    x = model.addVars(k_count, bundle_count, vtype=GRB.BINARY, name="x")
    r = model.addVars(k_count, bundle_count, vtype=GRB.CONTINUOUS, lb=0.0, name="r")
    u = model.addVars(k_count, vtype=GRB.CONTINUOUS, lb=0.0, name="u")

    for s in range(n_products + 1):
        model.addConstr(p[s] <= size_price_ub[s], name=f"p_ub_{s}")
    model.addConstr(p[0] == 0.0, name="p_zero")

    for b in range(bundle_count):
        if b in anchor_prices:
            model.addConstr(q[b] == float(anchor_prices[b]), name=f"anchor_q_{b}")
        else:
            model.addConstr(q[b] == p[int(bundle_sizes[b])], name=f"size_link_{b}")
        model.addConstr(q[b] <= q_bar[b], name=f"q_ub_{b}")

    for k in range(k_count):
        model.addConstr(gp.quicksum(x[k, b] for b in range(bundle_count)) == 1, name=f"one_choice_{k}")
        for b in range(bundle_count):
            utility = float(v_kb[k, b]) - q[b]
            model.addConstr(u[k] >= utility, name=f"u_lb_{k}_{b}")
            model.addConstr(u[k] <= utility + big_m[k] * (1 - x[k, b]), name=f"u_ub_{k}_{b}")
            model.addConstr(r[k, b] <= q[b], name=f"r_ub_q_{k}_{b}")
            model.addConstr(r[k, b] <= q_bar[b] * x[k, b], name=f"r_ub_x_{k}_{b}")
            model.addConstr(r[k, b] >= q[b] - q_bar[b] * (1 - x[k, b]), name=f"r_lb_{k}_{b}")

    for s in range(1, n_products + 1):
        for a in range(0, s + 1):
            b = s - a
            if a <= b:
                model.addConstr(p[s] <= p[a] + p[b], name=f"size_subadd_{a}_{b}_{s}")

    for parent_idx, left_idx, right_idx in mixed_splits:
        model.addConstr(
            q[parent_idx] <= q[left_idx] + q[right_idx],
            name=f"mixed_subadd_{parent_idx}_{left_idx}_{right_idx}",
        )

    model.setObjective(
        gp.quicksum((r[k, b] - float(bundle_cost[b]) * x[k, b]) for k in range(k_count) for b in range(bundle_count)) / float(k_count),
        GRB.MAXIMIZE,
    )

    model.setParam("OutputFlag", output_flag)
    model.setParam("TimeLimit", time_limit)
    model.setParam("MIPGap", mip_gap)
    model.setParam("DualReductions", dual_reductions)
    model.setParam("InfUnbdInfo", 1)

    t0 = time.time()
    model.optimize()
    t1 = time.time()

    result = {
        "solver_status": int(model.Status),
        "feasible": model.SolCount > 0,
        "runtime": float(model.Runtime),
        "wall_time": float(t1 - t0),
        "objective": float(model.ObjVal) if model.SolCount > 0 else None,
        "mip_gap": float(model.MIPGap) if model.SolCount > 0 else None,
        "bundle_count": bundle_count,
        "mixed_split_count": len(mixed_splits),
        "size_prices": None,
        "completed_prices": None,
        "iis_path": str(iis_output_path) if iis_output_path is not None else None,
    }
    if model.Status == GRB.INFEASIBLE and iis_output_path is not None:
        model.computeIIS()
        model.write(str(iis_output_path))
    if model.SolCount > 0:
        size_prices = {s: float(p[s].X) for s in range(n_products + 1)}
        completed_prices = {b: float(q[b].X) for b in range(bundle_count)}
        result["size_prices"] = size_prices
        result["completed_prices"] = completed_prices
        result["chosen_bundle_idx_by_customer"] = {k: int(max(range(bundle_count), key=lambda b: x[k, b].X)) for k in range(k_count)}
    return result


def check_anchor_preservation(completed_prices: Dict[int, float], anchor_prices: Dict[int, float], tol: float = 1e-8) -> bool:
    for idx, price in anchor_prices.items():
        if abs(float(completed_prices[idx]) - float(price)) > tol:
            return False
    return True


def check_hybrid_subadditivity(
    full_assortments: np.ndarray,
    completed_prices: Dict[int, float],
    anchor_idx: set[int],
    tol: float = 1e-8,
) -> Dict:
    bundle_sizes = np.asarray(full_assortments.sum(axis=1), dtype=int)
    masks = [bundle_mask(row) for row in full_assortments]
    mask_to_idx = {mask: idx for idx, mask in enumerate(masks)}
    max_violation = 0.0
    violation_count = 0
    checked = 0

    for parent_idx, parent_mask in enumerate(masks):
        if parent_mask == 0:
            continue
        sub = (parent_mask - 1) & parent_mask
        while sub:
            other = parent_mask ^ sub
            if other:
                left_idx = mask_to_idx[sub]
                right_idx = mask_to_idx[other]
                size_left = int(bundle_sizes[left_idx])
                size_right = int(bundle_sizes[right_idx])
                if size_left < size_right or (size_left == size_right and sub < other):
                    in_f = (
                        (parent_idx in anchor_idx)
                        or (left_idx in anchor_idx)
                        or (right_idx in anchor_idx)
                    )
                    all_f = (
                        (parent_idx in anchor_idx)
                        and (left_idx in anchor_idx)
                        and (right_idx in anchor_idx)
                    )
                    if in_f and not all_f:
                        checked += 1
                        violation = (
                            float(completed_prices[parent_idx])
                            - float(completed_prices[left_idx])
                            - float(completed_prices[right_idx])
                        )
                        if violation > tol:
                            violation_count += 1
                            max_violation = max(max_violation, violation)
            sub = (sub - 1) & parent_mask

    for s in range(1, int(full_assortments.shape[1]) + 1):
        for a in range(0, s + 1):
            b = s - a
            if a <= b:
                checked += 1
                rep_s = next(idx for idx in range(len(bundle_sizes)) if bundle_sizes[idx] == s and idx not in anchor_idx)
                rep_a = next(idx for idx in range(len(bundle_sizes)) if bundle_sizes[idx] == a)
                rep_b = next(idx for idx in range(len(bundle_sizes)) if bundle_sizes[idx] == b)
                violation = float(completed_prices[rep_s]) - float(completed_prices[rep_a]) - float(completed_prices[rep_b])
                if violation > tol:
                    violation_count += 1
                    max_violation = max(max_violation, violation)

    return {
        "violation_count": int(violation_count),
        "max_violation": float(max_violation),
        "checked_constraint_count": int(checked),
    }


def write_markdown_summary(path: Path, payload: Dict) -> None:
    lines: List[str] = []
    lines.append("# Phase 3 Variant C Probe")
    lines.append("")
    lines.append(f"- Instance: `{payload['instance_id']}`")
    lines.append(f"- Setup: `{payload['setup_key']}`")
    lines.append(f"- Anchor bundle count: `{payload['anchor_bundle_count']}`")
    lines.append(f"- Full bundle count: `{payload['full_bundle_count']}`")
    lines.append(f"- Mixed split count: `{payload['variant_c']['mixed_split_count']}`")
    lines.append("")
    lines.append("## Baseline")
    lines.append("")
    lines.append(f"- Restricted FCP in-sample revenue: `{payload['baseline']['restricted_in_sample_revenue']:.6f}`")
    lines.append(f"- Restricted FCP OOS revenue: `{payload['baseline']['restricted_oos_revenue']:.6f}`")
    lines.append("")
    lines.append("## Variant C")
    lines.append("")
    lines.append(f"- Feasible: `{payload['variant_c']['feasible']}`")
    lines.append(f"- Solver status: `{payload['variant_c']['solver_status']}`")
    lines.append(f"- Runtime: `{payload['variant_c']['runtime']:.4f}`")
    lines.append(f"- MIP gap: `{payload['variant_c']['mip_gap']}`")
    lines.append(f"- Repaired in-sample revenue: `{payload['variant_c']['repaired_in_sample_revenue']}`")
    lines.append(f"- Repaired OOS revenue: `{payload['variant_c']['repaired_oos_revenue']}`")
    lines.append(f"- Delta OOS vs restricted: `{payload['variant_c']['delta_oos_vs_restricted']}`")
    lines.append(f"- Anchor preserved: `{payload['variant_c']['anchor_preserved']}`")
    lines.append(f"- Hybrid subadd violations: `{payload['variant_c']['hybrid_subadditivity']['violation_count']}`")
    lines.append(f"- Hybrid subadd max violation: `{payload['variant_c']['hybrid_subadditivity']['max_violation']}`")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe Phase 3 Variant C on the fixed N=10 diagnostic instance.")
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
        default=Path("/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/phase3_oos_variant_c_probe_n10_normal_rho0.0_full_hvhm_inst001"),
    )
    parser.add_argument("--k-out", type=int, default=5000)
    parser.add_argument("--time-limit", type=float, default=300.0)
    parser.add_argument("--mip-gap", type=float, default=1e-3)
    parser.add_argument("--output-flag", type=int, default=0)
    parser.add_argument("--dual-reductions", type=int, default=0)
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

    baseline = {
        "restricted_in_sample_revenue": float(fcp_result["objective"]),
        "restricted_oos_revenue": float(eval_mb_policy(v_out, c_n, restricted_prices, restricted_assortments)),
    }

    res = solve_variant_c(
        v_kn=v_kn,
        c_n=c_n,
        full_assortments=full_assortments,
        anchor_prices=anchor_prices,
        time_limit=args.time_limit,
        mip_gap=args.mip_gap,
        output_flag=args.output_flag,
        dual_reductions=args.dual_reductions,
        iis_output_path=args.output_root / "variant_c_iis.ilp",
    )

    if res.get("feasible"):
        completed_prices = normalize_numeric_keys(res["completed_prices"])
        packaged = {
            "name": "Variant-C-Hybrid-Fixed-Anchors",
            "feasible": True,
            "solver_status": res["solver_status"],
            "runtime": res["runtime"],
            "mip_gap": res["mip_gap"],
            "mixed_split_count": res["mixed_split_count"],
            "repaired_in_sample_revenue": float(eval_mb_policy(v_kn, c_n, completed_prices, full_assortments)),
            "repaired_oos_revenue": float(eval_mb_policy(v_out, c_n, completed_prices, full_assortments)),
            "delta_oos_vs_restricted": float(eval_mb_policy(v_out, c_n, completed_prices, full_assortments)) - baseline["restricted_oos_revenue"],
            "anchor_preserved": bool(check_anchor_preservation(completed_prices, anchor_prices)),
            "hybrid_subadditivity": check_hybrid_subadditivity(full_assortments, completed_prices, set(anchor_prices.keys())),
            "size_prices": res["size_prices"],
            "completed_prices": completed_prices,
        }
    else:
        packaged = {
            "name": "Variant-C-Hybrid-Fixed-Anchors",
            "feasible": False,
            "solver_status": res["solver_status"],
            "runtime": res["runtime"],
            "mip_gap": res["mip_gap"],
            "mixed_split_count": res["mixed_split_count"],
            "repaired_in_sample_revenue": None,
            "repaired_oos_revenue": None,
            "delta_oos_vs_restricted": None,
            "anchor_preserved": False,
            "hybrid_subadditivity": {"violation_count": -1, "max_violation": -1.0, "checked_constraint_count": 0},
            "size_prices": None,
            "completed_prices": None,
        }

    payload = {
        "instance_id": args.instance_path.stem,
        "setup_key": f"{setup['dist_family']}_rho{setup['rho']}_{setup['heterogeneity']}_{setup['cost_scenario']}",
        "anchor_bundle_count": len(anchor_prices),
        "full_bundle_count": int(full_assortments.shape[0]),
        "baseline": baseline,
        "variant_c": packaged,
    }

    json_path = args.output_root / "variant_c_probe_summary.json"
    md_path = args.output_root / "variant_c_probe_summary.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")
    write_markdown_summary(md_path, payload)
    print(json.dumps({"json": str(json_path), "markdown": str(md_path), "payload": payload}, ensure_ascii=False, indent=2, default=json_default))


if __name__ == "__main__":
    main()
