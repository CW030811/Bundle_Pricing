import csv
import json
from pathlib import Path
import sys

import gurobipy as gp
import msgpack
import msgpack_numpy as mnp
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.append(str(SCRIPT_DIR))

from generate_data_CPBSD import generate_batch, sample_valuations, valuation_means
from plot_cpbsd_results_v2 import plot_ratio_boxplot
from solve_cpbsd_a import solve_cpbsd_a
from solve_cpbsd_milp import load_instance_from_msgpack, solve as solve_milp
from solve_mb_bsp_on_cpbsd_v2 import MB_FORMULATION_VERSION, extract_mb_policy_info, eval_bsp_policy, eval_mb_policy, json_default, solve_bsp, solve_mb


# Main N=5 grid for the current reproduction phase.
# This intentionally compares CPBSD-MILP, CPBSD-A, BSP, and MB only.
# CP, PB, PBDC, and BCB are intentionally excluded for now.
EXPERIMENT_SCOPE = "main_n5_grid_v2"
ROOT = Path("/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/cpbsd_main_n5_v2")
OUT_SAMPLE_K = 5000


def status_text(code):
    mapping = {
        2: "OPTIMAL",
        9: "TIME_LIMIT",
        3: "INFEASIBLE",
        4: "INF_OR_UNBD",
        5: "UNBOUNDED",
        -1: "LICENSE_LIMIT",
    }
    return mapping.get(code, f"STATUS_{code}")


def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def read_setup(msgpack_path: Path):
    with open(msgpack_path, "rb") as f:
        obj = msgpack.load(f, object_hook=mnp.decode)
    return obj.get("setup", {})


def evaluate_cpbsd_policy(v_eval: np.ndarray, c_n: np.ndarray, p: np.ndarray, d: np.ndarray) -> float:
    k_count, n_products = v_eval.shape
    total = 0.0
    for k in range(k_count):
        best_surplus = 0.0
        best_idx = None
        best_size = 0
        for size in range(1, n_products + 1):
            util = v_eval[k] - p + d[size]
            idx = np.argpartition(util, -size)[-size:]
            surplus = float(util[idx].sum())
            if surplus > best_surplus:
                best_surplus = surplus
                best_idx = idx
                best_size = size
        if best_surplus <= 0.0 or best_idx is None:
            continue
        total += float((p[best_idx] - c_n[best_idx]).sum() - best_size * d[best_size])
    return total / k_count


def sample_out_of_sample_valuations(setup: dict, out_k: int = OUT_SAMPLE_K) -> np.ndarray:
    rng = np.random.default_rng(int(setup["seed"]) + 99991)
    means = valuation_means(int(setup["n_products"]), setup["heterogeneity"])
    return sample_valuations(
        k=out_k,
        means=means,
        family=setup["dist_family"],
        rho=float(setup["rho"]),
        rng=rng,
    )


def append_row(
    rows,
    *,
    setup,
    method,
    instance_id,
    n,
    k,
    time_limit,
    solver_runtime,
    wall_time,
    nodes,
    status_code,
    mip_gap,
    best_bound,
    sol_count,
    big_m,
    objective_raw,
    revenue_in_sample,
    revenue_out_sample,
    policy_scope,
    bundle_price_count_full,
    bundle_price_count_selected,
    result_path,
    used_cache,
    error_message,
):
    rows.append(
        {
            "instance_id": instance_id,
            "seed": setup.get("seed", ""),
            "n": n,
            "k": k,
            "method": method,
            "experiment_scope": EXPERIMENT_SCOPE,
            "dist_family": setup.get("dist_family", ""),
            "rho": setup.get("rho", ""),
            "heterogeneity": setup.get("heterogeneity", ""),
            "cost_scenario": setup.get("cost_scenario", ""),
            "time_limit": time_limit,
            "solver_runtime": solver_runtime,
            "wall_time": wall_time,
            "nodes": nodes,
            "status_code": status_code,
            "status_text": status_text(status_code),
            "mip_gap": mip_gap,
            "best_bound": best_bound,
            "sol_count": sol_count,
            "big_m": big_m,
            "objective_raw": objective_raw,
            "revenue_in_sample": revenue_in_sample,
            "revenue_out_sample": revenue_out_sample,
            "ratio_to_bsp": None,
            "ratio_to_cpbsd": None,
            "baseline_method": "CPBSD-MILP",
            "policy_scope": policy_scope,
            "bundle_price_count_full": bundle_price_count_full,
            "bundle_price_count_selected": bundle_price_count_selected,
            "result_path": str(result_path),
            "used_cache": used_cache,
            "error_message": error_message,
        }
    )


