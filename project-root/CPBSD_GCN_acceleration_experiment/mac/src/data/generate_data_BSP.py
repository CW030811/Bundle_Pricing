import numpy as np
import pandas as pd
import msgpack
import msgpack_numpy as mnp
import os
import torch
from torch_geometric.data import Data
import torch_geometric.utils
import gurobipy as gp
from gurobipy import GRB
import time
from itertools import combinations
import shutil

bin2num = lambda x: int(''.join(map(str, x.tolist())), 2)



def solve_bundle_size_pricing_MILP(n, m, B, assortments, costs, Rs, Rbar, Ns):
    """
    Bundle size pricing: bundles of the same size have the same price
    Using size-based variables (theta[k,s], P[k,s]) instead of bundle-based
    """
    segment_ind = range(m)
    bundle_ind = range(B)
    
    # Calculate bundle sizes
    bundle_sizes = np.sum(assortments, axis=1)  # size of each bundle
    max_size = int(np.max(bundle_sizes))
    size_indices = range(max_size + 1)  # 0, 1, 2, ..., max_size
    
    # For each size, compute maximum valuation and corresponding cost for each customer
    # v_ks: customer k's maximum valuation for size s
    # c_ks: cost of size s for customer k (we'll use the minimum cost among bundles of size s)
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
    
    # Initialize objective history tracking
    obj_hist = []
    start_time = time.time()
    last_record_time = 0
    
    # Define callback function to record objective every 5 seconds
    def callback_func(model, where):
        nonlocal last_record_time, obj_hist, start_time
        
        if where == GRB.Callback.MIP:
            current_time = time.time()
            elapsed_time = current_time - start_time
            
            # Record every 5 seconds
            if elapsed_time - last_record_time >= 5.0:
                obj_bound = model.cbGet(GRB.Callback.MIP_OBJBND)
                obj_best = model.cbGet(GRB.Callback.MIP_OBJBST)
                
                # Record the better of the two (for maximization problem, we want the best incumbent)
                if obj_best != GRB.INFINITY:
                    current_obj = obj_best
                else:
                    current_obj = obj_bound if obj_bound != -GRB.INFINITY else None
                
                if current_obj is not None:
                    obj_hist.append({
                        'time': elapsed_time,
                        'objective': current_obj
                    })
                
                last_record_time = elapsed_time

    model = gp.Model("Bundle Size Pricing MILP")

    # Variables (using original naming convention):
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


    model.setObjective(gp.quicksum(Ns[k, 0]*Z[k, s] for k in segment_ind for s in size_indices), GRB.MAXIMIZE)

    # Constraints:
    
    model.addConstrs((surplus[k] >= v_ks[k, s] - p[s] for k in segment_ind for s in size_indices))
    
    model.addConstrs((gp.quicksum(theta[k, s] for s in size_indices) == 1 for k in segment_ind))
    
    model.addConstrs((P[k, s] >= p[s] - Rbar * (1 - theta[k, s]) 
                     for k in segment_ind for s in size_indices))
    
    model.addConstrs((P[k, s] <= p[s] for k in segment_ind for s in size_indices))
    
    model.addConstrs((S[k, s] == v_ks[k, s] * theta[k, s] - P[k, s] 
                     for k in segment_ind for s in size_indices))
    
    model.addConstrs((surplus[k] == gp.quicksum(S[k, s] for s in size_indices) 
                     for k in segment_ind))
    
    model.addConstrs((surplus[k] >= gp.quicksum(v_ks[k, s] * theta[j, s] - P[j, s] for s in size_indices)
                     for k in segment_ind for j in segment_ind if j != k))
    
    model.addConstrs((Z[k, s] == P[k, s] - c_ks[k, s] * theta[k, s] for k in segment_ind for s in size_indices))
    
    for s1 in range(max_size + 1):
        for s2 in range(max_size + 1):
            if s1 + s2 <= max_size:
                model.addConstr(p[s1 + s2] <= p[s1] + p[s2])

    for s in range(max_size):
        model.addConstr(p[s + 1] >= p[s])
    
    model.addConstrs((S[k, 0] == 0 for k in segment_ind))

    model.setParam("OutputFlag", 1)
    model.setParam("MIPGap", 1e-2)
    t1 = time.time()
    model.optimize(callback_func)
    t2 = time.time()
    
    # Record final objective if available
    if model.SolCount > 0:
        final_time = t2 - start_time
        obj_hist.append({
            'time': final_time,
            'objective': model.ObjVal
        })

    # Check feasibility
    feasible = model.SolCount > 0

    if not feasible:
        return None, None, None, model.Runtime, None, False, obj_hist

    # Extract solution - only return prices for actually selected sizes
    selected_sizes = set()
    size_prices = {}
    solution_sizes = {}  # customer -> selected size
    
    # First, identify which sizes are actually selected by customers
    for k in segment_ind:
        for s in size_indices:
            if theta[k, s].X >= 1 - 1e-2:
                selected_sizes.add(s)
                solution_sizes[k] = s
    
    # Only return prices for selected sizes
    for s in selected_sizes:
        size_prices[s] = p[s].X
    
    # Note: In the new version, we return both customer size choices and size prices
    
    return solution_sizes, size_prices, model.ObjVal, model.Runtime, model.MIPGap, True, obj_hist


