"""
分析K=sqrt(m)策略的结果，并与K=2*sqrt(m)和原策略对比
"""
import pandas as pd
import numpy as np
import os

print("=" * 80)
print("K=sqrt(m) vs K=2*sqrt(m) vs 原策略对比分析")
print("=" * 80)

# 读取K=sqrt(m)的结果
sqrtm_results = {}
sqrtm_files = {
    'test_result_global_topk_sqrtm_m10_n10_sample_100.csv': 'm10_n10',
    'test_result_global_topk_sqrtm_test_BSP_m10n15.csv': 'BSP_m10n15',
    'test_result_global_topk_sqrtm_test_BSP_m10n20.csv': 'BSP_m10n20',
    'test_result_global_topk_sqrtm_test_BSP_m15n15.csv': 'BSP_m15n15',
}

for filename, dataset_name in sqrtm_files.items():
    if os.path.exists(filename):
        df = pd.read_csv(filename)
        sqrtm_results[dataset_name] = df
        print(f"读取K=sqrt(m)结果: {filename} - {dataset_name}")

# 读取K=2*sqrt(m)的结果
topk2_results = {}
topk2_files = {
    'test_result_global_topk_m10_n10_sample_100.csv': 'm10_n10',
    'test_result_global_topk_test_BSP_m10n15.csv': 'BSP_m10n15',
    'test_result_global_topk_test_BSP_m10n20.csv': 'BSP_m10n20',
    'test_result_global_topk_test_BSP_m15n15.csv': 'BSP_m15n15',
}

for filename, dataset_name in topk2_files.items():
    if os.path.exists(filename):
        df = pd.read_csv(filename)
        topk2_results[dataset_name] = df
        print(f"读取K=2*sqrt(m)结果: {filename} - {dataset_name}")

# 读取原策略结果
original_results = {}
original_files = {
    'test_result_local_search_mix_m10_n10_sample_100.csv': 'm10_n10',
    'test_result_local_search_mix_test_BSP_m10n15.csv': 'BSP_m10n15',
    'test_result_local_search_mix_test_BSP_m10n20.csv': 'BSP_m10n20',
    'test_result_local_search_mix_test_BSP_m15n15.csv': 'BSP_m15n15',
}

for filename, dataset_name in original_files.items():
    if os.path.exists(filename):
        df = pd.read_csv(filename)
        original_results[dataset_name] = df
        print(f"读取原策略结果: {filename} - {dataset_name}")

# 生成对比报告
print("\n" + "=" * 80)
print("策略对比表")
print("=" * 80)

report_lines = []
report_lines.append("# K值调整效果对比报告\n\n")
report_lines.append("## 实验概述\n\n")
report_lines.append("**实验目的**: 测试K=sqrt(m)策略，对比K=2*sqrt(m)和原策略(Segment-based)的效果\n\n")
report_lines.append("**测试数据集**:\n")
report_lines.append("- m10_n10 (m=10, n=10)\n")
report_lines.append("- BSP_m10n15 (m=10, n=15)\n")
report_lines.append("- BSP_m10n20 (m=10, n=20)\n")
report_lines.append("- BSP_m15n15 (m=15, n=15)\n\n")

report_lines.append("---\n\n")
report_lines.append("## 一、完整性能对比表\n\n")
report_lines.append("| 数据集 | 策略 | K值 | Revenue Ratio | Time Ratio | 总时间(s) | LP调用 | 迭代次数 |\n")
report_lines.append("|--------|------|-----|---------------|------------|-----------|--------|---------|\n")

datasets_order = ['m10_n10', 'BSP_m10n15', 'BSP_m10n20', 'BSP_m15n15']
m_values = {'m10_n10': 10, 'BSP_m10n15': 10, 'BSP_m10n20': 10, 'BSP_m15n15': 15}

