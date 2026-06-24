"""
生成m10_n10数据集的原策略和Global Top-K策略对比报告
"""

import os
import numpy as np
import pandas as pd
import sys
sys.stdout.reconfigure(encoding='utf-8')

def generate_comparison_report():
    """
    读取CSV结果文件，生成对比报告
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 读取原策略结果
    original_csv = os.path.join(script_dir, "test_result_local_search_mix_m10_n10_sample_100.csv")
    # 读取Global Top-K策略结果
    global_topk_csv = os.path.join(script_dir, "test_result_global_topk_sqrtm_m10_n10_sample_100.csv")
    
    print("=" * 80)
    print("m10_n10数据集策略对比 - 时间统计")
    print("=" * 80)
    
    # 读取原策略结果
    if os.path.exists(original_csv):
        original_df = pd.read_csv(original_csv)
        print(f"\n原策略结果文件: {os.path.basename(original_csv)}")
        print(f"样本数量: {len(original_df)}")
    else:
        print(f"\n错误：找不到原策略结果文件: {original_csv}")
        return
    
    # 读取Global Top-K策略结果
    if os.path.exists(global_topk_csv):
        global_topk_df = pd.read_csv(global_topk_csv)
        print(f"\nGlobal Top-K策略结果文件: {os.path.basename(global_topk_csv)}")
        print(f"样本数量: {len(global_topk_df)}")
    else:
        print(f"\n错误：找不到Global Top-K策略结果文件: {global_topk_csv}")
        return
    
    # 计算原策略的平均时间统计
    original_avg_local_search_time = original_df['local_search_time'].mean()
    original_avg_iterations = original_df['iterations'].mean()
    original_avg_lp_calls = original_df['lp_solver_calls'].mean()
    original_avg_per_iter_time = original_avg_local_search_time / original_avg_iterations if original_avg_iterations > 0 else 0.0
    original_avg_per_lp_time = original_avg_local_search_time / original_avg_lp_calls if original_avg_lp_calls > 0 else 0.0
    
    # 计算Global Top-K策略的平均时间统计
    global_topk_avg_local_search_time = global_topk_df['local_search_time'].mean()
    global_topk_avg_iterations = global_topk_df['iterations'].mean()
    global_topk_avg_lp_calls = global_topk_df['lp_solver_calls'].mean()
    global_topk_avg_per_iter_time = global_topk_avg_local_search_time / global_topk_avg_iterations if global_topk_avg_iterations > 0 else 0.0
    global_topk_avg_per_lp_time = global_topk_avg_local_search_time / global_topk_avg_lp_calls if global_topk_avg_lp_calls > 0 else 0.0
    
    # 打印对比表格
    print("\n" + "=" * 80)
    print("策略对比分析")
    print("=" * 80)
    
    print("\n### 总体时间对比")
    print("| 指标 | 原策略 | Global Top-K策略 | 差异 | 改善率 |")
    print("|------|--------|-----------------|------|--------|")
    
    diff_ls = global_topk_avg_local_search_time - original_avg_local_search_time
    improvement_ls = (1 - global_topk_avg_local_search_time/original_avg_local_search_time)*100 if original_avg_local_search_time > 0 else 0.0
    print(f"| 平均Local Search时间 | {original_avg_local_search_time:.4f}s | {global_topk_avg_local_search_time:.4f}s | "
          f"{diff_ls:.4f}s | {improvement_ls:.2f}% |")
    
    diff_iter = global_topk_avg_iterations - original_avg_iterations
    improvement_iter = (1 - global_topk_avg_iterations/original_avg_iterations)*100 if original_avg_iterations > 0 else 0.0
    print(f"| 平均迭代次数 | {original_avg_iterations:.2f} | {global_topk_avg_iterations:.2f} | "
          f"{diff_iter:.2f} | {improvement_iter:.2f}% |")
    
    diff_per_iter = global_topk_avg_per_iter_time - original_avg_per_iter_time
    improvement_per_iter = (1 - global_topk_avg_per_iter_time/original_avg_per_iter_time)*100 if original_avg_per_iter_time > 0 else 0.0
    print(f"| 平均每轮迭代时间 | {original_avg_per_iter_time:.4f}s | {global_topk_avg_per_iter_time:.4f}s | "
          f"{diff_per_iter:.4f}s | {improvement_per_iter:.2f}% |")
    
    diff_lp_calls = global_topk_avg_lp_calls - original_avg_lp_calls
    improvement_lp_calls = (1 - global_topk_avg_lp_calls/original_avg_lp_calls)*100 if original_avg_lp_calls > 0 else 0.0
    print(f"| 平均LP调用次数 | {original_avg_lp_calls:.2f} | {global_topk_avg_lp_calls:.2f} | "
          f"{diff_lp_calls:.2f} | {improvement_lp_calls:.2f}% |")
    
    diff_per_lp = global_topk_avg_per_lp_time - original_avg_per_lp_time
    improvement_per_lp = (1 - global_topk_avg_per_lp_time/original_avg_per_lp_time)*100 if original_avg_per_lp_time > 0 else 0.0
    print(f"| 平均每次LP调用时间 | {original_avg_per_lp_time*1000:.2f}ms | {global_topk_avg_per_lp_time*1000:.2f}ms | "
          f"{diff_per_lp*1000:.2f}ms | {improvement_per_lp:.2f}% |")
    
    # Revenue对比
    original_avg_revenue = original_df['revenue_ratio'].mean()
    global_topk_avg_revenue = global_topk_df['revenue_ratio'].mean()
    diff_revenue = global_topk_avg_revenue - original_avg_revenue
    print(f"\n| 平均Revenue Ratio | {original_avg_revenue:.4f} | {global_topk_avg_revenue:.4f} | "
          f"{diff_revenue:.4f} | {diff_revenue/original_avg_revenue*100:.2f}% |")
    
    # 详细统计
    print("\n### 详细统计")
    print("\n**原策略统计**:")
    print(f"- Local Search时间: {original_avg_local_search_time:.4f}s (标准差: {original_df['local_search_time'].std():.4f}s)")
    print(f"- 迭代次数: {original_avg_iterations:.2f} (标准差: {original_df['iterations'].std():.2f})")
    print(f"- LP调用次数: {original_avg_lp_calls:.2f} (标准差: {original_df['lp_solver_calls'].std():.2f})")
    print(f"- Revenue Ratio: {original_avg_revenue:.4f} (标准差: {original_df['revenue_ratio'].std():.4f})")
    
    print("\n**Global Top-K策略统计**:")
    print(f"- Local Search时间: {global_topk_avg_local_search_time:.4f}s (标准差: {global_topk_df['local_search_time'].std():.4f}s)")
    print(f"- 迭代次数: {global_topk_avg_iterations:.2f} (标准差: {global_topk_df['iterations'].std():.2f})")
    print(f"- LP调用次数: {global_topk_avg_lp_calls:.2f} (标准差: {global_topk_df['lp_solver_calls'].std():.2f})")
    print(f"- Revenue Ratio: {global_topk_avg_revenue:.4f} (标准差: {global_topk_df['revenue_ratio'].std():.4f})")
    
    print("\n" + "=" * 80)
    print("对比完成！")
    print("=" * 80)
    
    return {
        'original': {
            'avg_local_search_time': original_avg_local_search_time,
            'avg_iterations': original_avg_iterations,
            'avg_lp_calls': original_avg_lp_calls,
            'avg_per_iter_time': original_avg_per_iter_time,
            'avg_per_lp_time': original_avg_per_lp_time,
            'avg_revenue': original_avg_revenue,
        },
        'global_topk': {
            'avg_local_search_time': global_topk_avg_local_search_time,
            'avg_iterations': global_topk_avg_iterations,
            'avg_lp_calls': global_topk_avg_lp_calls,
            'avg_per_iter_time': global_topk_avg_per_iter_time,
            'avg_per_lp_time': global_topk_avg_per_lp_time,
            'avg_revenue': global_topk_avg_revenue,
        }
    }


if __name__ == "__main__":
    generate_comparison_report()


