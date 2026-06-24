"""
分析两个实验结果的对比
"""
import numpy as np
import pandas as pd
import os

# 读取两个CSV文件
script_dir = os.path.dirname(os.path.abspath(__file__))
topk_path = os.path.join(script_dir, 'test_result_global_topk_sqrtm_m10_n10_sample_100.csv')
mix_path = os.path.join(script_dir, 'test_result_local_search_mix_m10_n10_sample_100.csv')

topk = pd.read_csv(topk_path)
mix = pd.read_csv(mix_path)

print("=" * 80)
print("实验对比分析：Global Top-K Strategy vs Original Strategy (Segment-based)")
print("数据集: m10_n10_sample_100")
print("=" * 80)

print("\n【1. 基本统计信息】")
print(f"\n样本数量:")
print(f"  Global Top-K: {len(topk)} 个样本")
print(f"  Original:     {len(mix)} 个样本")

print(f"\n【2. 收益表现】")
print(f"\n平均收益比率 (revenue_ratio):")
print(f"  Global Top-K: {topk['revenue_ratio'].mean():.6f} (std: {topk['revenue_ratio'].std():.6f})")
print(f"  Original:     {mix['revenue_ratio'].mean():.6f} (std: {mix['revenue_ratio'].std():.6f})")
print(f"  差异:         {topk['revenue_ratio'].mean() - mix['revenue_ratio'].mean():.6f}")

print(f"\n收益比率范围:")
print(f"  Global Top-K: [{topk['revenue_ratio'].min():.6f}, {topk['revenue_ratio'].max():.6f}]")
print(f"  Original:     [{mix['revenue_ratio'].min():.6f}, {mix['revenue_ratio'].max():.6f}]")

print(f"\n【3. 时间性能】")
print(f"\n平均总时间 (total_time):")
print(f"  Global Top-K: {topk['total_time'].mean():.4f}s (std: {topk['total_time'].std():.4f}s)")
print(f"  Original:     {mix['total_time'].mean():.4f}s (std: {mix['total_time'].std():.4f}s)")
speedup_total = mix['total_time'].mean() / topk['total_time'].mean()
print(f"  加速比:       {speedup_total:.2f}x")

print(f"\n平均Local Search时间 (local_search_time):")
print(f"  Global Top-K: {topk['local_search_time'].mean():.4f}s (std: {topk['local_search_time'].std():.4f}s)")
print(f"  Original:     {mix['local_search_time'].mean():.4f}s (std: {mix['local_search_time'].std():.4f}s)")
speedup_ls = mix['local_search_time'].mean() / topk['local_search_time'].mean()
print(f"  加速比:       {speedup_ls:.2f}x")

print(f"\n平均迭代时间 (total_iteration_time):")
print(f"  Global Top-K: {topk['total_iteration_time'].mean():.4f}s (std: {topk['total_iteration_time'].std():.4f}s)")
print(f"  Original:     {mix['total_iteration_time'].mean():.4f}s (std: {mix['total_iteration_time'].std():.4f}s)")
speedup_iter = mix['total_iteration_time'].mean() / topk['total_iteration_time'].mean()
print(f"  加速比:       {speedup_iter:.2f}x")

print(f"\n【4. 迭代与LP调用】")
print(f"\n平均迭代次数 (iterations):")
print(f"  Global Top-K: {topk['iterations'].mean():.2f} (std: {topk['iterations'].std():.2f})")
print(f"  Original:     {mix['iterations'].mean():.2f} (std: {mix['iterations'].std():.2f})")

print(f"\n平均LP调用次数 (lp_solver_calls):")
print(f"  Global Top-K: {topk['lp_solver_calls'].mean():.2f} (std: {topk['lp_solver_calls'].std():.2f})")
print(f"  Original:     {mix['lp_solver_calls'].mean():.2f} (std: {mix['lp_solver_calls'].std():.2f})")
lp_reduction = (1 - topk['lp_solver_calls'].mean() / mix['lp_solver_calls'].mean()) * 100
print(f"  LP调用减少:   {lp_reduction:.1f}%")

print(f"\n平均每次LP调用时间:")
avg_lp_time_topk = topk['lp_solve_time'].mean() / topk['lp_solver_calls'].mean()
avg_lp_time_mix = mix['lp_solve_time'].mean() / mix['lp_solver_calls'].mean()
print(f"  Global Top-K: {avg_lp_time_topk*1000:.2f}ms")
print(f"  Original:     {avg_lp_time_mix*1000:.2f}ms")

