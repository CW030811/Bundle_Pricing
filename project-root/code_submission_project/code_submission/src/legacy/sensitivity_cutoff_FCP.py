"""
FCP Cutoff Sensitivity Experiment

Sensitivity test for Cutoff=0.5 in FCP strategy.
- Test dataset: 30 samples from each of m10n10, m20n10, m30n10 (90 total)
- Cutoff values: 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9
- Outputs: revenue ratio comparison, Error Rate, FNR based on Optimal Bundle

Reproducibility:
- Random seed: np.random.seed(42)
- Model: model_edge_4layer_seed1.pt
- Dataset: dataset2_4_2026 (test_m10n10_1e_3, test_m20n10_1e_3, test_m30n10_1e_3)
"""

import os
import time
import numpy as np
import torch
import matplotlib.pyplot as plt
from tqdm import tqdm

# Reproducibility
np.random.seed(42)
if torch.cuda.is_available():
    torch.manual_seed(42)
    torch.cuda.manual_seed_all(42)

# Configuration (use paths relative to script dir for encoding robustness)
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(_SCRIPT_DIR, "models_multi_layer_edge_update", "model_edge_4layer_seed1.pt")
DATASET_DIR = os.path.join(_SCRIPT_DIR, "dataset2_4_2026")
CUTOFFS = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
SAMPLES_PER_DATASET = 30
MB_SUBDIRS = ["test_m10n10_1e_3", "test_m20n10_1e_3", "test_m30n10_1e_3"]
OUTPUT_CSV = "cutoff_sensitivity_results.csv"
OUTPUT_REVENUE_PNG = "cutoff_sensitivity_revenue.png"
OUTPUT_METRICS_PNG = "cutoff_sensitivity_metrics.png"
OUTPUT_PARETO_PNG = "cutoff_sensitivity_pareto.png"

# Import from test_FCP
from test_FCP import EdgeScoringGCN, process_data, revenue_ratio


def load_test_samples():
    """Load 30 samples from each of m10n10, m20n10, m30n10."""
    samples = []
    for subdir in MB_SUBDIRS:
        sub_path = os.path.join(DATASET_DIR, subdir)
        if not os.path.exists(sub_path):
            print(f"Warning: {sub_path} not found, skipping")
            continue
        files = sorted([f for f in os.listdir(sub_path) if f.endswith(".msgpack") and f != ".DS_Store"])
        # Sample 30 with fixed seed
        rng = np.random.default_rng(42)
        indices = rng.choice(len(files), size=min(SAMPLES_PER_DATASET, len(files)), replace=False)
        for idx in indices:
            fpath = os.path.join(sub_path, files[idx])
            try:
                dat, misc = process_data(fpath)
                n, m, unit_cs, ship_cs, unit_us, Ns, opt_bundles, opt_prices, opt_rev, running_time, gap = misc
                samples.append({
                    "dat": dat,
                    "misc": misc,
                    "dataset": subdir,
                    "file_name": files[idx],
                    "n": n,
                    "m": m,
                })
            except Exception as e:
                print(f"Error loading {files[idx]}: {e}")
    return samples


def logit_threshold(cutoff):
    """Convert probability cutoff to logit threshold: sigmoid(x) >= cutoff <=> x >= log(c/(1-c))"""
    if cutoff <= 0 or cutoff >= 1:
        raise ValueError("cutoff must be in (0, 1)")
    return np.log(cutoff / (1 - cutoff))


