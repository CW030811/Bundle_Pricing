"""
检查时间分解的准确性
"""
import pandas as pd
import os

script_dir = os.path.dirname(os.path.abspath(__file__))
csv_path = os.path.join(script_dir, "test_result_global_topk_sqrtm_m10_n10_sample_100.csv")

df = pd.read_csv(csv_path)

print("=" * 80)
print("时间统计检查")
print("=" * 80)

print(f"\nLocal Search Time统计:")
print(f"  平均: {df['local_search_time'].mean():.4f}s")
print(f"  最小: {df['local_search_time'].min():.4f}s")
print(f"  最大: {df['local_search_time'].max():.4f}s")
print(f"  标准差: {df['local_search_time'].std():.4f}s")

print(f"\n初始MILP Time统计:")
print(f"  平均: {df['initial_milp_time'].mean():.4f}s")

print(f"\n注意:")
print("  - local_search_time 是函数 local_search_with_lp_global_topk 的整个执行时间")
print("  - 包括：初始MILP + 初始LP + 迭代循环 + 最终MILP + 其他开销")
print("  - 详细时间分解（0.1223s）只包括迭代循环的时间（total_iteration_time）")
print("  - 所以 0.1223s < 0.2195s 是正常的")

# 计算差值
avg_ls_time = df['local_search_time'].mean()
avg_initial_milp = df['initial_milp_time'].mean()
avg_iteration_time = 0.1223  # 从输出中获取

print(f"\n时间分解:")
print(f"  Local Search总时间: {avg_ls_time:.4f}s")
print(f"  - 初始MILP时间: {avg_initial_milp:.4f}s")
print(f"  - 迭代循环时间: {avg_iteration_time:.4f}s")
print(f"  - 其他时间（初始LP + 最终MILP + 开销）: {avg_ls_time - avg_initial_milp - avg_iteration_time:.4f}s")




