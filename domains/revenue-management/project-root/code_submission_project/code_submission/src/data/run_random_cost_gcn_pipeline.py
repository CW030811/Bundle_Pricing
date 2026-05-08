"""
End-to-end pipeline for training GCN models on random cost scenarios.

Steps:
  1. Generate 4000 CPBSD instances (N=5, K=50)
  2. Write manifest CSV with train/val/test splits (3000/600/400)
  3. Generate MB labels via label_cpbsd_mb_from_manifest.py
  4. Train GCN via Training_multi_layer_cpbsd_mb_x.py

Usage (in tmux):
  python run_random_cost_gcn_pipeline.py --cost random_ind
  python run_random_cost_gcn_pipeline.py --cost random_corr
"""

from __future__ import annotations

import argparse
import csv
import json
import shlex
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = Path("/Users/sensen/.openclaw/workspace/domains/revenue-management")
EXPERIMENTS_DIR = BASE_DIR / "experiments"
CODE_DIR = BASE_DIR / "project-root" / "code_submission_project" / "code_submission"

LABEL_SCRIPT = SCRIPT_DIR / "label_cpbsd_mb_from_manifest.py"
TRAIN_SCRIPT = SCRIPT_DIR / "Training_multi_layer_cpbsd_mb_x.py"


def _run(cmd: list[str], cwd: Path | None = None) -> int:
    normalized = list(cmd)
    if normalized and normalized[0].endswith("python") and "-u" not in normalized[1:2]:
        normalized.insert(1, "-u")
    print(f"\n>>> {shlex.join(normalized)}", flush=True)
    proc = subprocess.Popen(
        normalized, cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        print(line, end="", flush=True)
    proc.wait()
    if proc.returncode != 0:
        print(f"!!! Command exited with code {proc.returncode}", flush=True)
    return proc.returncode


# ---------------------------------------------------------------------------
# Step 1: Generate instances
# ---------------------------------------------------------------------------

def step_generate(
    out_dir: Path,
    n_products: int,
    k_samples: int,
    dist: str,
    rho: float,
    hetero: str,
    cost: str,
    n_instances: int,
    seed: int,
) -> list[str]:
    """Generate CPBSD instances using generate_data_CPBSD.generate_batch()."""
    print(f"\n{'='*60}")
    print(f"STEP 1: Generate {n_instances} instances (N={n_products}, K={k_samples}, cost={cost})")
    print(f"{'='*60}", flush=True)

    sys.path.insert(0, str(SCRIPT_DIR))
    from generate_data_CPBSD import generate_batch

    t0 = time.time()
    paths = generate_batch(
        out_dir=str(out_dir),
        n_products=n_products,
        k_samples=k_samples,
        dist_family=dist,
        rho=rho,
        heterogeneity=hetero,
        cost_scenario=cost,
        n_instances=n_instances,
        seed=seed,
    )
    elapsed = time.time() - t0
    print(f"Generated {len(paths)} instances in {elapsed:.1f}s -> {out_dir}")
    return paths


# ---------------------------------------------------------------------------
# Step 2: Write manifest CSV
# ---------------------------------------------------------------------------

def step_manifest(
    instance_paths: list[str],
    manifest_path: Path,
    train_count: int,
    val_count: int,
) -> dict[str, Path]:
    """Write a single manifest CSV and per-split manifests."""
    print(f"\n{'='*60}")
    print(f"STEP 2: Write manifest ({train_count} train / {val_count} val / {len(instance_paths) - train_count - val_count} test)")
    print(f"{'='*60}", flush=True)

    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    for i, p in enumerate(instance_paths):
        if i < train_count:
            split = "train"
        elif i < train_count + val_count:
            split = "eval"
        else:
            split = "test"
        rows.append({
            "instance_path": p,
            "split": split,
            "index_in_split": i,
            "filename": Path(p).name,
        })

    with manifest_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["instance_path", "split", "index_in_split", "filename"])
        writer.writeheader()
        writer.writerows(rows)

    # Also write per-split manifests for the label step
    split_manifests = {}
    for split_name in ("train", "eval", "test"):
        split_rows = [r for r in rows if r["split"] == split_name]
        split_path = manifest_path.parent / f"manifest_{split_name}.csv"
        with split_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["instance_path", "split", "index_in_split", "filename"])
            writer.writeheader()
            writer.writerows(split_rows)
        split_manifests[split_name] = split_path
        print(f"  {split_name}: {len(split_rows)} instances -> {split_path}")

    print(f"  Full manifest: {manifest_path}")
    return split_manifests


