#!/usr/bin/env python3
"""
Analyze MB (Mixed Bundling) solver bundle customer coverage distribution.

Reads MB result JSONs, computes per-bundle customer coverage stats,
and generates CSV, charts, and markdown reports.

Supports two result formats:
  - New format: has 'chosen_bundle_idx_by_customer' → use directly
  - Old format: has only 'bundle_prices' → reconstruct choices from instance data
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def build_assortments(n: int) -> np.ndarray:
    """Build (2^n, n) binary assortment matrix."""
    total = 1 << n
    out = np.zeros((total, n), dtype=int)
    for i in range(total):
        for j in range(n):
            out[i, n - 1 - j] = (i >> j) & 1
    return out


def reconstruct_choices(
    v_kn: np.ndarray,
    c_n: np.ndarray,
    bundle_prices: dict,
    assortments: np.ndarray,
) -> np.ndarray:
    """Reconstruct chosen_bundle_idx from valuations + prices.

    For ties (equal surplus), prefer the bundle with more products
    (matching typical solver behaviour of maximizing purchase).
    """
    k_count = v_kn.shape[0]
    n_bundles = assortments.shape[0]

    revenues = v_kn @ assortments.T  # (k, 2^n)

    prices = np.full(n_bundles, 1e18)
    prices[0] = 0.0  # empty bundle always 0
    for idx_str, price in bundle_prices.items():
        prices[int(idx_str)] = price

    surplus = revenues - prices[np.newaxis, :]  # (k, 2^n)

    # Tie-breaking: for equal surplus, prefer larger bundle_size, then larger index
    bundle_sizes = assortments.sum(axis=1)  # (2^n,)
    # Add tiny perturbation for tie-breaking: prefer larger bundles
    tiebreak = bundle_sizes * 1e-12 + np.arange(n_bundles) * 1e-15
    surplus_adj = surplus + tiebreak[np.newaxis, :]

    chosen = np.argmax(surplus_adj, axis=1)

    # Ensure non-negative surplus for chosen bundle
    for k in range(k_count):
        if surplus[k, chosen[k]] < -1e-9:
            chosen[k] = 0

    return chosen


def load_instance_valuations(instance_path: Path):
    """Load valuations V and costs c from a CPBSD instance msgpack."""
    import msgpack
    import msgpack_numpy as mnp

    with open(instance_path, "rb") as f:
        obj = msgpack.load(f, object_hook=mnp.decode)
    v = np.asarray(obj["valuation_samples_V"], dtype=float)
    c = np.asarray(obj["production_cost_c"], dtype=float)
    return v, c


def find_instance_path(result_path: Path, instance_dirs: list) -> Path | None:
    """Derive instance msgpack path from result filename."""
    stem = result_path.stem  # e.g. cpbsd_instance_001_N5_K50_...__mb
    # Remove __mb suffix
    instance_stem = stem.replace("__mb", "")
    for idir in instance_dirs:
        for sub in [idir] + list(idir.iterdir()) if idir.is_dir() else [idir]:
            if not sub.is_dir():
                continue
            candidate = sub / f"{instance_stem}.msgpack"
            if candidate.exists():
                return candidate
    return None


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------

def analyze_results(result_dir: Path, instance_dir: Path | None, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)

    # Collect MB result files
    mb_files = sorted(result_dir.glob("*mb*.json"))
    if not mb_files:
        mb_files = sorted(result_dir.glob("*MB*.json"))
    if not mb_files:
        print(f"ERROR: No MB result JSON files found in {result_dir}")
        sys.exit(1)

    # Possible instance directories
    instance_dirs = []
    if instance_dir and instance_dir.exists():
        instance_dirs.append(instance_dir)
    # Also check sibling 'instances' directory of result_dir
    sibling_inst = result_dir.parent / "instances"
    if sibling_inst.exists():
        instance_dirs.append(sibling_inst)

    # Process each result file
    all_choices = []      # (bundle_idx, instance_id) tuples
    all_prices = {}       # bundle_idx -> list of prices across instances
    n_products = None
    total_customers = 0
    instance_stats = []
    log_lines = []

    log_lines.append(f"# MB Bundle Coverage Run Log\n")
    log_lines.append(f"Run time: {datetime.now().isoformat()}")
    log_lines.append(f"Result directory: {result_dir}")
    log_lines.append(f"Output directory: {output_dir}")
    log_lines.append(f"MB result files found: {len(mb_files)}\n")

    processed = 0
    skipped = 0

    for fp in mb_files:
        with open(fp) as f:
            result = json.load(f)

        if not result.get("feasible", True):
            log_lines.append(f"SKIP (infeasible): {fp.name}")
            skipped += 1
            continue

        assortments = np.array(result["assortments"])
        n_bundles, n_prod = assortments.shape
        if n_products is None:
            n_products = n_prod
        instance_id = fp.stem

        # Get chosen bundles
        if "chosen_bundle_idx_by_customer" in result:
            chosen = np.array(result["chosen_bundle_idx_by_customer"])
            source = "direct"
        else:
            # Reconstruct from instance data
            inst_path = find_instance_path(fp, instance_dirs)
            if inst_path is None:
                log_lines.append(f"SKIP (no instance file): {fp.name}")
                skipped += 1
                continue
            v, c = load_instance_valuations(inst_path)
            bp = result.get("bundle_prices", result.get("bundle_prices_full", {}))
            chosen = reconstruct_choices(v, c, bp, assortments)
            source = "reconstructed"

        k_count = len(chosen)
        total_customers += k_count

        for idx in chosen:
            all_choices.append(int(idx))

        # Collect prices
        bp = result.get("bundle_prices_selected",
                         result.get("bundle_prices",
                                    result.get("bundle_prices_full", {})))
        for idx_str, price in bp.items():
            idx = int(idx_str)
            all_prices.setdefault(idx, []).append(float(price))

        # Per-instance stats
        counts = Counter(chosen.tolist())
        n_unique = len(counts)
        instance_stats.append({
            "instance": instance_id,
            "k_count": k_count,
            "unique_bundles": n_unique,
            "source": source,
        })

        processed += 1
        log_lines.append(f"OK [{source}]: {fp.name}  K={k_count}  unique_bundles={n_unique}")

    if processed == 0:
        print("ERROR: No results processed successfully")
        sys.exit(1)

    log_lines.append(f"\nProcessed: {processed}, Skipped: {skipped}")
    log_lines.append(f"Total customers pooled: {total_customers}")

    # ---------------------------------------------------------------------------
    # Aggregate coverage stats
    # ---------------------------------------------------------------------------
    bundle_counts = Counter(all_choices)
    n_bundles_total = 1 << n_products

    rows = []
    for bundle_idx in range(n_bundles_total):
        count = bundle_counts.get(bundle_idx, 0)
        assort = build_assortments(n_products)[bundle_idx]
        binary_str = "".join(map(str, assort))
        bundle_size = int(assort.sum())
        prices_list = all_prices.get(bundle_idx, [])
        avg_price = float(np.mean(prices_list)) if prices_list else 0.0
        inst_count = len(prices_list)

        rows.append({
            "bundle_id": bundle_idx,
            "bundle_binary": binary_str,
            "bundle_size": bundle_size,
            "selected_segment_count": count,
            "selected_customer_weight": count / total_customers,
            "avg_price": avg_price,
            "instance_count": inst_count,
        })

    df = pd.DataFrame(rows)
    df = df.sort_values("selected_segment_count", ascending=False).reset_index(drop=True)

    # Compute customer_share and cumulative (only among selected bundles)
    total_weight = df["selected_customer_weight"].sum()
    df["customer_share"] = df["selected_customer_weight"] / total_weight if total_weight > 0 else 0.0
    df["cumulative_customer_share"] = df["customer_share"].cumsum()

    # ---------------------------------------------------------------------------
    # Validation checks
    # ---------------------------------------------------------------------------
    log_lines.append("\n## Validation Checks\n")

    sum_weight = df["selected_customer_weight"].sum()
    log_lines.append(f"1. Sum of selected_customer_weight: {sum_weight:.6f} (expected ~1.0) "
                     f"{'PASS' if abs(sum_weight - 1.0) < 0.01 else 'FAIL'}")

    sum_share = df["customer_share"].sum()
    log_lines.append(f"2. Sum of customer_share: {sum_share:.6f} (expected ~1.0) "
                     f"{'PASS' if abs(sum_share - 1.0) < 0.01 else 'FAIL'}")

    cum = df["cumulative_customer_share"].values
    monotonic = all(cum[i] <= cum[i + 1] + 1e-12 for i in range(len(cum) - 1))
    log_lines.append(f"3. cumulative_customer_share monotonically non-decreasing: "
                     f"{'PASS' if monotonic else 'FAIL'}")

    final_cum = cum[-1] if len(cum) > 0 else 0
    log_lines.append(f"4. Final cumulative_customer_share: {final_cum:.6f} (expected ~1.0) "
                     f"{'PASS' if abs(final_cum - 1.0) < 0.01 else 'FAIL'}")

    # Top-N coverage
    log_lines.append("\n## Top-N Cumulative Coverage\n")
    for n in [1, 5, 10, 20, 50]:
        if n <= len(cum):
            log_lines.append(f"Top-{n}: {cum[n - 1]:.4f} ({cum[n - 1] * 100:.2f}%)")
        else:
            log_lines.append(f"Top-{n}: N/A (only {len(cum)} bundles)")

    # Number of bundles needed for coverage thresholds
    log_lines.append("\n## Bundles Needed for Coverage Thresholds\n")
    for threshold in [0.5, 0.8, 0.9, 0.95, 0.99]:
        idx = np.searchsorted(cum, threshold)
        if idx < len(cum):
            log_lines.append(f"{threshold * 100:.0f}% coverage: {idx + 1} bundles")
        else:
            log_lines.append(f"{threshold * 100:.0f}% coverage: >{len(cum)} bundles")

    # ---------------------------------------------------------------------------
    # Save CSV
    # ---------------------------------------------------------------------------
    csv_path = output_dir / "mb_bundle_coverage_details.csv"
    df.to_csv(csv_path, index=False, float_format="%.6f")
    log_lines.append(f"\nCSV saved: {csv_path}")

    # ---------------------------------------------------------------------------
    # Charts
    # ---------------------------------------------------------------------------

    # Filter to bundles with >0 coverage for charts
    df_sel = df[df["selected_segment_count"] > 0].copy()

    # 1. Bar chart
    fig, ax = plt.subplots(figsize=(12, 6))
    colors = plt.cm.viridis(df_sel["bundle_size"].values / max(n_products, 1))
    bars = ax.bar(range(len(df_sel)), df_sel["customer_share"].values, color=colors)
    ax.set_xlabel("Bundle rank (sorted by coverage)")
    ax.set_ylabel("Customer share")
    ax.set_title(f"MB Bundle Coverage Distribution (N={n_products}, {processed} instances, {total_customers} customers)")

    # Add bundle labels for top 10
    for i in range(min(10, len(df_sel))):
        ax.text(i, df_sel.iloc[i]["customer_share"] + 0.005,
                f'{df_sel.iloc[i]["bundle_binary"]}\n(sz={df_sel.iloc[i]["bundle_size"]})',
                ha="center", va="bottom", fontsize=7, rotation=45)

    # Colorbar for bundle size
    sm = plt.cm.ScalarMappable(cmap="viridis",
                                norm=plt.Normalize(0, n_products))
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, label="Bundle size (# products)")
    plt.tight_layout()
    bar_path = output_dir / "mb_bundle_coverage_bar.png"
    fig.savefig(bar_path, dpi=150)
    plt.close(fig)
    log_lines.append(f"Bar chart saved: {bar_path}")

    # 2. Cumulative curve
    fig, ax = plt.subplots(figsize=(10, 6))
    x_vals = np.arange(1, len(df_sel) + 1)
    ax.plot(x_vals, df_sel["cumulative_customer_share"].values, "b-o", markersize=4)
    ax.set_xlabel("Top-N bundles")
    ax.set_ylabel("Cumulative customer coverage")
    ax.set_title(f"Top-N Bundle Cumulative Coverage (N={n_products}, {processed} instances)")

    # Reference lines
    for level, color in [(0.5, "green"), (0.8, "orange"), (0.9, "red"), (0.95, "purple")]:
        ax.axhline(y=level, color=color, linestyle="--", alpha=0.5, label=f"{level * 100:.0f}%")

    ax.legend(loc="lower right")
    ax.set_ylim(0, 1.05)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    cum_path = output_dir / "mb_bundle_topN_cumulative.png"
    fig.savefig(cum_path, dpi=150)
    plt.close(fig)
    log_lines.append(f"Cumulative chart saved: {cum_path}")

    # ---------------------------------------------------------------------------
    # Experiment markdown
    # ---------------------------------------------------------------------------
    top20_cov = cum[min(19, len(cum) - 1)] if len(cum) > 0 else 0

    # Determine if few bundles cover most demand
    bundles_for_80 = int(np.searchsorted(cum, 0.8)) + 1 if len(cum) > 0 else 0
    bundles_for_90 = int(np.searchsorted(cum, 0.9)) + 1 if len(cum) > 0 else 0

    exp_lines = []
    exp_lines.append("# MB Bundle Customer Coverage Experiment\n")
    exp_lines.append("## Objective\n")
    exp_lines.append("Analyze the distribution of customer demand across bundles in MB (Mixed Bundling)")
    exp_lines.append("solver optimal solutions. Determine whether a small number of bundles covers")
    exp_lines.append("most customer demand.\n")
    exp_lines.append("## Data Source\n")
    exp_lines.append(f"- Result directory: `{result_dir}`")
    exp_lines.append(f"- Instances processed: {processed}")
    exp_lines.append(f"- Instances skipped: {skipped}")
    exp_lines.append(f"- Products per instance (N): {n_products}")
    exp_lines.append(f"- Total bundle space: 2^{n_products} = {1 << n_products} bundles")
    exp_lines.append(f"- Total customers pooled: {total_customers}\n")

    exp_lines.append("## Coverage Definition\n")
    exp_lines.append("- **Customer coverage** = proportion of customers (across all pooled instances)")
    exp_lines.append("  who chose a given bundle in the MB optimal solution.")
    exp_lines.append("- The MB solver uses **uniform customer weights** (1/K per customer),")
    exp_lines.append("  so count-based proportion equals the Ns-weighted version.")
    exp_lines.append("  (See `solve_mb_bsp_on_cpbsd_v2.py` line 182: `weights = np.ones(...) / k_count`)")
    exp_lines.append("- Bundles are ranked by coverage in descending order.")
    exp_lines.append("- `cumulative_customer_share` = running sum of `customer_share` in rank order.\n")

    # Distinguish reconstruction approach
    sources = set(s["source"] for s in instance_stats)
    if "reconstructed" in sources:
        exp_lines.append("## Note on Choice Reconstruction\n")
        exp_lines.append("Some result files used the older format without `chosen_bundle_idx_by_customer`.")
        exp_lines.append("For these, customer choices were reconstructed from valuations + prices")
        exp_lines.append("by computing surplus = v·bundle - price and choosing the max-surplus bundle.")
        exp_lines.append("Tie-breaking may differ slightly from the original MILP solver.\n")

    exp_lines.append("## Key Results\n")
    exp_lines.append(f"- Unique bundles selected (across all instances): {len(df_sel)}")
    exp_lines.append(f"- Bundle space utilization: {len(df_sel)}/{1 << n_products} "
                     f"({len(df_sel) / (1 << n_products) * 100:.1f}%)\n")

    exp_lines.append("### Top-N Cumulative Coverage\n")
    exp_lines.append("| Top-N | Cumulative Coverage |")
    exp_lines.append("|-------|-------------------|")
    for n in [1, 2, 3, 5, 10, 15, 20, 25, 30, 50]:
        if n <= len(cum):
            exp_lines.append(f"| {n} | {cum[n - 1] * 100:.2f}% |")

    exp_lines.append("")
    exp_lines.append("### Coverage Thresholds\n")
    exp_lines.append("| Coverage | Bundles Needed |")
    exp_lines.append("|----------|---------------|")
    for threshold in [0.5, 0.8, 0.9, 0.95, 0.99, 1.0]:
        idx = np.searchsorted(cum, threshold - 1e-9)
        if idx < len(cum):
            exp_lines.append(f"| {threshold * 100:.0f}% | {idx + 1} |")

    exp_lines.append("")
    exp_lines.append("## Top-20 Bundles Detail\n")
    exp_lines.append("| Rank | Bundle ID | Binary | Size | Count | Share | Cumulative | Avg Price |")
    exp_lines.append("|------|-----------|--------|------|-------|-------|------------|-----------|")
    for i, row in df_sel.head(20).iterrows():
        rank = df_sel.index.get_loc(i) + 1
        exp_lines.append(
            f"| {rank} | {int(row['bundle_id'])} | {row['bundle_binary']} | "
            f"{int(row['bundle_size'])} | {int(row['selected_segment_count'])} | "
            f"{row['customer_share'] * 100:.2f}% | {row['cumulative_customer_share'] * 100:.2f}% | "
            f"{row['avg_price']:.2f} |"
        )

    exp_lines.append("")
    exp_lines.append("## Conclusion\n")
    few_cover = bundles_for_80 <= max(5, (1 << n_products) // 4)
    if few_cover:
        exp_lines.append(f"**Yes, a small number of bundles covers most demand.**")
        exp_lines.append(f"Only {bundles_for_80} bundles are needed to cover 80% of customer demand,")
        exp_lines.append(f"and {bundles_for_90} bundles for 90% coverage.")
    else:
        exp_lines.append(f"**Coverage is relatively dispersed.**")
        exp_lines.append(f"{bundles_for_80} bundles are needed for 80% coverage,")
        exp_lines.append(f"and {bundles_for_90} for 90%.")

    exp_lines.append(f"Top-20 bundles cover {top20_cov * 100:.2f}% of total customer demand.")
    exp_lines.append(f"\nThis analysis pooled {total_customers} customer-level choices from {processed} "
                     f"MB solver instances.")

    exp_path = output_dir / "mb_bundle_coverage_experiment.md"
    with open(exp_path, "w") as f:
        f.write("\n".join(exp_lines) + "\n")
    log_lines.append(f"Experiment report saved: {exp_path}")

    # ---------------------------------------------------------------------------
    # Run log
    # ---------------------------------------------------------------------------
    runlog_path = output_dir / "mb_bundle_coverage_runlog.md"
    with open(runlog_path, "w") as f:
        f.write("\n".join(log_lines) + "\n")

    print(f"\n=== MB Bundle Coverage Analysis Complete ===")
    print(f"Instances processed: {processed}")
    print(f"Total customers: {total_customers}")
    print(f"Unique bundles selected: {len(df_sel)}")
    print(f"Top-20 cumulative coverage: {top20_cov * 100:.2f}%")
    print(f"\nOutput files:")
    print(f"  {csv_path}")
    print(f"  {bar_path}")
    print(f"  {cum_path}")
    print(f"  {exp_path}")
    print(f"  {runlog_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="MB Bundle Coverage Analysis")
    parser.add_argument("--result-dir", type=Path, required=True,
                        help="Directory containing MB result JSON files")
    parser.add_argument("--instance-dir", type=Path, default=None,
                        help="Directory containing instance msgpack files (for old-format results)")
    parser.add_argument("--output-dir", type=Path, required=True,
                        help="Output directory for results")
    args = parser.parse_args()

    analyze_results(args.result_dir, args.instance_dir, args.output_dir)


if __name__ == "__main__":
    main()
