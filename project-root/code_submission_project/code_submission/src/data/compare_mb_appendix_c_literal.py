import argparse
import csv
import json
import os
import sys
import time
from functools import lru_cache
from itertools import combinations
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

import gurobipy as gp
import msgpack
import msgpack_numpy as mnp
import numpy as np
from gurobipy import GRB


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.append(str(SCRIPT_DIR))

from generate_data_CPBSD import sample_valuations, valuation_means
from solve_mb_bsp_on_cpbsd_v2 import (
    MB_FORMULATION_VERSION,
    build_assortments,
    eval_mb_policy,
    json_default,
    solve_mb,
)


DEFAULT_OUTPUT_ROOT = Path(
    "/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/mb_literal_appendix_c_check"
)
BASELINES_V2_ROOT = Path(
    "/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/cpbsd_baselines_v2"
)
MAIN_N5_ROOT = Path(
    "/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/cpbsd_main_n5"
)


def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def load_msgpack(path: Path) -> dict:
    with path.open("rb") as f:
        return msgpack.load(f, object_hook=mnp.decode)


def sample_out_of_sample_valuations(setup: dict, out_k: int = 5000) -> np.ndarray:
    rng = np.random.default_rng(int(setup["seed"]) + 99991)
    means = valuation_means(int(setup["n_products"]), setup["heterogeneity"])
    return sample_valuations(
        k=out_k,
        means=means,
        family=setup["dist_family"],
        rho=float(setup["rho"]),
        rng=rng,
    )


def _canonical_partition(blocks: Sequence[Sequence[int]]) -> Tuple[Tuple[int, ...], ...]:
    return tuple(sorted(tuple(sorted(block)) for block in blocks))


def _set_partitions(items: Tuple[int, ...]) -> Iterable[Tuple[Tuple[int, ...], ...]]:
    if len(items) == 1:
        yield ((items[0],),)
        return
    first = items[0]
    for partition in _set_partitions(items[1:]):
        yield ((first,),) + partition
        for idx in range(len(partition)):
            updated = list(partition)
            updated[idx] = tuple(sorted(updated[idx] + (first,)))
            yield _canonical_partition(updated)


@lru_cache(maxsize=None)
def literal_partition_families(bundle_idx: int, n_products: int) -> Tuple[Tuple[int, ...], ...]:
    bits = np.array(list(map(int, format(bundle_idx, f"0{n_products}b"))), dtype=int)
    items = tuple(np.where(bits == 1)[0].tolist())
    if len(items) <= 1:
        return tuple()
    seen = set()
    bundle_families = []
    for partition in _set_partitions(items):
        partition = _canonical_partition(partition)
        if len(partition) <= 1 or partition in seen:
            continue
        seen.add(partition)
        family = []
        for block in partition:
            arr = np.zeros(n_products, dtype=int)
            arr[list(block)] = 1
            family.append(int("".join(map(str, arr.tolist())), 2))
        bundle_families.append(tuple(sorted(family)))
    return tuple(sorted(set(bundle_families)))


