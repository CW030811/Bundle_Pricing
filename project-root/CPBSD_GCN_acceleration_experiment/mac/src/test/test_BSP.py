import numpy as np
import msgpack
import msgpack_numpy as mnp
import os
import time
from tqdm import tqdm
import gurobipy as gp
from gurobipy import GRB
from itertools import combinations

bin2num = lambda x: int(''.join(map(str, x.tolist())), 2)


def process_data(file_path):
    """
    Load and process data from a msgpack file
    """
    with open(file_path, 'rb') as f:
        data = msgpack.load(f, object_hook=mnp.decode, strict_map_key=False)
    
    product_num = data['product_num']
    segment_num = data['segment_num']
    unit_cs = data['unit_cs']
    ship_cs = data['ship_cs']
    unit_us = data['unit_us']
    cs = data['cs']          # costs for all possible bundles (m, 2^n)
    Rs = data['Rs']          # reservation prices for all possible bundles (m, 2^n)
    Ns = data['Ns']          # segment sizes (m, 1)
    opt_bundles = data['opt_bundles']
    opt_prices = data['opt_prices']
    opt_rev = data['opt_rev']
    running_time = data['running_time']
    gap = data['gap']
    
    # Calculate the index of the full bundle (all products = 1)
    full_bundle_idx = 2**product_num - 1  # binary 111...1 = 2^n - 1
    
    # Extract costs and reservation prices for the full bundle
    full_bundle_costs = cs[:, full_bundle_idx:full_bundle_idx+1]  # (m, 1)
    full_bundle_Rs = Rs[:, full_bundle_idx:full_bundle_idx+1]     # (m, 1)
    
    return {
        'product_num': product_num,
        'segment_num': segment_num,
        'unit_cs': unit_cs,
        'ship_cs': ship_cs,
        'unit_us': unit_us,
        'cs': cs,
        'Rs': Rs,
        'Ns': Ns,
        'full_bundle_costs': full_bundle_costs,
        'full_bundle_Rs': full_bundle_Rs,
        'opt_bundles': opt_bundles,
        'opt_prices': opt_prices,
        'opt_rev': opt_rev,
        'running_time': running_time,
        'gap': gap,
        'full_bundle_idx': full_bundle_idx
    }


