"""Phase 3 OOS Repair: Component Pricing Completion Probe.

Uses CPBSD-style component pricing (p_n, d_s) to fill non-anchor bundle
prices, preserving FCP anchor prices and satisfying subadditivity via
discount subadditivity.
"""
from __future__ import annotations

import argparse
import json
import time
from itertools import combinations
from pathlib import Path
from typing import Dict, List, Tuple

import gurobipy as gp
import msgpack
import msgpack_numpy as mnp
import numpy as np
from gurobipy import GRB

from generate_data_CPBSD import sample_valuations, valuation_means
from solve_mb_bsp_on_cpbsd_v2 import (
    build_assortments,
    eval_mb_policy,
    json_default,
    normalize_numeric_keys,
)


# ---------------------------------------------------------------------------
# IO helpers (same pattern as existing probes)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Component Pricing Completion LP
# ---------------------------------------------------------------------------

def solve_component_pricing(
    full_assortments: np.ndarray,
    anchor_prices: Dict[int, float],
    n_products: int,
    objective_mode: str = "max_discount",
    output_flag: int = 0,
    time_limit: float = 300.0,
) -> Dict:
    """Solve for (p_n, d_s) that satisfy all anchor-induced subadditivity.

    Non-anchor bundle S of size s is priced as: sum_{n in S} p_n - s * d_s
    Anchor bundles keep their fixed prices P_F(S).
    """
    N = n_products
    bundle_sizes = full_assortments.sum(axis=1).astype(int)

    # Identify anchor items
    anchor_idx_set = set(anchor_prices.keys())
    anchor_items = {}   # full_idx -> set of item indices
    for idx in anchor_idx_set:
        if idx == 0:
            continue
        anchor_items[idx] = set(np.where(full_assortments[idx] == 1)[0].tolist())

    model = gp.Model("ComponentPricing")
    model.setParam("OutputFlag", output_flag)
    model.setParam("TimeLimit", time_limit)

    # Variables
    p = model.addVars(range(N), lb=0.0, vtype=GRB.CONTINUOUS, name="p")
    d = model.addVars(range(1, N + 1), lb=0.0, vtype=GRB.CONTINUOUS, name="d")
    model.addConstr(d[1] == 0.0, name="d1_zero")

    # A. Discount subadditivity: s*d_s >= s1*d_s1 + s2*d_s2
    for s in range(2, N + 1):
        for s1 in range(1, s):
            s2 = s - s1
            model.addConstr(
                s * d[s] >= s1 * d[s1] + s2 * d[s2],
                name=f"disc_subadd_{s}_{s1}_{s2}",
            )

    # Build helper: for each anchor, the linear expression sum_{n in A} p[n]
    def anchor_p_sum(anchor_full_idx: int) -> gp.LinExpr:
        items = anchor_items[anchor_full_idx]
        return gp.quicksum(p[n] for n in items)

    # B. Anchor-induced subadditivity constraints
    # We enumerate 2-way disjoint partitions involving anchors.

    constraint_count = {"type_c": 0, "type_d": 0, "type_e": 0, "type_f": 0}

    # Type C: For each anchor A (size s_A), for each complement size t = 1..N-s_A:
    #   sum_{n in A} p_n <= P_F(A) + (s_A+t)*d[s_A+t] - t*d[t]
    # This comes from P(A union T) <= P_F(A) + P(T) for any disjoint T of size t.
    for a_idx, a_price in anchor_prices.items():
        if a_idx == 0:
            continue
        s_a = int(bundle_sizes[a_idx])
        for t in range(1, N - s_a + 1):
            st = s_a + t
            if st > N:
                break
            model.addConstr(
                anchor_p_sum(a_idx) <= a_price + st * d[st] - t * d[t],
                name=f"type_c_{a_idx}_t{t}",
            )
            constraint_count["type_c"] += 1

    # Type D: For each pair (A1 subset A2), both anchors, A2\A1 non-anchor:
    #   sum_{n in A2\A1} p_n >= P_F(A2) - P_F(A1) + |A2\A1|*d[|A2\A1|]
    anchor_list = [(idx, anchor_items[idx], anchor_prices[idx])
                   for idx in anchor_items if idx != 0]
    for i, (a1_idx, a1_items, a1_price) in enumerate(anchor_list):
        for j, (a2_idx, a2_items, a2_price) in enumerate(anchor_list):
            if i == j:
                continue
            if not a1_items.issubset(a2_items):
                continue
            diff_items = a2_items - a1_items
            if not diff_items:
                continue
            # Check if diff set is itself an anchor
            diff_vec = np.zeros(N, dtype=int)
            for n in diff_items:
                diff_vec[n] = 1
            diff_tuple = tuple(diff_vec.tolist())
            # Find full index of diff
            diff_full_idx = None
            for row_idx in range(full_assortments.shape[0]):
                if tuple(full_assortments[row_idx].tolist()) == diff_tuple:
                    diff_full_idx = row_idx
                    break
            if diff_full_idx is not None and diff_full_idx in anchor_idx_set:
                continue  # Both parts are anchors; anchor-anchor already OK
            diff_size = len(diff_items)
            diff_p_sum = gp.quicksum(p[n] for n in diff_items)
            model.addConstr(
                diff_p_sum >= a2_price - a1_price + diff_size * d[diff_size],
                name=f"type_d_{a1_idx}_{a2_idx}",
            )
            constraint_count["type_d"] += 1

    # Type E: For each anchor A, for each 2-way partition (s1, s2) with
    #   s1+s2=|A|, both parts non-anchor:
    #   sum_{n in A} p_n >= P_F(A) + s1*d[s1] + s2*d[s2]
    # We use size-pair-level constraints (sufficient since item identity
    # doesn't change the constraint form for the both-non-anchor case).
    # But if one partition part IS an anchor, we skip (handled by type D).
    for a_idx, a_items_set, a_price in anchor_list:
        s_a = len(a_items_set)
        seen_size_pairs = set()
        a_items_list = sorted(a_items_set)
        for s1 in range(1, s_a):
            s2 = s_a - s1
            pair = (min(s1, s2), max(s1, s2))
            if pair in seen_size_pairs:
                continue
            seen_size_pairs.add(pair)
            # Check if ANY partition with these sizes has both parts non-anchor.
            # For efficiency, just add the constraint (it's valid even if some
            # partitions have an anchor part; it just might be weaker than type D).
            model.addConstr(
                anchor_p_sum(a_idx) >= a_price + s1 * d[s1] + s2 * d[s2],
                name=f"type_e_{a_idx}_{s1}_{s2}",
            )
            constraint_count["type_e"] += 1

    # Type F: For each disjoint anchor pair (A1, A2), A1 union A2 non-anchor:
    #   sum_{n in A1 union A2} p_n <= P_F(A1) + P_F(A2) + |A1 union A2|*d[|A1 union A2|]
    for i, (a1_idx, a1_items, a1_price) in enumerate(anchor_list):
        for j, (a2_idx, a2_items, a2_price) in enumerate(anchor_list):
            if j <= i:
                continue
            if a1_items & a2_items:
                continue  # Not disjoint
            union_items = a1_items | a2_items
            union_size = len(union_items)
            if union_size > N:
                continue
            # Check if union is anchor
            union_vec = np.zeros(N, dtype=int)
            for n in union_items:
                union_vec[n] = 1
            union_tuple = tuple(union_vec.tolist())
            union_full_idx = None
            for row_idx in range(full_assortments.shape[0]):
                if tuple(full_assortments[row_idx].tolist()) == union_tuple:
                    union_full_idx = row_idx
                    break
            if union_full_idx is not None and union_full_idx in anchor_idx_set:
                continue  # Anchor-anchor, already OK
            union_p_sum = gp.quicksum(p[n] for n in union_items)
            model.addConstr(
                union_p_sum <= a1_price + a2_price + union_size * d[union_size],
                name=f"type_f_{a1_idx}_{a2_idx}",
            )
            constraint_count["type_f"] += 1

    # Objective
    if objective_mode == "max_discount":
        # Maximize total discount to encourage lower prices for larger bundles
        # Bounded by requiring p_n <= max anchor price as a practical upper limit
        p_ub = max(anchor_prices.values()) if anchor_prices else 100.0
        for n in range(N):
            p[n].UB = p_ub * 2  # generous upper bound
        for s in range(2, N + 1):
            d[s].UB = p_ub       # discount can't exceed max price
        model.setObjective(gp.quicksum(s * d[s] for s in range(2, N + 1)), GRB.MAXIMIZE)
    elif objective_mode == "min_price_sum":
        # Minimize total item prices (encourage lower non-anchor prices for coverage)
        model.setObjective(gp.quicksum(p[n] for n in range(N)), GRB.MINIMIZE)
    elif objective_mode == "feasibility":
        model.setObjective(0, GRB.MAXIMIZE)
    else:
        raise ValueError(f"Unknown objective_mode: {objective_mode}")

    # Disable dual reductions so infeasible status is definitive
    model.setParam("DualReductions", 0)

    t0 = time.time()
    model.optimize()
    t1 = time.time()

    result = {
        "solver_status": int(model.Status),
        "feasible": model.SolCount > 0,
        "runtime": model.Runtime,
        "wall_time": t1 - t0,
        "objective": float(model.ObjVal) if model.SolCount > 0 else None,
        "constraint_count": constraint_count,
        "model_num_vars": int(model.NumVars),
        "model_num_constrs": int(model.NumConstrs),
        "item_prices": None,
        "size_discounts": None,
        "iis_constraints": None,
    }
    if model.SolCount > 0:
        result["item_prices"] = {n: float(p[n].X) for n in range(N)}
        result["size_discounts"] = {s: float(d[s].X) for s in range(1, N + 1)}
    elif model.Status == GRB.INFEASIBLE:
        # Compute IIS for diagnosis
        model.computeIIS()
        iis_names = [c.ConstrName for c in model.getConstrs() if c.IISConstr]
        result["iis_constraints"] = iis_names
    return result


