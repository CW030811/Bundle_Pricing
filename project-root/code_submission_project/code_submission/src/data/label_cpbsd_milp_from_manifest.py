import argparse
import csv
import json
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.append(str(SCRIPT_DIR))

from solve_cpbsd_milp import load_instance_from_msgpack, solve


def read_manifest(path: Path):
    with path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_manifest(path: Path, rows):
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description="Batch label CPBSD instances with CPBSD-MILP using manifest files.")
    parser.add_argument("--manifest", required=True, type=str)
    parser.add_argument("--out-dir", required=True, type=str)
    parser.add_argument("--time-limit", type=float, default=300.0)
    parser.add_argument("--mip-gap", type=float, default=1e-2)
    parser.add_argument("--output-flag", type=int, default=0)
    parser.add_argument("--big-m", type=float, default=-1.0)
    parser.add_argument("--p-ub", type=float, default=-1.0)
    parser.add_argument("--d-ub", type=float, default=-1.0)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = read_manifest(manifest_path)
    if args.limit > 0:
        rows = rows[: args.limit]

    result_rows = []
    big_m = None if args.big_m <= 0 else args.big_m
    p_ub = None if args.p_ub <= 0 else args.p_ub
    d_ub = None if args.d_ub <= 0 else args.d_ub

    started_at = time.time()
    for idx, row in enumerate(rows, 1):
        instance_path = Path(row["instance_path"])
        split = row.get("split", "unknown")
        stem = instance_path.stem
        result_path = out_dir / f"{stem}__cpbsd_milp.json"

        if result_path.exists() and not args.overwrite:
            try:
                result = json.loads(result_path.read_text(encoding="utf-8"))
            except Exception as exc:
                result = {"error": f"Failed to read cached result: {exc}"}
        else:
            try:
                v_kn, c_n = load_instance_from_msgpack(instance_path)
                result = solve(
                    v_kn=v_kn,
                    c_n=c_n,
                    mip_gap=args.mip_gap,
                    time_limit=args.time_limit,
                    output_flag=args.output_flag,
                    big_m=big_m,
                    p_ub=p_ub,
                    d_ub=d_ub,
                )
            except Exception as exc:
                result = {"error": str(exc)}
            result_path.write_text(
                json.dumps(
                    result,
                    ensure_ascii=False,
                    indent=2,
                    default=lambda x: x.tolist() if hasattr(x, "tolist") else x,
                ),
                encoding="utf-8",
            )

        solver_status = result.get("solver_status", -1)
        sol_count = result.get("sol_count", 0)
        runtime = result.get("runtime")
        wall_time = result.get("wall_time")
        mip_gap = result.get("mip_gap")
        best_bound = result.get("best_bound")
        objective = None
        q_positive_rate = None
        q_mean = None
        if result.get("solution"):
            objective = result["solution"].get("objective")
            q = result["solution"].get("q")
            if q is not None:
                import numpy as np

                q_arr = np.asarray(q, dtype=float)
                q_kn = q_arr.sum(axis=2)
                q_positive_rate = float((q_kn > 0).mean())
                q_mean = float(q_kn.mean())

        result_rows.append(
            {
                "split": split,
                "index_in_split": row.get("index_in_split", idx),
                "filename": row.get("filename", instance_path.name),
                "instance_path": str(instance_path),
                "result_path": str(result_path),
                "solver_status": solver_status,
                "sol_count": sol_count,
                "runtime": runtime,
                "wall_time": wall_time,
                "mip_gap": mip_gap,
                "best_bound": best_bound,
                "objective": objective,
                "q_positive_rate": q_positive_rate,
                "q_mean": q_mean,
                "has_solution": bool(result.get("solution")),
                "error": result.get("error", ""),
            }
        )

        if idx % 10 == 0 or idx == len(rows):
            elapsed = time.time() - started_at
            print(f"[{idx}/{len(rows)}] labeled {stem} | status={solver_status} | sol_count={sol_count} | elapsed={elapsed:.1f}s")

    result_manifest_path = out_dir / f"{manifest_path.stem}__cpbsd_milp_results.csv"
    write_manifest(result_manifest_path, result_rows)
    summary = {
        "manifest": str(manifest_path),
        "out_dir": str(out_dir),
        "count": len(result_rows),
        "time_limit": args.time_limit,
        "mip_gap": args.mip_gap,
        "has_solution_count": sum(1 for r in result_rows if r["has_solution"]),
        "status_counts": {},
        "result_manifest": str(result_manifest_path),
    }
    for row in result_rows:
        key = str(row["solver_status"])
        summary["status_counts"][key] = summary["status_counts"].get(key, 0) + 1

    summary_path = out_dir / f"{manifest_path.stem}__cpbsd_milp_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
