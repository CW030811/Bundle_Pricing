"""MB Out-of-Sample Generalization Quick Diagnostics.

Evaluates three MB pricing variants on cached N=5 results to quantify
how much of the in→out revenue drop comes from phantom bundles vs
intrinsic price tuning:

  MB-full:  all 32 bundle prices (current baseline)
  MB-sel:   only bundles selected by >=1 in-sample customer
  MB-floor: all 32 prices clipped to max(price, bundle_cost)

Zero compute cost — uses only cached solver results.
"""

import csv
import json
import sys
from pathlib import Path

import msgpack
import msgpack_numpy as mnp
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.append(str(SCRIPT_DIR))

from generate_data_CPBSD import sample_valuations, valuation_means
from solve_mb_bsp_on_cpbsd_v2 import (
    build_assortments,
    eval_bsp_policy,
    eval_mb_policy,
    normalize_numeric_keys,
)

ROOT = Path(
    "/Users/sensen/.openclaw/workspace/domains/revenue-management/"
    "experiments/cpbsd_baselines_v2"
)
# Mirror the baselines_v2 experiment root when run from code_submission.
CODE_ROOT = Path(
    "/Users/sensen/.openclaw/workspace/domains/revenue-management/"
    "project-root/code_submission_project/code_submission/"
    "experiments/cpbsd_baselines_v2"
)
# Use whichever exists.
if CODE_ROOT.exists():
    ROOT = CODE_ROOT

OUT_SAMPLE_K = 5000
N_INSTANCES = 5
N_PRODUCTS = 5


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


def sample_out_of_sample_valuations(setup: dict, out_k: int = OUT_SAMPLE_K) -> np.ndarray:
    rng = np.random.default_rng(int(setup["seed"]) + 99991)
    means = valuation_means(int(setup["n_products"]), setup["heterogeneity"])
    return sample_valuations(
        k=out_k,
        means=means,
        family=setup["dist_family"],
        rho=float(setup["rho"]),
        rng=rng,
    )


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def make_floor_prices(bundle_prices_full: dict, assortments: np.ndarray, c_n: np.ndarray) -> dict:
    """Clip each bundle price to max(price, bundle_cost)."""
    bundle_cost = assortments @ c_n
    clipped = {}
    for idx_str, price in bundle_prices_full.items():
        idx = int(idx_str) if isinstance(idx_str, str) else idx_str
        floor = float(bundle_cost[idx])
        clipped[idx] = max(float(price), floor)
    return clipped


def run_study():
    inst_dir = ROOT / "instances" / "n5"
    res_dir = ROOT / "results"
    plot_dir = ROOT / "plots"
    plot_dir.mkdir(parents=True, exist_ok=True)

    instance_files = sorted(inst_dir.glob("*.msgpack"))
    if len(instance_files) < N_INSTANCES:
        print(f"ERROR: expected {N_INSTANCES} instance files in {inst_dir}, found {len(instance_files)}")
        return

    rows = []

    for idx in range(1, N_INSTANCES + 1):
        instance_id = f"n5_inst{idx:03d}"
        mp = instance_files[idx - 1]
        mb_path = res_dir / f"baseline_mb_n5_inst{idx:03d}.json"
        bsp_path = res_dir / f"baseline_bsp_n5_inst{idx:03d}.json"

        if not mb_path.exists() or not bsp_path.exists():
            print(f"SKIP {instance_id}: missing cached result ({mb_path.exists()=}, {bsp_path.exists()=})")
            continue

        # Load instance data
        v_in, c_n = load_instance(mp)
        setup = read_setup(mp)
        v_out = sample_out_of_sample_valuations(setup)

        # Load cached results
        mb_res = load_json(mb_path)
        bsp_res = load_json(bsp_path)

        assortments = np.asarray(mb_res["assortments"], dtype=int)
        bundle_prices_full = normalize_numeric_keys(mb_res.get("bundle_prices_full", {}))
        bundle_prices_selected = normalize_numeric_keys(mb_res.get("bundle_prices_selected") or mb_res.get("bundle_prices", {}))
        size_prices = normalize_numeric_keys(bsp_res.get("size_prices", {}))

        # Build floor-clipped prices
        bundle_prices_floor = make_floor_prices(bundle_prices_full, assortments, c_n)

        # Evaluate BSP (reference)
        bsp_in = eval_bsp_policy(v_in, c_n, size_prices)
        bsp_out = eval_bsp_policy(v_out, c_n, size_prices)

        # Evaluate 3 MB variants
        variants = [
            ("MB-full", bundle_prices_full),
            ("MB-sel", bundle_prices_selected),
            ("MB-floor", bundle_prices_floor),
        ]

        for variant_name, prices in variants:
            rev_in = eval_mb_policy(v_in, c_n, prices, assortments)
            rev_out = eval_mb_policy(v_out, c_n, prices, assortments)
            rows.append({
                "instance_id": instance_id,
                "variant": variant_name,
                "revenue_in_sample": rev_in,
                "revenue_out_sample": rev_out,
                "bsp_in_sample": bsp_in,
                "bsp_out_sample": bsp_out,
                "ratio_to_bsp_in": rev_in / bsp_in if bsp_in else None,
                "ratio_to_bsp_out": rev_out / bsp_out if bsp_out else None,
                "overfitting_drop_pct": 100.0 * (1.0 - rev_out / rev_in) if rev_in else None,
                "n_prices": len(prices),
            })

        # BSP reference row
        rows.append({
            "instance_id": instance_id,
            "variant": "BSP",
            "revenue_in_sample": bsp_in,
            "revenue_out_sample": bsp_out,
            "bsp_in_sample": bsp_in,
            "bsp_out_sample": bsp_out,
            "ratio_to_bsp_in": 1.0,
            "ratio_to_bsp_out": 1.0,
            "overfitting_drop_pct": 100.0 * (1.0 - bsp_out / bsp_in) if bsp_in else None,
            "n_prices": len(size_prices),
        })

    if not rows:
        print("ERROR: no rows generated")
        return

    # Write CSV
    csv_path = ROOT / "mb_generalization_study.csv"
    fieldnames = [
        "instance_id", "variant", "revenue_in_sample", "revenue_out_sample",
        "bsp_in_sample", "bsp_out_sample", "ratio_to_bsp_in", "ratio_to_bsp_out",
        "overfitting_drop_pct", "n_prices",
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"written: {csv_path}")

    # Generate plot
    _plot_diagnostic(rows, plot_dir)

    # Print summary table
    _print_summary(rows)


