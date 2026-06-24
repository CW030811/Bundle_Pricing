"""
分析所有数据集的实验结果，对比原策略和Global Top-K策略
"""
import pandas as pd
import numpy as np
import os
from math import ceil, sqrt

print("=" * 80)
print("Local Search 路径策略综合对比分析")
print("=" * 80)

# 读取所有结果文件
results = {}

# 原策略（Segment-based）结果
if os.path.exists('test_result_local_search_mix_m10_n10_sample_100.csv'):
    df_original = pd.read_csv('test_result_local_search_mix_m10_n10_sample_100.csv')
    results['original_m10n10'] = {
        'strategy': 'Segment-based (2*m)',
        'm': 10,
        'n': 10,
        'df': df_original
    }

# Global Top-K策略结果
global_topk_files = {
    'test_result_global_topk_m10_n10_sample_100.csv': ('Global Top-K', 10, 10),
    'test_result_global_topk_m20_n10_sample_100.csv': ('Global Top-K', 20, 10),
    'test_result_global_topk_m30_n10_sample_100.csv': ('Global Top-K', 30, 10),
    'test_result_global_topk_test_BSP_m10n15.csv': ('Global Top-K', 10, 15),
    'test_result_global_topk_test_BSP_m10n20.csv': ('Global Top-K', 10, 20),
    'test_result_global_topk_test_BSP_m10n25.csv': ('Global Top-K', 10, 25),
    'test_result_global_topk_test_BSP_m15n15.csv': ('Global Top-K', 15, 15),
    'test_result_global_topk_test_BSP_m20n15.csv': ('Global Top-K', 20, 15),
}

for filename, (strategy, m, n) in global_topk_files.items():
    if os.path.exists(filename):
        df = pd.read_csv(filename)
        key = f'{strategy}_m{m}n{n}'
        results[key] = {
            'strategy': strategy,
            'm': m,
            'n': n,
            'df': df,
            'filename': filename
        }

# 生成对比表
print("\n" + "=" * 80)
print("数据集性能对比表")
print("=" * 80)

# 表头
print(f"\n{'数据集':<25} {'策略':<20} {'m':<5} {'n':<5} {'Revenue Ratio':<18} {'Time Ratio':<15} {'总时间(s)':<12} {'LP调用':<10} {'迭代':<8}")
print("-" * 130)

# 按m和n排序输出
sorted_results = sorted(results.items(), key=lambda x: (x[1]['m'], x[1]['n']))

for key, data in sorted_results:
    df = data['df']
    strategy = data['strategy']
    m = data['m']
    n = data['n']
    
    dataset_name = f"m{m}_n{n}"
    if 'BSP' in key:
        dataset_name = f"BSP_m{m}n{n}"
    
    revenue_ratio_mean = df['revenue_ratio'].mean()
    revenue_ratio_std = df['revenue_ratio'].std()
    time_ratio_mean = df['runtime_ratio'].mean()
    time_ratio_std = df['runtime_ratio'].std()
    total_time_mean = df['total_time'].mean()
    lp_calls_mean = df['lp_solver_calls'].mean()
    iterations_mean = df['iterations'].mean()
    
    print(f"{dataset_name:<25} {strategy:<20} {m:<5} {n:<5} "
          f"{revenue_ratio_mean:.4f}±{revenue_ratio_std:.4f}  "
          f"{time_ratio_mean:.4f}±{time_ratio_std:.4f}  "
          f"{total_time_mean:.3f}      "
          f"{lp_calls_mean:.1f}    "
          f"{iterations_mean:.1f}")

# 对比分析：m10n10数据集
print("\n" + "=" * 80)
print("m10_n10_sample_100 数据集策略对比")
print("=" * 80)

