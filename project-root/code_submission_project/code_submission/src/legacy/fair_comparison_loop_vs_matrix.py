"""
公平对比: Loop版本 vs Matrix版本
- 使用相同的K值: K = ceil(sqrt(m))
- 仅对比候选生成方式的差异: 双层循环 vs 向量化矩阵操作
- 在 m10_n10, m20_n10, m30_n10 数据集上进行测试
"""

import os
import numpy as np
import time
from math import ceil, sqrt
from tqdm import tqdm

# Import functions and classes from test_FCP_LS
from test_FCP_LS import (
    EdgeScoringGCN,  # Required for model loading
    process_data,
    convert_pred_assort_to_assignment,
    assignment_to_pred_assort,
    revenue_ratio_with_optimal_bundle,
    revenue_ratio_LP,
    check_lp_feasibility_and_revenue,
    predict_initial_bundles,
    solve_initial_milp,
)


def generate_neighbor_assignments_loop(current_assignment, prob, n, m, K):
    """
    Loop版本: 使用双层循环生成候选
    """
    import time

    # Convert assignment to pred_assort matrix
    convert_start = time.time()
    current_pred_assort = assignment_to_pred_assort(current_assignment, n, m)
    convert_time = time.time() - convert_start

    neighbors = []
    timing_info = {
        'add_candidate_time': 0.0,
        'drop_candidate_time': 0.0,
        'neighbor_generation_time': 0.0,
        'convert_time': convert_time
    }

    # Step 1: Generate Add candidates (双层循环)
    add_start = time.time()
    add_candidates = []
    for k in range(m):
        for j in range(n):
            if current_pred_assort[k, j] == 0:  # Currently not selected
                score_add = prob[k, j]  # Higher probability = better candidate
                add_candidates.append((k, j, score_add))

    # Sort Add candidates by score (descending: high prob -> low prob)
    add_candidates.sort(key=lambda x: x[2], reverse=True)

    # Take top K Add candidates
    add_list = add_candidates[:K]
    timing_info['add_candidate_time'] = time.time() - add_start

    # Step 2: Generate Drop candidates (双层循环)
    drop_start = time.time()
    drop_candidates = []
    for k in range(m):
        for j in range(n):
            if current_pred_assort[k, j] == 1 and prob[k, j] >= 0.5:
                score_drop = prob[k, j]
                drop_candidates.append((k, j, score_drop))

    # Sort Drop candidates by score (ascending: low prob -> high prob)
    drop_candidates.sort(key=lambda x: x[2])

    # Take top K Drop candidates
    drop_list = drop_candidates[:K]
    timing_info['drop_candidate_time'] = time.time() - drop_start

    # Step 3: Generate neighbors in priority order
    neighbor_gen_start = time.time()
    # First: AddList (high prob -> low prob)
    for k, j, _ in add_list:
        neighbor_pred = current_pred_assort.copy()
        neighbor_pred[k, j] = 1  # Add product j to segment k
        neighbor_assignment = convert_pred_assort_to_assignment(neighbor_pred)
        neighbors.append(neighbor_assignment)

    # Second: DropList (low prob -> high prob)
    for k, j, _ in drop_list:
        neighbor_pred = current_pred_assort.copy()
        neighbor_pred[k, j] = 0  # Drop product j from segment k
        neighbor_assignment = convert_pred_assort_to_assignment(neighbor_pred)
        neighbors.append(neighbor_assignment)
    timing_info['neighbor_generation_time'] = time.time() - neighbor_gen_start

    return neighbors, timing_info


