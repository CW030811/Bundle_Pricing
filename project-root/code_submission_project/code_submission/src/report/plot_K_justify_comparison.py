"""
K Strategy Comparison - Pareto Plots Only

Reads justify_K_*.csv from Local_Search_Exper (or script dir) and generates:
- K_justify_pareto_MB.png: MB datasets only (m10n10, m20n10, m30n10)
- K_justify_pareto_BSP.png: BSP datasets only (BSP_m10n20, BSP_m20n20)
"""

import os
import glob
import numpy as np
import matplotlib.pyplot as plt

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

K_STRATEGIES = ['original', 'K_m', 'K_const_5', 'K_const_10', 'K_sqrt_mn', 'K_sqrt_m', 'K_2sqrt_m']
STRATEGY_LABELS = {
    'original': '2m',
    'K_m': 'K=m',
    'K_const_5': 'K=5',
    'K_const_10': 'K=10',
    'K_sqrt_m': 'K=sqrt(m)',
    'K_sqrt_mn': 'K=sqrt(mn)',
    'K_2sqrt_m': 'K=2*sqrt(m)',
}
# MB: 3 datasets only (m10n10, m20n10, m30n10)
MB_DATASETS = ['test_m10n10_1e_3', 'test_m20n10_1e_3', 'test_m30n10_1e_3']
# BSP: 2 datasets only (BSP_m10n20, BSP_m20n20)
BSP_DATASETS = ['test_BSP_m10n20_1e_3', 'test_BSP_m20n20_1e_3']
DATASETS = MB_DATASETS + BSP_DATASETS
DATASET_LABELS = {
    'test_m10n10_1e_3': 'm=10, n=10',
    'test_m20n10_1e_3': 'm=20, n=10',
    'test_m30n10_1e_3': 'm=30, n=10',
    'test_BSP_m10n20_1e_3': 'm=10, n=20',
    'test_BSP_m20n20_1e_3': 'm=20, n=20',
}
# Point labels on Pareto: MB = m10n10, m20n10, m30n10; BSP = BSP_m10n20, BSP_m20n20
DATASET_COMPACT_LABELS = {
    'test_m10n10_1e_3': 'm10n10',
    'test_m20n10_1e_3': 'm20n10',
    'test_m30n10_1e_3': 'm30n10',
    'test_BSP_m10n20_1e_3': 'BSP_m10n20',
    'test_BSP_m20n20_1e_3': 'BSP_m20n20',
}
COL_NAMES = ['n_products', 'revenue_ratio', 'runtime_ratio', 'total_time', 'base_running_time',
             'improvement', 'iterations', 'improvements', 'lp_solver_calls', 'milp_solver_calls',
             'K', 'max_neighbors_per_iter']

# Strategy colors and markers for Pareto plot
STRATEGY_COLORS = {
    'original': '#1f77b4',
    'K_m': '#1f77b4',
    'K_const_5': '#2ca02c',
    'K_const_10': '#d62728',
    'K_sqrt_m': '#9467bd',
    'K_sqrt_mn': '#8c564b',
    'K_2sqrt_m': '#bcbd22',
}
STRATEGY_MARKERS = {
    'original': 'o',
    'K_m': 'P',
    'K_const_5': 's',
    'K_const_10': '^',
    'K_sqrt_m': 'D',
    'K_sqrt_mn': 'v',
    'K_2sqrt_m': 'X',
}


def load_justify_csv(filepath):
    """Load justify CSV, return dict with arrays."""
    if not os.path.exists(filepath):
        return None
    data = np.genfromtxt(filepath, delimiter=',', skip_header=1)
    if data.size == 0:
        return None
    if data.ndim == 1:
        data = data.reshape(1, -1)
    result = {}
    for i, name in enumerate(COL_NAMES):
        if i < data.shape[1]:
            result[name] = data[:, i]
    return result


def parse_filename(filepath):
    """Parse justify_K_{strategy}_{dataset}.csv -> (strategy, dataset)."""
    basename = os.path.basename(filepath)
    if not basename.startswith('justify_K_') or not basename.endswith('.csv'):
        return None, None
    middle = basename[len('justify_K_'):-len('.csv')]
    # Longer names first (K_2sqrt_m before K_2, K_sqrt_mn before K_sqrt_m, etc.)
    for strat in ['K_2sqrt_m', 'K_sqrt_mn', 'K_sqrt_m', 'K_const_10', 'K_const_5', 'K_m', 'original']:
        if middle.startswith(strat + '_'):
            return strat, middle[len(strat) + 1:]
        elif middle == strat:
            return strat, ''
    return None, None


