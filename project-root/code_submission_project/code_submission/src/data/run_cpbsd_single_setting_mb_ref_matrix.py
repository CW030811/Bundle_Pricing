from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List

import matplotlib
import msgpack
import msgpack_numpy as mnp
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.append(str(SCRIPT_DIR))

from generate_data_CPBSD import generate_batch, sample_valuations, valuation_means
from plot_cpbsd_results_v2 import plot_ratio_boxplot
from run_cpbsd_fcp_pruned_mb_compare import (
    build_fcp_candidate_bundles,
    build_graph,
    infer_probabilities,
    load_model,
    resolve_torch_device,
)
from solve_cpbsd_a import solve_cpbsd_a
from solve_cpbsd_milp import load_instance_from_msgpack, solve as solve_milp
from solve_mb_bsp_on_cpbsd_v2 import (
    MB_FORMULATION_VERSION,
    eval_bsp_policy,
    eval_mb_policy,
    extract_mb_policy_info,
    json_default,
    normalize_numeric_keys,
    solve_bsp,
    solve_mb,
    solve_mb_restricted,
)


EXPERIMENT_SCOPE = "single_setting_mb_ref_matrix_v1"
DEFAULT_ROOT = Path(
    os.environ.get(
        "CPBSD_SINGLE_SETTING_MB_REF_ROOT",
        "/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/cpbsd_single_setting_mb_ref_normal_rho0.0_full_zero",
    )
)
DEFAULT_MODEL_PATH = Path(
    "/Users/sensen/.openclaw/workspace/domains/revenue-management/project-root/code_submission_project/code_submission/models_cpbsd_mb_x/best_model_edge_cpbsd_mb_x_2layer_seed42.pt"
)
METHODS = ("CPBSD-MILP", "CPBSD-A", "MB", "BSP", "FCP-pruned-MB")
METHOD_LABELS = {
    "CPBSD-MILP": "CPBSD",
    "CPBSD-A": "CPBSD-A",
    "MB": "MB",
    "BSP": "BSP",
    "FCP-pruned-MB": "FCP-MB",
}
METHOD_ORDER = ["CPBSD-MILP", "CPBSD-A", "MB", "FCP-pruned-MB"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a zero-cost single-setting CPBSD / CPBSD-A / MB / FCP-pruned-MB comparison across multiple N values."
    )
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--model-path", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--dist", type=str, default="normal")
    parser.add_argument("--rho", type=float, default=0.0)
    parser.add_argument("--hetero", type=str, default="full")
    parser.add_argument("--cost", type=str, default="zero")
    parser.add_argument("--n-values", type=str, default="5,10,20,30")
    parser.add_argument("--k-in", type=int, default=50)
    parser.add_argument("--k-out", type=int, default=5000)
    parser.add_argument("--instances-per-n", type=int, default=3)
    parser.add_argument("--base-seed", type=int, default=20260331)
    parser.add_argument("--time-limit-small", type=float, default=300.0)
    parser.add_argument("--time-limit-large", type=float, default=600.0)
    parser.add_argument("--mip-gap", type=float, default=1e-3)
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--device", type=str, default="auto")
    parser.add_argument("--output-flag", type=int, default=0)
    parser.add_argument("--threads", type=int, default=0)
    parser.add_argument("--skip-full-mb-from-n", type=int, default=20)
    return parser.parse_args()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def parse_n_values(text: str) -> List[int]:
    values = []
    for chunk in text.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        values.append(int(chunk))
    if not values:
        raise ValueError("Expected at least one N value.")
    return values


def status_text(code: int | None) -> str:
    mapping = {
        2: "OPTIMAL",
        3: "INFEASIBLE",
        4: "INF_OR_UNBD",
        5: "UNBOUNDED",
        9: "TIME_LIMIT",
        -2: "SKIPPED_INTRACTABLE",
        -1: "LICENSE_LIMIT",
        -99: "ERROR",
    }
    return mapping.get(code, f"STATUS_{code}")


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")


def load_cached_result(path: Path) -> Dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive cache handling
        return {"error": f"Failed to load cached result: {exc}"}


def run_json_solver_subprocess(
    *,
    cmd: List[str],
    result_path: Path,
    log_path: Path,
    timeout_seconds: float,
    cwd: Path,
) -> Dict[str, Any]:
    ensure_dir(log_path.parent)
    started_at = time.time()
    with log_path.open("w", encoding="utf-8") as handle:
        handle.write("COMMAND:\n")
        handle.write(" ".join(cmd) + "\n\n")
        handle.flush()
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(cwd),
                stdout=handle,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
            handle.write(f"\nEXIT_CODE:{proc.returncode}\n")
            handle.flush()
        except subprocess.TimeoutExpired:
            payload = {
                "error": f"Subprocess timeout after {timeout_seconds:.1f}s",
                "wall_time": time.time() - started_at,
            }
            write_json(result_path, payload)
            handle.write(f"\nTIMEOUT_AFTER:{timeout_seconds:.1f}\n")
            handle.flush()
            return payload
        except Exception as exc:
            payload = {
                "error": f"Subprocess launch failed: {exc}",
                "wall_time": time.time() - started_at,
            }
            write_json(result_path, payload)
            handle.write(f"\nSUBPROCESS_ERROR:{exc}\n")
            handle.flush()
            return payload

    cached = load_cached_result(result_path)
    if cached is not None:
        return cached

    payload = {
        "error": f"Solver subprocess exited without producing {result_path.name}",
        "wall_time": time.time() - started_at,
    }
    write_json(result_path, payload)
    return payload


