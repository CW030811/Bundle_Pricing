# -*- coding: utf-8 -*-
"""
对比test_BSP_m20n15数据集上原始版本和矩阵优化版本的结果
"""
import numpy as np
import os

script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)

original_path = 'test_result_global_topk_sqrtm_test_BSP_m20n15.csv'
matrix_path = 'test_result_global_topk_sqrtm_matrix_test_BSP_m20n15.csv'

print('='*80)
print('Matrix Optimization Comparison Report - test_BSP_m20n15')
print('='*80)

if not os.path.exists(original_path):
    print(f'\nError: Original version result file not found: {original_path}')
    print('Please run LS_Path_Test.py first')
    exit(1)

if not os.path.exists(matrix_path):
    print(f'\nError: Matrix version result file not found: {matrix_path}')
    print('Please run LS_Path_Test_Matrix.py first')
    exit(1)

orig = np.genfromtxt(original_path, delimiter=',', skip_header=1)
matrix = np.genfromtxt(matrix_path, delimiter=',', skip_header=1)

print(f'\nSample count: {len(orig)}')

print(f'\n--- Total Time Comparison ---')
orig_time = np.mean(orig[:,3])
matrix_time = np.mean(matrix[:,3])
speedup = orig_time / matrix_time if matrix_time > 0 else np.nan
print(f'  Original: {orig_time:.4f}s')
print(f'  Matrix:   {matrix_time:.4f}s')
print(f'  Speedup:  {speedup:.2f}x')
if speedup > 1.0:
    print(f'  [IMPROVED] Matrix version is {speedup:.2f}x faster')
elif speedup < 1.0:
    print(f'  [SLOWER] Matrix version is {1/speedup:.2f}x slower')
else:
    print(f'  [SAME] Performance is similar')

print(f'\n--- Local Search Time Comparison ---')
orig_ls = np.mean(orig[:,7])
matrix_ls = np.mean(matrix[:,7])
ls_speedup = orig_ls / matrix_ls if matrix_ls > 0 else np.nan
print(f'  Original: {orig_ls:.4f}s')
print(f'  Matrix:   {matrix_ls:.4f}s')
print(f'  Speedup:  {ls_speedup:.2f}x')
if ls_speedup > 1.0:
    print(f'  [IMPROVED] Matrix version is {ls_speedup:.2f}x faster')
elif ls_speedup < 1.0:
    print(f'  [SLOWER] Matrix version is {1/ls_speedup:.2f}x slower')
else:
    print(f'  [SAME] Performance is similar')

print(f'\n--- Result Consistency ---')
orig_rev = np.mean(orig[:,1])
matrix_rev = np.mean(matrix[:,1])
max_diff = np.max(np.abs(orig[:,1] - matrix[:,1]))
avg_diff = np.mean(np.abs(orig[:,1] - matrix[:,1]))
print(f'  Original Revenue: {orig_rev:.6f}')
print(f'  Matrix Revenue:   {matrix_rev:.6f}')
print(f'  Average Difference: {avg_diff:.8f}')
print(f'  Max Difference:    {max_diff:.8f}')
if max_diff < 1e-6:
    print('  [OK] Results are identical (diff < 1e-6)')
elif max_diff < 1e-4:
    print('  [OK] Results are consistent (diff < 1e-4)')
else:
    print('  [WARNING] Results differ (diff >= 1e-4)')

print(f'\n--- Iteration Statistics ---')
orig_iters = np.mean(orig[:,10])
matrix_iters = np.mean(matrix[:,10])
print(f'  Original avg iterations: {orig_iters:.2f}')
print(f'  Matrix avg iterations:   {matrix_iters:.2f}')

print(f'\n--- Improvement Statistics ---')
orig_improvements = np.mean(orig[:,11])
matrix_improvements = np.mean(matrix[:,11])
print(f'  Original avg improvements: {orig_improvements:.2f}')
print(f'  Matrix avg improvements:   {matrix_improvements:.2f}')

print('='*80)




