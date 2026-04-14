"""
对比分析: Global Top-K 策略 vs 矩阵优化策略
- Global Top-K (Loop): K = ceil(sqrt(m*n)), 使用双层循环生成候选
- Matrix Optimized: K = ceil(sqrt(m)), 使用向量化矩阵操作生成候选
"""
import pandas as pd
import numpy as np
import os

# 定义文件
files = {
    # Global Top-K (Loop版本, K=sqrt(m*n))
    'loop_m10_n10': 'test_result_global_topk_sqrtm_m10_n10_sample_100.csv',
    'loop_m20_n10': 'test_result_global_topk_sqrtm_m20_n10_sample_100.csv',
    'loop_m30_n10': 'test_result_global_topk_sqrtm_m30_n10_sample_100.csv',

    # Matrix Optimized (K=sqrt(m))
    'matrix_m10_n10': 'test_result_global_topk_sqrtm_matrix_m10_n10_sample_100.csv',
    'matrix_m20_n10': 'test_result_global_topk_sqrtm_matrix_m20_n10_sample_100.csv',
}

# 读取数据
data = {}
for name, file in files.items():
    if os.path.exists(file):
        data[name] = pd.read_csv(file)
        print(f"Loaded {name}: {len(data[name])} samples, K={data[name]['K'].mean():.0f}")

print()
print("=" * 120)
print("Global Top-K (Loop) vs 矩阵优化版本 详细对比分析")
print("=" * 120)

# 对比数据集
datasets = ['m10_n10', 'm20_n10']

print("\n" + "=" * 120)
print("一、策略参数对比")
print("=" * 120)
print()
print(f"{'数据集':<15} {'Loop版本 K':<15} {'Matrix版本 K':<15} {'K差异':<15} {'最大邻域数(Loop)':<20} {'最大邻域数(Matrix)':<20}")
print("-" * 120)

for ds in datasets:
    loop_key = f'loop_{ds}'
    matrix_key = f'matrix_{ds}'

    if loop_key in data and matrix_key in data:
        loop_k = data[loop_key]['K'].mean()
        matrix_k = data[matrix_key]['K'].mean()
        loop_max = data[loop_key]['max_neighbors_per_iter'].mean()
        matrix_max = data[matrix_key]['max_neighbors_per_iter'].mean()

        print(f"{ds:<15} {loop_k:<15.0f} {matrix_k:<15.0f} {loop_k - matrix_k:<15.0f} {loop_max:<20.0f} {matrix_max:<20.0f}")

# 详细对比
print("\n" + "=" * 120)
print("二、性能指标对比")
print("=" * 120)

results = []
for ds in datasets:
    loop_key = f'loop_{ds}'
    matrix_key = f'matrix_{ds}'

    if loop_key in data and matrix_key in data:
        loop_df = data[loop_key]
        matrix_df = data[matrix_key]

        result = {
            'dataset': ds,
            # Loop版本
            'loop_K': loop_df['K'].mean(),
            'loop_revenue': loop_df['revenue_ratio'].mean(),
            'loop_revenue_std': loop_df['revenue_ratio'].std(),
            'loop_total_time': loop_df['total_time'].mean(),
            'loop_ls_time': loop_df['local_search_time'].mean(),
            'loop_iter_time': loop_df['total_iteration_time'].mean(),
            'loop_lp_time': loop_df['lp_solve_time'].mean(),
            'loop_lp_calls': loop_df['lp_solver_calls'].mean(),
            'loop_iterations': loop_df['iterations'].mean(),
            'loop_add_time': loop_df['add_candidate_time'].mean(),
            'loop_drop_time': loop_df['drop_candidate_time'].mean(),
            'loop_neighbor_gen': loop_df['neighbor_generation_time'].mean(),

            # Matrix版本
            'matrix_K': matrix_df['K'].mean(),
            'matrix_revenue': matrix_df['revenue_ratio'].mean(),
            'matrix_revenue_std': matrix_df['revenue_ratio'].std(),
            'matrix_total_time': matrix_df['total_time'].mean(),
            'matrix_ls_time': matrix_df['local_search_time'].mean(),
            'matrix_iter_time': matrix_df['total_iteration_time'].mean(),
            'matrix_lp_time': matrix_df['lp_solve_time'].mean(),
            'matrix_lp_calls': matrix_df['lp_solver_calls'].mean(),
            'matrix_iterations': matrix_df['iterations'].mean(),
            'matrix_add_time': matrix_df['add_candidate_time'].mean(),
            'matrix_drop_time': matrix_df['drop_candidate_time'].mean(),
            'matrix_neighbor_gen': matrix_df['neighbor_generation_time'].mean(),
        }
        results.append(result)

