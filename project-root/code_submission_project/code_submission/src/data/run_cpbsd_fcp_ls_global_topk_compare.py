from __future__ import annotations

import argparse
import csv
import json
import time
from math import ceil, sqrt
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

from run_cpbsd_fcp_pruned_mb_compare import (
    build_fcp_candidate_bundles,
    build_graph,
    infer_probabilities,
    load_instance,
    load_model,
    out_of_sample_revenue,
    resolve_torch_device,
    result_to_row,
)
from generate_data_CPBSD import sample_valuations, valuation_means
from solve_cpbsd_a import solve_cpbsd_a
from solve_mb_bsp_on_cpbsd_v2 import (
    eval_bsp_policy,
    eval_mb_policy,
    json_default,
    normalize_numeric_keys,
    solve_bsp,
    solve_mb_restricted,
)


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def pred_assort_to_assignment(pred_assort: np.ndarray) -> Dict[int, int]:
    assignment: Dict[int, int] = {}
    for customer_idx in range(pred_assort.shape[0]):
        bits = "".join(map(str, pred_assort[customer_idx].astype(int).tolist()))
        assignment[customer_idx] = int(bits, 2)
    return assignment


def assignment_to_pred_assort(assignment: Dict[int, int], n_products: int, n_customers: int) -> np.ndarray:
    pred_assort = np.zeros((n_customers, n_products), dtype=int)
    for customer_idx in range(n_customers):
        bundle_bits = format(int(assignment[customer_idx]), f"0{n_products}b")
        pred_assort[customer_idx, :] = [int(bit) for bit in bundle_bits]
    return pred_assort


def generate_neighbor_assignments_global_topk(
    current_assignment: Dict[int, int],
    prob: np.ndarray,
    n_products: int,
    n_customers: int,
) -> Tuple[List[Dict[int, int]], Dict[str, float]]:
    convert_start = time.time()
    current_pred_assort = assignment_to_pred_assort(current_assignment, n_products, n_customers)
    convert_time = time.time() - convert_start

    k_top = int(ceil(sqrt(n_customers)))
    neighbors: List[Dict[int, int]] = []
    timing_info = {
        "add_candidate_time": 0.0,
        "drop_candidate_time": 0.0,
        "neighbor_generation_time": 0.0,
        "convert_time": convert_time,
    }

    add_start = time.time()
    add_candidates = []
    for customer_idx in range(n_customers):
        for product_idx in range(n_products):
            if current_pred_assort[customer_idx, product_idx] == 0:
                add_candidates.append((customer_idx, product_idx, float(prob[customer_idx, product_idx])))
    add_candidates.sort(key=lambda x: x[2], reverse=True)
    add_list = add_candidates[:k_top]
    timing_info["add_candidate_time"] = time.time() - add_start

    drop_start = time.time()
    drop_candidates = []
    for customer_idx in range(n_customers):
        for product_idx in range(n_products):
            if current_pred_assort[customer_idx, product_idx] == 1 and prob[customer_idx, product_idx] >= 0.5:
                drop_candidates.append((customer_idx, product_idx, float(prob[customer_idx, product_idx])))
    drop_candidates.sort(key=lambda x: x[2])
    drop_list = drop_candidates[:k_top]
    timing_info["drop_candidate_time"] = time.time() - drop_start

    neighbor_gen_start = time.time()
    for customer_idx, product_idx, _ in add_list:
        neighbor_pred = current_pred_assort.copy()
        neighbor_pred[customer_idx, product_idx] = 1
        neighbors.append(pred_assort_to_assignment(neighbor_pred))
    for customer_idx, product_idx, _ in drop_list:
        neighbor_pred = current_pred_assort.copy()
        neighbor_pred[customer_idx, product_idx] = 0
        neighbors.append(pred_assort_to_assignment(neighbor_pred))
    timing_info["neighbor_generation_time"] = time.time() - neighbor_gen_start
    return neighbors, timing_info


