from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Dict, List


def _chunk_sort_key(path: Path) -> int:
    try:
        return int(path.parent.name.split("_")[-1])
    except (IndexError, ValueError):
        return 0


def _index_sort_key(row: Dict[str, str]) -> tuple[int, str]:
    try:
        index_in_split = int(row.get("index_in_split", "0"))
    except ValueError:
        index_in_split = 0
    return index_in_split, row.get("filename", "")


def _read_rows(path: Path) -> List[Dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _write_rows(path: Path, rows: List[Dict[str, str]], fieldnames: List[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def merge_split(input_root: Path, output_root: Path, split: str, smoke_limit: int) -> Dict[str, object]:
    chunk_files = sorted(
        input_root.glob(f"{split}/{split}_chunk_*/{split}_chunk_*__mb_results.csv"),
        key=_chunk_sort_key,
    )
    if not chunk_files:
        raise FileNotFoundError(f"No chunk result CSVs found for split={split} under {input_root}")

    merged_rows: List[Dict[str, str]] = []
    fieldnames: List[str] | None = None
    seen_result_paths = set()
    missing_paths: List[str] = []

    for chunk_file in chunk_files:
        rows = _read_rows(chunk_file)
        if not rows:
            continue
        row_fieldnames = list(rows[0].keys())
        if fieldnames is None:
            fieldnames = row_fieldnames
        elif row_fieldnames != fieldnames:
            raise ValueError(f"Field mismatch in {chunk_file}: {row_fieldnames} != {fieldnames}")

        for row in rows:
            result_path = row.get("result_path", "")
            instance_path = row.get("instance_path", "")
            if result_path in seen_result_paths:
                raise ValueError(f"Duplicate result_path detected: {result_path}")
            seen_result_paths.add(result_path)

            if not Path(instance_path).exists():
                missing_paths.append(instance_path)
            if not Path(result_path).exists():
                missing_paths.append(result_path)
            merged_rows.append(row)

    if missing_paths:
        preview = ", ".join(missing_paths[:5])
        raise FileNotFoundError(f"Found missing instance/result paths for split={split}: {preview}")
    if fieldnames is None:
        raise RuntimeError(f"No rows loaded for split={split}")

    merged_rows.sort(key=_index_sort_key)

    merged_path = output_root / f"{split}__mb_results_merged.csv"
    smoke_path = output_root / f"{split}__mb_results_merged_smoke{smoke_limit}.csv"
    _write_rows(merged_path, merged_rows, fieldnames)
    _write_rows(smoke_path, merged_rows[:smoke_limit], fieldnames)

    has_solution_count = sum(str(row.get("has_solution", "")).lower() in {"true", "1"} for row in merged_rows)
    smoke_has_solution_count = sum(
        str(row.get("has_solution", "")).lower() in {"true", "1"} for row in merged_rows[:smoke_limit]
    )
    summary = {
        "split": split,
        "chunk_files": len(chunk_files),
        "merged_rows": len(merged_rows),
        "has_solution_count": has_solution_count,
        "merged_path": str(merged_path),
        "smoke_rows": min(smoke_limit, len(merged_rows)),
        "smoke_has_solution_count": smoke_has_solution_count,
        "smoke_path": str(smoke_path),
    }
    print(json.dumps(summary, ensure_ascii=False))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge chunk-level CPBSD MB result manifests into split-level manifests.")
    parser.add_argument(
        "--input-root",
        type=str,
        required=True,
        help="Root directory containing train/eval/test chunk result directories.",
    )
    parser.add_argument(
        "--output-root",
        type=str,
        required=True,
        help="Directory to write merged manifests to.",
    )
    parser.add_argument("--splits", nargs="+", default=["train", "eval", "test"])
    parser.add_argument("--smoke-limit", type=int, default=64)
    args = parser.parse_args()

    input_root = Path(args.input_root)
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    summaries = [merge_split(input_root, output_root, split, args.smoke_limit) for split in args.splits]
    print(json.dumps({"summaries": summaries}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
