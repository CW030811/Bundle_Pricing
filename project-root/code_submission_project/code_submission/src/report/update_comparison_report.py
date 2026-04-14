"""
更新路径策略效果对比报告，添加原策略在所有数据集上的结果
"""
import pandas as pd
import numpy as np
import os

print("=" * 80)
print("更新路径策略效果对比报告")
print("=" * 80)

# 读取所有结果文件
original_results = {}
global_topk_results = {}

# 原策略（Segment-based）结果
original_files = {
    'test_result_local_search_mix_m10_n10_sample_100.csv': ('m10_n10', 10, 10),
    'test_result_local_search_mix_m20_n10_sample_100.csv': ('m20_n10', 20, 10),
    'test_result_local_search_mix_test_BSP_m10n15.csv': ('BSP_m10n15', 10, 15),
    'test_result_local_search_mix_test_BSP_m10n20.csv': ('BSP_m10n20', 10, 20),
    'test_result_local_search_mix_test_BSP_m10n25.csv': ('BSP_m10n25', 10, 25),
    'test_result_local_search_mix_test_BSP_m15n15.csv': ('BSP_m15n15', 15, 15),
    'test_result_local_search_mix_test_BSP_m20n15.csv': ('BSP_m20n15', 20, 15),
}

for filename, (dataset_name, m, n) in original_files.items():
    if os.path.exists(filename):
        df = pd.read_csv(filename)
        original_results[dataset_name] = {
            'm': m,
            'n': n,
            'df': df
        }
        print(f"读取原策略结果: {filename} - {dataset_name}")

# Global Top-K策略结果
global_topk_files = {
    'test_result_global_topk_m10_n10_sample_100.csv': ('m10_n10', 10, 10),
    'test_result_global_topk_m20_n10_sample_100.csv': ('m20_n10', 20, 10),
    'test_result_global_topk_m30_n10_sample_100.csv': ('m30_n10', 30, 10),
    'test_result_global_topk_test_BSP_m10n15.csv': ('BSP_m10n15', 10, 15),
    'test_result_global_topk_test_BSP_m10n20.csv': ('BSP_m10n20', 10, 20),
    'test_result_global_topk_test_BSP_m10n25.csv': ('BSP_m10n25', 10, 25),
    'test_result_global_topk_test_BSP_m15n15.csv': ('BSP_m15n15', 15, 15),
    'test_result_global_topk_test_BSP_m20n15.csv': ('BSP_m20n15', 20, 15),
}

for filename, (dataset_name, m, n) in global_topk_files.items():
    if os.path.exists(filename):
        df = pd.read_csv(filename)
        global_topk_results[dataset_name] = {
            'm': m,
            'n': n,
            'df': df
        }
        print(f"读取Global Top-K结果: {filename} - {dataset_name}")

# 生成对比表
print("\n" + "=" * 80)
print("策略对比表")
print("=" * 80)

# 获取所有数据集（按m和n排序）
all_datasets = set()
for key in original_results.keys():
    all_datasets.add(key)
for key in global_topk_results.keys():
    all_datasets.add(key)

sorted_datasets = sorted(all_datasets, key=lambda x: (original_results.get(x, global_topk_results.get(x, {}))['m'], 
                                                      original_results.get(x, global_topk_results.get(x, {}))['n']))

# 生成报告内容
report_lines = []
report_lines.append("# Local Search 路径策略效果对比报告\n\n")
report_lines.append("## 实验概述\n\n")
report_lines.append("**实验日期**: 2024年  \n")
report_lines.append("**测试策略**: \n")
report_lines.append("1. **原策略 (Segment-based)**: 每轮生成 2*m 个邻域\n")
report_lines.append("2. **新策略 (Global Top-K)**: 每轮生成最多 2*K 个邻域，K = ceil(2 * sqrt(m))\n\n")

