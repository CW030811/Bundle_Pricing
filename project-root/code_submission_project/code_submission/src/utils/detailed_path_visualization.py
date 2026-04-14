"""
详细路径可视化脚本 - 展示单个样本的Local Search完整过程
"""
import os
import numpy as np
import time
import msgpack
import msgpack_numpy as mnp
import matplotlib.pyplot as plt
from math import ceil, sqrt
import sys

# 设置matplotlib支持中文
plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

# 导入必要的函数
from test_FCP_LS import (
    EdgeScoringGCN,
    process_data,
    convert_pred_assort_to_assignment,
    assignment_to_pred_assort,
    revenue_ratio_with_optimal_bundle,
    revenue_ratio_LP,
    check_lp_feasibility_and_revenue,
    predict_initial_bundles,
    solve_initial_milp,
)


def generate_neighbor_assignments_global_topk(current_assignment, prob, n, m):
    """
    Generate neighbor assignments using global Top-K strategy
    """
    current_pred_assort = assignment_to_pred_assort(current_assignment, n, m)
    K = int(ceil(sqrt(m)))
    
    neighbors = []
    neighbor_info = []  # 记录每个neighbor的信息
    
    # Step 1: Generate Add candidates
    add_candidates = []
    for k in range(m):
        for j in range(n):
            if current_pred_assort[k, j] == 0:
                score_add = prob[k, j]
                add_candidates.append((k, j, score_add))
    
    add_candidates.sort(key=lambda x: x[2], reverse=True)
    add_list = add_candidates[:K]
    
    # Step 2: Generate Drop candidates
    # Only consider products with prob >= 0.5 (consistent with Initial FCP threshold strategy)
    drop_candidates = []
    for k in range(m):
        for j in range(n):
            if current_pred_assort[k, j] == 1 and prob[k, j] >= 0.5:
                score_drop = prob[k, j]
                drop_candidates.append((k, j, score_drop))
    
    drop_candidates.sort(key=lambda x: x[2])  # Ascending: low prob -> high prob (prefer dropping low prob products)
    drop_list = drop_candidates[:K]
    
    # Step 3: Generate neighbors
    for idx, (k, j, score) in enumerate(add_list):
        neighbor_pred = current_pred_assort.copy()
        neighbor_pred[k, j] = 1
        neighbor_assignment = convert_pred_assort_to_assignment(neighbor_pred)
        neighbors.append(neighbor_assignment)
        neighbor_info.append({
            'type': 'Add',
            'segment': k,
            'product': j,
            'score': score,
            'index': idx
        })
    
    for idx, (k, j, score) in enumerate(drop_list):
        neighbor_pred = current_pred_assort.copy()
        neighbor_pred[k, j] = 0
        neighbor_assignment = convert_pred_assort_to_assignment(neighbor_pred)
        neighbors.append(neighbor_assignment)
        neighbor_info.append({
            'type': 'Drop',
            'segment': k,
            'product': j,
            'score': score,
            'index': idx + K
        })
    
    return neighbors, neighbor_info


