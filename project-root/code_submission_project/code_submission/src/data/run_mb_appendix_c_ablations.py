import argparse
import csv
import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

import gurobipy as gp
import numpy as np
from gurobipy import GRB


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.append(str(SCRIPT_DIR))

from compare_mb_appendix_c_literal import (
    DEFAULT_OUTPUT_ROOT,
    ensure_dir,
    full_price_vector,
    literal_partition_families,
    load_msgpack,
    markdown_table,
    representative_instances,
    sample_out_of_sample_valuations,
    status_text,
    write_csv,
)
from solve_mb_bsp_on_cpbsd_v2 import (
    MB_FORMULATION_VERSION,
    _disjoint_partition_pairs,
    build_assortments,
    eval_mb_policy,
    json_default,
    solve_mb,
)


ABLATION_VARIANTS = [
    ("current", "Current solver", {"outside_mode": "explicit_empty", "exclude_self_envy": False, "subadd_mode": "pairwise"}),
    ("outside_only", "Paper outside option", {"outside_mode": "paper", "exclude_self_envy": False, "subadd_mode": "pairwise"}),
    ("envy_only", "Paper envy indexing", {"outside_mode": "explicit_empty", "exclude_self_envy": True, "subadd_mode": "pairwise"}),
    ("subadd_only", "Full partition subadditivity", {"outside_mode": "explicit_empty", "exclude_self_envy": False, "subadd_mode": "full_partition"}),
    ("all_paper_switches", "All Appendix C switches", {"outside_mode": "paper", "exclude_self_envy": True, "subadd_mode": "full_partition"}),
]


def solve_mb_ablation(
    v_kn: np.ndarray,
    c_n: np.ndarray,
    *,
    outside_mode: str,
    exclude_self_envy: bool,
    subadd_mode: str,
    time_limit: float,
    mip_gap: float,
    output_flag: int = 0,
) -> Dict:
    k_count, n_products = v_kn.shape
    assortments = build_assortments(n_products)
    bundle_count = assortments.shape[0]
    revenues = v_kn @ assortments.T
    bundle_cost = assortments @ c_n
    revenue_ub = float(np.max(revenues))
    weights = np.ones((k_count, 1), dtype=float) / k_count

    if outside_mode == "explicit_empty":
        active_idx = list(range(bundle_count))
    elif outside_mode == "paper":
        active_idx = list(range(1, bundle_count))
    else:
        raise ValueError(f"Unknown outside_mode: {outside_mode}")

    model = gp.Model(f"MB_ablation_{outside_mode}_{subadd_mode}_{'exclude' if exclude_self_envy else 'include'}")
    p = model.addVars(active_idx, vtype=GRB.CONTINUOUS, lb=0.0, name="p")
    theta = model.addVars(k_count, active_idx, vtype=GRB.BINARY, name="theta")
    surplus = model.addVars(k_count, vtype=GRB.CONTINUOUS, lb=0.0, name="w")
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

    if subadd_mode == "pairwise":
        for i in active_idx:
            if i == 0:
                continue
            for pair_idx, (m1, m2) in enumerate(_disjoint_partition_pairs(assortments[i])):
                model.addConstr(p[i] <= p[m1] + p[m2], name=f"subadd_pair_{i}_{pair_idx}")
    elif subadd_mode == "full_partition":
        for i in active_idx:
            if i == 0:
                continue
            for part_no, family in enumerate(literal_partition_families(i, n_products)):
                model.addConstr(p[i] <= gp.quicksum(p[j] for j in family), name=f"subadd_full_{i}_{part_no}")
    else:
        raise ValueError(f"Unknown subadd_mode: {subadd_mode}")

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

    if outside_mode == "explicit_empty":
        model.addConstrs(
            (gp.quicksum(theta[k, i] for i in active_idx) == 1 for k in range(k_count)),
            name="one_choice",
        )
        model.addConstrs((s_terms[k, 0] == 0 for k in range(k_count)), name="empty_bundle")
    else:
        model.addConstrs(
            (gp.quicksum(theta[k, i] for i in active_idx) <= 1 for k in range(k_count)),
            name="at_most_one",
        )

    if exclude_self_envy:
        model.addConstrs(
            (
                surplus[k] >= gp.quicksum(float(revenues[k, i]) * theta[j, i] - payment[j, i] for i in active_idx)
                for k in range(k_count)
                for j in range(k_count)
                if j != k
            ),
            name="envy_exclude_self",
        )
    else:
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
        "runtime": model.Runtime,
        "wall_time": t1 - t0,
        "mip_gap": float(model.MIPGap) if model.SolCount > 0 else None,
        "objective": float(model.ObjVal) if model.SolCount > 0 else None,
        "model_num_vars": int(model.NumVars),
        "model_num_binvars": int(model.NumBinVars),
        "model_num_constrs": int(model.NumConstrs),
        "policy_scope": f"ablation_{outside_mode}_{subadd_mode}_{'exclude' if exclude_self_envy else 'include'}" if model.SolCount > 0 else "missing",
        "bundle_prices_full": None,
        "bundle_prices_selected": None,
        "chosen_bundle_idx_by_customer": None,
        "assortments": assortments,
        "outside_mode": outside_mode,
        "exclude_self_envy": exclude_self_envy,
        "subadd_mode": subadd_mode,
        "mb_formulation_version": MB_FORMULATION_VERSION,
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
        result["bundle_prices_full"] = bundle_prices_full
        result["bundle_prices_selected"] = bundle_prices_selected
        result["chosen_bundle_idx_by_customer"] = chosen
    return result


