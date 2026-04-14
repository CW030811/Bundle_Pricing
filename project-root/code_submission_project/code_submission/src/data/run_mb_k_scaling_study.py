"""MB K-Scaling Study: how does training sample size affect generalization?

For N=5 (32 bundle prices), tests K in {50, 100, 200, 400} to quantify
the relationship between sample size and in→out revenue drop.

Paper uses K=50 for N=5, but the paper's boxplot aggregates across 135
parameter combinations — many of which are easy for MB. Our specific
setting (normal, full heterogeneity, hvhm) is in the hard tail.

This study answers: can we close the 28% gap by increasing K?
"""

import csv
import json
import os
import sys
import time
from pathlib import Path

# Prefer explicit academic license file when present
if not os.environ.get("GRB_LICENSE_FILE") and Path.home().joinpath(".gurobi", "gurobi.lic").exists():
    os.environ["GRB_LICENSE_FILE"] = str(Path.home().joinpath(".gurobi", "gurobi.lic"))

import msgpack
import msgpack_numpy as mnp
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.append(str(SCRIPT_DIR))

from generate_data_CPBSD import generate_batch, sample_valuations, valuation_means
from solve_mb_bsp_on_cpbsd_v2 import (
    build_assortments,
    eval_bsp_policy,
    eval_mb_policy,
    extract_mb_policy_info,
    json_default,
    normalize_numeric_keys,
    solve_bsp,
    solve_mb,
)

CODE_ROOT = Path(
    "/Users/sensen/.openclaw/workspace/domains/revenue-management/"
    "project-root/code_submission_project/code_submission/"
    "experiments/cpbsd_baselines_v2"
)
STUDY_ROOT = CODE_ROOT / "mb_k_scaling_study"

N_PRODUCTS = 5
N_INSTANCES = 5
BASE_SEED = 20260304
K_VALUES = [50, 100, 200, 400]
OUT_SAMPLE_K = 5000
TIME_LIMIT = 300.0


def read_setup(msgpack_path: Path) -> dict:
    with open(msgpack_path, "rb") as f:
        obj = msgpack.load(f, object_hook=mnp.decode)
    return obj.get("setup", {})


def load_instance(msgpack_path: Path):
    with open(msgpack_path, "rb") as f:
        obj = msgpack.load(f, object_hook=mnp.decode)
    v = np.asarray(obj["valuation_samples_V"], dtype=float)
    c = np.asarray(obj["production_cost_c"], dtype=float)
    return v, c


def sample_out_of_sample(setup: dict) -> np.ndarray:
    rng = np.random.default_rng(int(setup["seed"]) + 99991)
    means = valuation_means(int(setup["n_products"]), setup["heterogeneity"])
    return sample_valuations(
        k=OUT_SAMPLE_K,
        means=means,
        family=setup["dist_family"],
        rho=float(setup["rho"]),
        rng=rng,
    )


def load_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")


