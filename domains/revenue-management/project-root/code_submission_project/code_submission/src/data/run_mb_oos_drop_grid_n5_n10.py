from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from statistics import NormalDist
from typing import Any, Dict, Iterable, List

import msgpack
import msgpack_numpy as mnp
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.append(str(SCRIPT_DIR))

from solve_mb_bsp_on_cpbsd_v2 import MB_FORMULATION_VERSION, eval_mb_policy, json_default, normalize_numeric_keys


EXPERIMENT_SCOPE = "mb_oos_drop_grid_n5_n10_v1"
DEFAULT_ROOT = Path(
    "/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/mb_oos_drop_grid_n5_n10_t300"
)

DIST_FAMILIES = ["exponential", "logit", "lognormal", "normal", "uniform"]
RHOS = [-0.5, 0.0, 0.5]
HETEROS = ["none", "partial", "full"]
COSTS = ["zero", "hvhm", "hvlm"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan MB out-of-sample drop across all sample settings for N=5 and N=10.")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--n-values", type=str, default="5,10")
    parser.add_argument("--k-in", type=int, default=50)
    parser.add_argument("--k-out", type=int, default=5000)
    parser.add_argument("--instance-index", type=int, default=1)
    parser.add_argument("--base-seed", type=int, default=20260306)
    parser.add_argument("--time-limit", type=float, default=300.0)
    parser.add_argument("--mip-gap", type=float, default=1e-2)
    parser.add_argument("--output-flag", type=int, default=0)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--dist-families", type=str, default=",".join(DIST_FAMILIES))
    parser.add_argument("--rhos", type=str, default=",".join(str(item) for item in RHOS))
    parser.add_argument("--heteros", type=str, default=",".join(HETEROS))
    parser.add_argument("--costs", type=str, default=",".join(COSTS))
    return parser.parse_args()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def parse_n_values(text: str) -> List[int]:
    values: List[int] = []
    for chunk in text.split(","):
        chunk = chunk.strip()
        if chunk:
            values.append(int(chunk))
    if not values:
        raise ValueError("Expected at least one N value.")
    return values


def parse_str_list(text: str) -> List[str]:
    return [item.strip() for item in text.split(",") if item.strip()]


def parse_float_list(text: str) -> List[float]:
    return [float(item.strip()) for item in text.split(",") if item.strip()]


def status_text(code: int | None) -> str:
    mapping = {
        2: "OPTIMAL",
        3: "INFEASIBLE",
        4: "INF_OR_UNBD",
        5: "UNBOUNDED",
        9: "TIME_LIMIT",
        -1: "LICENSE_LIMIT",
        -99: "ERROR",
    }
    return mapping.get(code, f"STATUS_{code}")


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")


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


def _norm_cdf(x: np.ndarray) -> np.ndarray:
    return 0.5 * (1.0 + np.vectorize(math.erf)(x / math.sqrt(2.0)))


def _norm_ppf(u: np.ndarray) -> np.ndarray:
    inv = np.vectorize(NormalDist().inv_cdf)
    return inv(u)


def _toeplitz_corr(n: int, rho: float) -> np.ndarray:
    idx = np.arange(n)
    return rho ** np.abs(idx[:, None] - idx[None, :])


def valuation_means(n: int, heterogeneity: str) -> np.ndarray:
    if heterogeneity == "none":
        return np.ones(n)
    if heterogeneity == "partial":
        n1 = int(0.4 * n)
        means = np.ones(n)
        means[n1:] = 5.0
        return means
    if n == 1:
        return np.array([1.0])
    idx = np.arange(n)
    return 1.0 + 9.0 * idx / (n - 1)