def detailed_local_search_with_tracking(meta, initial_pred_assort, prob, max_iterations=50, tolerance=1e-6):
    """
    详细的Local Search过程，记录每一步的信息
    """
    n, segment_num, unit_cs, ship_cs, unit_us, Ns, opt_bundles, opt_prices, opt_rev, running_time, gap, stored_cs, stored_Rs = meta
    m = segment_num
    
    K = int(ceil(sqrt(m)))
    
    # 记录信息
    search_history = {
        'initial_pred_assort': initial_pred_assort.copy(),
        'initial_assignment': None,
        'initial_milp_revenue': None,
        'initial_lp_revenue': None,
        'iterations': [],
        'final_pred_assort': None,
        'final_milp_revenue': None,
        'K': K,
        'max_neighbors': 2 * K
    }
    
    print("=" * 80)
    print("详细Local Search路径追踪")
    print("=" * 80)
    print(f"数据集: m={m}, n={n}")
    print(f"K = {K}, 每轮最多生成 {2*K} 个neighbor\n")
    
    # Step 1: Initial MILP
    print("Step 1: Initial MILP求解...")
    start_time = time.time()
    initial_milp_ratio, initial_milp_time, initial_assignment = revenue_ratio_with_optimal_bundle(
        n, m, unit_cs, ship_cs, unit_us, Ns, opt_rev, initial_pred_assort, stored_cs, stored_Rs)
    milp_time = time.time() - start_time
    
    search_history['initial_assignment'] = initial_assignment
    search_history['initial_milp_revenue'] = initial_milp_ratio
    search_history['initial_milp_time'] = initial_milp_time
    
    print(f"Initial MILP结果:")
    print(f"  Revenue Ratio: {initial_milp_ratio:.6f}")
    print(f"  求解时间: {initial_milp_time:.4f}s")
    print(f"  Assignment: {initial_assignment}\n")
    
    # Step 2: Initial LP
    print("Step 2: Initial LP求解...")
    start_time = time.time()
    current_revenue, initial_lp_time = revenue_ratio_LP(n, m, unit_cs, ship_cs, unit_us, Ns, opt_rev, initial_assignment, stored_cs, stored_Rs)
    lp_time = time.time() - start_time
    
    search_history['initial_lp_revenue'] = current_revenue
    search_history['initial_lp_time'] = initial_lp_time
    
    print(f"Initial LP结果:")
    print(f"  Revenue Ratio: {current_revenue:.6f}")
    print(f"  求解时间: {initial_lp_time:.4f}s\n")
    
    current_assignment = initial_assignment.copy()
    
    # Step 3: Local Search Loop
    print("Step 3: Local Search循环 (Global Top-K策略)...")
    print("-" * 80)
    
    improved = True
    iteration = 0
    
    while improved and iteration < max_iterations:
        iteration_start_time = time.time()
        improved = False
        
        # 生成neighbors
        neighbors, neighbor_info = generate_neighbor_assignments_global_topk(current_assignment, prob, n, m)
        
        iteration_data = {
            'iteration': iteration + 1,
            'current_revenue': current_revenue,
            'neighbors': [],
            'best_neighbor': None,
            'improvement': None,
            'accepted': False,
            'iteration_time': 0.0
        }
        
        print(f"\nIteration {iteration + 1}: 评估 {len(neighbors)} 个neighbors (最多: {2*K})")
        
        # 评估每个neighbor（贪婪策略：找到第一个改进就接受）
        for idx, neighbor_assignment in enumerate(neighbors):
            neighbor_start_time = time.time()
            
            # LP可行性检查
            is_feasible, neighbor_revenue, lp_time_neighbor = check_lp_feasibility_and_revenue(
                neighbor_assignment, n, m, unit_cs, ship_cs, unit_us, Ns, opt_rev, stored_cs, stored_Rs)
            
            neighbor_time = time.time() - neighbor_start_time
            
            neighbor_data = {
                'index': idx + 1,
                'type': neighbor_info[idx]['type'],
                'segment': neighbor_info[idx]['segment'],
                'product': neighbor_info[idx]['product'],
                'score': neighbor_info[idx]['score'],
                'feasible': is_feasible,
                'revenue': neighbor_revenue if is_feasible else None,
                'time': neighbor_time
            }
            
            iteration_data['neighbors'].append(neighbor_data)
            
            # 贪婪策略：找到第一个改进就立即接受并break
            if is_feasible and neighbor_revenue > current_revenue + tolerance:
                improvement = neighbor_revenue - current_revenue
                current_revenue = neighbor_revenue
                current_assignment = neighbor_assignment
                improved = True
                
                iteration_data['best_neighbor'] = idx + 1
                iteration_data['improvement'] = improvement
                iteration_data['accepted'] = True
                iteration_data['new_revenue'] = current_revenue
                
                iteration_time = time.time() - iteration_start_time
                iteration_data['iteration_time'] = iteration_time
                
                print(f"  找到改进! Neighbor {idx + 1}/{len(neighbors)}")
                print(f"  Revenue提升: {improvement:.6f} ({improvement/current_revenue*100:.4f}%)")
                print(f"  新Revenue: {current_revenue:.6f}")
                print(f"  迭代时间: {iteration_time:.4f}s")
                break  # Greedy strategy: immediately accept improvement
        
        if not improved:
            iteration_time = time.time() - iteration_start_time
            iteration_data['iteration_time'] = iteration_time
            iteration_data['accepted'] = False
            print(f"  未找到改进")
            print(f"  迭代时间: {iteration_time:.4f}s")
        
        search_history['iterations'].append(iteration_data)
        iteration += 1
        
        if not improved:
            print(f"\n搜索收敛，在第 {iteration} 轮停止")
            break
    
    if iteration >= max_iterations:
        print(f"\n达到最大迭代次数 {max_iterations}")
    
    # Step 4: 转换为最终pred_assort
    print("\n" + "=" * 80)
    print("Step 4: 转换为最终Prediction...")
    final_pred_assort = assignment_to_pred_assort(current_assignment, n, m)
    search_history['final_pred_assort'] = final_pred_assort
    search_history['final_lp_revenue'] = current_revenue
    
    print(f"最终LP Revenue Ratio: {current_revenue:.6f}")
    
    # Step 5: 最终MILP验证
    print("\n" + "=" * 80)
    print("Step 5: 最终MILP验证...")
    start_time = time.time()
    final_milp_ratio, final_milp_time, final_milp_assignment = revenue_ratio_with_optimal_bundle(
        n, m, unit_cs, ship_cs, unit_us, Ns, opt_rev, final_pred_assort, stored_cs, stored_Rs)
    final_milp_total_time = time.time() - start_time
    
    search_history['final_milp_revenue'] = final_milp_ratio
    search_history['final_milp_time'] = final_milp_time
    
    print(f"最终MILP结果:")
    print(f"  Revenue Ratio: {final_milp_ratio:.6f}")
    print(f"  求解时间: {final_milp_time:.4f}s")
    print(f"  Total Improvement: {final_milp_ratio - initial_milp_ratio:.6f}")
    
    return search_history


