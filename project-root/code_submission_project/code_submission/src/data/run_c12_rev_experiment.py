"""
C12-rev experiment: compare 3 C12 variants on N=5 old instances.
  - bsp_ge_fcp (C12-rev): q_s >= max p_i for size-s bundles
  - fcp_le_bsp (C12-orig): p_i <= q_s
  - none (no C12)
"""
from __future__ import annotations
import json, sys, time
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import msgpack, msgpack_numpy as mnp
from eval_bsp_fcp_hybrid_oos import eval_hybrid_oos
from generate_data_CPBSD import sample_valuations, valuation_means
from solve_joint_fcp_bsp import solve_joint_fcp_bsp
from solve_mb_bsp_on_cpbsd_v2 import build_assortments, json_default

EXP = Path("/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments")


def load_instance(path):
    with open(path, "rb") as f:
        obj = msgpack.load(f, object_hook=mnp.decode, strict_map_key=False)
    return obj, np.asarray(obj["valuation_samples_V"], dtype=float), np.asarray(obj["production_cost_c"], dtype=float)


def oos_samples(setup, k_out=5000):
    rng = np.random.default_rng(int(setup["seed"]) + 99991)
    means = valuation_means(int(setup["n_products"]), setup["heterogeneity"])
    return sample_valuations(k=k_out, means=means, family=setup["dist_family"], rho=float(setup["rho"]), rng=rng)


def main():
    def fmt(v):
        return f"{v:.4f}" if v is not None else "N/A"

    n = 5
    costs = ["random_ind", "random_corr"]
    modes = [
        ("bsp_ge_fcp", "Joint-C12rev"),
        ("fcp_le_bsp", "Joint-C12orig"),
        ("none",       "Joint-noC12"),
    ]
    TL = 600.0; GAP = 1e-2
    all_rows = []

    for cost in costs:
        print(f"\n{'='*80}")
        print(f"N={n} / {cost}")
        print(f"{'='*80}")

        inst_dir = EXP / f"fcp_random_cost_eval_n{n}_{cost}/instances"
        paths = sorted(inst_dir.glob("*.msgpack"))

        ass = build_assortments(n)

        for idx, ip in enumerate(paths):
            obj, v_kn, c_n = load_instance(ip)
            setup = obj["setup"]
            name = ip.stem
            print(f"\n  [{idx+1}/{len(paths)}] {name}  seed={setup['seed']}")

            v_out = oos_samples(setup)
            base = {"N": n, "cost": cost, "instance_id": name, "seed": int(setup["seed"])}

            for cross_mode, label in modes:
                t0 = time.time()
                res = solve_joint_fcp_bsp(
                    v_kn, c_n, ass,
                    time_limit=TL, mip_gap=GAP, output_flag=0,
                    cross_mode=cross_mode,
                )
                t1 = time.time()

                oos = None
                if res["feasible"] and res["bundle_prices_full"] and res["size_prices"]:
                    oos = eval_hybrid_oos(
                        v_out, c_n, res["bundle_prices_full"],
                        np.asarray(res["assortments"], dtype=int), res["size_prices"],
                    )["hybrid_oos"]

                row = {
                    **base, "method": label, "cross_mode": cross_mode,
                    "in_sample": res.get("objective"), "oos": oos,
                    "runtime": t1 - t0, "choice": res.get("choice_summary"),
                    "size_prices": res.get("size_prices"),
                }
                all_rows.append(row)
                print(f"    {label:20s}  InS={fmt(res.get('objective'))}  OOS={fmt(oos)}  RT={t1-t0:.1f}s  {res.get('choice_summary')}")

    # Save
    out_path = EXP / "c12_rev_experiment_n5.json"
    with open(out_path, "w") as f:
        json.dump(all_rows, f, indent=2, default=json_default)
    print(f"\nSaved {len(all_rows)} rows to {out_path}")


if __name__ == "__main__":
    main()