def solve_mb_appendix_c_literal(
    v_kn: np.ndarray,
    c_n: np.ndarray,
    *,
    time_limit: float = 300.0,
    mip_gap: float = 1e-2,
    output_flag: int = 0,
) -> Dict:
    k_count, n_products = v_kn.shape
    assortments = build_assortments(n_products)
    nonempty_idx = list(range(1, assortments.shape[0]))
    bundle_count = len(nonempty_idx)
    nonempty_assortments = assortments[1:]
    valuations = v_kn @ nonempty_assortments.T
    bundle_cost = nonempty_assortments @ c_n
    revenue_ub = float(np.max(valuations))
    weights = np.ones((k_count, 1), dtype=float) / k_count

    model = gp.Model("MB_Appendix_C_Literal")
    p = model.addVars(nonempty_idx, vtype=GRB.CONTINUOUS, lb=0.0, name="p")
    y = model.addVars(k_count, nonempty_idx, vtype=GRB.BINARY, name="y")
    q = model.addVars(k_count, nonempty_idx, vtype=GRB.CONTINUOUS, lb=0.0, name="q")
    w = model.addVars(k_count, vtype=GRB.CONTINUOUS, lb=0.0, name="w")

    model.setObjective(
        gp.quicksum(
            weights[k, 0] * (q[k, bundle_idx] - float(bundle_cost[bundle_idx - 1]) * y[k, bundle_idx])
            for k in range(k_count)
            for bundle_idx in nonempty_idx
        ),
        GRB.MAXIMIZE,
    )

    model.addConstrs(
        (w[k] >= float(valuations[k, bundle_idx - 1]) - p[bundle_idx] for k in range(k_count) for bundle_idx in nonempty_idx),
        name="surplus_lb",
    )
    model.addConstrs(
        (gp.quicksum(y[k, bundle_idx] for bundle_idx in nonempty_idx) <= 1 for k in range(k_count)),
        name="at_most_one_bundle",
    )
    model.addConstrs(
        (q[k, bundle_idx] >= p[bundle_idx] - revenue_ub * (1 - y[k, bundle_idx]) for k in range(k_count) for bundle_idx in nonempty_idx),
        name="payment_lb",
    )
    model.addConstrs(
        (q[k, bundle_idx] <= p[bundle_idx] for k in range(k_count) for bundle_idx in nonempty_idx),
        name="payment_ub",
    )
    model.addConstrs(
        (
            w[k]
            == gp.quicksum(float(valuations[k, bundle_idx - 1]) * y[k, bundle_idx] - q[k, bundle_idx] for bundle_idx in nonempty_idx)
            for k in range(k_count)
        ),
        name="surplus_eq",
    )
    model.addConstrs(
        (
            w[k]
            >= gp.quicksum(float(valuations[k, bundle_idx - 1]) * y[j, bundle_idx] - q[j, bundle_idx] for bundle_idx in nonempty_idx)
            for k in range(k_count)
            for j in range(k_count)
            if j != k
        ),
        name="envy_like_literal",
    )

    for bundle_idx in nonempty_idx:
        for part_no, family in enumerate(literal_partition_families(bundle_idx, n_products)):
            model.addConstr(
                p[bundle_idx] <= gp.quicksum(p[part] for part in family),
                name=f"subadd_literal_{bundle_idx}_{part_no}",
            )

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
        "mip_gap": float(model.MIPGap) if model.SolCount > 0 else None,
        "objective": float(model.ObjVal) if model.SolCount > 0 else None,
        "policy_scope": "paper_appendix_c_literal" if model.SolCount > 0 else "missing",
        "bundle_prices_full": None,
        "bundle_prices_selected": None,
        "chosen_bundle_idx_by_customer": None,
        "assortments": assortments,
        "literal_partition_counts": {str(i): len(literal_partition_families(i, n_products)) for i in nonempty_idx},
    }
    if model.SolCount > 0:
        bundle_prices_full = {0: 0.0}
        bundle_prices_selected = {}
        chosen_bundle_idx = []
        for bundle_idx in nonempty_idx:
            bundle_prices_full[bundle_idx] = float(p[bundle_idx].X)
        for k in range(k_count):
            chosen = 0
            for bundle_idx in nonempty_idx:
                if y[k, bundle_idx].X >= 1 - 1e-2:
                    chosen = int(bundle_idx)
                    break
            chosen_bundle_idx.append(chosen)
        for bundle_idx in nonempty_idx:
            if any(choice == bundle_idx for choice in chosen_bundle_idx):
                bundle_prices_selected[bundle_idx] = float(p[bundle_idx].X)
        result["bundle_prices_full"] = bundle_prices_full
        result["bundle_prices_selected"] = bundle_prices_selected
        result["chosen_bundle_idx_by_customer"] = chosen_bundle_idx
    return result


def status_text(code: int) -> str:
    mapping = {
        2: "OPTIMAL",
        9: "TIME_LIMIT",
        3: "INFEASIBLE",
        4: "INF_OR_UNBD",
        5: "UNBOUNDED",
    }
    return mapping.get(code, f"STATUS_{code}")