def solve_bsp_for_evaluation(n, m, costs, Rs, Ns):
    """
    BSP solver using size-based variables for evaluation.
    """
    segment_ind = range(m)
    bundle_ind = range(2**n)
    
    # Generate all possible assortments
    assortments = np.array([list(map(int, format(num, '0' + str(n) + 'b'))) for num in range(2**n)], dtype=int)
    bundle_sizes = np.sum(assortments, axis=1)
    max_size = int(np.max(bundle_sizes))
    size_indices = range(max_size + 1)
    
    # For each size, compute maximum valuation and corresponding cost for each customer
    v_ks = np.zeros((m, max_size + 1))  # customer k's max valuation for size s
    c_ks = np.zeros((m, max_size + 1))  # cost for customer k to get size s
    
    for s in range(max_size + 1):
        # Find all bundles of size s
        size_s_bundles = [i for i in bundle_ind if bundle_sizes[i] == s]
        
        if len(size_s_bundles) > 0:
            for k in segment_ind:
                # Find the bundle with maximum valuation for customer k among all bundles of size s
                best_bundle_idx = max(size_s_bundles, key=lambda i: Rs[k, i])
                # Use the valuation and cost of the same best bundle
                v_ks[k, s] = Rs[k, best_bundle_idx]
                c_ks[k, s] = costs[k, best_bundle_idx]
    
    Rbar = np.max(Rs)

    model = gp.Model("BSP Evaluation")
    model.setParam("OutputFlag", 0)
    model.setParam("MIPGap", 1e-2)
    model.Params.TimeLimit = 600

    # Variables:
    # p[s] = price for bundles of size s
    p = model.addVars(max_size + 1, vtype=GRB.CONTINUOUS, lb=0, name="p")
    # theta[k,s] = 1 if customer k purchases a bundle of size s, 0 otherwise  
    theta = model.addVars(m, max_size + 1, vtype=GRB.BINARY, name="theta")
    # P[k,s] = price paid by customer k for bundle of size s
    P = model.addVars(m, max_size + 1, vtype=GRB.CONTINUOUS, lb=0, name="P")
    # S[k,s] = surplus of customer k from bundle of size s
    S = model.addVars(m, max_size + 1, vtype=GRB.CONTINUOUS, lb=0, name="S")
    # Z[k,s] = profit from customer k choosing bundle of size s
    Z = model.addVars(m, max_size + 1, vtype=GRB.CONTINUOUS, name="Z")
    # surplus[k] = total surplus of customer k  
    surplus = model.addVars(m, vtype=GRB.CONTINUOUS, name="s")

    # Objective: maximize total profit
    model.setObjective(gp.quicksum(Ns[k, 0]*Z[k, s] for k in segment_ind for s in size_indices), GRB.MAXIMIZE)

    # Constraints:
    
    # IC constraint: surplus[k] >= v_ks[k,s] - p[s] for all k, s
    model.addConstrs((surplus[k] >= v_ks[k, s] - p[s] for k in segment_ind for s in size_indices))
    
    # Each customer chooses exactly one bundle size  
    model.addConstrs((gp.quicksum(theta[k, s] for s in size_indices) == 1 for k in segment_ind))
    
    # Price consistency: P[k,s] >= p[s] - M*(1-theta[k,s])
    model.addConstrs((P[k, s] >= p[s] - Rbar * (1 - theta[k, s]) 
                     for k in segment_ind for s in size_indices))
    
    # Price upper bound: P[k,s] <= p[s]
    model.addConstrs((P[k, s] <= p[s] for k in segment_ind for s in size_indices))
    
    # Surplus definition: S[k,s] = v_ks[k,s] * theta[k,s] - P[k,s]
    model.addConstrs((S[k, s] == v_ks[k, s] * theta[k, s] - P[k, s] 
                     for k in segment_ind for s in size_indices))
    
    # Total surplus: surplus[k] = sum_s S[k,s]
    model.addConstrs((surplus[k] == gp.quicksum(S[k, s] for s in size_indices) 
                     for k in segment_ind))
    
    # IC constraint between customers: surplus[k] >= sum_s (v_ks[k,s] * theta[j,s] - P[j,s])
    # for all k, j != k
    model.addConstrs((surplus[k] >= gp.quicksum(v_ks[k, s] * theta[j, s] - P[j, s] for s in size_indices)
                     for k in segment_ind for j in segment_ind if j != k))
    
    # Profit definition: Z[k,s] = P[k,s] - c_ks[k,s] * theta[k,s]  
    model.addConstrs((Z[k, s] == P[k, s] - c_ks[k, s] * theta[k, s] for k in segment_ind for s in size_indices))
    
    # Subadditivity constraints for size-based pricing
    for s1 in range(max_size + 1):
        for s2 in range(max_size + 1):
            if s1 + s2 <= max_size:
                model.addConstr(p[s1 + s2] <= p[s1] + p[s2])

    # Monotonicity constraints: larger bundles should have higher or equal prices
    for s in range(max_size):
        model.addConstr(p[s + 1] >= p[s])
    
    # No surplus from size 0 (empty bundle)
    model.addConstrs((S[k, 0] == 0 for k in segment_ind))

    model.optimize()
    
    if model.SolCount > 0:
        # Extract solution - only return prices for actually selected sizes
        selected_sizes = set()
        size_prices = {}
        solution_sizes = {}  # segment -> selected size
        
        # First, identify which sizes are actually selected by customers
        for k in segment_ind:
            for s in size_indices:
                if theta[k, s].X >= 1 - 1e-2:
                    selected_sizes.add(s)
                    solution_sizes[k] = s
                    break
        
        # Only return prices for selected sizes
        for s in selected_sizes:
            size_prices[s] = p[s].X
        
        return model.ObjVal, model.Runtime, solution_sizes, size_prices
    else:
        return None, model.Runtime, None, None


