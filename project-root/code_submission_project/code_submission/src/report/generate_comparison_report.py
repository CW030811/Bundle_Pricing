"""
生成路径策略效果对比报告
"""
import pandas as pd
import numpy as np
from math import ceil, sqrt

# 读取所有结果文件
results = {}

# 原策略（Segment-based）结果
try:
    df_original = pd.read_csv('test_result_local_search_mix_m10_n10_sample_100.csv')
    results['original_m10n10'] = {
        'strategy': 'Segment-based (2*m)',
        'm': 10,
        'n': 10,
        'df': df_original
    }
except:
    pass

# Global Top-K策略结果
global_topk_files = {
    'test_result_global_topk_m10_n10_sample_100.csv': (10, 10),
    'test_result_global_topk_m20_n10_sample_100.csv': (20, 10),
    'test_result_global_topk_m30_n10_sample_100.csv': (30, 10),
    'test_result_global_topk_test_BSP_m10n15.csv': (10, 15),
    'test_result_global_topk_test_BSP_m10n20.csv': (10, 20),
    'test_result_global_topk_test_BSP_m10n25.csv': (10, 25),
    'test_result_global_topk_test_BSP_m15n15.csv': (15, 15),
    'test_result_global_topk_test_BSP_m20n15.csv': (20, 15),
}

for filename, (m, n) in global_topk_files.items():
    try:
        df = pd.read_csv(filename)
        key = f'global_topk_m{m}n{n}'
        results[key] = {
            'strategy': 'Global Top-K',
            'm': m,
            'n': n,
            'df': df,
            'filename': filename
        }
    except Exception as e:
        print(f"Error reading {filename}: {e}")

# 生成报告
report_lines = []
report_lines.append("# Local Search 路径策略效果对比报告\n")
report_lines.append("## 实验概述\n\n")
report_lines.append("**实验日期**: 2024年  \n")
report_lines.append("**测试策略**: \n")
report_lines.append("1. **原策略 (Segment-based)**: 每轮生成 2*m 个邻域\n")
report_lines.append("2. **新策略 (Global Top-K)**: 每轮生成最多 2*K 个邻域，K = ceil(2 * sqrt(m))\n\n")

# 数据集列表
datasets_list = []
if 'original_m10n10' in results:
    datasets_list.append("- m10_n10_sample_100 (m=10, n=10) - 两种策略都有测试")
for key, data in results.items():
    if data['strategy'] == 'Global Top-K':
        m, n = data['m'], data['n']
        if f"m{m}_n{n}" not in [d.split()[0] for d in datasets_list]:
            if 'BSP' in key:
                datasets_list.append(f"- test_BSP_m{m}n{n} (m={m}, n={n}) - 仅Global Top-K")
            else:
                datasets_list.append(f"- m{m}_n{n}_sample_100 (m={m}, n={n}) - 仅Global Top-K")

report_lines.append("**数据集**:\n")
report_lines.append("\n".join(datasets_list))
report_lines.append("\n\n---\n\n")