def run_study():
    inst_base = STUDY_ROOT / "instances"
    res_dir = STUDY_ROOT / "results"
    plot_dir = STUDY_ROOT / "plots"
    for d in (inst_base, res_dir, plot_dir):
        d.mkdir(parents=True, exist_ok=True)

    rows = []

    for k_val in K_VALUES:
        print(f"\n{'='*60}")
        print(f"K = {k_val}  (N={N_PRODUCTS}, 2^N={2**N_PRODUCTS} bundles)")
        print(f"{'='*60}")

        # Generate instances for this K
        inst_dir = inst_base / f"k{k_val}"
        generate_batch(
            out_dir=str(inst_dir),
            n_products=N_PRODUCTS,
            k_samples=k_val,
            dist_family="normal",
            rho=0.0,
            heterogeneity="full",
            cost_scenario="hvhm",
            n_instances=N_INSTANCES,
            seed=BASE_SEED,
        )

        instance_files = sorted(inst_dir.glob("*.msgpack"))

        for idx in range(1, N_INSTANCES + 1):
            instance_id = f"k{k_val}_inst{idx:03d}"
            mp = instance_files[idx - 1]
            v_in, c_n = load_instance(mp)
            setup = read_setup(mp)
            v_out = sample_out_of_sample(setup)

            # --- MB solve (with cache) ---
            mb_cache = res_dir / f"mb_k{k_val}_inst{idx:03d}.json"
            mb_res = load_json(mb_cache)
            if mb_res is None or not mb_res.get("bundle_prices_full"):
                print(f"  solving MB {instance_id} ...", end=" ", flush=True)
                t0 = time.time()
                mb_res = solve_mb(v_in, c_n, time_limit=TIME_LIMIT, mip_gap=1e-2, output_flag=0)
                elapsed = time.time() - t0
                save_json(mb_cache, mb_res)
                print(f"done ({elapsed:.1f}s, status={mb_res.get('solver_status')})")
            else:
                print(f"  cached MB {instance_id}")

            # --- BSP solve (with cache) ---
            bsp_cache = res_dir / f"bsp_k{k_val}_inst{idx:03d}.json"
            bsp_res = load_json(bsp_cache)
            if bsp_res is None or not bsp_res.get("size_prices"):
                print(f"  solving BSP {instance_id} ...", end=" ", flush=True)
                t0 = time.time()
                bsp_res = solve_bsp(v_in, c_n, time_limit=TIME_LIMIT, mip_gap=1e-2, output_flag=0)
                elapsed = time.time() - t0
                save_json(bsp_cache, bsp_res)
                print(f"done ({elapsed:.1f}s)")
            else:
                print(f"  cached BSP {instance_id}")

            # --- Evaluate ---
            mb_info = extract_mb_policy_info(mb_res)
            bp_full = mb_info["bundle_prices_full"]
            assortments = mb_info["assortments"]
            size_prices = normalize_numeric_keys(bsp_res.get("size_prices", {}))

            if not bp_full or assortments is None:
                print(f"  SKIP {instance_id}: MB solve failed")
                continue

            mb_in = eval_mb_policy(v_in, c_n, bp_full, assortments)
            mb_out = eval_mb_policy(v_out, c_n, bp_full, assortments)
            bsp_in = eval_bsp_policy(v_in, c_n, size_prices)
            bsp_out = eval_bsp_policy(v_out, c_n, size_prices)

            for variant, rev_in, rev_out in [
                ("MB", mb_in, mb_out),
                ("BSP", bsp_in, bsp_out),
            ]:
                rows.append({
                    "k": k_val,
                    "instance_idx": idx,
                    "instance_id": instance_id,
                    "variant": variant,
                    "revenue_in_sample": rev_in,
                    "revenue_out_sample": rev_out,
                    "drop_pct": 100.0 * (1.0 - rev_out / rev_in) if rev_in else None,
                    "ratio_to_bsp_in": rev_in / bsp_in if bsp_in else None,
                    "ratio_to_bsp_out": rev_out / bsp_out if bsp_out else None,
                    "n_bundles": 2 ** N_PRODUCTS if variant == "MB" else N_PRODUCTS,
                    "samples_per_param": k_val / (2 ** N_PRODUCTS) if variant == "MB" else k_val / N_PRODUCTS,
                })

    if not rows:
        print("ERROR: no rows generated")
        return

    # Write CSV
    csv_path = STUDY_ROOT / "mb_k_scaling_study.csv"
    fieldnames = list(rows[0].keys())
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nwritten: {csv_path}")

    # Plot
    _plot_k_scaling(rows, plot_dir)

    # Print summary
    _print_summary(rows)


