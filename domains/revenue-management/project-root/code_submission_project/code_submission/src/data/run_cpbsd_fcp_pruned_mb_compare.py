from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

import msgpack
import msgpack_numpy as mnp
import numpy as np
import torch
from torch_geometric.data import Data

from Training_multi_layer_cpbsd_mb_x import EdgeScoringGCN
from generate_data_CPBSD import generate_batch, sample_valuations, valuation_means
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


def load_instance(path: Path) -> Tuple[dict, np.ndarray, np.ndarray]:
    with open(path, "rb") as f:
        obj = msgpack.load(f, object_hook=mnp.decode, strict_map_key=False)
    return obj, np.asarray(obj["valuation_samples_V"], dtype=float), np.asarray(obj["production_cost_c"], dtype=float)


def build_graph(v_kn: np.ndarray, c_n: np.ndarray) -> Data:
    k_count, n_products = v_kn.shape

    feature_mat = np.zeros((n_products + k_count, 4), dtype=float)
    feature_mat[:n_products, 0] = c_n
    feature_mat[:n_products, 1] = np.mean(v_kn, axis=0)

    rho_k = np.mean((v_kn - c_n[None, :]) > 0, axis=1)
    feature_mat[n_products:, 2] = float(k_count)
    feature_mat[n_products:, 3] = rho_k

    x = torch.tensor(feature_mat, dtype=torch.float)

    left_nodes = []
    right_nodes = []
    edge_attr = []
    for product_idx in range(n_products):
        for customer_idx in range(k_count):
            left_nodes.append(product_idx)
            right_nodes.append(customer_idx + n_products)
            edge_attr.append([v_kn[customer_idx, product_idx]])

    data = Data(
        x=x,
        edge_index=torch.tensor([left_nodes, right_nodes], dtype=torch.long),
        edge_attr=torch.tensor(edge_attr, dtype=torch.float),
        y=torch.empty(0, dtype=torch.long),
    )
    data.product_num = n_products
    data.segment_num = k_count
    return data


def resolve_torch_device(device_name: str) -> torch.device:
    requested = device_name.lower()
    if requested == "auto":
        if torch.cuda.is_available():
            return torch.device("cuda")
        mps_backend = getattr(torch.backends, "mps", None)
        if mps_backend is not None and mps_backend.is_available():
            return torch.device("mps")
        return torch.device("cpu")
    return torch.device(requested)


def load_model(model_path: Path, device: torch.device):
    setattr(sys.modules["__main__"], "EdgeScoringGCN", EdgeScoringGCN)
    loaded = torch.load(model_path, map_location=device, weights_only=False)
    if isinstance(loaded, torch.nn.Module):
        model = loaded
    elif isinstance(loaded, dict):
        model = EdgeScoringGCN()
        model.load_state_dict(loaded, strict=True)
    else:
        raise TypeError(f"Unsupported checkpoint type: {type(loaded)}")
    model.to(device)
    model.eval()
    return model


def infer_probabilities(model, graph_data: Data, device: torch.device) -> np.ndarray:
    graph_data = graph_data.to(device)
    with torch.no_grad():
        raw_out = model(graph_data)
    if isinstance(raw_out, dict):
        if "logit_matrix" in raw_out:
            logits_nm = raw_out["logit_matrix"].detach().cpu().numpy()
        elif "edge_logits" in raw_out:
            n = int(graph_data.product_num)
            m = int(graph_data.segment_num)
            logits_nm = raw_out["edge_logits"].detach().cpu().numpy().reshape(n, m)
        else:
            raise ValueError(f"Unexpected output keys: {list(raw_out.keys())}")
    else:
        raise TypeError(f"Unexpected model output type: {type(raw_out)}")
    return torch.sigmoid(torch.tensor(logits_nm)).numpy().T


def build_fcp_candidate_bundles(prob: np.ndarray, threshold: float = 0.5) -> Tuple[np.ndarray, int]:
    customer_bundles = []
    for k in range(prob.shape[0]):
        bundle = (prob[k] >= threshold).astype(int)
        customer_bundles.append(bundle.tolist())

    unique_candidates = np.array(sorted({tuple(bundle) for bundle in customer_bundles}), dtype=int)
    if unique_candidates.size == 0:
        unique_candidates = np.zeros((0, prob.shape[1]), dtype=int)
    return unique_candidates, len(customer_bundles)


