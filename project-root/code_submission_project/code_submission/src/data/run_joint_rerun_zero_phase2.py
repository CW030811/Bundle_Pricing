"""
Re-run Joint on phase2 zero-cost instances (N=10, N=30) to match 060426 baselines.
Also re-compute BSP/FCP/CPBSD-A OOS for full apple-to-apple comparison.
"""
from __future__ import annotations
import json, sys, time
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import msgpack, msgpack_numpy as mnp
from generate_data_CPBSD import sample_valuations, valuation_means
from eval_bsp_fcp_hybrid_oos import eval_hybrid_oos
from solve_joint_fcp_bsp import solve_joint_fcp_bsp
from solve_mb_bsp_on_cpbsd_v2 import (
    eval_bsp_policy, eval_mb_policy, normalize_numeric_keys, json_default,
)
from solve_cpbsd_a import solve_cpbsd_a
from run_cpbsd_fcp_pruned_mb_compare import evaluate_revenue

EXP = Path("/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments")
TL = 600.0
GAP = 1e-2


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

    all_rows = []

    for n in [10, 30]:
        print(f"\n{'='*80}")
        print(f"N={n} / zero (phase2 instances)")
        print(f"{'='*80}")

        phase2_dir = EXP / f"fcp_mb_phase2_selected_n10_n30_5inst/n{n}/normal_rho0.0_full_zero/runs"
        seed_dirs = sorted(phase2_dir.iterdir())

        for idx, seed_dir in enumerate(seed_dirs):
            inst_file = list(seed_dir.glob("instances/*.msgpack"))[0]
            obj, v_kn, c_n = load_instance(inst_file)
            setup = obj["setup"]
            name = inst_file.stem
            print(f"\n  [{idx+1}/{len(seed_dirs)}] {seed_dir.name}  seed={setup['seed']}")

            v_out = oos_samples(setup)
            base = {"N": n, "cost": "zero", "seed_dir": seed_dir.name, "seed": int(setup["seed"])}

            # --- Load existing BSP result ---
            bsp_files = list(seed_dir.glob("results/*__bsp.json"))
            bsp_oos = None
            bsp_ins = None
            if bsp_files:
                bsp_data = json.loads(bsp_files[0].read_text())
                if bsp_data.get("feasible"):
                    bsp_oos = eval_bsp_policy(v_out, c_n, bsp_data["size_prices"])
                    bsp_ins = bsp_data.get("objective")
            all_rows.append({**base, "method": "BSP", "in_sample": bsp_ins, "oos": bsp_oos})
            print(f"    BSP:              InS={fmt(bsp_ins)}  OOS={fmt(bsp_oos)}")

            # --- Load existing FCP result ---
            fcp_files = list(seed_dir.glob("results/*__fcp_pruned_mb.json"))
            fcp_oos = None
            fcp_ins = None
            ass = None
            if fcp_files:
                fcp_data = json.loads(fcp_files[0].read_text())
                ass = np.array(fcp_data["assortments"], dtype=int)
                bp = fcp_data.get("bundle_prices_full") or fcp_data.get("bundle_prices") or {}
                if fcp_data.get("feasible") and bp:
                    fcp_oos = eval_mb_policy(v_out, c_n, bp, ass)
                    fcp_ins = fcp_data.get("objective")
            all_rows.append({**base, "method": "FCP", "in_sample": fcp_ins, "oos": fcp_oos})
            print(f"    FCP:              InS={fmt(fcp_ins)}  OOS={fmt(fcp_oos)}")

            # --- Load existing CPBSD-A result ---
            cpbsd_files = list(seed_dir.glob("results/*__cpbsd_a.json"))
            cpbsd_oos = None
            cpbsd_ins = None
            if cpbsd_files:
                cpbsd_data = json.loads(cpbsd_files[0].read_text())
                if cpbsd_data.get("sol_count", 0) > 0:
                    p_vec = np.array(cpbsd_data.get("p", []), dtype=float)
                    d_vec = np.array(cpbsd_data.get("d", []), dtype=float)
                    if len(p_vec) > 0:
                        cpbsd_oos = evaluate_revenue(v_out, c_n, p_vec, d_vec)
                        cpbsd_ins = cpbsd_data.get("objective")
            all_rows.append({**base, "method": "CPBSD-A", "in_sample": cpbsd_ins, "oos": cpbsd_oos})
            print(f"    CPBSD-A:          InS={fmt(cpbsd_ins)}  OOS={fmt(cpbsd_oos)}")

            # --- Joint (C12-rev) ---
            if ass is None:
                print(f"    !! No assortments, skipping Joint")
                continue

            for cross_mode, label in [("bsp_ge_fcp", "Joint"), ("none", "Joint-noC12")]:
                t0 = time.time()
                j = solve_joint_fcp_bsp(
                    v_kn, c_n, ass,
                    time_limit=TL, mip_gap=GAP, output_flag=0,
                    cross_mode=cross_mode,
                )
                t1 = time.time()

                j_oos = None
                if j["feasible"] and j["bundle_prices_full"] and j["size_prices"]:
                    j_oos = eval_hybrid_oos(
                        v_out, c_n, j["bundle_prices_full"],
                        np.asarray(j["assortments"], dtype=int), j["size_prices"],
                    )["hybrid_oos"]

                all_rows.append({
                    **base, "method": label, "cross_mode": cross_mode,
                    "in_sample": j.get("objective"), "oos": j_oos,
                    "runtime": t1 - t0, "choice": j.get("choice_summary"),
                })
                print(f"    {label:18s}InS={fmt(j.get('objective'))}  OOS={fmt(j_oos)}  RT={t1-t0:.1f}s  {j.get('choice_summary')}")

    # Save
    out_path = EXP / "joint_rerun_zero_phase2.json"
    with open(out_path, "w") as f:
        json.dump(all_rows, f, indent=2, default=json_default)
    print(f"\nSaved {len(all_rows)} rows to {out_path}")

    # Print summary
    from collections import defaultdict
    agg = defaultdict(lambda: defaultdict(list))
    for r in all_rows:
        key = (r["N"], r["method"])
        if r["oos"] is not None:
            agg[key]["oos"].append(r["oos"])
        if r["in_sample"] is not None:
            agg[key]["ins"].append(r["in_sample"])

    print(f"\n{'='*80}")
    print("ZERO-COST AVERAGES (phase2 instances, 5-seed)")
    print(f"{'='*80}")
    for n in [10, 30]:
        for m in ["BSP", "CPBSD-A", "FCP", "Joint", "Joint-noC12"]:
            key = (n, m)
            if key in agg and agg[key]["oos"]:
                ins_avg = np.mean(agg[key]["ins"]) if agg[key]["ins"] else None
                oos_avg = np.mean(agg[key]["oos"])
                print(f"  N={n:2d} {m:16s} InS={fmt(ins_avg)}  OOS={oos_avg:.4f}  (#={len(agg[key]['oos'])})")
        print()


if __name__ == "__main__":
    main()
