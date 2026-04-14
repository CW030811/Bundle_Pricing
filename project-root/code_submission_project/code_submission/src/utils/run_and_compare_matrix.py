"""
简化对比脚本：分别运行两个版本并对比结果

运行方式：
1. 先运行 LS_Path_Test.py 生成原始版本结果
2. 再运行 LS_Path_Test_Matrix.py 生成矩阵优化版本结果
3. 对比两个结果文件中的时间指标
"""

import os
import numpy as np
import sys

def load_results(csv_path):
    """加载CSV结果文件"""
    if not os.path.exists(csv_path):
        return None
    
    # 读取CSV文件（跳过header）
    data = np.genfromtxt(csv_path, delimiter=',', skip_header=1)
    
    # 根据header解析列
    # n_products,revenue_ratio,runtime_ratio,total_time,base_running_time,
    # threshold_time,initial_milp_time,local_search_time,
    # initial_revenue,improvement,iterations,improvements,
    # lp_solver_calls,milp_solver_calls,K,max_neighbors_per_iter
    return {
        'n_products': data[:, 0],
        'revenue_ratio': data[:, 1],
        'runtime_ratio': data[:, 2],
        'total_time': data[:, 3],
        'base_running_time': data[:, 4],
        'threshold_time': data[:, 5],
        'initial_milp_time': data[:, 6],
        'local_search_time': data[:, 7],
        'initial_revenue': data[:, 8],
        'improvement': data[:, 9],
        'iterations': data[:, 10],
        'improvements': data[:, 11],
        'lp_solver_calls': data[:, 12],
        'milp_solver_calls': data[:, 13],
        'K': data[:, 14],
        'max_neighbors_per_iter': data[:, 15],
    }


