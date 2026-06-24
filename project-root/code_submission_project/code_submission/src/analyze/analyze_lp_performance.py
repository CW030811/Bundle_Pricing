"""
分析 Local Search 中 LP 求解器的性能
重点分析：
1. 平均每次 LP 调用的时间
2. LP 调用次数分布
3. 时间瓶颈分析（LP 求解速度 vs LP 调用次数）
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# 读取结果文件
result_file = 'test_result_local_search_mix_m10_n10_sample_100.csv'
data = np.loadtxt(result_file, delimiter=',', skiprows=1)

# 提取关键指标
n_products = data[:, 0]
revenue_ratio = data[:, 1]
runtime_ratio = data[:, 2]
total_time = data[:, 3]
base_running_time = data[:, 4]
threshold_time = data[:, 5]  # GCN 推理时间
initial_milp_time = data[:, 6]
local_search_time = data[:, 7]
initial_revenue = data[:, 8]
improvement = data[:, 9]
iterations = data[:, 10]
improvements = data[:, 11]
lp_solver_calls = data[:, 12]
milp_solver_calls = data[:, 13]

# 计算每次 LP 调用的平均时间
lp_time_per_call = local_search_time / lp_solver_calls

# 过滤掉异常值（LP 调用次数为 0 的情况）
valid_mask = lp_solver_calls > 0
lp_time_per_call_valid = lp_time_per_call[valid_mask]
lp_calls_valid = lp_solver_calls[valid_mask]
local_search_time_valid = local_search_time[valid_mask]

print("=" * 80)
print("Local Search LP 求解器性能分析 (m10_n10_sample_100)")
print("=" * 80)

print(f"\n【总体统计】")
print(f"有效样本数: {np.sum(valid_mask)} / {len(data)}")
print(f"平均总时间: {np.mean(total_time):.4f} 秒")
print(f"平均 Local Search 时间: {np.mean(local_search_time_valid):.4f} 秒")
print(f"Local Search 时间占比: {np.mean(local_search_time_valid / total_time[valid_mask]) * 100:.2f}%")

print(f"\n【LP 调用次数分析】")
print(f"平均 LP 调用次数: {np.mean(lp_calls_valid):.2f}")
print(f"中位数 LP 调用次数: {np.median(lp_calls_valid):.2f}")
print(f"最小 LP 调用次数: {np.min(lp_calls_valid):.0f}")
print(f"最大 LP 调用次数: {np.max(lp_calls_valid):.0f}")
print(f"标准差: {np.std(lp_calls_valid):.2f}")
print(f"25% 分位数: {np.percentile(lp_calls_valid, 25):.2f}")
print(f"75% 分位数: {np.percentile(lp_calls_valid, 75):.2f}")

print(f"\n【每次 LP 调用时间分析】")
print(f"平均每次 LP 调用时间: {np.mean(lp_time_per_call_valid):.6f} 秒 ({np.mean(lp_time_per_call_valid) * 1000:.3f} 毫秒)")
print(f"中位数每次 LP 调用时间: {np.median(lp_time_per_call_valid):.6f} 秒 ({np.median(lp_time_per_call_valid) * 1000:.3f} 毫秒)")
print(f"最小每次 LP 调用时间: {np.min(lp_time_per_call_valid):.6f} 秒 ({np.min(lp_time_per_call_valid) * 1000:.3f} 毫秒)")
print(f"最大每次 LP 调用时间: {np.max(lp_time_per_call_valid):.6f} 秒 ({np.max(lp_time_per_call_valid) * 1000:.3f} 毫秒)")
print(f"标准差: {np.std(lp_time_per_call_valid):.6f} 秒 ({np.std(lp_time_per_call_valid) * 1000:.3f} 毫秒)")
print(f"25% 分位数: {np.percentile(lp_time_per_call_valid, 25):.6f} 秒 ({np.percentile(lp_time_per_call_valid, 25) * 1000:.3f} 毫秒)")
print(f"75% 分位数: {np.percentile(lp_time_per_call_valid, 75):.6f} 秒 ({np.percentile(lp_time_per_call_valid, 75) * 1000:.3f} 毫秒)")

print(f"\n【时间组成分析】")
print(f"GCN 推理时间: {np.mean(threshold_time):.4f} 秒 ({np.mean(threshold_time / total_time) * 100:.2f}%)")
print(f"初始 MILP 时间: {np.mean(initial_milp_time):.4f} 秒 ({np.mean(initial_milp_time / total_time) * 100:.2f}%)")
print(f"Local Search 时间: {np.mean(local_search_time_valid):.4f} 秒 ({np.mean(local_search_time_valid / total_time[valid_mask]) * 100:.2f}%)")
print(f"  - 其中 LP 求解总时间: {np.mean(local_search_time_valid):.4f} 秒")
print(f"  - 平均每次 LP 调用: {np.mean(lp_time_per_call_valid):.6f} 秒")

print(f"\n【迭代次数分析】")
print(f"平均迭代次数: {np.mean(iterations[valid_mask]):.2f}")
print(f"平均改进次数: {np.mean(improvements[valid_mask]):.2f}")
print(f"平均每次迭代的 LP 调用次数: {np.mean(lp_calls_valid / iterations[valid_mask]):.2f}")

print(f"\n【时间瓶颈分析】")
# 计算 LP 调用次数对总时间的贡献
lp_calls_contribution = np.corrcoef(lp_calls_valid, local_search_time_valid)[0, 1]
lp_time_per_call_contribution = np.corrcoef(lp_time_per_call_valid, local_search_time_valid)[0, 1]

print(f"LP 调用次数与 Local Search 时间的相关系数: {lp_calls_contribution:.4f}")
print(f"每次 LP 调用时间与 Local Search 时间的相关系数: {lp_time_per_call_contribution:.4f}")

# 计算如果减少 LP 调用次数的潜在时间节省
print(f"\n【优化潜力分析】")
current_avg_lp_calls = np.mean(lp_calls_valid)
current_avg_lp_time = np.mean(lp_time_per_call_valid)
current_avg_ls_time = np.mean(local_search_time_valid)

print(f"当前平均 Local Search 时间: {current_avg_ls_time:.4f} 秒")
print(f"  - 由 LP 调用次数贡献: {current_avg_lp_calls * current_avg_lp_time:.4f} 秒")
print(f"  - 其他开销: {current_avg_ls_time - current_avg_lp_calls * current_avg_lp_time:.4f} 秒")

# 假设减少 20% LP 调用次数
reduced_calls = current_avg_lp_calls * 0.8
potential_time_saving = (current_avg_lp_calls - reduced_calls) * current_avg_lp_time
print(f"\n如果减少 20% LP 调用次数:")
print(f"  - 新平均 LP 调用次数: {reduced_calls:.2f}")
print(f"  - 潜在时间节省: {potential_time_saving:.4f} 秒 ({potential_time_saving / current_avg_ls_time * 100:.2f}%)")

# 假设每次 LP 调用时间减少 20%
reduced_lp_time = current_avg_lp_time * 0.8
potential_time_saving2 = current_avg_lp_calls * (current_avg_lp_time - reduced_lp_time)
print(f"\n如果每次 LP 调用时间减少 20%:")
print(f"  - 新平均每次 LP 调用时间: {reduced_lp_time:.6f} 秒 ({reduced_lp_time * 1000:.3f} 毫秒)")
print(f"  - 潜在时间节省: {potential_time_saving2:.4f} 秒 ({potential_time_saving2 / current_avg_ls_time * 100:.2f}%)")

print(f"\n【结论】")
if lp_calls_contribution > abs(lp_time_per_call_contribution):
    print("[结论] 时间瓶颈主要在 LP 调用次数上")
    print("  建议: 优化邻域生成策略，减少不必要的 LP 调用")
else:
    print("[结论] 时间瓶颈主要在每次 LP 调用时间上")
    print("  建议: 优化 LP 模型构建或求解器参数")

print("=" * 80)

# 保存详细分析结果
analysis_results = {
    'metric': [
        '平均 LP 调用次数',
        '平均每次 LP 调用时间 (秒)',
        '平均每次 LP 调用时间 (毫秒)',
        '平均 Local Search 时间 (秒)',
        'LP 调用次数贡献占比 (%)',
        '每次 LP 调用时间贡献占比 (%)',
        '减少 20% LP 调用次数的时间节省 (秒)',
        '减少 20% LP 调用次数的时间节省 (%)',
        '减少 20% 每次 LP 调用时间的时间节省 (秒)',
        '减少 20% 每次 LP 调用时间的时间节省 (%)',
    ],
    'value': [
        f"{np.mean(lp_calls_valid):.2f}",
        f"{np.mean(lp_time_per_call_valid):.6f}",
        f"{np.mean(lp_time_per_call_valid) * 1000:.3f}",
        f"{np.mean(local_search_time_valid):.4f}",
        f"{lp_calls_contribution * 100:.2f}",
        f"{lp_time_per_call_contribution * 100:.2f}",
        f"{potential_time_saving:.4f}",
        f"{potential_time_saving / current_avg_ls_time * 100:.2f}",
        f"{potential_time_saving2:.4f}",
        f"{potential_time_saving2 / current_avg_ls_time * 100:.2f}",
    ]
}

df = pd.DataFrame(analysis_results)
df.to_csv('lp_performance_analysis_m10_n10.csv', index=False, encoding='utf-8-sig')
print(f"\n详细分析结果已保存到: lp_performance_analysis_m10_n10.csv")