def production_costs(n: int, heterogeneity: str, scenario: str) -> np.ndarray:
    idx = np.arange(n)
    if scenario == "zero":
        return np.zeros(n)
    if heterogeneity == "none":
        if scenario == "hvhm":
            return np.full(n, 0.8)
        return 0.1 + 1.5 * idx / max(1, (n - 1))
    if heterogeneity == "partial":
        n1 = int(0.4 * n)
        c = np.zeros(n)
        if scenario == "hvhm":
            c[:n1] = 0.8
            c[n1:] = 4.4
            return c
        c[:n1] = 0.1 + 1.5 * np.arange(n1) / max(1, (n - 1))
        n2 = n - n1
        c[n1:] = 4.1 + 1.5 * np.arange(n2) / max(1, (n2 - 1))
        return c
    if scenario == "hvhm":
        return 0.8 + 8.6 * idx / max(1, (n - 1))
    return 0.1 + 10.5 * idx / max(1, (n - 1))


def sample_valuations(k: int, means: np.ndarray, family: str, rho: float, rng: np.random.Generator) -> np.ndarray:
    n = len(means)
    corr = _toeplitz_corr(n, rho)
    z = rng.multivariate_normal(mean=np.zeros(n), cov=corr, size=k)
    u = np.clip(_norm_cdf(z), 1e-10, 1 - 1e-10)
    if family == "exponential":
        v = -means * np.log(1.0 - u)
    elif family == "logit":
        scale = 0.25
        loc = means - 0.577 * scale
        v = loc + (-scale * np.log(-np.log(u)))
    elif family == "lognormal":
        sigma = 0.5
        mu = np.log(means) - 0.5 * (sigma**2)
        v = np.exp(mu + sigma * _norm_ppf(u))
    elif family == "normal":
        sigma = 0.5
        v = means + sigma * _norm_ppf(u)
    elif family == "uniform":
        v = (means - 1.0) + 2.0 * u
    else:
        raise ValueError(f"Unsupported family: {family}")
    return np.maximum(v, 0.0)


def instance_stem(*, n: int, k_in: int, instance_index: int, dist: str, rho: float, hetero: str, cost: str) -> str:
    return f"cpbsd_instance_{instance_index:03d}_N{n}_K{k_in}_{dist}_rho{rho}_{hetero}_{cost}"


def build_instance_payload(
    *,
    n: int,
    k_in: int,
    dist: str,
    rho: float,
    hetero: str,
    cost: str,
    seed: int,
) -> Dict[str, Any]:
    rng = np.random.default_rng(seed)
    means = valuation_means(n, hetero)
    costs = production_costs(n, hetero, cost)
    valuations = sample_valuations(k=k_in, means=means, family=dist, rho=rho, rng=rng)
    potential_surplus = valuations - costs[None, :]
    return {
        "setup": {
            "n_products": n,
            "k_samples": k_in,
            "dist_family": dist,
            "rho": rho,
            "heterogeneity": hetero,
            "cost_scenario": cost,
            "seed": seed,
        },
        "means_E_V": means,
        "production_cost_c": costs,
        "valuation_samples_V": valuations,
        "potential_surplus_Z": potential_surplus,
    }


def generate_instance_if_missing(
    *,
    path: Path,
    n: int,
    k_in: int,
    dist: str,
    rho: float,
    hetero: str,
    cost: str,
    seed: int,
) -> None:
    if path.exists():
        return
    payload = build_instance_payload(n=n, k_in=k_in, dist=dist, rho=rho, hetero=hetero, cost=cost, seed=seed)
    with path.open("wb") as handle:
        msgpack.dump(payload, handle, default=mnp.encode)


def read_instance(path: Path) -> tuple[Dict[str, Any], np.ndarray, np.ndarray]:
    with path.open("rb") as handle:
        obj = msgpack.load(handle, object_hook=mnp.decode)
    setup = obj.get("setup", {})
    v_kn = np.asarray(obj["valuation_samples_V"], dtype=float)
    c_n = np.asarray(obj["production_cost_c"], dtype=float)
    return setup, v_kn, c_n


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


def load_cached_result(path: Path) -> Dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        res = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not (res.get("bundle_prices_full") or {}):
        return None
    if res.get("mb_formulation_version") != MB_FORMULATION_VERSION:
        return None
    return res