# 打印Revenue对比
print("\n### 2.1 Revenue Ratio 对比")
print("-" * 120)
print(f"{'数据集':<12} {'Loop K':<10} {'Loop Revenue':<18} {'Matrix K':<10} {'Matrix Revenue':<18} {'差异':<15}")
print("-" * 120)
for r in results:
    diff = r['matrix_revenue'] - r['loop_revenue']
    diff_pct = diff / r['loop_revenue'] * 100
    print(f"{r['dataset']:<12} {r['loop_K']:<10.0f} {r['loop_revenue']:.4f} (±{r['loop_revenue_std']:.4f})  {r['matrix_K']:<10.0f} {r['matrix_revenue']:.4f} (±{r['matrix_revenue_std']:.4f})  {diff:+.4f} ({diff_pct:+.2f}%)")

# 打印时间对比
print("\n### 2.2 总时间对比 (ms)")
print("-" * 120)
print(f"{'数据集':<12} {'Loop Total':<15} {'Matrix Total':<15} {'加速比':<15} {'时间减少':<15}")
print("-" * 120)
for r in results:
    speedup = r['loop_total_time'] / r['matrix_total_time']
    reduction = (1 - r['matrix_total_time'] / r['loop_total_time']) * 100
    print(f"{r['dataset']:<12} {r['loop_total_time']*1000:<15.2f} {r['matrix_total_time']*1000:<15.2f} {speedup:<15.2f}x -{reduction:<14.1f}%")

# 打印Local Search时间对比
print("\n### 2.3 Local Search 时间对比 (ms)")
print("-" * 120)
print(f"{'数据集':<12} {'Loop LS':<15} {'Matrix LS':<15} {'加速比':<15} {'时间减少':<15}")
print("-" * 120)
for r in results:
    speedup = r['loop_ls_time'] / r['matrix_ls_time']
    reduction = (1 - r['matrix_ls_time'] / r['loop_ls_time']) * 100
    print(f"{r['dataset']:<12} {r['loop_ls_time']*1000:<15.2f} {r['matrix_ls_time']*1000:<15.2f} {speedup:<15.2f}x -{reduction:<14.1f}%")

# 打印LP调用次数对比
print("\n### 2.4 LP 调用次数对比")
print("-" * 120)
print(f"{'数据集':<12} {'Loop LP次数':<15} {'Matrix LP次数':<15} {'减少':<15} {'减少率':<15}")
print("-" * 120)
for r in results:
    diff = r['loop_lp_calls'] - r['matrix_lp_calls']
    reduction = diff / r['loop_lp_calls'] * 100
    print(f"{r['dataset']:<12} {r['loop_lp_calls']:<15.1f} {r['matrix_lp_calls']:<15.1f} {diff:<15.1f} -{reduction:<14.1f}%")