def compare_results(original_path, matrix_path, dataset_name):
    """对比两个结果文件"""
    print(f"\n{'='*80}")
    print(f"对比结果: {dataset_name}")
    print(f"{'='*80}")
    
    original = load_results(original_path)
    matrix = load_results(matrix_path)
    
    if original is None:
        print(f"原始版本结果文件不存在: {original_path}")
        return None
    
    if matrix is None:
        print(f"矩阵版本结果文件不存在: {matrix_path}")
        return None
    
    # 确保样本数一致
    n_samples_orig = len(original['revenue_ratio'])
    n_samples_matrix = len(matrix['revenue_ratio'])
    
    if n_samples_orig != n_samples_matrix:
        print(f"警告: 样本数不一致 (原始: {n_samples_orig}, 矩阵: {n_samples_matrix})")
        n_samples = min(n_samples_orig, n_samples_matrix)
    else:
        n_samples = n_samples_orig
    
    print(f"\n--- 样本统计 ---")
    print(f"样本数: {n_samples}")
    
    # 对比时间指标
    print(f"\n--- 总时间对比 ---")
    avg_orig_time = np.mean(original['total_time'][:n_samples])
    avg_matrix_time = np.mean(matrix['total_time'][:n_samples])
    time_speedup = avg_orig_time / avg_matrix_time if avg_matrix_time > 0 else np.nan
    print(f"原始版本平均总时间: {avg_orig_time:.4f} s")
    print(f"矩阵版本平均总时间: {avg_matrix_time:.4f} s")
    if not np.isnan(time_speedup):
        print(f"总时间加速比: {time_speedup:.2f}x")
    
    print(f"\n--- Local Search时间对比 ---")
    avg_orig_ls_time = np.mean(original['local_search_time'][:n_samples])
    avg_matrix_ls_time = np.mean(matrix['local_search_time'][:n_samples])
    ls_time_speedup = avg_orig_ls_time / avg_matrix_ls_time if avg_matrix_ls_time > 0 else np.nan
    print(f"原始版本平均LS时间: {avg_orig_ls_time:.4f} s")
    print(f"矩阵版本平均LS时间: {avg_matrix_ls_time:.4f} s")
    if not np.isnan(ls_time_speedup):
        print(f"LS时间加速比: {ls_time_speedup:.2f}x")
    
    # 对比结果一致性
    print(f"\n--- 结果一致性 ---")
    revenue_diff = np.abs(original['revenue_ratio'][:n_samples] - matrix['revenue_ratio'][:n_samples])
    avg_revenue_diff = np.mean(revenue_diff)
    max_revenue_diff = np.max(revenue_diff)
    print(f"原始版本平均Revenue: {np.mean(original['revenue_ratio'][:n_samples]):.6f}")
    print(f"矩阵版本平均Revenue: {np.mean(matrix['revenue_ratio'][:n_samples]):.6f}")
    print(f"平均Revenue差异: {avg_revenue_diff:.8f}")
    print(f"最大Revenue差异: {max_revenue_diff:.8f}")
    
    if max_revenue_diff < 1e-6:
        print("[OK] 结果完全一致（差异 < 1e-6）")
    elif max_revenue_diff < 1e-4:
        print("[OK] 结果基本一致（差异 < 1e-4）")
    else:
        print("[WARNING] 结果存在差异（差异 >= 1e-4）")
    
    # 对比迭代次数
    print(f"\n--- 迭代统计 ---")
    avg_orig_iters = np.mean(original['iterations'][:n_samples])
    avg_matrix_iters = np.mean(matrix['iterations'][:n_samples])
    print(f"原始版本平均迭代次数: {avg_orig_iters:.2f}")
    print(f"矩阵版本平均迭代次数: {avg_matrix_iters:.2f}")
    
    # 对比改进次数
    print(f"\n--- 改进统计 ---")
    avg_orig_improvements = np.mean(original['improvements'][:n_samples])
    avg_matrix_improvements = np.mean(matrix['improvements'][:n_samples])
    print(f"原始版本平均改进次数: {avg_orig_improvements:.2f}")
    print(f"矩阵版本平均改进次数: {avg_matrix_improvements:.2f}")
    
    return {
        'dataset_name': dataset_name,
        'n_samples': n_samples,
        'time_speedup': time_speedup,
        'ls_time_speedup': ls_time_speedup,
        'avg_revenue_diff': avg_revenue_diff,
        'max_revenue_diff': max_revenue_diff,
    }


def main():
    """主函数"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 定义数据集
    dataset_name = 'm10_n10_sample_100'
    
    # 结果文件路径
    original_path = os.path.join(script_dir, f'test_result_global_topk_sqrtm_{dataset_name}.csv')
    matrix_path = os.path.join(script_dir, f'test_result_global_topk_sqrtm_matrix_{dataset_name}.csv')
    
    print("=" * 80)
    print("矩阵优化对比分析")
    print("=" * 80)
    print(f"\n原始版本结果文件: {original_path}")
    print(f"矩阵版本结果文件: {matrix_path}")
    
    # 检查文件是否存在
    if not os.path.exists(original_path):
        print(f"\n错误: 原始版本结果文件不存在!")
        print(f"请先运行: python src/test/LS_Path_Test.py")
        return
    
    if not os.path.exists(matrix_path):
        print(f"\n错误: 矩阵版本结果文件不存在!")
        print(f"请先运行: python LS_Path_Test_Matrix.py")
        return
    
    # 对比结果
    summary = compare_results(original_path, matrix_path, dataset_name)
    
    if summary:
        print(f"\n{'='*80}")
        print("总结")
        print(f"{'='*80}")
        print(f"数据集: {summary['dataset_name']}")
        print(f"样本数: {summary['n_samples']}")
        if not np.isnan(summary['time_speedup']):
            print(f"总时间加速比: {summary['time_speedup']:.2f}x")
        if not np.isnan(summary['ls_time_speedup']):
            print(f"LS时间加速比: {summary['ls_time_speedup']:.2f}x")
        print(f"最大Revenue差异: {summary['max_revenue_diff']:.8f}")


if __name__ == "__main__":
    main()