def run_solver_subprocess(
    *,
    instance_path: Path,
    result_path: Path,
    log_path: Path,
    time_limit: float,
    mip_gap: float,
    output_flag: int,
) -> Dict[str, Any]:
    ensure_dir(log_path.parent)
    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "solve_mb_bsp_on_cpbsd_v2.py"),
        "--instance",
        str(instance_path),
        "--method",
        "mb",
        "--time-limit",
        str(time_limit),
        "--mip-gap",
        str(mip_gap),
        "--output-flag",
        str(output_flag),
        "--save-json",
        str(result_path),
    ]
    started_at = time.time()
    with log_path.open("w", encoding="utf-8") as handle:
        handle.write("COMMAND:\n")
        handle.write(" ".join(cmd) + "\n\n")
        handle.flush()
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(SCRIPT_DIR),
                stdout=handle,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=float(time_limit + 60.0),
                check=False,
            )
            handle.write(f"\nEXIT_CODE:{proc.returncode}\n")
            handle.flush()
        except subprocess.TimeoutExpired:
            payload = {
                "error": f"Subprocess timeout after {time_limit + 60.0:.1f}s",
                "solver_status": -99,
                "feasible": False,
                "runtime": None,
                "wall_time": time.time() - started_at,
            }
            write_json(result_path, payload)
            return payload
        except Exception as exc:
            payload = {
                "error": str(exc),
                "solver_status": -99,
                "feasible": False,
                "runtime": None,
                "wall_time": time.time() - started_at,
            }
            write_json(result_path, payload)
            return payload

    cached = load_cached_result(result_path)
    if cached is not None:
        return cached
    try:
        return json.loads(result_path.read_text(encoding="utf-8"))
    except Exception:
        payload = {
            "error": f"Solver subprocess exited without producing a valid result at {result_path}",
            "solver_status": -99,
            "feasible": False,
            "runtime": None,
            "wall_time": time.time() - started_at,
        }
        write_json(result_path, payload)
        return payload


def setting_tasks(args: argparse.Namespace) -> List[Dict[str, Any]]:
    n_values = parse_n_values(args.n_values)
    dist_families = parse_str_list(args.dist_families)
    rhos = parse_float_list(args.rhos)
    heteros = parse_str_list(args.heteros)
    costs = parse_str_list(args.costs)
    tasks: List[Dict[str, Any]] = []
    for n in n_values:
        setting_idx = 0
        for dist in dist_families:
            for rho in rhos:
                for hetero in heteros:
                    for cost in costs:
                        setting_idx += 1
                        seed = int(args.base_seed + n * 100000 + setting_idx * 1000 + (args.instance_index - 1))
                        tasks.append(
                            {
                                "n": n,
                                "dist_family": dist,
                                "rho": rho,
                                "heterogeneity": hetero,
                                "cost_scenario": cost,
                                "setting_idx": setting_idx,
                                "seed": seed,
                            }
                        )
    return tasks


