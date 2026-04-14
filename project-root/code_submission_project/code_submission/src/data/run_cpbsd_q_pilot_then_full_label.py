import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent


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


def run_cmd(cmd, cwd: Path):
    print(f"RUN: {' '.join(map(str, cmd))}")
    subprocess.run(cmd, cwd=str(cwd), check=True)


def main():
    parser = argparse.ArgumentParser(description="Pilot CPBSD q_kn training, then auto-launch full CPBSD-MILP labeling if pilot is healthy.")
    parser.add_argument(
        "--dataset-root",
        type=str,
        default="/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/cpbsd_gcn_single_setting_n5_normal_rho0_full_hvhm",
    )
    parser.add_argument(
        "--work-root",
        type=str,
        default="/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/cpbsd_q_pilot_then_full",
    )
    parser.add_argument(
        "--python-bin",
        type=str,
        default="/Users/sensen/.openclaw/workspace/domains/revenue-management/project-root/code_submission_project/code_submission/.venv/bin/python",
    )
    parser.add_argument("--pilot-total", type=int, default=50)
    parser.add_argument("--pilot-train", type=int, default=40)
    parser.add_argument("--pilot-eval", type=int, default=5)
    parser.add_argument("--pilot-test", type=int, default=5)
    parser.add_argument("--label-time-limit", type=float, default=300.0)
    parser.add_argument("--label-mip-gap", type=float, default=1e-2)
    parser.add_argument("--pilot-epochs", type=int, default=30)
    parser.add_argument("--pilot-batch-size", type=int, default=8)
    parser.add_argument("--pilot-hidden", type=int, default=64)
    parser.add_argument("--pilot-layers", type=int, default=2)
    parser.add_argument("--pilot-patience", type=int, default=10)
    args = parser.parse_args()

    if args.pilot_train + args.pilot_eval + args.pilot_test != args.pilot_total:
        raise ValueError("pilot_train + pilot_eval + pilot_test must equal pilot_total")

    dataset_root = Path(args.dataset_root)
    work_root = Path(args.work_root)
    work_root.mkdir(parents=True, exist_ok=True)

    train_rows = read_manifest(dataset_root / "train_manifest.csv")
    eval_rows = read_manifest(dataset_root / "eval_manifest.csv")
    test_rows = read_manifest(dataset_root / "test_manifest.csv")

    pilot_dir = work_root / "pilot"
    pilot_dir.mkdir(parents=True, exist_ok=True)
    pilot_train_manifest = pilot_dir / "pilot_train_manifest.csv"
    pilot_eval_manifest = pilot_dir / "pilot_eval_manifest.csv"
    pilot_test_manifest = pilot_dir / "pilot_test_manifest.csv"
    write_manifest(pilot_train_manifest, train_rows[: args.pilot_train])
    write_manifest(pilot_eval_manifest, eval_rows[: args.pilot_eval])
    write_manifest(pilot_test_manifest, test_rows[: args.pilot_test])

    label_script = SCRIPT_DIR / "label_cpbsd_milp_from_manifest.py"
    train_script = SCRIPT_DIR / "Training_multi_layer_cpbsd_q.py"

    pilot_label_root = pilot_dir / "labels"
    pilot_label_root.mkdir(parents=True, exist_ok=True)

    for split_name, manifest_path in [
        ("train", pilot_train_manifest),
        ("eval", pilot_eval_manifest),
        ("test", pilot_test_manifest),
    ]:
        split_out = pilot_label_root / split_name
        split_out.mkdir(parents=True, exist_ok=True)
        run_cmd(
            [
                args.python_bin,
                str(label_script),
                "--manifest",
                str(manifest_path),
                "--out-dir",
                str(split_out),
                "--time-limit",
                str(args.label_time_limit),
                "--mip-gap",
                str(args.label_mip_gap),
                "--output-flag",
                "0",
            ],
            SCRIPT_DIR,
        )

    pilot_train_results = pilot_label_root / "train" / f"{pilot_train_manifest.stem}__cpbsd_milp_results.csv"
    pilot_eval_results = pilot_label_root / "eval" / f"{pilot_eval_manifest.stem}__cpbsd_milp_results.csv"
    pilot_test_results = pilot_label_root / "test" / f"{pilot_test_manifest.stem}__cpbsd_milp_results.csv"

    pilot_model_dir = pilot_dir / "models"
    pilot_chart_dir = pilot_dir / "charts"
    pilot_log_dir = pilot_dir / "logs"
    run_cmd(
        [
            args.python_bin,
            str(train_script),
            "--train_manifest",
            str(pilot_train_results),
            "--eval_manifest",
            str(pilot_eval_results),
            "--test_manifest",
            str(pilot_test_results),
            "--model_dir",
            str(pilot_model_dir),
            "--charts_dir",
            str(pilot_chart_dir),
            "--log_dir",
            str(pilot_log_dir),
            "--epochs",
            str(args.pilot_epochs),
            "--batch_size",
            str(args.pilot_batch_size),
            "--hidden",
            str(args.pilot_hidden),
            "--num_layers",
            str(args.pilot_layers),
            "--patience",
            str(args.pilot_patience),
        ],
        SCRIPT_DIR,
    )

    metrics_path = pilot_model_dir / f"metrics_edge_cpbsd_q_{args.pilot_layers}layer_seed42.json"
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    history = metrics.get("metrics", [])
    split_metrics = metrics.get("split_metrics", {})
    eval_metrics = split_metrics.get("eval") or {}
    test_metrics = split_metrics.get("test") or {}

    first_train_loss = history[0]["train_loss"] if history else None
    last_train_loss = history[-1]["train_loss"] if history else None
    pilot_healthy = bool(
        history
        and first_train_loss is not None
        and last_train_loss is not None
        and last_train_loss <= first_train_loss
        and eval_metrics.get("loss") is not None
        and eval_metrics.get("loss") == eval_metrics.get("loss")
        and eval_metrics.get("pred_std", 0.0) > 1e-6
        and test_metrics.get("loss") is not None
        and test_metrics.get("loss") == test_metrics.get("loss")
    )

    pilot_summary = {
        "pilot_total": args.pilot_total,
        "pilot_train": args.pilot_train,
        "pilot_eval": args.pilot_eval,
        "pilot_test": args.pilot_test,
        "label_time_limit": args.label_time_limit,
        "pilot_healthy": pilot_healthy,
        "first_train_loss": first_train_loss,
        "last_train_loss": last_train_loss,
        "eval_metrics": eval_metrics,
        "test_metrics": test_metrics,
        "pilot_metrics_path": str(metrics_path),
    }
    (pilot_dir / "pilot_summary.json").write_text(json.dumps(pilot_summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(pilot_summary, ensure_ascii=False, indent=2))

    if not pilot_healthy:
        print("Pilot check failed. Stop before full labeling.")
        return

    full_label_root = work_root / "full_labels"
    full_label_root.mkdir(parents=True, exist_ok=True)
    for split_name, manifest_name in [
        ("train", "train_manifest.csv"),
        ("eval", "eval_manifest.csv"),
        ("test", "test_manifest.csv"),
    ]:
        split_out = full_label_root / split_name
        split_out.mkdir(parents=True, exist_ok=True)
        run_cmd(
            [
                args.python_bin,
                str(label_script),
                "--manifest",
                str(dataset_root / manifest_name),
                "--out-dir",
                str(split_out),
                "--time-limit",
                str(args.label_time_limit),
                "--mip-gap",
                str(args.label_mip_gap),
                "--output-flag",
                "0",
            ],
            SCRIPT_DIR,
        )


if __name__ == "__main__":
    main()
