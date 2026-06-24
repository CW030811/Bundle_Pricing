"""
Local Search 时间组成详细分析
分析 Global Top-K 策略下 m10n10, m20n10, m30n10 数据集的时间分解
"""
import pandas as pd
import numpy as np
import os

# 读取数据
datasets = {
    'm10_n10': 'test_result_global_topk_sqrtm_m10_n10_sample_100.csv',
    'm20_n10': 'test_result_global_topk_sqrtm_m20_n10_sample_100.csv',
    'm30_n10': 'test_result_global_topk_sqrtm_m30_n10_sample_100.csv',
}

data = {}
for name, file in datasets.items():
    if os.path.exists(file):
        data[name] = pd.read_csv(file)
        print(f"Loaded {name}: {len(data[name])} samples")

print()
print("=" * 100)
print("LOCAL SEARCH 时间组成详细分析 - Global Top-K (K=sqrt(m*n)) 策略")
print("=" * 100)

# 分析每个数据集
results = []

for ds_name, df in data.items():
    print(f"\n{'='*100}")
    print(f"数据集: {ds_name}")
    print(f"{'='*100}")

    # 提取m值
    if 'm10' in ds_name:
        m = 10
    elif 'm20' in ds_name:
        m = 20
    elif 'm30' in ds_name:
        m = 30
    else:
        m = 10

    n = 10  # 产品数量

    # 计算各时间组成的平均值
    result = {
        'dataset': ds_name,
        'm': m,
        'n': n,
        'K': df['K'].mean() if 'K' in df.columns else np.ceil(np.sqrt(m * n)),
        'samples': len(df),

        # 总时间
        'total_time': df['total_time'].mean(),
        'total_time_std': df['total_time'].std(),

        # GCN推理时间
        'threshold_time': df['threshold_time'].mean(),
        'threshold_time_std': df['threshold_time'].std(),

        # 初始MILP时间
        'initial_milp_time': df['initial_milp_time'].mean(),
        'initial_milp_time_std': df['initial_milp_time'].std(),

        # Local Search 时间
        'local_search_time': df['local_search_time'].mean(),
        'local_search_time_std': df['local_search_time'].std(),

        # 迭代总时间
        'total_iteration_time': df['total_iteration_time'].mean(),
        'total_iteration_time_std': df['total_iteration_time'].std(),

        # Add候选构建时间
        'add_candidate_time': df['add_candidate_time'].mean(),
        'add_candidate_time_std': df['add_candidate_time'].std(),

        # Drop候选构建时间
        'drop_candidate_time': df['drop_candidate_time'].mean(),
        'drop_candidate_time_std': df['drop_candidate_time'].std(),

        # 邻域生成时间
        'neighbor_generation_time': df['neighbor_generation_time'].mean(),
        'neighbor_generation_time_std': df['neighbor_generation_time'].std(),

        # LP求解总时间
        'lp_solve_time': df['lp_solve_time'].mean(),
        'lp_solve_time_std': df['lp_solve_time'].std(),

        # 邻域遍历时间（不含LP）
        'neighbor_iteration_time': df['neighbor_iteration_time'].mean(),
        'neighbor_iteration_time_std': df['neighbor_iteration_time'].std(),

        # 迭代次数
        'iterations': df['iterations'].mean(),

        # LP调用次数
        'lp_solver_calls': df['lp_solver_calls'].mean(),

        # MILP调用次数 (包含初始和最终)
        'milp_solver_calls': df['milp_solver_calls'].mean(),
    }

    results.append(result)

    # 打印详细信息
    print(f"\n参数信息:")
    print(f"  m (segments) = {m}")
    print(f"  n (products) = {n}")
    print(f"  K = {result['K']:.0f}")
    print(f"  平均迭代次数 = {result['iterations']:.1f}")
    print(f"  平均LP调用次数 = {result['lp_solver_calls']:.1f}")
    print(f"  平均MILP调用次数 = {result['milp_solver_calls']:.1f}")

    print(f"\n时间组成 (平均值 ± 标准差):")
    print(f"-" * 80)

    # 总时间分解
    print(f"\n[总时间分解]")
    print(f"  Total Time:           {result['total_time']*1000:8.2f} ms  (±{result['total_time_std']*1000:.2f} ms)")
    print(f"    ├─ GCN Inference:   {result['threshold_time']*1000:8.2f} ms  ({result['threshold_time']/result['total_time']*100:5.1f}%)")
    print(f"    ├─ Initial MILP:    {result['initial_milp_time']*1000:8.2f} ms  ({result['initial_milp_time']/result['total_time']*100:5.1f}%)")
    print(f"    └─ Local Search:    {result['local_search_time']*1000:8.2f} ms  ({result['local_search_time']/result['total_time']*100:5.1f}%)")

    # Local Search 内部分解
    ls_time = result['local_search_time']
    print(f"\n[Local Search 内部分解]")
    print(f"  Local Search Time:    {ls_time*1000:8.2f} ms")
    print(f"    ├─ Iteration Time:  {result['total_iteration_time']*1000:8.2f} ms  ({result['total_iteration_time']/ls_time*100:5.1f}%)")

    # 计算Final MILP时间（通过差值估算）
    # Final MILP时间 ≈ Local Search时间 - Iteration时间 - 初始LP时间
    # 但这里需要更精确的计算
    other_time = ls_time - result['total_iteration_time']
    print(f"    └─ Other (初始LP+Final MILP等): {other_time*1000:8.2f} ms  ({other_time/ls_time*100:5.1f}%)")

    # Iteration内部分解
    iter_time = result['total_iteration_time']
    print(f"\n[Iteration Time 内部分解]")
    print(f"  Total Iteration Time: {iter_time*1000:8.2f} ms")

    # Add + Drop候选构建时间
    candidate_time = result['add_candidate_time'] + result['drop_candidate_time']
    print(f"    ├─ Add Candidate:   {result['add_candidate_time']*1000:8.4f} ms  ({result['add_candidate_time']/iter_time*100 if iter_time > 0 else 0:5.2f}%)")
    print(f"    ├─ Drop Candidate:  {result['drop_candidate_time']*1000:8.4f} ms  ({result['drop_candidate_time']/iter_time*100 if iter_time > 0 else 0:5.2f}%)")
    print(f"    ├─ Neighbor Gen:    {result['neighbor_generation_time']*1000:8.4f} ms  ({result['neighbor_generation_time']/iter_time*100 if iter_time > 0 else 0:5.2f}%)")
    print(f"    ├─ LP Solve:        {result['lp_solve_time']*1000:8.2f} ms  ({result['lp_solve_time']/iter_time*100 if iter_time > 0 else 0:5.1f}%)")
    print(f"    └─ Neighbor Iter:   {result['neighbor_iteration_time']*1000:8.4f} ms  ({result['neighbor_iteration_time']/iter_time*100 if iter_time > 0 else 0:5.2f}%)")

    # 计算每次LP调用的平均时间
    if result['lp_solver_calls'] > 0:
        avg_lp_time = result['lp_solve_time'] / result['lp_solver_calls']
        print(f"\n[每次调用平均时间]")
        print(f"  平均每次LP调用时间: {avg_lp_time*1000:.2f} ms")