def generate_neighbor_assignments_matrix(current_assignment, prob, n, m, K):
    """
    Matrix版本: 使用向量化矩阵操作生成候选
    """
    import time

    # Convert assignment to pred_assort matrix
    convert_start = time.time()
    current_pred_assort = assignment_to_pred_assort(current_assignment, n, m)
    convert_time = time.time() - convert_start

    neighbors = []
    timing_info = {
        'add_candidate_time': 0.0,
        'drop_candidate_time': 0.0,
        'neighbor_generation_time': 0.0,
        'convert_time': convert_time
    }

    # Step 1: Generate Add candidates using matrix operations
    add_start = time.time()

    # Create mask for unselected positions
    add_mask = (current_pred_assort == 0)  # [m, n], True for unselected positions

    # Calculate scores for all candidate positions
    add_scores = prob * add_mask.astype(float)  # [m, n], selected positions become 0

    # Get indices and scores of all candidate positions
    add_indices = np.argwhere(add_mask)  # [N, 2], N is number of candidates
    add_score_values = add_scores[add_mask]  # [N], corresponding scores

    # Sort and take Top-K (descending: high prob -> low prob)
    if len(add_score_values) > 0:
        sorted_idx = np.argsort(add_score_values)[::-1]  # Descending order
        top_k_idx = sorted_idx[:K]  # Top-K indices

        # Extract Top-K (k, j, score) tuples
        add_list = [(int(add_indices[i][0]), int(add_indices[i][1]), float(add_score_values[sorted_idx[i]]))
                    for i in top_k_idx]
    else:
        add_list = []

    timing_info['add_candidate_time'] = time.time() - add_start

    # Step 2: Generate Drop candidates using matrix operations
    drop_start = time.time()

    # Create mask for selected positions with prob >= 0.5
    drop_mask = (current_pred_assort == 1) & (prob >= 0.5)  # [m, n], bool

    # Calculate scores for all candidate positions
    drop_scores = prob * drop_mask.astype(float)  # [m, n], non-qualifying positions become 0

    # Get indices and scores of all candidate positions
    drop_indices = np.argwhere(drop_mask)  # [M, 2], M is number of candidates
    drop_score_values = drop_scores[drop_mask]  # [M], corresponding scores

    # Sort and take Top-K (ascending: low prob -> high prob)
    if len(drop_score_values) > 0:
        sorted_idx = np.argsort(drop_score_values)  # Ascending order
        top_k_idx = sorted_idx[:K]  # Top-K indices

        # Extract Top-K (k, j, score) tuples
        drop_list = [(int(drop_indices[i][0]), int(drop_indices[i][1]), float(drop_score_values[sorted_idx[i]]))
                     for i in top_k_idx]
    else:
        drop_list = []

    timing_info['drop_candidate_time'] = time.time() - drop_start

    # Step 3: Generate neighbors in priority order
    neighbor_gen_start = time.time()
    # First: AddList (high prob -> low prob)
    for k, j, _ in add_list:
        neighbor_pred = current_pred_assort.copy()
        neighbor_pred[k, j] = 1  # Add product j to segment k
        neighbor_assignment = convert_pred_assort_to_assignment(neighbor_pred)
        neighbors.append(neighbor_assignment)

    # Second: DropList (low prob -> high prob)
    for k, j, _ in drop_list:
        neighbor_pred = current_pred_assort.copy()
        neighbor_pred[k, j] = 0  # Drop product j from segment k
        neighbor_assignment = convert_pred_assort_to_assignment(neighbor_pred)
        neighbors.append(neighbor_assignment)
    timing_info['neighbor_generation_time'] = time.time() - neighbor_gen_start

    return neighbors, timing_info


