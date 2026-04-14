"""
对比测试脚本：比较原始版本和矩阵优化版本的性能差异

在m10_n10_sample_100数据集上对比：
1. LS_Path_Test.py (原始版本，使用嵌套循环)
2. LS_Path_Test_Matrix.py (优化版本，使用矩阵运算)

对比指标：
- Add/Drop候选构建时间
- 总迭代时间
- 结果一致性（revenue ratio）
"""

import os
import numpy as np
import time
import sys
from math import ceil, sqrt

# 导入两个版本的函数
from LS_Path_Test import (
    generate_neighbor_assignments_global_topk as generate_neighbor_original,
    local_search_with_lp_global_topk as local_search_original,
    evaluate_single_dataset as evaluate_original,
)

from LS_Path_Test_Matrix import (
    generate_neighbor_assignments_global_topk as generate_neighbor_matrix,
    local_search_with_lp_global_topk as local_search_matrix,
    evaluate_single_dataset as evaluate_matrix,
)

from test_FCP_LS import (
    process_data,
    predict_initial_bundles,
    solve_initial_milp,
)


def compare_single_sample(dat, miscellaneous, sample_id=0, verbose=False):
    """
    对比单个样本在两个版本上的表现
    
    Args:
        dat: 数据样本
        miscellaneous: 元数据
        sample_id: 样本ID
        verbose: 是否打印详细信息
    
    Returns:
        dict: 对比结果
    """
    n, segment_num, unit_cs, ship_cs, unit_us, Ns, opt_bundles, opt_prices, opt_rev, running_time, gap, stored_cs, stored_Rs = miscellaneous
    m = segment_num
    
    # 生成初始预测
    initial_pred, prob = predict_initial_bundles(dat, miscellaneous)
    initial_revenue = solve_initial_milp(initial_pred, miscellaneous)
    
    max_iterations = 50
    tolerance = 1e-6
    
    # 测试原始版本
    if verbose:
        print(f"\n--- Sample {sample_id}: Testing Original Version ---")
    original_start = time.time()
    try:
        best_pred_orig, best_rev_orig, search_info_orig = local_search_original(
            initial_pred, prob, miscellaneous, max_iterations, tolerance
        )
        original_time = time.time() - original_start
        original_success = True
    except Exception as e:
        if verbose:
            print(f"Original version failed: {e}")
        original_time = time.time() - original_start
        original_success = False
        best_rev_orig = -np.inf
        search_info_orig = {}
    
    # 测试矩阵优化版本
    if verbose:
        print(f"\n--- Sample {sample_id}: Testing Matrix Optimized Version ---")
    matrix_start = time.time()
    try:
        best_pred_matrix, best_rev_matrix, search_info_matrix = local_search_matrix(
            initial_pred, prob, miscellaneous, max_iterations, tolerance
        )
        matrix_time = time.time() - matrix_start
        matrix_success = True
    except Exception as e:
        if verbose:
            print(f"Matrix version failed: {e}")
        matrix_time = time.time() - matrix_start
        matrix_success = False
        best_rev_matrix = -np.inf
        search_info_matrix = {}
    
    # 收集对比数据
    comparison = {
        'sample_id': sample_id,
        'n': n,
        'm': m,
        'original_success': original_success,
        'matrix_success': matrix_success,
        'original_time': original_time,
        'matrix_time': matrix_time,
        'time_speedup': original_time / matrix_time if matrix_time > 0 else np.nan,
        'original_revenue': best_rev_orig if original_success else np.nan,
        'matrix_revenue': best_rev_matrix if matrix_success else np.nan,
        'revenue_diff': abs(best_rev_orig - best_rev_matrix) if (original_success and matrix_success) else np.nan,
        'original_iterations': search_info_orig.get('iterations', 0) if original_success else 0,
        'matrix_iterations': search_info_matrix.get('iterations', 0) if matrix_success else 0,
        'original_add_time': search_info_orig.get('total_add_candidate_time', 0.0) if original_success else 0.0,
        'matrix_add_time': search_info_matrix.get('total_add_candidate_time', 0.0) if matrix_success else 0.0,
        'original_drop_time': search_info_orig.get('total_drop_candidate_time', 0.0) if original_success else 0.0,
        'matrix_drop_time': search_info_matrix.get('total_drop_candidate_time', 0.0) if matrix_success else 0.0,
        'original_iteration_time': search_info_orig.get('total_iteration_time', 0.0) if original_success else 0.0,
        'matrix_iteration_time': search_info_matrix.get('total_iteration_time', 0.0) if matrix_success else 0.0,
        'add_speedup': search_info_orig.get('total_add_candidate_time', 0.0) / search_info_matrix.get('total_add_candidate_time', 1e-10) if (original_success and matrix_success and search_info_matrix.get('total_add_candidate_time', 0) > 0) else np.nan,
        'drop_speedup': search_info_orig.get('total_drop_candidate_time', 0.0) / search_info_matrix.get('total_drop_candidate_time', 1e-10) if (original_success and matrix_success and search_info_matrix.get('total_drop_candidate_time', 0) > 0) else np.nan,
    }
    
    return comparison