# 打印候选构建时间对比
print("\n### 2.5 候选构建时间对比 (ms) - 矩阵优化核心")
print("-" * 120)
print(f"{'数据集':<12} {'Loop Add':<12} {'Matrix Add':<12} {'Loop Drop':<12} {'Matrix Drop':<12} {'Loop NeighGen':<15} {'Matrix NeighGen':<15}")
print("-" * 120)
for r in results:
    print(f"{r['dataset']:<12} {r['loop_add_time']*1000:<12.4f} {r['matrix_add_time']*1000:<12.4f} {r['loop_drop_time']*1000:<12.4f} {r['matrix_drop_time']*1000:<12.4f} {r['loop_neighbor_gen']*1000:<15.4f} {r['matrix_neighbor_gen']*1000:<15.4f}")

# 计算候选构建总时间
print("\n### 2.6 候选构建总时间对比 (ms)")
print("-" * 120)
print(f"{'数据集':<12} {'Loop候选总时间':<18} {'Matrix候选总时间':<18} {'加速比':<15} {'占Iter比(Loop)':<18} {'占Iter比(Matrix)':<18}")
print("-" * 120)
for r in results:
    loop_cand = r['loop_add_time'] + r['loop_drop_time'] + r['loop_neighbor_gen']
    matrix_cand = r['matrix_add_time'] + r['matrix_drop_time'] + r['matrix_neighbor_gen']
    speedup = loop_cand / matrix_cand if matrix_cand > 0 else 0
    loop_pct = loop_cand / r['loop_iter_time'] * 100 if r['loop_iter_time'] > 0 else 0
    matrix_pct = matrix_cand / r['matrix_iter_time'] * 100 if r['matrix_iter_time'] > 0 else 0
    print(f"{r['dataset']:<12} {loop_cand*1000:<18.4f} {matrix_cand*1000:<18.4f} {speedup:<15.2f}x {loop_pct:<18.2f}% {matrix_pct:<18.2f}%")

# 迭代次数对比
print("\n### 2.7 迭代次数对比")
print("-" * 120)
print(f"{'数据集':<12} {'Loop迭代次数':<15} {'Matrix迭代次数':<15} {'差异':<15}")
print("-" * 120)
for r in results:
    diff = r['matrix_iterations'] - r['loop_iterations']
    print(f"{r['dataset']:<12} {r['loop_iterations']:<15.1f} {r['matrix_iterations']:<15.1f} {diff:<+15.1f}")

# LP求解时间对比
print("\n### 2.8 LP求解时间对比 (ms)")
print("-" * 120)
print(f"{'数据集':<12} {'Loop LP总时间':<18} {'Matrix LP总时间':<18} {'单次LP(Loop)':<18} {'单次LP(Matrix)':<18}")
print("-" * 120)
for r in results:
    loop_per_lp = r['loop_lp_time'] / r['loop_lp_calls'] * 1000 if r['loop_lp_calls'] > 0 else 0
    matrix_per_lp = r['matrix_lp_time'] / r['matrix_lp_calls'] * 1000 if r['matrix_lp_calls'] > 0 else 0
    print(f"{r['dataset']:<12} {r['loop_lp_time']*1000:<18.2f} {r['matrix_lp_time']*1000:<18.2f} {loop_per_lp:<18.2f} {matrix_per_lp:<18.2f}")

# 总结
print("\n" + "=" * 120)
print("三、核心发现总结")
print("=" * 120)

print("""
1. K值差异:
   - Loop版本: K = ceil(sqrt(m*n)) = 10 (m10) / 15 (m20)
   - Matrix版本: K = ceil(sqrt(m)) = 4 (m10) / 5 (m20)
   - Matrix版本K值更小，每轮邻域数更少

2. 性能差异来源:
   - 主要来自K值减小导致的LP调用次数减少
   - 矩阵操作本身的加速效果有限（候选构建时间本身很小）

3. Revenue影响:
   - Matrix版本Revenue略低（因为K值更小，搜索空间受限）
   - 差异通常在1-2%以内

4. 结论:
   - "矩阵优化"的加速效果主要来自于更小的K值，而非矩阵操作本身
   - 若要公平对比矩阵操作的效果，需要使用相同的K值
""")