# m10n10对比
if 'original_m10n10' in results and 'global_topk_m10n10' in results:
    df_orig = results['original_m10n10']['df']
    df_topk = results['global_topk_m10n10']['df']
    
    report_lines.append("## 一、m10_n10_sample_100 数据集策略对比\n\n")
    report_lines.append("### 1.1 性能指标对比\n\n")
    report_lines.append("| 指标 | 原策略 (Segment-based) | 新策略 (Global Top-K) | 变化 |\n")
    report_lines.append("|------|----------------------|---------------------|------|\n")
    
    revenue_orig = df_orig['revenue_ratio'].mean()
    revenue_std_orig = df_orig['revenue_ratio'].std()
    revenue_topk = df_topk['revenue_ratio'].mean()
    revenue_std_topk = df_topk['revenue_ratio'].std()
    revenue_change = revenue_topk - revenue_orig
    revenue_change_pct = (revenue_change / revenue_orig) * 100
    
    time_orig = df_orig['runtime_ratio'].mean()
    time_std_orig = df_orig['runtime_ratio'].std()
    time_topk = df_topk['runtime_ratio'].mean()
    time_std_topk = df_topk['runtime_ratio'].std()
    time_change = time_topk - time_orig
    time_change_pct = (time_change / time_orig) * 100
    
    total_time_orig = df_orig['total_time'].mean()
    total_time_topk = df_topk['total_time'].mean()
    total_time_change_pct = ((total_time_topk - total_time_orig) / total_time_orig) * 100
    
    ls_time_orig = df_orig['local_search_time'].mean()
    ls_time_topk = df_topk['local_search_time'].mean()
    ls_time_change_pct = ((ls_time_topk - ls_time_orig) / ls_time_orig) * 100
    
    lp_orig = df_orig['lp_solver_calls'].mean()
    lp_topk = df_topk['lp_solver_calls'].mean()
    lp_change_pct = ((lp_topk - lp_orig) / lp_orig) * 100
    
    iter_orig = df_orig['iterations'].mean()
    iter_topk = df_topk['iterations'].mean()
    iter_change = iter_topk - iter_orig
    iter_change_pct = (iter_change / iter_orig) * 100
    
    improvements_orig = (df_orig['improvements'] > 0).sum() / len(df_orig) * 100
    improvements_topk = (df_topk['improvements'] > 0).sum() / len(df_topk) * 100
    
    report_lines.append(f"| **Revenue Ratio** | {revenue_orig:.4f} ± {revenue_std_orig:.4f} | {revenue_topk:.4f} ± {revenue_std_topk:.4f} | {revenue_change:+.4f} ({revenue_change_pct:+.2f}%) |\n")
    report_lines.append(f"| **Time Ratio** | {time_orig:.4f} ± {time_std_orig:.4f} | {time_topk:.4f} ± {time_std_topk:.4f} | {time_change:+.4f} ({time_change_pct:+.2f}%) |\n")
    report_lines.append(f"| **总时间** | {total_time_orig:.3f}s | {total_time_topk:.3f}s | {total_time_change_pct:+.2f}% |\n")
    report_lines.append(f"| **Local Search 时间** | {ls_time_orig:.3f}s | {ls_time_topk:.3f}s | {ls_time_change_pct:+.2f}% |\n")
    report_lines.append(f"| **LP 调用次数** | {lp_orig:.2f} | {lp_topk:.2f} | {lp_change_pct:+.2f}% |\n")
    report_lines.append(f"| **迭代次数** | {iter_orig:.2f} | {iter_topk:.2f} | {iter_change:+.2f} ({iter_change_pct:+.2f}%) |\n")
    report_lines.append(f"| **每轮最大邻域数** | 20 | 14 | -6 (-30.0%) |\n")
    report_lines.append(f"| **改进率** | {improvements_orig:.1f}% | {improvements_topk:.1f}% | 持平 |\n\n")

# Global Top-K策略完整性能表
report_lines.append("## 二、Global Top-K 策略在各数据集上的表现\n\n")
report_lines.append("### 2.1 完整性能表\n\n")
report_lines.append("| 数据集 | m | n | Revenue Ratio | Time Ratio | 总时间(s) | Local Search时间(s) | LP调用 | 迭代次数 | K值 | 最大邻域/轮 | 改进率 |\n")
report_lines.append("|--------|---|---|---------------|------------|-----------|-------------------|--------|---------|-----|------------|--------|\n")

sorted_results = sorted([(k, v) for k, v in results.items() if v['strategy'] == 'Global Top-K'], 
                        key=lambda x: (x[1]['m'], x[1]['n']))

for key, data in sorted_results:
    df = data['df']
    m = data['m']
    n = data['n']
    
    if 'BSP' in key:
        dataset_name = f"BSP_m{m}n{n}"
    else:
        dataset_name = f"m{m}_n{n}"
    
    revenue_mean = df['revenue_ratio'].mean()
    revenue_std = df['revenue_ratio'].std()
    time_mean = df['runtime_ratio'].mean()
    time_std = df['runtime_ratio'].std()
    total_time_mean = df['total_time'].mean()
    ls_time_mean = df['local_search_time'].mean()
    lp_mean = df['lp_solver_calls'].mean()
    iter_mean = df['iterations'].mean()
    K_mean = df['K'].mean() if 'K' in df.columns else ceil(2 * sqrt(m))
    max_neighbors = df['max_neighbors_per_iter'].mean() if 'max_neighbors_per_iter' in df.columns else 2 * K_mean
    improvements = (df['improvements'] > 0).sum() / len(df) * 100
    
    report_lines.append(f"| **{dataset_name}** | {m} | {n} | {revenue_mean:.4f} ± {revenue_std:.4f} | {time_mean:.4f} ± {time_std:.4f} | {total_time_mean:.3f} | {ls_time_mean:.3f} | {lp_mean:.1f} | {iter_mean:.1f} | {K_mean:.0f} | {max_neighbors:.0f} | {improvements:.1f}% |\n")

# 写入文件
with open('路径策略效果对比报告.md', 'w', encoding='utf-8') as f:
    f.writelines(report_lines)

print("报告已生成: 路径策略效果对比报告.md")



