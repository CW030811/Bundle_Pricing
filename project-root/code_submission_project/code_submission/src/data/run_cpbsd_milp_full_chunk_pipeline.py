import argparse
import json
import subprocess
import sys
import time
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent


def run_cmd(cmd, cwd: Path):
    print("RUN:", " ".join(map(str, cmd)), flush=True)
    return subprocess.run(cmd, cwd=str(cwd), check=False)


def main():
    parser = argparse.ArgumentParser(description="Run the full CPBSD-MILP chunk labeling pipeline across train/eval/test.")
    parser.add_argument("--python-bin", required=True, type=str)
    parser.add_argument("--manifest-root", required=True, type=str)
    parser.add_argument("--out-root", required=True, type=str)
    parser.add_argument("--time-limit", type=float, default=300.0)
    parser.add_argument("--mip-gap", type=float, default=1e-2)
    parser.add_argument("--output-flag", type=int, default=0)
    args = parser.parse_args()

    out_root = Path(args.out_root)
    out_root.mkdir(parents=True, exist_ok=True)
    status_path = out_root / "full_pipeline_status.json"

    queue_script = SCRIPT_DIR / "run_cpbsd_milp_chunk_queue.py"
    plan = [("train", 1, 20), ("eval", 1, 3), ("test", 1, 3)]

    status = {
        "manifest_root": args.manifest_root,
        "out_root": args.out_root,
        "time_limit": args.time_limit,
        "mip_gap": args.mip_gap,
        "plan": [],
        "started_at": time.time(),
    }
    status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")

    for split, start, end in plan:
        phase_started = time.time()
        cmd = [
            args.python_bin,
            str(queue_script),
            "--python-bin",
            args.python_bin,
            "--manifest-root",
            args.manifest_root,
            "--out-root",
            args.out_root,
            "--split",
            split,
            "--start",
            str(start),
            "--end",
            str(end),
            "--time-limit",
            str(args.time_limit),
            "--mip-gap",
            str(args.mip_gap),
            "--output-flag",
            str(args.output_flag),
        ]
        proc = run_cmd(cmd, SCRIPT_DIR)
        phase = {
            "split": split,
            "start": start,
            "end": end,
            "returncode": proc.returncode,
            "elapsed": time.time() - phase_started,
        }
        status["plan"].append(phase)
        status["updated_at"] = time.time()
        status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"PHASE {split} finished with returncode={proc.returncode}", flush=True)
        if proc.returncode != 0:
            print("Stopping full pipeline due to phase failure.", flush=True)
            break

    status["finished_at"] = time.time()
    status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