def evaluate_revenue(v_kn: np.ndarray, c_n: np.ndarray, p: np.ndarray, d: np.ndarray) -> float:
    k_count, n_products = v_kn.shape
    total = 0.0
    for k in range(k_count):
        best_surplus = 0.0
        best_idx = None
        best_s = 0
        for s in range(1, n_products + 1):
            util = v_kn[k] - p + d[s]
            idx = np.argpartition(util, -s)[-s:]
            surplus = float(util[idx].sum())
            if surplus > best_surplus:
                best_surplus = surplus
                best_idx = idx
                best_s = s
        if best_surplus <= 0 or best_idx is None:
            continue
        profit = float((p[best_idx] - c_n[best_idx]).sum() - best_s * d[best_s])
        total += profit
    return total / k_count


def out_of_sample_revenue(setup: dict, c_n: np.ndarray, p: np.ndarray, d: np.ndarray, out_k: int = 5000) -> float:
    rng = np.random.default_rng(int(setup["seed"]) + 99991)
    means = valuation_means(int(setup["n_products"]), setup["heterogeneity"])
    v_out = sample_valuations(
        k=out_k,
        means=means,
        family=setup["dist_family"],
        rho=float(setup["rho"]),
        rng=rng,
    )
    return evaluate_revenue(v_out, c_n, p, d)