def compute_bundle_metrics(pred_assort, opt_bundles, n, m):
    """
    pred_assort: (m, n), predicted bundle per segment
    opt_bundles: from data, may be (m, n) or (n, m); ensure (m, n) for comparison
    """
    opt_raw = np.array(opt_bundles)
    if opt_raw.shape == (m, n):
        opt_mn = opt_raw
    elif opt_raw.shape == (n, m):
        opt_mn = opt_raw.T
    else:
        opt_mn = opt_raw.T if opt_raw.shape[0] == n else opt_raw
    pred = np.asarray(pred_assort).astype(int)
    opt = np.asarray(opt_mn).astype(int)

    tp = np.sum((pred == 1) & (opt == 1))
    fn = np.sum((pred == 0) & (opt == 1))
    fp = np.sum((pred == 1) & (opt == 0))
    tn = np.sum((pred == 0) & (opt == 0))
    total = tp + fn + fp + tn

    accuracy = (tp + tn) / total if total > 0 else 0.0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    tpr = recall  # TPR = Recall = TP / (TP + FN)
    tnr = tn / (tn + fp) if (tn + fp) > 0 else 0.0
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
    fnr = fn / (fn + tp) if (fn + tp) > 0 else 0.0
    error_rate = (fp + fn) / total if total > 0 else 0.0

    return {
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "tpr": tpr,
        "tnr": tnr,
        "fpr": fpr,
        "fnr": fnr,
        "error_rate": error_rate,
    }


