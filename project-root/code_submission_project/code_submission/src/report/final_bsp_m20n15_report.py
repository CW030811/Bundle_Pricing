# -*- coding: utf-8 -*-
import numpy as np
import os

os.chdir('code_submission')

orig = np.genfromtxt('test_result_global_topk_sqrtm_test_BSP_m20n15.csv', delimiter=',', skip_header=1)
matrix = np.genfromtxt('test_result_global_topk_sqrtm_matrix_test_BSP_m20n15.csv', delimiter=',', skip_header=1)

print('='*80)
print('Matrix Optimization Comparison - test_BSP_m20n15')
print('='*80)
print(f'\nSamples: {len(orig)}')

print(f'\n--- Total Time ---')
orig_time = np.mean(orig[:,3])
matrix_time = np.mean(matrix[:,3])
speedup = orig_time / matrix_time
print(f'  Original: {orig_time:.4f}s')
print(f'  Matrix:   {matrix_time:.4f}s')
print(f'  Speedup:  {speedup:.2f}x')

print(f'\n--- Local Search Time ---')
orig_ls = np.mean(orig[:,7])
matrix_ls = np.mean(matrix[:,7])
ls_speedup = orig_ls / matrix_ls
print(f'  Original: {orig_ls:.4f}s')
print(f'  Matrix:   {matrix_ls:.4f}s')
print(f'  Speedup:  {ls_speedup:.2f}x')

print(f'\n--- Revenue Consistency ---')
orig_rev = np.mean(orig[:,1])
matrix_rev = np.mean(matrix[:,1])
max_diff = np.max(np.abs(orig[:,1] - matrix[:,1]))
avg_diff = np.mean(np.abs(orig[:,1] - matrix[:,1]))
print(f'  Original: {orig_rev:.6f}')
print(f'  Matrix:   {matrix_rev:.6f}')
print(f'  Avg Diff: {avg_diff:.8f}')
print(f'  Max Diff: {max_diff:.8f}')
if max_diff < 1e-6:
    print('  [OK] Identical')
elif max_diff < 1e-4:
    print('  [OK] Consistent')
else:
    print('  [WARNING] Different')

print(f'\n--- Iterations ---')
orig_iters = np.mean(orig[:,10])
matrix_iters = np.mean(matrix[:,10])
print(f'  Original: {orig_iters:.2f}')
print(f'  Matrix:   {matrix_iters:.2f}')

print('='*80)




