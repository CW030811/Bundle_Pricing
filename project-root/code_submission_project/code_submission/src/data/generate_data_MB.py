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

bin2num = lambda x: int(''.join(map(str, x.tolist())), 2)

def solve_bundle_MILP(n, m, B, assortments, costs, Rs, Rbar, Ns):
    product_ind = np.array([i for i in range(n)])
    segment_ind = np.array([i for i in range(m)])
    bundle_ind = np.array([i for i in range(B)])

    model = gp.Model("Bundle MILP")

    p = model.addVars(B, vtype=GRB.CONTINUOUS, lb=0, name="p")
    theta = model.addVars(m, B, vtype=GRB.BINARY, name="theta")
    s = model.addVars(m, vtype=GRB.CONTINUOUS, name="s")
    S = model.addVars(m, B, vtype=GRB.CONTINUOUS, lb=0, name='S')
    Z = model.addVars(m, B, vtype=GRB.CONTINUOUS, name='Z')
    P = model.addVars(m, B, vtype=GRB.CONTINUOUS, lb=0, name='P')

    model.setObjective(gp.quicksum(Ns[k, 0]*Z[k, i] for k in segment_ind for i in bundle_ind), GRB.MAXIMIZE)

    model.addConstrs((s[k] >= Rs[k, i] - p[i] for i in bundle_ind for k in segment_ind))
    for i in bundle_ind:
        tmp_assort = assortments[i, :]
        set_inds = np.where(tmp_assort)[0]
        for num in range(1, sum(tmp_assort)//2+1):
            for inds in combinations(set_inds, num):
                assort1 = np.zeros(n, dtype=int)
                assort1[list(inds)] = 1
                assort2 = tmp_assort - assort1
                model.addConstr(p[bin2num(tmp_assort)] <= p[bin2num(assort1)] + p[bin2num(assort2)])

    model.addConstrs((P[k, i] >= p[i] - Rbar*(1-theta[k, i]) for i in bundle_ind for k in segment_ind))
    model.addConstrs((P[k, i] <= p[i] for i in bundle_ind for k in segment_ind))

    model.addConstrs((s[k] >= gp.quicksum(Rs[k, i]*theta[j, i] - P[j, i] for i in bundle_ind) for k in segment_ind for j in segment_ind))

    model.addConstrs((Z[k, i] == P[k, i] - costs[k, i] * theta[k, i] for i in bundle_ind for k in segment_ind))
    model.addConstrs((S[k, i] == Rs[k, i]*theta[k, i] - P[k, i] for i in bundle_ind for k in segment_ind))
    model.addConstrs((s[k] == gp.quicksum(S[k, i] for i in bundle_ind) for k in segment_ind))
    model.addConstrs((gp.quicksum(theta[k, i] for i in bundle_ind) == 1 for k in segment_ind))
    model.addConstrs((S[k, 0] == 0 for k in segment_ind))

    model.setParam("OutputFlag", 0)
    model.setParam("MIPGap", 1e-2)
    
    model.Params.TimeLimit = 600 * 4
    t1 = time.time()
    model.optimize()
    t2 = time.time()

    # Check feasibility: if no feasible solution found, simply indicate infeasibility
    feasible = model.SolCount > 0

    if not feasible:
        # Return placeholders when infeasible; caller will handle
        return None, None, None, model.Runtime, None, False

    opt_bundles = []
    opt_prices = {}
    for k in segment_ind:
        for i in bundle_ind:
            # Guard against attributes being None in edge cases
            if theta[k, i].X >= 1 - 1e-2:
                opt_bundles.append(assortments[i, :].tolist())
                opt_prices[i] = p[i].X

    return opt_bundles, opt_prices, model.ObjVal, model.Runtime, model.MIPGap, True
        


def generate_sample(m, ship_cs, l, u, sample_num, folder_path):
    """
    Generate samples for mixed bundling problems
    
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

    # Clean up existing folder
    folder_to_clean = folder_path
    delete_all_files(folder_to_clean)
    for iter in range(sample_num):
        if np.mod(iter + 1, 10) == 0:
            print('Generating samples: {}/{}'.format(iter+1, sample_num))
        n = np.random.randint(l, u) # product number
        B = 2**n # bundle number
        unit_cs = np.random.rand(1, n)
        
        assortments = np.array([list(map(int, format(num, '0' + str(n) + 'b'))) for num in range(2**n)], dtype=int)
        costs = np.sum(assortments * unit_cs, axis=1) + ship_cs
        costs = costs * 0.2
        unit_us = np.random.rand(m, n)
        
        Rs = np.sqrt(unit_us.dot(assortments.T))
        Rbar = np.max(Rs)
        Xs = np.random.rand(m, 1)
        Ns = Xs / np.sum(Xs)
    
    
        opt_bundles, opt_prices, opt_rev, runtime, gap, feasible = solve_bundle_MILP(n, m, B, assortments, costs, Rs, Rbar, Ns)

        # Skip saving if the model was infeasible
        if not feasible:
            print(f"Sample {iter+1}: infeasible model – skipping save.")
            continue

        data_to_pack = {
            'product_num': n,
            'segment_num': m,
            'unit_cs': unit_cs,
            'ship_cs': ship_cs,
            'unit_us': unit_us,
            'cs': costs,
            'Rs': Rs,
            'Ns': Ns,
            'opt_bundles': opt_bundles,
            'opt_prices': opt_prices,
            'opt_rev': opt_rev,
            'running_time': runtime,
            'gap': gap
        }

        path = os.path.join(folder_path, 'sample_data_{}_size_{}.msgpack'.format(iter+1, n))
        with open(path, 'wb') as f:
            msgpack.dump(data_to_pack, f, default=mnp.encode)
    return


if __name__ == '__main__':
    # Default configuration
    output_dir = './dataset/mixed_bundling/'
    m = 10  # segment number

    np.random.seed(53)
    ship_cs = np.random.rand(m, 1)
    np.random.seed(None)

    # Generate samples for mixed bundling
    generate_sample(m, ship_cs, 10, 11, 50, output_dir)
    
    




