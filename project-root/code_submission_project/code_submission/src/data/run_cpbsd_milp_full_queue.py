import argparse
import json
import subprocess
import sys
import time
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent


def discover_chunk_range(manifest_root: Path, split: str) -> tuple[int, int]:
    split_dir = manifest_root / split
    paths = sorted(split_dir.glob(f"{split}_chunk_*.csv"))
    if not paths:
        raise FileNotFoundError(f"No chunk manifests found for split={split} under {split_dir}")
    indices = [int(path.stem.split("_")[-1]) for path in paths]
    return min(indices), max(indices)


def main():
    parser = argparse.ArgumentParser(description="Run full CPBSD-MILP labeling queue across train/eval/test splits.")
    parser.add_argument("--python-bin", required=True, type=str)
    parser.add_argument("--manifest-root", required=True, type=str)
    parser.add_argument("--out-root", required=True, type=str)
    parser.add_argument("--time-limit", type=float, default=300.0)
    parser.add_argument("--mip-gap", type=float, default=1e-2)
    parser.add_argument("--output-flag", type=int, default=0)
    parser.add_argument(
        "--splits",
        nargs="+",
        default=["train", "eval", "test"],
        help="Split execution order.",
    )
    args = parser.parse_args()

    manifest_root = Path(args.manifest_root)
    out_root = Path(args.out_root)
    out_root.mkdir(parents=True, exist_ok=True)
    queue_script = SCRIPT_DIR / "run_cpbsd_milp_chunk_queue.py"
    status_path = out_root / "full_queue_status.json"

    status = {
        "manifest_root": str(manifest_root),
        "out_root": str(out_root),
        "python_bin": args.python_bin,
        "time_limit": args.time_limit,
        "mip_gap": args.mip_gap,
        "output_flag": args.output_flag,
        "splits": [],
        "started_at": time.time(),
    }
    status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")

    for split in args.splits:
        start_idx, end_idx = discover_chunk_range(manifest_root, split)
        split_started = time.time()
        cmd = [
            args.python_bin,
            str(queue_script),
            "--python-bin",
            args.python_bin,
            "--manifest-root",
            str(manifest_root),
            "--out-root",
            str(out_root),
            "--split",
            split,
            "--start",
            str(start_idx),
            "--end",
            str(end_idx),
            "--time-limit",
            str(args.time_limit),
            "--mip-gap",
            str(args.mip_gap),
            "--output-flag",
            str(args.output_flag),
        ]

        print(f"=== START SPLIT {split} chunks {start_idx}-{end_idx} ===", flush=True)
        print("RUN:", " ".join(cmd), flush=True)
        proc = subprocess.run(cmd, cwd=str(SCRIPT_DIR), check=False)

        split_entry = {
            "split": split,
            "start": start_idx,
            "end": end_idx,
            "returncode": proc.returncode,
            "elapsed": time.time() - split_started,
        }
        split_status_path = out_root / f"{split}_queue_status.json"
        if split_status_path.exists():
            try:
                split_entry["status_path"] = str(split_status_path)
                split_entry["status"] = json.loads(split_status_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        status["splits"].append(split_entry)
        status["updated_at"] = time.time()
        status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"=== END SPLIT {split} returncode={proc.returncode} elapsed={split_entry['elapsed']:.1f}s ===", flush=True)

        if proc.returncode != 0:
            print("Full queue stopped due to split failure.", flush=True)
            break

    status["finished_at"] = time.time()
    status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