def assignment_to_candidate_assortments(assignment: Dict[int, int], n_products: int) -> np.ndarray:
    rows = []
    for bundle_id in assignment.values():
        rows.append(list(map(int, format(int(bundle_id), f"0{n_products}b"))))
    if not rows:
        return np.zeros((0, n_products), dtype=int)
    return np.unique(np.asarray(rows, dtype=int), axis=0)


def assortments_key(assortments: np.ndarray) -> Tuple[Tuple[int, ...], ...]:
    if assortments.size == 0:
        return tuple()
    return tuple(tuple(int(v) for v in row.tolist()) for row in np.asarray(assortments, dtype=int))


def load_baseline_summary(summary_path: Path) -> Dict[str, Dict[str, object]]:
    rows = json.loads(summary_path.read_text(encoding="utf-8"))
    by_method: Dict[str, Dict[str, object]] = {}
    for row in rows:
        by_method[str(row["method"])] = row
    return by_method


def evaluate_assignment_bundle_space(
    *,
    assignment: Dict[int, int],
    n_products: int,
    v_kn: np.ndarray,
    c_n: np.ndarray,
    time_limit: float,
    mip_gap: float,
    output_flag: int,
    cache: Dict[Tuple[Tuple[int, ...], ...], Dict[str, object]],
) -> Dict[str, object]:
    assortments = assignment_to_candidate_assortments(assignment, n_products)
    key = assortments_key(assortments)
    cached = cache.get(key)
    if cached is not None:
        out = dict(cached)
        out["from_cache"] = True
        return out

    solve_t0 = time.time()
    res = solve_mb_restricted(
        v_kn=v_kn,
        c_n=c_n,
        assortments=assortments,
        time_limit=time_limit,
        mip_gap=mip_gap,
        output_flag=output_flag,
    )
    solve_t1 = time.time()
    info = normalize_numeric_keys(res)
    info["assortments"] = np.asarray(info.get("assortments", assortments), dtype=int)
    info["bundle_space_size"] = int(info.get("bundle_space_size", info["assortments"].shape[0]))
    info["wall_time_search_eval"] = solve_t1 - solve_t0
    info["from_cache"] = False
    cache[key] = info
    return dict(info)


