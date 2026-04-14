import argparse
import csv
import json
import math
from pathlib import Path


def read_manifest(path: Path):
    with path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_manifest(path: Path, rows):
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def chunk_rows(rows, chunk_size):
    for start in range(0, len(rows), chunk_size):
        yield rows[start : start + chunk_size]


def main():
    parser = argparse.ArgumentParser(description="Split CPBSD dataset manifests into fixed-size chunk manifests.")
    parser.add_argument(
        "--dataset-root",
        type=str,
        default="/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/cpbsd_gcn_single_setting_n5_normal_rho0_full_hvhm",
    )
    parser.add_argument(
        "--out-root",
        type=str,
        default="/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/cpbsd_gcn_single_setting_n5_normal_rho0_full_hvhm_chunked_manifests",
    )
    parser.add_argument("--chunk-size", type=int, default=200)
    args = parser.parse_args()

    dataset_root = Path(args.dataset_root)
    out_root = Path(args.out_root)
    out_root.mkdir(parents=True, exist_ok=True)

    summary = {"dataset_root": str(dataset_root), "out_root": str(out_root), "chunk_size": args.chunk_size, "splits": {}}

    for split in ["train", "eval", "test"]:
        manifest_path = dataset_root / f"{split}_manifest.csv"
        rows = read_manifest(manifest_path)
        split_dir = out_root / split
        split_dir.mkdir(parents=True, exist_ok=True)

        split_entries = []
        for idx, chunk in enumerate(chunk_rows(rows, args.chunk_size), 1):
            chunk_name = f"{split}_chunk_{idx:03d}.csv"
            chunk_path = split_dir / chunk_name
            write_manifest(chunk_path, chunk)
            split_entries.append(
                {
                    "chunk_index": idx,
                    "chunk_name": chunk_name,
                    "chunk_path": str(chunk_path),
                    "count": len(chunk),
                    "first_instance": chunk[0]["filename"],
                    "last_instance": chunk[-1]["filename"],
                }
            )

        summary["splits"][split] = {
            "count_total": len(rows),
            "num_chunks": math.ceil(len(rows) / args.chunk_size),
            "chunks": split_entries,
        }

    (out_root / "chunk_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
