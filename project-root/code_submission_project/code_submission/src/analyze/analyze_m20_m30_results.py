"""
分析 m20 和 m30 数据集的实验结果
"""
import pandas as pd
import numpy as np

# 读取结果文件
df_m20 = pd.read_csv('test_result_global_topk_m20_n10_sample_100.csv')
df_m30 = pd.read_csv('test_result_global_topk_m30_n10_sample_100.csv')

print("=" * 80)
print("m20 和 m30 数据集实验结果分析")
print("=" * 80)

print("\n=== m20_n10_sample_100 (Global Top-K) ===")
print(f"平均 Revenue Ratio: {df_m20['revenue_ratio'].mean():.4f} ± {df_m20['revenue_ratio'].std():.4f}")
print(f"平均 Time Ratio: {df_m20['runtime_ratio'].mean():.4f} ± {df_m20['runtime_ratio'].std():.4f}")
print(f"平均总时间: {df_m20['total_time'].mean():.4f}s ± {df_m20['total_time'].std():.4f}s")
print(f"平均 Local Search 时间: {df_m20['local_search_time'].mean():.4f}s")
print(f"平均 LP 调用次数: {df_m20['lp_solver_calls'].mean():.2f} ± {df_m20['lp_solver_calls'].std():.2f}")
print(f"平均迭代次数: {df_m20['iterations'].mean():.2f} ± {df_m20['iterations'].std():.2f}")
print(f"平均 K: {df_m20['K'].mean():.2f}")
print(f"平均最大邻域数/轮: {df_m20['max_neighbors_per_iter'].mean():.2f}")
avg_neighbors_per_iter_m20 = df_m20['lp_solver_calls'].sum() / df_m20['iterations'].sum()
print(f"平均每轮邻域数: {avg_neighbors_per_iter_m20:.2f}")
print(f"平均改进次数: {df_m20['improvements'].mean():.2f}")
print(f"改进率: {(df_m20['improvements'] > 0).sum() / len(df_m20) * 100:.1f}%")
print(f"平均改进: {df_m20['improvement'].mean():.4f}")

print("\n=== m30_n10_sample_100 (Global Top-K) ===")
print(f"平均 Revenue Ratio: {df_m30['revenue_ratio'].mean():.4f} ± {df_m30['revenue_ratio'].std():.4f}")
print(f"平均 Time Ratio: {df_m30['runtime_ratio'].mean():.4f} ± {df_m30['runtime_ratio'].std():.4f}")
print(f"平均总时间: {df_m30['total_time'].mean():.4f}s ± {df_m30['total_time'].std():.4f}s")
print(f"平均 Local Search 时间: {df_m30['local_search_time'].mean():.4f}s")
print(f"平均 LP 调用次数: {df_m30['lp_solver_calls'].mean():.2f} ± {df_m30['lp_solver_calls'].std():.2f}")
print(f"平均迭代次数: {df_m30['iterations'].mean():.2f} ± {df_m30['iterations'].std():.2f}")
print(f"平均 K: {df_m30['K'].mean():.2f}")
print(f"平均最大邻域数/轮: {df_m30['max_neighbors_per_iter'].mean():.2f}")
avg_neighbors_per_iter_m30 = df_m30['lp_solver_calls'].sum() / df_m30['iterations'].sum()
print(f"平均每轮邻域数: {avg_neighbors_per_iter_m30:.2f}")
print(f"平均改进次数: {df_m30['improvements'].mean():.2f}")
print(f"改进率: {(df_m30['improvements'] > 0).sum() / len(df_m30) * 100:.1f}%")
print(f"平均改进: {df_m30['improvement'].mean():.4f}")

print("\n=== 可扩展性分析 ===")
print(f"m=10: K=7, 最大邻域数/轮=14")
print(f"m=20: K=9, 最大邻域数/轮=18")
print(f"m=30: K=11, 最大邻域数/轮=22")
print(f"\nK值增长: sqrt(20)/sqrt(10) = {np.sqrt(20)/np.sqrt(10):.2f}, 实际: 9/7 = {9/7:.2f}")
print(f"K值增长: sqrt(30)/sqrt(10) = {np.sqrt(30)/np.sqrt(10):.2f}, 实际: 11/7 = {11/7:.2f}")

print("\n=== 时间效率对比 ===")
print(f"m=10: 平均总时间 0.396s, Local Search 时间 0.239s")
print(f"m=20: 平均总时间 {df_m20['total_time'].mean():.4f}s, Local Search 时间 {df_m20['local_search_time'].mean():.4f}s")
print(f"m=30: 平均总时间 {df_m30['total_time'].mean():.4f}s, Local Search 时间 {df_m30['local_search_time'].mean():.4f}s")
print(f"\nm=20 相对 m=10 时间增长: {df_m20['total_time'].mean() / 0.396:.2f}x")
print(f"m=30 相对 m=10 时间增长: {df_m30['total_time'].mean() / 0.396:.2f}x")

print("\n" + "=" * 80)

