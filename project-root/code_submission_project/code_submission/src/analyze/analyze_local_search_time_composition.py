"""
分析并对比路径策略和矩阵优化策略的Local Search时间组成
"""
import pandas as pd
import numpy as np
import os

script_dir = os.path.dirname(os.path.abspath(__file__))

# 数据集
datasets = ['m10_n10_sample_100', 'm20_n10_sample_100']

# 读取结果
results = {}

for dataset in datasets:
    # 路径策略结果
    path_file = f'test_result_global_topk_sqrtm_{dataset}.csv'
    matrix_file = f'test_result_global_topk_sqrtm_matrix_{dataset}.csv'
    
    if os.path.exists(os.path.join(script_dir, path_file)):
        df_path = pd.read_csv(os.path.join(script_dir, path_file))
        results[f'{dataset}_path'] = df_path
    
    if os.path.exists(os.path.join(script_dir, matrix_file)):
        df_matrix = pd.read_csv(os.path.join(script_dir, matrix_file))
        results[f'{dataset}_matrix'] = df_matrix

# 生成对比报告
print("=" * 90)
print("Local Search时间组成对比分析")
print("=" * 90)

for dataset in datasets:
    path_key = f'{dataset}_path'
    matrix_key = f'{dataset}_matrix'
    
    if path_key in results and matrix_key in results:
        df_path = results[path_key]
        df_matrix = results[matrix_key]
        
        print(f"\n{'='*90}")
        print(f"数据集: {dataset}")
        print(f"{'='*90}\n")
        
        # 计算平均值
        path_ls_time = df_path['local_search_time'].mean()
        matrix_ls_time = df_matrix['local_search_time'].mean()
        
        path_add_time = df_path['add_candidate_time'].mean()
        path_drop_time = df_path['drop_candidate_time'].mean()
        path_neighbor_gen_time = df_path['neighbor_generation_time'].mean()
        path_lp_time = df_path['lp_solve_time'].mean()
        path_iter_time = df_path['total_iteration_time'].mean()
        
        matrix_add_time = df_matrix['add_candidate_time'].mean()
        matrix_drop_time = df_matrix['drop_candidate_time'].mean()
        matrix_neighbor_gen_time = df_matrix['neighbor_generation_time'].mean()
        matrix_lp_time = df_matrix['lp_solve_time'].mean()
        matrix_iter_time = df_matrix['total_iteration_time'].mean()
        
        # 打印表格
        print("【Local Search总时间对比】")
        print(f"{'指标':<30} {'路径策略':<20} {'矩阵优化策略':<20} {'改进':<20}")
        print("-" * 90)
        print(f"{'Local Search总时间 (s)':<30} {path_ls_time:<20.6f} {matrix_ls_time:<20.6f} {(path_ls_time-matrix_ls_time):<20.6f}")
        print(f"{'改进率 (%)':<30} {'':<20} {'':<20} {((path_ls_time-matrix_ls_time)/path_ls_time*100):<20.2f}")
        
        print("\n【时间组成详细对比】")
        print(f"{'时间组成':<30} {'路径策略 (s)':<20} {'矩阵优化 (s)':<20} {'改进 (s)':<20} {'改进率 (%)':<20}")
        print("-" * 90)
        
        # Add Candidate时间
        add_improvement = path_add_time - matrix_add_time
        add_improvement_pct = (add_improvement / path_add_time * 100) if path_add_time > 0 else 0
        print(f"{'Add Candidate构建时间':<30} {path_add_time:<20.6f} {matrix_add_time:<20.6f} {add_improvement:<20.6f} {add_improvement_pct:<20.2f}")
        
        # Drop Candidate时间
        drop_improvement = path_drop_time - matrix_drop_time
        drop_improvement_pct = (drop_improvement / path_drop_time * 100) if path_drop_time > 0 else 0
        print(f"{'Drop Candidate构建时间':<30} {path_drop_time:<20.6f} {matrix_drop_time:<20.6f} {drop_improvement:<20.6f} {drop_improvement_pct:<20.2f}")
        
        # Neighbor生成时间
        neighbor_improvement = path_neighbor_gen_time - matrix_neighbor_gen_time
        neighbor_improvement_pct = (neighbor_improvement / path_neighbor_gen_time * 100) if path_neighbor_gen_time > 0 else 0
        print(f"{'Neighbor生成时间':<30} {path_neighbor_gen_time:<20.6f} {matrix_neighbor_gen_time:<20.6f} {neighbor_improvement:<20.6f} {neighbor_improvement_pct:<20.2f}")
        
        # LP求解时间
        lp_improvement = path_lp_time - matrix_lp_time
        lp_improvement_pct = (lp_improvement / path_lp_time * 100) if path_lp_time > 0 else 0
        print(f"{'LP求解总时间':<30} {path_lp_time:<20.6f} {matrix_lp_time:<20.6f} {lp_improvement:<20.6f} {lp_improvement_pct:<20.2f}")
        
        # 总迭代时间
        iter_improvement = path_iter_time - matrix_iter_time
        iter_improvement_pct = (iter_improvement / path_iter_time * 100) if path_iter_time > 0 else 0
        print(f"{'总迭代时间':<30} {path_iter_time:<20.6f} {matrix_iter_time:<20.6f} {iter_improvement:<20.6f} {iter_improvement_pct:<20.2f}")
        
        print("\n【时间占比分析（基于总迭代时间）】")
        print(f"{'时间组成':<30} {'路径策略 (%)':<20} {'矩阵优化 (%)':<20}")
        print("-" * 90)
        print(f"{'Add Candidate占比':<30} {(path_add_time/path_iter_time*100):<20.2f} {(matrix_add_time/matrix_iter_time*100):<20.2f}")
        print(f"{'Drop Candidate占比':<30} {(path_drop_time/path_iter_time*100):<20.2f} {(matrix_drop_time/matrix_iter_time*100):<20.2f}")
        print(f"{'Neighbor生成占比':<30} {(path_neighbor_gen_time/path_iter_time*100):<20.2f} {(matrix_neighbor_gen_time/matrix_iter_time*100):<20.2f}")
        print(f"{'LP求解占比':<30} {(path_lp_time/path_iter_time*100):<20.2f} {(matrix_lp_time/matrix_iter_time*100):<20.2f}")
        
        # 其他统计信息
        print("\n【其他统计信息】")
        print(f"{'指标':<30} {'路径策略':<30} {'矩阵优化策略':<30}")
        print("-" * 90)
        print(f"{'平均迭代次数':<30} {df_path['iterations'].mean():<30.2f} {df_matrix['iterations'].mean():<30.2f}")
        print(f"{'平均LP调用次数':<30} {df_path['lp_solver_calls'].mean():<30.2f} {df_matrix['lp_solver_calls'].mean():<30.2f}")
        print(f"{'平均K值':<30} {df_path['K'].mean():<30.2f} {df_matrix['K'].mean():<30.2f}")
        print(f"{'平均最大邻域数/轮':<30} {df_path['max_neighbors_per_iter'].mean():<30.2f} {df_matrix['max_neighbors_per_iter'].mean():<30.2f}")

print("\n" + "=" * 90)