def print_detailed_summary(search_history):
    """打印详细摘要"""
    print("\n" + "=" * 80)
    print("详细摘要")
    print("=" * 80)
    
    print(f"\nInitial Prediction (pred_assort):")
    initial_pred = search_history['initial_pred_assort']
    for k in range(initial_pred.shape[0]):
        bundle_str = ''.join(['1' if x else '0' for x in initial_pred[k, :]])
        print(f"  Segment {k}: {bundle_str}")
    
    print(f"\nInitial Assignment: {search_history['initial_assignment']}")
    print(f"Initial MILP Revenue: {search_history['initial_milp_revenue']:.6f}")
    print(f"Initial LP Revenue: {search_history['initial_lp_revenue']:.6f}")
    
    print(f"\nK = {search_history['K']}, 每轮最多生成 {search_history['max_neighbors']} 个neighbor")
    
    print(f"\nLocal Search过程:")
    for iter_data in search_history['iterations']:
        print(f"\n  Iteration {iter_data['iteration']}:")
        print(f"    当前Revenue: {iter_data['current_revenue']:.6f}")
        print(f"    评估Neighbors: {len(iter_data['neighbors'])}")
        for nb in iter_data['neighbors']:
            if nb['feasible']:
                print(f"      Neighbor {nb['index']} ({nb['type']}): Seg{nb['segment']}, Prod{nb['product']}, "
                      f"Score={nb['score']:.4f}, Revenue={nb['revenue']:.6f}, Time={nb['time']:.4f}s")
            else:
                print(f"      Neighbor {nb['index']} ({nb['type']}): Seg{nb['segment']}, Prod{nb['product']}, "
                      f"Score={nb['score']:.4f}, Infeasible, Time={nb['time']:.4f}s")
        
        if iter_data['accepted']:
            print(f"    ✓ 接受改进: Neighbor {iter_data['best_neighbor']}, "
                  f"Improvement={iter_data['improvement']:.6f}, "
                  f"New Revenue={iter_data['new_revenue']:.6f}")
        else:
            print(f"    ✗ 未找到改进")
        print(f"    迭代时间: {iter_data['iteration_time']:.4f}s")
    
    print(f"\n最终Prediction (pred_assort):")
    final_pred = search_history['final_pred_assort']
    for k in range(final_pred.shape[0]):
        bundle_str = ''.join(['1' if x else '0' for x in final_pred[k, :]])
        print(f"  Segment {k}: {bundle_str}")
    
    print(f"\n最终LP Revenue: {search_history['final_lp_revenue']:.6f}")
    print(f"最终MILP Revenue: {search_history['final_milp_revenue']:.6f}")
    print(f"Total Improvement: {search_history['final_milp_revenue'] - search_history['initial_milp_revenue']:.6f}")


