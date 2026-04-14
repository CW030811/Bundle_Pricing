"""
分析原始策略和全局 Top-K 策略的对比结果
"""
import pandas as pd
import numpy as np
import os

# 读取结果文件
df_original = pd.read_csv('test_result_local_search_mix_m10_n10_sample_100.csv')
df_topk = pd.read_csv('test_result_global_topk_m10_n10_sample_100.csv')

print("=" * 80)
print("Local Search 路径策略对比分析")
print("=" * 80)

print("\n=== 原始策略 (Segment-based, 2*m 邻域) ===")
print(f"平均 Revenue Ratio: {df_original['revenue_ratio'].mean():.4f} ± {df_original['revenue_ratio'].std():.4f}")
print(f"平均 Time Ratio: {df_original['runtime_ratio'].mean():.4f} ± {df_original['runtime_ratio'].std():.4f}")
print(f"平均总时间: {df_original['total_time'].mean():.4f}s ± {df_original['total_time'].std():.4f}s")
print(f"平均 Local Search 时间: {df_original['local_search_time'].mean():.4f}s")
print(f"平均 LP 调用次数: {df_original['lp_solver_calls'].mean():.2f} ± {df_original['lp_solver_calls'].std():.2f}")
print(f"平均迭代次数: {df_original['iterations'].mean():.2f} ± {df_original['iterations'].std():.2f}")
avg_neighbors_per_iter_original = df_original['lp_solver_calls'].sum() / df_original['iterations'].sum()
print(f"平均每轮邻域数: {avg_neighbors_per_iter_original:.2f}")
print(f"平均改进次数: {df_original['improvements'].mean():.2f}")
print(f"改进率: {(df_original['improvements'] > 0).sum() / len(df_original) * 100:.1f}%")

print("\n=== 新策略 (Global Top-K, K=ceil(2*sqrt(m))) ===")
print(f"平均 Revenue Ratio: {df_topk['revenue_ratio'].mean():.4f} ± {df_topk['revenue_ratio'].std():.4f}")
print(f"平均 Time Ratio: {df_topk['runtime_ratio'].mean():.4f} ± {df_topk['runtime_ratio'].std():.4f}")
print(f"平均总时间: {df_topk['total_time'].mean():.4f}s ± {df_topk['total_time'].std():.4f}s")
print(f"平均 Local Search 时间: {df_topk['local_search_time'].mean():.4f}s")
print(f"平均 LP 调用次数: {df_topk['lp_solver_calls'].mean():.2f} ± {df_topk['lp_solver_calls'].std():.2f}")
print(f"平均迭代次数: {df_topk['iterations'].mean():.2f} ± {df_topk['iterations'].std():.2f}")
avg_neighbors_per_iter_topk = df_topk['lp_solver_calls'].sum() / df_topk['iterations'].sum()
print(f"平均每轮邻域数: {avg_neighbors_per_iter_topk:.2f}")
print(f"平均 K 值: {df_topk['K'].mean():.2f}")
print(f"平均最大邻域数/轮: {df_topk['max_neighbors_per_iter'].mean():.2f}")
print(f"平均改进次数: {df_topk['improvements'].mean():.2f}")
print(f"改进率: {(df_topk['improvements'] > 0).sum() / len(df_topk) * 100:.1f}%")

print("\n=== 对比分析 ===")
rev_diff = df_topk['revenue_ratio'].mean() - df_original['revenue_ratio'].mean()
rev_pct = (df_topk['revenue_ratio'].mean() / df_original['revenue_ratio'].mean() - 1) * 100
print(f"Revenue Ratio 变化: {rev_diff:+.4f} ({rev_pct:+.2f}%)")

time_ratio_diff = df_topk['runtime_ratio'].mean() - df_original['runtime_ratio'].mean()
time_ratio_pct = (df_topk['runtime_ratio'].mean() / df_original['runtime_ratio'].mean() - 1) * 100
print(f"Time Ratio 变化: {time_ratio_diff:+.4f} ({time_ratio_pct:+.2f}%)")

total_time_diff = df_topk['total_time'].mean() - df_original['total_time'].mean()
total_time_pct = (df_topk['total_time'].mean() / df_original['total_time'].mean() - 1) * 100
print(f"总时间变化: {total_time_diff:+.4f}s ({total_time_pct:+.2f}%)")

ls_time_diff = df_topk['local_search_time'].mean() - df_original['local_search_time'].mean()
ls_time_pct = (df_topk['local_search_time'].mean() / df_original['local_search_time'].mean() - 1) * 100
print(f"Local Search 时间变化: {ls_time_diff:+.4f}s ({ls_time_pct:+.2f}%)")

lp_calls_diff = df_topk['lp_solver_calls'].mean() - df_original['lp_solver_calls'].mean()
lp_calls_pct = (df_topk['lp_solver_calls'].mean() / df_original['lp_solver_calls'].mean() - 1) * 100
print(f"LP 调用次数变化: {lp_calls_diff:+.2f} ({lp_calls_pct:+.2f}%)")

neighbors_diff = avg_neighbors_per_iter_topk - avg_neighbors_per_iter_original
neighbors_pct = (avg_neighbors_per_iter_topk / avg_neighbors_per_iter_original - 1) * 100
print(f"每轮邻域数变化: {neighbors_diff:+.2f} ({neighbors_pct:+.2f}%)")

iter_diff = df_topk['iterations'].mean() - df_original['iterations'].mean()
iter_pct = (df_topk['iterations'].mean() / df_original['iterations'].mean() - 1) * 100
print(f"迭代次数变化: {iter_diff:+.2f} ({iter_pct:+.2f}%)")

print("\n=== 效率分析 ===")
# 计算每单位时间的改进
original_efficiency = df_original['improvement'].mean() / df_original['local_search_time'].mean()
topk_efficiency = df_topk['improvement'].mean() / df_topk['local_search_time'].mean()
print(f"原始策略效率 (改进/秒): {original_efficiency:.6f}")
print(f"Top-K 策略效率 (改进/秒): {topk_efficiency:.6f}")
print(f"效率提升: {(topk_efficiency / original_efficiency - 1) * 100:+.2f}%")

# 计算每 LP 调用的改进
original_lp_efficiency = df_original['improvement'].mean() / df_original['lp_solver_calls'].mean()
topk_lp_efficiency = df_topk['improvement'].mean() / df_topk['lp_solver_calls'].mean()
print(f"\n原始策略 LP 效率 (改进/LP调用): {original_lp_efficiency:.6f}")
print(f"Top-K 策略 LP 效率 (改进/LP调用): {topk_lp_efficiency:.6f}")
print(f"LP 效率提升: {(topk_lp_efficiency / original_lp_efficiency - 1) * 100:+.2f}%")

print("\n" + "=" * 80)