def local_search_with_lp(initial_pred_assort, prob, meta, max_iterations, tolerance, use_matrix=False):
    """
    Local search function - can use either Loop or Matrix candidate generation

    Args:
        use_matrix: if True, use matrix operations; if False, use loop
    """
    n, segment_num, unit_cs, ship_cs, unit_us, Ns, opt_bundles, opt_prices, opt_rev, running_time, gap, stored_cs, stored_Rs = meta
    m = segment_num

    # Calculate K = ceil(sqrt(m)) - SAME FOR BOTH VERSIONS
    K = int(ceil(sqrt(m)))

    # Choose candidate generation function
    if use_matrix:
        generate_neighbors = lambda curr_assign, p, n, m: generate_neighbor_assignments_matrix(curr_assign, p, n, m, K)
        method_name = "Matrix"
    else:
        generate_neighbors = lambda curr_assign, p, n, m: generate_neighbor_assignments_loop(curr_assign, p, n, m, K)
        method_name = "Loop"

    # Step 1: Initial MILP solve
    initial_milp_ratio, initial_milp_time, initial_assignment = revenue_ratio_with_optimal_bundle(
        n, m, unit_cs, ship_cs, unit_us, Ns, opt_rev, initial_pred_assort, stored_cs, stored_Rs)

    # Step 2: LP solve
    current_revenue, initial_lp_time = revenue_ratio_LP(n, m, unit_cs, ship_cs, unit_us, Ns, opt_rev, initial_assignment, stored_cs, stored_Rs)
    current_assignment = initial_assignment.copy()

    # Search information recording
    search_start_time = time.time()
    search_info = {
        'method': method_name,
        'initial_milp_revenue': initial_milp_ratio,
        'initial_lp_revenue': current_revenue,
        'iterations': 0,
        'improvements': 0,
        'lp_solver_calls': 1,
        'milp_solver_calls': 1,
        'total_iteration_time': 0.0,
        'K': K,
        'max_neighbors_per_iter': 2 * K,
        # Detailed timing breakdown
        'total_add_candidate_time': 0.0,
        'total_drop_candidate_time': 0.0,
        'total_neighbor_generation_time': 0.0,
        'total_lp_solve_time': 0.0,
        'initial_milp_time': initial_milp_time,
        'initial_lp_time': initial_lp_time,
    }

    # Step 3: Local Search loop
    improved = True
    iteration = 0

    while improved and iteration < max_iterations:
        improved = False
        iteration += 1
        iteration_start_time = time.time()

        # Generate neighbors using selected method
        neighbors, neighbor_timing = generate_neighbors(current_assignment, prob, n, m)

        # Accumulate candidate generation times
        search_info['total_add_candidate_time'] += neighbor_timing['add_candidate_time']
        search_info['total_drop_candidate_time'] += neighbor_timing['drop_candidate_time']
        search_info['total_neighbor_generation_time'] += neighbor_timing['neighbor_generation_time']

        # Evaluate each neighbor
        for neighbor_assignment in neighbors:
            is_feasible, neighbor_revenue, lp_time = check_lp_feasibility_and_revenue(
                neighbor_assignment, n, m, unit_cs, ship_cs, unit_us, Ns, opt_rev, stored_cs, stored_Rs)

            search_info['lp_solver_calls'] += 1
            search_info['total_lp_solve_time'] += lp_time

            if is_feasible and neighbor_revenue > current_revenue + tolerance:
                current_assignment = neighbor_assignment
                current_revenue = neighbor_revenue
                improved = True
                search_info['improvements'] += 1
                break  # Greedy strategy

        iteration_time = time.time() - iteration_start_time
        search_info['total_iteration_time'] += iteration_time

    search_info['iterations'] = iteration
    search_info['final_lp_revenue'] = current_revenue

    # Step 4: Convert optimal assignment to pred_assort
    final_pred_assort = assignment_to_pred_assort(current_assignment, n, m)

    # Step 5: Final MILP solve
    final_milp_ratio, final_milp_time = revenue_ratio_with_optimal_bundle(
        n, m, unit_cs, ship_cs, unit_us, Ns, opt_rev, final_pred_assort, stored_cs, stored_Rs)[:2]

    search_info['final_milp_revenue'] = final_milp_ratio
    search_info['final_milp_time'] = final_milp_time
    search_info['milp_solver_calls'] += 1
    search_info['total_improvement'] = final_milp_ratio - search_info['initial_milp_revenue']

    return final_pred_assort, final_milp_ratio, search_info