# 生成汇总表格
print("\n")
print("=" * 100)
print("时间组成汇总表格")
print("=" * 100)

print("\n### 表1: 总时间分解 (ms)")
print("-" * 100)
print(f"{'数据集':<12} {'Total':<12} {'GCN':<12} {'Initial MILP':<14} {'Local Search':<14} {'K值':<8}")
print("-" * 100)
for r in results:
    print(f"{r['dataset']:<12} {r['total_time']*1000:<12.2f} {r['threshold_time']*1000:<12.2f} {r['initial_milp_time']*1000:<14.2f} {r['local_search_time']*1000:<14.2f} {r['K']:<8.0f}")

print("\n### 表2: Local Search内部分解 (ms)")
print("-" * 100)
print(f"{'数据集':<12} {'LS Time':<12} {'Iter Time':<12} {'LP Time':<12} {'LP占比':<10} {'迭代次数':<10} {'LP次数':<10}")
print("-" * 100)
for r in results:
    lp_pct = r['lp_solve_time'] / r['total_iteration_time'] * 100 if r['total_iteration_time'] > 0 else 0
    print(f"{r['dataset']:<12} {r['local_search_time']*1000:<12.2f} {r['total_iteration_time']*1000:<12.2f} {r['lp_solve_time']*1000:<12.2f} {lp_pct:<10.1f}% {r['iterations']:<10.1f} {r['lp_solver_calls']:<10.1f}")