# ---------------------------------------------------------------------------
# Build hybrid prices
# ---------------------------------------------------------------------------

def build_hybrid_prices(
    full_assortments: np.ndarray,
    anchor_prices: Dict[int, float],
    item_prices: Dict[int, float],
    size_discounts: Dict[int, float],
) -> Dict[int, float]:
    """Build full bundle prices: anchors fixed, non-anchors via component pricing."""
    bundle_count = full_assortments.shape[0]
    bundle_sizes = full_assortments.sum(axis=1).astype(int)
    hybrid = {}
    for idx in range(bundle_count):
        if idx in anchor_prices:
            hybrid[idx] = float(anchor_prices[idx])
        else:
            size = int(bundle_sizes[idx])
            if size == 0:
                hybrid[idx] = 0.0
            else:
                p_sum = sum(item_prices[n] for n in range(full_assortments.shape[1])
                            if full_assortments[idx, n] == 1)
                hybrid[idx] = p_sum - size * size_discounts.get(size, 0.0)
    return hybrid


# ---------------------------------------------------------------------------
# Subadditivity check
# ---------------------------------------------------------------------------

def check_global_subadditivity(
    full_assortments: np.ndarray,
    completed_prices: Dict[int, float],
    tol: float = 1e-8,
) -> Dict:
    bundle_count = full_assortments.shape[0]
    union_index = {tuple(row.tolist()): idx for idx, row in enumerate(full_assortments)}
    max_violation = 0.0
    violation_count = 0
    worst_pair = None
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
                    worst_pair = (i, j, union_idx, violation)
    return {
        "violation_count": int(violation_count),
        "max_violation": float(max_violation),
        "worst_pair": worst_pair,
    }