if 'original_m10n10' in results and 'Global Top-K_m10n10' in results:
    df_orig = results['original_m10n10']['df']
    df_topk = results['Global Top-K_m10n10']['df']
    
    print(f"\n原策略 (Segment-based, 2*m=20):")
    print(f"  Revenue Ratio: {df_orig['revenue_ratio'].mean():.4f} ± {df_orig['revenue_ratio'].std():.4f}")
    print(f"  Time Ratio: {df_orig['runtime_ratio'].mean():.4f} ± {df_orig['runtime_ratio'].std():.4f}")
    print(f"  总时间: {df_orig['total_time'].mean():.4f}s")
    print(f"  LP调用次数: {df_orig['lp_solver_calls'].mean():.2f}")
    print(f"  迭代次数: {df_orig['iterations'].mean():.2f}")
    
    print(f"\n新策略 (Global Top-K, K=7, 2*K=14):")
    print(f"  Revenue Ratio: {df_topk['revenue_ratio'].mean():.4f} ± {df_topk['revenue_ratio'].std():.4f}")
    print(f"  Time Ratio: {df_topk['runtime_ratio'].mean():.4f} ± {df_topk['runtime_ratio'].std():.4f}")
    print(f"  总时间: {df_topk['total_time'].mean():.4f}s")
    print(f"  LP调用次数: {df_topk['lp_solver_calls'].mean():.2f}")
    print(f"  迭代次数: {df_topk['iterations'].mean():.2f}")
    
    print(f"\n改进效果:")
    revenue_improvement = (df_topk['revenue_ratio'].mean() - df_orig['revenue_ratio'].mean()) / df_orig['revenue_ratio'].mean() * 100
    time_improvement = (df_orig['runtime_ratio'].mean() - df_topk['runtime_ratio'].mean()) / df_orig['runtime_ratio'].mean() * 100
    print(f"  Revenue Ratio提升: {revenue_improvement:+.2f}%")
    print(f"  Time Ratio改善: {time_improvement:+.2f}%")
    print(f"  总时间减少: {(1 - df_topk['total_time'].mean() / df_orig['total_time'].mean()) * 100:+.2f}%")
    print(f"  LP调用减少: {(1 - df_topk['lp_solver_calls'].mean() / df_orig['lp_solver_calls'].mean()) * 100:+.2f}%")

# BSP数据集汇总
print("\n" + "=" * 80)
print("BSP数据集汇总（仅Global Top-K策略）")
print("=" * 80)

bsp_results = {k: v for k, v in results.items() if 'BSP' in k}
if bsp_results:
    print(f"\n{'数据集':<20} {'m':<5} {'n':<5} {'Revenue Ratio':<18} {'Time Ratio':<15} {'总时间(s)':<12} {'LP调用':<10} {'K值':<6}")
    print("-" * 100)
    
    for key, data in sorted(bsp_results.items(), key=lambda x: (x[1]['m'], x[1]['n'])):
        df = data['df']
        m = data['m']
        n = data['n']
        dataset_name = f"BSP_m{m}n{n}"
        
        revenue_ratio_mean = df['revenue_ratio'].mean()
        revenue_ratio_std = df['revenue_ratio'].std()
        time_ratio_mean = df['runtime_ratio'].mean()
        time_ratio_std = df['runtime_ratio'].std()
        total_time_mean = df['total_time'].mean()
        lp_calls_mean = df['lp_solver_calls'].mean()
        K_mean = df['K'].mean()
        
        print(f"{dataset_name:<20} {m:<5} {n:<5} "
              f"{revenue_ratio_mean:.4f}±{revenue_ratio_std:.4f}  "
              f"{time_ratio_mean:.4f}±{time_ratio_std:.4f}  "
              f"{total_time_mean:.3f}      "
              f"{lp_calls_mean:.1f}    "
              f"{K_mean:.0f}")

# 可扩展性分析
print("\n" + "=" * 80)
print("可扩展性分析")
print("=" * 80)

# 按m分组分析
m_groups = {}
for key, data in results.items():
    if data['strategy'] == 'Global Top-K':
        m = data['m']
        if m not in m_groups:
            m_groups[m] = []
        m_groups[m].append(data)

for m in sorted(m_groups.keys()):
    print(f"\nm={m} (客户段数):")
    print(f"  K值: {ceil(2 * sqrt(m)):.0f}, 最大邻域数/轮: {2 * ceil(2 * sqrt(m)):.0f}")
    for data in sorted(m_groups[m], key=lambda x: x['n']):
        df = data['df']
        n = data['n']
        print(f"    n={n}: Revenue={df['revenue_ratio'].mean():.4f}, "
              f"Time={df['total_time'].mean():.3f}s, "
              f"LP调用={df['lp_solver_calls'].mean():.1f}, "
              f"迭代={df['iterations'].mean():.1f}")

# 按n分组分析
n_groups = {}
for key, data in results.items():
    if data['strategy'] == 'Global Top-K':
        n = data['n']
        if n not in n_groups:
            n_groups[n] = []
        n_groups[n].append(data)

for n in sorted(n_groups.keys()):
    print(f"\nn={n} (产品数):")
    for data in sorted(n_groups[n], key=lambda x: x['m']):
        df = data['df']
        m = data['m']
        print(f"    m={m}: Revenue={df['revenue_ratio'].mean():.4f}, "
              f"Time={df['total_time'].mean():.3f}s, "
              f"LP调用={df['lp_solver_calls'].mean():.1f}, "
              f"迭代={df['iterations'].mean():.1f}")

print("\n" + "=" * 80)

