"""
Global Top-K 策略对比分析脚本
分析所有数据集上的实验结果，生成详细对比报告
"""
import pandas as pd
import numpy as np
import os

# 读取所有相关CSV文件
files = {
    'orig_m10_n10': 'test_result_local_search_mix_m10_n10_sample_100.csv',
    'orig_m20_n10': 'test_result_local_search_mix_m20_n10_sample_100.csv',
    'orig_m30_n10': 'test_result_local_search_mix_m30_n10_sample_100.csv',
    'orig_BSP_m10n15': 'test_result_local_search_mix_test_BSP_m10n15.csv',
    'orig_BSP_m10n20': 'test_result_local_search_mix_test_BSP_m10n20.csv',
    'orig_BSP_m10n25': 'test_result_local_search_mix_test_BSP_m10n25.csv',
    'orig_BSP_m15n15': 'test_result_local_search_mix_test_BSP_m15n15.csv',
    'orig_BSP_m20n15': 'test_result_local_search_mix_test_BSP_m20n15.csv',
    'topk_2sqrtm_m10_n10': 'test_result_global_topk_m10_n10_sample_100.csv',
    'topk_2sqrtm_m20_n10': 'test_result_global_topk_m20_n10_sample_100.csv',
    'topk_2sqrtm_m30_n10': 'test_result_global_topk_m30_n10_sample_100.csv',
    'topk_2sqrtm_BSP_m10n15': 'test_result_global_topk_test_BSP_m10n15.csv',
    'topk_2sqrtm_BSP_m10n20': 'test_result_global_topk_test_BSP_m10n20.csv',
    'topk_2sqrtm_BSP_m10n25': 'test_result_global_topk_test_BSP_m10n25.csv',
    'topk_2sqrtm_BSP_m15n15': 'test_result_global_topk_test_BSP_m15n15.csv',
    'topk_2sqrtm_BSP_m20n15': 'test_result_global_topk_test_BSP_m20n15.csv',
    'topk_sqrtm_m10_n10': 'test_result_global_topk_sqrtm_m10_n10_sample_100.csv',
    'topk_sqrtm_m20_n10': 'test_result_global_topk_sqrtm_m20_n10_sample_100.csv',
    'topk_sqrtm_m30_n10': 'test_result_global_topk_sqrtm_m30_n10_sample_100.csv',
    'topk_sqrtm_BSP_m10n15': 'test_result_global_topk_sqrtm_test_BSP_m10n15.csv',
    'topk_sqrtm_BSP_m10n20': 'test_result_global_topk_sqrtm_test_BSP_m10n20.csv',
    'topk_sqrtm_BSP_m10n25': 'test_result_global_topk_sqrtm_test_BSP_m10n25.csv',
    'topk_sqrtm_BSP_m15n15': 'test_result_global_topk_sqrtm_test_BSP_m15n15.csv',
    'topk_sqrtm_BSP_m20n15': 'test_result_global_topk_sqrtm_test_BSP_m20n15.csv',
}

data = {}
for name, file in files.items():
    if os.path.exists(file):
        data[name] = pd.read_csv(file)

# 数据集列表
datasets = ['m10_n10', 'm20_n10', 'm30_n10', 'BSP_m10n15', 'BSP_m10n20', 'BSP_m10n25', 'BSP_m15n15', 'BSP_m20n15']

print('='*100)
print('GLOBAL TOP-K 策略对比原策略 - 详细分析报告')
print('='*100)
print()

# 计算统计数据
results = []