def evaluate_sample(data_dict):
    """
    Evaluate a single sample: compare BSP solution with optimal solution
    """
    n = data_dict['product_num']
    m = data_dict['segment_num']
    cs = data_dict['cs']
    Rs = data_dict['Rs']
    Ns = data_dict['Ns']
    opt_rev = data_dict['opt_rev']
    opt_time = data_dict['running_time']
    
    # Solve BSP problem on this instance
    bsp_rev, bsp_time, solution_sizes, size_prices = solve_bsp_for_evaluation(n, m, cs, Rs, Ns)
    if bsp_rev is None:  # infeasible
        return None, None, None, None, None, None
        
    # Package solution
    bsp_solution = (solution_sizes, size_prices)
    
    # Calculate revenue ratio (BSP revenue / optimal revenue)
    revenue_ratio = bsp_rev / opt_rev if opt_rev > 0 else 0
    
    # Calculate time ratio (BSP time / optimal time)
    time_ratio = bsp_time / opt_time if opt_time > 0 else 0
    
    return revenue_ratio, time_ratio, bsp_time, bsp_rev, None, bsp_solution


def main():
    # Set paths
    test_data_path = './dataset/test_data/'

    # Bundle size pricing evaluation
    print("=== Bundle Size Pricing Evaluation ===")
    
    # Load test dataset
    dir_list = os.listdir(test_data_path)
    sample_num = len([f for f in dir_list if f.endswith('.msgpack')])
    
    print(f'Found {sample_num} test samples.')
    print("Evaluating Bundle Size Pricing algorithm...")
    
    # Evaluate samples
    results = []
    failed_samples = 0
    
    for filename in tqdm(dir_list, desc="Evaluating BSP"):
        if not filename.endswith('.msgpack'):
            continue
            
        file_path = os.path.join(test_data_path, filename)
        
        try:
            # Load and process data
            data_dict = process_data(file_path)
            
            # Evaluate sample: BSP vs optimal
            result = evaluate_sample(data_dict)
            revenue_ratio, time_ratio, bsp_time, bsp_rev, bsp_price, bsp_solution = result
            
            if revenue_ratio is None:  # infeasible
                failed_samples += 1
                continue
            
            results.append({
                'filename': filename,
                'product_num': data_dict['product_num'],
                'segment_num': data_dict['segment_num'],
                'revenue_ratio': revenue_ratio,
                'time_ratio': time_ratio,
                'bsp_time': bsp_time,
                'bsp_rev': bsp_rev,
                'opt_rev': data_dict['opt_rev'],
                'opt_time': data_dict['running_time']
            })
            
        except Exception as e:
            print(f"Error processing file {filename}: {e}")
            failed_samples += 1
            continue
    
    # Save results
    if results:
        # Convert to arrays for analysis
        revenue_ratios = np.array([r['revenue_ratio'] for r in results])
        time_ratios = np.array([r['time_ratio'] for r in results])
        product_nums = np.array([r['product_num'] for r in results])
        
        # Save detailed results
        result_path = 'test_result_BSP_vs_optimal.csv'
        
        # Prepare data for CSV
        csv_data = np.column_stack((
            product_nums,
            revenue_ratios,
            time_ratios
        ))
        
        # Save with proper headers
        header = 'n_products,revenue_ratio,runtime_ratio'
        # Save results to CSV
        # np.savetxt(result_path, csv_data, delimiter=',', header=header, comments='')
        
        # Print summary statistics
        print(f'\n=== BUNDLE SIZE PRICING RESULTS ===')
        print(f'Test completed successfully')
        print(f'Results can be saved to: {result_path}')
        print(f'Number of samples evaluated: {len(results)}')
        print(f'Number of failed samples: {failed_samples}')
        
        # Revenue ratio statistics
        print(f'\n=== REVENUE RATIO STATISTICS ===')
        print(f'Mean: {np.mean(revenue_ratios):.4f}')
        print(f'Std:  {np.std(revenue_ratios):.4f}')
        print(f'Min:  {np.min(revenue_ratios):.4f}')
        print(f'Max:  {np.max(revenue_ratios):.4f}')
        
        # Time ratio statistics
        print(f'\n=== TIME RATIO STATISTICS ===')
        print(f'Mean: {np.mean(time_ratios):.4f}')
        print(f'Std:  {np.std(time_ratios):.4f}')
        print(f'Min:  {np.min(time_ratios):.4f}')
        print(f'Max:  {np.max(time_ratios):.4f}')
    
    else:
        print("No samples were successfully evaluated.")
        if failed_samples > 0:
            print(f"Total failed samples: {failed_samples}")


if __name__ == "__main__":
    main()