def _plot_k_scaling(rows, plot_dir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    mb_rows = [r for r in rows if r["variant"] == "MB"]
    bsp_rows = [r for r in rows if r["variant"] == "BSP"]

    # --- Plot 1: Overfitting drop % vs K ---
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), dpi=180)
    fig.patch.set_facecolor("white")

    ax = axes[0]
    ax.set_facecolor("#ebebeb")
    for variant, color, vrows in [("MB", "#2b8cbe", mb_rows), ("BSP", "#cc6d2d", bsp_rows)]:
        k_vals = sorted(set(r["k"] for r in vrows))
        means = []
        stds = []
        for k in k_vals:
            drops = [r["drop_pct"] for r in vrows if r["k"] == k and r["drop_pct"] is not None]
            means.append(np.mean(drops))
            stds.append(np.std(drops))
        ax.errorbar(k_vals, means, yerr=stds, marker="o", capsize=4, color=color, label=variant, linewidth=2)
    ax.set_xlabel("K (training samples)")
    ax.set_ylabel("In→Out Revenue Drop (%)")
    ax.set_title("Overfitting vs Training Sample Size (N=5)")
    ax.legend()
    ax.grid(axis="y", color="white", linewidth=1.0)
    ax.set_axisbelow(True)

    # --- Plot 2: Out-of-sample revenue ratio vs BSP ---
    ax = axes[1]
    ax.set_facecolor("#ebebeb")
    k_vals = sorted(set(r["k"] for r in mb_rows))
    in_means = []
    out_means = []
    in_stds = []
    out_stds = []
    for k in k_vals:
        kr = [r for r in mb_rows if r["k"] == k]
        ins = [r["ratio_to_bsp_in"] for r in kr if r["ratio_to_bsp_in"] is not None]
        outs = [r["ratio_to_bsp_out"] for r in kr if r["ratio_to_bsp_out"] is not None]
        in_means.append(np.mean(ins))
        out_means.append(np.mean(outs))
        in_stds.append(np.std(ins))
        out_stds.append(np.std(outs))
    ax.errorbar(k_vals, in_means, yerr=in_stds, marker="s", capsize=4, color="#74c0e3", label="MB in-sample / BSP", linewidth=2)
    ax.errorbar(k_vals, out_means, yerr=out_stds, marker="o", capsize=4, color="#2b8cbe", label="MB out-of-sample / BSP", linewidth=2)
    ax.axhline(1.0, color="#cc6d2d", linestyle="--", linewidth=1.2, label="BSP = 1.0")
    ax.set_xlabel("K (training samples)")
    ax.set_ylabel("Revenue Ratio vs BSP")
    ax.set_title("MB Generalization vs BSP (N=5)")
    ax.legend(fontsize=8)
    ax.grid(axis="y", color="white", linewidth=1.0)
    ax.set_axisbelow(True)

    fig.tight_layout()
    plot_path = plot_dir / "mb_k_scaling_diagnostic.png"
    fig.savefig(plot_path, bbox_inches="tight")
    plt.close(fig)
    print(f"written: {plot_path}")


def _print_summary(rows):
    print()
    print("=" * 90)
    print(f"{'K':>5} {'Variant':<8} {'Samples/Param':>14} {'Mean Rev-In':>12} {'Mean Rev-Out':>12} "
          f"{'Mean Drop%':>11} {'vs BSP-Out':>11}")
    print("-" * 90)
    for k_val in sorted(set(r["k"] for r in rows)):
        for variant in ["MB", "BSP"]:
            vr = [r for r in rows if r["k"] == k_val and r["variant"] == variant]
            if not vr:
                continue
            rev_in = np.mean([r["revenue_in_sample"] for r in vr])
            rev_out = np.mean([r["revenue_out_sample"] for r in vr])
            drop = np.mean([r["drop_pct"] for r in vr if r["drop_pct"] is not None])
            bsp_out = np.mean([r["ratio_to_bsp_out"] for r in vr if r["ratio_to_bsp_out"] is not None])
            spp = vr[0]["samples_per_param"]
            print(f"{k_val:>5} {variant:<8} {spp:>14.1f} {rev_in:>12.4f} {rev_out:>12.4f} "
                  f"{drop:>10.2f}% {bsp_out:>11.4f}")
        print()
    print("=" * 90)

    # Conclusion
    mb_k50 = [r for r in rows if r["k"] == 50 and r["variant"] == "MB"]
    mb_k400 = [r for r in rows if r["k"] == 400 and r["variant"] == "MB"]
    if mb_k50 and mb_k400:
        drop_50 = np.mean([r["drop_pct"] for r in mb_k50])
        drop_400 = np.mean([r["drop_pct"] for r in mb_k400])
        print(f"\nConclusion: K=50 → {drop_50:.1f}% drop, K=400 → {drop_400:.1f}% drop")
        improvement = drop_50 - drop_400
        print(f"Increasing K by 8x reduces overfitting by {improvement:.1f} percentage points")


if __name__ == "__main__":
    run_study()