for ds in datasets:
    orig_key = f'orig_{ds}'
    topk_2sqrt_key = f'topk_2sqrtm_{ds}'
    topk_sqrt_key = f'topk_sqrtm_{ds}'

    if orig_key in data and topk_sqrt_key in data:
        orig = data[orig_key]
        topk_sqrt = data[topk_sqrt_key]
        topk_2sqrt = data.get(topk_2sqrt_key)

        result = {
            'dataset': ds,
            'orig_revenue': orig['revenue_ratio'].mean(),
            'orig_revenue_std': orig['revenue_ratio'].std(),
            'orig_time_ratio': orig['runtime_ratio'].mean(),
            'orig_total_time': orig['total_time'].mean(),
            'orig_ls_time': orig['local_search_time'].mean(),
            'orig_lp_calls': orig['lp_solver_calls'].mean(),
            'orig_iterations': orig['iterations'].mean(),
            'orig_improvements': orig['improvements'].mean(),
            'sqrt_revenue': topk_sqrt['revenue_ratio'].mean(),
            'sqrt_revenue_std': topk_sqrt['revenue_ratio'].std(),
            'sqrt_time_ratio': topk_sqrt['runtime_ratio'].mean(),
            'sqrt_total_time': topk_sqrt['total_time'].mean(),
            'sqrt_ls_time': topk_sqrt['local_search_time'].mean(),
            'sqrt_lp_calls': topk_sqrt['lp_solver_calls'].mean(),
            'sqrt_iterations': topk_sqrt['iterations'].mean(),
            'sqrt_improvements': topk_sqrt['improvements'].mean(),
            'sqrt_K': topk_sqrt['K'].mean() if 'K' in topk_sqrt.columns else 0,
        }

        if topk_2sqrt is not None:
            result['2sqrt_revenue'] = topk_2sqrt['revenue_ratio'].mean()
            result['2sqrt_time_ratio'] = topk_2sqrt['runtime_ratio'].mean()
            result['2sqrt_total_time'] = topk_2sqrt['total_time'].mean()
            result['2sqrt_ls_time'] = topk_2sqrt['local_search_time'].mean()
            result['2sqrt_lp_calls'] = topk_2sqrt['lp_solver_calls'].mean()
            result['2sqrt_K'] = topk_2sqrt['K'].mean() if 'K' in topk_2sqrt.columns else 0

        results.append(result)

# 打印详细结果
print('一、Revenue Ratio 对比 (收益比率)')
print('-'*100)
header = f"{'数据集':<15} {'原策略':<15} {'K=2*sqrt(m)':<15} {'K=sqrt(m)':<15} {'sqrt vs 原 (差异)':<20}"
print(header)
print('-'*100)
for r in results:
    sqrt_diff = r['sqrt_revenue'] - r['orig_revenue']
    sqrt_pct = (sqrt_diff / r['orig_revenue']) * 100
    _2sqrt = f"{r.get('2sqrt_revenue', 0):.4f}" if r.get('2sqrt_revenue') else 'N/A'
    print(f"{r['dataset']:<15} {r['orig_revenue']:.4f}          {_2sqrt:<15} {r['sqrt_revenue']:.4f}          {sqrt_diff:+.4f} ({sqrt_pct:+.2f}%)")

print()
print('二、Time Ratio 对比 (时间/基准时间)')
print('-'*100)
header = f"{'数据集':<15} {'原策略':<15} {'K=2*sqrt(m)':<15} {'K=sqrt(m)':<15} {'加速比 (sqrt vs 原)':<20}"
print(header)
print('-'*100)
for r in results:
    speedup = r['orig_time_ratio'] / r['sqrt_time_ratio'] if r['sqrt_time_ratio'] > 0 else 0
    reduction = (1 - r['sqrt_time_ratio'] / r['orig_time_ratio']) * 100 if r['orig_time_ratio'] > 0 else 0
    _2sqrt = f"{r.get('2sqrt_time_ratio', 0):.4f}" if r.get('2sqrt_time_ratio') else 'N/A'
    print(f"{r['dataset']:<15} {r['orig_time_ratio']:.4f}          {_2sqrt:<15} {r['sqrt_time_ratio']:.4f}          {speedup:.2f}x (-{reduction:.1f}%)")

print()
print('三、LP调用次数对比')
print('-'*100)
header = f"{'数据集':<15} {'原策略':<15} {'K=2*sqrt(m)':<15} {'K=sqrt(m)':<15} {'减少率 (sqrt vs 原)':<20}"
print(header)
print('-'*100)
for r in results:
    reduction = (r['orig_lp_calls'] - r['sqrt_lp_calls']) / r['orig_lp_calls'] * 100 if r['orig_lp_calls'] > 0 else 0
    _2sqrt = f"{r.get('2sqrt_lp_calls', 0):.1f}" if r.get('2sqrt_lp_calls') else 'N/A'
    print(f"{r['dataset']:<15} {r['orig_lp_calls']:.1f}           {_2sqrt:<15} {r['sqrt_lp_calls']:.1f}           -{reduction:.1f}%")

