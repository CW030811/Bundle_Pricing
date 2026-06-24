"""
对比两个策略的实验结果：K=sqrt(m) vs K=sqrt(m*n)
"""
import numpy as np
import pandas as pd
import os

# 读取CSV文件
script_dir = os.path.dirname(os.path.abspath(__file__))

# 数据集列表
datasets = ['m10_n10_sample_100', 'm20_n10_sample_100', 'test_BSP_m10n20']

# 策略1: K = sqrt(m)
strategy1_files = {
    'm10_n10_sample_100': 'test_result_global_topk_sqrtm_m10_n10_sample_100.csv',
    'm20_n10_sample_100': 'test_result_global_topk_sqrtm_m20_n10_sample_100.csv',
    'test_BSP_m10n20': 'test_result_global_topk_sqrtm_test_BSP_m10n20.csv'
}

# 策略2: K = sqrt(m*n)
strategy2_files = {
    'm10_n10_sample_100': 'test_result_global_topk_sqrtmn_m10_n10_sample_100.csv',
    'm20_n10_sample_100': 'test_result_global_topk_sqrtmn_m20_n10_sample_100.csv',
    'test_BSP_m10n20': 'test_result_global_topk_sqrtmn_test_BSP_m10n20.csv'
}

print("=" * 80)
print("策略对比：K = sqrt(m) vs K = sqrt(m*n)")
print("=" * 80)

# 存储结果
results = []

for dataset_name in datasets:
    # 读取策略1结果
    file1 = strategy1_files.get(dataset_name)
    file2 = strategy2_files.get(dataset_name)
    
    if file1 and os.path.exists(os.path.join(script_dir, file1)):
        df1 = pd.read_csv(os.path.join(script_dir, file1))
        rev1 = df1['revenue_ratio'].mean()
        time1 = df1['runtime_ratio'].mean()
    else:
        rev1 = np.nan
        time1 = np.nan
    
    if file2 and os.path.exists(os.path.join(script_dir, file2)):
        df2 = pd.read_csv(os.path.join(script_dir, file2))
        rev2 = df2['revenue_ratio'].mean()
        time2 = df2['runtime_ratio'].mean()
    else:
        rev2 = np.nan
        time2 = np.nan
    
    results.append({
        'dataset': dataset_name,
        'sqrt_m_revenue': rev1,
        'sqrt_m_time': time1,
        'sqrt_mn_revenue': rev2,
        'sqrt_mn_time': time2
    })

# 打印表格
print("\n" + "=" * 80)
print("实验结果对比表")
print("=" * 80)
print()

# 表头
print(f"{'数据集':<25} | {'K=sqrt(m)':^30} | {'K=sqrt(m*n)':^30}")
print(f"{'':<25} | {'Revenue Ratio':<15} {'Time Ratio':<15} | {'Revenue Ratio':<15} {'Time Ratio':<15}")
print("-" * 80)

# 数据行
for r in results:
    dataset = r['dataset']
    rev1 = r['sqrt_m_revenue']
    time1 = r['sqrt_m_time']
    rev2 = r['sqrt_mn_revenue']
    time2 = r['sqrt_mn_time']
    
    if pd.isna(rev1):
        rev1_str = "N/A"
        time1_str = "N/A"
    else:
        rev1_str = f"{rev1:.6f}"
        time1_str = f"{time1:.6f}"
    
    if pd.isna(rev2):
        rev2_str = "N/A"
        time2_str = "N/A"
    else:
        rev2_str = f"{rev2:.6f}"
        time2_str = f"{time2:.6f}"
    
    print(f"{dataset:<25} | {rev1_str:<15} {time1_str:<15} | {rev2_str:<15} {time2_str:<15}")

print("-" * 80)

# 计算差异
print("\n差异分析（K=sqrt(m*n) - K=sqrt(m)）:")
print("-" * 80)
for r in results:
    dataset = r['dataset']
    if not (pd.isna(r['sqrt_m_revenue']) or pd.isna(r['sqrt_mn_revenue'])):
        rev_diff = r['sqrt_mn_revenue'] - r['sqrt_m_revenue']
        time_diff = r['sqrt_mn_time'] - r['sqrt_m_time']
        rev_pct = (rev_diff / r['sqrt_m_revenue']) * 100 if r['sqrt_m_revenue'] > 0 else 0
        time_pct = (time_diff / r['sqrt_m_time']) * 100 if r['sqrt_m_time'] > 0 else 0
        
        print(f"{dataset}:")
        print(f"  Revenue Ratio差异: {rev_diff:+.6f} ({rev_pct:+.2f}%)")
        print(f"  Time Ratio差异:     {time_diff:+.6f} ({time_pct:+.2f}%)")
    else:
        print(f"{dataset}: 数据不完整，无法计算差异")

print("\n" + "=" * 80)


