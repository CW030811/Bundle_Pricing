"""
Export Revenue Ratio and Time Ratio comparison tables from K justify experiment.
Output: K_justify_comparison_tables.md
"""

import os
import glob
import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

K_STRATEGIES = ['original', 'K_m', 'K_const_5', 'K_const_10', 'K_sqrt_mn', 'K_sqrt_m', 'K_2sqrt_m']
STRATEGY_LABELS = {'original': '2m', 'K_m': 'K=m', 'K_const_5': 'K=5', 'K_const_10': 'K=10',
                   'K_sqrt_m': 'K=sqrt(m)', 'K_sqrt_mn': 'K=sqrt(mn)', 'K_2sqrt_m': 'K=2*sqrt(m)'}
DATASETS = ['m10_n10_sample_100', 'm20_n10_sample_100', 'm30_n10_sample_100',
            'test_m10n10_1e_3', 'test_m20n10_1e_3', 'test_m30n10_1e_3',
            'test_BSP_m10n15', 'test_BSP_m10n20', 'test_BSP_m10n25',
            'test_BSP_m10n20_1e_3', 'test_BSP_m20n20_1e_3']
DATASET_LABELS = {
    'm10_n10_sample_100': 'm=10, n=10',
    'm20_n10_sample_100': 'm=20, n=10',
    'm30_n10_sample_100': 'm=30, n=10',
    'test_m10n10_1e_3': 'm=10, n=10',
    'test_m20n10_1e_3': 'm=20, n=10',
    'test_m30n10_1e_3': 'm=30, n=10',
    'test_BSP_m10n15': 'm=10, n=15',
    'test_BSP_m10n20': 'm=10, n=20',
    'test_BSP_m10n25': 'm=10, n=25',
    'test_BSP_m10n20_1e_3': 'm=10, n=20',
    'test_BSP_m20n20_1e_3': 'm=20, n=20',
}
COL_NAMES = ['n_products', 'revenue_ratio', 'runtime_ratio', 'total_time', 'base_running_time',
             'improvement', 'iterations', 'improvements', 'lp_solver_calls', 'milp_solver_calls',
             'K', 'max_neighbors_per_iter']


def load_csv(filepath):
    if not os.path.exists(filepath):
        return None
    data = np.genfromtxt(filepath, delimiter=',', skip_header=1)
    if data.size == 0:
        return None
    if data.ndim == 1:
        data = data.reshape(1, -1)
    return {COL_NAMES[i]: data[:, i] for i in range(min(len(COL_NAMES), data.shape[1]))}


def parse_filename(filepath):
    basename = os.path.basename(filepath)
    if not basename.startswith('justify_K_') or not basename.endswith('.csv'):
        return None, None
    middle = basename[len('justify_K_'):-len('.csv')]
    for strat in ['K_2sqrt_m', 'K_sqrt_mn', 'K_sqrt_m', 'K_const_10', 'K_const_5', 'K_m', 'original']:
        if middle.startswith(strat + '_'):
            return strat, middle[len(strat) + 1:]
        elif middle == strat:
            return strat, ''
    return None, None


