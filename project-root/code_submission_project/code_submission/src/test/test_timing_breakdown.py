"""
测试Local Search的详细时间分解
"""

import os
import sys
sys.stdout.reconfigure(encoding='utf-8')

from LS_Path_Test import (
    process_data,
    predict_initial_bundles,
    local_search_with_lp_global_topk,
)

def test_timing_breakdown():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    sample_file = os.path.join(script_dir, "Dataset", "m10_n10_sample_100", "sample_data_100_size_10.msgpack")
    
    if not os.path.exists(sample_file):
        print(f"Sample file not found: {sample_file}")
        return
    
    print("加载数据...")
    dat, meta = process_data(sample_file)
    initial_pred, prob = predict_initial_bundles(dat, meta)
    
    print("运行Local Search（限制5轮迭代）...")
    final_pred, final_rev, search_info = local_search_with_lp_global_topk(
        initial_pred, prob, meta, max_iterations=5, tolerance=1e-6
    )
    
    print("\n" + "=" * 80)
    print("时间分解分析")
    print("=" * 80)
    
    total_iter_time = search_info.get('total_iteration_time', 0.0)
    add_time = search_info.get('total_add_candidate_time', 0.0)
    drop_time = search_info.get('total_drop_candidate_time', 0.0)
    neighbor_gen_time = search_info.get('total_neighbor_generation_time', 0.0)
    lp_solve_time = search_info.get('total_lp_solve_time', 0.0)
    neighbor_iter_time = search_info.get('total_neighbor_iteration_time', 0.0)
    lp_calls = search_info.get('lp_solver_calls', 0)
    
    print(f"\n总迭代时间: {total_iter_time:.6f}s")
    print(f"\n详细时间分解:")
    print(f"  Add candidate构建时间: {add_time:.6f}s ({add_time/total_iter_time*100:.2f}%)")
    print(f"  Drop candidate构建时间: {drop_time:.6f}s ({drop_time/total_iter_time*100:.2f}%)")
    print(f"  Neighbor生成时间: {neighbor_gen_time:.6f}s ({neighbor_gen_time/total_iter_time*100:.2f}%)")
    print(f"  LP求解总时间: {lp_solve_time:.6f}s ({lp_solve_time/total_iter_time*100:.2f}%)")
    print(f"  Neighbor遍历时间（不包括LP）: {neighbor_iter_time:.6f}s ({neighbor_iter_time/total_iter_time*100:.2f}%)")
    
    print(f"\nLP求解统计:")
    print(f"  LP调用次数: {lp_calls}")
    if lp_calls > 0:
        avg_lp_time = lp_solve_time / lp_calls
        print(f"  平均每次LP调用时间: {avg_lp_time:.6f}s ({avg_lp_time*1000:.2f}ms)")
    
    # 计算其他开销
    accounted_time = add_time + drop_time + neighbor_gen_time + lp_solve_time + neighbor_iter_time
    other_time = total_iter_time - accounted_time
    print(f"\n其他开销: {other_time:.6f}s ({other_time/total_iter_time*100:.2f}%)")
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    test_timing_breakdown()