def write_json(path: Path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")


def extract_milp_solution(res: dict):
    sol = (res.get("solution", {}) or {})
    p = np.array(sol.get("p", []), dtype=float)
    d = np.array(sol.get("d", []), dtype=float)
    return p, d, sol.get("objective", None)


def extract_cpbsd_a_solution(res: dict):
    p = np.array(res.get("p", []), dtype=float)
    d = np.array(res.get("d", []), dtype=float)
    return p, d, res.get("objective", None)


def load_cached_result(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"error": f"Failed to load cached result: {exc}"}


def extract_mb_solution(res: dict):
    mb_info = extract_mb_policy_info(res)
    return mb_info["bundle_prices_full"], mb_info["assortments"], res.get("objective"), mb_info


def main():
    inst_dir = ROOT / "instances" / "n5"
    res_dir = ROOT / "results"
    plot_dir = ROOT / "plots"
    ensure_dir(inst_dir)
    ensure_dir(res_dir)
    ensure_dir(plot_dir)

    rows = []
    time_limit = 300.0

    dist_families = ["exponential", "logit", "lognormal", "normal", "uniform"]
    rhos = [-0.5, 0.0, 0.5]
    heteros = ["none", "partial", "full"]
    costs = ["zero", "hvhm", "hvlm"]

    seed0 = 20260306
    setup_idx = 0
    for dist in dist_families:
        for rho in rhos:
            for hetero in heteros:
                for cost in costs:
                    generate_batch(
                        out_dir=str(inst_dir),
                        n_products=5,
                        k_samples=50,
                        dist_family=dist,
                        rho=rho,
                        heterogeneity=hetero,
                        cost_scenario=cost,
                        n_instances=5,
                        seed=seed0 + setup_idx * 1000,
                    )
                    setup_idx += 1

    for mp in sorted(inst_dir.glob("*.msgpack")):
        setup = read_setup(mp)
        instance_id = mp.stem
        v_kn, c_n = load_instance_from_msgpack(mp)
        v_out = sample_out_of_sample_valuations(setup)

        specs = [
            {
                "method": "CPBSD-MILP",
                "result_path": res_dir / f"{instance_id}__cpbsd_milp.json",
                "solver": lambda: solve_milp(v_kn=v_kn, c_n=c_n, mip_gap=1e-2, time_limit=time_limit, output_flag=0),
                "extract": extract_milp_solution,
                "evaluate_out": lambda payload: evaluate_cpbsd_policy(v_out, c_n, payload[0], payload[1]),
            },
            {
                "method": "CPBSD-A",
                "result_path": res_dir / f"{instance_id}__cpbsd_a.json",
                "solver": lambda: solve_cpbsd_a(v_kn=v_kn, c_n=c_n, mip_gap=1e-2, time_limit=time_limit, output_flag=0),
                "extract": extract_cpbsd_a_solution,
                "evaluate_out": lambda payload: evaluate_cpbsd_policy(v_out, c_n, payload[0], payload[1]),
            },
            {
                "method": "BSP",
                "result_path": res_dir / f"{instance_id}__bsp.json",
                "solver": lambda: solve_bsp(v_kn, c_n, time_limit=time_limit, mip_gap=1e-2, output_flag=0),
                "extract": lambda res: (res.get("size_prices") or {}, None, res.get("objective")),
                "evaluate_out": lambda payload: eval_bsp_policy(v_out, c_n, payload[0]),
            },
            {
                "method": "MB",
                "result_path": res_dir / f"{instance_id}__mb.json",
                "solver": lambda: solve_mb(v_kn, c_n, time_limit=time_limit, mip_gap=1e-2, output_flag=0),
                "extract": extract_mb_solution,
                "evaluate_out": lambda payload: eval_mb_policy(v_out, c_n, payload[0], payload[1]),
            },
        ]

        for spec in specs:
            used_cache = False
            result_path = spec["result_path"]
            res = load_cached_result(result_path)
            if spec["method"] == "MB" and res is not None and (
                not (res.get("bundle_prices_full") or {}) or res.get("mb_formulation_version") != MB_FORMULATION_VERSION
            ):
                res = None
            if res is None:
                try:
                    res = spec["solver"]()
                    write_json(result_path, res)
                except Exception as exc:
                    res = {"error": str(exc)}
                    write_json(result_path, res)
            else:
                used_cache = True

            if res.get("error"):
                append_row(
                    rows,
                    setup=setup,
                    method=spec["method"],
                    instance_id=instance_id,
                    n=5,
                    k=50,
                    time_limit=time_limit,
                    solver_runtime=None,
                    wall_time=None,
                    nodes=None,
                    status_code=-1,
                    mip_gap=None,
                    best_bound=None,
                    sol_count=None,
                    big_m=None,
                    objective_raw=None,
                    revenue_in_sample=None,
                    revenue_out_sample=None,
                    policy_scope="missing",
                    bundle_price_count_full=None,
                    bundle_price_count_selected=None,
                    result_path=result_path,
                    used_cache=used_cache,
                    error_message=res["error"],
                )
                continue

            if spec["method"] == "CPBSD-MILP":
                p_vec, d_vec, objective_raw = spec["extract"](res)
                valid = len(p_vec) == c_n.shape[0] and len(d_vec) == c_n.shape[0] + 1
                revenue_in = evaluate_cpbsd_policy(v_kn, c_n, p_vec, d_vec) if valid else None
                revenue_out = spec["evaluate_out"]((p_vec, d_vec)) if valid else None
                append_row(
                    rows,
                    setup=setup,
                    method=spec["method"],
                    instance_id=instance_id,
                    n=5,
                    k=50,
                    time_limit=time_limit,
                    solver_runtime=res.get("runtime"),
                    wall_time=res.get("wall_time"),
                    nodes=res.get("node_count"),
                    status_code=int(res.get("solver_status", -99)),
                    mip_gap=res.get("mip_gap"),
                    best_bound=res.get("best_bound"),
                    sol_count=res.get("sol_count"),
                    big_m=(res.get("meta", {}) or {}).get("big_M"),
                    objective_raw=objective_raw,
                    revenue_in_sample=revenue_in,
                    revenue_out_sample=revenue_out,
                    policy_scope=None,
                    bundle_price_count_full=None,
                    bundle_price_count_selected=None,
                    result_path=result_path,
                    used_cache=used_cache,
                    error_message=None if valid else "Cached or solved MILP result missing valid prices.",
                )
                continue

            if spec["method"] == "CPBSD-A":
                p_vec, d_vec, objective_raw = spec["extract"](res)
                valid = len(p_vec) == c_n.shape[0] and len(d_vec) == c_n.shape[0] + 1
                revenue_in = evaluate_cpbsd_policy(v_kn, c_n, p_vec, d_vec) if valid else None
                revenue_out = spec["evaluate_out"]((p_vec, d_vec)) if valid else None
                append_row(
                    rows,
                    setup=setup,
                    method=spec["method"],
                    instance_id=instance_id,
                    n=5,
                    k=50,
                    time_limit=time_limit,
                    solver_runtime=res.get("runtime"),
                    wall_time=res.get("wall_time"),
                    nodes=res.get("node_count"),
                    status_code=int(res.get("solver_status", -99)),
                    mip_gap=res.get("mip_gap"),
                    best_bound=res.get("best_bound"),
                    sol_count=res.get("sol_count"),
                    big_m=res.get("big_M"),
                    objective_raw=objective_raw,
                    revenue_in_sample=revenue_in,
                    revenue_out_sample=revenue_out,
                    policy_scope=None,
                    bundle_price_count_full=None,
                    bundle_price_count_selected=None,
                    result_path=result_path,
                    used_cache=used_cache,
                    error_message=None if valid else "Cached or solved CPBSD-A result missing valid prices.",
                )
                continue

            if spec["method"] == "BSP":
                size_prices, _, objective_raw = spec["extract"](res)
                valid = bool(size_prices) and bool(res.get("feasible"))
                revenue_in = eval_bsp_policy(v_kn, c_n, size_prices) if valid else None
                revenue_out = spec["evaluate_out"]((size_prices, None)) if valid else None
                append_row(
                    rows,
                    setup=setup,
                    method=spec["method"],
                    instance_id=instance_id,
                    n=5,
                    k=50,
                    time_limit=time_limit,
                    solver_runtime=res.get("runtime"),
                    wall_time=res.get("wall_time"),
                    nodes=None,
                    status_code=int(res.get("solver_status", -99)),
                    mip_gap=res.get("mip_gap"),
                    best_bound=None,
                    sol_count=1 if valid else 0,
                    big_m=None,
                    objective_raw=objective_raw,
                    revenue_in_sample=revenue_in,
                    revenue_out_sample=revenue_out,
                    policy_scope=None,
                    bundle_price_count_full=None,
                    bundle_price_count_selected=None,
                    result_path=result_path,
                    used_cache=used_cache,
                    error_message=None if valid else "Cached or solved BSP result missing valid size prices.",
                )
                continue

            bundle_prices, assortments, objective_raw, mb_info = spec["extract"](res)
            valid = bool(bundle_prices) and assortments is not None and bool(res.get("feasible")) and mb_info["policy_scope"] == "full_bundle_prices"
            revenue_in = eval_mb_policy(v_kn, c_n, bundle_prices, assortments) if valid else None
            revenue_out = spec["evaluate_out"]((bundle_prices, assortments)) if valid else None
            append_row(
                rows,
                setup=setup,
                method=spec["method"],
                instance_id=instance_id,
                n=5,
                k=50,
                time_limit=time_limit,
                solver_runtime=res.get("runtime"),
                wall_time=res.get("wall_time"),
                nodes=None,
                status_code=int(res.get("solver_status", -99)),
                mip_gap=res.get("mip_gap"),
                best_bound=None,
                sol_count=1 if valid else 0,
                big_m=None,
                objective_raw=objective_raw,
                revenue_in_sample=revenue_in,
                revenue_out_sample=revenue_out,
                policy_scope=mb_info["policy_scope"],
                bundle_price_count_full=mb_info["bundle_price_count_full"],
                bundle_price_count_selected=mb_info["bundle_price_count_selected"],
                result_path=result_path,
                used_cache=used_cache,
                error_message=None if valid else "Cached or solved MB result missing a full bundle price table.",
            )

    by_instance = {}
    for row in rows:
        by_instance.setdefault(row["instance_id"], {})[row["method"]] = row

    for methods in by_instance.values():
        bsp_rev = methods.get("BSP", {}).get("revenue_in_sample")
        cpbsd_rev = methods.get("CPBSD-MILP", {}).get("revenue_in_sample")
        for row in methods.values():
            if isinstance(bsp_rev, (int, float)) and bsp_rev != 0 and isinstance(row.get("revenue_in_sample"), (int, float)):
                row["ratio_to_bsp"] = row["revenue_in_sample"] / bsp_rev
            if isinstance(cpbsd_rev, (int, float)) and cpbsd_rev != 0 and isinstance(row.get("revenue_in_sample"), (int, float)):
                row["ratio_to_cpbsd"] = row["revenue_in_sample"] / cpbsd_rev

    json_path = ROOT / "unified_log.json"
    csv_path = ROOT / "unified_log.csv"
    write_json(json_path, rows)

    fieldnames = [
        "instance_id",
        "seed",
        "n",
        "k",
        "method",
        "experiment_scope",
        "dist_family",
        "rho",
        "heterogeneity",
        "cost_scenario",
        "time_limit",
        "solver_runtime",
        "wall_time",
        "nodes",
        "status_code",
        "status_text",
        "mip_gap",
        "best_bound",
        "sol_count",
        "big_m",
        "objective_raw",
        "revenue_in_sample",
        "revenue_out_sample",
        "ratio_to_bsp",
        "ratio_to_cpbsd",
        "baseline_method",
        "policy_scope",
        "bundle_price_count_full",
        "bundle_price_count_selected",
        "result_path",
        "used_cache",
        "error_message",
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    plot_paths = []
    bsp_plot = plot_ratio_boxplot(
        rows,
        out_dir=plot_dir,
        n=5,
        ref_method="BSP",
        title="Main Grid Revenue Ratio vs BSP (N=5)",
    )
    if bsp_plot is not None:
        plot_paths.append(bsp_plot)
    cpbsd_plot = plot_ratio_boxplot(
        rows,
        out_dir=plot_dir,
        n=5,
        ref_method="CPBSD-MILP",
        title="Main Grid Revenue Ratio vs CPBSD-MILP (N=5)",
    )
    if cpbsd_plot is not None:
        plot_paths.append(cpbsd_plot)

    print(f"written: {json_path}")
    print(f"written: {csv_path}")
    for plot_path in plot_paths:
        print(f"written: {plot_path}")


if __name__ == "__main__":
    main()
