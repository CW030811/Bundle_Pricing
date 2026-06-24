"""
生成策略对比表格
"""
import pandas as pd
import os

script_dir = os.path.dirname(os.path.abspath(__file__))

# 读取数据
datasets = {
    'm10_n10_sample_100': {
        'sqrt_m': 'test_result_global_topk_sqrtm_m10_n10_sample_100.csv',
        'sqrt_mn': 'test_result_global_topk_sqrtmn_m10_n10_sample_100.csv'
    },
    'm20_n10_sample_100': {
        'sqrt_m': 'test_result_global_topk_sqrtm_m20_n10_sample_100.csv',
        'sqrt_mn': 'test_result_global_topk_sqrtmn_m20_n10_sample_100.csv'
    },
    'test_BSP_m10n20': {
        'sqrt_m': 'test_result_global_topk_sqrtm_test_BSP_m10n20.csv',
        'sqrt_mn': 'test_result_global_topk_sqrtmn_test_BSP_m10n20.csv'
    }
}

print("=" * 90)
print("策略对比表：K = sqrt(m) vs K = sqrt(m*n)")
print("=" * 90)
print()
print(f"{'数据集':<25} | {'K=sqrt(m)':^35} | {'K=sqrt(m*n)':^35}")
print(f"{'':<25} | {'Revenue Ratio':<17} {'Time Ratio':<17} | {'Revenue Ratio':<17} {'Time Ratio':<17}")
print("-" * 90)

for dataset_name, files in datasets.items():
    # 读取K=sqrt(m)结果
    if os.path.exists(os.path.join(script_dir, files['sqrt_m'])):
        df1 = pd.read_csv(os.path.join(script_dir, files['sqrt_m']))
        rev1 = df1['revenue_ratio'].mean()
        time1 = df1['runtime_ratio'].mean()
    else:
        rev1 = None
        time1 = None
    
    # 读取K=sqrt(m*n)结果
    if os.path.exists(os.path.join(script_dir, files['sqrt_mn'])):
        df2 = pd.read_csv(os.path.join(script_dir, files['sqrt_mn']))
        rev2 = df2['revenue_ratio'].mean()
        time2 = df2['runtime_ratio'].mean()
    else:
        rev2 = None
        time2 = None
    
    # 打印行
    if rev1 is not None and time1 is not None:
        rev1_str = f"{rev1:.6f}"
        time1_str = f"{time1:.6f}"
    else:
        rev1_str = "N/A"
        time1_str = "N/A"
    
    if rev2 is not None and time2 is not None:
        rev2_str = f"{rev2:.6f}"
        time2_str = f"{time2:.6f}"
    else:
        rev2_str = "N/A"
        time2_str = "N/A"
    
    print(f"{dataset_name:<25} | {rev1_str:<17} {time1_str:<17} | {rev2_str:<17} {time2_str:<17}")

print("-" * 90)
print()

# 计算差异
print("差异分析（K=sqrt(m*n) - K=sqrt(m)）:")
print("-" * 90)
for dataset_name, files in datasets.items():
    if os.path.exists(os.path.join(script_dir, files['sqrt_m'])) and os.path.exists(os.path.join(script_dir, files['sqrt_mn'])):
        df1 = pd.read_csv(os.path.join(script_dir, files['sqrt_m']))
        df2 = pd.read_csv(os.path.join(script_dir, files['sqrt_mn']))
        
        rev1 = df1['revenue_ratio'].mean()
        time1 = df1['runtime_ratio'].mean()
        rev2 = df2['revenue_ratio'].mean()
        time2 = df2['runtime_ratio'].mean()
        
        rev_diff = rev2 - rev1
        time_diff = time2 - time1
        rev_pct = (rev_diff / rev1) * 100 if rev1 > 0 else 0
        time_pct = (time_diff / time1) * 100 if time1 > 0 else 0
        
        print(f"{dataset_name}:")
        print(f"  Revenue Ratio差异: {rev_diff:+.6f} ({rev_pct:+.2f}%)")
        print(f"  Time Ratio差异:     {time_diff:+.6f} ({time_pct:+.2f}%)")
        print()

print("=" * 90)