for dataset_name in datasets_order:
    m = m_values[dataset_name]
    k_sqrt = int(np.ceil(np.sqrt(m)))
    k_2sqrt = int(np.ceil(2 * np.sqrt(m)))
    
    # 原策略
    if dataset_name in original_results:
        df = original_results[dataset_name]
        revenue = df['revenue_ratio'].mean()
        revenue_std = df['revenue_ratio'].std()
        time_ratio = df['runtime_ratio'].mean()
        time_std = df['runtime_ratio'].std()
        total_time = df['total_time'].mean()
        lp_calls = df['lp_solver_calls'].mean()
        iterations = df['iterations'].mean()
        report_lines.append(f"| {dataset_name} | 原策略 | 2*m={2*m} | {revenue:.4f} ± {revenue_std:.4f} | {time_ratio:.4f} ± {time_std:.4f} | {total_time:.3f} | {lp_calls:.1f} | {iterations:.1f} |\n")
    
    # K=2*sqrt(m)
    if dataset_name in topk2_results:
        df = topk2_results[dataset_name]
        revenue = df['revenue_ratio'].mean()
        revenue_std = df['revenue_ratio'].std()
        time_ratio = df['runtime_ratio'].mean()
        time_std = df['runtime_ratio'].std()
        total_time = df['total_time'].mean()
        lp_calls = df['lp_solver_calls'].mean()
        iterations = df['iterations'].mean()
        report_lines.append(f"| {dataset_name} | Global Top-K | K={k_2sqrt} | {revenue:.4f} ± {revenue_std:.4f} | {time_ratio:.4f} ± {time_std:.4f} | {total_time:.3f} | {lp_calls:.1f} | {iterations:.1f} |\n")
    
    # K=sqrt(m)
    if dataset_name in sqrtm_results:
        df = sqrtm_results[dataset_name]
        revenue = df['revenue_ratio'].mean()
        revenue_std = df['revenue_ratio'].std()
        time_ratio = df['runtime_ratio'].mean()
        time_std = df['runtime_ratio'].std()
        total_time = df['total_time'].mean()
        lp_calls = df['lp_solver_calls'].mean()
        iterations = df['iterations'].mean()
        report_lines.append(f"| {dataset_name} | Global Top-K | K={k_sqrt} | {revenue:.4f} ± {revenue_std:.4f} | {time_ratio:.4f} ± {time_std:.4f} | {total_time:.3f} | {lp_calls:.1f} | {iterations:.1f} |\n")

# 详细对比分析
report_lines.append("\n---\n\n")
report_lines.append("## 二、详细对比分析\n\n")

for dataset_name in datasets_order:
    m = m_values[dataset_name]
    k_sqrt = int(np.ceil(np.sqrt(m)))
    k_2sqrt = int(np.ceil(2 * np.sqrt(m)))
    
    report_lines.append(f"### {dataset_name} (m={m}, n={m_values.get(dataset_name, 'N/A')})\n\n")
    report_lines.append("| 指标 | 原策略 (2*m) | K=2*sqrt(m) | K=sqrt(m) | K=sqrt(m) vs 原策略 | K=sqrt(m) vs K=2*sqrt(m) |\n")
    report_lines.append("|------|-------------|------------|-----------|-------------------|------------------------|\n")
    
    # Revenue Ratio
    if dataset_name in original_results and dataset_name in topk2_results and dataset_name in sqrtm_results:
        orig_rev = original_results[dataset_name]['revenue_ratio'].mean()
        topk2_rev = topk2_results[dataset_name]['revenue_ratio'].mean()
        sqrtm_rev = sqrtm_results[dataset_name]['revenue_ratio'].mean()
        diff_orig = sqrtm_rev - orig_rev
        diff_topk2 = sqrtm_rev - topk2_rev
        diff_orig_pct = (diff_orig / orig_rev) * 100 if orig_rev > 0 else 0
        diff_topk2_pct = (diff_topk2 / topk2_rev) * 100 if topk2_rev > 0 else 0
        report_lines.append(f"| **Revenue Ratio** | {orig_rev:.4f} | {topk2_rev:.4f} | {sqrtm_rev:.4f} | {diff_orig:+.4f} ({diff_orig_pct:+.2f}%) | {diff_topk2:+.4f} ({diff_topk2_pct:+.2f}%) |\n")
        
        # Time Ratio
        orig_time = original_results[dataset_name]['runtime_ratio'].mean()
        topk2_time = topk2_results[dataset_name]['runtime_ratio'].mean()
        sqrtm_time = sqrtm_results[dataset_name]['runtime_ratio'].mean()
        diff_orig = sqrtm_time - orig_time
        diff_topk2 = sqrtm_time - topk2_time
        diff_orig_pct = (diff_orig / orig_time) * 100 if orig_time > 0 else 0
        diff_topk2_pct = (diff_topk2 / topk2_time) * 100 if topk2_time > 0 else 0
        report_lines.append(f"| **Time Ratio** | {orig_time:.4f} | {topk2_time:.4f} | {sqrtm_time:.4f} | {diff_orig:+.4f} ({diff_orig_pct:+.2f}%) | {diff_topk2:+.4f} ({diff_topk2_pct:+.2f}%) |\n")
        
        # 总时间
        orig_total = original_results[dataset_name]['total_time'].mean()
        topk2_total = topk2_results[dataset_name]['total_time'].mean()
        sqrtm_total = sqrtm_results[dataset_name]['total_time'].mean()
        diff_orig_pct = ((sqrtm_total - orig_total) / orig_total) * 100 if orig_total > 0 else 0
        diff_topk2_pct = ((sqrtm_total - topk2_total) / topk2_total) * 100 if topk2_total > 0 else 0
        report_lines.append(f"| **总时间** | {orig_total:.3f}s | {topk2_total:.3f}s | {sqrtm_total:.3f}s | {diff_orig_pct:+.2f}% | {diff_topk2_pct:+.2f}% |\n")
        
        # LP调用次数
        orig_lp = original_results[dataset_name]['lp_solver_calls'].mean()
        topk2_lp = topk2_results[dataset_name]['lp_solver_calls'].mean()
        sqrtm_lp = sqrtm_results[dataset_name]['lp_solver_calls'].mean()
        diff_orig_pct = ((sqrtm_lp - orig_lp) / orig_lp) * 100 if orig_lp > 0 else 0
        diff_topk2_pct = ((sqrtm_lp - topk2_lp) / topk2_lp) * 100 if topk2_lp > 0 else 0
        report_lines.append(f"| **LP调用次数** | {orig_lp:.1f} | {topk2_lp:.1f} | {sqrtm_lp:.1f} | {diff_orig_pct:+.2f}% | {diff_topk2_pct:+.2f}% |\n")
    
    report_lines.append("\n")

