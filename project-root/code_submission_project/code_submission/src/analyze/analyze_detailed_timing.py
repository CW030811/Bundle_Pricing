"""
分析Local Search的详细时间组成
运行LS_Path_Test.py后，分析并生成详细的时间分解报告
"""

import os
import numpy as np
import pandas as pd
from glob import glob

def analyze_timing_breakdown():
    """
    分析Local Search的详细时间组成
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 读取CSV结果文件
    csv_files = glob(os.path.join(script_dir, "test_result_global_topk_sqrtm_*.csv"))
    
    if not csv_files:
        print("未找到结果文件")
        return
    
    print("=" * 80)
    print("Local Search详细时间组成分析")
    print("=" * 80)
    
    all_results = []
    
    for csv_file in csv_files:
        dataset_name = os.path.basename(csv_file).replace("test_result_global_topk_sqrtm_", "").replace(".csv", "")
        print(f"\n分析数据集: {dataset_name}")
        
        # 读取CSV
        df = pd.read_csv(csv_file)
        
        # 计算平均时间
        avg_local_search_time = df['local_search_time'].mean()
        avg_lp_calls = df['lp_solver_calls'].mean()
        avg_iterations = df['iterations'].mean()
        
        print(f"平均Local Search时间: {avg_local_search_time:.4f}s")
        print(f"平均LP调用次数: {avg_lp_calls:.2f}")
        print(f"平均迭代次数: {avg_iterations:.2f}")
        
        # 估算时间组成（基于代码逻辑）
        # 注意：这里需要从实际运行中获取详细时间，目前只能估算
        avg_per_lp_time = avg_local_search_time / avg_lp_calls if avg_lp_calls > 0 else 0
        print(f"平均每次LP调用时间: {avg_per_lp_time:.6f}s ({avg_per_lp_time*1000:.2f}ms)")
        
        all_results.append({
            'dataset': dataset_name,
            'avg_local_search_time': avg_local_search_time,
            'avg_lp_calls': avg_lp_calls,
            'avg_iterations': avg_iterations,
            'avg_per_lp_time': avg_per_lp_time,
        })
    
    print("\n" + "=" * 80)
    print("总结")
    print("=" * 80)
    
    if all_results:
        df_summary = pd.DataFrame(all_results)
        print(df_summary.to_string(index=False))
    
    print("\n注意：详细的时间分解（Add/Drop candidate构建时间、neighbor遍历时间等）")
    print("需要从实际运行中获取，请运行LS_Path_Test.py并查看search_info中的详细时间信息")


if __name__ == "__main__":
    analyze_timing_breakdown()