def solve_variant(v_kn: np.ndarray, c_n: np.ndarray, variant_key: str, variant_cfg: Dict, time_limit: float, mip_gap: float) -> Dict:
    return solve_mb_ablation(v_kn, c_n, time_limit=time_limit, mip_gap=mip_gap, output_flag=0, **variant_cfg)


def compare_instance(instance_path: Path, *, time_limit: float, mip_gap: float, out_k: int) -> Tuple[List[Dict], Dict]:
    obj = load_msgpack(instance_path)
    v_kn = np.asarray(obj["valuation_samples_V"], dtype=float)
    c_n = np.asarray(obj["production_cost_c"], dtype=float)
    setup = obj["setup"]
    v_out = sample_out_of_sample_valuations(setup, out_k=out_k)
    assortments = build_assortments(v_kn.shape[1])

    variant_results = {}
    for variant_key, variant_name, variant_cfg in ABLATION_VARIANTS:
        variant_results[variant_key] = solve_variant(v_kn, c_n, variant_key, variant_cfg, time_limit, mip_gap)

    current_prices = variant_results["current"].get("bundle_prices_full") or {}
    current_in = eval_mb_policy(v_kn, c_n, current_prices, assortments)
    current_out = eval_mb_policy(v_out, c_n, current_prices, assortments)
    current_vec = full_price_vector(current_prices, assortments.shape[0])

    rows = []
    raw_payload = {}
    for variant_key, variant_name, _variant_cfg in ABLATION_VARIANTS:
        res = variant_results[variant_key]
        prices = res.get("bundle_prices_full") or {}
        rev_in = eval_mb_policy(v_kn, c_n, prices, assortments) if prices else None
        rev_out = eval_mb_policy(v_out, c_n, prices, assortments) if prices else None
        vec = full_price_vector(prices, assortments.shape[0])
        rows.append(
            {
                "instance_id": instance_path.stem,
                "variant_key": variant_key,
                "variant_name": variant_name,
                "dist_family": setup["dist_family"],
                "rho": setup["rho"],
                "heterogeneity": setup["heterogeneity"],
                "cost_scenario": setup["cost_scenario"],
                "status_text": status_text(int(res["solver_status"])),
                "objective": res.get("objective"),
                "revenue_in_sample": rev_in,
                "revenue_out_sample": rev_out,
                "delta_in_vs_current": None if rev_in is None else float(rev_in - current_in),
                "delta_out_vs_current": None if rev_out is None else float(rev_out - current_out),
                "price_l1_vs_current": float(np.sum(np.abs(vec - current_vec))),
                "price_linf_vs_current": float(np.max(np.abs(vec - current_vec))),
                "runtime": res.get("runtime"),
                "bundle_count_selected": len(res.get("bundle_prices_selected") or {}),
            }
        )
        raw_payload[variant_key] = res
    return rows, raw_payload


