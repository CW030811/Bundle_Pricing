import argparse
import csv
import json
import shutil
from pathlib import Path

from generate_data_CPBSD import generate_batch


def write_manifest(path: Path, rows):
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description="Generate a single-setting CPBSD dataset and split it into train/eval/test.")
    parser.add_argument(
        "--root",
        type=str,
        default="/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/cpbsd_gcn_single_setting_n5_normal_rho0_full_hvhm",
    )
    parser.add_argument("--N", type=int, default=5)
    parser.add_argument("--K", type=int, default=50, help="In-instance customer sample size for each generated CPBSD instance")
    parser.add_argument("--dist", type=str, default="normal")
    parser.add_argument("--rho", type=float, default=0.0)
    parser.add_argument("--hetero", type=str, default="full")
    parser.add_argument("--cost", type=str, default="hvhm")
    parser.add_argument("--instances", type=int, default=5000)
    parser.add_argument("--train", type=int, default=4000)
    parser.add_argument("--eval", type=int, default=500)
    parser.add_argument("--test", type=int, default=500)
    parser.add_argument("--seed", type=int, default=20260310)
    parser.add_argument("--copy_split_dirs", action="store_true", help="Also copy files into train/eval/test subdirectories")
    args = parser.parse_args()

    total_split = args.train + args.eval + args.test
    if total_split != args.instances:
        raise ValueError(f"train+eval+test must equal instances, got {total_split} vs {args.instances}")

    root = Path(args.root)
    all_dir = root / "all_instances"
    root.mkdir(parents=True, exist_ok=True)
    all_dir.mkdir(parents=True, exist_ok=True)

    paths = generate_batch(
        out_dir=str(all_dir),
        n_products=args.N,
        k_samples=args.K,
        dist_family=args.dist,
        rho=args.rho,
        heterogeneity=args.hetero,
        cost_scenario=args.cost,
        n_instances=args.instances,
        seed=args.seed,
    )

    paths = [Path(p) for p in sorted(paths)]
    train_paths = paths[: args.train]
    eval_paths = paths[args.train : args.train + args.eval]
    test_paths = paths[args.train + args.eval :]

    manifests = {
        "train": train_paths,
        "eval": eval_paths,
        "test": test_paths,
    }

    summary = {
        "root": str(root),
        "setting": {
            "N": args.N,
            "K": args.K,
            "dist": args.dist,
            "rho": args.rho,
            "heterogeneity": args.hetero,
            "cost": args.cost,
            "seed": args.seed,
        },
        "counts": {
            "instances_total": args.instances,
            "train": len(train_paths),
            "eval": len(eval_paths),
            "test": len(test_paths),
        },
        "all_instances_dir": str(all_dir),
    }

    for split_name, split_paths in manifests.items():
        rows = []
        for idx, path in enumerate(split_paths, 1):
            rows.append(
                {
                    "split": split_name,
                    "index_in_split": idx,
                    "filename": path.name,
                    "instance_path": str(path),
                }
            )
        write_manifest(root / f"{split_name}_manifest.csv", rows)
        (root / f"{split_name}_manifest.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

        if args.copy_split_dirs:
            split_dir = root / split_name
            split_dir.mkdir(parents=True, exist_ok=True)
            for path in split_paths:
                target = split_dir / path.name
                if not target.exists():
                    shutil.copy2(path, target)

    (root / "dataset_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
