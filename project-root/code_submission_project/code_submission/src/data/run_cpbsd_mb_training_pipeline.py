from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Sequence, Tuple


SCRIPT_DIR = Path(__file__).resolve().parent
TRAIN_SCRIPT = SCRIPT_DIR / "Training_multi_layer_cpbsd_mb_x.py"
MERGE_SCRIPT = SCRIPT_DIR / "merge_cpbsd_mb_chunk_results.py"


def _ensure_dirs(*paths: Path) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def _emit(message: str, log_paths: Sequence[Optional[Path]] = ()) -> None:
    print(message, flush=True)
    for log_path in log_paths:
        if log_path is None:
            continue
        with log_path.open("a", encoding="utf-8") as f:
            f.write(message)
            if not message.endswith("\n"):
                f.write("\n")


def _run(cmd: Sequence[str], cwd: Path, log_paths: Sequence[Optional[Path]] = ()) -> int:
    normalized_cmd = list(cmd)
    if normalized_cmd and normalized_cmd[0].endswith("python") and "-u" not in normalized_cmd[1:2]:
        normalized_cmd.insert(1, "-u")
    _emit(f"RUN: {shlex.join(normalized_cmd)}", log_paths)
    proc = subprocess.Popen(
        normalized_cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        _emit(line.rstrip("\n"), log_paths)
    proc.wait()
    _emit(f"RETURN CODE: {proc.returncode}", log_paths)
    return proc.returncode


def _attempt_plan(requested_device: str, batch_size: int) -> List[Tuple[str, int]]:
    if requested_device != "mps":
        return [(requested_device, batch_size)]

    attempts: List[Tuple[str, int]] = []
    for candidate in [batch_size, 16, 8]:
        if candidate <= 0:
            continue
        pair = ("mps", candidate)
        if pair not in attempts:
            attempts.append(pair)
    cpu_pair = ("cpu", min(8, batch_size) if batch_size > 0 else 8)
    if cpu_pair not in attempts:
        attempts.append(cpu_pair)
    return attempts


def _train_with_fallbacks(
    *,
    python_bin: str,
    workdir: Path,
    train_manifest: str,
    eval_manifest: str,
    test_manifest: str,
    model_dir: str,
    charts_dir: str,
    log_dir: str,
    device: str,
    epochs: int,
    batch_size: int,
    learning_rate: float,
    hidden_channels: int,
    num_layers: int,
    early_stopping_patience: int,
    seed: int,
    run_log_file: Optional[Path],
    smoke_log_file: Optional[Path] = None,
) -> None:
    attempts = _attempt_plan(device, batch_size)
    stage_log_paths: List[Optional[Path]] = [run_log_file]
    if smoke_log_file is not None:
        stage_log_paths.append(smoke_log_file)

    _emit(
        json.dumps(
            {
                "stage": "training",
                "requested_device": device,
                "attempts": [{"device": dev, "batch_size": bs} for dev, bs in attempts],
            },
            ensure_ascii=False,
        ),
        stage_log_paths,
    )

    last_returncode = 0
    for attempt_idx, (attempt_device, attempt_batch_size) in enumerate(attempts, 1):
        _emit(
            f"=== TRAIN ATTEMPT {attempt_idx}/{len(attempts)} "
            f"device={attempt_device} batch_size={attempt_batch_size} ===",
            stage_log_paths,
        )
        cmd = [
            python_bin,
            str(TRAIN_SCRIPT),
            "--train_manifest",
            train_manifest,
            "--eval_manifest",
            eval_manifest,
            "--test_manifest",
            test_manifest,
            "--model_dir",
            model_dir,
            "--charts_dir",
            charts_dir,
            "--log_dir",
            log_dir,
            "--device",
            attempt_device,
            "--epochs",
            str(epochs),
            "--batch_size",
            str(attempt_batch_size),
            "--learning_rate",
            str(learning_rate),
            "--hidden_channels",
            str(hidden_channels),
            "--num_layers",
            str(num_layers),
            "--early_stopping_patience",
            str(early_stopping_patience),
            "--seed",
            str(seed),
        ]
        returncode = _run(cmd, cwd=workdir, log_paths=stage_log_paths)
        last_returncode = returncode
        if returncode == 0:
            _emit(
                f"=== TRAIN SUCCEEDED device={attempt_device} batch_size={attempt_batch_size} ===",
                stage_log_paths,
            )
            return

        if attempt_idx < len(attempts):
            _emit(
                f"=== TRAIN FAILED device={attempt_device} batch_size={attempt_batch_size}; retrying ===",
                stage_log_paths,
            )

    raise SystemExit(f"Training failed after all fallback attempts. Last return code: {last_returncode}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run CPBSD MB training pipeline: merge manifests, smoke train, full train.")
    parser.add_argument("--python-bin", type=str, default=sys.executable)
    parser.add_argument(
        "--workdir",
        type=str,
        default="/Users/sensen/.openclaw/workspace/domains/revenue-management/project-root/code_submission_project/code_submission",
    )
    parser.add_argument(
        "--input-root",
        type=str,
        default="/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/cpbsd_mb_labels_chunked_run1",
    )
    parser.add_argument(
        "--output-root",
        type=str,
        default="/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/cpbsd_mb_labels_chunked_run1",
    )
    parser.add_argument(
        "--model-dir",
        type=str,
        default="/Users/sensen/.openclaw/workspace/domains/revenue-management/project-root/code_submission_project/code_submission/models_cpbsd_mb_x",
    )
    parser.add_argument(
        "--charts-dir",
        type=str,
        default="/Users/sensen/.openclaw/workspace/domains/revenue-management/project-root/code_submission_project/code_submission/charts_cpbsd_mb_x",
    )
    parser.add_argument(
        "--log-dir",
        type=str,
        default="/Users/sensen/.openclaw/workspace/domains/revenue-management/project-root/code_submission_project/code_submission/log_cpbsd_mb_x",
    )
    parser.add_argument("--smoke-limit", type=int, default=64)
    parser.add_argument("--device", type=str, default="mps", choices=["auto", "cuda", "mps", "cpu"])
    parser.add_argument("--epochs", type=int, default=200)
    parser.add_argument("--smoke-epochs", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--hidden-channels", type=int, default=128)
    parser.add_argument("--num-layers", type=int, default=2)
    parser.add_argument("--early-stopping-patience", type=int, default=30)
    parser.add_argument("--smoke-early-stopping-patience", type=int, default=5)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    workdir = Path(args.workdir)
    output_root = Path(args.output_root)
    model_dir = Path(args.model_dir)
    charts_dir = Path(args.charts_dir)
    log_dir = Path(args.log_dir)
    run_log_file = log_dir / "tmux_train_run.log"
    smoke_log_file = log_dir / "tmux_smoke_run.log"
    smoke_model_dir = model_dir / f"smoke{args.smoke_limit}"
    smoke_charts_dir = charts_dir / f"smoke{args.smoke_limit}"
    smoke_log_dir = log_dir / f"smoke{args.smoke_limit}"
    _ensure_dirs(model_dir, charts_dir, log_dir, smoke_model_dir, smoke_charts_dir, smoke_log_dir)
    for log_file in [run_log_file, smoke_log_file]:
        if log_file.exists():
            log_file.unlink()

    merge_cmd = [
        args.python_bin,
        str(MERGE_SCRIPT),
        "--input-root",
        args.input_root,
        "--output-root",
        args.output_root,
        "--smoke-limit",
        str(args.smoke_limit),
    ]
    _emit("=== STEP 1/3: MERGE MANIFESTS ===", [run_log_file])
    if _run(merge_cmd, cwd=workdir, log_paths=[run_log_file]) != 0:
        raise SystemExit("Merge step failed.")

    train_manifest = str(output_root / "train__mb_results_merged.csv")
    eval_manifest = str(output_root / "eval__mb_results_merged.csv")
    test_manifest = str(output_root / "test__mb_results_merged.csv")
    smoke_train_manifest = str(output_root / f"train__mb_results_merged_smoke{args.smoke_limit}.csv")
    smoke_eval_manifest = str(output_root / f"eval__mb_results_merged_smoke{args.smoke_limit}.csv")
    smoke_test_manifest = str(output_root / f"test__mb_results_merged_smoke{args.smoke_limit}.csv")

    _emit("=== STEP 2/3: SMOKE TRAINING ===", [run_log_file, smoke_log_file])
    _train_with_fallbacks(
        python_bin=args.python_bin,
        workdir=workdir,
        train_manifest=smoke_train_manifest,
        eval_manifest=smoke_eval_manifest,
        test_manifest=smoke_test_manifest,
        model_dir=str(smoke_model_dir),
        charts_dir=str(smoke_charts_dir),
        log_dir=str(smoke_log_dir),
        device=args.device,
        epochs=args.smoke_epochs,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        hidden_channels=args.hidden_channels,
        num_layers=args.num_layers,
        early_stopping_patience=args.smoke_early_stopping_patience,
        seed=args.seed,
        run_log_file=run_log_file,
        smoke_log_file=smoke_log_file,
    )

    _emit("=== STEP 3/3: FULL TRAINING ===", [run_log_file])
    _train_with_fallbacks(
        python_bin=args.python_bin,
        workdir=workdir,
        train_manifest=train_manifest,
        eval_manifest=eval_manifest,
        test_manifest=test_manifest,
        model_dir=str(model_dir),
        charts_dir=str(charts_dir),
        log_dir=str(log_dir),
        device=args.device,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        hidden_channels=args.hidden_channels,
        num_layers=args.num_layers,
        early_stopping_patience=args.early_stopping_patience,
        seed=args.seed,
        run_log_file=run_log_file,
    )

    _emit(
        json.dumps(
            {
                "status": "completed",
                "train_manifest": train_manifest,
                "eval_manifest": eval_manifest,
                "test_manifest": test_manifest,
                "smoke_model_dir": str(smoke_model_dir),
                "full_model_dir": str(model_dir),
                "charts_dir": str(charts_dir),
                "log_dir": str(log_dir),
                "run_log_file": str(run_log_file),
                "smoke_log_file": str(smoke_log_file),
            },
            ensure_ascii=False,
            indent=2,
        ),
        [run_log_file],
    )


if __name__ == "__main__":
    main()
