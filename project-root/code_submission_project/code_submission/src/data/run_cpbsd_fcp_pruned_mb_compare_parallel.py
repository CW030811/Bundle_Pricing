from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Tuple


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run many single-instance FCP-pruned MB comparisons in parallel and aggregate results.")
    parser.add_argument(
        "--script-path",
        type=str,
        default="/Users/sensen/.openclaw/workspace/domains/revenue-management/project-root/code_submission_project/code_submission/src/data/run_cpbsd_fcp_pruned_mb_compare.py",
    )
    parser.add_argument(
        "--python-bin",
        type=str,
        default="/Users/sensen/.openclaw/workspace/domains/revenue-management/project-root/code_submission_project/code_submission/.venv/bin/python",
    )
    parser.add_argument(
        "--base-root",
        type=str,
        default="/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/cpbsd_fcp_pruned_mb_compare_n10k50_10inst_strict300",
    )
    parser.add_argument("--instances", type=int, default=10)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--base-seed", type=int, default=20260321)
    parser.add_argument("--N", type=int, default=10)
    parser.add_argument("--K", type=int, default=50)
    parser.add_argument("--dist", type=str, default="normal")
    parser.add_argument("--rho", type=float, default=0.0)
    parser.add_argument("--hetero", type=str, default="full")
    parser.add_argument("--cost", type=str, default="hvhm")
    parser.add_argument("--device", type=str, default="auto")
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--time-limit-fcp-mb", type=float, default=300.0)
    parser.add_argument("--time-limit-bsp", type=float, default=300.0)
    parser.add_argument("--time-limit-cpbsd-a", type=float, default=300.0)
    parser.add_argument("--mip-gap", type=float, default=1e-2)
    parser.add_argument("--output-flag", type=int, default=0)
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    return parser.parse_args()


def build_jobs(args: argparse.Namespace) -> List[Tuple[int, Path, Path, List[str]]]:
    base_root = Path(args.base_root)
    runs_dir = base_root / "runs"
    logs_dir = base_root / "logs"
    ensure_dir(runs_dir)
    ensure_dir(logs_dir)

    jobs: List[Tuple[int, Path, Path, List[str]]] = []
    for idx in range(args.instances):
        seed = args.base_seed + idx
        run_root = runs_dir / f"seed_{seed}"
        log_file = logs_dir / f"seed_{seed}.log"
        ensure_dir(run_root)
        cmd = [
            args.python_bin,
            args.script_path,
            "--root",
            str(run_root),
            "--instances",
            "1",
            "--seed",
            str(seed),
            "--N",
            str(args.N),
            "--K",
            str(args.K),
            "--dist",
            args.dist,
            "--rho",
            str(args.rho),
            "--hetero",
            args.hetero,
            "--cost",
            args.cost,
            "--device",
            args.device,
            "--threshold",
            str(args.threshold),
            "--time-limit-fcp-mb",
            str(args.time_limit_fcp_mb),
            "--time-limit-bsp",
            str(args.time_limit_bsp),
            "--time-limit-cpbsd-a",
            str(args.time_limit_cpbsd_a),
            "--mip-gap",
            str(args.mip_gap),
            "--output-flag",
            str(args.output_flag),
        ]
        jobs.append((seed, run_root, log_file, cmd))
    return jobs


def run_jobs(args: argparse.Namespace, jobs: List[Tuple[int, Path, Path, List[str]]]) -> None:
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    running: Dict[int, Dict[str, object]] = {}
    waiting = list(jobs)

    while waiting or running:
        while waiting and len(running) < args.workers:
            seed, run_root, log_file, cmd = waiting.pop(0)
            log_fh = log_file.open("w", encoding="utf-8")
            print(f"[start] seed={seed} root={run_root}")
            proc = subprocess.Popen(
                cmd,
                stdout=log_fh,
                stderr=subprocess.STDOUT,
                env=env,
            )
            running[seed] = {
                "proc": proc,
                "log_fh": log_fh,
                "run_root": run_root,
                "log_file": log_file,
                "start_time": time.time(),
            }

        finished = []
        for seed, meta in running.items():
            proc = meta["proc"]
            rc = proc.poll()
            if rc is None:
                continue
            meta["log_fh"].close()
            elapsed = time.time() - float(meta["start_time"])
            print(f"[done] seed={seed} rc={rc} elapsed={elapsed:.1f}s log={meta['log_file']}")
            if rc != 0:
                raise RuntimeError(f"Seed {seed} failed with rc={rc}. See {meta['log_file']}")
            finished.append(seed)

        for seed in finished:
            running.pop(seed, None)

        if waiting or running:
            time.sleep(args.poll_seconds)


def aggregate_results(base_root: Path) -> Dict[str, object]:
    rows = []
    for path in sorted(base_root.glob("runs/seed_*/comparison_summary.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for row in data:
            row["run_root"] = str(path.parent)
            rows.append(row)

    if not rows:
        raise RuntimeError("No comparison_summary.json files found under runs/seed_*/")

    summary_json = base_root / "comparison_summary_all.json"
    summary_csv = base_root / "comparison_summary_all.csv"
    aggregate_json = base_root / "aggregate_metrics.json"

    summary_json.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    fieldnames: List[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with summary_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    aggregate: Dict[str, Dict[str, float]] = {}
    for method in sorted({row["method"] for row in rows}):
        method_rows = [row for row in rows if row["method"] == method]
        in_vals = [float(row["revenue_in_sample"]) for row in method_rows if row.get("revenue_in_sample") is not None]
        out_vals = [float(row["revenue_out_sample"]) for row in method_rows if row.get("revenue_out_sample") is not None]
        time_vals = [float(row["solver_runtime"]) for row in method_rows if row.get("solver_runtime") is not None]
        ratio_to_bsp_vals = [float(row["ratio_to_bsp"]) for row in method_rows if row.get("ratio_to_bsp") is not None]
        ratio_to_cpbsd_vals = [float(row["ratio_to_cpbsd_a"]) for row in method_rows if row.get("ratio_to_cpbsd_a") is not None]
        aggregate[method] = {
            "count": len(method_rows),
            "avg_revenue_in_sample": sum(in_vals) / len(in_vals) if in_vals else None,
            "avg_revenue_out_sample": sum(out_vals) / len(out_vals) if out_vals else None,
            "avg_solver_runtime": sum(time_vals) / len(time_vals) if time_vals else None,
            "avg_ratio_to_bsp": sum(ratio_to_bsp_vals) / len(ratio_to_bsp_vals) if ratio_to_bsp_vals else None,
            "avg_ratio_to_cpbsd_a": sum(ratio_to_cpbsd_vals) / len(ratio_to_cpbsd_vals) if ratio_to_cpbsd_vals else None,
        }

    aggregate_json.write_text(json.dumps(aggregate, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "summary_json": str(summary_json),
        "summary_csv": str(summary_csv),
        "aggregate_json": str(aggregate_json),
        "aggregate": aggregate,
        "row_count": len(rows),
    }


def main() -> None:
    args = parse_args()
    jobs = build_jobs(args)
    run_jobs(args, jobs)
    result = aggregate_results(Path(args.base_root))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
