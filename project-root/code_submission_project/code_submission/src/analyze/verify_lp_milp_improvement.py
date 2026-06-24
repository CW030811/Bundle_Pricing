"""
LP-MILP Improvement Verification Script

Verifies that each LP-guided improvement during Local Search translates to MILP gains.
Runs on 60 samples (10 per dataset): MB m10n10, m20n10, m30n10; BSP m10n15, m10n20, m10n25.
"""

import os
import sys
import json
import numpy as np
import torch
import time
from math import ceil, sqrt
from tqdm import tqdm

# Reproducibility
np.random.seed(42)
if torch.cuda.is_available():
    torch.manual_seed(42)
    torch.cuda.manual_seed_all(42)

# Import from test_FCP_LS and LS_Path_Test
from test_FCP_LS import (
    EdgeScoringGCN,
    process_data,
    convert_pred_assort_to_assignment,
    assignment_to_pred_assort,
    revenue_ratio_with_optimal_bundle,
    revenue_ratio_LP,
    check_lp_feasibility_and_revenue,
    predict_initial_bundles,
    solve_initial_milp,
)
from LS_Path_Test import generate_neighbor_assignments_global_topk


def local_search_with_lp_milp_verification(
    initial_pred_assort, prob, meta, max_iterations=50, tolerance=1e-3, verbose=True
):
    """
    Local search with MILP verification at each LP improvement.

    When LP finds improvement, call MILP to verify if MILP also improves.
    Records lp_path, milp_path, and lp_to_milp_translation.

    Returns:
        tuple: (final_pred_assort, final_milp_ratio, verification_info)
        verification_info contains: lp_path, milp_path, lp_to_milp_translation, all_translated, etc.
    """
    n, segment_num, unit_cs, ship_cs, unit_us, Ns, opt_bundles, opt_prices, opt_rev, running_time, gap, stored_cs, stored_Rs = meta
    m = segment_num
    K = int(ceil(sqrt(m)))

    def log(msg):
        if verbose:
            print(msg)

    # Step 1: Initial MILP
    log("Step 1: Initial MILP solve...")
    initial_milp_ratio, initial_milp_time, initial_assignment = revenue_ratio_with_optimal_bundle(
        n, m, unit_cs, ship_cs, unit_us, Ns, opt_rev, initial_pred_assort, stored_cs, stored_Rs
    )
    log(f"Initial MILP: profit ratio={initial_milp_ratio:.6f}")

    # Step 2: Initial LP
    log("Step 2: Initial LP solve...")
    current_profit, _ = revenue_ratio_LP(
        n, m, unit_cs, ship_cs, unit_us, Ns, opt_rev, initial_assignment, stored_cs, stored_Rs
    )
    current_assignment = initial_assignment.copy()
    current_milp_profit = initial_milp_ratio
    log(f"Initial LP: profit ratio={current_profit:.6f}")

    # Verification paths: step 0 = initial
    lp_path = [current_profit]
    milp_path = [initial_milp_ratio]
    lp_to_milp_translation = []  # For each improvement step: did MILP also improve?

    # Step 3: Local Search loop
    improved = True
    iteration = 0

    while improved and iteration < max_iterations:
        improved = False
        iteration += 1

        neighbors, _ = generate_neighbor_assignments_global_topk(current_assignment, prob, n, m)
        log(f"Iteration {iteration}: Evaluating {len(neighbors)} neighbors")

        for neighbor_idx, neighbor_assignment in enumerate(neighbors):
            is_feasible, neighbor_profit, _ = check_lp_feasibility_and_revenue(
                neighbor_assignment, n, m, unit_cs, ship_cs, unit_us, Ns, opt_rev, stored_cs, stored_Rs
            )

            if is_feasible and neighbor_profit > current_profit + tolerance:
                # LP found improvement -> verify with MILP
                neighbor_pred_assort = assignment_to_pred_assort(neighbor_assignment, n, m)
                milp_ratio, _, milp_assignment = revenue_ratio_with_optimal_bundle(
                    n, m, unit_cs, ship_cs, unit_us, Ns, opt_rev, neighbor_pred_assort, stored_cs, stored_Rs
                )

                # Record paths
                lp_path.append(neighbor_profit)
                milp_path.append(milp_ratio)

                # Check if MILP also improved
                milp_translated = milp_ratio > current_milp_profit
                lp_to_milp_translation.append(milp_translated)

                log(f"  LP improvement: {neighbor_profit:.6f} -> MILP: {milp_ratio:.6f} "
                    f"(translated={milp_translated}, prev_milp={current_milp_profit:.6f})")

                # Accept assignment (keep search behavior unchanged)
                current_assignment = neighbor_assignment
                current_profit = neighbor_profit
                current_milp_profit = milp_ratio
                improved = True
                break

        if not improved:
            log(f"Iteration {iteration}: No improvement, converged")

    # Final pred_assort and MILP
    final_pred_assort = assignment_to_pred_assort(current_assignment, n, m)
    final_milp_ratio, final_milp_time, _ = revenue_ratio_with_optimal_bundle(
        n, m, unit_cs, ship_cs, unit_us, Ns, opt_rev, final_pred_assort, stored_cs, stored_Rs
    )

    all_translated = all(lp_to_milp_translation) if lp_to_milp_translation else True

    verification_info = {
        "lp_path": lp_path,
        "milp_path": milp_path,
        "lp_to_milp_translation": lp_to_milp_translation,
        "all_translated": all_translated,
        "improvement_count": len(lp_to_milp_translation),
        "initial_lp_profit": lp_path[0],
        "initial_milp_profit": milp_path[0],
        "final_lp_profit": current_profit,
        "final_milp_profit": final_milp_ratio,
        "iterations": iteration,
        "K": K,
    }

    return final_pred_assort, final_milp_ratio, verification_info