def result_to_row(
    *,
    instance_id: str,
    seed: int,
    n_products: int,
    k_samples: int,
    method: str,
    result_path: Path,
    in_sample_revenue: float | None,
    out_sample_revenue: float | None,
    runtime: float | None,
    status_code: int,
    extra: Dict[str, object],
) -> Dict[str, object]:
    row = {
        "instance_id": instance_id,
        "seed": seed,
        "n": n_products,
        "k": k_samples,
        "method": method,
        "revenue_in_sample": in_sample_revenue,
        "revenue_out_sample": out_sample_revenue,
        "solver_runtime": runtime,
        "status_code": status_code,
        "result_path": str(result_path),
    }
    row.update(extra)
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare FCP-pruned MB vs BSP vs CPBSD-A on CPBSD N=10, K=50 instances.")
    parser.add_argument(
        "--model-path",
        type=str,
        default="/Users/sensen/.openclaw/workspace/domains/revenue-management/project-root/code_submission_project/code_submission/models_cpbsd_mb_x/best_model_edge_cpbsd_mb_x_2layer_seed42.pt",
    )
    parser.add_argument(
        "--root",
        type=str,
        default="/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/cpbsd_fcp_pruned_mb_compare_n10k50",
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
    parser.add_argument("--time-limit-fcp-mb", type=float, default=600.0)
    parser.add_argument("--time-limit-bsp", type=float, default=600.0)
    parser.add_argument("--time-limit-cpbsd-a", type=float, default=600.0)
    parser.add_argument("--mip-gap", type=float, default=1e-2)
    parser.add_argument("--output-flag", type=int, default=0)
    args = parser.parse_args()

    root = Path(args.root)
    inst_dir = root / "instances"
    result_dir = root / "results"
    ensure_dir(inst_dir)
    ensure_dir(result_dir)

    if not any(inst_dir.glob("*.msgpack")):
        generate_batch(
            out_dir=str(inst_dir),
            n_products=args.N,
            k_samples=args.K,
            dist_family=args.dist,
            rho=args.rho,
            heterogeneity=args.hetero,
            cost_scenario=args.cost,
            n_instances=args.instances,
            seed=args.seed,
        )

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

        cand_t0 = time.time()
        candidate_assortments, raw_customer_bundle_count = build_fcp_candidate_bundles(prob, threshold=args.threshold)
        cand_t1 = time.time()

        fcp_t0 = time.time()
        fcp_res = solve_mb_restricted(
            v_kn=v_kn,
            c_n=c_n,
            assortments=candidate_assortments,
            time_limit=args.time_limit_fcp_mb,
            mip_gap=args.mip_gap,
            output_flag=args.output_flag,
            subadditivity_mode="predicted_cover_pairwise",
        )
        fcp_t1 = time.time()
        fcp_info = normalize_numeric_keys(fcp_res)
        fcp_json = result_dir / f"{instance_id}__fcp_pruned_mb.json"
        fcp_json.write_text(json.dumps(fcp_info, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")

        fcp_policy = fcp_info.get("bundle_prices_full") or fcp_info.get("bundle_prices") or {}
        fcp_out = None
        if fcp_info.get("feasible") and fcp_policy:
            rng = np.random.default_rng(int(setup["seed"]) + 99991)
            means = valuation_means(int(setup["n_products"]), setup["heterogeneity"])
            v_out = sample_valuations(
                k=5000,
                means=means,
                family=setup["dist_family"],
                rho=float(setup["rho"]),
                rng=rng,
            )
            fcp_out = eval_mb_policy(v_out, c_n, fcp_policy, np.asarray(fcp_info["assortments"], dtype=int))

        rows.append(
            result_to_row(
                instance_id=instance_id,
                seed=int(setup["seed"]),
                n_products=int(setup["n_products"]),
                k_samples=int(setup["k_samples"]),
                method="FCP-pruned-MB",
                result_path=fcp_json,
                in_sample_revenue=fcp_info.get("objective"),
                out_sample_revenue=fcp_out,
                runtime=fcp_t1 - fcp_t0,
                status_code=int(fcp_info.get("solver_status", -1)),
                extra={
                    "gcn_inference_time": infer_t1 - infer_t0,
                    "candidate_generation_time": cand_t1 - cand_t0,
                    "bundle_space_size": int(fcp_info.get("bundle_space_size", len(candidate_assortments))),
                    "bundle_space_fraction": float(fcp_info.get("bundle_space_size", len(candidate_assortments))) / float(2 ** args.N),
                    "full_bundle_space_size": int(2 ** args.N),
                    "raw_customer_bundle_count": raw_customer_bundle_count,
                    "unique_threshold_bundle_count": int(candidate_assortments.shape[0]),
                    "threshold": args.threshold,
                },
            )
        )

        bsp_t0 = time.time()
        bsp_res = solve_bsp(v_kn, c_n, time_limit=args.time_limit_bsp, mip_gap=args.mip_gap, output_flag=args.output_flag)
        bsp_t1 = time.time()
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
        rows.append(
            result_to_row(
                instance_id=instance_id,
                seed=int(setup["seed"]),
                n_products=int(setup["n_products"]),
                k_samples=int(setup["k_samples"]),
                method="BSP",
                result_path=bsp_json,
                in_sample_revenue=bsp_res.get("objective"),
                out_sample_revenue=bsp_out,
                runtime=bsp_t1 - bsp_t0,
                status_code=2 if bsp_res.get("feasible") else 3,
                extra={"bundle_space_size": None, "bundle_space_fraction": None, "full_bundle_space_size": int(2 ** args.N)},
            )
        )

        cpbsd_t0 = time.time()
        cpbsd_a_res = solve_cpbsd_a(
            v_kn=v_kn,
            c_n=c_n,
            mip_gap=args.mip_gap,
            time_limit=args.time_limit_cpbsd_a,
            output_flag=args.output_flag,
        )
        cpbsd_t1 = time.time()
        cpbsd_json = result_dir / f"{instance_id}__cpbsd_a.json"
        cpbsd_json.write_text(json.dumps(cpbsd_a_res, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")
        cpbsd_out = None
        if cpbsd_a_res.get("sol_count", 0) > 0:
            p_vec = np.array(cpbsd_a_res.get("p", []), dtype=float)
            d_vec = np.array(cpbsd_a_res.get("d", []), dtype=float)
            cpbsd_out = out_of_sample_revenue(setup, c_n, p_vec, d_vec) if len(p_vec) else None
        rows.append(
            result_to_row(
                instance_id=instance_id,
                seed=int(setup["seed"]),
                n_products=int(setup["n_products"]),
                k_samples=int(setup["k_samples"]),
                method="CPBSD-A",
                result_path=cpbsd_json,
                in_sample_revenue=cpbsd_a_res.get("objective"),
                out_sample_revenue=cpbsd_out,
                runtime=cpbsd_t1 - cpbsd_t0,
                status_code=int(cpbsd_a_res.get("solver_status", -1)),
                extra={"bundle_space_size": None, "bundle_space_fraction": None, "full_bundle_space_size": int(2 ** args.N)},
            )
        )

    by_instance: Dict[str, Dict[str, Dict[str, object]]] = {}
    for row in rows:
        by_instance.setdefault(str(row["instance_id"]), {})[str(row["method"])] = row

    summary_rows = []
    for instance_id, methods in by_instance.items():
        bsp_rev = methods.get("BSP", {}).get("revenue_in_sample")
        cpbsd_rev = methods.get("CPBSD-A", {}).get("revenue_in_sample")
        for method_name, row in methods.items():
            row["ratio_to_bsp"] = (row["revenue_in_sample"] / bsp_rev) if bsp_rev not in (None, 0) and row["revenue_in_sample"] is not None else None
            row["ratio_to_cpbsd_a"] = (row["revenue_in_sample"] / cpbsd_rev) if cpbsd_rev not in (None, 0) and row["revenue_in_sample"] is not None else None
            summary_rows.append(row)

    summary_path = root / "comparison_summary.json"
    summary_path.write_text(json.dumps(summary_rows, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")

    csv_path = root / "comparison_summary.csv"
    fieldnames = list(summary_rows[0].keys()) if summary_rows else []
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