def summarize(rows: List[Dict]) -> List[Dict]:
    out = []
    for variant_key, variant_name, _cfg in ABLATION_VARIANTS:
        sub = [row for row in rows if row["variant_key"] == variant_key]
        out.append(
            {
                "variant_key": variant_key,
                "variant_name": variant_name,
                "instances": len(sub),
                "mean_revenue_in_sample": float(np.mean([row["revenue_in_sample"] for row in sub])),
                "mean_revenue_out_sample": float(np.mean([row["revenue_out_sample"] for row in sub])),
                "mean_delta_in_vs_current": float(np.mean([row["delta_in_vs_current"] for row in sub])),
                "mean_delta_out_vs_current": float(np.mean([row["delta_out_vs_current"] for row in sub])),
                "mean_price_l1_vs_current": float(np.mean([row["price_l1_vs_current"] for row in sub])),
                "mean_price_linf_vs_current": float(np.mean([row["price_linf_vs_current"] for row in sub])),
                "optimal_count": int(sum(row["status_text"] == "OPTIMAL" for row in sub)),
                "time_limit_count": int(sum(row["status_text"] == "TIME_LIMIT" for row in sub)),
            }
        )
    return out


def render_report(output_root: Path, rows: List[Dict], summary_rows: List[Dict], instance_count: int, time_limit: float, out_k: int):
    lines = [
        "# Ablation Results",
        "",
        "## Scope",
        "",
        f"- Compared `{len(ABLATION_VARIANTS)}` MB variants on `{instance_count}` representative instances.",
        f"- Solve time limit per variant: `{time_limit}` seconds.",
        f"- Out-of-sample evaluation size: `{out_k}` customers per instance.",
        "",
        "## Summary by Variant",
        "",
        markdown_table(
            [
                "variant_key",
                "variant_name",
                "instances",
                "mean_revenue_in_sample",
                "mean_revenue_out_sample",
                "mean_delta_in_vs_current",
                "mean_delta_out_vs_current",
                "mean_price_l1_vs_current",
                "optimal_count",
                "time_limit_count",
            ],
            summary_rows,
        ),
        "",
        "## Per-Instance Rows",
        "",
        markdown_table(
            [
                "instance_id",
                "variant_key",
                "status_text",
                "delta_in_vs_current",
                "delta_out_vs_current",
                "price_l1_vs_current",
                "price_linf_vs_current",
            ],
            rows,
        ),
    ]
    (output_root / "ABLATION_RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Run MB Appendix C ablation study.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--time-limit", type=float, default=120.0)
    parser.add_argument("--mip-gap", type=float, default=1e-2)
    parser.add_argument("--out-k", type=int, default=2000)
    parser.add_argument("--instance", action="append", default=[])
    args = parser.parse_args()

    ensure_dir(args.output_root)
    ablation_root = args.output_root / "ablation"
    raw_root = ablation_root / "raw_results"
    ensure_dir(ablation_root)
    ensure_dir(raw_root)

    instance_paths = [Path(p) for p in args.instance] if args.instance else representative_instances()

    all_rows = []
    for instance_path in instance_paths:
        rows, raw_payload = compare_instance(instance_path, time_limit=args.time_limit, mip_gap=args.mip_gap, out_k=args.out_k)
        all_rows.extend(rows)
        stem = instance_path.stem
        for variant_key, payload in raw_payload.items():
            (raw_root / f"{stem}__{variant_key}.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, default=json_default),
                encoding="utf-8",
            )
        print(json.dumps({"instance": stem, "variants_done": len(rows)}, ensure_ascii=False))

    summary_rows = summarize(all_rows)
    write_csv(ablation_root / "ablation_rows.csv", all_rows)
    write_csv(ablation_root / "ablation_summary.csv", summary_rows)
    render_report(ablation_root, all_rows, summary_rows, len(instance_paths), args.time_limit, args.out_k)


if __name__ == "__main__":
    main()
