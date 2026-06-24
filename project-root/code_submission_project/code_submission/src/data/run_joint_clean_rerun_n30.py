"""
Run Joint + baselines on old instances for N=30.
random_ind and random_corr, 5 instances each.
Uses GCN-pruned assortments from FCP result JSONs.
"""
from __future__ import annotations
import json, sys, time
from collections import defaultdict
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import msgpack, msgpack_numpy as mnp
from eval_bsp_fcp_hybrid_oos import eval_hybrid_oos
from generate_data_CPBSD import sample_valuations, valuation_means
from solve_joint_fcp_bsp import solve_joint_fcp_bsp
from solve_mb_bsp_on_cpbsd_v2 import (
    eval_bsp_policy, eval_mb_policy, json_default,
    solve_bsp, solve_mb_restricted,
)
from solve_cpbsd_a import solve_cpbsd_a

EXP = Path("/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments")


def load_instance(path):
    with open(path, "rb") as f:
        obj = msgpack.load(f, object_hook=mnp.decode, strict_map_key=False)
    return obj, np.asarray(obj["valuation_samples_V"], dtype=float), np.asarray(obj["production_cost_c"], dtype=float)


def oos_samples(setup, k_out=5000):
    rng = np.random.default_rng(int(setup["seed"]) + 99991)
    means = valuation_means(int(setup["n_products"]), setup["heterogeneity"])
    return sample_valuations(k=k_out, means=means, family=setup["dist_family"], rho=float(setup["rho"]), rng=rng)


def get_assortments(cost, inst_name):
    fcp_file = EXP / f"fcp_random_cost_eval_n30_{cost}/results/{inst_name}__fcp_pruned_mb.json"
    return np.array(json.loads(fcp_file.read_text())["assortments"], dtype=int)


def fmt(v):
    return f"{v:.4f}" if v is not None else "N/A"


