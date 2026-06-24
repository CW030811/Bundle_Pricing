"""
对比原策略和Global Top-K策略在m10_n10数据集上的时间统计
"""

import os
import numpy as np
import sys
sys.stdout.reconfigure(encoding='utf-8')

from test_FCP_LS import evaluate_single_dataset as evaluate_original_strategy
from LS_Path_Test import evaluate_single_dataset as evaluate_global_topk_strategy

def compare_strategies():
    """
    对比原策略和Global Top-K策略在m10_n10数据集上的时间统计
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    dataset_base_dir = os.path.join(script_dir, "Dataset")
    dataset_path = os.path.join(dataset_base_dir, "m10_n10_sample_100")
    
    print("=" * 80)
    print("m10_n10数据集策略对比 - 时间统计")
    print("=" * 80)
    
    # 测试原策略
    print("\n" + "=" * 80)
    print("1. 测试原策略（Segment-based策略）")
    print("=" * 80)
    original_result = evaluate_original_strategy(dataset_path, "m10_n10_sample_100")
    
    # 测试Global Top-K策略
    print("\n" + "=" * 80)
    print("2. 测试Global Top-K策略（K=sqrt(m)）")
    print("=" * 80)
    global_topk_result = evaluate_global_topk_strategy(dataset_path, "m10_n10_sample_100")
    
    # 对比分析
    print("\n" + "=" * 80)
    print("3. 策略对比分析")
    print("=" * 80)
    
    if original_result is None or global_topk_result is None:
        print("错误：无法获取测试结果")
        return
    
    # 提取原策略的时间统计
    original_results = original_result['results']
    original_avg_iter_time = original_result.get('avg_iteration_time', 0.0)
    original_avg_lp_calls = np.mean(original_results[:, 12]) if len(original_results) > 0 else 0.0
    original_avg_iterations = original_result.get('avg_iterations', 0.0)
    original_avg_per_iter_time = original_result.get('avg_per_iter_time', 0.0)
    original_avg_local_search_time = np.mean(original_results[:, 7]) if len(original_results) > 0 else 0.0
    
    # 提取Global Top-K策略的时间统计
    global_topk_results = global_topk_result['results']
    global_topk_avg_iter_time = global_topk_result.get('avg_iteration_time', 0.0)
    global_topk_avg_lp_calls = np.mean(global_topk_results[:, 12]) if len(global_topk_results) > 0 else 0.0
    global_topk_avg_iterations = global_topk_result.get('avg_iterations', 0.0)
    global_topk_avg_per_iter_time = global_topk_result.get('avg_per_iter_time', 0.0)
    global_topk_avg_local_search_time = np.mean(global_topk_results[:, 7]) if len(global_topk_results) > 0 else 0.0
    
    # 详细时间分解（Global Top-K策略）
    global_topk_avg_add_time = global_topk_result.get('avg_add_candidate_time', 0.0)
    global_topk_avg_drop_time = global_topk_result.get('avg_drop_candidate_time', 0.0)
    global_topk_avg_neighbor_gen_time = global_topk_result.get('avg_neighbor_generation_time', 0.0)
    global_topk_avg_lp_time = global_topk_result.get('avg_lp_solve_time', 0.0)
    global_topk_avg_neighbor_iter_time = global_topk_result.get('avg_neighbor_iteration_time', 0.0)
    
    # 打印对比表格
    print("\n### 总体时间对比")
    print("| 指标 | 原策略 | Global Top-K策略 | 差异 | 改善率 |")
    print("|------|--------|-----------------|------|--------|")
    print(f"| 平均Local Search时间 | {original_avg_local_search_time:.4f}s | {global_topk_avg_local_search_time:.4f}s | "
          f"{global_topk_avg_local_search_time - original_avg_local_search_time:.4f}s | "
          f"{(1 - global_topk_avg_local_search_time/original_avg_local_search_time)*100:.2f}% |")
    print(f"| 平均总迭代时间 | {original_avg_iter_time:.4f}s | {global_topk_avg_iter_time:.4f}s | "
          f"{global_topk_avg_iter_time - original_avg_iter_time:.4f}s | "
          f"{(1 - global_topk_avg_iter_time/original_avg_iter_time)*100:.2f}% |")
    print(f"| 平均迭代次数 | {original_avg_iterations:.2f} | {global_topk_avg_iterations:.2f} | "
          f"{global_topk_avg_iterations - original_avg_iterations:.2f} | "
          f"{(1 - global_topk_avg_iterations/original_avg_iterations)*100:.2f}% |")
    print(f"| 平均每轮迭代时间 | {original_avg_per_iter_time:.4f}s | {global_topk_avg_per_iter_time:.4f}s | "
          f"{global_topk_avg_per_iter_time - original_avg_per_iter_time:.4f}s | "
          f"{(1 - global_topk_avg_per_iter_time/original_avg_per_iter_time)*100:.2f}% |")
    print(f"| 平均LP调用次数 | {original_avg_lp_calls:.2f} | {global_topk_avg_lp_calls:.2f} | "
          f"{global_topk_avg_lp_calls - original_avg_lp_calls:.2f} | "
          f"{(1 - global_topk_avg_lp_calls/original_avg_lp_calls)*100:.2f}% |")
    
    if global_topk_avg_lp_calls > 0:
        original_avg_per_lp_time = original_avg_local_search_time / original_avg_lp_calls if original_avg_lp_calls > 0 else 0.0
        global_topk_avg_per_lp_time = global_topk_avg_lp_time / global_topk_avg_lp_calls
        print(f"| 平均每次LP调用时间 | {original_avg_per_lp_time*1000:.2f}ms | {global_topk_avg_per_lp_time*1000:.2f}ms | "
              f"{(global_topk_avg_per_lp_time - original_avg_per_lp_time)*1000:.2f}ms | "
              f"{(1 - global_topk_avg_per_lp_time/original_avg_per_lp_time)*100:.2f}% |")
    
    # Global Top-K策略的详细时间分解
    print("\n### Global Top-K策略详细时间分解")
    print("| 时间组成 | 时间 | 占比 |")
    print("|---------|------|------|")
    print(f"| Add Candidate构建 | {global_topk_avg_add_time:.6f}s | {global_topk_avg_add_time/global_topk_avg_iter_time*100:.2f}% |")
    print(f"| Drop Candidate构建 | {global_topk_avg_drop_time:.6f}s | {global_topk_avg_drop_time/global_topk_avg_iter_time*100:.2f}% |")
    print(f"| Neighbor生成 | {global_topk_avg_neighbor_gen_time:.6f}s | {global_topk_avg_neighbor_gen_time/global_topk_avg_iter_time*100:.2f}% |")
    print(f"| LP求解总时间 | {global_topk_avg_lp_time:.6f}s | {global_topk_avg_lp_time/global_topk_avg_iter_time*100:.2f}% |")
    print(f"| Neighbor遍历(不包括LP) | {global_topk_avg_neighbor_iter_time:.6f}s | {global_topk_avg_neighbor_iter_time/global_topk_avg_iter_time*100:.2f}% |")
    
    other_time = global_topk_avg_iter_time - (global_topk_avg_add_time + global_topk_avg_drop_time + 
                                               global_topk_avg_neighbor_gen_time + global_topk_avg_lp_time + 
                                               global_topk_avg_neighbor_iter_time)
    print(f"| 其他开销 | {other_time:.6f}s | {other_time/global_topk_avg_iter_time*100:.2f}% |")
    
    print("\n" + "=" * 80)
    print("对比完成！")
    print("=" * 80)
    
    return {
        'original': {
            'avg_local_search_time': original_avg_local_search_time,
            'avg_iter_time': original_avg_iter_time,
            'avg_iterations': original_avg_iterations,
            'avg_per_iter_time': original_avg_per_iter_time,
            'avg_lp_calls': original_avg_lp_calls,
        },
        'global_topk': {
            'avg_local_search_time': global_topk_avg_local_search_time,
            'avg_iter_time': global_topk_avg_iter_time,
            'avg_iterations': global_topk_avg_iterations,
            'avg_per_iter_time': global_topk_avg_per_iter_time,
            'avg_lp_calls': global_topk_avg_lp_calls,
            'avg_add_time': global_topk_avg_add_time,
            'avg_drop_time': global_topk_avg_drop_time,
            'avg_neighbor_gen_time': global_topk_avg_neighbor_gen_time,
            'avg_lp_time': global_topk_avg_lp_time,
            'avg_neighbor_iter_time': global_topk_avg_neighbor_iter_time,
        }
    }


if __name__ == "__main__":
    compare_strategies()