def local_search_bundle_space_global_topk(
    *,
    initial_pred_assort: np.ndarray,
    prob: np.ndarray,
    v_kn: np.ndarray,
    c_n: np.ndarray,
    search_time_limit: float,
    search_mip_gap: float,
    output_flag: int,
    max_iterations: int,
    tolerance: float,
) -> Tuple[Dict[int, int], Dict[str, object], Dict[str, object]]:
    n_products = int(initial_pred_assort.shape[1])
    n_customers = int(initial_pred_assort.shape[0])
    current_assignment = pred_assort_to_assignment(initial_pred_assort)

    cache: Dict[Tuple[Tuple[int, ...], ...], Dict[str, object]] = {}
    current_eval = evaluate_assignment_bundle_space(
        assignment=current_assignment,
        n_products=n_products,
        v_kn=v_kn,
        c_n=c_n,
        time_limit=search_time_limit,
        mip_gap=search_mip_gap,
        output_flag=output_flag,
        cache=cache,
    )
    current_objective = current_eval.get("objective")
    if current_objective is None:
        raise RuntimeError("Initial FCP candidate space did not produce a feasible restricted MB solution.")

    k_top = int(np.ceil(np.sqrt(n_customers)))
    search_t0 = time.time()
    trace = {
        "search_strategy": "global_topk",
        "topk_k": k_top,
        "max_neighbors_per_iteration": 2 * k_top,
        "search_time_limit_per_eval": search_time_limit,
        "search_mip_gap": search_mip_gap,
        "max_iterations": max_iterations,
        "tolerance": tolerance,
        "initial_objective": float(current_objective),
        "initial_bundle_space_size": int(current_eval["bundle_space_size"]),
        "iterations": [],
        "accepted_objective_path": [float(current_objective)],
        "accepted_bundle_space_sizes": [int(current_eval["bundle_space_size"])],
        "accepted_elapsed_time_path": [0.0],
        "neighbor_evaluations": 1,
        "cache_hits": 1 if current_eval.get("from_cache") else 0,
        "unique_space_evaluations": len(cache),
    }

    for iteration in range(1, max_iterations + 1):
        iter_t0 = time.time()
        neighbors, neighbor_timing = generate_neighbor_assignments_global_topk(
            current_assignment,
            prob,
            n_products,
            n_customers,
        )
        accepted = False
        iter_record = {
            "iteration": iteration,
            "neighbor_count": len(neighbors),
            "neighbor_generation_timing": neighbor_timing,
            "evaluations": [],
            "accepted_neighbor_index": None,
            "accepted_objective": None,
            "accepted_bundle_space_size": None,
            "iteration_wall_time": None,
        }

        for neighbor_idx, neighbor_assignment in enumerate(neighbors, start=1):
            neighbor_eval = evaluate_assignment_bundle_space(
                assignment=neighbor_assignment,
                n_products=n_products,
                v_kn=v_kn,
                c_n=c_n,
                time_limit=search_time_limit,
                mip_gap=search_mip_gap,
                output_flag=output_flag,
                cache=cache,
            )
            trace["neighbor_evaluations"] += 1
            if neighbor_eval.get("from_cache"):
                trace["cache_hits"] += 1

            neighbor_obj = neighbor_eval.get("objective")
            eval_record = {
                "neighbor_index": neighbor_idx,
                "objective": neighbor_obj,
                "bundle_space_size": int(neighbor_eval.get("bundle_space_size", 0)),
                "solver_status": int(neighbor_eval.get("solver_status", -1)),
                "runtime": neighbor_eval.get("runtime"),
                "wall_time_search_eval": neighbor_eval.get("wall_time_search_eval"),
                "mip_gap": neighbor_eval.get("mip_gap"),
                "from_cache": bool(neighbor_eval.get("from_cache")),
            }
            iter_record["evaluations"].append(eval_record)

            if neighbor_obj is not None and float(neighbor_obj) > float(current_objective) + tolerance:
                current_assignment = neighbor_assignment
                current_eval = neighbor_eval
                current_objective = float(neighbor_obj)
                accepted = True
                iter_record["accepted_neighbor_index"] = neighbor_idx
                iter_record["accepted_objective"] = current_objective
                iter_record["accepted_bundle_space_size"] = int(neighbor_eval["bundle_space_size"])
                trace["accepted_objective_path"].append(current_objective)
                trace["accepted_bundle_space_sizes"].append(int(neighbor_eval["bundle_space_size"]))
                trace["accepted_elapsed_time_path"].append(time.time() - search_t0)
                break

        iter_record["iteration_wall_time"] = time.time() - iter_t0
        trace["iterations"].append(iter_record)
        trace["unique_space_evaluations"] = len(cache)
        if not accepted:
            break

    trace["search_wall_time"] = time.time() - search_t0
    trace["final_search_objective"] = float(current_objective)
    trace["final_bundle_space_size"] = int(current_eval["bundle_space_size"])
    trace["iteration_count"] = len(trace["iterations"])
    trace["improvement_count"] = max(0, len(trace["accepted_objective_path"]) - 1)
    return current_assignment, current_eval, trace


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare FCP+GlobalTopK-LocalSearch MB against prior CPBSD baselines.")
    parser.add_argument(
        "--model-path",
        type=str,
        default="/Users/sensen/.openclaw/workspace/domains/revenue-management/project-root/code_submission_project/code_submission/models_cpbsd_mb_x/best_model_edge_cpbsd_mb_x_2layer_seed42.pt",
    )
    parser.add_argument(
        "--root",
        type=str,
        default="/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/cpbsd_fcp_ls_global_topk_compare_n10k50_strict300",
    )
    parser.add_argument(
        "--baseline-root",
        type=str,
        default="/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/cpbsd_fcp_pruned_mb_compare_n10k50_strict300",
    )
    parser.add_argument("--instances", type=int, default=1)
    parser.add_argument("--N", type=int, default=10)
    parser.add_argument("--K", type=int, default=50)
    parser.add_argument("--seed", type=int, default=20260321)
    parser.add_argument("--dist", type=str, default="normal")
    parser.add_argument("--rho", type=float, default=0.0)
    parser.add_argument("--hetero", type=str, default="full")
    parser.add_argument("--cost", type=str, default="hvhm")
    parser.add_argument("--device", type=str, default="auto")
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--search-time-limit", type=float, default=2.0)
    parser.add_argument("--search-mip-gap", type=float, default=0.1)
    parser.add_argument("--search-max-iterations", type=int, default=10)
    parser.add_argument("--search-tolerance", type=float, default=1e-4)
    parser.add_argument("--time-limit-final-mb", type=float, default=300.0)
    parser.add_argument("--time-limit-bsp", type=float, default=300.0)
    parser.add_argument("--time-limit-cpbsd-a", type=float, default=300.0)
    parser.add_argument("--mip-gap", type=float, default=1e-2)
    parser.add_argument("--output-flag", type=int, default=0)
    parser.add_argument("--rerun-baselines", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    root = Path(args.root)
    inst_dir = root / "instances"
    result_dir = root / "results"
    ensure_dir(inst_dir)
    ensure_dir(result_dir)

    baseline_root = Path(args.baseline_root)
    baseline_summary_path = baseline_root / "comparison_summary.json"
    baseline_by_method = load_baseline_summary(baseline_summary_path) if baseline_summary_path.exists() else {}

    baseline_inst_dir = baseline_root / "instances"
    if baseline_inst_dir.exists() and any(baseline_inst_dir.glob("*.msgpack")):
        for src in sorted(baseline_inst_dir.glob("*.msgpack"))[: args.instances]:
            dst = inst_dir / src.name
            if not dst.exists():
                dst.write_bytes(src.read_bytes())

    instance_paths = sorted(inst_dir.glob("*.msgpack"))[: args.instances]
    if not instance_paths:
        raise FileNotFoundError(f"No instances found under {inst_dir}")

    device = resolve_torch_device(args.device)
    model = load_model(Path(args.model_path), device)
    rows: List[Dict[str, object]] = []

    for instance_path in instance_paths:
        obj, v_kn, c_n = load_instance(instance_path)
        setup = obj["setup"]
        instance_id = instance_path.stem

        graph_data = build_graph(v_kn, c_n)
        infer_t0 = time.time()
        prob = infer_probabilities(model, graph_data, device)
        infer_t1 = time.time()

        initial_pred_assort = (prob >= args.threshold).astype(int)
        initial_candidate_assortments, raw_customer_bundle_count = build_fcp_candidate_bundles(prob, threshold=args.threshold)

        search_assignment, search_eval, search_trace = local_search_bundle_space_global_topk(
            initial_pred_assort=initial_pred_assort,
            prob=prob,
            v_kn=v_kn,
            c_n=c_n,
            search_time_limit=args.search_time_limit,
            search_mip_gap=args.search_mip_gap,
            output_flag=args.output_flag,
            max_iterations=args.search_max_iterations,
            tolerance=args.search_tolerance,
        )

        final_assortments = assignment_to_candidate_assortments(search_assignment, int(v_kn.shape[1]))
        final_t0 = time.time()
        final_res = solve_mb_restricted(
            v_kn=v_kn,
            c_n=c_n,
            assortments=final_assortments,
            time_limit=args.time_limit_final_mb,
            mip_gap=args.mip_gap,
            output_flag=args.output_flag,
        )
        final_t1 = time.time()
        final_info = normalize_numeric_keys(final_res)

        ls_json = result_dir / f"{instance_id}__fcp_ls_global_topk_mb.json"
        search_json = result_dir / f"{instance_id}__fcp_ls_global_topk_search.json"
        final_payload = {
            "instance_id": instance_id,
            "search_trace_path": str(search_json),
            "search_trace_summary": {
                "initial_objective": search_trace["initial_objective"],
                "final_search_objective": search_trace["final_search_objective"],
                "initial_bundle_space_size": search_trace["initial_bundle_space_size"],
                "final_bundle_space_size": search_trace["final_bundle_space_size"],
                "iteration_count": search_trace["iteration_count"],
                "improvement_count": search_trace["improvement_count"],
                "neighbor_evaluations": search_trace["neighbor_evaluations"],
                "unique_space_evaluations": search_trace["unique_space_evaluations"],
                "cache_hits": search_trace["cache_hits"],
                "search_wall_time": search_trace["search_wall_time"],
            },
            "final_result": final_info,
        }
        search_json.write_text(json.dumps(search_trace, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")
        ls_json.write_text(json.dumps(final_payload, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")

        ls_policy = final_info.get("bundle_prices_full") or final_info.get("bundle_prices") or {}
        ls_out = None
        if final_info.get("feasible") and ls_policy:
            ls_out = eval_mb_policy(
                sample_valuations(
                    k=5000,
                    means=valuation_means(int(setup["n_products"]), setup["heterogeneity"]),
                    family=setup["dist_family"],
                    rho=float(setup["rho"]),
                    rng=np.random.default_rng(int(setup["seed"]) + 99991),
                ),
                c_n,
                ls_policy,
                np.asarray(final_info["assortments"], dtype=int),
            )

        ls_row = result_to_row(
            instance_id=instance_id,
            seed=int(setup["seed"]),
            n_products=int(setup["n_products"]),
            k_samples=int(setup["k_samples"]),
            method="FCP+LS-GlobalTopK-MB",
            result_path=ls_json,
            in_sample_revenue=final_info.get("objective"),
            out_sample_revenue=ls_out,
            runtime=(final_t1 - final_t0) + float(search_trace["search_wall_time"]),
            status_code=int(final_info.get("solver_status", -1)),
            extra={
                "gcn_inference_time": infer_t1 - infer_t0,
                "initial_bundle_space_size": int(initial_candidate_assortments.shape[0]),
                "bundle_space_size": int(final_info.get("bundle_space_size", final_assortments.shape[0])),
                "bundle_space_fraction": float(final_info.get("bundle_space_size", final_assortments.shape[0])) / float(2 ** args.N),
                "full_bundle_space_size": int(2 ** args.N),
                "raw_customer_bundle_count": raw_customer_bundle_count,
                "unique_threshold_bundle_count": int(initial_candidate_assortments.shape[0]),
                "search_final_bundle_space_size": int(search_trace["final_bundle_space_size"]),
                "search_initial_objective": search_trace["initial_objective"],
                "search_final_objective": search_trace["final_search_objective"],
                "search_iterations": int(search_trace["iteration_count"]),
                "search_improvements": int(search_trace["improvement_count"]),
                "search_neighbor_evaluations": int(search_trace["neighbor_evaluations"]),
                "search_unique_space_evaluations": int(search_trace["unique_space_evaluations"]),
                "search_cache_hits": int(search_trace["cache_hits"]),
                "search_wall_time": float(search_trace["search_wall_time"]),
                "search_eval_time_limit": args.search_time_limit,
                "search_eval_mip_gap": args.search_mip_gap,
                "final_solver_runtime": final_info.get("runtime"),
                "final_solver_wall_time": final_t1 - final_t0,
                "final_solver_mip_gap": final_info.get("mip_gap"),
                "threshold": args.threshold,
            },
        )
        rows.append(ls_row)

        if args.rerun_baselines or not baseline_by_method:
            baseline_methods: List[Dict[str, object]] = []

            fcp_res = solve_mb_restricted(
                v_kn=v_kn,
                c_n=c_n,
                assortments=initial_candidate_assortments,
                time_limit=args.time_limit_final_mb,
                mip_gap=args.mip_gap,
                output_flag=args.output_flag,
            )
            fcp_info = normalize_numeric_keys(fcp_res)
            fcp_json = result_dir / f"{instance_id}__fcp_pruned_mb.json"
            fcp_json.write_text(json.dumps(fcp_info, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")
            fcp_policy = fcp_info.get("bundle_prices_full") or fcp_info.get("bundle_prices") or {}
            fcp_out = None
            if fcp_info.get("feasible") and fcp_policy:
                fcp_out = eval_mb_policy(
                    sample_valuations(
                        k=5000,
                        means=valuation_means(int(setup["n_products"]), setup["heterogeneity"]),
                        family=setup["dist_family"],
                        rho=float(setup["rho"]),
                        rng=np.random.default_rng(int(setup["seed"]) + 99991),
                    ),
                    c_n,
                    fcp_policy,
                    np.asarray(fcp_info["assortments"], dtype=int),
                )
            baseline_methods.append(
                result_to_row(
                    instance_id=instance_id,
                    seed=int(setup["seed"]),
                    n_products=int(setup["n_products"]),
                    k_samples=int(setup["k_samples"]),
                    method="FCP-pruned-MB",
                    result_path=fcp_json,
                    in_sample_revenue=fcp_info.get("objective"),
                    out_sample_revenue=fcp_out,
                    runtime=fcp_info.get("wall_time"),
                    status_code=int(fcp_info.get("solver_status", -1)),
                    extra={
                        "bundle_space_size": int(fcp_info.get("bundle_space_size", initial_candidate_assortments.shape[0])),
                        "bundle_space_fraction": float(fcp_info.get("bundle_space_size", initial_candidate_assortments.shape[0])) / float(2 ** args.N),
                        "full_bundle_space_size": int(2 ** args.N),
                        "raw_customer_bundle_count": raw_customer_bundle_count,
                        "unique_threshold_bundle_count": int(initial_candidate_assortments.shape[0]),
                        "threshold": args.threshold,
                    },
                )
            )

            bsp_res = solve_bsp(v_kn, c_n, time_limit=args.time_limit_bsp, mip_gap=args.mip_gap, output_flag=args.output_flag)
            bsp_json = result_dir / f"{instance_id}__bsp.json"
            bsp_json.write_text(json.dumps(bsp_res, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")
            bsp_out = eval_bsp_policy(
                sample_valuations(
                    k=5000,
                    means=valuation_means(int(setup["n_products"]), setup["heterogeneity"]),
                    family=setup["dist_family"],
                    rho=float(setup["rho"]),
                    rng=np.random.default_rng(int(setup["seed"]) + 99991),
                ),
                c_n,
                bsp_res.get("size_prices", {}) or {},
            ) if bsp_res.get("feasible") and bsp_res.get("size_prices") else None
            baseline_methods.append(
                result_to_row(
                    instance_id=instance_id,
                    seed=int(setup["seed"]),
                    n_products=int(setup["n_products"]),
                    k_samples=int(setup["k_samples"]),
                    method="BSP",
                    result_path=bsp_json,
                    in_sample_revenue=bsp_res.get("objective"),
                    out_sample_revenue=bsp_out,
                    runtime=bsp_res.get("wall_time"),
                    status_code=2 if bsp_res.get("feasible") else 3,
                    extra={"bundle_space_size": None, "bundle_space_fraction": None, "full_bundle_space_size": int(2 ** args.N)},
                )
            )

            cpbsd_a_res = solve_cpbsd_a(
                v_kn=v_kn,
                c_n=c_n,
                mip_gap=args.mip_gap,
                time_limit=args.time_limit_cpbsd_a,
                output_flag=args.output_flag,
            )
            cpbsd_json = result_dir / f"{instance_id}__cpbsd_a.json"
            cpbsd_json.write_text(json.dumps(cpbsd_a_res, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")
            cpbsd_out = None
            if cpbsd_a_res.get("sol_count", 0) > 0:
                p_vec = np.array(cpbsd_a_res.get("p", []), dtype=float)
                d_vec = np.array(cpbsd_a_res.get("d", []), dtype=float)
                cpbsd_out = out_of_sample_revenue(setup, c_n, p_vec, d_vec) if len(p_vec) else None
            baseline_methods.append(
                result_to_row(
                    instance_id=instance_id,
                    seed=int(setup["seed"]),
                    n_products=int(setup["n_products"]),
                    k_samples=int(setup["k_samples"]),
                    method="CPBSD-A",
                    result_path=cpbsd_json,
                    in_sample_revenue=cpbsd_a_res.get("objective"),
                    out_sample_revenue=cpbsd_out,
                    runtime=cpbsd_a_res.get("wall_time"),
                    status_code=int(cpbsd_a_res.get("solver_status", -1)),
                    extra={"bundle_space_size": None, "bundle_space_fraction": None, "full_bundle_space_size": int(2 ** args.N)},
                )
            )
            rows.extend(baseline_methods)
        else:
            for method_name in ["FCP-pruned-MB", "BSP", "CPBSD-A"]:
                if method_name in baseline_by_method:
                    rows.append(dict(baseline_by_method[method_name]))

    by_instance: Dict[str, Dict[str, Dict[str, object]]] = {}
    for row in rows:
        by_instance.setdefault(str(row["instance_id"]), {})[str(row["method"])] = row

    summary_rows: List[Dict[str, object]] = []
    for _, methods in by_instance.items():
        bsp_rev = methods.get("BSP", {}).get("revenue_in_sample")
        cpbsd_rev = methods.get("CPBSD-A", {}).get("revenue_in_sample")
        for _, row in methods.items():
            row["ratio_to_bsp"] = (row["revenue_in_sample"] / bsp_rev) if bsp_rev not in (None, 0) and row["revenue_in_sample"] is not None else None
            row["ratio_to_cpbsd_a"] = (row["revenue_in_sample"] / cpbsd_rev) if cpbsd_rev not in (None, 0) and row["revenue_in_sample"] is not None else None
            summary_rows.append(row)

    summary_path = root / "comparison_summary.json"
    summary_path.write_text(json.dumps(summary_rows, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")

    csv_path = root / "comparison_summary.csv"
    fieldnames: List[str] = []
    for row in summary_rows:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(key)
    if fieldnames:
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(summary_rows)

    aggregate = {}
    for method in sorted({row["method"] for row in summary_rows}):
        method_rows = [row for row in summary_rows if row["method"] == method]
        aggregate[method] = {
            "count": len(method_rows),
            "avg_revenue_in_sample": float(np.mean([row["revenue_in_sample"] for row in method_rows if row["revenue_in_sample"] is not None])),
            "avg_revenue_out_sample": float(np.mean([row["revenue_out_sample"] for row in method_rows if row["revenue_out_sample"] is not None])),
            "avg_runtime": float(np.mean([row["solver_runtime"] for row in method_rows if row["solver_runtime"] is not None])),
        }

    print(
        json.dumps(
            {
                "root": str(root),
                "summary_path": str(summary_path),
                "csv_path": str(csv_path),
                "aggregate": aggregate,
                "rows": summary_rows,
            },
            ensure_ascii=False,
            indent=2,
            default=json_default,
        )
    )


if __name__ == "__main__":
    main()