def _plot_diagnostic(rows, plot_dir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    variant_order = ["MB-full", "MB-sel", "MB-floor"]
    variant_rows = {v: [] for v in variant_order}
    for row in rows:
        if row["variant"] in variant_rows:
            variant_rows[row["variant"]].append(row)

    labels = variant_order
    x = np.arange(len(labels), dtype=float)

    in_data = []
    out_data = []
    for v in variant_order:
        in_data.append([r["ratio_to_bsp_in"] for r in variant_rows[v] if r["ratio_to_bsp_in"] is not None])
        out_data.append([r["ratio_to_bsp_out"] for r in variant_rows[v] if r["ratio_to_bsp_out"] is not None])

    fig, ax = plt.subplots(figsize=(7.0, 4.8), dpi=180)
    ax.set_facecolor("#ebebeb")
    fig.patch.set_facecolor("white")

    bp_in = ax.boxplot(
        in_data, positions=x - 0.18, widths=0.32,
        patch_artist=True, showfliers=False, manage_ticks=False,
    )
    bp_out = ax.boxplot(
        out_data, positions=x + 0.18, widths=0.32,
        patch_artist=True, showfliers=False, manage_ticks=False,
    )

    for patch in bp_in["boxes"]:
        patch.set(facecolor="#74c0e3", edgecolor="#2b8cbe", linewidth=1.0)
    for key in ("whiskers", "caps", "medians"):
        for artist in bp_in[key]:
            artist.set(color="#2b8cbe", linewidth=1.0)

    for patch in bp_out["boxes"]:
        patch.set(facecolor="#2b8cbe", edgecolor="#1f5d84", linewidth=1.0)
    for key in ("whiskers", "caps", "medians"):
        for artist in bp_out[key]:
            artist.set(color="#1f5d84", linewidth=1.0)

    ax.axhline(1.0, color="#cc6d2d", linestyle="--", linewidth=1.2, label="BSP")
    ax.plot([], [], color="#74c0e3", linewidth=6, label="In-sample")
    ax.plot([], [], color="#2b8cbe", linewidth=6, label="Out-of-sample")

    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Revenue Ratio vs BSP")
    ax.set_title("MB Generalization Diagnostic (N=5)")
    ax.grid(axis="y", color="white", linewidth=1.0)
    ax.set_axisbelow(True)
    ax.legend(loc="upper left", ncol=3, fontsize=8, frameon=True)
    fig.tight_layout()

    plot_path = plot_dir / "mb_generalization_diagnostic.png"
    fig.savefig(plot_path, bbox_inches="tight")
    plt.close(fig)
    print(f"written: {plot_path}")


def _print_summary(rows):
    print()
    print("=" * 95)
    print(f"{'Instance':<14} {'Variant':<10} {'Rev-In':>10} {'Rev-Out':>10} "
          f"{'Drop%':>8} {'vs BSP-In':>10} {'vs BSP-Out':>10} {'#Prices':>8}")
    print("-" * 95)
    for row in rows:
        drop = f"{row['overfitting_drop_pct']:7.2f}%" if row["overfitting_drop_pct"] is not None else "    N/A"
        r_in = f"{row['ratio_to_bsp_in']:.4f}" if row["ratio_to_bsp_in"] is not None else "N/A"
        r_out = f"{row['ratio_to_bsp_out']:.4f}" if row["ratio_to_bsp_out"] is not None else "N/A"
        print(f"{row['instance_id']:<14} {row['variant']:<10} "
              f"{row['revenue_in_sample']:10.4f} {row['revenue_out_sample']:10.4f} "
              f"{drop:>8} {r_in:>10} {r_out:>10} {row['n_prices']:>8}")
    print("=" * 95)

    # Aggregate summary per variant
    print()
    print("Aggregate Summary:")
    print(f"{'Variant':<10} {'Mean Drop%':>12} {'Mean vs BSP-Out':>16}")
    print("-" * 42)
    variants = ["MB-full", "MB-sel", "MB-floor", "BSP"]
    for v in variants:
        vr = [r for r in rows if r["variant"] == v]
        drops = [r["overfitting_drop_pct"] for r in vr if r["overfitting_drop_pct"] is not None]
        outs = [r["ratio_to_bsp_out"] for r in vr if r["ratio_to_bsp_out"] is not None]
        mean_drop = f"{np.mean(drops):.2f}%" if drops else "N/A"
        mean_out = f"{np.mean(outs):.4f}" if outs else "N/A"
        print(f"{v:<10} {mean_drop:>12} {mean_out:>16}")
    print()


if __name__ == "__main__":
    run_study()