def load_sample(dataset_path, sample_id=0):
    """Load a single sample from dataset directory."""
    dir_list = [f for f in os.listdir(dataset_path) if f.endswith(".msgpack") and f != ".DS_Store"]
    dir_list.sort()
    if sample_id >= len(dir_list):
        return None, None, None
    file_path = os.path.join(dataset_path, dir_list[sample_id])
    try:
        dat, miscellaneous = process_data(file_path)
        return dat, miscellaneous, file_path
    except Exception as e:
        print(f"Error loading {file_path}: {e}")
        return None, None, None


def run_verification_for_sample(
    dataset_name, dataset_path, sample_id, model_path, verbose=True
):
    """Run LP-MILP verification for one sample. Returns result dict or None."""
    dat, meta, file_path = load_sample(dataset_path, sample_id)
    if dat is None:
        return None

    n, segment_num, unit_cs, ship_cs, unit_us, Ns, opt_bundles, opt_prices, opt_rev, running_time, gap, stored_cs, stored_Rs = meta
    m = segment_num

    # Predict initial bundles
    initial_pred, prob = predict_initial_bundles(dat, meta)

    # Run verification
    final_pred, final_milp, info = local_search_with_lp_milp_verification(
        initial_pred, prob, meta, max_iterations=50, tolerance=1e-3, verbose=verbose
    )

    result = {
        "dataset_name": dataset_name,
        "sample_id": sample_id,
        "file_path": file_path,
        "m": m,
        "n": n,
        "opt_rev": float(opt_rev),
        "lp_path": info["lp_path"],
        "milp_path": info["milp_path"],
        "lp_to_milp_translation": info["lp_to_milp_translation"],
        "all_translated": info["all_translated"],
        "improvement_count": info["improvement_count"],
        "initial_lp_profit": info["initial_lp_profit"],
        "initial_milp_profit": info["initial_milp_profit"],
        "final_lp_profit": info["final_lp_profit"],
        "final_milp_profit": info["final_milp_profit"],
        "iterations": info["iterations"],
    }
    return result