def evaluate_single_dataset(test_data_path, dataset_name, max_samples=100):
    """
    Evaluate both Loop and Matrix versions on a single dataset
    """
    print(f"\n{'='*80}")
    print(f"Evaluating Dataset: {dataset_name}")
    print(f"{'='*80}")

    if not os.path.exists(test_data_path):
        print(f"Dataset path does not exist: {test_data_path}")
        return None

    # Load test dataset
    print('Loading dataset...')
    dir_list = os.listdir(test_data_path)
    test_dataset = []
    miscellaneous_dataset = []

    for i in range(len(dir_list)):
        if dir_list[i] == '.DS_Store':
            continue
        file_path = os.path.join(test_data_path, dir_list[i])
        try:
            dat, miscellaneous = process_data(file_path)
            test_dataset.append(dat)
            miscellaneous_dataset.append(miscellaneous)
        except Exception as e:
            continue

    sample_num = len(test_dataset)
    print(f'Successfully loaded {sample_num} test samples.')

    if sample_num == 0:
        return None

    # Limit samples
    actual_test_count = min(sample_num, max_samples)
    test_dataset = test_dataset[:actual_test_count]
    miscellaneous_dataset = miscellaneous_dataset[:actual_test_count]

    # Results storage
    loop_results = []
    matrix_results = []

    max_iterations = 50
    tolerance = 1e-6

    for i in tqdm(range(actual_test_count), desc=f"Evaluating {dataset_name}"):
        try:
            dat = test_dataset[i]
            miscellaneous = miscellaneous_dataset[i]
            n, segment_num, unit_cs, ship_cs, unit_us, Ns, opt_bundles, opt_prices, opt_rev, running_time, gap, stored_cs, stored_Rs = miscellaneous

            # Generate initial prediction (same for both)
            initial_pred, prob = predict_initial_bundles(dat, miscellaneous)

            # ===== Test Loop Version =====
            loop_start = time.time()
            _, loop_rev, loop_info = local_search_with_lp(
                initial_pred, prob, miscellaneous, max_iterations, tolerance, use_matrix=False
            )
            loop_total_time = time.time() - loop_start

            loop_results.append({
                'sample_id': i,
                'n': n,
                'm': segment_num,
                'K': loop_info['K'],
                'revenue_ratio': loop_rev,
                'total_time': loop_total_time,
                'iterations': loop_info['iterations'],
                'lp_calls': loop_info['lp_solver_calls'],
                'add_candidate_time': loop_info['total_add_candidate_time'],
                'drop_candidate_time': loop_info['total_drop_candidate_time'],
                'neighbor_gen_time': loop_info['total_neighbor_generation_time'],
                'lp_solve_time': loop_info['total_lp_solve_time'],
                'iteration_time': loop_info['total_iteration_time'],
            })

            # ===== Test Matrix Version =====
            matrix_start = time.time()
            _, matrix_rev, matrix_info = local_search_with_lp(
                initial_pred, prob, miscellaneous, max_iterations, tolerance, use_matrix=True
            )
            matrix_total_time = time.time() - matrix_start

            matrix_results.append({
                'sample_id': i,
                'n': n,
                'm': segment_num,
                'K': matrix_info['K'],
                'revenue_ratio': matrix_rev,
                'total_time': matrix_total_time,
                'iterations': matrix_info['iterations'],
                'lp_calls': matrix_info['lp_solver_calls'],
                'add_candidate_time': matrix_info['total_add_candidate_time'],
                'drop_candidate_time': matrix_info['total_drop_candidate_time'],
                'neighbor_gen_time': matrix_info['total_neighbor_generation_time'],
                'lp_solve_time': matrix_info['total_lp_solve_time'],
                'iteration_time': matrix_info['total_iteration_time'],
            })

        except Exception as e:
            print(f"Error evaluating sample {i}: {e}")
            import traceback
            traceback.print_exc()
            continue

    return {
        'dataset_name': dataset_name,
        'loop_results': loop_results,
        'matrix_results': matrix_results,
        'sample_count': len(loop_results)
    }