def check_anchor_preservation(
    completed_prices: Dict[int, float],
    anchor_prices: Dict[int, float],
    tol: float = 1e-8,
) -> bool:
    for idx, price in anchor_prices.items():
        if abs(float(completed_prices[idx]) - float(price)) > tol:
            return False
    return True


# ---------------------------------------------------------------------------
# Hybrid OOS evaluator using BSP compression
# ---------------------------------------------------------------------------

def eval_hybrid_oos(
    v_eval: np.ndarray,
    c_n: np.ndarray,
    anchor_prices: Dict[int, float],
    anchor_assortments: np.ndarray,  # (num_anchors, N)
    item_prices: Dict[int, float],
    size_discounts: Dict[int, float],
) -> Dict:
    """Evaluate OOS revenue on the hybrid menu.

    For each customer:
    - Check surplus from each anchor bundle (fixed prices).
    - Check surplus from best non-anchor per size (BSP compression:
      sort items by v_kn - p_n, top-s prefix is optimal non-anchor).
    - Choose max surplus option.
    """
    k_count, N = v_eval.shape
    p_arr = np.array([item_prices[n] for n in range(N)])
    d_arr = np.array([size_discounts.get(s, 0.0) for s in range(N + 1)])

    # Pre-compute anchor properties
    anchor_list = []
    for a_idx, a_price in anchor_prices.items():
        if a_idx == 0:
            continue
        anchor_list.append((a_idx, a_price))
    anchor_vals = v_eval @ anchor_assortments.T    # (K, num_anchors)
    anchor_costs = anchor_assortments @ c_n         # (num_anchors,)

    # Pre-compute all anchor prices in order
    anchor_prices_arr = np.array([ap for _, ap in anchor_list])

    total_profit = 0.0
    outside_count = 0
    anchor_chosen_count = 0
    nonanchor_chosen_count = 0

    for k in range(k_count):
        best_surplus = 0.0
        best_profit = 0.0
        best_source = "outside"

        # Evaluate anchors
        for ai, (a_idx, a_price) in enumerate(anchor_list):
            val_k = float(anchor_vals[k, ai])
            surplus = val_k - a_price
            profit = a_price - float(anchor_costs[ai])
            eps = 1e-9
            if surplus > best_surplus + eps:
                best_surplus = surplus
                best_profit = profit
                best_source = "anchor"
            elif abs(surplus - best_surplus) <= eps and profit > best_profit + eps:
                best_profit = profit
                best_source = "anchor"

        # Evaluate non-anchor per size (BSP compression)
        net_val = v_eval[k] - p_arr   # v_kn - p_n
        order = np.argsort(-net_val)   # Sort descending by net value
        prefix_net_val = 0.0
        prefix_cost = 0.0
        for s in range(1, N + 1):
            item_idx = int(order[s - 1])
            prefix_net_val += net_val[item_idx]
            prefix_cost += c_n[item_idx]
            # Non-anchor price = sum p_n(top-s items) - s*d_s
            # Surplus = sum v_kn(top-s) - price = sum (v_kn - p_n)(top-s) + s*d_s
            surplus = prefix_net_val + s * d_arr[s]
            # Revenue = price - cost = sum p_n(top-s) - s*d_s - sum c_n(top-s)
            prefix_p = sum(p_arr[int(order[j])] for j in range(s))
            profit = prefix_p - s * d_arr[s] - prefix_cost
            eps = 1e-9
            if surplus > best_surplus + eps:
                best_surplus = surplus
                best_profit = profit
                best_source = "nonanchor"
            elif abs(surplus - best_surplus) <= eps and profit > best_profit + eps:
                best_profit = profit
                best_source = "nonanchor"

        if best_source == "outside":
            outside_count += 1
        elif best_source == "anchor":
            anchor_chosen_count += 1
            total_profit += best_profit
        else:
            nonanchor_chosen_count += 1
            total_profit += best_profit

    return {
        "oos_revenue": total_profit / k_count,
        "outside_count": outside_count,
        "anchor_chosen_count": anchor_chosen_count,
        "nonanchor_chosen_count": nonanchor_chosen_count,
        "total_customers": k_count,
    }