print()
print('四、Local Search时间对比 (秒)')
print('-'*100)
header = f"{'数据集':<15} {'原策略':<15} {'K=2*sqrt(m)':<15} {'K=sqrt(m)':<15} {'加速比 (sqrt vs 原)':<20}"
print(header)
print('-'*100)
for r in results:
    speedup = r['orig_ls_time'] / r['sqrt_ls_time'] if r['sqrt_ls_time'] > 0 else 0
    reduction = (1 - r['sqrt_ls_time'] / r['orig_ls_time']) * 100 if r['orig_ls_time'] > 0 else 0
    _2sqrt = f"{r.get('2sqrt_ls_time', 0):.4f}" if r.get('2sqrt_ls_time') else 'N/A'
    print(f"{r['dataset']:<15} {r['orig_ls_time']:.4f}s         {_2sqrt:<15} {r['sqrt_ls_time']:.4f}s         {speedup:.2f}x (-{reduction:.1f}%)")

print()
print('五、总时间对比 (秒)')
print('-'*100)
header = f"{'数据集':<15} {'原策略':<15} {'K=2*sqrt(m)':<15} {'K=sqrt(m)':<15} {'加速比 (sqrt vs 原)':<20}"
print(header)
print('-'*100)
for r in results:
    speedup = r['orig_total_time'] / r['sqrt_total_time'] if r['sqrt_total_time'] > 0 else 0
    reduction = (1 - r['sqrt_total_time'] / r['orig_total_time']) * 100 if r['orig_total_time'] > 0 else 0
    _2sqrt = f"{r.get('2sqrt_total_time', 0):.4f}" if r.get('2sqrt_total_time') else 'N/A'
    print(f"{r['dataset']:<15} {r['orig_total_time']:.4f}s         {_2sqrt:<15} {r['sqrt_total_time']:.4f}s         {speedup:.2f}x (-{reduction:.1f}%)")

print()
print('六、迭代次数对比')
print('-'*100)
header = f"{'数据集':<15} {'原策略':<15} {'K=sqrt(m)':<15} {'K值':<10}"
print(header)
print('-'*100)
for r in results:
    print(f"{r['dataset']:<15} {r['orig_iterations']:.1f}           {r['sqrt_iterations']:.1f}           K={r['sqrt_K']:.0f}")

print()
print('七、改进次数对比')
print('-'*100)
header = f"{'数据集':<15} {'原策略':<15} {'K=sqrt(m)':<15} {'差异':<15}"
print(header)
print('-'*100)
for r in results:
    diff = r['sqrt_improvements'] - r['orig_improvements']
    print(f"{r['dataset']:<15} {r['orig_improvements']:.1f}           {r['sqrt_improvements']:.1f}           {diff:+.1f}")

print()
print('='*100)
print('八、综合汇总表')
print('='*100)
print()

# 计算平均值
avg_revenue_diff = np.mean([r['sqrt_revenue'] - r['orig_revenue'] for r in results])
avg_time_speedup = np.mean([r['orig_time_ratio'] / r['sqrt_time_ratio'] for r in results if r['sqrt_time_ratio'] > 0])
avg_lp_reduction = np.mean([(r['orig_lp_calls'] - r['sqrt_lp_calls']) / r['orig_lp_calls'] * 100 for r in results if r['orig_lp_calls'] > 0])
avg_ls_speedup = np.mean([r['orig_ls_time'] / r['sqrt_ls_time'] for r in results if r['sqrt_ls_time'] > 0])

print(f"平均 Revenue Ratio 差异:  {avg_revenue_diff:+.4f} ({avg_revenue_diff*100:+.2f}%)")
print(f"平均 Time Ratio 加速比:   {avg_time_speedup:.2f}x")
print(f"平均 LP调用减少率:        {avg_lp_reduction:.1f}%")
print(f"平均 Local Search 加速比: {avg_ls_speedup:.2f}x")

print()
print('='*100)
print('九、K值参数设置说明')
print('='*100)
print()
for r in results:
    # 从数据集名称推断m值
    ds = r['dataset']
    if 'm10' in ds:
        m = 10
    elif 'm15' in ds:
        m = 15
    elif 'm20' in ds:
        m = 20
    elif 'm30' in ds:
        m = 30
    else:
        m = 10

    k_val = r['sqrt_K']
    theoretical_k = int(np.ceil(np.sqrt(m)))
    print(f"{ds}: m={m}, K=ceil(sqrt({m}))={theoretical_k}, 实际K={k_val:.0f}")