def full_price_vector(bundle_prices_full: Dict, bundle_count: int) -> np.ndarray:
    out = np.zeros(bundle_count, dtype=float)
    for idx in range(bundle_count):
        out[idx] = float((bundle_prices_full or {}).get(idx, 0.0))
    return out


def compare_one_instance(instance_path: Path, *, time_limit: float, mip_gap: float, out_k: int) -> Tuple[Dict, Dict, Dict]:
    obj = load_msgpack(instance_path)
    v_kn = np.asarray(obj["valuation_samples_V"], dtype=float)
    c_n = np.asarray(obj["production_cost_c"], dtype=float)
    setup = obj["setup"]
    v_out = sample_out_of_sample_valuations(setup, out_k=out_k)

    current = solve_mb(v_kn, c_n, time_limit=time_limit, mip_gap=mip_gap, output_flag=0)
    literal = solve_mb_appendix_c_literal(v_kn, c_n, time_limit=time_limit, mip_gap=mip_gap, output_flag=0)

    assortments = build_assortments(v_kn.shape[1])
    current_prices = current.get("bundle_prices_full") or {}
    literal_prices = literal.get("bundle_prices_full") or {}
    current_in = eval_mb_policy(v_kn, c_n, current_prices, assortments) if current_prices else None
    current_out = eval_mb_policy(v_out, c_n, current_prices, assortments) if current_prices else None
    literal_in = eval_mb_policy(v_kn, c_n, literal_prices, assortments) if literal_prices else None
    literal_out = eval_mb_policy(v_out, c_n, literal_prices, assortments) if literal_prices else None

    current_vec = full_price_vector(current_prices, assortments.shape[0])
    literal_vec = full_price_vector(literal_prices, assortments.shape[0])
    price_l1 = float(np.sum(np.abs(current_vec - literal_vec)))
    price_linf = float(np.max(np.abs(current_vec - literal_vec)))

    row = {
        "instance_id": instance_path.stem,
        "dist_family": setup["dist_family"],
        "rho": setup["rho"],
        "heterogeneity": setup["heterogeneity"],
        "cost_scenario": setup["cost_scenario"],
        "current_status": status_text(int(current["solver_status"])),
        "literal_status": status_text(int(literal["solver_status"])),
        "current_objective": current.get("objective"),
        "literal_objective": literal.get("objective"),
        "objective_delta_literal_minus_current": None if current.get("objective") is None or literal.get("objective") is None else float(literal["objective"] - current["objective"]),
        "current_revenue_in_sample": current_in,
        "literal_revenue_in_sample": literal_in,
        "delta_in_sample": None if current_in is None or literal_in is None else float(literal_in - current_in),
        "current_revenue_out_sample": current_out,
        "literal_revenue_out_sample": literal_out,
        "delta_out_sample": None if current_out is None or literal_out is None else float(literal_out - current_out),
        "price_l1_distance": price_l1,
        "price_linf_distance": price_linf,
        "current_runtime": current.get("runtime"),
        "literal_runtime": literal.get("runtime"),
        "bundle_count_selected_current": len(current.get("bundle_prices_selected") or {}),
        "bundle_count_selected_literal": len(literal.get("bundle_prices_selected") or {}),
    }
    return row, current, literal


def representative_instances() -> List[Path]:
    hard = sorted((BASELINES_V2_ROOT / "instances" / "n5").glob("cpbsd_instance_*_N5_K50_normal_rho0.0_full_hvhm.msgpack"))
    diverse = [
        MAIN_N5_ROOT / "instances" / "n5" / "cpbsd_instance_001_N5_K50_exponential_rho-0.5_none_zero.msgpack",
        MAIN_N5_ROOT / "instances" / "n5" / "cpbsd_instance_001_N5_K50_logit_rho0.5_partial_zero.msgpack",
        MAIN_N5_ROOT / "instances" / "n5" / "cpbsd_instance_001_N5_K50_lognormal_rho-0.5_full_zero.msgpack",
        MAIN_N5_ROOT / "instances" / "n5" / "cpbsd_instance_001_N5_K50_uniform_rho0.5_full_hvlm.msgpack",
    ]
    out = []
    out.extend(hard[:5])
    out.extend([path for path in diverse if path.exists()])
    return out


