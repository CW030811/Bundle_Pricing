#!/usr/bin/env python3
"""
Analyze bundle customer coverage under the native MB (Mixed Bundling) setting.

Reads pre-solved MB-format msgpack datasets (from generate_data_MB.py),
extracts opt_bundles + Ns weights, and computes Ns-weighted coverage.
Generates per-m CSV, charts, comparison with CPBSD, and markdown reports.
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import msgpack
import msgpack_numpy as mnp
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE = Path(__file__).resolve().parents[2]  # code_submission root
DATASET_DIR = BASE / "Dataset"
EXPERIMENT_OUT = Path("/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/mb_native_bundle_coverage")
CPBSD_CSV = Path("/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/mb_bundle_coverage_v2/mb_bundle_coverage_details.csv")

M_CONFIGS = [
    ("m10", "m10_n10_sample_100", 10),
    ("m20", "m20_n10_sample_100", 20),
    ("m30", "m30_n10_sample_100", 30),
]

bin2num = lambda x: int("".join(map(str, [int(v) for v in x])), 2)


# ---------------------------------------------------------------------------
# Load one MB msgpack
# ---------------------------------------------------------------------------
def load_mb_instance(path: Path) -> dict:
    with open(path, "rb") as f:
        d = msgpack.load(f, object_hook=mnp.decode, strict_map_key=False)
    return d


# ---------------------------------------------------------------------------
# Analyze one m-config
# ---------------------------------------------------------------------------
def analyze_m_config(label: str, folder_name: str, m_expected: int, log: list) -> pd.DataFrame | None:
    folder = DATASET_DIR / folder_name
    files = sorted(folder.glob("*.msgpack"))
    if not files:
        log.append(f"SKIP {label}: no files in {folder}")
        return None

    log.append(f"\n## {label} ({folder_name})")
    log.append(f"Files found: {len(files)}")

    n_products = None
    total_samples = 0
    # bundle_idx -> cumulative Ns-weighted coverage across all samples
    weighted_coverage = defaultdict(float)
    # bundle_idx -> unweighted count
    unweighted_count = Counter()
    # bundle_idx -> list of prices
    price_lists = defaultdict(list)
    # bundle_idx -> set of sample indices where it appeared
    instance_sets = defaultdict(set)

    for fi, fp in enumerate(files):
        try:
            d = load_mb_instance(fp)
        except Exception as e:
            log.append(f"  ERROR loading {fp.name}: {e}")
            continue

        m = d["segment_num"]
        n = d["product_num"]
        if n_products is None:
            n_products = n

        opt_bundles = np.array(d["opt_bundles"])  # (m, n) binary
        Ns = np.array(d["Ns"]).flatten()           # (m,)
        opt_prices = d.get("opt_prices", {})

        # Validate Ns
        ns_sum = Ns.sum()
        if abs(ns_sum - 1.0) > 0.01:
            log.append(f"  WARN {fp.name}: Ns sum = {ns_sum:.6f}")

        # opt_bundles has m rows, one per segment
        if opt_bundles.shape[0] != m:
            log.append(f"  WARN {fp.name}: opt_bundles has {opt_bundles.shape[0]} rows, expected {m}")
            continue

        for k in range(m):
            bundle_binary = opt_bundles[k]
            bundle_idx = bin2num(bundle_binary)
            weighted_coverage[bundle_idx] += Ns[k]
            unweighted_count[bundle_idx] += 1
            instance_sets[bundle_idx].add(fi)

        # Collect prices
        for idx_key, price in opt_prices.items():
            price_lists[int(idx_key)].append(float(price))

        total_samples += 1

    if total_samples == 0:
        log.append(f"  No valid samples processed for {label}")
        return None

    log.append(f"Samples processed: {total_samples}")
    log.append(f"Unique bundles selected: {len(weighted_coverage)}")
    log.append(f"Bundle space: 2^{n_products} = {1 << n_products}")

    # Build DataFrame
    bundle_space = 1 << n_products
    rows = []
    for bundle_idx in range(bundle_space):
        wc = weighted_coverage.get(bundle_idx, 0.0)
        uc = unweighted_count.get(bundle_idx, 0)
        prices = price_lists.get(bundle_idx, [])
        binary_str = format(bundle_idx, f"0{n_products}b")
        bundle_size = sum(int(b) for b in binary_str)

        rows.append({
            "bundle_id": bundle_idx,
            "bundle_binary": binary_str,
            "bundle_size": bundle_size,
            "selected_segment_count": uc,
            "selected_customer_weight": wc / total_samples,  # average per-sample Ns-weight
            "avg_price": float(np.mean(prices)) if prices else 0.0,
            "instance_count": len(instance_sets.get(bundle_idx, set())),
        })

    df = pd.DataFrame(rows)
    df = df.sort_values("selected_customer_weight", ascending=False).reset_index(drop=True)

    total_weight = df["selected_customer_weight"].sum()
    df["customer_share"] = df["selected_customer_weight"] / total_weight if total_weight > 0 else 0.0
    df["cumulative_customer_share"] = df["customer_share"].cumsum()

    # Validation
    log.append(f"\n### Validation ({label})")
    log.append(f"Sum of selected_customer_weight: {total_weight:.6f} (expected ~1.0) "
               f"{'PASS' if abs(total_weight - 1.0) < 0.01 else 'FAIL'}")
    cum = df["cumulative_customer_share"].values
    monotonic = all(cum[i] <= cum[i + 1] + 1e-12 for i in range(len(cum) - 1))
    log.append(f"Cumulative monotonic: {'PASS' if monotonic else 'FAIL'}")
    log.append(f"Final cumulative: {cum[-1]:.6f} {'PASS' if abs(cum[-1] - 1.0) < 0.01 else 'FAIL'}")

    # Top-N
    log.append(f"\n### Top-N Cumulative Coverage ({label})")
    for topn in [1, 2, 3, 5, 10, 20, 50, 100]:
        if topn <= len(cum):
            log.append(f"Top-{topn}: {cum[topn-1]*100:.2f}%")

    # Bundles needed
    log.append(f"\n### Bundles Needed ({label})")
    for threshold in [0.5, 0.8, 0.9, 0.95, 0.99]:
        idx = int(np.searchsorted(cum, threshold))
        log.append(f"{threshold*100:.0f}%: {idx+1} bundles")

    return df


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    EXPERIMENT_OUT.mkdir(parents=True, exist_ok=True)
    log = [f"# MB Native Bundle Coverage Run Log\n",
           f"Run time: {datetime.now().isoformat()}",
           f"Dataset directory: {DATASET_DIR}",
           f"Output directory: {EXPERIMENT_OUT}\n"]

    results = {}  # label -> DataFrame

    for label, folder_name, m_val in M_CONFIGS:
        df = analyze_m_config(label, folder_name, m_val, log)
        if df is not None:
            results[label] = df
            csv_path = EXPERIMENT_OUT / f"mb_native_coverage_{label}.csv"
            df.to_csv(csv_path, index=False, float_format="%.6f")
            log.append(f"CSV saved: {csv_path}")

    if not results:
        print("ERROR: No results produced")
        sys.exit(1)

    # -----------------------------------------------------------------------
    # Charts
    # -----------------------------------------------------------------------

    # 1. Bar chart — one subplot per m
    n_configs = len(results)
    fig, axes = plt.subplots(1, n_configs, figsize=(6 * n_configs, 5), sharey=True)
    if n_configs == 1:
        axes = [axes]

    for ax, (label, df) in zip(axes, results.items()):
        df_sel = df[df["selected_segment_count"] > 0].head(30)
        n_products = len(df_sel.iloc[0]["bundle_binary"]) if len(df_sel) > 0 else 10
        colors = plt.cm.viridis(df_sel["bundle_size"].values / max(n_products, 1))
        ax.bar(range(len(df_sel)), df_sel["customer_share"].values, color=colors)
        ax.set_xlabel("Bundle rank")
        ax.set_ylabel("Customer share (Ns-weighted)")
        ax.set_title(f"{label} (top 30 bundles)")

    fig.suptitle("MB Native: Bundle Coverage Distribution", fontsize=14)
    plt.tight_layout()
    bar_path = EXPERIMENT_OUT / "mb_native_coverage_bar.png"
    fig.savefig(bar_path, dpi=150)
    plt.close(fig)
    log.append(f"\nBar chart saved: {bar_path}")

    # 2. Cumulative curve — all m values
    fig, ax = plt.subplots(figsize=(10, 6))
    colors_m = {"m10": "blue", "m20": "green", "m30": "red"}

    for label, df in results.items():
        df_sel = df[df["selected_segment_count"] > 0]
        x = np.arange(1, len(df_sel) + 1)
        ax.plot(x, df_sel["cumulative_customer_share"].values,
                "-o", markersize=2, color=colors_m.get(label, "black"),
                label=f"MB {label} ({len(df_sel)} active bundles)")

    for level, ls in [(0.5, "--"), (0.8, "--"), (0.9, "--"), (0.95, ":")]:
        ax.axhline(y=level, color="gray", linestyle=ls, alpha=0.4,
                   label=f"{level*100:.0f}%" if level == 0.5 else "")

    ax.set_xlabel("Top-N bundles")
    ax.set_ylabel("Cumulative customer coverage (Ns-weighted)")
    ax.set_title("MB Native: Top-N Bundle Cumulative Coverage")
    ax.legend(loc="lower right")
    ax.set_ylim(0, 1.05)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    cum_path = EXPERIMENT_OUT / "mb_native_topN_cumulative.png"
    fig.savefig(cum_path, dpi=150)
    plt.close(fig)
    log.append(f"Cumulative chart saved: {cum_path}")

    # 3. Comparison with CPBSD
    fig, ax = plt.subplots(figsize=(10, 6))

    for label, df in results.items():
        df_sel = df[df["selected_segment_count"] > 0]
        n_total = len(df)  # total bundle space (1024)
        x_frac = np.arange(1, len(df_sel) + 1) / n_total
        ax.plot(x_frac, df_sel["cumulative_customer_share"].values,
                "-", linewidth=2, color=colors_m.get(label, "black"),
                label=f"MB {label} (n=10, {n_total} bundles)")

    # Load CPBSD
    if CPBSD_CSV.exists():
        cpbsd_df = pd.read_csv(CPBSD_CSV)
        cpbsd_sel = cpbsd_df[cpbsd_df["selected_segment_count"] > 0].sort_values(
            "customer_share", ascending=False).reset_index(drop=True)
        cpbsd_sel["cumulative_customer_share"] = cpbsd_sel["customer_share"].cumsum()
        n_cpbsd_total = len(cpbsd_df)
        x_frac_cpbsd = np.arange(1, len(cpbsd_sel) + 1) / n_cpbsd_total
        ax.plot(x_frac_cpbsd, cpbsd_sel["cumulative_customer_share"].values,
                "-s", linewidth=2, markersize=4, color="orange",
                label=f"CPBSD (n=5, {n_cpbsd_total} bundles, uniform weights)")

    for level, ls in [(0.5, "--"), (0.8, "--"), (0.9, "--")]:
        ax.axhline(y=level, color="gray", linestyle=ls, alpha=0.4)

    ax.set_xlabel("Fraction of bundle space (Top-N / total bundles)")
    ax.set_ylabel("Cumulative customer coverage")
    ax.set_title("Bundle Coverage: MB Native (Ns-weighted) vs CPBSD (uniform)")
    ax.legend(loc="lower right")
    ax.set_ylim(0, 1.05)
    ax.set_xlim(0, 1.0)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    comp_path = EXPERIMENT_OUT / "mb_vs_cpbsd_comparison.png"
    fig.savefig(comp_path, dpi=150)
    plt.close(fig)
    log.append(f"Comparison chart saved: {comp_path}")

    # -----------------------------------------------------------------------
    # Experiment report
    # -----------------------------------------------------------------------
    exp = []
    exp.append("# MB Native Bundle Customer Coverage Experiment\n")
    exp.append("## Objective\n")
    exp.append("Analyze bundle coverage under the original MB (Mixed Bundling) data setting")
    exp.append("with non-uniform Ns segment weights, and compare with CPBSD-setting results.\n")

    exp.append("## Data Source\n")
    exp.append("| Config | Dataset | m (segments) | n (products) | Bundle space | Samples |")
    exp.append("|--------|---------|-------------|-------------|-------------|---------|")
    for label, folder_name, m_val in M_CONFIGS:
        if label in results:
            exp.append(f"| {label} | `{folder_name}` | {m_val} | 10 | 1024 | 100 |")
    exp.append("")

    exp.append("## Coverage Definition\n")
    exp.append("- **Ns-weighted coverage**: For each segment k choosing bundle B,")
    exp.append("  add `Ns[k]` to that bundle's coverage. Since `sum(Ns) = 1` per sample,")
    exp.append("  total coverage per sample = 1.0.")
    exp.append("- Averaged across 100 samples per m-value.")
    exp.append("- Bundles ranked by average Ns-weighted coverage, descending.")
    exp.append("- This is the TRUE Ns-weighted metric (non-uniform segment weights),")
    exp.append("  unlike the CPBSD setting which uses uniform 1/K weights.\n")

    exp.append("## Key Results\n")

    for label, df in results.items():
        df_sel = df[df["selected_segment_count"] > 0]
        cum = df_sel["cumulative_customer_share"].values
        exp.append(f"### {label}\n")
        exp.append(f"- Active bundles: {len(df_sel)} / 1024 ({len(df_sel)/1024*100:.1f}%)")

        exp.append("\n| Top-N | Cumulative Coverage |")
        exp.append("|-------|-------------------|")
        for topn in [1, 2, 3, 5, 10, 20, 50]:
            if topn <= len(cum):
                exp.append(f"| {topn} | {cum[topn-1]*100:.2f}% |")

        exp.append("\n| Coverage | Bundles Needed |")
        exp.append("|----------|---------------|")
        for threshold in [0.5, 0.8, 0.9, 0.95, 0.99]:
            idx = int(np.searchsorted(cum, threshold))
            if idx < len(cum):
                exp.append(f"| {threshold*100:.0f}% | {idx+1} |")
        exp.append("")

    # Top-20 detail for m10
    if "m10" in results:
        df_m10 = results["m10"]
        df_m10_sel = df_m10[df_m10["selected_segment_count"] > 0].head(20)
        exp.append("### Top-20 Bundles Detail (m10)\n")
        exp.append("| Rank | ID | Binary | Size | Count | Ns-Share | Cumulative | Avg Price |")
        exp.append("|------|----|--------|------|-------|----------|------------|-----------|")
        for i, (_, row) in enumerate(df_m10_sel.iterrows()):
            exp.append(
                f"| {i+1} | {int(row['bundle_id'])} | {row['bundle_binary']} | "
                f"{int(row['bundle_size'])} | {int(row['selected_segment_count'])} | "
                f"{row['customer_share']*100:.2f}% | {row['cumulative_customer_share']*100:.2f}% | "
                f"{row['avg_price']:.2f} |"
            )
        exp.append("")

    # Comparison section
    exp.append("## Comparison: MB Native vs CPBSD\n")
    exp.append("| Metric | CPBSD (n=5, K=50) | MB m=10 | MB m=20 | MB m=30 |")
    exp.append("|--------|-------------------|---------|---------|---------|")

    cpbsd_cum = None
    if CPBSD_CSV.exists():
        cpbsd_df = pd.read_csv(CPBSD_CSV)
        cpbsd_sel = cpbsd_df[cpbsd_df["selected_segment_count"] > 0].sort_values(
            "customer_share", ascending=False).reset_index(drop=True)
        cpbsd_sel["cumulative_customer_share"] = cpbsd_sel["customer_share"].cumsum()
        cpbsd_cum = cpbsd_sel["cumulative_customer_share"].values

    def get_topn(cum, n):
        return f"{cum[n-1]*100:.1f}%" if cum is not None and n <= len(cum) else "N/A"

    def get_threshold(cum, t):
        if cum is None:
            return "N/A"
        idx = int(np.searchsorted(cum, t))
        return str(idx + 1) if idx < len(cum) else "N/A"

    cums = {}
    for label, df in results.items():
        cums[label] = df[df["selected_segment_count"] > 0]["cumulative_customer_share"].values

    exp.append(f"| Bundle space | 32 | 1024 | 1024 | 1024 |")
    exp.append(f"| Active bundles | {len(cpbsd_sel) if cpbsd_cum is not None else 'N/A'} "
               f"| {len(results.get('m10', pd.DataFrame()).query('selected_segment_count > 0'))} "
               f"| {len(results.get('m20', pd.DataFrame()).query('selected_segment_count > 0'))} "
               f"| {len(results.get('m30', pd.DataFrame()).query('selected_segment_count > 0'))} |")
    exp.append(f"| Segment weights | uniform 1/K | Ns (non-uniform) | Ns | Ns |")

    for topn in [1, 5, 10, 20]:
        row = f"| Top-{topn} coverage | {get_topn(cpbsd_cum, topn)}"
        for label in ["m10", "m20", "m30"]:
            row += f" | {get_topn(cums.get(label), topn)}"
        row += " |"
        exp.append(row)

    for t in [0.5, 0.8, 0.9]:
        row = f"| Bundles for {t*100:.0f}% | {get_threshold(cpbsd_cum, t)}"
        for label in ["m10", "m20", "m30"]:
            row += f" | {get_threshold(cums.get(label), t)}"
        row += " |"
        exp.append(row)

    exp.append("")
    exp.append("## Conclusion\n")

    # Determine if MB is more concentrated
    for label in ["m10", "m20", "m30"]:
        if label in cums:
            cum = cums[label]
            b80 = int(np.searchsorted(cum, 0.8)) + 1
            b90 = int(np.searchsorted(cum, 0.9)) + 1
            top5 = cum[4] if len(cum) >= 5 else 0
            exp.append(f"- **{label}**: Top-5 bundles cover {top5*100:.1f}% of Ns-weighted demand. "
                       f"Need {b80} bundles for 80%, {b90} for 90%.")

    if cpbsd_cum is not None:
        b80_cpbsd = int(np.searchsorted(cpbsd_cum, 0.8)) + 1
        exp.append(f"- **CPBSD**: Need {b80_cpbsd} bundles for 80% (out of 32 total).")

    exp.append("")

    exp_path = EXPERIMENT_OUT / "mb_native_bundle_coverage_experiment.md"
    with open(exp_path, "w") as f:
        f.write("\n".join(exp) + "\n")
    log.append(f"\nExperiment report saved: {exp_path}")

    # -----------------------------------------------------------------------
    # Run log
    # -----------------------------------------------------------------------
    runlog_path = EXPERIMENT_OUT / "mb_native_bundle_coverage_runlog.md"
    with open(runlog_path, "w") as f:
        f.write("\n".join(log) + "\n")

    # Summary
    print("\n=== MB Native Bundle Coverage Analysis Complete ===")
    for label, df in results.items():
        df_sel = df[df["selected_segment_count"] > 0]
        cum = df_sel["cumulative_customer_share"].values
        top20 = cum[min(19, len(cum) - 1)] if len(cum) > 0 else 0
        print(f"  {label}: {len(df_sel)} active bundles, Top-20 coverage = {top20*100:.2f}%")
    print(f"\nOutput: {EXPERIMENT_OUT}")


if __name__ == "__main__":
    main()