def generate_sample(m, ship_cs, l, u, sample_num, folder_path):
    """
    Generate samples for bundle size pricing problems
    
    Parameters:
    m: number of customer segments
    ship_cs: shipping costs
    l: minimum number of products
    u: maximum number of products
    sample_num: number of samples to generate
    folder_path: output folder path
    """
    import os
    import shutil

    def delete_all_files(folder_path):
        """
        Delete all files in the specified folder (keeping the empty folder)
        """
        try:
            shutil.rmtree(folder_path)
            print(f"Folder '{folder_path}' deleted successfully.")
            time.sleep(5)
        except:
            print('No such folder.')
        os.makedirs(folder_path, exist_ok=True)
        print(f"Folder '{folder_path}' created successfully.")

    folder_to_clean = folder_path
    delete_all_files(folder_to_clean)
    
    for iter in range(sample_num):
        if np.mod(iter + 1, 10) == 0:
            print('Generating samples: {}/{}'.format(iter+1, sample_num))
        n = np.random.randint(l, u) # product number
        B = 2**n # bundle number
        unit_cs = np.random.rand(1, n)
        assortments = np.array([list(map(int, format(num, '0' + str(n) + 'b'))) for num in range(2**n)], dtype=int)
        costs = np.sum(assortments * unit_cs, axis=1) + ship_cs  # unit cost + ship cost (subadditive)
        costs = costs * 0.2
        
        unit_us = np.random.rand(m, n)
        Rs = np.sqrt(unit_us.dot(assortments.T))
        
        Rbar = np.max(Rs)
        Xs = np.random.rand(m, 1)
        Ns = Xs / np.sum(Xs)

        result = solve_bundle_size_pricing_MILP(n, m, B, assortments, costs, Rs, Rbar, Ns)
        solution_sizes, size_prices, opt_rev, runtime, gap, feasible, obj_hist = result

        if not feasible:
            print(f"Sample {iter+1}: infeasible model – skipping save.")
            continue

        # Determine specific bundle selections from size-based solution
        customer_bundle_map = {}  # customer -> bundle_index (for internal use)
        opt_prices = {}   # bundle_index -> price
        
        bundle_sizes_array = np.sum(assortments, axis=1)
        
        # For each customer, find the best bundle within their chosen size
        for k in range(m):
            if k in solution_sizes:
                chosen_size = solution_sizes[k]
                
                # Find all bundles of the chosen size
                size_bundles = [i for i in range(B) if bundle_sizes_array[i] == chosen_size]
                
                if size_bundles:
                    # Choose the bundle with highest valuation for this customer
                    best_bundle_idx = max(size_bundles, key=lambda i: Rs[k, i])
                    customer_bundle_map[k] = best_bundle_idx
                    
                    # Set price for this bundle
                    if chosen_size in size_prices:
                        opt_prices[best_bundle_idx] = size_prices[chosen_size]
                    else:
                        opt_prices[best_bundle_idx] = 0.0
        
        opt_bundles = []
        for k in range(m):
            if k in customer_bundle_map:
                bundle_idx = customer_bundle_map[k]
                bundle_binary = assortments[bundle_idx, :].tolist()  # Convert to binary representation
                opt_bundles.append(bundle_binary)
            else:
                # If customer has no bundle, use empty bundle (all zeros)
                opt_bundles.append([0] * n)
        
        
        # Print selected bundles and their prices for verification
        for bundle_idx, price in opt_prices.items():
            bundle_bits = assortments[bundle_idx, :]
            bundle_size = np.sum(bundle_bits)
            print(f"  Bundle {bundle_idx} (size {bundle_size}): {price:.6f}")

        data_to_pack = {
            'product_num': n,
            'segment_num': m,
            'unit_cs': unit_cs,
            'ship_cs': ship_cs,
            'unit_us': unit_us,
            'Ns': Ns,
            'opt_bundles': opt_bundles,
            'opt_prices': opt_prices,
            'opt_rev': opt_rev,
            'running_time': runtime,
            'gap': gap,
            'obj_hist': obj_hist,
            'solution_sizes': solution_sizes,
            'size_prices': size_prices,
            'customer_bundle_map': customer_bundle_map
        }

        path = os.path.join(folder_path, 'sample_data_{}_size_{}_sizepricing.msgpack'.format(iter+1, n))

        with open(path, 'wb') as f:
            msgpack.dump(data_to_pack, f, default=mnp.encode)
    return


if __name__ == '__main__':
    # Default configuration
    output_dir = './dataset/bundle_size_pricing/'
    m = 20  # segment number

    np.random.seed(53)
    ship_cs = np.random.rand(m, 1)
    np.random.seed(None)

    # Generate samples for bundle size pricing
    generate_sample(m, ship_cs, 15, 16, 100, output_dir) 
    
    
    
    
    