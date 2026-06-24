"""
FCP vs PCP Cutoff Sensitivity Comparison

Merges results from FCP and PCP cutoff sensitivity experiments,
computes average metrics by cutoff, and generates comparison plots.

Inputs:
- cutoff_sensitivity_results.csv (FCP, 90 samples)
- cutoff_sensitivity_PCP_results.csv (PCP, 30 samples)

Outputs:
- cutoff_sensitivity_FCP_PCP_combined.csv
- Comparison plots: revenue, time, metrics, pareto
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# Configuration
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FCP_CSV = os.path.join(_SCRIPT_DIR, "cutoff_sensitivity_results.csv")
PCP_CSV = os.path.join(_SCRIPT_DIR, "cutoff_sensitivity_PCP_results.csv")
OUTPUT_CSV = "cutoff_sensitivity_FCP_PCP_combined.csv"
OUTPUT_REVENUE_PNG = "cutoff_comparison_FCP_PCP_revenue.png"
OUTPUT_TIME_PNG = "cutoff_comparison_FCP_PCP_time.png"
OUTPUT_METRICS_PNG = "cutoff_comparison_FCP_PCP_metrics.png"
OUTPUT_PARETO_PNG = "cutoff_comparison_FCP_PCP_pareto.png"
OUTPUT_COMBINED_PNG = "cutoff_comparison_FCP_PCP_combined.png"

CUTOFFS = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
METRIC_COLS = ["revenue_ratio", "time_ratio", "accuracy", "precision", "recall", "tpr", "tnr", "fpr", "fnr", "error_rate"]


def load_and_merge_data():
    """Load FCP and PCP CSV files, add strategy column, merge."""
    if not os.path.exists(FCP_CSV):
        raise FileNotFoundError(f"FCP CSV not found: {FCP_CSV}")
    if not os.path.exists(PCP_CSV):
        raise FileNotFoundError(f"PCP CSV not found: {PCP_CSV}")
    
    df_fcp = pd.read_csv(FCP_CSV)
    df_pcp = pd.read_csv(PCP_CSV)
    
    df_fcp["strategy"] = "FCP"
    df_pcp["strategy"] = "PCP"
    
    df_combined = pd.concat([df_fcp, df_pcp], ignore_index=True)
    return df_combined


def aggregate_by_cutoff(df):
    """Aggregate by cutoff and strategy, compute mean and std."""
    agg_dict = {}
    for col in METRIC_COLS:
        agg_dict[col] = ["mean", "std", "count"]
    
    grouped = df.groupby(["cutoff", "strategy"]).agg(agg_dict).reset_index()
    
    # Flatten column names: handle MultiIndex columns
    if isinstance(grouped.columns, pd.MultiIndex):
        new_cols = []
        for col in grouped.columns:
            if col[0] in ["cutoff", "strategy"]:
                new_cols.append(col[0])
            else:
                new_cols.append(f"{col[0]}_{col[1]}")
        grouped.columns = new_cols
    else:
        # Already flat
        pass
    
    return grouped


def compute_averages_by_cutoff(df):
    """Compute average metrics for each cutoff across both strategies."""
    results = {}
    for cutoff in CUTOFFS:
        cutoff_data = df[df["cutoff"] == cutoff]
        if len(cutoff_data) == 0:
            continue
        
        results[cutoff] = {}
        for col in METRIC_COLS:
            valid = cutoff_data[col].dropna()
            if len(valid) > 0:
                results[cutoff][f"{col}_mean"] = valid.mean()
                results[cutoff][f"{col}_std"] = valid.std() if len(valid) > 1 else 0.0
                results[cutoff][f"{col}_count"] = len(valid)
            else:
                results[cutoff][f"{col}_mean"] = np.nan
                results[cutoff][f"{col}_std"] = np.nan
                results[cutoff][f"{col}_count"] = 0
    
    return results


def plot_revenue_comparison(df_agg):
    """Plot Revenue Ratio comparison: FCP vs PCP."""
    fig, ax = plt.subplots(figsize=(8, 5))
    
    for strategy in ["FCP", "PCP"]:
        data = df_agg[df_agg["strategy"] == strategy].sort_values("cutoff")
        cutoffs = data["cutoff"].values
        means = data["revenue_ratio_mean"].values
        stds = data["revenue_ratio_std"].values
        
        ax.plot(cutoffs, means, "o-", linewidth=2, markersize=8, label=strategy, alpha=0.85)
        ax.fill_between(cutoffs, means - stds, means + stds, alpha=0.2)
    
    ax.axvline(x=0.5, color="gray", linestyle="--", alpha=0.5, label="Default (0.5)")
    ax.set_xlabel("Cutoff Threshold")
    ax.set_ylabel("Revenue Ratio")
    ax.set_title("FCP vs PCP: Revenue Ratio Comparison")
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.set_xticks(CUTOFFS)
    plt.tight_layout()
    plt.savefig(OUTPUT_REVENUE_PNG, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Revenue comparison plot saved to {OUTPUT_REVENUE_PNG}")


def plot_time_comparison(df_agg):
    """Plot Time Ratio comparison: FCP vs PCP."""
    fig, ax = plt.subplots(figsize=(8, 5))
    
    for strategy in ["FCP", "PCP"]:
        data = df_agg[df_agg["strategy"] == strategy].sort_values("cutoff")
        cutoffs = data["cutoff"].values
        means = data["time_ratio_mean"].values
        stds = data["time_ratio_std"].values
        
        valid = np.isfinite(means) & (means < 1e10)
        if np.any(valid):
            ax.plot(cutoffs[valid], means[valid], "o-", linewidth=2, markersize=8, label=strategy, alpha=0.85)
            ax.fill_between(cutoffs[valid], means[valid] - stds[valid], means[valid] + stds[valid], alpha=0.2)
    
    ax.axvline(x=0.5, color="gray", linestyle="--", alpha=0.5, label="Default (0.5)")
    ax.axhline(y=1.0, color="gray", linestyle=":", alpha=0.5, label="Time=Baseline")
    ax.set_xlabel("Cutoff Threshold")
    ax.set_ylabel("Time Ratio")
    ax.set_title("FCP vs PCP: Time Ratio Comparison")
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.set_xticks(CUTOFFS)
    plt.tight_layout()
    plt.savefig(OUTPUT_TIME_PNG, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Time comparison plot saved to {OUTPUT_TIME_PNG}")


def plot_metrics_comparison(df_agg):
    """Plot bundle prediction metrics comparison."""
    fig, axes = plt.subplots(2, 2, figsize=(12, 10), sharex=True)
    metrics_to_plot = [
        ("accuracy", "Accuracy", axes[0, 0]),
        ("precision", "Precision", axes[0, 1]),
        ("recall", "Recall", axes[1, 0]),
        ("fnr", "FNR", axes[1, 1]),
    ]
    
    for metric_name, metric_label, ax in metrics_to_plot:
        for strategy in ["FCP", "PCP"]:
            data = df_agg[df_agg["strategy"] == strategy].sort_values("cutoff")
            cutoffs = data["cutoff"].values
            means = data[f"{metric_name}_mean"].values
            
            ax.plot(cutoffs, means, "o-", linewidth=2, markersize=6, label=strategy, alpha=0.85)
        
        ax.axvline(x=0.5, color="gray", linestyle="--", alpha=0.5)
        ax.set_ylabel(metric_label)
        ax.set_xlabel("Cutoff Threshold" if ax == axes[1, 0] or ax == axes[1, 1] else "")
        ax.legend()
        ax.grid(True, alpha=0.3)
        ax.set_xticks(CUTOFFS)
    
    fig.suptitle("FCP vs PCP: Bundle Prediction Metrics Comparison", fontsize=14, fontweight="bold")
    plt.tight_layout()
    plt.savefig(OUTPUT_METRICS_PNG, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Metrics comparison plot saved to {OUTPUT_METRICS_PNG}")


def plot_combined_comparison(df_agg, df_combined):
    """Plot combined comparison: Revenue, Time, and Metrics (Accuracy, Recall only) in one figure."""
    fig = plt.figure(figsize=(16, 10))
    gs = fig.add_gridspec(2, 2, hspace=0.3, wspace=0.3)
    
    # Row 0: Revenue (left) and Time (right)
    ax_rev = fig.add_subplot(gs[0, 0])
    ax_time = fig.add_subplot(gs[0, 1])
    
    # Revenue plot
    for strategy in ["FCP", "PCP"]:
        data = df_agg[df_agg["strategy"] == strategy].sort_values("cutoff")
        cutoffs = data["cutoff"].values
        means = data["revenue_ratio_mean"].values
        stds = data["revenue_ratio_std"].values
        
        ax_rev.plot(cutoffs, means, "o-", linewidth=2, markersize=8, label=strategy, alpha=0.85)
        ax_rev.fill_between(cutoffs, means - stds, means + stds, alpha=0.2)
    
    # Combined average for Revenue
    combined_means = []
    combined_stds = []
    for cutoff in CUTOFFS:
        cutoff_data = df_combined[df_combined["cutoff"] == cutoff]["revenue_ratio"].dropna()
        if len(cutoff_data) > 0:
            combined_means.append(cutoff_data.mean())
            combined_stds.append(cutoff_data.std() if len(cutoff_data) > 1 else 0.0)
        else:
            combined_means.append(np.nan)
            combined_stds.append(np.nan)
    
    combined_means = np.array(combined_means)
    combined_stds = np.array(combined_stds)
    valid = np.isfinite(combined_means)
    
    if np.any(valid):
        ax_rev.plot(np.array(CUTOFFS)[valid], combined_means[valid], "s--", linewidth=2, 
                   markersize=8, label="FCP+PCP Average", color="C2", alpha=0.85)
        ax_rev.fill_between(np.array(CUTOFFS)[valid], combined_means[valid] - combined_stds[valid], 
                            combined_means[valid] + combined_stds[valid], alpha=0.15, color="C2")
    
    ax_rev.axvline(x=0.5, color="gray", linestyle="--", alpha=0.5)
    ax_rev.set_xlabel("Cutoff Threshold")
    ax_rev.set_ylabel("Revenue Ratio")
    ax_rev.set_title("(a) Revenue Ratio Comparison", fontsize=12, fontweight="bold")
    ax_rev.legend()
    ax_rev.grid(True, alpha=0.3)
    ax_rev.set_xticks(CUTOFFS)
    
    # Time plot
    for strategy in ["FCP", "PCP"]:
        data = df_agg[df_agg["strategy"] == strategy].sort_values("cutoff")
        cutoffs = data["cutoff"].values
        means = data["time_ratio_mean"].values
        stds = data["time_ratio_std"].values
        
        valid = np.isfinite(means) & (means < 1e10)
        if np.any(valid):
            ax_time.plot(cutoffs[valid], means[valid], "o-", linewidth=2, markersize=8, label=strategy, alpha=0.85)
            ax_time.fill_between(cutoffs[valid], means[valid] - stds[valid], means[valid] + stds[valid], alpha=0.2)
    
    ax_time.axvline(x=0.5, color="gray", linestyle="--", alpha=0.5)
    ax_time.axhline(y=1.0, color="gray", linestyle=":", alpha=0.5)
    ax_time.set_xlabel("Cutoff Threshold")
    ax_time.set_ylabel("Time Ratio")
    ax_time.set_title("(b) Time Ratio Comparison", fontsize=12, fontweight="bold")
    ax_time.legend()
    ax_time.grid(True, alpha=0.3)
    ax_time.set_xticks(CUTOFFS)
    
    # Row 1: Accuracy (left) and Recall (right) only
    metrics_to_plot = [
        ("accuracy", "Accuracy", fig.add_subplot(gs[1, 0])),
        ("recall", "Recall", fig.add_subplot(gs[1, 1])),
    ]
    
    for metric_name, metric_label, ax in metrics_to_plot:
        for strategy in ["FCP", "PCP"]:
            data = df_agg[df_agg["strategy"] == strategy].sort_values("cutoff")
            cutoffs = data["cutoff"].values
            means = data[f"{metric_name}_mean"].values
            
            ax.plot(cutoffs, means, "o-", linewidth=2, markersize=6, label=strategy, alpha=0.85)
        
        ax.axvline(x=0.5, color="gray", linestyle="--", alpha=0.5)
        ax.set_ylabel(metric_label)
        ax.set_xlabel("Cutoff Threshold")
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.3)
        ax.set_xticks(CUTOFFS)
    
    fig.suptitle("FCP vs PCP: Cutoff Sensitivity Comparison", fontsize=16, fontweight="bold", y=0.995)
    plt.savefig(OUTPUT_COMBINED_PNG, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Combined comparison plot saved to {OUTPUT_COMBINED_PNG}")


def plot_pareto_comparison(df_agg):
    """Plot Pareto comparison: Revenue vs Time for FCP and PCP."""
    fig, ax = plt.subplots(figsize=(8, 6))
    
    colors = {"FCP": "C0", "PCP": "C1"}
    markers = {"FCP": "o", "PCP": "s"}
    
    for strategy in ["FCP", "PCP"]:
        data = df_agg[df_agg["strategy"] == strategy].sort_values("cutoff")
        time_means = data["time_ratio_mean"].values
        rev_means = data["revenue_ratio_mean"].values
        
        valid = np.isfinite(time_means) & np.isfinite(rev_means) & (time_means < 1e10)
        if np.any(valid):
            time_valid = time_means[valid]
            rev_valid = rev_means[valid]
            cutoffs_valid = data["cutoff"].values[valid]
            
            # Scatter points
            ax.scatter(time_valid, rev_valid, s=120, c=colors[strategy], marker=markers[strategy],
                      label=strategy, alpha=0.85, edgecolors="black", linewidths=0.5, zorder=5)
            
            # Annotate cutoff values
            for t, r, c in zip(time_valid, rev_valid, cutoffs_valid):
                ax.annotate(f"{c:.1f}", (t, r), xytext=(6, 6), textcoords="offset points",
                           fontsize=8, fontweight="bold", alpha=0.8)
            
            # Pareto frontier for this strategy
            order = np.argsort(time_valid)
            pareto_x, pareto_y = [], []
            max_rev = -np.inf
            for i in order:
                if rev_valid[i] >= max_rev:
                    max_rev = rev_valid[i]
                    pareto_x.append(time_valid[i])
                    pareto_y.append(rev_valid[i])
            
            if len(pareto_x) >= 2:
                ax.plot(pareto_x, pareto_y, "--", linewidth=2, alpha=0.6,
                       color=colors[strategy], label=f"{strategy} Pareto")
    
    ax.axvline(x=1.0, color="gray", linestyle=":", alpha=0.5, label="Time=Baseline")
    ax.set_xlabel("Time Ratio (Lower is Better)")
    ax.set_ylabel("Revenue Ratio (Higher is Better)")
    ax.set_title("FCP vs PCP: Revenue vs Time Trade-off (Pareto)")
    ax.legend(loc="best", fontsize=9)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(OUTPUT_PARETO_PNG, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Pareto comparison plot saved to {OUTPUT_PARETO_PNG}")


def print_summary_table(df_agg):
    """Print summary comparison table."""
    print("\n" + "=" * 80)
    print("FCP vs PCP Cutoff Sensitivity Comparison Summary")
    print("=" * 80)
    
    print("\nRevenue Ratio by Cutoff:")
    print("-" * 80)
    print(f"{'Cutoff':>6} | {'FCP Mean':>10} | {'FCP Std':>10} | {'PCP Mean':>10} | {'PCP Std':>10} | {'Diff':>10}")
    print("-" * 80)
    for cutoff in CUTOFFS:
        fcp_data = df_agg[(df_agg["cutoff"] == cutoff) & (df_agg["strategy"] == "FCP")]
        pcp_data = df_agg[(df_agg["cutoff"] == cutoff) & (df_agg["strategy"] == "PCP")]
        
        fcp_mean = fcp_data["revenue_ratio_mean"].values[0] if len(fcp_data) > 0 else np.nan
        fcp_std = fcp_data["revenue_ratio_std"].values[0] if len(fcp_data) > 0 else np.nan
        pcp_mean = pcp_data["revenue_ratio_mean"].values[0] if len(pcp_data) > 0 else np.nan
        pcp_std = pcp_data["revenue_ratio_std"].values[0] if len(pcp_data) > 0 else np.nan
        
        diff = (pcp_mean - fcp_mean) if (np.isfinite(pcp_mean) and np.isfinite(fcp_mean)) else np.nan
        marker = " <--" if cutoff == 0.5 else ""
        
        fcp_str = f"{fcp_mean:.4f}±{fcp_std:.4f}" if np.isfinite(fcp_mean) else "N/A"
        pcp_str = f"{pcp_mean:.4f}±{pcp_std:.4f}" if np.isfinite(pcp_mean) else "N/A"
        diff_str = f"{diff:+.4f}" if np.isfinite(diff) else "N/A"
        
        print(f"{cutoff:>6.1f} | {fcp_str:>10} | {pcp_str:>10} | {diff_str:>10}{marker}")
    
    print("\nTime Ratio by Cutoff:")
    print("-" * 80)
    print(f"{'Cutoff':>6} | {'FCP Mean':>10} | {'PCP Mean':>10} | {'Diff':>10}")
    print("-" * 80)
    for cutoff in CUTOFFS:
        fcp_data = df_agg[(df_agg["cutoff"] == cutoff) & (df_agg["strategy"] == "FCP")]
        pcp_data = df_agg[(df_agg["cutoff"] == cutoff) & (df_agg["strategy"] == "PCP")]
        
        fcp_mean = fcp_data["time_ratio_mean"].values[0] if len(fcp_data) > 0 else np.nan
        pcp_mean = pcp_data["time_ratio_mean"].values[0] if len(pcp_data) > 0 else np.nan
        
        if np.isfinite(fcp_mean) and fcp_mean < 1e10:
            fcp_mean = fcp_mean
        else:
            fcp_mean = np.nan
        if np.isfinite(pcp_mean) and pcp_mean < 1e10:
            pcp_mean = pcp_mean
        else:
            pcp_mean = np.nan
        
        diff = (pcp_mean - fcp_mean) if (np.isfinite(pcp_mean) and np.isfinite(fcp_mean)) else np.nan
        marker = " <--" if cutoff == 0.5 else ""
        
        fcp_str = f"{fcp_mean:.4f}" if np.isfinite(fcp_mean) else "N/A"
        pcp_str = f"{pcp_mean:.4f}" if np.isfinite(pcp_mean) else "N/A"
        diff_str = f"{diff:+.4f}" if np.isfinite(diff) else "N/A"
        
        print(f"{cutoff:>6.1f} | {fcp_str:>10} | {pcp_str:>10} | {diff_str:>10}{marker}")


def main():
    print("=" * 80)
    print("FCP vs PCP Cutoff Sensitivity Comparison")
    print("=" * 80)
    
    # Load and merge data
    print("Loading data...")
    df_combined = load_and_merge_data()
    print(f"  FCP samples: {len(df_combined[df_combined['strategy'] == 'FCP'])}")
    print(f"  PCP samples: {len(df_combined[df_combined['strategy'] == 'PCP'])}")
    print(f"  Total samples: {len(df_combined)}")
    
    # Save combined CSV
    df_combined.to_csv(OUTPUT_CSV, index=False, encoding="utf-8")
    print(f"\nCombined CSV saved to {OUTPUT_CSV}")
    
    # Aggregate by cutoff and strategy
    print("\nAggregating by cutoff and strategy...")
    df_agg = aggregate_by_cutoff(df_combined)
    
    # Compute overall averages (across both strategies)
    overall_avg = compute_averages_by_cutoff(df_combined)
    
    # Generate plots
    print("\nGenerating comparison plots...")
    plot_revenue_comparison(df_agg)
    plot_time_comparison(df_agg)
    plot_metrics_comparison(df_agg)
    plot_pareto_comparison(df_agg)
    plot_combined_comparison(df_agg, df_combined)
    
    # Print summary
    print_summary_table(df_agg)
    
    print("\n" + "=" * 80)
    print("Comparison completed!")
    print("=" * 80)


if __name__ == "__main__":
    main()