def load_all_results():
    """Load all justify CSV files -> dict[strategy][dataset] = data. Checks SCRIPT_DIR and Local_Search_Exper."""
    results = {s: {} for s in K_STRATEGIES}
    for search_dir in [SCRIPT_DIR, os.path.join(SCRIPT_DIR, 'Local_Search_Exper')]:
        if not os.path.isdir(search_dir):
            continue
        pattern = os.path.join(search_dir, 'justify_K_*.csv')
        for f in glob.glob(pattern):
            strat, ds = parse_filename(f)
            if strat and ds and ds in DATASETS and strat in results:
                data = load_justify_csv(f)
                if data is not None:
                    results[strat][ds] = data
    return results


def plot_pareto_front(ax, results, datasets):
    """Pareto front plot: Competitive Ratio vs Absolute Time (s), points connected by strategy."""
    for strat in K_STRATEGIES:
        x_vals, y_vals, ds_labels = [], [], []
        for ds in datasets:
            d = results.get(strat, {}).get(ds)
            if d is not None:
                time_mean = np.mean(d['total_time'])  # absolute time in seconds
                rev_mean = np.mean(d['revenue_ratio'])
                x_vals.append(time_mean)
                y_vals.append(rev_mean)
                ds_labels.append(DATASET_COMPACT_LABELS.get(ds, ds))
        if x_vals and y_vals:
            ax.plot(x_vals, y_vals, marker=STRATEGY_MARKERS[strat], linestyle='--',
                    color=STRATEGY_COLORS[strat], label=STRATEGY_LABELS[strat],
                    markersize=8, linewidth=2, alpha=0.8)
            for xi, yi, lbl in zip(x_vals, y_vals, ds_labels):
                ax.annotate(lbl, (xi, yi), xytext=(5, 5), textcoords='offset points',
                            fontsize=8, alpha=0.8)
    ax.set_xlabel('Absolute Time (s) (Lower is Better)', fontsize=11)
    ax.set_ylabel('Competitive Ratio (Higher is Better)', fontsize=11)
    ax.set_title('Competitive Ratio vs Absolute Time (Pareto View)', fontsize=12)
    ax.legend(loc='best', fontsize=9)
    ax.grid(True, alpha=0.3)


def main():
    plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial']
    plt.rcParams['axes.unicode_minus'] = False

    results = load_all_results()

    # MB: only m10n10, m20n10, m30n10 (3 points per strategy)
    mb_datasets_present = [ds for ds in MB_DATASETS
                           if any(results[s].get(ds) is not None for s in K_STRATEGIES)]
    # BSP: only BSP_m10n20, BSP_m20n20 (2 points per strategy)
    bsp_datasets_present = [ds for ds in BSP_DATASETS
                            if any(results[s].get(ds) is not None for s in K_STRATEGIES)]

    if not mb_datasets_present and not bsp_datasets_present:
        print("No justify_K_*.csv data found. Run LS_Path_Test_K_Justify.py first.")
        return

    # Pareto plot: MB (m10n10, m20n10, m30n10)
    if mb_datasets_present:
        fig_mb, ax_mb = plt.subplots(figsize=(8, 6))
        plot_pareto_front(ax_mb, results, mb_datasets_present)
        fig_mb.suptitle('MB Datasets - Competitive Ratio vs Time Trade-off (Pareto View)', fontsize=14, fontweight='bold')
        fig_mb.tight_layout(rect=[0, 0, 1, 0.96])
        path_mb = os.path.join(SCRIPT_DIR, 'K_justify_pareto_MB.png')
        fig_mb.savefig(path_mb, dpi=150, bbox_inches='tight')
        print(f"Saved: {path_mb}")
        plt.close(fig_mb)

    # Pareto plot: BSP (BSP_m10n20, BSP_m20n20)
    if bsp_datasets_present:
        fig_bsp, ax_bsp = plt.subplots(figsize=(8, 6))
        plot_pareto_front(ax_bsp, results, bsp_datasets_present)
        fig_bsp.suptitle('BSP Datasets - Competitive Ratio vs Time Trade-off (Pareto View)', fontsize=14, fontweight='bold')
        fig_bsp.tight_layout(rect=[0, 0, 1, 0.96])
        path_bsp = os.path.join(SCRIPT_DIR, 'K_justify_pareto_BSP.png')
        fig_bsp.savefig(path_bsp, dpi=150, bbox_inches='tight')
        print(f"Saved: {path_bsp}")
        plt.close(fig_bsp)


if __name__ == "__main__":
    main()
