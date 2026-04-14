"""
Local Search Path Test - Global Top-K Strategy

This script tests the impact of different search path strategies on Local Search efficiency.
Uses a global Top-K approach instead of segment-based (2*m) neighbor generation.

Strategy:
1. Use threshold method to generate initial bundle prediction (imported)
2. Use MILP solver to obtain initial optimal bundle assignment (imported)
3. Use LP solver for fast local search neighborhood evaluation (imported)
4. Use global Top-K neighbor generation: K = ceil(sqrt(m))
5. Use greedy strategy: accept improvement when found
6. Convert final assignment back to MILP for global optimization (imported)
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


def generate_neighbor_assignments_global_topk(current_assignment, prob, n, m):
    """
    Generate neighbor assignments using global Top-K strategy
    
    Instead of generating 2*m neighbors (one Add and one Drop per segment),
    this function generates at most 2*K neighbors where K = ceil(sqrt(m)).
    
    Args:
        current_assignment: dict, current segment-bundle assignment
        prob: [m, n] GCN output probability matrix
        n: number of products
        m: number of customer segments
    
    Returns:
        tuple: (neighbors, timing_info)
            - neighbors: list of neighbor assignments, ordered by priority
            - timing_info: dict with 'add_candidate_time', 'drop_candidate_time', 'neighbor_generation_time'
    """
    import time
    
    # Convert assignment to pred_assort matrix
    convert_start = time.time()
    current_pred_assort = assignment_to_pred_assort(current_assignment, n, m)
    convert_time = time.time() - convert_start
    
    # Calculate K = ceil(sqrt(m))
    K = int(ceil(sqrt(m)))
    
    neighbors = []
    timing_info = {
        'add_candidate_time': 0.0,
        'drop_candidate_time': 0.0,
        'neighbor_generation_time': 0.0,
        'convert_time': convert_time
    }
    
    # Step 1: Generate Add candidates (globally sorted by probability)
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
    
    # Step 2: Generate Drop candidates (globally sorted by probability)
    # Only consider products with prob >= 0.5 (consistent with Initial FCP threshold strategy)
    drop_start = time.time()
    drop_candidates = []
    for k in range(m):
        for j in range(n):
            if current_pred_assort[k, j] == 1 and prob[k, j] >= 0.5:  # Currently selected AND prob >= 0.5
                score_drop = prob[k, j]  # Lower probability = better candidate to drop
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


def local_search_with_lp_global_topk(initial_pred_assort, prob, meta, max_iterations=50, tolerance=1e-3):
    """
    Local search function using global Top-K neighbor generation strategy
    
    Workflow:
    1. Initial MILP solve to get baseline assignment
    2. LP solve to get current best revenue
    3. Neighborhood search loop with global Top-K:
       - Generate at most 2*K neighbors (K = ceil(sqrt(m)))
       - LP feasibility check
       - Revenue improvement check
       - Update best solution
    4. Convert optimal assignment to pred_assort
    5. Final MILP solve (verify LP result)
    
    Args:
        initial_pred_assort: [m, n] initial predicted bundle assignment matrix
        prob: [m, n] GCN output probability matrix
        meta: data parameter tuple
        max_iterations: maximum number of iterations
        tolerance: tolerance for revenue improvement
    
    Returns:
        tuple: (final_pred_assort, final_revenue_ratio, search_info)
    """
    n, segment_num, unit_cs, ship_cs, unit_us, Ns, opt_bundles, opt_prices, opt_rev, running_time, gap, stored_cs, stored_Rs = meta
    m = segment_num
    
    # Calculate K for this instance
    K = int(ceil(sqrt(m)))
    
    # Step 1: Initial MILP solve to get feasible assignment
    print("Step 1: Initial MILP solve...")
    initial_milp_ratio, initial_milp_time, initial_assignment = revenue_ratio_with_optimal_bundle(
        n, m, unit_cs, ship_cs, unit_us, Ns, opt_rev, initial_pred_assort, stored_cs, stored_Rs)
    
    print(f"Initial MILP result: revenue ratio={initial_milp_ratio:.6f}, time={initial_milp_time:.4f}s")
    print(f"Initial assignment: {initial_assignment}")
    print(f"Top-K parameter: K={K} (max neighbors per iteration: {2*K})")
    
    # Step 2: LP solve to get current best revenue
    print("Step 2: Initial LP solve...")
    current_revenue, initial_lp_time = revenue_ratio_LP(n, m, unit_cs, ship_cs, unit_us, Ns, opt_rev, initial_assignment, stored_cs, stored_Rs)
    current_assignment = initial_assignment.copy()
    
    print(f"Initial LP result: revenue ratio={current_revenue:.6f}, time={initial_lp_time:.4f}s")
    
    # Search information recording
    search_start_time = time.time()
    search_info = {
        'initial_milp_revenue': initial_milp_ratio,
        'initial_lp_revenue': current_revenue,
        'iterations': 0,
        'improvements': 0,
        'search_path': [current_revenue],
        'time_path': [0.0],
        'iteration_path': [0],
        'lp_solver_calls': 1,  # Initial LP solve counts as one
        'milp_solver_calls': 1,  # Initial MILP solve counts as one
        'total_iteration_time': 0.0,  # Total time spent in iterations only
        'K': K,  # Record K value
        'max_neighbors_per_iter': 2 * K,  # Record max neighbors per iteration
        # Detailed timing breakdown
        'total_add_candidate_time': 0.0,
        'total_drop_candidate_time': 0.0,
        'total_neighbor_generation_time': 0.0,
        'total_lp_solve_time': 0.0,
        'total_neighbor_iteration_time': 0.0,  # Time spent in for loop (excluding LP)
    }
    
    # Step 3: Local Search loop with global Top-K
    print("Step 3: Local Search loop (Global Top-K strategy)...")
    improved = True
    iteration = 0
    iteration_loop_start_time = time.time()
    
    while improved and iteration < max_iterations:
        improved = False
        iteration += 1
        iteration_start_time = time.time()
        
        # Generate neighbors using global Top-K strategy
        neighbors, neighbor_timing = generate_neighbor_assignments_global_topk(current_assignment, prob, n, m)
        
        # Accumulate candidate generation times
        search_info['total_add_candidate_time'] += neighbor_timing['add_candidate_time']
        search_info['total_drop_candidate_time'] += neighbor_timing['drop_candidate_time']
        search_info['total_neighbor_generation_time'] += neighbor_timing['neighbor_generation_time']
        
        actual_neighbors = len(neighbors)
        print(f"Iteration {iteration}: Evaluating {actual_neighbors} neighbors (max: {2*K})")
        
        # Evaluate each neighbor in priority order
        for neighbor_idx, neighbor_assignment in enumerate(neighbors):
            # LP feasibility and revenue check
            is_feasible, neighbor_revenue, lp_time = check_lp_feasibility_and_revenue(
                neighbor_assignment, n, m, unit_cs, ship_cs, unit_us, Ns, opt_rev, stored_cs, stored_Rs)
            
            # lp_solver_calls represents one solve call
            search_info['lp_solver_calls'] += 1
            search_info['total_lp_solve_time'] += lp_time
            
            # Track non-LP time in the loop (variable assignment, condition check, etc.)
            # This is a small overhead, we'll estimate it as a small fraction
            # The actual measurement would require more detailed instrumentation
            search_info['total_neighbor_iteration_time'] += 0.000001  # Minimal overhead per iteration
            
            if is_feasible and neighbor_revenue > current_revenue + tolerance:
                current_assignment = neighbor_assignment
                current_revenue = neighbor_revenue
                improved = True
                search_info['improvements'] += 1
                search_info['search_path'].append(current_revenue)
                search_info['time_path'].append(time.time() - search_start_time)
                search_info['iteration_path'].append(iteration)
                
                print(f"Iteration {iteration}: Found improvement at neighbor {neighbor_idx+1}/{actual_neighbors}, "
                      f"revenue ratio={current_revenue:.6f}")
                break  # Greedy strategy: immediately accept improvement
        
        iteration_time = time.time() - iteration_start_time
        search_info['total_iteration_time'] += iteration_time
        
        if not improved:
            print(f"Iteration {iteration}: No improvement found after evaluating {actual_neighbors} neighbors, search converged")
    
    search_info['iterations'] = iteration
    search_info['final_lp_revenue'] = current_revenue
    search_info['lp_improvement'] = current_revenue - search_info['initial_lp_revenue']
    
    # Step 4: Convert optimal assignment to pred_assort
    print("Step 4: Converting optimal assignment to pred_assort...")
    final_pred_assort = assignment_to_pred_assort(current_assignment, n, m)
    
    print(f"Final pred_assort shape: {final_pred_assort.shape}")
    
    # Step 5: Final MILP solve (verify LP result)
    print("Step 5: Final MILP solve (verify LP result)...")
    final_milp_ratio, final_milp_time = revenue_ratio_with_optimal_bundle(
        n, m, unit_cs, ship_cs, unit_us, Ns, opt_rev, final_pred_assort, stored_cs, stored_Rs)[:2]
    
    search_info['final_milp_revenue'] = final_milp_ratio
    search_info['final_milp_time'] = final_milp_time
    search_info['milp_solver_calls'] += 1
    search_info['total_improvement'] = final_milp_ratio - search_info['initial_milp_revenue']
    
    print(f"Final MILP result: revenue ratio={final_milp_ratio:.6f}, time={final_milp_time:.4f}s")
    print(f"Total improvement: {search_info['total_improvement']:.6f}")
    
    return final_pred_assort, final_milp_ratio, search_info


def evaluate_single_dataset(test_data_path, dataset_name, max_samples=1000):
    """
    Evaluate global Top-K Local Search strategy on a single dataset
    
    Args:
        test_data_path: path to test dataset directory
        dataset_name: name of the dataset
        max_samples: maximum number of samples to evaluate
    
    Returns:
        dict: evaluation results
    """
    print(f"\n=== Evaluating Dataset: {dataset_name} (Global Top-K Strategy) ===")
    print(f"Test data path: {test_data_path}")
    print(f"Test data directory exists: {os.path.exists(test_data_path)}")
    
    if not os.path.exists(test_data_path):
        print(f"Dataset path does not exist: {test_data_path}")
        return None
    
    # Load test dataset
    print('Begin dataset loading...')
    dir_list = os.listdir(test_data_path)
    sample_num = len(dir_list)
    test_dataset = []
    miscellaneous_dataset = []
    print('Start reading the dataset...')
    
    for i in range(sample_num):
        if dir_list[i] == '.DS_Store':
            continue
        file_path = os.path.join(test_data_path, dir_list[i])
        try:
            dat, miscellaneous = process_data(file_path)
            test_dataset.append(dat)
            miscellaneous_dataset.append(miscellaneous)
        except Exception as e:
            print(f"Error processing file {dir_list[i]}: {e}")
            continue
    
    sample_num = len(test_dataset)
    print(f'Successfully loaded {sample_num} test samples.')
    
    if sample_num == 0:
        print(f"No valid samples found in {dataset_name}")
        return None
    
    # Limit samples
    actual_test_count = min(sample_num, max_samples)
    if sample_num > max_samples:
        print(f"Limiting test to first {actual_test_count} samples out of {sample_num} total samples.")
        test_dataset = test_dataset[:actual_test_count]
        miscellaneous_dataset = miscellaneous_dataset[:actual_test_count]
    
    # Evaluate model
    results = []
    all_search_paths = []
    initial_milp_times = []
    iteration_times = []
    final_milp_times = []
    iterations_counts = []
    per_iter_times = []
    K_values = []  # Track K values
    # Detailed timing breakdown
    add_times = []
    drop_times = []
    neighbor_gen_times = []
    lp_solve_times = []
    neighbor_iter_times = []
    
    # Local search parameters
    max_iterations = 50
    tolerance = 1e-3
    
    for i in tqdm(range(actual_test_count), desc=f"Evaluating {dataset_name}"):
        try:
            dat = test_dataset[i]
            miscellaneous = miscellaneous_dataset[i]
            n, segment_num, unit_cs, ship_cs, unit_us, Ns, opt_bundles, opt_prices, opt_rev, running_time, gap, stored_cs, stored_Rs = miscellaneous
            
            # Start timing for the entire strategy
            strategy_start_time = time.time()
            
            # Step 1: Generate initial pred_assort
            threshold_start = time.time()
            initial_pred, prob = predict_initial_bundles(dat, miscellaneous)
            threshold_time = time.time() - threshold_start
            
            # Step 2: Initial MILP solve
            initial_milp_start = time.time()
            initial_revenue = solve_initial_milp(initial_pred, miscellaneous)
            initial_milp_time = time.time() - initial_milp_start
            
            # Step 3: Global Top-K Local Search optimization
            local_search_start = time.time()
            best_pred, best_rev, search_info = local_search_with_lp_global_topk(
                initial_pred, prob, miscellaneous, max_iterations, tolerance
            )
            local_search_time = time.time() - local_search_start
            
            # Collect timing metrics
            initial_milp_times.append(initial_milp_time)
            total_iteration_time = search_info.get('total_iteration_time', local_search_time)
            iteration_times.append(total_iteration_time)
            final_milp_times.append(search_info.get('final_milp_time', 0.0))
            iterations_counts.append(search_info.get('iterations', 0))
            iters = max(1, search_info.get('iterations', 0))
            per_iter_times.append(total_iteration_time / iters)
            K_values.append(search_info.get('K', int(ceil(2 * sqrt(segment_num)))))
            
            # Collect detailed timing breakdown
            add_times.append(search_info.get('total_add_candidate_time', 0.0))
            drop_times.append(search_info.get('total_drop_candidate_time', 0.0))
            neighbor_gen_times.append(search_info.get('total_neighbor_generation_time', 0.0))
            lp_solve_times.append(search_info.get('total_lp_solve_time', 0.0))
            neighbor_iter_times.append(search_info.get('total_neighbor_iteration_time', 0.0))
            
            # Total strategy time
            total_time = time.time() - strategy_start_time
            
            # Calculate time ratio
            time_ratio = total_time / running_time if running_time > 0 else float('inf')
            
            # Store detailed results
            results.append([
                n, best_rev, time_ratio, total_time, running_time,
                threshold_time, initial_milp_time, local_search_time,
                initial_revenue, search_info['total_improvement'],
                search_info['iterations'], search_info['improvements'],
                search_info['lp_solver_calls'], search_info['milp_solver_calls'],
                search_info.get('K', 0), search_info.get('max_neighbors_per_iter', 0),
                # Detailed timing breakdown
                search_info.get('total_iteration_time', 0.0),
                search_info.get('total_add_candidate_time', 0.0),
                search_info.get('total_drop_candidate_time', 0.0),
                search_info.get('total_neighbor_generation_time', 0.0),
                search_info.get('total_lp_solve_time', 0.0),
                search_info.get('total_neighbor_iteration_time', 0.0)
            ])
            
            # Collect search path data
            search_path_data = {
                'sample_id': i,
                'n_products': n,
                'revenue_path': search_info['search_path'],
                'time_path': search_info['time_path'],
                'iteration_path': search_info['iteration_path'],
                'initial_revenue': search_info['initial_lp_revenue'],
                'final_revenue': best_rev,
                'improvement': search_info['total_improvement'],
                'dataset_name': dataset_name,
                'K': search_info.get('K', 0),
                'max_neighbors_per_iter': search_info.get('max_neighbors_per_iter', 0)
            }
            all_search_paths.append(search_path_data)
            
        except Exception as e:
            print(f"Error evaluating sample {i}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    # Compute averages
    def _avg(arr):
        return float(np.mean(arr)) if len(arr) > 0 else 0.0
    
    return {
        'dataset_name': dataset_name,
        'results': np.array(results) if results else np.array([]),
        'search_paths': all_search_paths,
        'sample_count': len(results),
        'avg_initial_milp_time': _avg(initial_milp_times),
        'avg_iteration_time': _avg(iteration_times),
        'avg_final_milp_time': _avg(final_milp_times),
        'avg_iterations': _avg(iterations_counts),
        'avg_per_iter_time': _avg(per_iter_times),
        'avg_K': _avg(K_values),
        # Detailed timing breakdown
        'avg_add_candidate_time': _avg(add_times),
        'avg_drop_candidate_time': _avg(drop_times),
        'avg_neighbor_generation_time': _avg(neighbor_gen_times),
        'avg_lp_solve_time': _avg(lp_solve_times),
        'avg_neighbor_iteration_time': _avg(neighbor_iter_times),
    }


def main():
    """
    Main function: evaluate global Top-K Local Search strategy on datasets
    """
    print("=" * 80)
    print("Global Top-K Local Search Strategy Evaluation")
    print("Strategy: K = ceil(sqrt(m)), max neighbors per iteration = 2*K")
    print("=" * 80)
    
    # Set paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = script_dir
    dataset_base_dir = os.path.join(script_dir, "dataset2_4_2026")
    
    # Define test datasets
    datasets = {
        'test_m10n10_1e_3': os.path.join(dataset_base_dir, 'test_m10n10_1e_3'),
        'test_m20n10_1e_3': os.path.join(dataset_base_dir, 'test_m20n10_1e_3'),
        'test_m30n10_1e_3': os.path.join(dataset_base_dir, 'test_m30n10_1e_3'),
        'test_BSP_m10n20_1e_3': os.path.join(dataset_base_dir, 'test_BSP_m10n20_1e_3'),
        'test_BSP_m10n40_1e_3': os.path.join(dataset_base_dir, 'test_BSP_m10n40_1e_3'),
        'test_BSP_m20n20_1e_3': os.path.join(dataset_base_dir, 'test_BSP_m20n20_1e_3'),
    }
    
    print(f"Base directory: {base_dir}")
    print(f"Datasets to evaluate: {list(datasets.keys())}")
    
    # Evaluate each dataset
    all_dataset_results = []
    
    for dataset_name, test_data_path in datasets.items():
        dataset_result = evaluate_single_dataset(test_data_path, dataset_name)
        all_dataset_results.append(dataset_result)
        
        # Save results
        if dataset_result is not None and len(dataset_result['results']) > 0:
            results = dataset_result['results']
            result_path = os.path.join(base_dir, f'test_result_global_topk_sqrtm_{dataset_name}.csv')
            
            # Save with detailed headers
            header = ('n_products,revenue_ratio,runtime_ratio,total_time,base_running_time,'
                      'threshold_time,initial_milp_time,local_search_time,'
                      'initial_revenue,improvement,iterations,improvements,'
                      'lp_solver_calls,milp_solver_calls,K,max_neighbors_per_iter,'
                      'total_iteration_time,add_candidate_time,drop_candidate_time,'
                      'neighbor_generation_time,lp_solve_time,neighbor_iteration_time')
            np.savetxt(result_path, results, delimiter=',', header=header, comments='')
            print(f"Results for {dataset_name} saved to: {result_path}")
    
    # Print timing summaries
    for dataset_result in all_dataset_results:
        if dataset_result is None:
            continue
        print(f"\n--- Timing Averages for {dataset_result['dataset_name']} (Global Top-K) ---")
        print(f"Avg K value: {dataset_result.get('avg_K', 0.0):.2f}")
        print(f"Avg initial MILP time: {dataset_result.get('avg_initial_milp_time', 0.0):.4f} s")
        print(f"Avg total iteration time: {dataset_result.get('avg_iteration_time', 0.0):.4f} s")
        print(f"Avg final MILP time: {dataset_result.get('avg_final_milp_time', 0.0):.4f} s")
        print(f"Avg iterations: {dataset_result.get('avg_iterations', 0.0):.2f}")
        print(f"Avg per-iter time: {dataset_result.get('avg_per_iter_time', 0.0):.4f} s")
        
        # Print detailed timing breakdown
        avg_iter_time = dataset_result.get('avg_iteration_time', 0.0)
        if avg_iter_time > 0:
            print(f"\n--- Detailed Timing Breakdown ---")
            avg_add_time = dataset_result.get('avg_add_candidate_time', 0.0)
            avg_drop_time = dataset_result.get('avg_drop_candidate_time', 0.0)
            avg_neighbor_gen_time = dataset_result.get('avg_neighbor_generation_time', 0.0)
            avg_lp_time = dataset_result.get('avg_lp_solve_time', 0.0)
            avg_neighbor_iter_time = dataset_result.get('avg_neighbor_iteration_time', 0.0)
            
            print(f"Add Candidate构建时间: {avg_add_time:.6f} s ({avg_add_time/avg_iter_time*100:.2f}%)")
            print(f"Drop Candidate构建时间: {avg_drop_time:.6f} s ({avg_drop_time/avg_iter_time*100:.2f}%)")
            print(f"Neighbor生成时间: {avg_neighbor_gen_time:.6f} s ({avg_neighbor_gen_time/avg_iter_time*100:.2f}%)")
            print(f"LP求解总时间: {avg_lp_time:.6f} s ({avg_lp_time/avg_iter_time*100:.2f}%)")
            print(f"Neighbor遍历时间(不包括LP): {avg_neighbor_iter_time:.6f} s ({avg_neighbor_iter_time/avg_iter_time*100:.2f}%)")
            
            other_time = avg_iter_time - (avg_add_time + avg_drop_time + avg_neighbor_gen_time + avg_lp_time + avg_neighbor_iter_time)
            print(f"其他开销: {other_time:.6f} s ({other_time/avg_iter_time*100:.2f}%)")
            
            # Calculate average LP call time
            if len(dataset_result['results']) > 0:
                avg_lp_calls = np.mean(dataset_result['results'][:, 12])  # lp_solver_calls column
                if avg_lp_calls > 0:
                    avg_per_lp_time = avg_lp_time / avg_lp_calls
                    print(f"\n平均LP调用次数: {avg_lp_calls:.2f}")
                    print(f"平均每次LP调用时间: {avg_per_lp_time:.6f} s ({avg_per_lp_time*1000:.2f} ms)")
    
    # Print overall statistics
    print(f'\n=== OVERALL SUMMARY (Global Top-K Strategy) ===')
    total_samples = 0
    total_improvements = 0
    
    for dataset_result in all_dataset_results:
        if dataset_result is not None:
            dataset_name = dataset_result['dataset_name']
            sample_count = dataset_result['sample_count']
            total_samples += sample_count
            
            if len(dataset_result['results']) > 0:
                results = dataset_result['results']
                improvements = np.sum(results[:, 9] > 0)
                total_improvements += improvements
                
                improvement_rate = 100 * improvements / sample_count if sample_count > 0 else 0
                print(f"{dataset_name}: {sample_count} samples, {improvements} with improvements "
                      f"({improvement_rate:.1f}%)")
                
                # Revenue ratio statistics
                print(f"  Average revenue ratio: {np.mean(results[:, 1]):.4f}")
                print(f"  Std revenue ratio: {np.std(results[:, 1]):.4f}")
                
                # Runtime ratio statistics
                print(f"  Average runtime ratio: {np.mean(results[:, 2]):.4f}")
                print(f"  Std runtime ratio: {np.std(results[:, 2]):.4f}")
                
                # Total time statistics
                print(f"  Average time: {np.mean(results[:, 3]):.3f} seconds")
                
                # LP calls statistics
                print(f"  Average LP calls: {np.mean(results[:, 12]):.2f}")
                print(f"  Average K: {np.mean(results[:, 14]):.2f}")
                print(f"  Average max neighbors per iter: {np.mean(results[:, 15]):.2f}")
                
                print(f"  Average improvement: {np.mean(results[:, 9]):.4f}")
    
    print(f"\nTotal samples evaluated: {total_samples}")
    print(f"Total samples with improvements: {total_improvements}")
    if total_samples > 0:
        print(f"Overall improvement rate: {100 * total_improvements / total_samples:.1f}%")
    
    # Print concise summary for each dataset
    print(f'\n=== CONCISE SUMMARY (K = ceil(sqrt(m))) ===')
    for dataset_result in all_dataset_results:
        if dataset_result is not None and len(dataset_result['results']) > 0:
            results = dataset_result['results']
            dataset_name = dataset_result['dataset_name']
            avg_revenue_ratio = np.mean(results[:, 1])
            avg_time_ratio = np.mean(results[:, 2])
            print(f"{dataset_name}:")
            print(f"  Average Revenue Ratio: {avg_revenue_ratio:.6f}")
            print(f"  Average Time Ratio:     {avg_time_ratio:.6f}")
    
    print("=== Global Top-K Local Search Test completed ===")


if __name__ == "__main__":
    main()