def main():
    """
    Main function: fair comparison of Loop vs Matrix candidate generation
    """
    print("=" * 100)
    print("公平对比: Loop版本 vs Matrix版本 (相同K值)")
    print("K = ceil(sqrt(m)), 仅对比候选生成方式的差异")
    print("=" * 100)

    # Set paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    dataset_base_dir = os.path.join(script_dir, "Dataset")

    # Define test datasets
    datasets = {
        'm10_n10': os.path.join(dataset_base_dir, 'm10_n10_sample_100'),
        'm20_n10': os.path.join(dataset_base_dir, 'm20_n10_sample_100'),
        'm30_n10': os.path.join(dataset_base_dir, 'm30_n10_sample_100'),
    }

    # Evaluate each dataset
    all_results = []

    for dataset_name, test_data_path in datasets.items():
        result = evaluate_single_dataset(test_data_path, dataset_name, max_samples=100)
        if result is not None:
            all_results.append(result)

            # Save results to CSV
            import pandas as pd

            loop_df = pd.DataFrame(result['loop_results'])
            matrix_df = pd.DataFrame(result['matrix_results'])

            loop_df.to_csv(os.path.join(script_dir, f'fair_comparison_loop_{dataset_name}.csv'), index=False)
            matrix_df.to_csv(os.path.join(script_dir, f'fair_comparison_matrix_{dataset_name}.csv'), index=False)

    # Print comparison summary
    print("\n" + "=" * 100)
    print("公平对比结果汇总")
    print("=" * 100)

    for result in all_results:
        dataset_name = result['dataset_name']
        loop_results = result['loop_results']
        matrix_results = result['matrix_results']

        if len(loop_results) == 0:
            continue

        # Calculate averages
        def avg(lst, key):
            return np.mean([r[key] for r in lst])

        print(f"\n### {dataset_name} (K = {loop_results[0]['K']}) ###")
        print(f"样本数: {len(loop_results)}")
        print()

        # Revenue comparison
        loop_rev = avg(loop_results, 'revenue_ratio')
        matrix_rev = avg(matrix_results, 'revenue_ratio')
        print(f"Revenue Ratio:")
        print(f"  Loop:   {loop_rev:.6f}")
        print(f"  Matrix: {matrix_rev:.6f}")
        print(f"  差异:   {matrix_rev - loop_rev:+.6f}")
        print()

        # Total time comparison
        loop_time = avg(loop_results, 'total_time') * 1000
        matrix_time = avg(matrix_results, 'total_time') * 1000
        speedup = loop_time / matrix_time if matrix_time > 0 else 0
        print(f"总时间 (ms):")
        print(f"  Loop:   {loop_time:.2f}")
        print(f"  Matrix: {matrix_time:.2f}")
        print(f"  加速比: {speedup:.2f}x")
        print()

        # Candidate generation time comparison (core comparison)
        loop_add = avg(loop_results, 'add_candidate_time') * 1000
        matrix_add = avg(matrix_results, 'add_candidate_time') * 1000
        add_speedup = loop_add / matrix_add if matrix_add > 0 else 0

        loop_drop = avg(loop_results, 'drop_candidate_time') * 1000
        matrix_drop = avg(matrix_results, 'drop_candidate_time') * 1000
        drop_speedup = loop_drop / matrix_drop if matrix_drop > 0 else 0

        loop_neigh = avg(loop_results, 'neighbor_gen_time') * 1000
        matrix_neigh = avg(matrix_results, 'neighbor_gen_time') * 1000
        neigh_speedup = loop_neigh / matrix_neigh if matrix_neigh > 0 else 0

        print(f"候选构建时间 (ms):")
        print(f"  Add Candidate:")
        print(f"    Loop:   {loop_add:.4f}")
        print(f"    Matrix: {matrix_add:.4f}")
        print(f"    加速比: {add_speedup:.2f}x")
        print(f"  Drop Candidate:")
        print(f"    Loop:   {loop_drop:.4f}")
        print(f"    Matrix: {matrix_drop:.4f}")
        print(f"    加速比: {drop_speedup:.2f}x")
        print(f"  Neighbor Generation:")
        print(f"    Loop:   {loop_neigh:.4f}")
        print(f"    Matrix: {matrix_neigh:.4f}")
        print(f"    加速比: {neigh_speedup:.2f}x")
        print()

        # Total candidate time
        loop_cand_total = loop_add + loop_drop + loop_neigh
        matrix_cand_total = matrix_add + matrix_drop + matrix_neigh
        cand_speedup = loop_cand_total / matrix_cand_total if matrix_cand_total > 0 else 0

        print(f"候选构建总时间 (ms):")
        print(f"  Loop:   {loop_cand_total:.4f}")
        print(f"  Matrix: {matrix_cand_total:.4f}")
        print(f"  加速比: {cand_speedup:.2f}x")
        print()

        # LP solve time (should be similar)
        loop_lp = avg(loop_results, 'lp_solve_time') * 1000
        matrix_lp = avg(matrix_results, 'lp_solve_time') * 1000

        print(f"LP求解时间 (ms):")
        print(f"  Loop:   {loop_lp:.2f}")
        print(f"  Matrix: {matrix_lp:.2f}")
        print()

        # Iteration time
        loop_iter = avg(loop_results, 'iteration_time') * 1000
        matrix_iter = avg(matrix_results, 'iteration_time') * 1000

        print(f"迭代总时间 (ms):")
        print(f"  Loop:   {loop_iter:.2f}")
        print(f"  Matrix: {matrix_iter:.2f}")
        print()

        # Time breakdown percentage
        print(f"时间占比分析 (占迭代时间):")
        print(f"  Loop版本:")
        print(f"    候选构建: {loop_cand_total/loop_iter*100:.2f}%")
        print(f"    LP求解:   {loop_lp/loop_iter*100:.2f}%")
        print(f"  Matrix版本:")
        print(f"    候选构建: {matrix_cand_total/matrix_iter*100:.2f}%")
        print(f"    LP求解:   {matrix_lp/matrix_iter*100:.2f}%")

    print("\n" + "=" * 100)
    print("测试完成")
    print("=" * 100)


if __name__ == "__main__":
    main()