def main():
    TL = 600.0; GAP = 1e-2
    all_rows = []

    for cost in ["random_ind", "random_corr"]:
        print(f"\n{'='*80}")
        print(f"N=30 / {cost}")
        print(f"{'='*80}")

        inst_dir = EXP / f"fcp_random_cost_eval_n30_{cost}/instances"
        paths = sorted(inst_dir.glob("*.msgpack"))

        for idx, ip in enumerate(paths):
            obj, v_kn, c_n = load_instance(ip)
            setup = obj["setup"]
            name = ip.stem
            print(f"\n  [{idx+1}/{len(paths)}] {name}  seed={setup['seed']}")

            ass = get_assortments(cost, name)
            v_out = oos_samples(setup)
            base = {"N": 30, "cost": cost, "instance_id": name, "seed": int(setup["seed"])}

            # FCP
            t0 = time.time()
            fcp = solve_mb_restricted(v_kn, c_n, ass, time_limit=TL, mip_gap=GAP, output_flag=0)
            t1 = time.time()
            fcp_bp = fcp.get("bundle_prices_full") or fcp.get("bundle_prices") or {}
            fcp_oos = eval_mb_policy(v_out, c_n, fcp_bp, np.asarray(fcp.get("assortments", ass), dtype=int)) if fcp.get("feasible") and fcp_bp else None
            all_rows.append({**base, "method": "FCP", "in_sample": fcp.get("objective"), "oos": fcp_oos, "runtime": t1-t0})
            print(f"    FCP:          InS={fmt(fcp.get('objective'))}  OOS={fmt(fcp_oos)}  RT={t1-t0:.1f}s")

            # BSP
            t0 = time.time()
            bsp = solve_bsp(v_kn, c_n, time_limit=TL, mip_gap=GAP, output_flag=0)
            t1 = time.time()
            bsp_oos = eval_bsp_policy(v_out, c_n, bsp["size_prices"]) if bsp.get("feasible") and bsp.get("size_prices") else None
            all_rows.append({**base, "method": "BSP", "in_sample": bsp.get("objective"), "oos": bsp_oos, "runtime": t1-t0})
            print(f"    BSP:          InS={fmt(bsp.get('objective'))}  OOS={fmt(bsp_oos)}  RT={t1-t0:.1f}s")

            # CPBSD-A
            t0 = time.time()
            ca = solve_cpbsd_a(v_kn, c_n, time_limit=TL, mip_gap=GAP, output_flag=0)
            t1 = time.time()
            ca_oos = None
            if ca.get("sol_count", 0) > 0:
                p_vec = np.array(ca.get("p", []), dtype=float)
                d_vec = np.array(ca.get("d", []), dtype=float)
                if len(p_vec) > 0:
                    from run_cpbsd_fcp_pruned_mb_compare import evaluate_revenue
                    ca_oos = evaluate_revenue(v_out, c_n, p_vec, d_vec)
            all_rows.append({**base, "method": "CPBSD-A", "in_sample": ca.get("objective"), "oos": ca_oos, "runtime": t1-t0})
            print(f"    CPBSD-A:      InS={fmt(ca.get('objective'))}  OOS={fmt(ca_oos)}  RT={t1-t0:.1f}s")

            # Joint
            t0 = time.time()
            j1 = solve_joint_fcp_bsp(v_kn, c_n, ass, time_limit=TL, mip_gap=GAP, output_flag=0, cross_mode="fcp_le_bsp")
            t1 = time.time()
            j1_oos = None
            if j1["feasible"] and j1["bundle_prices_full"] and j1["size_prices"]:
                j1_oos = eval_hybrid_oos(v_out, c_n, j1["bundle_prices_full"], np.asarray(j1["assortments"], dtype=int), j1["size_prices"])["hybrid_oos"]
            all_rows.append({**base, "method": "Joint", "in_sample": j1.get("objective"), "oos": j1_oos, "runtime": t1-t0, "choice": j1.get("choice_summary")})
            print(f"    Joint:        InS={fmt(j1.get('objective'))}  OOS={fmt(j1_oos)}  RT={t1-t0:.1f}s  {j1.get('choice_summary')}")

            # Joint-noC12
            t0 = time.time()
            j2 = solve_joint_fcp_bsp(v_kn, c_n, ass, time_limit=TL, mip_gap=GAP, output_flag=0, cross_mode="none")
            t1 = time.time()
            j2_oos = None
            if j2["feasible"] and j2["bundle_prices_full"] and j2["size_prices"]:
                j2_oos = eval_hybrid_oos(v_out, c_n, j2["bundle_prices_full"], np.asarray(j2["assortments"], dtype=int), j2["size_prices"])["hybrid_oos"]
            all_rows.append({**base, "method": "Joint-noC12", "in_sample": j2.get("objective"), "oos": j2_oos, "runtime": t1-t0, "choice": j2.get("choice_summary")})
            print(f"    Joint-noC12:  InS={fmt(j2.get('objective'))}  OOS={fmt(j2_oos)}  RT={t1-t0:.1f}s  {j2.get('choice_summary')}")

    # Summary
    print(f"\n{'='*90}")
    print("AVERAGES")
    print(f"{'='*90}")

    by_cost = defaultdict(lambda: defaultdict(list))
    for r in all_rows:
        by_cost[r["cost"]][r["method"]].append(r)

    for cost_val, md in sorted(by_cost.items()):
        print(f"\n### N=30 / {cost_val}")
        print(f"  {'Method':<18} {'InS':>8} {'OOS':>8} {'RT':>8}")
        print(f"  {'-'*46}")
        for method in ["FCP", "BSP", "CPBSD-A", "Joint", "Joint-noC12"]:
            rows = md.get(method, [])
            if rows:
                ins_v = [r["in_sample"] for r in rows if r["in_sample"] is not None]
                oos_v = [r["oos"] for r in rows if r["oos"] is not None]
                rt_v = [r["runtime"] for r in rows if r["runtime"] is not None]
                print(f"  {method:<18} {np.mean(ins_v):>8.2f} {np.mean(oos_v):>8.2f} {np.mean(rt_v):>7.1f}s")

    out = EXP / "joint_clean_rerun_n30.json"
    out.write_text(json.dumps(all_rows, indent=2, default=json_default), encoding="utf-8")
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()
