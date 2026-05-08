"""
Joint FCP+BSP experiment: compare Joint MILP vs FCP-only vs BSP-only vs CPBSD-A vs PostHoc Hybrid.

Tests 3 cost scenarios (zero, random_ind, random_corr) × 5 instances at N=5, K=50.

Usage:
  python run_joint_fcp_bsp_experiment.py
  python run_joint_fcp_bsp_experiment.py --instances 1  # smoke test
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from eval_bsp_fcp_hybrid_oos import eval_hybrid_oos
from generate_data_CPBSD import generate_batch, sample_valuations, valuation_means
from solve_cpbsd_a import solve_cpbsd_a
from solve_joint_fcp_bsp import solve_joint_fcp_bsp
from solve_mb_bsp_on_cpbsd_v2 import (
    build_assortments,
    eval_bsp_policy,
    eval_mb_policy,
    json_default,
    normalize_numeric_keys,
    solve_bsp,
    solve_mb_restricted,
)

BASE = Path("/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments")


def load_instance(path: Path):
    import msgpack
    import msgpack_numpy as mnp

    with open(path, "rb") as f:
        obj = msgpack.load(f, object_hook=mnp.decode, strict_map_key=False)
    return obj, np.asarray(obj["valuation_samples_V"], dtype=float), np.asarray(obj["production_cost_c"], dtype=float)


def oos_samples(setup: dict, k_out: int = 5000):
    rng = np.random.default_rng(int(setup["seed"]) + 99991)
    means = valuation_means(int(setup["n_products"]), setup["heterogeneity"])
    return sample_valuations(k=k_out, means=means, family=setup["dist_family"], rho=float(setup["rho"]), rng=rng)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--instances", type=int, default=5)
    parser.add_argument("--N", type=int, default=5)
    parser.add_argument("--K", type=int, default=50)
    parser.add_argument("--seed", type=int, default=20260425)
    parser.add_argument("--time-limit", type=float, default=600.0)
    parser.add_argument("--mip-gap", type=float, default=1e-2)
    parser.add_argument("--output-flag", type=int, default=0)
    args = parser.parse_args()

    cost_scenarios = ["zero", "random_ind", "random_corr"]
    exp_root = BASE / "joint_fcp_bsp_n5"
    exp_root.mkdir(parents=True, exist_ok=True)

    all_rows = []

    for cost in cost_scenarios:
        print(f"\n{'='*70}")
        print(f"Cost scenario: {cost}")
        print(f"{'='*70}")

        inst_dir = exp_root / f"instances_{cost}"
        inst_dir.mkdir(parents=True, exist_ok=True)

        # Generate instances if not present
        existing = sorted(inst_dir.glob("*.msgpack"))
        if len(existing) < args.instances:
            generate_batch(
                out_dir=str(inst_dir),
                n_products=args.N,
                k_samples=args.K,
                dist_family="normal",
                rho=0.0,
                heterogeneity="full",
                cost_scenario=cost,
                n_instances=args.instances,
                seed=args.seed,
            )
            existing = sorted(inst_dir.glob("*.msgpack"))

        instance_paths = existing[: args.instances]
        assortments = build_assortments(args.N)  # full 2^N for N=5

        for inst_idx, inst_path in enumerate(instance_paths):
            obj, v_kn, c_n = load_instance(inst_path)
            setup = obj["setup"]
            inst_id = inst_path.stem
            print(f"\n  Instance {inst_idx+1}/{len(instance_paths)}: {inst_id}")

            v_out = oos_samples(setup)

            row_base = {
                "cost": cost,
                "instance_id": inst_id,
                "N": args.N,
                "K": args.K,
                "seed": int(setup["seed"]),
            }

            # --- 1. Joint FCP+BSP ---
            t0 = time.time()
            joint_res = solve_joint_fcp_bsp(
                v_kn, c_n, assortments,
                time_limit=args.time_limit, mip_gap=args.mip_gap,
                output_flag=args.output_flag,
            )
            t1 = time.time()
            joint_oos = None
            if joint_res["feasible"] and joint_res["bundle_prices_full"] and joint_res["size_prices"]:
                joint_hybrid = eval_hybrid_oos(
                    v_out, c_n,
                    joint_res["bundle_prices_full"],
                    np.asarray(joint_res["assortments"], dtype=int),
                    joint_res["size_prices"],
                )
                joint_oos = joint_hybrid["hybrid_oos"]
            all_rows.append({
                **row_base,
                "method": "Joint-FCP-BSP",
                "in_sample": joint_res.get("objective"),
                "oos": joint_oos,
                "runtime": t1 - t0,
                "choice_summary": joint_res.get("choice_summary"),
            })
            ins_s = f"{joint_res['objective']:.4f}" if joint_res.get("objective") is not None else "N/A"
            oos_s = f"{joint_oos:.4f}" if joint_oos is not None else "N/A"
            print(f"    Joint:    InS={ins_s}  OOS={oos_s}  RT={t1-t0:.1f}s  {joint_res.get('choice_summary')}")

            # --- 1b. Joint FCP+BSP without C12 ---
            t0 = time.time()
            joint_noc12_res = solve_joint_fcp_bsp(
                v_kn, c_n, assortments,
                time_limit=args.time_limit, mip_gap=args.mip_gap,
                output_flag=args.output_flag,
                cross_mode="none",
            )
            t1 = time.time()
            joint_noc12_oos = None
            if joint_noc12_res["feasible"] and joint_noc12_res["bundle_prices_full"] and joint_noc12_res["size_prices"]:
                joint_noc12_hybrid = eval_hybrid_oos(
                    v_out, c_n,
                    joint_noc12_res["bundle_prices_full"],
                    np.asarray(joint_noc12_res["assortments"], dtype=int),
                    joint_noc12_res["size_prices"],
                )
                joint_noc12_oos = joint_noc12_hybrid["hybrid_oos"]
            all_rows.append({
                **row_base,
                "method": "Joint-FCP-BSP-noC12",
                "in_sample": joint_noc12_res.get("objective"),
                "oos": joint_noc12_oos,
                "runtime": t1 - t0,
                "choice_summary": joint_noc12_res.get("choice_summary"),
            })
            ins_s = f"{joint_noc12_res['objective']:.4f}" if joint_noc12_res.get("objective") is not None else "N/A"
            oos_s = f"{joint_noc12_oos:.4f}" if joint_noc12_oos is not None else "N/A"
            print(f"    Joint-noC12: InS={ins_s}  OOS={oos_s}  RT={t1-t0:.1f}s  {joint_noc12_res.get('choice_summary')}")

            # --- 2. FCP-only (solve_mb_restricted) ---
            t0 = time.time()
            fcp_res = solve_mb_restricted(
                v_kn, c_n, assortments,
                time_limit=args.time_limit, mip_gap=args.mip_gap,
                output_flag=args.output_flag,
            )
            t1 = time.time()
            fcp_oos = None
            fcp_policy = fcp_res.get("bundle_prices_full") or fcp_res.get("bundle_prices") or {}
            if fcp_res.get("feasible") and fcp_policy:
                fcp_oos = eval_mb_policy(
                    v_out, c_n, fcp_policy,
                    np.asarray(fcp_res.get("assortments", assortments), dtype=int),
                )
            all_rows.append({
                **row_base,
                "method": "FCP-only",
                "in_sample": fcp_res.get("objective"),
                "oos": fcp_oos,
                "runtime": t1 - t0,
            })
            ins_s = f"{fcp_res['objective']:.4f}" if fcp_res.get("objective") is not None else "N/A"
            oos_s = f"{fcp_oos:.4f}" if fcp_oos is not None else "N/A"
            print(f"    FCP:      InS={ins_s}  OOS={oos_s}  RT={t1-t0:.1f}s")

            # --- 3. BSP-only ---
            t0 = time.time()
            bsp_res = solve_bsp(
                v_kn, c_n,
                time_limit=args.time_limit, mip_gap=args.mip_gap,
                output_flag=args.output_flag,
            )
            t1 = time.time()
            bsp_oos = None
            if bsp_res.get("feasible") and bsp_res.get("size_prices"):
                bsp_oos = eval_bsp_policy(v_out, c_n, bsp_res["size_prices"])
            all_rows.append({
                **row_base,
                "method": "BSP-only",
                "in_sample": bsp_res.get("objective"),
                "oos": bsp_oos,
                "runtime": t1 - t0,
            })
            ins_s = f"{bsp_res['objective']:.4f}" if bsp_res.get("objective") is not None else "N/A"
            oos_s = f"{bsp_oos:.4f}" if bsp_oos is not None else "N/A"
            print(f"    BSP:      InS={ins_s}  OOS={oos_s}  RT={t1-t0:.1f}s")

            # --- 4. CPBSD-A ---
            t0 = time.time()
            cpbsd_res = solve_cpbsd_a(
                v_kn, c_n,
                time_limit=args.time_limit, mip_gap=args.mip_gap,
                output_flag=args.output_flag,
            )
            t1 = time.time()
            cpbsd_oos = None
            if cpbsd_res.get("sol_count", 0) > 0:
                p_vec = np.array(cpbsd_res.get("p", []), dtype=float)
                d_vec = np.array(cpbsd_res.get("d", []), dtype=float)
                if len(p_vec) > 0:
                    rng_oos = np.random.default_rng(int(setup["seed"]) + 99991)
                    means = valuation_means(int(setup["n_products"]), setup["heterogeneity"])
                    v_oos_cpbsd = sample_valuations(k=5000, means=means, family=setup["dist_family"], rho=float(setup["rho"]), rng=rng_oos)
                    from run_cpbsd_fcp_pruned_mb_compare import evaluate_revenue
                    cpbsd_oos = evaluate_revenue(v_oos_cpbsd, c_n, p_vec, d_vec)
            all_rows.append({
                **row_base,
                "method": "CPBSD-A",
                "in_sample": cpbsd_res.get("objective"),
                "oos": cpbsd_oos,
                "runtime": t1 - t0,
            })
            ins_s = f"{cpbsd_res['objective']:.4f}" if cpbsd_res.get("objective") is not None else "N/A"
            oos_s = f"{cpbsd_oos:.4f}" if cpbsd_oos is not None else "N/A"
            print(f"    CPBSD-A:  InS={ins_s}  OOS={oos_s}  RT={t1-t0:.1f}s")

            # --- 5. PostHoc Hybrid (FCP + BSP independently) ---
            posthoc_oos = None
            if fcp_policy and bsp_res.get("size_prices"):
                posthoc = eval_hybrid_oos(
                    v_out, c_n, fcp_policy,
                    np.asarray(fcp_res.get("assortments", assortments), dtype=int),
                    bsp_res["size_prices"],
                )
                posthoc_oos = posthoc["hybrid_oos"]
            all_rows.append({
                **row_base,
                "method": "PostHoc-Hybrid",
                "in_sample": None,
                "oos": posthoc_oos,
                "runtime": None,
            })
            oos_s = f"{posthoc_oos:.4f}" if posthoc_oos is not None else "N/A"
            print(f"    PostHoc:  OOS={oos_s}")

    # --- Summary ---
    print(f"\n{'='*90}")
    print("AVERAGES (per cost scenario)")
    print(f"{'='*90}")

    by_setup = defaultdict(lambda: defaultdict(list))
    for r in all_rows:
        if r["oos"] is not None:
            by_setup[r["cost"]][r["method"]].append(r["oos"])

    for cost in cost_scenarios:
        print(f"\n  {cost}:")
        methods_data = by_setup[cost]
        for method in ["Joint-FCP-BSP", "Joint-FCP-BSP-noC12", "FCP-only", "BSP-only", "CPBSD-A", "PostHoc-Hybrid"]:
            vals = methods_data.get(method, [])
            if vals:
                avg = np.mean(vals)
                print(f"    {method:<18}: OOS={avg:.4f}  (n={len(vals)})")

    # Save
    out_path = exp_root / "joint_fcp_bsp_comparison.json"
    out_path.write_text(json.dumps(all_rows, indent=2, ensure_ascii=False, default=json_default), encoding="utf-8")
    print(f"\nResults saved to: {out_path}")


if __name__ == "__main__":
    main()
