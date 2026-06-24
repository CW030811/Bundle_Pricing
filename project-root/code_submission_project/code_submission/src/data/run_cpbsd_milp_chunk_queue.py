import argparse
import json
import subprocess
import sys
import time
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent


def chunk_manifest_paths(manifest_dir: Path, split: str, start: int, end: int):
    split_dir = manifest_dir / split
    paths = sorted(split_dir.glob(f"{split}_chunk_*.csv"))
    selected = []
    for path in paths:
        idx = int(path.stem.split("_")[-1])
        if idx < start:
            continue
        if end > 0 and idx > end:
            continue
        selected.append((idx, path))
    return selected


def main():
    parser = argparse.ArgumentParser(description="Run CPBSD-MILP labeling chunk by chunk.")
    parser.add_argument("--python-bin", required=True, type=str)
    parser.add_argument("--manifest-root", required=True, type=str)
    parser.add_argument("--out-root", required=True, type=str)
    parser.add_argument("--split", type=str, default="train")
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=0, help="0 means all remaining chunks")
    parser.add_argument("--time-limit", type=float, default=300.0)
    parser.add_argument("--mip-gap", type=float, default=1e-2)
    parser.add_argument("--output-flag", type=int, default=0)
    args = parser.parse_args()

    manifest_root = Path(args.manifest_root)
    out_root = Path(args.out_root)
    out_root.mkdir(parents=True, exist_ok=True)
    status_path = out_root / f"{args.split}_queue_status.json"

    label_script = SCRIPT_DIR / "label_cpbsd_milp_from_manifest.py"
    chunks = chunk_manifest_paths(manifest_root, args.split, args.start, args.end)
    if not chunks:
        raise FileNotFoundError(f"No chunk manifests found for split={args.split}, start={args.start}, end={args.end}")

    status = {
        "split": args.split,
        "start": args.start,
        "end": args.end,
        "time_limit": args.time_limit,
        "mip_gap": args.mip_gap,
        "chunks": [],
        "started_at": time.time(),
    }
    status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")

    for idx, manifest_path in chunks:
        chunk_name = manifest_path.stem
        chunk_out_dir = out_root / args.split / chunk_name
        chunk_out_dir.mkdir(parents=True, exist_ok=True)

        chunk_started = time.time()
        cmd = [
            args.python_bin,
            str(label_script),
            "--manifest",
            str(manifest_path),
            "--out-dir",
            str(chunk_out_dir),
            "--time-limit",
            str(args.time_limit),
            "--mip-gap",
            str(args.mip_gap),
            "--output-flag",
            str(args.output_flag),
        ]
        print(f"=== START {chunk_name} ===", flush=True)
        print("RUN:", " ".join(cmd), flush=True)
        proc = subprocess.run(cmd, cwd=str(SCRIPT_DIR), check=False)
        chunk_entry = {
            "chunk_index": idx,
            "chunk_name": chunk_name,
            "manifest_path": str(manifest_path),
            "out_dir": str(chunk_out_dir),
            "returncode": proc.returncode,
            "elapsed": time.time() - chunk_started,
        }
        summary_path = chunk_out_dir / f"{manifest_path.stem}__cpbsd_milp_summary.json"
        if summary_path.exists():
            try:
                chunk_entry["summary"] = json.loads(summary_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        status["chunks"].append(chunk_entry)
        status["updated_at"] = time.time()
        status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"=== END {chunk_name} returncode={proc.returncode} elapsed={chunk_entry['elapsed']:.1f}s ===", flush=True)
        if proc.returncode != 0:
            print("Queue stopped due to chunk failure.", flush=True)
            break

    status["finished_at"] = time.time()
    status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