# ---------------------------------------------------------------------------
# Markdown summary
# ---------------------------------------------------------------------------

def write_markdown_summary(path: Path, payload: Dict) -> None:
    lines: List[str] = []
    lines.append("# Phase 3 Component Pricing Completion Probe")
    lines.append("")
    lines.append(f"- Instance: `{payload['instance_id']}`")
    lines.append(f"- Setup: `{payload['setup_key']}`")
    lines.append(f"- Anchor count: `{payload['anchor_count']}`")
    lines.append(f"- Full bundle count: `{payload['full_bundle_count']}`")
    lines.append(f"- N products: `{payload['n_products']}`")
    lines.append("")
    lines.append("## Baseline")
    lines.append("")
    lines.append(f"- Restricted FCP OOS revenue: `{payload['baseline']['restricted_oos_revenue']:.6f}`")
    lines.append(f"- Restricted FCP In-sample revenue: `{payload['baseline']['restricted_in_sample_revenue']:.6f}`")
    lines.append(f"- BSP OOS revenue: `{payload['bsp_oos_revenue']:.6f}`")
    lines.append("")
    lines.append("## Component Pricing LP")
    lines.append("")
    cp = payload["component_pricing"]
    lines.append(f"- Solver status: `{cp['solver_status']}`")
    lines.append(f"- Feasible: `{cp['feasible']}`")
    lines.append(f"- Runtime: `{cp['runtime']:.4f}s`")
    lines.append(f"- Model vars: `{cp['model_num_vars']}`")
    lines.append(f"- Model constraints: `{cp['model_num_constrs']}`")
    lines.append(f"- Constraint breakdown: `{cp['constraint_count']}`")
    lines.append("")
    if cp["feasible"]:
        lines.append("### Item Prices (p_n)")
        lines.append("```")
        for n, val in sorted(cp["item_prices"].items()):
            lines.append(f"  p[{n}] = {val:.6f}")
        lines.append("```")
        lines.append("")
        lines.append("### Size Discounts (d_s)")
        lines.append("```")
        for s, val in sorted(cp["size_discounts"].items()):
            lines.append(f"  d[{s}] = {val:.6f}")
        lines.append("```")
        lines.append("")
        lines.append("## Hybrid OOS Evaluation")
        lines.append("")
        hyb = payload["hybrid_oos"]
        lines.append(f"- **Hybrid OOS revenue: `{hyb['oos_revenue']:.6f}`**")
        lines.append(f"- Outside option count: `{hyb['outside_count']}`")
        lines.append(f"- Anchor chosen count: `{hyb['anchor_chosen_count']}`")
        lines.append(f"- Non-anchor chosen count: `{hyb['nonanchor_chosen_count']}`")
        lines.append("")
        lines.append("## Verification")
        lines.append("")
        lines.append(f"- Anchor preserved: `{payload['anchor_preserved']}`")
        sa = payload["subadditivity"]
        lines.append(f"- Subadditivity violations: `{sa['violation_count']}`")
        lines.append(f"- Max violation: `{sa['max_violation']:.8f}`")
        lines.append("")
        lines.append("## Revenue Comparison")
        lines.append("")
        lines.append("| Method | OOS Revenue |")
        lines.append("| --- | ---: |")
        lines.append(f"| Restricted FCP | {payload['baseline']['restricted_oos_revenue']:.6f} |")
        lines.append(f"| BSP | {payload['bsp_oos_revenue']:.6f} |")
        lines.append(f"| **Hybrid (Component Pricing)** | **{hyb['oos_revenue']:.6f}** |")
    lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Phase 3 Component Pricing Completion probe.")
    parser.add_argument(
        "--instance-path", type=Path,
        default=Path("/Users/sensen/.openclaw/workspace/domains/revenue-management/"
                      "experiments/cpbsd_fcp_pruned_mb_compare_n10k50_strict300/instances/"
                      "cpbsd_instance_001_N10_K50_normal_rho0.0_full_hvhm.msgpack"),
    )
    parser.add_argument(
        "--fcp-result-path", type=Path,
        default=Path("/Users/sensen/.openclaw/workspace/domains/revenue-management/"
                      "experiments/cpbsd_fcp_pruned_mb_compare_n10k50_strict300/results/"
                      "cpbsd_instance_001_N10_K50_normal_rho0.0_full_hvhm__fcp_pruned_mb.json"),
    )
    parser.add_argument(
        "--bsp-result-path", type=Path,
        default=Path("/Users/sensen/.openclaw/workspace/domains/revenue-management/"
                      "experiments/fcp_mb_phase2_selected_n10_n30_5inst/n10/"
                      "normal_rho0.0_full_hvhm/runs/seed_20260413/results/"
                      "cpbsd_instance_001_N10_K50_normal_rho0.0_full_hvhm__bsp.json"),
    )
    parser.add_argument(
        "--output-root", type=Path,
        default=Path("/Users/sensen/.openclaw/workspace/domains/revenue-management/"
                      "experiments/phase3_oos_component_pricing_probe_n10_normal_rho0.0_full_hvhm_inst001"),
    )
    parser.add_argument("--k-out", type=int, default=5000)
    parser.add_argument("--time-limit", type=float, default=300.0)
    parser.add_argument("--output-flag", type=int, default=1)
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()
    ensure_dir(args.output_root)

    print("=== Phase 3 Component Pricing Completion Probe ===")
    print(f"Instance: {args.instance_path.name}")

    # Load data
    obj, v_kn, c_n = load_msgpack_with_setup(args.instance_path)
    setup = obj["setup"]
    n_products = int(setup["n_products"])
    fcp_result = load_json(args.fcp_result_path)
    full_assortments = build_assortments(n_products)
    anchor_prices = build_anchor_prices(fcp_result, full_assortments)

    # Remove empty bundle from anchor set if present
    anchor_prices.pop(0, None)

    restricted_assortments = np.asarray(fcp_result["assortments"], dtype=int)
    restricted_prices = normalize_numeric_keys(fcp_result["bundle_prices_full"])
    v_out = generate_v_out(setup, args.k_out)

    print(f"N = {n_products}, K_in = {v_kn.shape[0]}, K_out = {v_out.shape[0]}")
    print(f"Anchor count: {len(anchor_prices)}")
    print(f"Full bundle count: {full_assortments.shape[0]}")

    # Baselines
    baseline_restricted_oos = float(eval_mb_policy(v_out, c_n, restricted_prices, restricted_assortments))
    baseline_restricted_ins = float(fcp_result["objective"])

    # BSP baseline
    bsp_result = load_json(args.bsp_result_path)
    from solve_mb_bsp_on_cpbsd_v2 import eval_bsp_policy
    bsp_oos = float(eval_bsp_policy(v_out, c_n, bsp_result["size_prices"]))

    print(f"\nBaseline restricted FCP OOS:  {baseline_restricted_oos:.6f}")
    print(f"Baseline restricted FCP InS:  {baseline_restricted_ins:.6f}")
    print(f"BSP OOS:                      {bsp_oos:.6f}")

    # Solve component pricing LP
    print("\n--- Solving Component Pricing LP ---")
    cp_result = solve_component_pricing(
        full_assortments=full_assortments,
        anchor_prices=anchor_prices,
        n_products=n_products,
        objective_mode="max_discount",
        output_flag=args.output_flag,
        time_limit=args.time_limit,
    )
    print(f"Status: {cp_result['solver_status']}, Feasible: {cp_result['feasible']}")
    print(f"Constraints: {cp_result['constraint_count']}")

    # Build output payload
    payload = {
        "instance_id": args.instance_path.stem,
        "setup_key": f"N{n_products}_{setup.get('dist_family','?')}_{setup.get('heterogeneity','?')}_{setup.get('cost_scenario','?')}",
        "n_products": n_products,
        "anchor_count": len(anchor_prices),
        "full_bundle_count": full_assortments.shape[0],
        "baseline": {
            "restricted_oos_revenue": baseline_restricted_oos,
            "restricted_in_sample_revenue": baseline_restricted_ins,
        },
        "bsp_oos_revenue": bsp_oos,
        "component_pricing": cp_result,
        "hybrid_oos": None,
        "anchor_preserved": None,
        "subadditivity": None,
    }

    if cp_result["feasible"]:
        item_prices = cp_result["item_prices"]
        size_discounts = cp_result["size_discounts"]

        print(f"\nItem prices:    {[f'{v:.4f}' for v in item_prices.values()]}")
        print(f"Size discounts: {[f'{v:.4f}' for v in size_discounts.values()]}")

        # Build hybrid prices and verify
        hybrid_prices = build_hybrid_prices(
            full_assortments, anchor_prices, item_prices, size_discounts,
        )
        anchor_ok = check_anchor_preservation(hybrid_prices, anchor_prices)
        subadd_check = check_global_subadditivity(full_assortments, hybrid_prices)

        print(f"\nAnchor preserved: {anchor_ok}")
        print(f"Subadditivity violations: {subadd_check['violation_count']}")
        print(f"Max violation: {subadd_check['max_violation']:.8f}")

        # Build anchor assortments array for hybrid evaluator
        anchor_indices = sorted(anchor_prices.keys())
        anchor_assortments_arr = full_assortments[anchor_indices]

        # Evaluate OOS with hybrid menu
        hybrid_oos = eval_hybrid_oos(
            v_eval=v_out,
            c_n=c_n,
            anchor_prices=anchor_prices,
            anchor_assortments=anchor_assortments_arr,
            item_prices=item_prices,
            size_discounts=size_discounts,
        )
        print(f"\n=== Hybrid OOS Revenue: {hybrid_oos['oos_revenue']:.6f} ===")
        print(f"Outside:    {hybrid_oos['outside_count']}")
        print(f"Anchor:     {hybrid_oos['anchor_chosen_count']}")
        print(f"Non-anchor: {hybrid_oos['nonanchor_chosen_count']}")

        # Also evaluate using eval_mb_policy for cross-check
        hybrid_oos_mb = float(eval_mb_policy(v_out, c_n, hybrid_prices, full_assortments))
        print(f"Cross-check (eval_mb_policy): {hybrid_oos_mb:.6f}")

        payload["hybrid_oos"] = hybrid_oos
        payload["hybrid_oos_mb_crosscheck"] = hybrid_oos_mb
        payload["anchor_preserved"] = anchor_ok
        payload["subadditivity"] = subadd_check
    else:
        print("\n*** INFEASIBLE - component pricing LP has no solution ***")
        if cp_result.get("iis_constraints"):
            print(f"\nIIS constraints ({len(cp_result['iis_constraints'])}):")
            for c_name in cp_result["iis_constraints"]:
                print(f"  {c_name}")
        payload["iis_constraints"] = cp_result.get("iis_constraints")

    # Write outputs
    summary_json_path = args.output_root / "component_pricing_probe_summary.json"
    summary_json_path.write_text(
        json.dumps(payload, indent=2, default=json_default, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nJSON summary: {summary_json_path}")

    summary_md_path = args.output_root / "component_pricing_probe_summary.md"
    write_markdown_summary(summary_md_path, payload)
    print(f"MD summary:   {summary_md_path}")


if __name__ == "__main__":
    main()