def calculate_translation_statistics(all_results):
    """Calculate translation statistics from all results."""
    stats = {
        "by_dataset": {},
        "by_step": {},
        "overall": {"total": 0, "success": 0}
    }
    
    # Group by dataset
    by_dataset = {}
    for res in all_results:
        name = res["dataset_name"]
        if name not in by_dataset:
            by_dataset[name] = []
        by_dataset[name].append(res)
    
    # Calculate per-dataset statistics
    for name, samples in by_dataset.items():
        total_improvements = sum(s["improvement_count"] for s in samples)
        successful = sum(
            sum(s["lp_to_milp_translation"]) 
            for s in samples 
            if s["lp_to_milp_translation"]
        )
        all_translated_count = sum(1 for s in samples if s["all_translated"])
        
        stats["by_dataset"][name] = {
            "total_improvements": total_improvements,
            "successful_translations": successful,
            "translation_rate": successful / total_improvements if total_improvements > 0 else 0,
            "samples_with_all_translated": all_translated_count,
            "total_samples": len(samples),
            "sample_success_rate": all_translated_count / len(samples) if len(samples) > 0 else 0
        }
    
    # Calculate per-step statistics
    samples_with_improvements = [s for s in all_results if s["lp_to_milp_translation"]]
    if samples_with_improvements:
        max_steps = max(len(s["lp_to_milp_translation"]) for s in samples_with_improvements)
        for step in range(1, max_steps + 1):
            step_results = [
                s["lp_to_milp_translation"][step - 1]
                for s in samples_with_improvements
                if len(s["lp_to_milp_translation"]) >= step
            ]
            if step_results:
                stats["by_step"][step] = {
                    "success": sum(step_results),
                    "total": len(step_results),
                    "rate": sum(step_results) / len(step_results)
                }
    
    # Overall statistics
    stats["overall"]["total"] = sum(s["improvement_count"] for s in all_results)
    stats["overall"]["success"] = sum(
        sum(s["lp_to_milp_translation"])
        for s in all_results
        if s["lp_to_milp_translation"]
    )
    if stats["overall"]["total"] > 0:
        stats["overall"]["translation_rate"] = (
            stats["overall"]["success"] / stats["overall"]["total"]
        )
    
    return stats


