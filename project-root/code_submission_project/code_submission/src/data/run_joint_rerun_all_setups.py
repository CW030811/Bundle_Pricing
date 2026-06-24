"""
Re-run Joint FCP+BSP with latest formulation (C12-rev, pairwise C9) across all 9 setups.
Reuse existing BSP/FCP/CPBSD-A baselines from previous runs; only Joint is freshly solved.

Output: experiments/joint_rerun_all_setups.json
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

# ── Setup definitions ────────────────────────────────────────────────
SETUPS = [
    # (N, cost_label, inst_dir, result_dir_for_assortments)
    # N=5: full 2^5 assortments, no GCN pruning needed
    (5,  "zero",        EXP / "joint_fcp_bsp_n5/instances_zero",                              None),
    (5,  "random_ind",  EXP / "fcp_random_cost_eval_n5_random_ind/instances",                  None),
    (5,  "random_corr", EXP / "fcp_random_cost_eval_n5_random_corr/instances",                 None),
    # N=10: need GCN-pruned assortments
    (10, "zero",        EXP / "cpbsd_single_setting_mb_ref_normal_rho0.0_full_zero/instances/n10",
                        EXP / "cpbsd_single_setting_mb_ref_normal_rho0.0_full_zero/results/n10"),
    (10, "random_ind",  EXP / "fcp_random_cost_eval_n10_random_ind/instances",
                        EXP / "fcp_random_cost_eval_n10_random_ind/results"),
    (10, "random_corr", EXP / "fcp_random_cost_eval_n10_random_corr/instances",
                        EXP / "fcp_random_cost_eval_n10_random_corr/results"),
    # N=30: need GCN-pruned assortments
    (30, "zero",        EXP / "cpbsd_single_setting_mb_ref_normal_rho0.0_full_zero/instances/n30",
                        EXP / "cpbsd_single_setting_mb_ref_normal_rho0.0_full_zero/results/n30"),
    (30, "random_ind",  EXP / "fcp_random_cost_eval_n30_random_ind/instances",
                        EXP / "fcp_random_cost_eval_n30_random_ind/results"),
    (30, "random_corr", EXP / "fcp_random_cost_eval_n30_random_corr/instances",
                        EXP / "fcp_random_cost_eval_n30_random_corr/results"),
]


def load_instance(path):
    with open(path, "rb") as f:
        obj = msgpack.load(f, object_hook=mnp.decode, strict_map_key=False)
    return obj, np.asarray(obj["valuation_samples_V"], dtype=float), np.asarray(obj["production_cost_c"], dtype=float)


def oos_samples(setup, k_out=5000):
    rng = np.random.default_rng(int(setup["seed"]) + 99991)
    means = valuation_means(int(setup["n_products"]), setup["heterogeneity"])
    return sample_valuations(k=k_out, means=means, family=setup["dist_family"], rho=float(setup["rho"]), rng=rng)


def get_assortments(n, inst_name, result_dir):
    """Return assortments: full 2^N for N<=5, GCN-pruned from FCP result for N>5."""
    if n <= 5:
        return build_assortments(n)
    # Look up FCP pruned result for GCN assortments
    # Try naming conventions: {inst_name}__fcp_pruned_mb.json or n{N}_inst{NNN}__fcp_pruned_mb.json
    candidates = [
        result_dir / f"{inst_name}__fcp_pruned_mb.json",
    ]
    # For zero-cost, naming is like "n10_inst001__fcp_pruned_mb.json"
    # Extract instance number from name
    import re
    m = re.search(r'instance_(\d+)', inst_name)
    if m:
        inst_num = m.group(1)
        candidates.append(result_dir / f"n{n}_inst{inst_num}__fcp_pruned_mb.json")

    for cand in candidates:
        if cand.exists():
            data = json.loads(cand.read_text())
            return np.array(data["assortments"], dtype=int)

    raise FileNotFoundError(f"No FCP pruned assortments found for {inst_name} in {result_dir}. Tried: {candidates}")


def main():
    def fmt(v):
        return f"{v:.4f}" if v is not None else "N/A"

    TL = 600.0
    GAP = 1e-2
    all_rows = []

    # Joint cross_mode: use C12-rev (bsp_ge_fcp) as the standard
    cross_mode = "bsp_ge_fcp"

    for n, cost, inst_dir, result_dir in SETUPS:
        print(f"\n{'='*80}")
        print(f"N={n} / {cost}")
        print(f"{'='*80}")

        if not inst_dir.exists():
            print(f"  !! Instance dir not found: {inst_dir}")
            continue

        paths = sorted(inst_dir.glob("*.msgpack"))
        if not paths:
            print(f"  !! No instances found in {inst_dir}")
            continue

        print(f"  Found {len(paths)} instances")

        for idx, ip in enumerate(paths):
            obj, v_kn, c_n = load_instance(ip)
            setup = obj["setup"]
            name = ip.stem
            print(f"\n  [{idx+1}/{len(paths)}] {name}  seed={setup['seed']}")

            try:
                ass = get_assortments(n, name, result_dir)
            except FileNotFoundError as e:
                print(f"    !! {e}")
                continue

            v_out = oos_samples(setup)
            base = {"N": n, "cost": cost, "instance_id": name, "seed": int(setup["seed"])}

            # --- Joint (C12-rev) ---
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

            row = {
                **base,
                "method": "Joint",
                "cross_mode": cross_mode,
                "in_sample": j.get("objective"),
                "oos": j_oos,
                "runtime": t1 - t0,
                "choice": j.get("choice_summary"),
                "size_prices": j.get("size_prices"),
                "feasible": j.get("feasible"),
                "mip_gap": j.get("mip_gap"),
                "num_constrs": j.get("model_num_constrs"),
                "num_bundles": j.get("bundle_count"),
            }
            all_rows.append(row)
            print(f"    Joint (C12-rev)   InS={fmt(j.get('objective'))}  OOS={fmt(j_oos)}  "
                  f"RT={t1-t0:.1f}s  {j.get('choice_summary')}  constrs={j.get('model_num_constrs')}")

            # --- Joint (no C12) ---
            t0 = time.time()
            j2 = solve_joint_fcp_bsp(
                v_kn, c_n, ass,
                time_limit=TL, mip_gap=GAP, output_flag=0,
                cross_mode="none",
            )
            t1 = time.time()

            j2_oos = None
            if j2["feasible"] and j2["bundle_prices_full"] and j2["size_prices"]:
                j2_oos = eval_hybrid_oos(
                    v_out, c_n, j2["bundle_prices_full"],
                    np.asarray(j2["assortments"], dtype=int), j2["size_prices"],
                )["hybrid_oos"]

            row2 = {
                **base,
                "method": "Joint-noC12",
                "cross_mode": "none",
                "in_sample": j2.get("objective"),
                "oos": j2_oos,
                "runtime": t1 - t0,
                "choice": j2.get("choice_summary"),
                "size_prices": j2.get("size_prices"),
                "feasible": j2.get("feasible"),
                "mip_gap": j2.get("mip_gap"),
                "num_constrs": j2.get("model_num_constrs"),
                "num_bundles": j2.get("bundle_count"),
            }
            all_rows.append(row2)
            print(f"    Joint (noC12)     InS={fmt(j2.get('objective'))}  OOS={fmt(j2_oos)}  "
                  f"RT={t1-t0:.1f}s  {j2.get('choice_summary')}  constrs={j2.get('model_num_constrs')}")

    # Save
    out_path = EXP / "joint_rerun_all_setups.json"
    with open(out_path, "w") as f:
        json.dump(all_rows, f, indent=2, default=json_default)
    print(f"\n{'='*80}")
    print(f"Saved {len(all_rows)} rows to {out_path}")

    # Print summary table
    print(f"\n{'='*80}")
    print("OOS Summary (avg per setup)")
    print(f"{'='*80}")
    from collections import defaultdict
    agg = defaultdict(lambda: defaultdict(list))
    for r in all_rows:
        key = (r["N"], r["cost"], r["method"])
        if r["oos"] is not None:
            agg[key]["oos"].append(r["oos"])
        if r["in_sample"] is not None:
            agg[key]["ins"].append(r["in_sample"])
        agg[key]["rt"].append(r["runtime"])

    print(f"{'Setup':30s} {'Method':16s} {'InS':>10s} {'OOS':>10s} {'RT':>8s} {'#inst':>5s}")
    for (nn, cost, method), vals in sorted(agg.items()):
        ins_avg = np.mean(vals["ins"]) if vals["ins"] else None
        oos_avg = np.mean(vals["oos"]) if vals["oos"] else None
        rt_avg = np.mean(vals["rt"])
        n_inst = len(vals["rt"])
        print(f"N={nn:2d}/{cost:12s}        {method:16s} {fmt(ins_avg):>10s} {fmt(oos_avg):>10s} {rt_avg:>7.1f}s {n_inst:>5d}")


if __name__ == "__main__":
    main()
