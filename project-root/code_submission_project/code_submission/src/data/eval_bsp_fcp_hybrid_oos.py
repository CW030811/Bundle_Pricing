"""
Post-hoc BSP+FCP hybrid OOS evaluation.

Reads existing FCP and BSP result JSONs from fcp_random_cost_eval_* dirs,
computes hybrid OOS where each customer picks the best option from both menus.

Usage:
  python eval_bsp_fcp_hybrid_oos.py
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_data_CPBSD import sample_valuations, valuation_means
from solve_mb_bsp_on_cpbsd_v2 import normalize_numeric_keys

BASE = Path("/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments")


def eval_hybrid_oos(
    v_eval: np.ndarray,
    c_n: np.ndarray,
    # FCP policy
    bundle_prices: dict,
    assortments: np.ndarray,
    # BSP policy
    size_prices: dict,
) -> dict:
    """Each customer picks the best option from FCP menu OR BSP menu."""
    bundle_prices = normalize_numeric_keys(bundle_prices or {})
    size_prices = normalize_numeric_keys(size_prices or {})
    assortments = np.asarray(assortments, dtype=int)
    k_count, n_products = v_eval.shape
    bundle_cost = assortments @ c_n
    eps = 1e-9

    total_profit = 0.0
    chose_fcp = 0
    chose_bsp = 0
    chose_outside = 0

    for k in range(k_count):
        # --- FCP best option ---
        fcp_surplus = 0.0
        fcp_profit = 0.0
        fcp_bundle = None
        for bi in range(assortments.shape[0]):
            price = bundle_prices.get(bi)
            if price is None:
                continue
            value = float(v_eval[k] @ assortments[bi])
            surplus = value - float(price)
            if abs(surplus) <= eps:
                surplus = 0.0
            profit = float(price) - float(bundle_cost[bi])
            if surplus > fcp_surplus + eps:
                fcp_surplus = surplus
                fcp_bundle = bi
                fcp_profit = profit
            elif abs(surplus - fcp_surplus) <= eps and profit > fcp_profit + eps:
                fcp_bundle = bi
                fcp_profit = profit

        # --- BSP best option ---
        bsp_surplus = 0.0
        bsp_profit = 0.0
        bsp_size = 0
        order = np.argsort(-v_eval[k])
        prefix_val = 0.0
        prefix_cost = 0.0
        for size in range(1, n_products + 1):
            idx = order[size - 1]
            prefix_val += v_eval[k, idx]
            prefix_cost += c_n[idx]
            price = size_prices.get(size)
            if price is None:
                continue
            surplus = prefix_val - float(price)
            if surplus > bsp_surplus:
                bsp_surplus = surplus
                bsp_size = size
                bsp_profit = float(price) - prefix_cost

        # --- Customer chooses best ---
        if fcp_surplus <= 0 and bsp_surplus <= 0:
            chose_outside += 1
            continue

        if fcp_surplus > bsp_surplus + eps:
            total_profit += fcp_profit
            chose_fcp += 1
        elif bsp_surplus > fcp_surplus + eps:
            total_profit += bsp_profit
            chose_bsp += 1
        else:
            # tie: pick higher profit for firm
            if fcp_profit >= bsp_profit:
                total_profit += fcp_profit
                chose_fcp += 1
            else:
                total_profit += bsp_profit
                chose_bsp += 1

    return {
        "hybrid_oos": total_profit / k_count,
        "chose_fcp": chose_fcp,
        "chose_bsp": chose_bsp,
        "chose_outside": chose_outside,
        "k_out": k_count,
    }


def main():
    results = []

    for cost in ["random_ind", "random_corr"]:
        for n in [5, 10, 30]:
            exp_dir = BASE / f"fcp_random_cost_eval_n{n}_{cost}"
            summary_path = exp_dir / "comparison_summary.json"
            if not summary_path.exists():
                print(f"SKIP: {summary_path}")
                continue

            rows = json.load(open(summary_path))
            by_inst = defaultdict(dict)
            for r in rows:
                by_inst[r["instance_id"]][r["method"]] = r

            for inst_id in sorted(by_inst.keys()):
                methods = by_inst[inst_id]
                fcp_row = methods.get("FCP-pruned-MB")
                bsp_row = methods.get("BSP")
                if not fcp_row or not bsp_row:
                    continue

                # Load FCP policy
                fcp_json_path = Path(fcp_row["result_path"])
                if not fcp_json_path.exists():
                    print(f"SKIP: {fcp_json_path}")
                    continue
                fcp_res = json.load(open(fcp_json_path))
                fcp_policy = fcp_res.get("bundle_prices_full") or fcp_res.get("bundle_prices") or {}
                fcp_assortments = np.asarray(fcp_res["assortments"], dtype=int)

                # Load BSP policy
                bsp_json_path = Path(bsp_row["result_path"])
                if not bsp_json_path.exists():
                    print(f"SKIP: {bsp_json_path}")
                    continue
                bsp_res = json.load(open(bsp_json_path))
                bsp_size_prices = bsp_res.get("size_prices", {})

                if not fcp_policy or not bsp_size_prices:
                    continue

                # Load instance to get setup for OOS sampling
                inst_path = Path(exp_dir / "instances" / f"{inst_id}.msgpack")
                if not inst_path.exists():
                    # try glob
                    candidates = list((exp_dir / "instances").glob(f"{inst_id}*"))
                    if candidates:
                        inst_path = candidates[0]
                    else:
                        print(f"SKIP instance: {inst_id}")
                        continue

                import msgpack, msgpack_numpy as mnp
                with open(inst_path, "rb") as f:
                    obj = msgpack.load(f, object_hook=mnp.decode, strict_map_key=False)
                setup = obj["setup"]
                c_n = np.asarray(obj["production_cost_c"], dtype=float)

                # Generate OOS samples (same seed as the comparison script)
                rng = np.random.default_rng(int(setup["seed"]) + 99991)
                means = valuation_means(int(setup["n_products"]), setup["heterogeneity"])
                v_out = sample_valuations(
                    k=5000,
                    means=means,
                    family=setup["dist_family"],
                    rho=float(setup["rho"]),
                    rng=rng,
                )

                hybrid = eval_hybrid_oos(v_out, c_n, fcp_policy, fcp_assortments, bsp_size_prices)

                row = {
                    "cost": cost,
                    "N": n,
                    "instance_id": inst_id,
                    "fcp_oos": fcp_row.get("revenue_out_sample"),
                    "bsp_oos": bsp_row.get("revenue_out_sample"),
                    "cpbsd_a_oos": methods.get("CPBSD-A", {}).get("revenue_out_sample"),
                    "hybrid_oos": hybrid["hybrid_oos"],
                    "chose_fcp": hybrid["chose_fcp"],
                    "chose_bsp": hybrid["chose_bsp"],
                    "chose_outside": hybrid["chose_outside"],
                }
                results.append(row)
                print(
                    f"N={n:>2} {cost:<12} {inst_id[-20:]}: "
                    f"FCP={row['fcp_oos']:.3f}  BSP={row['bsp_oos']:.3f}  "
                    f"CPBSD-A={row['cpbsd_a_oos']:.3f}  "
                    f"Hybrid={hybrid['hybrid_oos']:.3f}  "
                    f"(fcp={hybrid['chose_fcp']} bsp={hybrid['chose_bsp']} out={hybrid['chose_outside']})"
                )

    # Print averages per setup
    print("\n" + "=" * 90)
    print("AVERAGES (5-instance mean)")
    print("=" * 90)
    by_setup = defaultdict(list)
    for r in results:
        by_setup[(r["cost"], r["N"])].append(r)

    for (cost, n), rows in sorted(by_setup.items()):
        fcp_avg = np.mean([r["fcp_oos"] for r in rows])
        bsp_avg = np.mean([r["bsp_oos"] for r in rows])
        cpbsd_avg = np.mean([r["cpbsd_a_oos"] for r in rows if r["cpbsd_a_oos"] is not None])
        hybrid_avg = np.mean([r["hybrid_oos"] for r in rows])
        print(
            f"N={n:>2} {cost:<12}: "
            f"FCP={fcp_avg:.3f}  BSP={bsp_avg:.3f}  CPBSD-A={cpbsd_avg:.3f}  "
            f"Hybrid={hybrid_avg:.3f}  "
            f"Δ(Hybrid-FCP)={hybrid_avg - fcp_avg:+.3f}  "
            f"Δ(Hybrid-BSP)={hybrid_avg - bsp_avg:+.3f}"
        )

    # Save results
    out_path = BASE / "fcp_bsp_hybrid_oos_results.json"
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nResults saved to: {out_path}")


if __name__ == "__main__":
    main()