print("\n### 表3: 候选构建与邻域生成时间 (ms)")
print("-" * 100)
print(f"{'数据集':<12} {'Add Cand':<12} {'Drop Cand':<12} {'Neighbor Gen':<14} {'Neighbor Iter':<14} {'总计':<12}")
print("-" * 100)
for r in results:
    total_overhead = r['add_candidate_time'] + r['drop_candidate_time'] + r['neighbor_generation_time'] + r['neighbor_iteration_time']
    print(f"{r['dataset']:<12} {r['add_candidate_time']*1000:<12.4f} {r['drop_candidate_time']*1000:<12.4f} {r['neighbor_generation_time']*1000:<14.4f} {r['neighbor_iteration_time']*1000:<14.4f} {total_overhead*1000:<12.4f}")

print("\n### 表4: 每次LP调用平均时间 (ms)")
print("-" * 100)
print(f"{'数据集':<12} {'LP总时间':<14} {'LP调用次数':<14} {'平均每次LP':<14} {'m值':<8} {'K值':<8}")
print("-" * 100)
for r in results:
    avg_lp = r['lp_solve_time'] / r['lp_solver_calls'] * 1000 if r['lp_solver_calls'] > 0 else 0
    print(f"{r['dataset']:<12} {r['lp_solve_time']*1000:<14.2f} {r['lp_solver_calls']:<14.1f} {avg_lp:<14.2f} {r['m']:<8} {r['K']:<8.0f}")

print("\n### 表5: 时间占比分析")
print("-" * 100)
print(f"{'数据集':<12} {'GCN占比':<12} {'MILP占比':<12} {'LS占比':<12} {'LP占LS比':<12} {'LP占Total比':<12}")
print("-" * 100)
for r in results:
    gcn_pct = r['threshold_time'] / r['total_time'] * 100
    milp_pct = r['initial_milp_time'] / r['total_time'] * 100
    ls_pct = r['local_search_time'] / r['total_time'] * 100
    lp_ls_pct = r['lp_solve_time'] / r['local_search_time'] * 100 if r['local_search_time'] > 0 else 0
    lp_total_pct = r['lp_solve_time'] / r['total_time'] * 100
    print(f"{r['dataset']:<12} {gcn_pct:<12.1f}% {milp_pct:<12.1f}% {ls_pct:<12.1f}% {lp_ls_pct:<12.1f}% {lp_total_pct:<12.1f}%")

# 分析随m变化的趋势
print("\n")
print("=" * 100)
print("随m增长的时间变化分析")
print("=" * 100)

base = results[0]  # m10_n10 作为基准
print(f"\n以 m10_n10 为基准 (1.0x):")
print("-" * 100)
print(f"{'数据集':<12} {'m值':<8} {'Total增长':<12} {'MILP增长':<12} {'LS增长':<12} {'LP增长':<12} {'LP调用增长':<14}")
print("-" * 100)
for r in results:
    total_ratio = r['total_time'] / base['total_time']
    milp_ratio = r['initial_milp_time'] / base['initial_milp_time']
    ls_ratio = r['local_search_time'] / base['local_search_time']
    lp_ratio = r['lp_solve_time'] / base['lp_solve_time'] if base['lp_solve_time'] > 0 else 0
    lp_calls_ratio = r['lp_solver_calls'] / base['lp_solver_calls'] if base['lp_solver_calls'] > 0 else 0
    print(f"{r['dataset']:<12} {r['m']:<8} {total_ratio:<12.2f}x {milp_ratio:<12.2f}x {ls_ratio:<12.2f}x {lp_ratio:<12.2f}x {lp_calls_ratio:<14.2f}x")