# ---------------------------------------------------------------------------
# Step 3: Generate MB labels
# ---------------------------------------------------------------------------

def step_label(
    manifest_path: Path,
    result_dir: Path,
    time_limit: float = 300.0,
) -> int:
    """Run label_cpbsd_mb_from_manifest.py on the full manifest."""
    print(f"\n{'='*60}")
    print(f"STEP 3: Generate MB labels")
    print(f"{'='*60}", flush=True)

    result_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, str(LABEL_SCRIPT),
        "--manifest", str(manifest_path),
        "--out-dir", str(result_dir),
        "--time-limit", str(time_limit),
    ]
    return _run(cmd, cwd=SCRIPT_DIR)


# ---------------------------------------------------------------------------
# Step 4: Train GCN
# ---------------------------------------------------------------------------

def step_train(
    result_dir: Path,
    split_manifests: dict[str, Path],
    model_dir: Path,
    charts_dir: Path,
    log_dir: Path,
    epochs: int = 200,
    batch_size: int = 32,
    device: str = "auto",
    seed: int = 42,
    num_layers: int = 2,
    early_stopping_patience: int = 30,
) -> int:
    """Train GCN using result manifests from the label step."""
    print(f"\n{'='*60}")
    print(f"STEP 4: Train GCN ({epochs} epochs, device={device})")
    print(f"{'='*60}", flush=True)

    # The label step produces <manifest_stem>__mb_results.csv in result_dir.
    # We need to use those as train/eval/test manifests for the training script.
    train_result_manifest = result_dir / "manifest_train__mb_results.csv"
    eval_result_manifest = result_dir / "manifest_eval__mb_results.csv"
    test_result_manifest = result_dir / "manifest_test__mb_results.csv"

    for name, path in [("train", train_result_manifest), ("eval", eval_result_manifest)]:
        if not path.exists():
            print(f"ERROR: {name} result manifest not found: {path}")
            return 1

    model_dir.mkdir(parents=True, exist_ok=True)
    charts_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, str(TRAIN_SCRIPT),
        "--train_manifest", str(train_result_manifest),
        "--eval_manifest", str(eval_result_manifest),
        "--test_manifest", str(test_result_manifest) if test_result_manifest.exists() else "",
        "--model_dir", str(model_dir),
        "--charts_dir", str(charts_dir),
        "--log_dir", str(log_dir),
        "--device", device,
        "--epochs", str(epochs),
        "--batch_size", str(batch_size),
        "--num_layers", str(num_layers),
        "--early_stopping_patience", str(early_stopping_patience),
        "--seed", str(seed),
    ]
    return _run(cmd, cwd=SCRIPT_DIR)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Random cost GCN training pipeline")
    parser.add_argument("--cost", required=True, choices=["random_ind", "random_corr"])
    parser.add_argument("--N", type=int, default=5)
    parser.add_argument("--K", type=int, default=50)
    parser.add_argument("--dist", default="normal")
    parser.add_argument("--rho", type=float, default=0.0)
    parser.add_argument("--hetero", default="full")
    parser.add_argument("--instances", type=int, default=4000)
    parser.add_argument("--train-count", type=int, default=3000)
    parser.add_argument("--val-count", type=int, default=600)
    parser.add_argument("--seed", type=int, default=1000)
    parser.add_argument("--mb-time-limit", type=float, default=300.0)
    parser.add_argument("--epochs", type=int, default=200)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--device", default="auto", choices=["auto", "cuda", "mps", "cpu"])
    parser.add_argument("--num-layers", type=int, default=2)
    parser.add_argument("--early-stopping-patience", type=int, default=30)
    parser.add_argument("--skip-generate", action="store_true", help="Skip instance generation (reuse existing)")
    parser.add_argument("--skip-label", action="store_true", help="Skip MB label generation (reuse existing)")
    parser.add_argument("--skip-train", action="store_true", help="Skip GCN training")
    args = parser.parse_args()

    tag = f"cpbsd_random_{args.cost.split('_')[1]}_n{args.N}"
    exp_dir = EXPERIMENTS_DIR / tag
    instance_dir = exp_dir / "instances"
    result_dir = exp_dir / "results"
    manifest_path = exp_dir / "manifest_all.csv"
    model_dir = CODE_DIR / f"models_cpbsd_mb_x_{args.cost}"
    charts_dir = CODE_DIR / f"charts_cpbsd_mb_x_{args.cost}"
    log_dir = CODE_DIR / f"log_cpbsd_mb_x_{args.cost}"

    print(f"Pipeline: {args.cost} | N={args.N} K={args.K} | {args.instances} instances")
    print(f"Experiment dir: {exp_dir}")
    print(f"Model dir: {model_dir}")
    t_start = time.time()

    # Step 1: Generate
    if args.skip_generate:
        print("\n[SKIP] Instance generation")
        import glob
        instance_paths = sorted(glob.glob(str(instance_dir / "*.msgpack")))
        if not instance_paths:
            print(f"ERROR: No instances found in {instance_dir}")
            sys.exit(1)
        print(f"  Found {len(instance_paths)} existing instances")
    else:
        instance_paths = step_generate(
            out_dir=instance_dir,
            n_products=args.N,
            k_samples=args.K,
            dist=args.dist,
            rho=args.rho,
            hetero=args.hetero,
            cost=args.cost,
            n_instances=args.instances,
            seed=args.seed,
        )

    # Step 2: Manifest
    split_manifests = step_manifest(
        instance_paths=instance_paths,
        manifest_path=manifest_path,
        train_count=args.train_count,
        val_count=args.val_count,
    )

    # Step 3: Label
    if args.skip_label:
        print("\n[SKIP] MB label generation")
    else:
        # Label each split separately so result manifests are named correctly
        for split_name, split_path in split_manifests.items():
            rc = step_label(
                manifest_path=split_path,
                result_dir=result_dir,
                time_limit=args.mb_time_limit,
            )
            if rc != 0:
                print(f"ERROR: Label generation failed for {split_name} (rc={rc})")
                sys.exit(rc)

    # Step 4: Train
    if args.skip_train:
        print("\n[SKIP] GCN training")
    else:
        rc = step_train(
            result_dir=result_dir,
            split_manifests=split_manifests,
            model_dir=model_dir,
            charts_dir=charts_dir,
            log_dir=log_dir,
            epochs=args.epochs,
            batch_size=args.batch_size,
            device=args.device,
            seed=args.seed,
            num_layers=args.num_layers,
            early_stopping_patience=args.early_stopping_patience,
        )
        if rc != 0:
            print(f"ERROR: Training failed (rc={rc})")
            sys.exit(rc)

    elapsed = time.time() - t_start
    print(f"\n{'='*60}")
    print(f"PIPELINE COMPLETE: {args.cost} | {elapsed/60:.1f} min total")
    print(f"  Instances: {instance_dir}")
    print(f"  Results:   {result_dir}")
    print(f"  Model:     {model_dir}")
    print(f"{'='*60}")

    # Write summary
    summary = {
        "cost_scenario": args.cost,
        "N": args.N, "K": args.K,
        "instances": len(instance_paths),
        "splits": {"train": args.train_count, "val": args.val_count, "test": args.instances - args.train_count - args.val_count},
        "experiment_dir": str(exp_dir),
        "model_dir": str(model_dir),
        "elapsed_minutes": round(elapsed / 60, 1),
    }
    summary_path = exp_dir / "pipeline_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Summary: {summary_path}")


if __name__ == "__main__":
    main()