def plot_comprehensive_results(all_results, stats, output_dir):
    """Plot comprehensive visualization: paths and statistics."""
    import matplotlib.pyplot as plt
    
    plt.rcParams["font.sans-serif"] = ["SimHei", "Arial Unicode MS", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    
    # Group by dataset
    by_dataset = {}
    for res in all_results:
        name = res["dataset_name"]
        if name not in by_dataset:
            by_dataset[name] = []
        by_dataset[name].append(res)
    
    dataset_order = [
        "m10_n10_sample_100",
        "m20_n10_sample_100",
        "m30_n10_sample_100",
        "test_BSP_m10n15",
        "test_BSP_m10n20",
        "test_BSP_m10n25",
    ]
    
    # ===== Figure 1: Path Comparison (2x3 subplots) - Absolute Profit =====
    # Padding: shorter samples are padded with last value so all have same length.
    # This avoids average drop when high-profit samples converge early and are excluded.
    fig1, axes1 = plt.subplots(2, 3, figsize=(16, 10))
    axes1 = axes1.flatten()
    
    for idx, dataset_name in enumerate(dataset_order):
        if dataset_name not in by_dataset:
            continue
        ax = axes1[idx]
        samples = by_dataset[dataset_name]
        
        max_len = max(len(s["lp_path"]) for s in samples)
        opt_rev_default = 1.0  # fallback if opt_rev not in old results
        
        # Pad each sample with last value, convert to absolute profit
        lp_padded_list = []
        milp_padded_list = []
        for sample in samples:
            lp_path = sample["lp_path"]
            milp_path = sample["milp_path"]
            opt_rev = sample.get("opt_rev", opt_rev_default)
            # Pad with last value to max_len
            lp_padded = lp_path + [lp_path[-1]] * (max_len - len(lp_path)) if len(lp_path) < max_len else lp_path
            milp_padded = milp_path + [milp_path[-1]] * (max_len - len(milp_path)) if len(milp_path) < max_len else milp_path
            # Convert to absolute profit
            lp_padded_list.append([v * opt_rev for v in lp_padded])
            milp_padded_list.append([v * opt_rev for v in milp_padded])
        
        # Plot individual paths (semi-transparent, absolute profit)
        for i, sample in enumerate(samples):
            steps = list(range(max_len))
            ax.plot(steps, lp_padded_list[i], color="C0", alpha=0.2, linewidth=1)
            ax.plot(steps, milp_padded_list[i], color="C1", alpha=0.2, linewidth=1, linestyle="--")
        
        # Average over all samples (same set at every step, so no artificial drop)
        lp_avg = [np.mean([lp_padded_list[i][step] for i in range(len(samples))]) for step in range(max_len)]
        milp_avg = [np.mean([milp_padded_list[i][step] for i in range(len(samples))]) for step in range(max_len)]
        lp_std = [np.std([lp_padded_list[i][step] for i in range(len(samples))]) for step in range(max_len)]
        milp_std = [np.std([milp_padded_list[i][step] for i in range(len(samples))]) for step in range(max_len)]
        
        steps_avg = list(range(max_len))
        ax.plot(steps_avg, lp_avg, "o-", color="C0", linewidth=3, markersize=6, label="LP (avg)")
        ax.plot(steps_avg, milp_avg, "s--", color="C1", linewidth=3, markersize=6, label="MILP (avg)")
        
        # Error bands
        ax.fill_between(steps_avg,
                       np.array(lp_avg) - np.array(lp_std),
                       np.array(lp_avg) + np.array(lp_std),
                       color="C0", alpha=0.1)
        ax.fill_between(steps_avg,
                       np.array(milp_avg) - np.array(milp_std),
                       np.array(milp_avg) + np.array(milp_std),
                       color="C1", alpha=0.1)
        
        ax.set_xlabel("Improvement Step")
        ax.set_ylabel("Profit (absolute)")
        ax.set_title(f"{dataset_name} (n={len(samples)} samples, padded)")
        ax.legend()
        ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    paths_path = os.path.join(output_dir, "LP_MILP_verification_paths.png")
    plt.savefig(paths_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Paths plot saved: {paths_path}")
    
    # ===== Figure 1b: Path Comparison - Profit Ratio =====
    fig1b, axes1b = plt.subplots(2, 3, figsize=(16, 10))
    axes1b = axes1b.flatten()
    
    for idx, dataset_name in enumerate(dataset_order):
        if dataset_name not in by_dataset:
            continue
        ax = axes1b[idx]
        samples = by_dataset[dataset_name]
        
        max_len = max(len(s["lp_path"]) for s in samples)
        
        # Pad each sample with last value (ratio, no conversion)
        lp_padded_list = []
        milp_padded_list = []
        for sample in samples:
            lp_path = sample["lp_path"]
            milp_path = sample["milp_path"]
            lp_padded = lp_path + [lp_path[-1]] * (max_len - len(lp_path)) if len(lp_path) < max_len else lp_path
            milp_padded = milp_path + [milp_path[-1]] * (max_len - len(milp_path)) if len(milp_path) < max_len else milp_path
            lp_padded_list.append(lp_padded)
            milp_padded_list.append(milp_padded)
        
        for i in range(len(samples)):
            steps = list(range(max_len))
            ax.plot(steps, lp_padded_list[i], color="C0", alpha=0.2, linewidth=1)
            ax.plot(steps, milp_padded_list[i], color="C1", alpha=0.2, linewidth=1, linestyle="--")
        
        lp_avg = [np.mean([lp_padded_list[i][step] for i in range(len(samples))]) for step in range(max_len)]
        milp_avg = [np.mean([milp_padded_list[i][step] for i in range(len(samples))]) for step in range(max_len)]
        lp_std = [np.std([lp_padded_list[i][step] for i in range(len(samples))]) for step in range(max_len)]
        milp_std = [np.std([milp_padded_list[i][step] for i in range(len(samples))]) for step in range(max_len)]
        
        steps_avg = list(range(max_len))
        ax.plot(steps_avg, lp_avg, "o-", color="C0", linewidth=3, markersize=6, label="LP (avg)")
        ax.plot(steps_avg, milp_avg, "s--", color="C1", linewidth=3, markersize=6, label="MILP (avg)")
        ax.fill_between(steps_avg, np.array(lp_avg) - np.array(lp_std), np.array(lp_avg) + np.array(lp_std), color="C0", alpha=0.1)
        ax.fill_between(steps_avg, np.array(milp_avg) - np.array(milp_std), np.array(milp_avg) + np.array(milp_std), color="C1", alpha=0.1)
        ax.set_xlabel("Improvement Step")
        ax.set_ylabel("Profit Ratio")
        ax.set_title(f"{dataset_name} (n={len(samples)} samples, padded)")
        ax.legend()
        ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    paths_ratio_path = os.path.join(output_dir, "LP_MILP_verification_paths_ratio.png")
    plt.savefig(paths_ratio_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Paths plot (Profit Ratio) saved: {paths_ratio_path}")
    
    # ===== Figure 2: Statistics (2x2 subplots) =====
    fig2, axes2 = plt.subplots(2, 2, figsize=(14, 10))
    
    # Subplot 1: Dataset-level translation rate
    ax1 = axes2[0, 0]
    datasets = list(stats["by_dataset"].keys())
    rates = [stats["by_dataset"][d]["translation_rate"] for d in datasets]
    ax1.bar(range(len(datasets)), rates, color="C0", alpha=0.7)
    ax1.set_xticks(range(len(datasets)))
    ax1.set_xticklabels(datasets, rotation=45, ha="right")
    ax1.set_ylabel("Translation Rate")
    ax1.set_title("Dataset-level Translation Rate")
    ax1.set_ylim([0, 1.05])
    ax1.grid(True, alpha=0.3, axis="y")
    for i, (d, r) in enumerate(zip(datasets, rates)):
        ax1.text(i, r + 0.02, f"{r:.3f}", ha="center", va="bottom", fontsize=9)
    
    # Subplot 2: Sample-level success rate
    ax2 = axes2[0, 1]
    sample_rates = [stats["by_dataset"][d]["sample_success_rate"] for d in datasets]
    ax2.bar(range(len(datasets)), sample_rates, color="C1", alpha=0.7)
    ax2.set_xticks(range(len(datasets)))
    ax2.set_xticklabels(datasets, rotation=45, ha="right")
    ax2.set_ylabel("Sample Success Rate")
    ax2.set_title("Sample-level Success Rate (All Translated)")
    ax2.set_ylim([0, 1.05])
    ax2.grid(True, alpha=0.3, axis="y")
    for i, (d, r) in enumerate(zip(datasets, sample_rates)):
        ax2.text(i, r + 0.02, f"{r:.2f}", ha="center", va="bottom", fontsize=9)
    
    # Subplot 3: Step-level translation rate
    ax3 = axes2[1, 0]
    if stats["by_step"]:
        steps = sorted(stats["by_step"].keys())
        step_rates = [stats["by_step"][s]["rate"] for s in steps]
        ax3.plot(steps, step_rates, "o-", linewidth=2, markersize=6, color="C2")
        ax3.set_xlabel("Improvement Step")
        ax3.set_ylabel("Translation Rate")
        ax3.set_title("Step-level Translation Rate")
        ax3.set_ylim([0, 1.05])
        ax3.grid(True, alpha=0.3)
        ax3.axhline(y=0.95, color="r", linestyle="--", alpha=0.5, label="95% threshold")
        ax3.legend()
    
    # Subplot 4: Improvement count distribution
    ax4 = axes2[1, 1]
    improvement_counts_by_dataset = []
    dataset_labels = []
    for d in datasets:
        counts = [s["improvement_count"] for s in by_dataset.get(d, [])]
        if counts:
            improvement_counts_by_dataset.append(counts)
            dataset_labels.append(d)
    
    if improvement_counts_by_dataset:
        bp = ax4.boxplot(improvement_counts_by_dataset, labels=dataset_labels, patch_artist=True)
        for patch in bp["boxes"]:
            patch.set_facecolor("C3")
            patch.set_alpha(0.7)
        ax4.set_xticklabels(dataset_labels, rotation=45, ha="right")
        ax4.set_ylabel("Improvement Count")
        ax4.set_title("Improvement Count Distribution")
        ax4.grid(True, alpha=0.3, axis="y")
    
    plt.tight_layout()
    stats_path = os.path.join(output_dir, "LP_MILP_verification_statistics.png")
    plt.savefig(stats_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Statistics plot saved: {stats_path}")


def generate_summary_md(all_results, stats, output_path):
    """Generate summary markdown report with statistics."""
    lines = [
        "# LP-MILP Improvement Verification Summary",
        "",
        "## 实验配置",
        "- 随机种子: np=42, torch=42",
        "- max_iterations=50, tolerance=1e-3",
        "- 数据集路径: Dataset/m10_n10_sample_100, m20_n10_sample_100, m30_n10_sample_100, test_BSP_m10n15, test_BSP_m10n20, test_BSP_m10n25",
        "- 样本选择: 每个数据集10个样本（sample_id 0-9）",
        "",
        "## 转化成功率统计",
        "",
        "### 数据集级统计",
        "",
        "| 数据集 | 样本数 | 总改进次数 | 成功转化次数 | 转化成功率 | 全部转化样本数 | 样本成功率 |",
        "|--------|--------|------------|--------------|------------|----------------|------------|",
    ]
    
    for dataset_name in sorted(stats["by_dataset"].keys()):
        d = stats["by_dataset"][dataset_name]
        lines.append(
            f"| {dataset_name} | {d['total_samples']} | {d['total_improvements']} | "
            f"{d['successful_translations']} | {d['translation_rate']:.4f} | "
            f"{d['samples_with_all_translated']} | {d['sample_success_rate']:.4f} |"
        )
    
    lines.extend([
        "",
        "### 改进步骤级统计",
        "",
        "| 步骤 | 总次数 | 成功次数 | 成功率 |",
        "|------|--------|----------|--------|",
    ])
    
    for step in sorted(stats["by_step"].keys()):
        s = stats["by_step"][step]
        lines.append(f"| {step} | {s['total']} | {s['success']} | {s['rate']:.4f} |")
    
    lines.extend([
        "",
        "### 总体统计",
        "",
        f"- 总改进次数: {stats['overall']['total']}",
        f"- 成功转化次数: {stats['overall']['success']}",
        f"- 总体转化成功率: {stats['overall'].get('translation_rate', 0):.4f}",
        "",
        "## 可视化图表",
        "",
        "- `LP_MILP_verification_paths.png`: 路径对比图（2×3子图，每个数据集显示10个样本的平均路径）",
        "- `LP_MILP_verification_statistics.png`: 统计图（2×2子图：数据集级成功率、样本级成功率、步骤级成功率、改进次数分布）",
        "",
        "## 详细结果",
        "",
        "### 样本级结果汇总",
        "",
        "| 数据集 | 样本ID | 改进次数 | 全部转化为MILP提升 | LP路径(初->终) | MILP路径(初->终) |",
        "|--------|--------|----------|-------------------|----------------|------------------|",
    ])
    
    for res in sorted(all_results, key=lambda x: (x["dataset_name"], x["sample_id"])):
        trans = "是" if res["all_translated"] else "否"
        lp_range = f"{res['lp_path'][0]:.4f} -> {res['lp_path'][-1]:.4f}"
        milp_range = f"{res['milp_path'][0]:.4f} -> {res['milp_path'][-1]:.4f}"
        lines.append(
            f"| {res['dataset_name']} | {res['sample_id']} | {res['improvement_count']} | "
            f"{trans} | {lp_range} | {milp_range} |"
        )
    
    lines.extend([
        "",
        "## 整体结论",
        "",
    ])
    
    overall_rate = stats["overall"].get("translation_rate", 0)
    lines.append(
        f"总体转化成功率为 {overall_rate:.2%}。"
    )
    
    # Find datasets with low rates
    low_rate_datasets = [
        d for d, s in stats["by_dataset"].items()
        if s["translation_rate"] < 0.95
    ]
    if low_rate_datasets:
        lines.append(f"转化成功率低于95%的数据集: {', '.join(low_rate_datasets)}")
    else:
        lines.append("所有数据集的转化成功率均达到95%以上。")
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Summary saved: {output_path}")


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    dataset_base = os.path.join(script_dir, "Dataset")
    model_path = os.path.join(script_dir, "best_model_edge.pt")

    datasets = {
        "m10_n10_sample_100": os.path.join(dataset_base, "m10_n10_sample_100"),
        "m20_n10_sample_100": os.path.join(dataset_base, "m20_n10_sample_100"),
        "m30_n10_sample_100": os.path.join(dataset_base, "m30_n10_sample_100"),
        "test_BSP_m10n15": os.path.join(dataset_base, "test_BSP_m10n15"),
        "test_BSP_m10n20": os.path.join(dataset_base, "test_BSP_m10n20"),
        "test_BSP_m10n25": os.path.join(dataset_base, "test_BSP_m10n25"),
    }

    print("=" * 60)
    print("LP-MILP Improvement Verification (10 samples per dataset)")
    print("=" * 60)

    all_results = []
    for name, path in datasets.items():
        if not os.path.exists(path):
            print(f"Skip {name}: path not found")
            continue
        print(f"\n--- Processing {name} (10 samples) ---")
        dataset_results = []
        
        # For m10_n10_sample_100, skip sample_id=5 (profit ratio > 1, likely MILP Gap issue)
        # Use sample_id=10 as replacement
        if name == "m10_n10_sample_100":
            sample_ids = [0, 1, 2, 3, 4, 6, 7, 8, 9, 10]
            print(f"  Note: Skipping sample_id=5 (profit ratio > 1), using sample_id=10 instead")
        else:
            sample_ids = list(range(10))
        
        for sample_id in tqdm(sample_ids, desc=f"{name}"):
            res = run_verification_for_sample(name, path, sample_id, model_path, verbose=False)
            if res:
                dataset_results.append(res)
                all_results.append(res)
            else:
                print(f"  Warning: Failed to process {name} sample {sample_id}")
        print(f"  Completed: {len(dataset_results)}/10 samples")

    print(f"\nTotal samples processed: {len(all_results)}")

    # Calculate statistics
    stats = calculate_translation_statistics(all_results)
    
    # Save JSON
    json_path = os.path.join(script_dir, "LP_MILP_verification_results.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved: {json_path}")

    # Save statistics JSON
    stats_path = os.path.join(script_dir, "LP_MILP_verification_statistics.json")
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)
    print(f"Statistics saved: {stats_path}")

    # Plot
    if all_results:
        plot_comprehensive_results(all_results, stats, script_dir)

    # Summary
    summary_path = os.path.join(script_dir, "LP_MILP_verification_summary.md")
    generate_summary_md(all_results, stats, summary_path)

    print("\nDone.")


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
    main()
