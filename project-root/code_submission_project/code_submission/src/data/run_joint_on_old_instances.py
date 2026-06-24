"""
Run Joint FCP+BSP (with/without C12) on OLD seed=20260424 instances
to replace post-hoc hybrid results in 060426_Report.

Covers: N=5/10/30 × random_ind/random_corr × 5 instances.
For N=5: full 2^5 assortments.
For N=10/30: GCN-pruned assortments from existing FCP result JSONs.
"""

from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import msgpack
import msgpack_numpy as mnp

from eval_bsp_fcp_hybrid_oos import eval_hybrid_oos
from generate_data_CPBSD import sample_valuations, valuation_means
from solve_joint_fcp_bsp import solve_joint_fcp_bsp
from solve_mb_bsp_on_cpbsd_v2 import build_assortments, json_default

EXP_BASE = Path("/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments")


def load_instance(path: Path):
    with open(path, "rb") as f:
        obj = msgpack.load(f, object_hook=mnp.decode, strict_map_key=False)
    return obj, np.asarray(obj["valuation_samples_V"], dtype=float), np.asarray(obj["production_cost_c"], dtype=float)


def oos_samples(setup: dict, k_out: int = 5000):
    rng = np.random.default_rng(int(setup["seed"]) + 99991)
    means = valuation_means(int(setup["n_products"]), setup["heterogeneity"])
    return sample_valuations(k=k_out, means=means, family=setup["dist_family"], rho=float(setup["rho"]), rng=rng)


def get_assortments(n: int, cost: str, inst_name: str) -> np.ndarray:
    """For N=5, full 2^5. For N=10/30, load from FCP result JSON."""
    if n == 5:
        return build_assortments(5)

    result_dir = EXP_BASE / f"fcp_random_cost_eval_n{n}_{cost}/results"
    fcp_file = result_dir / f"{inst_name}__fcp_pruned_mb.json"
    if not fcp_file.exists():
        raise FileNotFoundError(f"No FCP result for assortments: {fcp_file}")
    data = json.loads(fcp_file.read_text())
    return np.array(data["assortments"], dtype=int)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--time-limit", type=float, default=600.0)
    parser.add_argument("--mip-gap", type=float, default=1e-2)
    args = parser.parse_args()

    setups = [
        (5, "random_ind"),
        (5, "random_corr"),
        (10, "random_ind"),
        (10, "random_corr"),
        (30, "random_ind"),
        (30, "random_corr"),
    ]

    all_rows = []

    for n, cost in setups:
        header = f"N={n} / {cost}"
        print(f"\n{'='*70}")
        print(header)
        print(f"{'='*70}")

        inst_dir = EXP_BASE / f"fcp_random_cost_eval_n{n}_{cost}/instances"
        instance_paths = sorted(inst_dir.glob("*.msgpack"))

        for inst_idx, inst_path in enumerate(instance_paths):
            obj, v_kn, c_n = load_instance(inst_path)
            setup = obj["setup"]
            inst_name = inst_path.stem
            print(f"\n  Instance {inst_idx+1}/{len(instance_paths)}: {inst_name}")

            assortments = get_assortments(n, cost, inst_name)
            v_out = oos_samples(setup)

            row_base = {"N": n, "cost": cost, "instance_id": inst_name, "seed": int(setup["seed"])}

            for cross_mode, label in [("fcp_le_bsp", "Joint-FCP-BSP"), ("none", "Joint-FCP-BSP-noC12")]:
                t0 = time.time()
                res = solve_joint_fcp_bsp(
                    v_kn, c_n, assortments,
                    time_limit=args.time_limit, mip_gap=args.mip_gap,
                    output_flag=0,
                    cross_mode=cross_mode,
                )
                t1 = time.time()

                oos = None
                if res["feasible"] and res["bundle_prices_full"] and res["size_prices"]:
                    hybrid = eval_hybrid_oos(
                        v_out, c_n,
                        res["bundle_prices_full"],
                        np.asarray(res["assortments"], dtype=int),
                        res["size_prices"],
                    )
                    oos = hybrid["hybrid_oos"]

                all_rows.append({
                    **row_base,
                    "method": label,
                    "in_sample": res.get("objective"),
                    "oos": oos,
                    "runtime": t1 - t0,
                    "choice_summary": res.get("choice_summary"),
                    "n_bundles": res.get("bundle_count"),
                    "n_binvars": res.get("model_num_binvars"),
                })

                ins_s = f"{res['objective']:.4f}" if res.get("objective") is not None else "N/A"
                oos_s = f"{oos:.4f}" if oos is not None else "N/A"
                cs = res.get("choice_summary", {})
                print(f"    {label:25s}: InS={ins_s}  OOS={oos_s}  RT={t1-t0:.1f}s  bundles={res.get('bundle_count')}  {cs}")

    # --- Summary tables by (N, cost) ---
    print(f"\n{'='*90}")
    print("SUMMARY TABLES")
    print(f"{'='*90}")

    by_setup = defaultdict(lambda: defaultdict(list))
    for r in all_rows:
        key = (r["N"], r["cost"])
        by_setup[key][r["method"]].append(r)

    for (n, cost), methods_data in sorted(by_setup.items()):
        print(f"\n### N={n} / {cost}")
        print(f"{'Method':<28} {'InS':>8} {'OOS':>8} {'Runtime':>8}")
        print("-" * 56)
        for method in ["Joint-FCP-BSP", "Joint-FCP-BSP-noC12"]:
            rows = methods_data.get(method, [])
            if rows:
                ins_vals = [r["in_sample"] for r in rows if r["in_sample"] is not None]
                oos_vals = [r["oos"] for r in rows if r["oos"] is not None]
                rt_vals = [r["runtime"] for r in rows if r["runtime"] is not None]
                avg_ins = np.mean(ins_vals) if ins_vals else float("nan")
                avg_oos = np.mean(oos_vals) if oos_vals else float("nan")
                avg_rt = np.mean(rt_vals) if rt_vals else float("nan")
                print(f"{method:<28} {avg_ins:>8.2f} {avg_oos:>8.2f} {avg_rt:>7.1f}s")

    # Save
    out_path = EXP_BASE / "joint_fcp_bsp_on_old_instances.json"
    out_path.write_text(json.dumps(all_rows, indent=2, ensure_ascii=False, default=json_default), encoding="utf-8")
    print(f"\nResults saved to: {out_path}")


if __name__ == "__main__":
    main()