# 数据集列表
datasets_list = []
for dataset_name in sorted_datasets:
    data = original_results.get(dataset_name) or global_topk_results.get(dataset_name)
    if data:
        m, n = data['m'], data['n']
        has_original = dataset_name in original_results
        has_topk = dataset_name in global_topk_results
        if has_original and has_topk:
            datasets_list.append(f"- {dataset_name} (m={m}, n={n}) - 两种策略都有测试")
        elif has_original:
            datasets_list.append(f"- {dataset_name} (m={m}, n={n}) - 仅原策略")
        else:
            datasets_list.append(f"- {dataset_name} (m={m}, n={n}) - 仅Global Top-K")

report_lines.append("**数据集**:\n")
report_lines.append("\n".join(datasets_list))
report_lines.append("\n\n---\n\n")

# 完整对比表
report_lines.append("## 一、完整性能对比表\n\n")
report_lines.append("| 数据集 | m | n | 策略 | Revenue Ratio | Time Ratio | 总时间(s) | LP调用 | 迭代次数 |\n")
report_lines.append("|--------|---|---|------|---------------|------------|-----------|--------|---------|\n")

for dataset_name in sorted_datasets:
    data_orig = original_results.get(dataset_name)
    data_topk = global_topk_results.get(dataset_name)
    
    if data_orig:
        df_orig = data_orig['df']
        m, n = data_orig['m'], data_orig['n']
        revenue_orig = df_orig['revenue_ratio'].mean()
        revenue_std_orig = df_orig['revenue_ratio'].std()
        time_orig = df_orig['runtime_ratio'].mean()
        time_std_orig = df_orig['runtime_ratio'].std()
        total_time_orig = df_orig['total_time'].mean()
        lp_orig = df_orig['lp_solver_calls'].mean()
        iter_orig = df_orig['iterations'].mean()
        
        report_lines.append(f"| {dataset_name} | {m} | {n} | 原策略 | {revenue_orig:.4f} ± {revenue_std_orig:.4f} | {time_orig:.4f} ± {time_std_orig:.4f} | {total_time_orig:.3f} | {lp_orig:.1f} | {iter_orig:.1f} |\n")
    
    if data_topk:
        df_topk = data_topk['df']
        m, n = data_topk['m'], data_topk['n']
        revenue_topk = df_topk['revenue_ratio'].mean()
        revenue_std_topk = df_topk['revenue_ratio'].std()
        time_topk = df_topk['runtime_ratio'].mean()
        time_std_topk = df_topk['runtime_ratio'].std()
        total_time_topk = df_topk['total_time'].mean()
        lp_topk = df_topk['lp_solver_calls'].mean()
        iter_topk = df_topk['iterations'].mean()
        
        report_lines.append(f"| {dataset_name} | {m} | {n} | Global Top-K | {revenue_topk:.4f} ± {revenue_std_topk:.4f} | {time_topk:.4f} ± {time_std_topk:.4f} | {total_time_topk:.3f} | {lp_topk:.1f} | {iter_topk:.1f} |\n")

# 详细对比分析（仅针对两种策略都有的数据集）
report_lines.append("\n---\n\n")
report_lines.append("## 二、详细对比分析（两种策略都有的数据集）\n\n")