print(f"\n【5. 改进效果】")
print(f"\n平均改进量 (improvement):")
print(f"  Global Top-K: {topk['improvement'].mean():.6f} (std: {topk['improvement'].std():.6f})")
print(f"  Original:     {mix['improvement'].mean():.6f} (std: {mix['improvement'].std():.6f})")

print(f"\n有改进的样本数:")
topk_improved = (topk['improvement'] > 0).sum()
mix_improved = (mix['improvement'] > 0).sum()
print(f"  Global Top-K: {topk_improved}/{len(topk)} ({100*topk_improved/len(topk):.1f}%)")
print(f"  Original:     {mix_improved}/{len(mix)} ({100*mix_improved/len(mix):.1f}%)")

print(f"\n【6. 详细时间分解 (Global Top-K)】")
avg_iter_time_topk = topk['total_iteration_time'].mean()
if avg_iter_time_topk > 0:
    print(f"\n平均迭代时间: {avg_iter_time_topk:.6f}s")
    print(f"  Add Candidate构建:     {topk['add_candidate_time'].mean():.6f}s ({topk['add_candidate_time'].mean()/avg_iter_time_topk*100:.2f}%)")
    print(f"  Drop Candidate构建:    {topk['drop_candidate_time'].mean():.6f}s ({topk['drop_candidate_time'].mean()/avg_iter_time_topk*100:.2f}%)")
    print(f"  Neighbor生成:          {topk['neighbor_generation_time'].mean():.6f}s ({topk['neighbor_generation_time'].mean()/avg_iter_time_topk*100:.2f}%)")
    print(f"  LP求解总时间:          {topk['lp_solve_time'].mean():.6f}s ({topk['lp_solve_time'].mean()/avg_iter_time_topk*100:.2f}%)")
    print(f"  Neighbor遍历(不含LP):  {topk['neighbor_iteration_time'].mean():.6f}s ({topk['neighbor_iteration_time'].mean()/avg_iter_time_topk*100:.2f}%)")

print(f"\n【7. 详细时间分解 (Original Strategy)】")
avg_iter_time_mix = mix['total_iteration_time'].mean()
if avg_iter_time_mix > 0:
    print(f"\n平均迭代时间: {avg_iter_time_mix:.6f}s")
    print(f"  Add Candidate构建:     {mix['add_candidate_time'].mean():.6f}s ({mix['add_candidate_time'].mean()/avg_iter_time_mix*100:.2f}%)")
    print(f"  Drop Candidate构建:    {mix['drop_candidate_time'].mean():.6f}s ({mix['drop_candidate_time'].mean()/avg_iter_time_mix*100:.2f}%)")
    print(f"  Neighbor生成:          {mix['neighbor_generation_time'].mean():.6f}s ({mix['neighbor_generation_time'].mean()/avg_iter_time_mix*100:.2f}%)")
    print(f"  LP求解总时间:          {mix['lp_solve_time'].mean():.6f}s ({mix['lp_solve_time'].mean()/avg_iter_time_mix*100:.2f}%)")
    print(f"  Neighbor遍历(不含LP):  {mix['neighbor_iteration_time'].mean():.6f}s ({mix['neighbor_iteration_time'].mean()/avg_iter_time_mix*100:.2f}%)")

print(f"\n【8. Global Top-K策略参数】")
print(f"  平均K值:                  {topk['K'].mean():.2f}")
print(f"  平均每次迭代最大邻域数:   {topk['max_neighbors_per_iter'].mean():.2f}")

print(f"\n【9. 总结】")
print(f"\n✓ Global Top-K策略相比Original策略:")
print(f"  - 总时间加速:     {speedup_total:.2f}x")
print(f"  - Local Search加速: {speedup_ls:.2f}x")
print(f"  - 迭代时间加速:   {speedup_iter:.2f}x")
print(f"  - LP调用减少:     {lp_reduction:.1f}%")
print(f"  - 收益表现:       {'更好' if topk['revenue_ratio'].mean() > mix['revenue_ratio'].mean() else '相当' if abs(topk['revenue_ratio'].mean() - mix['revenue_ratio'].mean()) < 0.0001 else '略差'}")

print("\n" + "=" * 80)