def write_skipped_mb_result(result_path: Path, *, n: int, k_in: int, reason: str) -> Dict[str, Any]:
    payload = {
        "solver_status": -2,
        "status_text": status_text(-2),
        "error": reason,
        "bundle_space_size": int(2**n),
        "estimated_theta_binvars": int(k_in * ((2**n) - 1)),
        "wall_time": 0.0,
    }
    write_json(result_path, payload)
    return payload


def read_setup(msgpack_path: Path) -> Dict[str, Any]:
    with open(msgpack_path, "rb") as handle:
        obj = msgpack.load(handle, object_hook=mnp.decode)
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


def sample_out_of_sample_valuations(setup: Dict[str, Any], out_k: int) -> np.ndarray:
    rng = np.random.default_rng(int(setup["seed"]) + 99991)
    means = valuation_means(int(setup["n_products"]), setup["heterogeneity"])
    return sample_valuations(
        k=out_k,
        means=means,
        family=setup["dist_family"],
        rho=float(setup["rho"]),
        rng=rng,
    )


def extract_milp_solution(res: Dict[str, Any]) -> tuple[np.ndarray, np.ndarray, Any]:
    sol = (res.get("solution") or {})
    p = np.asarray(sol.get("p", []), dtype=float)
    d = np.asarray(sol.get("d", []), dtype=float)
    return p, d, sol.get("objective")


def extract_cpbsd_a_solution(res: Dict[str, Any]) -> tuple[np.ndarray, np.ndarray, Any]:
    p = np.asarray(res.get("p", []), dtype=float)
    d = np.asarray(res.get("d", []), dtype=float)
    return p, d, res.get("objective")


def time_limit_for_n(n: int, args: argparse.Namespace) -> float:
    return float(args.time_limit_small if n <= 10 else args.time_limit_large)


def instance_seed_for_n(n: int, args: argparse.Namespace) -> int:
    return int(args.base_seed + n * 1000)