for dataset_name in sorted_datasets:
    data_orig = original_results.get(dataset_name)
    data_topk = global_topk_results.get(dataset_name)
    
    if data_orig and data_topk:
        df_orig = data_orig['df']
        df_topk = data_topk['df']
        m, n = data_orig['m'], data_orig['n']
        
        revenue_orig = df_orig['revenue_ratio'].mean()
        revenue_std_orig = df_orig['revenue_ratio'].std()
        revenue_topk = df_topk['revenue_ratio'].mean()
        revenue_std_topk = df_topk['revenue_ratio'].std()
        revenue_change = revenue_topk - revenue_orig
        revenue_change_pct = (revenue_change / revenue_orig) * 100 if revenue_orig > 0 else 0
        
        time_orig = df_orig['runtime_ratio'].mean()
        time_std_orig = df_orig['runtime_ratio'].std()
        time_topk = df_topk['runtime_ratio'].mean()
        time_std_topk = df_topk['runtime_ratio'].std()
        time_change = time_topk - time_orig
        time_change_pct = (time_change / time_orig) * 100 if time_orig > 0 else 0
        
        total_time_orig = df_orig['total_time'].mean()
        total_time_topk = df_topk['total_time'].mean()
        total_time_change_pct = ((total_time_topk - total_time_orig) / total_time_orig) * 100 if total_time_orig > 0 else 0
        
        lp_orig = df_orig['lp_solver_calls'].mean()
        lp_topk = df_topk['lp_solver_calls'].mean()
        lp_change_pct = ((lp_topk - lp_orig) / lp_orig) * 100 if lp_orig > 0 else 0
        
        report_lines.append(f"### {dataset_name} (m={m}, n={n})\n\n")
        report_lines.append("| 指标 | 原策略 (Segment-based) | Global Top-K | 变化 |\n")
        report_lines.append("|------|----------------------|-------------|------|\n")
        report_lines.append(f"| **Revenue Ratio** | {revenue_orig:.4f} ± {revenue_std_orig:.4f} | {revenue_topk:.4f} ± {revenue_std_topk:.4f} | {revenue_change:+.4f} ({revenue_change_pct:+.2f}%) |\n")
        report_lines.append(f"| **Time Ratio** | {time_orig:.4f} ± {time_std_orig:.4f} | {time_topk:.4f} ± {time_std_topk:.4f} | {time_change:+.4f} ({time_change_pct:+.2f}%) |\n")
        report_lines.append(f"| **总时间** | {total_time_orig:.3f}s | {total_time_topk:.3f}s | {total_time_change_pct:+.2f}% |\n")
        report_lines.append(f"| **LP调用次数** | {lp_orig:.1f} | {lp_topk:.1f} | {lp_change_pct:+.2f}% |\n")
        report_lines.append("\n")

# 总结
report_lines.append("---\n\n")
report_lines.append("## 三、关键发现总结\n\n")

report_lines.append("### 3.1 Revenue Ratio对比\n\n")
report_lines.append("| 数据集 | 原策略 | Global Top-K | 差异 |\n")
report_lines.append("|--------|--------|-------------|------|\n")

for dataset_name in sorted_datasets:
    data_orig = original_results.get(dataset_name)
    data_topk = global_topk_results.get(dataset_name)
    
    if data_orig and data_topk:
        revenue_orig = data_orig['df']['revenue_ratio'].mean()
        revenue_topk = data_topk['df']['revenue_ratio'].mean()
        diff = revenue_topk - revenue_orig
        diff_pct = (diff / revenue_orig) * 100 if revenue_orig > 0 else 0
        report_lines.append(f"| {dataset_name} | {revenue_orig:.4f} | {revenue_topk:.4f} | {diff:+.4f} ({diff_pct:+.2f}%) |\n")

report_lines.append("\n### 3.2 Time Ratio对比\n\n")
report_lines.append("| 数据集 | 原策略 | Global Top-K | 差异 |\n")
report_lines.append("|--------|--------|-------------|------|\n")

for dataset_name in sorted_datasets:
    data_orig = original_results.get(dataset_name)
    data_topk = global_topk_results.get(dataset_name)
    
    if data_orig and data_topk:
        time_orig = data_orig['df']['runtime_ratio'].mean()
        time_topk = data_topk['df']['runtime_ratio'].mean()
        diff = time_topk - time_orig
        diff_pct = (diff / time_orig) * 100 if time_orig > 0 else 0
        report_lines.append(f"| {dataset_name} | {time_orig:.4f} | {time_topk:.4f} | {diff:+.4f} ({diff_pct:+.2f}%) |\n")

report_lines.append("\n---\n\n")
report_lines.append("**报告生成时间**: 2024年  \n")
report_lines.append("**实验环境**: Windows, Python 3.11, Gurobi, PyTorch Geometric\n")

# 写入文件
with open('路径策略效果对比报告.md', 'w', encoding='utf-8') as f:
    f.writelines(report_lines)

print("\n报告已更新: 路径策略效果对比报告.md")



