# -*- coding: utf-8 -*-
import numpy as np
import os

os.chdir('code_submission')

orig = np.genfromtxt('test_result_global_topk_sqrtm_m10_n10_sample_100.csv', delimiter=',', skip_header=1)
matrix = np.genfromtxt('test_result_global_topk_sqrtm_matrix_m10_n10_sample_100.csv', delimiter=',', skip_header=1)

print('='*80)
print('Matrix Optimization Comparison Report')
print('='*80)
print(f'\nSample count: {len(orig)}')

print(f'\n--- Total Time Comparison ---')
orig_time = np.mean(orig[:,3])
matrix_time = np.mean(matrix[:,3])
speedup = orig_time / matrix_time if matrix_time > 0 else np.nan
print(f'  Original: {orig_time:.4f}s')
print(f'  Matrix:   {matrix_time:.4f}s')
print(f'  Speedup:  {speedup:.2f}x')

print(f'\n--- Local Search Time Comparison ---')
orig_ls = np.mean(orig[:,7])
matrix_ls = np.mean(matrix[:,7])
ls_speedup = orig_ls / matrix_ls if matrix_ls > 0 else np.nan
print(f'  Original: {orig_ls:.4f}s')
print(f'  Matrix:   {matrix_ls:.4f}s')
print(f'  Speedup:  {ls_speedup:.2f}x')

print(f'\n--- Result Consistency ---')
orig_rev = np.mean(orig[:,1])
matrix_rev = np.mean(matrix[:,1])
max_diff = np.max(np.abs(orig[:,1] - matrix[:,1]))
print(f'  Original Revenue: {orig_rev:.6f}')
print(f'  Matrix Revenue:   {matrix_rev:.6f}')
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

print('='*80)