def build_row(
    *,
    setup: Dict[str, Any],
    instance_id: str,
    method: str,
    n: int,
    k_in: int,
    k_out: int,
    time_limit: float,
    result_path: Path,
    solver_runtime: float | None,
    wall_time: float | None,
    nodes: float | None,
    status_code: int,
    mip_gap: float | None,
    best_bound: float | None,
    sol_count: int | None,
    big_m: float | None,
    objective_raw: float | None,
    revenue_in_sample: float | None,
    revenue_out_sample: float | None,
    policy_scope: str | None,
    bundle_price_count_full: int | None,
    bundle_price_count_selected: int | None,
    error_message: str | None,
    used_cache: bool,
    extra: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    row = {
        "instance_id": instance_id,
        "seed": int(setup.get("seed", -1)),
        "n": int(n),
        "k_in": int(k_in),
        "k_out": int(k_out),
        "method": method,
        "experiment_scope": EXPERIMENT_SCOPE,
        "dist_family": setup.get("dist_family"),
        "rho": float(setup.get("rho")) if setup.get("rho") is not None else None,
        "heterogeneity": setup.get("heterogeneity"),
        "cost_scenario": setup.get("cost_scenario"),
        "time_limit": float(time_limit),
        "solver_runtime": solver_runtime,
        "wall_time": wall_time,
        "nodes": nodes,
        "status_code": int(status_code),
        "status_text": status_text(int(status_code)),
        "mip_gap": mip_gap,
        "best_bound": best_bound,
        "sol_count": sol_count,
        "big_m": big_m,
        "objective_raw": objective_raw,
        "revenue_in_sample": revenue_in_sample,
        "revenue_out_sample": revenue_out_sample,
        "ratio_to_mb_in_sample": None,
        "ratio_to_mb_out_sample": None,
        "ratio_to_bsp_in_sample": None,
        "ratio_to_bsp_out_sample": None,
        "policy_scope": policy_scope,
        "bundle_price_count_full": bundle_price_count_full,
        "bundle_price_count_selected": bundle_price_count_selected,
        "result_path": str(result_path),
        "used_cache": bool(used_cache),
        "error_message": error_message,
    }
    if extra:
        row.update(extra)
    return row


def build_skipped_mb_row(
    *,
    setup: Dict[str, Any],
    instance_id: str,
    n: int,
    args: argparse.Namespace,
    result_path: Path,
    reason: str,
) -> Dict[str, Any]:
    return build_row(
        setup=setup,
        instance_id=instance_id,
        method="MB",
        n=n,
        k_in=args.k_in,
        k_out=args.k_out,
        time_limit=time_limit_for_n(n, args),
        result_path=result_path,
        solver_runtime=None,
        wall_time=0.0,
        nodes=None,
        status_code=-2,
        mip_gap=None,
        best_bound=None,
        sol_count=None,
        big_m=None,
        objective_raw=None,
        revenue_in_sample=None,
        revenue_out_sample=None,
        policy_scope="skipped",
        bundle_price_count_full=None,
        bundle_price_count_selected=None,
        error_message=reason,
        used_cache=False,
        extra={
            "bundle_space_size": int(2**n),
        },
    )


def summarize_by_n_and_method(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[tuple[int, str], List[Dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault((int(row["n"]), row["method"]), []).append(row)

    summary_rows = []
    for (n, method), subset in sorted(grouped.items(), key=lambda item: (item[0][0], item[0][1])):
        def numeric(key: str) -> List[float]:
            return [float(row[key]) for row in subset if isinstance(row.get(key), (int, float, np.integer, np.floating))]

        runtimes = numeric("solver_runtime")
        rev_in = numeric("revenue_in_sample")
        rev_out = numeric("revenue_out_sample")
        ratio_in = numeric("ratio_to_bsp_in_sample")
        ratio_out = numeric("ratio_to_bsp_out_sample")
        statuses: Dict[str, int] = {}
        for row in subset:
            statuses[row["status_text"]] = statuses.get(row["status_text"], 0) + 1

        summary_rows.append(
            {
                "n": n,
                "method": method,
                "method_label": METHOD_LABELS.get(method, method),
                "instances": len(subset),
                "status_counts": statuses,
                "runtime_mean": float(np.mean(runtimes)) if runtimes else None,
                "runtime_median": float(np.median(runtimes)) if runtimes else None,
                "runtime_min": float(np.min(runtimes)) if runtimes else None,
                "runtime_max": float(np.max(runtimes)) if runtimes else None,
                "revenue_in_sample_mean": float(np.mean(rev_in)) if rev_in else None,
                "revenue_out_sample_mean": float(np.mean(rev_out)) if rev_out else None,
                "ratio_to_bsp_in_sample_mean": float(np.mean(ratio_in)) if ratio_in else None,
                "ratio_to_bsp_out_sample_mean": float(np.mean(ratio_out)) if ratio_out else None,
            }
        )
    return summary_rows


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return
    fieldnames: List[str] = []
    for row in rows:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def fmt_metric(value: Any, digits: int = 4) -> str:
    if isinstance(value, (int, float, np.integer, np.floating)):
        return f"{float(value):.{digits}f}"
    return "-"


def write_unavailable_plot(out_dir: Path, *, n: int, ref_method: str, message: str) -> Path:
    ensure_dir(out_dir)
    plot_path = out_dir / f"boxplot_ratio_vs_{ref_method.lower().replace('-', '_')}_n{n}.png"
    fig, ax = plt.subplots(figsize=(10, 8))
    ax.axis("off")
    ax.text(
        0.5,
        0.55,
        f"N={n}",
        ha="center",
        va="center",
        fontsize=22,
        fontweight="bold",
        transform=ax.transAxes,
    )
    ax.text(
        0.5,
        0.40,
        message,
        ha="center",
        va="center",
        fontsize=14,
        wrap=True,
        transform=ax.transAxes,
    )
    fig.tight_layout()
    fig.savefig(plot_path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return plot_path


def write_readme(root: Path, args: argparse.Namespace, summary_rows: List[Dict[str, Any]], plot_paths: List[Path]) -> None:
    lines = [
        "# CPBSD Single-Setting BSP-Reference Matrix",
        "",
        f"- Scope: `{EXPERIMENT_SCOPE}`",
        f"- Setting: `dist={args.dist}`, `rho={args.rho}`, `heterogeneity={args.hetero}`, `cost={args.cost}`",
        f"- N values: `{args.n_values}`",
        f"- In-sample K: `{args.k_in}`",
        f"- Out-of-sample K: `{args.k_out}`",
        f"- Instances per N: `{args.instances_per_n}`",
        f"- Time limits: `N<=10 -> {args.time_limit_small}s`, `N>=20 -> {args.time_limit_large}s`",
        f"- FCP threshold: `{args.threshold}`",
        f"- Full MB skip threshold: `N >= {args.skip_full_mb_from_n}`",
        "",
        "## Aggregate Summary",
        "",
        "| N | Method | Instances | Status Counts | Runtime Mean (s) | Runtime Median (s) | Rev In Mean | Rev Out Mean | Ratio In vs BSP | Ratio Out vs BSP |",
        "| --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in summary_rows:
        status_counts = ", ".join(f"{k}:{v}" for k, v in sorted(row["status_counts"].items()))
        lines.append(
            f"| {row['n']} | {row['method_label']} | {row['instances']} | {status_counts} | "
            f"{fmt_metric(row['runtime_mean'], digits=2)} | {fmt_metric(row['runtime_median'], digits=2)} | "
            f"{fmt_metric(row['revenue_in_sample_mean'])} | {fmt_metric(row['revenue_out_sample_mean'])} | "
            f"{fmt_metric(row['ratio_to_bsp_in_sample_mean'])} | {fmt_metric(row['ratio_to_bsp_out_sample_mean'])} |"
        )
    if plot_paths:
        lines.extend(["", "## Plots", ""])
        for plot_path in plot_paths:
            lines.append(f"- `{plot_path}`")
    skipped_rows = [row for row in summary_rows if row["method"] == "MB" and row["status_counts"].get("SKIPPED_INTRACTABLE")]
    if skipped_rows:
        lines.extend(
            [
                "",
                "## Notes",
                "",
                "Full MB is intentionally skipped for larger N once the full bundle-space formulation becomes intractable.",
                "For skipped settings, full MB revenue is unavailable, but BSP-reference ratios remain available for the other methods.",
            ]
        )
    root.joinpath("README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_outputs(root: Path, args: argparse.Namespace, n_values: List[int], rows: List[Dict[str, Any]]) -> None:
    compute_mb_reference_ratios(rows)
    compute_bsp_reference_ratios(rows)
    summary_rows = summarize_by_n_and_method(rows)

    comparison_details_json = root / "comparison_details.json"
    comparison_details_csv = root / "comparison_details.csv"
    comparison_summary_json = root / "comparison_summary.json"
    runtime_summary_csv = root / "runtime_summary.csv"

    write_json(comparison_details_json, rows)
    write_csv(comparison_details_csv, rows)
    write_json(comparison_summary_json, summary_rows)
    write_csv(runtime_summary_csv, summary_rows)

    setting_plot_dir = root / "plots" / f"{args.dist}_rho{args.rho}_{args.hetero}_{args.cost}"
    plot_paths: List[Path] = []
    for n in n_values:
        plot_path = plot_ratio_boxplot(
            rows,
            out_dir=setting_plot_dir,
            n=n,
            ref_method="BSP",
            title=f"Revenue Ratio vs BSP (N={n}, {args.dist}, rho={args.rho}, {args.hetero}, {args.cost})",
            method_order=METHOD_ORDER,
            method_labels=METHOD_LABELS,
        )
        if plot_path is None:
            subset = [row for row in rows if int(row["n"]) == int(n)]
            if subset:
                message = "No valid BSP-reference ratios were available for this setting."
                plot_path = write_unavailable_plot(
                    setting_plot_dir,
                    n=n,
                    ref_method="bsp",
                    message=message,
                )
        if plot_path is not None:
            plot_paths.append(plot_path)

    write_readme(root, args, summary_rows, plot_paths)


def run_cpbsd_milp(
    *,
    result_path: Path,
    v_kn: np.ndarray,
    v_out: np.ndarray,
    c_n: np.ndarray,
    setup: Dict[str, Any],
    instance_id: str,
    n: int,
    args: argparse.Namespace,
) -> Dict[str, Any]:
    used_cache = False
    res = load_cached_result(result_path)
    if res is None:
        try:
            res = solve_milp(
                v_kn=v_kn,
                c_n=c_n,
                mip_gap=args.mip_gap,
                time_limit=time_limit_for_n(n, args),
                output_flag=args.output_flag,
                threads=args.threads,
            )
            write_json(result_path, res)
        except Exception as exc:
            res = {"error": str(exc)}
            write_json(result_path, res)
    else:
        used_cache = True

    if res.get("error"):
        return build_row(
            setup=setup,
            instance_id=instance_id,
            method="CPBSD-MILP",
            n=n,
            k_in=args.k_in,
            k_out=args.k_out,
            time_limit=time_limit_for_n(n, args),
            result_path=result_path,
            solver_runtime=None,
            wall_time=None,
            nodes=None,
            status_code=-99,
            mip_gap=None,
            best_bound=None,
            sol_count=None,
            big_m=None,
            objective_raw=None,
            revenue_in_sample=None,
            revenue_out_sample=None,
            policy_scope=None,
            bundle_price_count_full=None,
            bundle_price_count_selected=None,
            error_message=res["error"],
            used_cache=used_cache,
        )

    p_vec, d_vec, objective_raw = extract_milp_solution(res)
    valid = len(p_vec) == c_n.shape[0] and len(d_vec) == c_n.shape[0] + 1 and int(res.get("sol_count", 0)) > 0
    revenue_in = evaluate_cpbsd_policy(v_kn, c_n, p_vec, d_vec) if valid else None
    revenue_out = evaluate_cpbsd_policy(v_out, c_n, p_vec, d_vec) if valid else None
    return build_row(
        setup=setup,
        instance_id=instance_id,
        method="CPBSD-MILP",
        n=n,
        k_in=args.k_in,
        k_out=args.k_out,
        time_limit=time_limit_for_n(n, args),
        result_path=result_path,
        solver_runtime=res.get("runtime"),
        wall_time=res.get("wall_time"),
        nodes=res.get("node_count"),
        status_code=int(res.get("solver_status", -99)),
        mip_gap=res.get("mip_gap"),
        best_bound=res.get("best_bound"),
        sol_count=res.get("sol_count"),
        big_m=(res.get("meta") or {}).get("big_M"),
        objective_raw=objective_raw,
        revenue_in_sample=revenue_in,
        revenue_out_sample=revenue_out,
        policy_scope=None,
        bundle_price_count_full=None,
        bundle_price_count_selected=None,
        error_message=None if valid else "Cached or solved CPBSD-MILP result missing valid prices.",
        used_cache=used_cache,
    )


def run_cpbsd_a_method(
    *,
    result_path: Path,
    v_kn: np.ndarray,
    v_out: np.ndarray,
    c_n: np.ndarray,
    setup: Dict[str, Any],
    instance_id: str,
    n: int,
    args: argparse.Namespace,
) -> Dict[str, Any]:
    used_cache = False
    res = load_cached_result(result_path)
    if res is None:
        try:
            res = solve_cpbsd_a(
                v_kn=v_kn,
                c_n=c_n,
                mip_gap=args.mip_gap,
                time_limit=time_limit_for_n(n, args),
                output_flag=args.output_flag,
                threads=args.threads,
            )
            write_json(result_path, res)
        except Exception as exc:
            res = {"error": str(exc)}
            write_json(result_path, res)
    else:
        used_cache = True

    if res.get("error"):
        return build_row(
            setup=setup,
            instance_id=instance_id,
            method="CPBSD-A",
            n=n,
            k_in=args.k_in,
            k_out=args.k_out,
            time_limit=time_limit_for_n(n, args),
            result_path=result_path,
            solver_runtime=None,
            wall_time=None,
            nodes=None,
            status_code=-99,
            mip_gap=None,
            best_bound=None,
            sol_count=None,
            big_m=None,
            objective_raw=None,
            revenue_in_sample=None,
            revenue_out_sample=None,
            policy_scope=None,
            bundle_price_count_full=None,
            bundle_price_count_selected=None,
            error_message=res["error"],
            used_cache=used_cache,
        )

    p_vec, d_vec, objective_raw = extract_cpbsd_a_solution(res)
    valid = len(p_vec) == c_n.shape[0] and len(d_vec) == c_n.shape[0] + 1 and int(res.get("sol_count", 0)) > 0
    revenue_in = evaluate_cpbsd_policy(v_kn, c_n, p_vec, d_vec) if valid else None
    revenue_out = evaluate_cpbsd_policy(v_out, c_n, p_vec, d_vec) if valid else None
    return build_row(
        setup=setup,
        instance_id=instance_id,
        method="CPBSD-A",
        n=n,
        k_in=args.k_in,
        k_out=args.k_out,
        time_limit=time_limit_for_n(n, args),
        result_path=result_path,
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
        error_message=None if valid else "Cached or solved CPBSD-A result missing valid prices.",
        used_cache=used_cache,
    )


def run_mb_method(
    *,
    instance_path: Path,
    result_path: Path,
    v_kn: np.ndarray,
    v_out: np.ndarray,
    c_n: np.ndarray,
    setup: Dict[str, Any],
    instance_id: str,
    n: int,
    args: argparse.Namespace,
) -> Dict[str, Any]:
    used_cache = False
    res = load_cached_result(result_path)
    if res is not None and (
        not (res.get("bundle_prices_full") or {}) or res.get("mb_formulation_version") != MB_FORMULATION_VERSION
    ):
        res = None
    if res is None:
        res = run_json_solver_subprocess(
            cmd=[
                sys.executable,
                str(SCRIPT_DIR / "solve_mb_bsp_on_cpbsd_v2.py"),
                "--instance",
                str(instance_path),
                "--method",
                "mb",
                "--time-limit",
                str(time_limit_for_n(n, args)),
                "--mip-gap",
                str(args.mip_gap),
                "--output-flag",
                str(args.output_flag),
                "--threads",
                str(args.threads),
                "--save-json",
                str(result_path),
            ],
            result_path=result_path,
            log_path=result_path.with_suffix(".solver.log"),
            timeout_seconds=float(time_limit_for_n(n, args) + 120.0),
            cwd=SCRIPT_DIR,
        )
    else:
        used_cache = True

    if res.get("error"):
        return build_row(
            setup=setup,
            instance_id=instance_id,
            method="MB",
            n=n,
            k_in=args.k_in,
            k_out=args.k_out,
            time_limit=time_limit_for_n(n, args),
            result_path=result_path,
            solver_runtime=None,
            wall_time=None,
            nodes=None,
            status_code=-99,
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
            error_message=res["error"],
            used_cache=used_cache,
        )

    mb_info = extract_mb_policy_info(res)
    bundle_prices = mb_info["bundle_prices_full"]
    assortments = mb_info["assortments"]
    valid = bool(bundle_prices) and assortments is not None and bool(res.get("feasible")) and mb_info["policy_scope"] == "full_bundle_prices"
    revenue_in = eval_mb_policy(v_kn, c_n, bundle_prices, assortments) if valid else None
    revenue_out = eval_mb_policy(v_out, c_n, bundle_prices, assortments) if valid else None
    return build_row(
        setup=setup,
        instance_id=instance_id,
        method="MB",
        n=n,
        k_in=args.k_in,
        k_out=args.k_out,
        time_limit=time_limit_for_n(n, args),
        result_path=result_path,
        solver_runtime=res.get("runtime"),
        wall_time=res.get("wall_time"),
        nodes=res.get("node_count"),
        status_code=int(res.get("solver_status", -99)),
        mip_gap=res.get("mip_gap"),
        best_bound=res.get("best_bound"),
        sol_count=1 if valid else int(res.get("sol_count", 0)),
        big_m=None,
        objective_raw=res.get("objective"),
        revenue_in_sample=revenue_in,
        revenue_out_sample=revenue_out,
        policy_scope=mb_info["policy_scope"],
        bundle_price_count_full=mb_info["bundle_price_count_full"],
        bundle_price_count_selected=mb_info["bundle_price_count_selected"],
        error_message=None if valid else "Cached or solved MB result missing a full bundle price table.",
        used_cache=used_cache,
        extra={
            "bundle_space_size": mb_info["bundle_space_size"],
        },
    )


def run_bsp_method(
    *,
    result_path: Path,
    v_kn: np.ndarray,
    v_out: np.ndarray,
    c_n: np.ndarray,
    setup: Dict[str, Any],
    instance_id: str,
    n: int,
    args: argparse.Namespace,
) -> Dict[str, Any]:
    used_cache = False
    res = load_cached_result(result_path)
    if res is None:
        try:
            res = solve_bsp(
                v_kn=v_kn,
                c_n=c_n,
                mip_gap=args.mip_gap,
                time_limit=time_limit_for_n(n, args),
                output_flag=args.output_flag,
                threads=args.threads,
            )
            write_json(result_path, res)
        except Exception as exc:
            res = {"error": str(exc)}
            write_json(result_path, res)
    else:
        used_cache = True

    if res.get("error"):
        return build_row(
            setup=setup,
            instance_id=instance_id,
            method="BSP",
            n=n,
            k_in=args.k_in,
            k_out=args.k_out,
            time_limit=time_limit_for_n(n, args),
            result_path=result_path,
            solver_runtime=None,
            wall_time=None,
            nodes=None,
            status_code=-99,
            mip_gap=None,
            best_bound=None,
            sol_count=None,
            big_m=None,
            objective_raw=None,
            revenue_in_sample=None,
            revenue_out_sample=None,
            policy_scope=None,
            bundle_price_count_full=None,
            bundle_price_count_selected=None,
            error_message=res["error"],
            used_cache=used_cache,
        )

    size_prices = normalize_numeric_keys(res.get("size_prices") or {})
    valid = bool(size_prices) and bool(res.get("feasible"))
    revenue_in = eval_bsp_policy(v_kn, c_n, size_prices) if valid else None
    revenue_out = eval_bsp_policy(v_out, c_n, size_prices) if valid else None
    return build_row(
        setup=setup,
        instance_id=instance_id,
        method="BSP",
        n=n,
        k_in=args.k_in,
        k_out=args.k_out,
        time_limit=time_limit_for_n(n, args),
        result_path=result_path,
        solver_runtime=res.get("runtime"),
        wall_time=res.get("wall_time"),
        nodes=res.get("node_count"),
        status_code=int(res.get("solver_status", -99)),
        mip_gap=res.get("mip_gap"),
        best_bound=res.get("best_bound"),
        sol_count=1 if valid else int(res.get("sol_count", 0)),
        big_m=None,
        objective_raw=res.get("objective"),
        revenue_in_sample=revenue_in,
        revenue_out_sample=revenue_out,
        policy_scope="size_prices" if valid else "missing",
        bundle_price_count_full=len(size_prices),
        bundle_price_count_selected=len(size_prices),
        error_message=None if valid else "Cached or solved BSP result missing valid size prices.",
        used_cache=used_cache,
    )


def run_fcp_method(
    *,
    result_path: Path,
    v_kn: np.ndarray,
    v_out: np.ndarray,
    c_n: np.ndarray,
    setup: Dict[str, Any],
    instance_id: str,
    n: int,
    args: argparse.Namespace,
    model: Any,
    device: Any,
) -> Dict[str, Any]:
    used_cache = False
    expected_subadditivity_mode = "predicted_cover_pairwise"
    res = load_cached_result(result_path)
    if res is not None and (
        not (res.get("bundle_prices_full") or {}) or res.get("mb_formulation_version") != MB_FORMULATION_VERSION
    ):
        res = None
    if res is not None and res.get("subadditivity_mode") != expected_subadditivity_mode:
        res = None

    infer_time = None
    candidate_time = None
    raw_customer_bundle_count = None
    unique_threshold_bundle_count = None
    if res is None:
        try:
            graph_data = build_graph(v_kn, c_n)
            infer_t0 = time.time()
            prob = infer_probabilities(model, graph_data, device)
            infer_time = time.time() - infer_t0

            cand_t0 = time.time()
            candidate_assortments, raw_customer_bundle_count = build_fcp_candidate_bundles(prob, threshold=args.threshold)
            candidate_time = time.time() - cand_t0
            unique_threshold_bundle_count = int(candidate_assortments.shape[0])

            fcp_res = solve_mb_restricted(
                v_kn=v_kn,
                c_n=c_n,
                assortments=candidate_assortments,
                time_limit=time_limit_for_n(n, args),
                mip_gap=args.mip_gap,
                output_flag=args.output_flag,
                threads=args.threads,
                subadditivity_mode=expected_subadditivity_mode,
            )
            res = normalize_numeric_keys(fcp_res)
            write_json(result_path, res)
        except Exception as exc:
            res = {"error": str(exc)}
            write_json(result_path, res)
    else:
        used_cache = True

    if res.get("error"):
        return build_row(
            setup=setup,
            instance_id=instance_id,
            method="FCP-pruned-MB",
            n=n,
            k_in=args.k_in,
            k_out=args.k_out,
            time_limit=time_limit_for_n(n, args),
            result_path=result_path,
            solver_runtime=None,
            wall_time=None,
            nodes=None,
            status_code=-99,
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
            error_message=res["error"],
            used_cache=used_cache,
            extra={
                "gcn_inference_time": infer_time,
                "candidate_generation_time": candidate_time,
                "bundle_space_size": None,
                "raw_customer_bundle_count": raw_customer_bundle_count,
                "unique_threshold_bundle_count": unique_threshold_bundle_count,
                "threshold": float(args.threshold),
            },
        )

    fcp_info = extract_mb_policy_info(res)
    bundle_prices = fcp_info["bundle_prices_full"]
    assortments = fcp_info["assortments"]
    valid = bool(bundle_prices) and assortments is not None and bool(res.get("feasible")) and fcp_info["policy_scope"] == "full_bundle_prices"
    revenue_in = eval_mb_policy(v_kn, c_n, bundle_prices, assortments) if valid else None
    revenue_out = eval_mb_policy(v_out, c_n, bundle_prices, assortments) if valid else None
    return build_row(
        setup=setup,
        instance_id=instance_id,
        method="FCP-pruned-MB",
        n=n,
        k_in=args.k_in,
        k_out=args.k_out,
        time_limit=time_limit_for_n(n, args),
        result_path=result_path,
        solver_runtime=res.get("runtime"),
        wall_time=res.get("wall_time"),
        nodes=res.get("node_count"),
        status_code=int(res.get("solver_status", -99)),
        mip_gap=res.get("mip_gap"),
        best_bound=res.get("best_bound"),
        sol_count=1 if valid else int(res.get("sol_count", 0)),
        big_m=None,
        objective_raw=res.get("objective"),
        revenue_in_sample=revenue_in,
        revenue_out_sample=revenue_out,
        policy_scope=fcp_info["policy_scope"],
        bundle_price_count_full=fcp_info["bundle_price_count_full"],
        bundle_price_count_selected=fcp_info["bundle_price_count_selected"],
        error_message=None if valid else "Cached or solved FCP-pruned-MB result missing a full bundle price table.",
        used_cache=used_cache,
        extra={
            "gcn_inference_time": infer_time,
            "candidate_generation_time": candidate_time,
            "bundle_space_size": fcp_info["bundle_space_size"],
            "raw_customer_bundle_count": raw_customer_bundle_count,
            "unique_threshold_bundle_count": unique_threshold_bundle_count,
            "threshold": float(args.threshold),
        },
    )


def compute_mb_reference_ratios(rows: List[Dict[str, Any]]) -> None:
    by_instance: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for row in rows:
        by_instance.setdefault(row["instance_id"], {})[row["method"]] = row

    for methods in by_instance.values():
        mb_row = methods.get("MB")
        if mb_row is None:
            continue
        mb_in = mb_row.get("revenue_in_sample")
        mb_out = mb_row.get("revenue_out_sample")
        for row in methods.values():
            cur_in = row.get("revenue_in_sample")
            cur_out = row.get("revenue_out_sample")
            if isinstance(mb_in, (int, float, np.integer, np.floating)) and mb_in != 0 and isinstance(cur_in, (int, float, np.integer, np.floating)):
                row["ratio_to_mb_in_sample"] = float(cur_in) / float(mb_in)
            if isinstance(mb_out, (int, float, np.integer, np.floating)) and mb_out != 0 and isinstance(cur_out, (int, float, np.integer, np.floating)):
                row["ratio_to_mb_out_sample"] = float(cur_out) / float(mb_out)


def compute_bsp_reference_ratios(rows: List[Dict[str, Any]]) -> None:
    by_instance: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for row in rows:
        by_instance.setdefault(row["instance_id"], {})[row["method"]] = row

    for methods in by_instance.values():
        bsp_row = methods.get("BSP")
        if bsp_row is None:
            continue
        bsp_in = bsp_row.get("revenue_in_sample")
        bsp_out = bsp_row.get("revenue_out_sample")
        for row in methods.values():
            cur_in = row.get("revenue_in_sample")
            cur_out = row.get("revenue_out_sample")
            if isinstance(bsp_in, (int, float, np.integer, np.floating)) and bsp_in != 0 and isinstance(cur_in, (int, float, np.integer, np.floating)):
                row["ratio_to_bsp_in_sample"] = float(cur_in) / float(bsp_in)
            if isinstance(bsp_out, (int, float, np.integer, np.floating)) and bsp_out != 0 and isinstance(cur_out, (int, float, np.integer, np.floating)):
                row["ratio_to_bsp_out_sample"] = float(cur_out) / float(bsp_out)


def main() -> None:
    args = parse_args()
    n_values = parse_n_values(args.n_values)
    root = args.root
    ensure_dir(root)
    ensure_dir(root / "instances")
    ensure_dir(root / "results")
    ensure_dir(root / "plots")

    device = resolve_torch_device(args.device)
    model = load_model(args.model_path, device)
    rows: List[Dict[str, Any]] = []

    for n in n_values:
        inst_dir = root / "instances" / f"n{n}"
        result_dir = root / "results" / f"n{n}"
        ensure_dir(inst_dir)
        ensure_dir(result_dir)

        if len(list(inst_dir.glob("*.msgpack"))) < args.instances_per_n:
            generate_batch(
                out_dir=str(inst_dir),
                n_products=n,
                k_samples=args.k_in,
                dist_family=args.dist,
                rho=args.rho,
                heterogeneity=args.hetero,
                cost_scenario=args.cost,
                n_instances=args.instances_per_n,
                seed=instance_seed_for_n(n, args),
            )

        instance_paths = sorted(inst_dir.glob("*.msgpack"))[: args.instances_per_n]
        for index, instance_path in enumerate(instance_paths, start=1):
            setup = read_setup(instance_path)
            instance_id = f"n{n}_inst{index:03d}"
            v_kn, c_n = load_instance_from_msgpack(instance_path)
            v_out = sample_out_of_sample_valuations(setup, args.k_out)

            print(f"[START] N={n} instance={instance_id}", flush=True)

            rows.append(
                run_cpbsd_milp(
                    result_path=result_dir / f"{instance_id}__cpbsd_milp.json",
                    v_kn=v_kn,
                    v_out=v_out,
                    c_n=c_n,
                    setup=setup,
                    instance_id=instance_id,
                    n=n,
                    args=args,
                )
            )
            rows.append(
                run_cpbsd_a_method(
                    result_path=result_dir / f"{instance_id}__cpbsd_a.json",
                    v_kn=v_kn,
                    v_out=v_out,
                    c_n=c_n,
                    setup=setup,
                    instance_id=instance_id,
                    n=n,
                    args=args,
                )
            )
            rows.append(
                build_skipped_mb_row(
                    setup=setup,
                    instance_id=instance_id,
                    n=n,
                    args=args,
                    result_path=result_dir / f"{instance_id}__mb.json",
                    reason=(
                        f"Skipped full MB for N={n}: full bundle-space MILP requires 2^N bundles "
                        f"({2**n} bundles) and is treated as intractable for the main experiment."
                    ),
                )
                if n >= args.skip_full_mb_from_n
                else run_mb_method(
                    instance_path=instance_path,
                    result_path=result_dir / f"{instance_id}__mb.json",
                    v_kn=v_kn,
                    v_out=v_out,
                    c_n=c_n,
                    setup=setup,
                    instance_id=instance_id,
                    n=n,
                    args=args,
                )
            )
            if n >= args.skip_full_mb_from_n:
                write_skipped_mb_result(
                    result_dir / f"{instance_id}__mb.json",
                    n=n,
                    k_in=args.k_in,
                    reason=(
                        f"Skipped full MB for N={n}: full bundle-space MILP requires 2^N bundles "
                        f"({2**n} bundles) and is treated as intractable for the main experiment."
                    ),
                )
            rows.append(
                run_bsp_method(
                    result_path=result_dir / f"{instance_id}__bsp.json",
                    v_kn=v_kn,
                    v_out=v_out,
                    c_n=c_n,
                    setup=setup,
                    instance_id=instance_id,
                    n=n,
                    args=args,
                )
            )
            rows.append(
                run_fcp_method(
                    result_path=result_dir / f"{instance_id}__fcp_pruned_mb.json",
                    v_kn=v_kn,
                    v_out=v_out,
                    c_n=c_n,
                    setup=setup,
                    instance_id=instance_id,
                    n=n,
                    args=args,
                    model=model,
                    device=device,
                )
            )

            write_outputs(root, args, n_values, rows)
            print(f"[DONE] N={n} instance={instance_id}", flush=True)

    write_outputs(root, args, n_values, rows)

    print(
        json.dumps(
            {
                "comparison_details_json": str(root / "comparison_details.json"),
                "comparison_details_csv": str(root / "comparison_details.csv"),
                "comparison_summary_json": str(root / "comparison_summary.json"),
                "runtime_summary_csv": str(root / "runtime_summary.csv"),
                "plot_paths": [
                    str(path)
                    for path in sorted((root / "plots" / f"{args.dist}_rho{args.rho}_{args.hetero}_{args.cost}").glob("*.png"))
                ],
                "root": str(root),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