def evaluate_task(task: Dict[str, Any], args: argparse.Namespace) -> Dict[str, Any]:
    n = int(task["n"])
    dist = task["dist_family"]
    rho = float(task["rho"])
    hetero = task["heterogeneity"]
    cost = task["cost_scenario"]
    stem = instance_stem(
        n=n,
        k_in=args.k_in,
        instance_index=args.instance_index,
        dist=dist,
        rho=rho,
        hetero=hetero,
        cost=cost,
    )

    inst_dir = args.root / "instances" / f"n{n}"
    result_dir = args.root / "results" / f"n{n}"
    ensure_dir(inst_dir)
    ensure_dir(result_dir)

    instance_path = inst_dir / f"{stem}.msgpack"
    generate_instance_if_missing(
        path=instance_path,
        n=n,
        k_in=args.k_in,
        dist=dist,
        rho=rho,
        hetero=hetero,
        cost=cost,
        seed=int(task["seed"]),
    )

    setup, v_kn, c_n = read_instance(instance_path)
    v_out = sample_out_of_sample_valuations(setup, args.k_out)
    result_path = result_dir / f"{stem}__mb.json"
    log_path = result_dir / f"{stem}__mb.solver.log"

    used_cache = False
    result = load_cached_result(result_path)
    if result is None:
        result = run_solver_subprocess(
            instance_path=instance_path,
            result_path=result_path,
            log_path=log_path,
            time_limit=args.time_limit,
            mip_gap=args.mip_gap,
            output_flag=args.output_flag,
        )
    else:
        used_cache = True

    bundle_prices = normalize_numeric_keys(result.get("bundle_prices_full") or {})
    assortments = np.asarray(result.get("assortments"), dtype=int) if result.get("assortments") is not None else None
    feasible = bool(result.get("feasible")) and bool(bundle_prices) and assortments is not None
    revenue_in = eval_mb_policy(v_kn, c_n, bundle_prices, assortments) if feasible else None
    revenue_out = eval_mb_policy(v_out, c_n, bundle_prices, assortments) if feasible else None
    ratio_out_in = float(revenue_out) / float(revenue_in) if feasible and revenue_in not in (None, 0) else None
    drop = 1.0 - ratio_out_in if ratio_out_in is not None else None

    return {
        "n": n,
        "instance_index": int(args.instance_index),
        "instance_id": stem,
        "seed": int(task["seed"]),
        "dist_family": dist,
        "rho": rho,
        "heterogeneity": hetero,
        "cost_scenario": cost,
        "method": "MB",
        "experiment_scope": EXPERIMENT_SCOPE,
        "k_in": int(args.k_in),
        "k_out": int(args.k_out),
        "time_limit": float(args.time_limit),
        "mip_gap_target": float(args.mip_gap),
        "solver_status": int(result.get("solver_status", -99)),
        "status_text": status_text(int(result.get("solver_status", -99))),
        "feasible": bool(result.get("feasible")),
        "solver_runtime": result.get("runtime"),
        "wall_time": result.get("wall_time"),
        "mip_gap": result.get("mip_gap"),
        "objective_raw": result.get("objective"),
        "revenue_in_sample": revenue_in,
        "revenue_out_sample": revenue_out,
        "ratio_out_in": ratio_out_in,
        "drop": drop,
        "bundle_space_size": result.get("bundle_space_size"),
        "bundle_price_count_full": len(bundle_prices),
        "used_cache": used_cache,
        "instance_path": str(instance_path),
        "result_path": str(result_path),
        "log_path": str(log_path),
        "error_message": result.get("error"),
    }