# 总结
report_lines.append("---\n\n")
report_lines.append("## 三、关键发现总结\n\n")

report_lines.append("### 3.1 Revenue Ratio对比\n\n")
report_lines.append("| 数据集 | 原策略 | K=2*sqrt(m) | K=sqrt(m) | K=sqrt(m) vs 原策略 | K=sqrt(m) vs K=2*sqrt(m) |\n")
report_lines.append("|--------|--------|------------|-----------|-------------------|------------------------|\n")

for dataset_name in datasets_order:
    if dataset_name in original_results and dataset_name in topk2_results and dataset_name in sqrtm_results:
        orig_rev = original_results[dataset_name]['revenue_ratio'].mean()
        topk2_rev = topk2_results[dataset_name]['revenue_ratio'].mean()
        sqrtm_rev = sqrtm_results[dataset_name]['revenue_ratio'].mean()
        diff_orig = sqrtm_rev - orig_rev
        diff_topk2 = sqrtm_rev - topk2_rev
        diff_orig_pct = (diff_orig / orig_rev) * 100 if orig_rev > 0 else 0
        diff_topk2_pct = (diff_topk2 / topk2_rev) * 100 if topk2_rev > 0 else 0
        report_lines.append(f"| {dataset_name} | {orig_rev:.4f} | {topk2_rev:.4f} | {sqrtm_rev:.4f} | {diff_orig:+.4f} ({diff_orig_pct:+.2f}%) | {diff_topk2:+.4f} ({diff_topk2_pct:+.2f}%) |\n")

report_lines.append("\n### 3.2 Time Ratio对比\n\n")
report_lines.append("| 数据集 | 原策略 | K=2*sqrt(m) | K=sqrt(m) | K=sqrt(m) vs 原策略 | K=sqrt(m) vs K=2*sqrt(m) |\n")
report_lines.append("|--------|--------|------------|-----------|-------------------|------------------------|\n")

for dataset_name in datasets_order:
    if dataset_name in original_results and dataset_name in topk2_results and dataset_name in sqrtm_results:
        orig_time = original_results[dataset_name]['runtime_ratio'].mean()
        topk2_time = topk2_results[dataset_name]['runtime_ratio'].mean()
        sqrtm_time = sqrtm_results[dataset_name]['runtime_ratio'].mean()
        diff_orig = sqrtm_time - orig_time
        diff_topk2 = sqrtm_time - topk2_time
        diff_orig_pct = (diff_orig / orig_time) * 100 if orig_time > 0 else 0
        diff_topk2_pct = (diff_topk2 / topk2_time) * 100 if topk2_time > 0 else 0
        report_lines.append(f"| {dataset_name} | {orig_time:.4f} | {topk2_time:.4f} | {sqrtm_time:.4f} | {diff_orig:+.4f} ({diff_orig_pct:+.2f}%) | {diff_topk2:+.4f} ({diff_topk2_pct:+.2f}%) |\n")

report_lines.append("\n---\n\n")
report_lines.append("**报告生成时间**: 2024年  \n")
report_lines.append("**实验环境**: Windows, Python 3.11, Gurobi, PyTorch Geometric\n")

# 写入文件
with open('K值调整效果对比报告.md', 'w', encoding='utf-8') as f:
    f.writelines(report_lines)

print("\n报告已生成: K值调整效果对比报告.md")