def main():
    # Prefer Local_Search_Exper, fallback to script dir
    search_dirs = [os.path.join(SCRIPT_DIR, 'Local_Search_Exper'), SCRIPT_DIR]
    files = []
    for d in search_dirs:
        if os.path.isdir(d):
            files.extend(glob.glob(os.path.join(d, 'justify_K_*.csv')))
    files = list(dict.fromkeys(files))  # dedupe by path
    results = {s: {} for s in K_STRATEGIES}
    for f in files:
        strat, ds = parse_filename(f)
        if strat and ds and ds in DATASETS and strat in results:
            data = load_csv(f)
            if data is not None:
                results[strat][ds] = data

    # Prefer current experiment datasets (5 subsets from dataset2_4_2026), then any others with data
    current_exp_datasets = [
        'test_m10n10_1e_3', 'test_m20n10_1e_3', 'test_m30n10_1e_3',
        'test_BSP_m10n20_1e_3', 'test_BSP_m20n20_1e_3',
    ]
    all_with_data = set(ds for s in K_STRATEGIES for ds in results[s].keys())
    datasets_used = [ds for ds in current_exp_datasets if ds in all_with_data]
    datasets_used += sorted(all_with_data - set(datasets_used))  # append any remaining
    if not datasets_used:
        print("No results found. Run LS_Path_Test_K_Justify.py first.")
        return

    lines = []
    lines.append("# K Justify Experiment: Competitive Ratio & Time Ratio Comparison Tables\n")
    lines.append("(Competitive Ratio = Revenue Ratio; data from Local_Search_Exper)\n\n")

    header_cols = " | ".join(["Strategy"] + [DATASET_LABELS.get(ds, ds) for ds in datasets_used])

    # Table 1: Competitive Ratio (Revenue Ratio) (Mean ± Std)
    lines.append("## 1. Competitive Ratio (Revenue Ratio) (Mean ± Std)\n\n")
    sep = "|----------|" + "|".join(["------------"] * len(datasets_used)) + "|\n"
    lines.append("| " + header_cols + " |\n")
    lines.append(sep)
    for strat in K_STRATEGIES:
        row = [STRATEGY_LABELS[strat]]
        for ds in datasets_used:
            d = results.get(strat, {}).get(ds)
            if d is not None:
                m, s = np.mean(d['revenue_ratio']), np.std(d['revenue_ratio'])
                row.append(f"{m:.4f} ± {s:.4f}")
            else:
                row.append("N/A")
        lines.append("| " + " | ".join(row) + " |\n")

    # Table 2: Time Ratio (Mean ± Std)
    lines.append("\n## 2. Time Ratio (Mean ± Std)\n\n")
    lines.append("| " + header_cols + " |\n")
    lines.append(sep)
    for strat in K_STRATEGIES:
        row = [STRATEGY_LABELS[strat]]
        for ds in datasets_used:
            d = results.get(strat, {}).get(ds)
            if d is not None:
                m, s = np.mean(d['runtime_ratio']), np.std(d['runtime_ratio'])
                row.append(f"{m:.4f} ± {s:.4f}")
            else:
                row.append("N/A")
        lines.append("| " + " | ".join(row) + " |\n")

    # Table 3: Competitive Ratio (Mean only)
    lines.append("\n## 3. Competitive Ratio (Mean)\n\n")
    lines.append("| " + header_cols + " |\n")
    lines.append(sep)
    for strat in K_STRATEGIES:
        row = [STRATEGY_LABELS[strat]]
        for ds in datasets_used:
            d = results.get(strat, {}).get(ds)
            row.append(f"{np.mean(d['revenue_ratio']):.4f}" if d is not None else "N/A")
        lines.append("| " + " | ".join(row) + " |\n")

    # Table 4: Time Ratio (Mean only)
    lines.append("\n## 4. Time Ratio (Mean)\n\n")
    lines.append("| " + header_cols + " |\n")
    lines.append(sep)
    for strat in K_STRATEGIES:
        row = [STRATEGY_LABELS[strat]]
        for ds in datasets_used:
            d = results.get(strat, {}).get(ds)
            row.append(f"{np.mean(d['runtime_ratio']):.4f}" if d is not None else "N/A")
        lines.append("| " + " | ".join(row) + " |\n")

    out_path = os.path.join(SCRIPT_DIR, 'K_justify_comparison_tables.md')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    print(f"Saved: {out_path}")

    # Also print to console
    print("\n--- Competitive Ratio (Mean ± Std) ---")
    for strat in K_STRATEGIES:
        vals = []
        for ds in datasets_used:
            d = results.get(strat, {}).get(ds)
            vals.append(f"{np.mean(d['revenue_ratio']):.4f}±{np.std(d['revenue_ratio']):.4f}" if d else "N/A")
        print(f"  {STRATEGY_LABELS[strat]:12} | " + " | ".join(vals))
    print("\n--- Time Ratio (Mean ± Std) ---")
    for strat in K_STRATEGIES:
        vals = []
        for ds in datasets_used:
            d = results.get(strat, {}).get(ds)
            vals.append(f"{np.mean(d['runtime_ratio']):.4f}±{np.std(d['runtime_ratio']):.4f}" if d else "N/A")
        print(f"  {STRATEGY_LABELS[strat]:12} | " + " | ".join(vals))


if __name__ == "__main__":
    main()