def compare_datasets(test_data_path, dataset_name, max_samples=100, verbose=False):
    """
    对比整个数据集在两个版本上的表现
    
    Args:
        test_data_path: 测试数据路径
        dataset_name: 数据集名称
        max_samples: 最大样本数
        verbose: 是否打印详细信息
    
    Returns:
        dict: 对比结果汇总
    """
    print(f"\n{'='*80}")
    print(f"对比测试: {dataset_name}")
    print(f"原始版本: LS_Path_Test.py (嵌套循环)")
    print(f"优化版本: LS_Path_Test_Matrix.py (矩阵运算)")
    print(f"{'='*80}")
    
    if not os.path.exists(test_data_path):
        print(f"数据集路径不存在: {test_data_path}")
        return None
    
    # 加载数据集
    print('开始加载数据集...')
    dir_list = os.listdir(test_data_path)
    sample_num = len(dir_list)
    test_dataset = []
    miscellaneous_dataset = []
    
    for i in range(sample_num):
        if dir_list[i] == '.DS_Store':
            continue
        file_path = os.path.join(test_data_path, dir_list[i])
        try:
            dat, miscellaneous = process_data(file_path)
            test_dataset.append(dat)
            miscellaneous_dataset.append(miscellaneous)
        except Exception as e:
            print(f"处理文件 {dir_list[i]} 时出错: {e}")
            continue
    
    sample_num = len(test_dataset)
    print(f'成功加载 {sample_num} 个测试样本')
    
    if sample_num == 0:
        print(f"在 {dataset_name} 中未找到有效样本")
        return None
    
    # 限制样本数
    actual_test_count = min(sample_num, max_samples)
    if sample_num > max_samples:
        print(f"限制测试为前 {actual_test_count} 个样本（共 {sample_num} 个）")
        test_dataset = test_dataset[:actual_test_count]
        miscellaneous_dataset = miscellaneous_dataset[:actual_test_count]
    
    # 对比每个样本
    comparisons = []
    from tqdm import tqdm
    
    for i in tqdm(range(actual_test_count), desc=f"对比测试 {dataset_name}"):
        try:
            comparison = compare_single_sample(
                test_dataset[i], 
                miscellaneous_dataset[i], 
                sample_id=i,
                verbose=verbose and i < 3  # 只对前3个样本打印详细信息
            )
            comparisons.append(comparison)
        except Exception as e:
            print(f"对比样本 {i} 时出错: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    if len(comparisons) == 0:
        print("没有成功的对比结果")
        return None
    
    # 计算统计信息
    def safe_mean(arr, key):
        values = [c[key] for c in comparisons if not np.isnan(c.get(key, np.nan)) and c.get('original_success', False) and c.get('matrix_success', False)]
        return np.mean(values) if len(values) > 0 else np.nan
    
    def safe_std(arr, key):
        values = [c[key] for c in comparisons if not np.isnan(c.get(key, np.nan)) and c.get('original_success', False) and c.get('matrix_success', False)]
        return np.std(values) if len(values) > 0 else np.nan
    
    summary = {
        'dataset_name': dataset_name,
        'total_samples': len(comparisons),
        'original_success_count': sum(1 for c in comparisons if c['original_success']),
        'matrix_success_count': sum(1 for c in comparisons if c['matrix_success']),
        'both_success_count': sum(1 for c in comparisons if c['original_success'] and c['matrix_success']),
        # 时间统计
        'avg_original_time': safe_mean(comparisons, 'original_time'),
        'avg_matrix_time': safe_mean(comparisons, 'matrix_time'),
        'avg_time_speedup': safe_mean(comparisons, 'time_speedup'),
        'std_time_speedup': safe_std(comparisons, 'time_speedup'),
        # Add时间统计
        'avg_original_add_time': safe_mean(comparisons, 'original_add_time'),
        'avg_matrix_add_time': safe_mean(comparisons, 'matrix_add_time'),
        'avg_add_speedup': safe_mean(comparisons, 'add_speedup'),
        'std_add_speedup': safe_std(comparisons, 'add_speedup'),
        # Drop时间统计
        'avg_original_drop_time': safe_mean(comparisons, 'original_drop_time'),
        'avg_matrix_drop_time': safe_mean(comparisons, 'matrix_drop_time'),
        'avg_drop_speedup': safe_mean(comparisons, 'drop_speedup'),
        'std_drop_speedup': safe_std(comparisons, 'drop_speedup'),
        # 迭代时间统计
        'avg_original_iteration_time': safe_mean(comparisons, 'original_iteration_time'),
        'avg_matrix_iteration_time': safe_mean(comparisons, 'matrix_iteration_time'),
        # Revenue统计
        'avg_original_revenue': safe_mean(comparisons, 'original_revenue'),
        'avg_matrix_revenue': safe_mean(comparisons, 'matrix_revenue'),
        'avg_revenue_diff': safe_mean(comparisons, 'revenue_diff'),
        'max_revenue_diff': max([c['revenue_diff'] for c in comparisons if not np.isnan(c.get('revenue_diff', np.nan))], default=np.nan),
        # 详细对比数据
        'detailed_comparisons': comparisons,
    }
    
    return summary


def print_comparison_report(summary):
    """
    打印对比报告
    """
    if summary is None:
        print("无法生成对比报告：没有有效数据")
        return
    
    print(f"\n{'='*80}")
    print(f"对比报告: {summary['dataset_name']}")
    print(f"{'='*80}")
    
    print(f"\n--- 样本统计 ---")
    print(f"总样本数: {summary['total_samples']}")
    print(f"原始版本成功: {summary['original_success_count']}")
    print(f"矩阵版本成功: {summary['matrix_success_count']}")
    print(f"两个版本都成功: {summary['both_success_count']}")
    
    print(f"\n--- 总时间对比 ---")
    print(f"原始版本平均时间: {summary['avg_original_time']:.4f} s")
    print(f"矩阵版本平均时间: {summary['avg_matrix_time']:.4f} s")
    if not np.isnan(summary['avg_time_speedup']):
        print(f"平均加速比: {summary['avg_time_speedup']:.2f}x")
        print(f"加速比标准差: {summary['std_time_speedup']:.2f}")
    
    print(f"\n--- Add候选构建时间对比 ---")
    print(f"原始版本平均时间: {summary['avg_original_add_time']:.6f} s")
    print(f"矩阵版本平均时间: {summary['avg_matrix_add_time']:.6f} s")
    if not np.isnan(summary['avg_add_speedup']):
        print(f"平均加速比: {summary['avg_add_speedup']:.2f}x")
        print(f"加速比标准差: {summary['std_add_speedup']:.2f}")
    
    print(f"\n--- Drop候选构建时间对比 ---")
    print(f"原始版本平均时间: {summary['avg_original_drop_time']:.6f} s")
    print(f"矩阵版本平均时间: {summary['avg_matrix_drop_time']:.6f} s")
    if not np.isnan(summary['avg_drop_speedup']):
        print(f"平均加速比: {summary['avg_drop_speedup']:.2f}x")
        print(f"加速比标准差: {summary['std_drop_speedup']:.2f}")
    
    print(f"\n--- 迭代时间对比 ---")
    print(f"原始版本平均迭代时间: {summary['avg_original_iteration_time']:.6f} s")
    print(f"矩阵版本平均迭代时间: {summary['avg_matrix_iteration_time']:.6f} s")
    if summary['avg_original_iteration_time'] > 0 and not np.isnan(summary['avg_matrix_iteration_time']):
        iter_speedup = summary['avg_original_iteration_time'] / summary['avg_matrix_iteration_time']
        print(f"迭代时间加速比: {iter_speedup:.2f}x")
    
    print(f"\n--- 结果一致性 ---")
    print(f"原始版本平均Revenue: {summary['avg_original_revenue']:.6f}")
    print(f"矩阵版本平均Revenue: {summary['avg_matrix_revenue']:.6f}")
    if not np.isnan(summary['avg_revenue_diff']):
        print(f"平均Revenue差异: {summary['avg_revenue_diff']:.8f}")
        print(f"最大Revenue差异: {summary['max_revenue_diff']:.8f}")
        if summary['max_revenue_diff'] < 1e-6:
            print("✓ 结果完全一致（差异 < 1e-6）")
        elif summary['max_revenue_diff'] < 1e-4:
            print("✓ 结果基本一致（差异 < 1e-4）")
        else:
            print("⚠ 结果存在差异（差异 >= 1e-4）")
    
    print(f"\n{'='*80}")


def main():
    """
    主函数：在m10_n10_sample_100数据集上对比两个版本
    """
    print("=" * 80)
    print("矩阵优化对比测试")
    print("对比原始版本（嵌套循环）和优化版本（矩阵运算）")
    print("=" * 80)
    
    # 设置路径
    script_dir = os.path.dirname(os.path.abspath(__file__))
    dataset_base_dir = os.path.join(script_dir, "Dataset")
    
    # 定义测试数据集
    datasets = {
        'm10_n10_sample_100': os.path.join(dataset_base_dir, 'm10_n10_sample_100'),
    }
    
    # 对比每个数据集
    all_summaries = []
    
    for dataset_name, test_data_path in datasets.items():
        summary = compare_datasets(test_data_path, dataset_name, max_samples=100, verbose=False)
        if summary is not None:
            all_summaries.append(summary)
            print_comparison_report(summary)
            
            # 保存详细对比数据
            if len(summary['detailed_comparisons']) > 0:
                # 提取所有键作为列名
                keys = list(summary['detailed_comparisons'][0].keys())
                # 构建数据数组
                data_rows = []
                for comp in summary['detailed_comparisons']:
                    row = [comp.get(k, np.nan) for k in keys]
                    data_rows.append(row)
                
                # 保存为CSV
                output_path = os.path.join(script_dir, f'comparison_matrix_optimization_{dataset_name}.csv')
                header = ','.join(keys)
                np.savetxt(output_path, data_rows, delimiter=',', header=header, comments='', fmt='%s')
                print(f"\n详细对比数据已保存到: {output_path}")
    
    # 打印总体总结
    if len(all_summaries) > 0:
        print(f"\n{'='*80}")
        print("总体总结")
        print(f"{'='*80}")
        for summary in all_summaries:
            print(f"\n{summary['dataset_name']}:")
            if not np.isnan(summary['avg_time_speedup']):
                print(f"  总时间加速比: {summary['avg_time_speedup']:.2f}x")
            if not np.isnan(summary['avg_add_speedup']):
                print(f"  Add时间加速比: {summary['avg_add_speedup']:.2f}x")
            if not np.isnan(summary['avg_drop_speedup']):
                print(f"  Drop时间加速比: {summary['avg_drop_speedup']:.2f}x")
    
    print("\n对比测试完成！")


if __name__ == "__main__":
    main()

