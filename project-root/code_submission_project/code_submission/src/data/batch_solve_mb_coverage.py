#!/usr/bin/env python3
"""
Batch-solve all CPBSD N=5 instances with the latest MB solver (v2)
and save results for bundle coverage analysis.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from solve_mb_bsp_on_cpbsd_v2 import load_instance, solve_mb, json_default

INSTANCE_DIR = Path("/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/cpbsd_main_n5/instances/n5")
OUTPUT_DIR = Path("/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/mb_bundle_coverage_v2/results")

# Only solve instance_001 with exponential distribution (27 parameter combos)
INSTANCE_GLOB = "cpbsd_instance_001_N5_K50_exponential_*.msgpack"


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    instances = sorted(INSTANCE_DIR.glob(INSTANCE_GLOB))
    print(f"Found {len(instances)} instance files")

    total_t0 = time.time()
    success = 0
    failed = 0

    for i, inst_path in enumerate(instances, 1):
        stem = inst_path.stem
        out_name = f"{stem}__mb.json"
        out_path = OUTPUT_DIR / out_name

        if out_path.exists():
            print(f"[{i}/{len(instances)}] SKIP (exists): {out_name}")
            success += 1
            continue

        print(f"[{i}/{len(instances)}] Solving: {stem} ...", end=" ", flush=True)
        t0 = time.time()

        try:
            v, c = load_instance(inst_path)
            res = solve_mb(v, c, time_limit=300.0, mip_gap=1e-2, output_flag=0)
            t1 = time.time()

            text = json.dumps(res, ensure_ascii=False, indent=2, default=json_default)
            out_path.write_text(text, encoding="utf-8")

            status = "OK" if res["feasible"] else "INFEASIBLE"
            obj = res.get("objective", "N/A")
            print(f"{status} in {t1-t0:.1f}s  obj={obj}")
            success += 1
        except Exception as e:
            t1 = time.time()
            print(f"FAILED in {t1-t0:.1f}s: {e}")
            failed += 1

    total_t1 = time.time()
    print(f"\nDone: {success} success, {failed} failed, total {total_t1-total_t0:.1f}s")


if __name__ == "__main__":
    main()