def run_experiment():
    print("=" * 60)
    print("FCP Cutoff Sensitivity Experiment")
    print("=" * 60)
    print(f"Model: {MODEL_PATH}")
    print(f"Dataset: {DATASET_DIR}")
    print(f"Cutoffs: {CUTOFFS}")
    print(f"Samples per dataset: {SAMPLES_PER_DATASET}")
    print("=" * 60)

    # Load model (4-layer; fallback to best_model_edge.pt if structure incompatible)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = None
    if os.path.exists(MODEL_PATH):
        try:
            loaded = torch.load(MODEL_PATH, map_location=device, weights_only=False)
            if hasattr(loaded, "l2r"):
                model = loaded
        except Exception as e:
            print(f"Load {MODEL_PATH} failed: {e}")
    if model is None:
        fallback = os.path.join(_SCRIPT_DIR, "best_model_edge.pt")
        print(f"Using fallback: {fallback}")
        model = torch.load(fallback, map_location=device, weights_only=False)
    model.to(device)
    model.eval()

    # Load samples
    samples = load_test_samples()
    print(f"Loaded {len(samples)} samples")

    # Pre-compute GCN logits for each sample (one inference per sample)
    print("Running GCN inference...")
    logits_list = []
    gcn_times = []
    for s in tqdm(samples, desc="GCN"):
        with torch.no_grad():
            t0 = time.perf_counter()
            dat = s["dat"].to(device)
            out = model(dat)
            if "logit_matrix" in out:
                logits_nm = out["logit_matrix"].detach().cpu().numpy()
            else:
                s_vec = out["edge_logits"].detach().cpu().numpy()
                n, m = s["n"], s["m"]
                logits_nm = s_vec.reshape(n, m)
            gcn_times.append(time.perf_counter() - t0)
            logits_list.append(logits_nm)

    # Run sensitivity over cutoffs
    results = []
    for cutoff in tqdm(CUTOFFS, desc="Cutoffs"):
        thresh = logit_threshold(cutoff)
        for i, s in enumerate(samples):
            logits_nm = logits_list[i]
            n, m = s["n"], s["m"]
            pred_assort = (logits_nm.T >= thresh).astype(int)  # (m, n)

            n, segment_num, unit_cs, ship_cs, unit_us, Ns, opt_bundles, opt_prices, opt_rev, running_time, gap = s["misc"]

            try:
                rev_ratio, milp_time = revenue_ratio(n, segment_num, unit_cs, ship_cs, unit_us, Ns, opt_rev, pred_assort)
            except Exception as e:
                rev_ratio = np.nan
                milp_time = np.nan
                print(f"  MILP failed sample {i} cutoff {cutoff}: {e}")

            total_time = gcn_times[i] + (milp_time if np.isfinite(milp_time) else 0)
            time_ratio = total_time / running_time if running_time > 0 else np.nan

            metrics = compute_bundle_metrics(pred_assort, opt_bundles, n, segment_num)

            results.append({
                "dataset": s["dataset"],
                "sample_id": s["file_name"],
                "cutoff": cutoff,
                "revenue_ratio": rev_ratio,
                "time_ratio": time_ratio,
                "accuracy": metrics["accuracy"],
                "precision": metrics["precision"],
                "recall": metrics["recall"],
                "tpr": metrics["tpr"],
                "tnr": metrics["tnr"],
                "fpr": metrics["fpr"],
                "fnr": metrics["fnr"],
                "error_rate": metrics["error_rate"],
            })

    # Save CSV
    import csv
    csv_fields = ["dataset", "sample_id", "cutoff", "revenue_ratio", "time_ratio",
                  "accuracy", "precision", "recall", "tpr", "tnr", "fpr", "fnr", "error_rate"]
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=csv_fields)
        writer.writeheader()
        writer.writerows(results)
    print(f"Results saved to {OUTPUT_CSV}")

    # Aggregate by cutoff
    cutoffs_u = np.unique([r["cutoff"] for r in results])
    agg = {}
    for k in ["revenue_ratio", "time_ratio", "accuracy", "precision", "recall", "tpr", "tnr", "fpr", "fnr", "error_rate"]:
        agg[k] = {"mean": [], "std": []}
    for c in cutoffs_u:
        vals = [r for r in results if r["cutoff"] == c]
        for k in agg:
            arr = np.array([v[k] for v in vals])
            agg[k]["mean"].append(np.nanmean(arr))
            agg[k]["std"].append(np.nanstd(arr) if len(arr) > 1 else 0)
    rev_mean = agg["revenue_ratio"]["mean"]
    rev_std = agg["revenue_ratio"]["std"]
    time_mean = agg["time_ratio"]["mean"]
    time_std = agg["time_ratio"]["std"]
    err_mean = agg["error_rate"]["mean"]
    fnr_mean = agg["fnr"]["mean"]

    # Plot 1: Revenue Ratio vs Cutoff
    fig1, ax1 = plt.subplots(figsize=(8, 5))
    ax1.plot(cutoffs_u, rev_mean, "o-", linewidth=2, markersize=8, color="C0", label="Mean")
    ax1.fill_between(cutoffs_u, np.array(rev_mean) - np.array(rev_std), np.array(rev_mean) + np.array(rev_std), alpha=0.3, color="C0")
    ax1.axvline(x=0.5, color="r", linestyle="--", alpha=0.7, label="Default (0.5)")
    ax1.set_xlabel("Cutoff Threshold")
    ax1.set_ylabel("Revenue Ratio")
    ax1.set_title("FCP Cutoff Sensitivity: Revenue Ratio")
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    ax1.set_xticks(cutoffs_u)
    plt.tight_layout()
    plt.savefig(OUTPUT_REVENUE_PNG, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Revenue plot saved to {OUTPUT_REVENUE_PNG}")

    # Plot 2: Revenue by dataset (grouped)
    fig2, ax2 = plt.subplots(figsize=(8, 5))
    for ds in MB_SUBDIRS:
        rev_by_c = []
        for c in cutoffs_u:
            vals = [r["revenue_ratio"] for r in results if r["dataset"] == ds and r["cutoff"] == c and np.isfinite(r["revenue_ratio"])]
            rev_by_c.append(np.mean(vals) if vals else np.nan)
        ax2.plot(cutoffs_u, rev_by_c, "o-", label=ds, linewidth=2, markersize=6)
    ax2.axvline(x=0.5, color="gray", linestyle="--", alpha=0.5)
    ax2.set_xlabel("Cutoff Threshold")
    ax2.set_ylabel("Revenue Ratio")
    ax2.set_title("Revenue Ratio by Dataset")
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    ax2.set_xticks(cutoffs_u)
    plt.tight_layout()
    plt.savefig("cutoff_sensitivity_revenue_by_dataset.png", dpi=300, bbox_inches="tight")
    plt.close()

    # Plot 3: Error Rate and FNR vs Cutoff
    fig3, (ax3a, ax3b) = plt.subplots(2, 1, figsize=(8, 8), sharex=True)
    ax3a.plot(cutoffs_u, err_mean, "o-", linewidth=2, markersize=8, color="C1")
    ax3a.set_ylabel("Error Rate")
    ax3a.set_title("Bundle Prediction Metrics vs Cutoff")
    ax3a.axvline(x=0.5, color="r", linestyle="--", alpha=0.5)
    ax3a.grid(True, alpha=0.3)
    ax3a.set_xticks(cutoffs_u)

    ax3b.plot(cutoffs_u, fnr_mean, "o-", linewidth=2, markersize=8, color="C2")
    ax3b.set_xlabel("Cutoff Threshold")
    ax3b.set_ylabel("FNR (False Negative Rate)")
    ax3b.axvline(x=0.5, color="r", linestyle="--", alpha=0.5)
    ax3b.grid(True, alpha=0.3)
    ax3b.set_xticks(cutoffs_u)
    plt.tight_layout()
    plt.savefig(OUTPUT_METRICS_PNG, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Metrics plot saved to {OUTPUT_METRICS_PNG}")

    # Plot 4: Pareto (Revenue Ratio vs Time Ratio)
    time_mean_arr = np.array(time_mean)
    rev_mean_arr = np.array(rev_mean)
    valid_pts = np.isfinite(time_mean_arr) & np.isfinite(rev_mean_arr) & (time_mean_arr < 1e10)
    if np.any(valid_pts):
        fig4, ax4 = plt.subplots(figsize=(8, 6))
        colors = plt.cm.viridis(np.linspace(0.2, 0.9, len(cutoffs_u)))
        # Scatter: each cutoff is a point (time_ratio, revenue_ratio)
        for idx, c in enumerate(cutoffs_u):
            if valid_pts[idx]:
                ax4.scatter(time_mean_arr[idx], rev_mean_arr[idx], s=120, zorder=5,
                            c=[colors[idx]], label=f"Cutoff={c:.1f}", alpha=0.85, edgecolors="black", linewidths=0.5)
                ax4.annotate(f"{c:.1f}", (time_mean_arr[idx], rev_mean_arr[idx]),
                             xytext=(6, 6), textcoords="offset points", fontsize=9, fontweight="bold")
        # Pareto frontier: sort by time_ratio asc, keep points where revenue increases
        order = np.argsort(time_mean_arr[valid_pts])
        pareto_x, pareto_y = [], []
        max_rev = -np.inf
        for i in order:
            idx = np.where(valid_pts)[0][i]
            if rev_mean_arr[idx] >= max_rev:
                max_rev = rev_mean_arr[idx]
                pareto_x.append(time_mean_arr[idx])
                pareto_y.append(rev_mean_arr[idx])
        if len(pareto_x) >= 2:
            ax4.plot(pareto_x, pareto_y, "k--", linewidth=2, alpha=0.6, label="Pareto frontier")
        ax4.axvline(x=1.0, color="gray", linestyle=":", alpha=0.5, label="Time=Baseline")
        ax4.set_xlabel("Time Ratio (Lower is Better)")
        ax4.set_ylabel("Revenue Ratio (Higher is Better)")
        ax4.set_title("FCP Cutoff: Revenue vs Time Trade-off (Pareto)")
        ax4.legend(loc="best", fontsize=8, ncol=2)
        ax4.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(OUTPUT_PARETO_PNG, dpi=300, bbox_inches="tight")
        plt.close()
        print(f"Pareto plot saved to {OUTPUT_PARETO_PNG}")

    # Summary
    print("\n" + "=" * 60)
    print("Summary by Cutoff")
    print("=" * 60)
    for idx, c in enumerate(cutoffs_u):
        marker = " <-- default" if c == 0.5 else ""
        tm_str = f"{time_mean[idx]:.4f}±{time_std[idx]:.4f}" if np.isfinite(time_mean[idx]) else "N/A"
        print(f"  Cutoff {c:.1f}: Revenue={rev_mean[idx]:.4f}±{rev_std[idx]:.4f}, TimeRatio={tm_str}{marker}")
    print("\n  Bundle Prediction Metrics (mean by cutoff):")
    print("  " + "-" * 70)
    print(f"  {'Cutoff':>6} | {'Acc':>6} | {'Prec':>6} | {'Recall':>6} | {'TPR':>6} | {'TNR':>6} | {'FPR':>6} | {'FNR':>6}")
    print("  " + "-" * 70)
    for idx, c in enumerate(cutoffs_u):
        m = " <--" if c == 0.5 else ""
        print(f"  {c:>6.1f} | {agg['accuracy']['mean'][idx]:.4f} | {agg['precision']['mean'][idx]:.4f} | "
              f"{agg['recall']['mean'][idx]:.4f} | {agg['tpr']['mean'][idx]:.4f} | {agg['tnr']['mean'][idx]:.4f} | "
              f"{agg['fpr']['mean'][idx]:.4f} | {agg['fnr']['mean'][idx]:.4f}{m}")


def plot_from_csv(csv_path=OUTPUT_CSV):
    """Regenerate Pareto and other plots from existing CSV (must contain time_ratio)."""
    import csv
    if not os.path.exists(csv_path):
        print(f"CSV not found: {csv_path}")
        return
    results = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            r = {k: (float(v) if v and v != "nan" else np.nan) for k, v in row.items()}
            results.append(r)
    if not results or "time_ratio" not in results[0]:
        print("CSV missing time_ratio column. Run full experiment first.")
        return
    cutoffs_u = np.unique([r["cutoff"] for r in results])
    rev_mean, time_mean = [], []
    for c in cutoffs_u:
        vals = [r for r in results if r["cutoff"] == c]
        rev_mean.append(np.nanmean([r["revenue_ratio"] for r in vals if np.isfinite(r["revenue_ratio"])]))
        time_mean.append(np.nanmean([r["time_ratio"] for r in vals if np.isfinite(r["time_ratio"]) and r["time_ratio"] < 1e10]))
    time_mean_arr = np.array(time_mean)
    rev_mean_arr = np.array(rev_mean)
    valid_pts = np.isfinite(time_mean_arr) & np.isfinite(rev_mean_arr) & (time_mean_arr < 1e10)
    if np.any(valid_pts):
        fig, ax = plt.subplots(figsize=(8, 6))
        colors = plt.cm.viridis(np.linspace(0.2, 0.9, len(cutoffs_u)))
        for idx, c in enumerate(cutoffs_u):
            if valid_pts[idx]:
                ax.scatter(time_mean_arr[idx], rev_mean_arr[idx], s=120, c=[colors[idx]],
                           label=f"Cutoff={c:.1f}", alpha=0.85, edgecolors="black", linewidths=0.5)
                ax.annotate(f"{c:.1f}", (time_mean_arr[idx], rev_mean_arr[idx]),
                            xytext=(6, 6), textcoords="offset points", fontsize=9, fontweight="bold")
        order = np.argsort(time_mean_arr[valid_pts])
        pareto_x, pareto_y = [], []
        max_rev = -np.inf
        for i in order:
            idx = np.where(valid_pts)[0][i]
            if rev_mean_arr[idx] >= max_rev:
                max_rev = rev_mean_arr[idx]
                pareto_x.append(time_mean_arr[idx])
                pareto_y.append(rev_mean_arr[idx])
        if len(pareto_x) >= 2:
            ax.plot(pareto_x, pareto_y, "k--", linewidth=2, alpha=0.6, label="Pareto frontier")
        ax.axvline(x=1.0, color="gray", linestyle=":", alpha=0.5, label="Time=Baseline")
        ax.set_xlabel("Time Ratio (Lower is Better)")
        ax.set_ylabel("Revenue Ratio (Higher is Better)")
        ax.set_title("FCP Cutoff: Revenue vs Time Trade-off (Pareto)")
        ax.legend(loc="best", fontsize=8, ncol=2)
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(OUTPUT_PARETO_PNG, dpi=300, bbox_inches="tight")
        plt.close()
        print(f"Pareto plot saved to {OUTPUT_PARETO_PNG}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--plot-only":
        plot_from_csv()
    else:
        run_experiment()