def sort_rows(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(
        rows,
        key=lambda row: (
            int(row["n"]),
            float(row["drop"]) if isinstance(row.get("drop"), (int, float, np.integer, np.floating)) else float("inf"),
            row["dist_family"],
            float(row["rho"]),
            row["heterogeneity"],
            row["cost_scenario"],
        ),
    )


def summarize(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[tuple[int, str, float, str, str], List[Dict[str, Any]]] = {}
    for row in rows:
        key = (
            int(row["n"]),
            row["dist_family"],
            float(row["rho"]),
            row["heterogeneity"],
            row["cost_scenario"],
        )
        grouped.setdefault(key, []).append(row)

    summary_rows: List[Dict[str, Any]] = []
    for key, subset in sorted(grouped.items()):
        drops = [float(row["drop"]) for row in subset if isinstance(row.get("drop"), (int, float, np.integer, np.floating))]
        ratios = [float(row["ratio_out_in"]) for row in subset if isinstance(row.get("ratio_out_in"), (int, float, np.integer, np.floating))]
        runtimes = [float(row["solver_runtime"]) for row in subset if isinstance(row.get("solver_runtime"), (int, float, np.integer, np.floating))]
        statuses: Dict[str, int] = {}
        for row in subset:
            statuses[row["status_text"]] = statuses.get(row["status_text"], 0) + 1
        summary_rows.append(
            {
                "n": key[0],
                "dist_family": key[1],
                "rho": key[2],
                "heterogeneity": key[3],
                "cost_scenario": key[4],
                "instances": len(subset),
                "status_counts": statuses,
                "runtime_mean": float(np.mean(runtimes)) if runtimes else None,
                "drop_mean": float(np.mean(drops)) if drops else None,
                "drop_median": float(np.median(drops)) if drops else None,
                "ratio_mean": float(np.mean(ratios)) if ratios else None,
                "ratio_median": float(np.median(ratios)) if ratios else None,
            }
        )
    return sort_rows(summary_rows)


def write_report(root: Path, args: argparse.Namespace, summary_rows: List[Dict[str, Any]]) -> None:
    lines = [
        "# MB Out-of-Sample Drop Grid Scan",
        "",
        f"- Scope: `{EXPERIMENT_SCOPE}`",
        f"- N values: `{args.n_values}`",
        f"- Instance per setting: `{args.instance_index:03d}`",
        f"- In-sample K: `{args.k_in}`",
        f"- Out-of-sample K: `{args.k_out}`",
        f"- Time limit: `{args.time_limit}s`",
        f"- MIP gap target: `{args.mip_gap}`",
        f"- Workers: `{args.workers}`",
        "",
    ]
    for n in sorted({int(row["n"]) for row in summary_rows}):
        lines.extend(
            [
                f"## N={n}",
                "",
                "| Dist | rho | Hetero | Cost | Status | Runtime Mean (s) | Out/In Ratio | Drop |",
                "| --- | ---: | --- | --- | --- | ---: | ---: | ---: |",
            ]
        )
        for row in [item for item in summary_rows if int(item["n"]) == n]:
            status_texts = ", ".join(f"{k}:{v}" for k, v in sorted(row["status_counts"].items()))
            lines.append(
                f"| {row['dist_family']} | {row['rho']} | {row['heterogeneity']} | {row['cost_scenario']} | "
                f"{status_texts} | {fmt_metric(row['runtime_mean'], 2)} | {fmt_metric(row['ratio_mean'])} | {fmt_metric(row['drop_mean'])} |"
            )
        lines.append("")
    root.joinpath("README.md").write_text("\n".join(lines), encoding="utf-8")


def write_outputs(root: Path, args: argparse.Namespace, rows: List[Dict[str, Any]]) -> None:
    rows_sorted = sort_rows(rows)
    summary_rows = summarize(rows_sorted)
    write_json(root / "details.json", rows_sorted)
    write_csv(root / "details.csv", rows_sorted)
    write_json(root / "summary.json", summary_rows)
    write_csv(root / "summary.csv", summary_rows)
    write_report(root, args, summary_rows)


def main() -> None:
    args = parse_args()
    ensure_dir(args.root)
    ensure_dir(args.root / "instances")
    ensure_dir(args.root / "results")

    tasks = setting_tasks(args)
    rows: List[Dict[str, Any]] = []
    started_at = time.time()

    with ThreadPoolExecutor(max_workers=max(1, int(args.workers))) as executor:
        future_map = {executor.submit(evaluate_task, task, args): task for task in tasks}
        for idx, future in enumerate(as_completed(future_map), start=1):
            row = future.result()
            rows.append(row)
            write_outputs(args.root, args, rows)
            if idx % 10 == 0 or idx == len(tasks):
                elapsed = time.time() - started_at
                print(
                    f"[PROGRESS] {idx}/{len(tasks)} completed elapsed={elapsed:.1f}s "
                    f"last={row['instance_id']} status={row['status_text']}",
                    flush=True,
                )

    write_outputs(args.root, args, rows)
    print(
        json.dumps(
            {
                "root": str(args.root),
                "details_csv": str(args.root / "details.csv"),
                "summary_csv": str(args.root / "summary.csv"),
                "readme": str(args.root / "README.md"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