def plot_search_path(search_history, output_path='search_path_visualization.png'):
    """绘制Local Search路径示意图"""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))
    
    # 提取数据
    iterations = [0] + [iter_data['iteration'] for iter_data in search_history['iterations']]
    revenues = [search_history['initial_lp_revenue']] + [
        iter_data['new_revenue'] if iter_data['accepted'] else iter_data['current_revenue']
        for iter_data in search_history['iterations']
    ]
    times = [0.0] + [iter_data['iteration_time'] for iter_data in search_history['iterations']]
    cumulative_times = np.cumsum([search_history['initial_milp_time'] + search_history['initial_lp_time']] + times[1:])
    
    # 子图1: Revenue变化路径
    ax1.plot(iterations, revenues, 'o-', linewidth=2, markersize=8, label='LP Revenue')
    ax1.axhline(y=search_history['initial_milp_revenue'], color='r', linestyle='--', 
                linewidth=1.5, label='Initial MILP Revenue')
    ax1.axhline(y=search_history['final_milp_revenue'], color='g', linestyle='--', 
                linewidth=1.5, label='Final MILP Revenue')
    
    # 标记改进点
    for i, iter_data in enumerate(search_history['iterations']):
        if iter_data['accepted']:
            ax1.plot(iter_data['iteration'], iter_data['new_revenue'], 'go', markersize=10)
    
    ax1.set_xlabel('Iteration', fontsize=12)
    ax1.set_ylabel('Revenue Ratio', fontsize=12)
    ax1.set_title('Local Search Revenue Path', fontsize=14, fontweight='bold')
    ax1.legend(fontsize=10)
    ax1.grid(True, alpha=0.3)
    
    # 子图2: 时间累积
    ax2.bar(iterations, times, alpha=0.6, color='skyblue', label='Iteration Time')
    ax2.plot(iterations, cumulative_times, 'o-', color='orange', linewidth=2, 
             markersize=6, label='Cumulative Time')
    
    ax2.set_xlabel('Iteration', fontsize=12)
    ax2.set_ylabel('Time (seconds)', fontsize=12)
    ax2.set_title('Time Consumption', fontsize=14, fontweight='bold')
    ax2.legend(fontsize=10)
    ax2.grid(True, alpha=0.3, axis='y')
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"\n可视化图表已保存: {output_path}")
    plt.close()


def main():
    """主函数"""
    # 设置路径
    script_dir = os.path.dirname(os.path.abspath(__file__))
    dataset_path = os.path.join(script_dir, "Dataset", "m10_n10_sample_100")
    
    # 加载第一个样本
    files = [f for f in os.listdir(dataset_path) if f.endswith('.msgpack')]
    if not files:
        print("未找到数据文件")
        return
    
    sample_file = os.path.join(dataset_path, files[0])
    print(f"加载样本: {files[0]}\n")
    
    # 使用process_data直接读取文件
    dat, miscellaneous = process_data(sample_file)
    n, segment_num, unit_cs, ship_cs, unit_us, Ns, opt_bundles, opt_prices, opt_rev, running_time, gap, stored_cs, stored_Rs = miscellaneous
    m = segment_num
    meta = miscellaneous
    
    # 加载模型并生成初始预测
    # 尝试多个可能的模型路径
    possible_model_paths = [
        os.path.join(script_dir, "best_model_edge.pt"),
        os.path.join(script_dir, "model", "edge_scoring_gcn.pth"),
        os.path.join(script_dir, "model", "best_model_edge.pt"),
    ]
    model_path = None
    for path in possible_model_paths:
        if os.path.exists(path):
            model_path = path
            break
    
    if model_path is None:
        print(f"模型文件不存在，尝试的路径: {possible_model_paths}")
        return
    
    print("加载GCN模型并生成初始预测...")
    initial_pred_assort, prob = predict_initial_bundles(dat, meta)
    
    # 执行详细Local Search
    search_history = detailed_local_search_with_tracking(
        meta, initial_pred_assort, prob, max_iterations=50, tolerance=1e-6)
    
    # 打印详细摘要
    print_detailed_summary(search_history)
    
    # 绘制可视化图表
    output_path = os.path.join(script_dir, 'search_path_visualization.png')
    plot_search_path(search_history, output_path)
    
    print("\n" + "=" * 80)
    print("完成!")
    print("=" * 80)


if __name__ == '__main__':
    # 设置UTF-8编码
    if sys.platform == 'win32':
        sys.stdout.reconfigure(encoding='utf-8')
    main()