def write_csv(path: Path, rows: List[Dict]):
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def markdown_table(columns: List[str], rows: List[Dict]) -> str:
    if not rows:
        return "_No rows_"
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join(["---"] * len(columns)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(col, "")) for col in columns) + " |")
    return "\n".join(lines)


def summarize_rows(rows: List[Dict]) -> Dict:
    def _mean(key: str) -> float:
        vals = [float(row[key]) for row in rows if row.get(key) not in ("", None)]
        return float(np.mean(vals)) if vals else float("nan")

    return {
        "instances": len(rows),
        "mean_delta_in_sample": _mean("delta_in_sample"),
        "mean_delta_out_sample": _mean("delta_out_sample"),
        "mean_objective_delta": _mean("objective_delta_literal_minus_current"),
        "mean_price_l1_distance": _mean("price_l1_distance"),
        "mean_price_linf_distance": _mean("price_linf_distance"),
        "literal_better_in_count": sum(float(row["delta_in_sample"]) > 1e-8 for row in rows if row.get("delta_in_sample") not in ("", None)),
        "literal_better_out_count": sum(float(row["delta_out_sample"]) > 1e-8 for row in rows if row.get("delta_out_sample") not in ("", None)),
        "same_status_count": sum(row["current_status"] == row["literal_status"] for row in rows),
    }


def render_results(output_root: Path, rows: List[Dict], summary: Dict, instance_paths: List[Path], time_limit: float, out_k: int):
    lines = [
        "# Results",
        "",
        "## Scope",
        "",
        f"- Compared current MB solver against a literal-transcription Appendix C solver on `{len(instance_paths)}` instances.",
        f"- Solve time limit per solver: `{time_limit}` seconds.",
        f"- Out-of-sample evaluation size: `{out_k}` customers per instance.",
        "",
        "## Summary",
        "",
        markdown_table(
            list(summary.keys()),
            [summary],
        ),
        "",
        "## Per-Instance Comparison",
        "",
        markdown_table(
            [
                "instance_id",
                "dist_family",
                "rho",
                "heterogeneity",
                "cost_scenario",
                "current_status",
                "literal_status",
                "delta_in_sample",
                "delta_out_sample",
                "objective_delta_literal_minus_current",
                "price_l1_distance",
                "price_linf_distance",
            ],
            rows,
        ),
        "",
        "## Preliminary Interpretation",
        "",
        "- This file only answers whether the literal Appendix C transcription behaves differently from the current implementation on a small representative set.",
        "- It does not yet constitute a full paper-level reproduction.",
    ]
    (output_root / "RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Compare current MB solver with literal Appendix C transcription.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--time-limit", type=float, default=300.0)
    parser.add_argument("--mip-gap", type=float, default=1e-2)
    parser.add_argument("--out-k", type=int, default=5000)
    parser.add_argument("--instance", action="append", default=[])
    args = parser.parse_args()

    ensure_dir(args.output_root)
    instance_paths = [Path(p) for p in args.instance] if args.instance else representative_instances()

    rows = []
    raw_root = args.output_root / "raw_results"
    ensure_dir(raw_root)

    for instance_path in instance_paths:
        row, current, literal = compare_one_instance(
            instance_path,
            time_limit=args.time_limit,
            mip_gap=args.mip_gap,
            out_k=args.out_k,
        )
        rows.append(row)
        stem = instance_path.stem
        (raw_root / f"{stem}__current_mb.json").write_text(json.dumps(current, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")
        (raw_root / f"{stem}__literal_mb.json").write_text(json.dumps(literal, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")
        print(json.dumps({"instance": stem, "delta_in": row["delta_in_sample"], "delta_out": row["delta_out_sample"]}, ensure_ascii=False))

    summary = summarize_rows(rows)
    write_csv(args.output_root / "comparison_rows.csv", rows)
    write_csv(args.output_root / "comparison_summary.csv", [summary])
    render_results(args.output_root, rows, summary, instance_paths, args.time_limit, args.out_k)


if __name__ == "__main__":
    main()
