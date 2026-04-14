"""
运行路径策略和矩阵优化策略，并详细记录Local Search时间组成
"""
import os
import pandas as pd
import numpy as np

script_dir = os.path.dirname(os.path.abspath(__file__))

# 数据集配置
datasets = {
    'm10_n10_sample_100': os.path.join(script_dir, "Dataset", 'm10_n10_sample_100'),
    'm20_n10_sample_100': os.path.join(script_dir, "Dataset", 'm20_n10_sample_100'),
    'm30_n10_sample_100': os.path.join(script_dir, "Dataset", 'm30_n10_sample_100'),
}

print("=" * 80)
print("Local Search时间组成分析")
print("=" * 80)
print("\n将运行两个策略：")
print("1. 路径策略 (LS_Path_Test.py) - K=sqrt(m)")
print("2. 矩阵优化策略 (LS_Path_Test_Matrix.py) - K=sqrt(m)")
print("\n数据集：")
for name in datasets.keys():
    print(f"  - {name}")

print("\n" + "=" * 80)
print("开始运行路径策略...")
print("=" * 80)

# 运行路径策略
import subprocess
import sys

for dataset_name, dataset_path in datasets.items():
    print(f"\n运行路径策略在 {dataset_name}...")
    # 注意：这里需要修改LS_Path_Test.py的main函数来支持指定数据集
    # 或者直接运行整个脚本，它会处理所有数据集

print("\n" + "=" * 80)
print("开始运行矩阵优化策略...")
print("=" * 80)

for dataset_name, dataset_path in datasets.items():
    print(f"\n运行矩阵优化策略在 {dataset_name}...")

print("\n" + "=" * 80)
print("分析结果...")
print("=" * 80)


