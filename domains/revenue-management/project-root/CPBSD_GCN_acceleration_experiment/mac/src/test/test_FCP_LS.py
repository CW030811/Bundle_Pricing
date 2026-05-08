"""
Local Search with Mixed MILP-LP Strategy

Strategy:
1. Use threshold method to generate initial bundle prediction
2. Use MILP solver to obtain initial optimal bundle assignment
3. Use LP solver for fast local search neighborhood evaluation
4. Use greedy strategy: accept improvement when found
5. Convert final assignment back to MILP for global optimization
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import torch_geometric.utils
import os
import numpy as np
import msgpack
import msgpack_numpy as mnp
import argparse
from pathlib import Path
from typing import Optional
import sys

import matplotlib.pyplot as plt
from tqdm import tqdm
import time

import torch
from torch_geometric.nn import GENConv
from torch_geometric.data import Data, Batch
from torch_geometric.loader import DataLoader
import gurobipy as gp
from gurobipy import GRB
from itertools import combinations


class EdgeScoringGCN(nn.Module):
    def __init__(
        self,
        in_channels: int = 4,
        hidden_channels: int = 128,
        num_layers: int = 2,
        edge_dim: int = 1,
        score_type: str = 'bilinear',  # 'bilinear' | 'dot' | 'mlp'
        proj_dim: int | None = None,   # for 'dot'
        use_edge_attr: bool = True,
        dropout: float = 0.5,
    ) -> None:
        super().__init__()
        self.use_edge_attr = use_edge_attr
        self.score_type = score_type

        # Directional GENConv stacks: left->right and right->left
        self.l2r = nn.ModuleList()
        self.r2l = nn.ModuleList()
        c_in = in_channels
        for _ in range(num_layers):
            self.l2r.append(GENConv(c_in, hidden_channels, edge_dim=edge_dim))
            self.r2l.append(GENConv(c_in, hidden_channels, edge_dim=edge_dim))
            c_in = hidden_channels

        self.dropout = nn.Dropout(dropout)

        # Edge-scoring head
        if score_type == 'bilinear':
            self.U = nn.Parameter(torch.empty(hidden_channels, hidden_channels))
            nn.init.xavier_uniform_(self.U)
        elif score_type == 'dot':
            d = proj_dim or hidden_channels
            self.proj_p = nn.Linear(hidden_channels, d, bias=False)
            self.proj_s = nn.Linear(hidden_channels, d, bias=False)
        elif score_type == 'mlp':
            d_in = hidden_channels * 2 + (edge_dim if use_edge_attr else 0)
            self.mlp = nn.Sequential(
                nn.Linear(d_in, hidden_channels),
                nn.ReLU(),
                nn.Linear(hidden_channels, 1),
            )
        else:
            raise ValueError(f"Unknown score_type={score_type}")

        if use_edge_attr and score_type in ('bilinear', 'dot'):
            self.edge_mlp = nn.Sequential(
                nn.Linear(edge_dim, hidden_channels),
                nn.ReLU(),
                nn.Linear(hidden_channels, 1),
            )

    def forward(self, data):
        x, edge_index, edge_attr, side_ind = data.x, data.edge_index, data.edge_attr, data.side_ind
        rev_edge_index = edge_index.flip(dims=[0])

        # Encoder: blend left-to-right and right-to-left messages
        for l2r_conv, r2l_conv in zip(self.l2r, self.r2l):
            r_x = l2r_conv(x, edge_index, edge_attr)
            l_x = r2l_conv(x, rev_edge_index, edge_attr)
            x = F.relu(r_x * (1 - side_ind) + l_x * side_ind)
            x = self.dropout(x)

        z = x  # node embeddings, shape (N, H)
        src, dst = edge_index  # edge endpoints

        # Edge scoring
        if self.score_type == 'bilinear':
            # s_e = h_src^T U h_dst
            s = torch.einsum('ei,ij,ej->e', z[src], self.U, z[dst])
            if self.use_edge_attr:
                s = s + self.edge_mlp(edge_attr).squeeze(-1)
        elif self.score_type == 'dot':
            s = (self.proj_p(z[src]) * self.proj_s(z[dst])).sum(dim=-1)
            if self.use_edge_attr:
                s = s + self.edge_mlp(edge_attr).squeeze(-1)
        else:  # 'mlp'
            feats = [z[src], z[dst]]
            if self.use_edge_attr:
                feats.append(edge_attr)
            s = self.mlp(torch.cat(feats, dim=-1)).squeeze(-1)

        out = { 'edge_logits': s }

        # Optional matrix view for single-graph inference
        if hasattr(data, 'product_num') and hasattr(data, 'segment_num'):
            try:
                n = int(data.product_num)
                m = int(data.segment_num)
                if s.numel() == n * m:
                    out['logit_matrix'] = s.view(n, m)
            except Exception:
                pass

        return out

if hasattr(torch.serialization, 'add_safe_globals'):
    torch.serialization.add_safe_globals([EdgeScoringGCN])

def process_data(file_path):
    """
    Process data file and return graph data and related parameters
    Supports both old and new data formats, dynamically calculates cs and Rs matrices
    """
    with open(file_path, 'rb') as f:
        data = msgpack.load(f, object_hook=mnp.decode, strict_map_key=False)
    
    product_num = int(data['product_num'])
    segment_num = int(data['segment_num'])
    unit_cs = data['unit_cs']
    ship_cs = data['ship_cs']
    unit_us = data['unit_us']
    Ns = data['Ns']
    opt_bundles = data['opt_bundles']
    opt_prices = data['opt_prices']
    opt_rev = data['opt_rev']
    running_time = data['running_time']
    gap = data['gap']
    
    # Check if cs and Rs are stored, if not we'll calculate them on-demand
    has_stored_cs = 'cs' in data
    has_stored_Rs = 'Rs' in data
    
    if has_stored_cs and has_stored_Rs:
        # Use stored matrices (old format)
        cs = data['cs']
        Rs = data['Rs']
    else:
        # New format - will be calculated on-demand
        cs = None
        Rs = None
    
    node_num = product_num + segment_num
    
    # Build node features robustly against shape mismatches
    feature = np.zeros((node_num, 4), dtype=float)

    # unit_cs: expect shape (1, n) or (n,)
    if isinstance(unit_cs, np.ndarray):
        if unit_cs.ndim == 2:
            uc = unit_cs[0]
        else:
            uc = unit_cs
        uc = np.asarray(uc).reshape(-1)[:product_num]
    else:
        uc = np.asarray(unit_cs).reshape(-1)[:product_num]
    feature[:product_num, 0] = uc

    # unit_us: shape (m, n), average across segments for product feature
    uu_avg = np.average(unit_us, axis=0)
    feature[:product_num, 1] = np.asarray(uu_avg).reshape(-1)[:product_num]

    # Ns: shape (m, 1) or (m,)
    if isinstance(Ns, np.ndarray) and Ns.ndim == 2:
        ns_vec = Ns[:, 0]
    else:
        ns_vec = np.asarray(Ns).reshape(-1)
    ns_vec = ns_vec[:segment_num]
    feature[product_num:, 2] = ns_vec

    # ship_cs: may have more rows than m; take the first m strictly
    if isinstance(ship_cs, np.ndarray) and ship_cs.ndim == 2:
        sc_vec = ship_cs[:segment_num, 0]
    else:
        sc_vec = np.asarray(ship_cs).reshape(-1)[:segment_num]
    feature[product_num:, 3] = sc_vec

    x = torch.tensor(feature, dtype=torch.float)
    
    prods = []
    custs = []
    edge_weights = []
    for i in range(product_num):
        for j in range(segment_num):
            prods.append(i)
            custs.append(j+product_num)
            edge_weights.append([float(unit_us[j, i])])
            
    edge_index = torch.tensor([prods, custs], dtype=torch.long)        
    edge_weight = torch.tensor(edge_weights, dtype=torch.float)
    side_ind = torch.tensor([1]*product_num + [0]*segment_num, dtype=torch.long).view(-1, 1)

    prod_labels = np.array(opt_bundles).T  
    seg_labels = -np.ones((segment_num, segment_num), dtype=int)
    y = np.append(prod_labels, seg_labels, axis=0)
    y = torch.tensor(y, dtype=torch.long)
    data = Data(x=x, edge_index=edge_index, edge_attr=edge_weight, side_ind=side_ind, y=y)
    miscellaneous = (product_num, segment_num, unit_cs, ship_cs, unit_us, Ns, opt_bundles, opt_prices, opt_rev, running_time, gap, cs, Rs)
    return data, miscellaneous


def convert_pred_assort_to_assignment(pred_assort):
    """
    Convert pred_assort matrix to segment_bundle_assignment dictionary
    """
    bin2num = lambda x: int(''.join(map(str, x.tolist())), 2)
    
    assignment = {}
    m, n = pred_assort.shape
    
    for k in range(m):
        bundle_binary = pred_assort[k, :]
        bundle_idx = bin2num(bundle_binary)
        assignment[k] = bundle_idx
    
    return assignment


def assignment_to_pred_assort(assignment, n, m):
    """
    Convert one-to-one assignment back to pred_assort matrix
    """
    pred_assort = np.zeros((m, n), dtype=int)

    for k in range(m):
        bundle_idx = assignment[k]
        bundle_binary = format(bundle_idx, f'0{n}b')
        pred_assort[k, :] = [int(x) for x in bundle_binary]

    return pred_assort


def bundle_to_product_set(bundle_id, n):
    """Convert bundle ID to product set"""
    binary_str = format(bundle_id, '0' + str(n) + 'b')
    return set(i for i, bit in enumerate(binary_str) if bit == '1')




def revenue_ratio_with_optimal_bundle(n, m, unit_cs, ship_cs, unit_us, Ns, opt_rev, pred_assort, stored_cs=None, stored_Rs=None):
    milp_start_time = time.time()
    
    bin2num = lambda x: int(''.join(map(str, x.tolist())), 2)
    segment_ind = np.array([i for i in range(m)])
    
    # Get unique predicted bundles
    bundle_dic = {}
    for i in range(m):
        bundle_idx = bin2num(pred_assort[i, :])
        try:
            bundle_dic[bundle_idx].append(i)
        except:
            bundle_dic[bundle_idx] = [i]
    
    predicted_bundles = list(bundle_dic.keys())
    
    # Calculate Rs and costs only for predicted bundles
    if stored_cs is not None and stored_Rs is not None:
        # Use stored matrices (old format)
        # Convert to compact format for consistency
        # Generate assortments only for predicted bundles
        predicted_assortments = []
        for bundle_id in predicted_bundles:
            bundle_binary = list(map(int, format(bundle_id, '0' + str(n) + 'b')))
            predicted_assortments.append(bundle_binary)
        predicted_assortments = np.array(predicted_assortments)
        
        # Create mapping from bundle_id to index in predicted arrays
        bundle_to_idx = {bundle_id: idx for idx, bundle_id in enumerate(predicted_bundles)}
        
        # Extract Rs and cs for predicted bundles from stored full-size arrays
        Rs_predicted = np.zeros((m, len(predicted_bundles)))
        cs_predicted = np.zeros((m, len(predicted_bundles)))
        for bundle_id, idx in bundle_to_idx.items():
            Rs_predicted[:, idx] = stored_Rs[:, bundle_id]
            cs_predicted[:, idx] = stored_cs[:, bundle_id]
        
        Rbar = np.max(Rs_predicted)
    else:
        # Calculate only for predicted bundles (new optimized format)
        # Only calculate for predicted bundles instead of all bundles
        
        # Generate assortments only for predicted bundles
        predicted_assortments = []
        for bundle_id in predicted_bundles:
            bundle_binary = list(map(int, format(bundle_id, '0' + str(n) + 'b')))
            predicted_assortments.append(bundle_binary)
        predicted_assortments = np.array(predicted_assortments)
        
        # Calculate Rs only for predicted bundles: Rs[customer, bundle]
        Rs_predicted = np.sqrt(unit_us.dot(predicted_assortments.T))  # shape: (m, len(predicted_bundles))
        
        # Calculate cs only for predicted bundles: cs[customer, bundle]  
        cs_base = np.sum(predicted_assortments * unit_cs, axis=1)  # shape: (len(predicted_bundles),)
        cs_predicted = cs_base + ship_cs  # Broadcasting: (len(predicted_bundles),) + (m, 1) -> (m, len(predicted_bundles))
        cs_predicted = cs_predicted * 0.2
        
        # Create mapping from bundle_id to index in predicted arrays
        bundle_to_idx = {bundle_id: idx for idx, bundle_id in enumerate(predicted_bundles)}
        
        Rbar = np.max(Rs_predicted)

    model = gp.Model("Bundle MILP")
    model.Params.OutputFlag = 0
    model.Params.MIPGap = 1e-3
    model.Params.TimeLimit = 600

    # Create variables ONLY for predicted bundles
    p = model.addVars(predicted_bundles, vtype=GRB.CONTINUOUS, lb=0, name="p")
    theta = model.addVars(m, predicted_bundles, vtype=GRB.BINARY, name="theta")
    s = model.addVars(m, vtype=GRB.CONTINUOUS, name="s")
    S = model.addVars(m, predicted_bundles, vtype=GRB.CONTINUOUS, lb=0, name='S')
    Z = model.addVars(m, predicted_bundles, vtype=GRB.CONTINUOUS, name='Z')
    P = model.addVars(m, predicted_bundles, vtype=GRB.CONTINUOUS, lb=0, name='P')

    # Objective: only consider predicted bundles
    model.setObjective(gp.quicksum(Ns[k, 0]*Z[k, i] for k in segment_ind for i in predicted_bundles), GRB.MAXIMIZE)

    # Standard constraints (only for predicted bundles)
    model.addConstrs((s[k] >= Rs_predicted[k, bundle_to_idx[i]] - p[i] for i in predicted_bundles for k in segment_ind))
    
    # Improved subadditivity constraints
    # Pre-compute product sets for all bundles
    bundle_product_sets = {}
    for bundle_id in predicted_bundles:
        bundle_product_sets[bundle_id] = bundle_to_product_set(bundle_id, n)

    # Filter constraints
    for k in predicted_bundles:
        if k == 0:  # Skip empty set
            continue

        k_set = bundle_product_sets[k]
        if len(k_set) == 0:
            continue

        for i in predicted_bundles:
            for j in predicted_bundles:
                if i >= j:  # Avoid duplicates
                    continue

                i_set = bundle_product_sets[i]
                j_set = bundle_product_sets[j]
                union_set = i_set.union(j_set)

                # Check if it's a valid inclusion relationship
                if (k_set.issubset(union_set) and
                    k_set != i_set and
                    k_set != j_set):
                    model.addConstr(p[k] <= p[i] + p[j])

    # Remaining constraints (only for predicted bundles)
    model.addConstrs((P[k, i] >= p[i] - Rbar*(1-theta[k, i]) for i in predicted_bundles for k in segment_ind))
    model.addConstrs((P[k, i] <= p[i] for i in predicted_bundles for k in segment_ind))
    
    # Modified constraint: only sum over predicted bundles
    model.addConstrs((s[k] >= gp.quicksum(Rs_predicted[k, bundle_to_idx[i]]*theta[j, i] - P[j, i] for i in predicted_bundles) for k in segment_ind for j in segment_ind))
    
    model.addConstrs((Z[k, i] == P[k, i] - cs_predicted[k, bundle_to_idx[i]] * theta[k, i] for i in predicted_bundles for k in segment_ind))
    model.addConstrs((S[k, i] == Rs_predicted[k, bundle_to_idx[i]]*theta[k, i] - P[k, i] for i in predicted_bundles for k in segment_ind))
    model.addConstrs((s[k] == gp.quicksum(S[k, i] for i in predicted_bundles) for k in segment_ind))
    model.addConstrs((gp.quicksum(theta[k, i] for i in predicted_bundles) == 1 for k in segment_ind))

    if 0 in predicted_bundles:
        model.addConstrs((S[k, 0] == 0 for k in segment_ind))

    model.optimize()

    milp_end_time = time.time()
    milp_time = milp_end_time - milp_start_time
    
    # Extract optimal bundle assignment
    optimal_bundle_assignment = {}
    if model.Status == GRB.OPTIMAL:
        for k in segment_ind:
            for i in predicted_bundles:
                if theta[k, i].X > 0.5:  # Binary variable is 1
                    optimal_bundle_assignment[k] = i
                    break
    
    return model.ObjVal/opt_rev, milp_time, optimal_bundle_assignment


def revenue_ratio_LP(n, m, unit_cs, ship_cs, unit_us, Ns, opt_rev, segment_bundle_assignment, stored_cs=None, stored_Rs=None):
    lp_start_time = time.time()

    # Extract involved bundle set from assignment
    assigned_bundles = set(segment_bundle_assignment.values())
    predicted_bundles = list(assigned_bundles)

    # Ensure empty bundle (index 0) is in the set
    if 0 not in predicted_bundles:
        predicted_bundles.append(0)

    segment_ind = np.array([i for i in range(m)])
    
    # Calculate Rs and costs only for involved bundles
    if stored_cs is not None and stored_Rs is not None:
        # Use stored matrices (old format)
        # Convert to compact format for consistency
        # Generate assortments only for involved bundles
        predicted_assortments = []
        for bundle_id in predicted_bundles:
            bundle_binary = list(map(int, format(bundle_id, '0' + str(n) + 'b')))
            predicted_assortments.append(bundle_binary)
        predicted_assortments = np.array(predicted_assortments)
        
        # Create mapping from bundle_id to index in predicted arrays
        bundle_to_idx = {bundle_id: idx for idx, bundle_id in enumerate(predicted_bundles)}
        
        # Extract Rs and cs for involved bundles from stored full-size arrays
        Rs_predicted = np.zeros((m, len(predicted_bundles)))
        cs_predicted = np.zeros((m, len(predicted_bundles)))
        for bundle_id, idx in bundle_to_idx.items():
            Rs_predicted[:, idx] = stored_Rs[:, bundle_id]
            cs_predicted[:, idx] = stored_cs[:, bundle_id]
    else:
        # Calculate only for involved bundles (new optimized format)
        # LP only calculates for involved bundles instead of all bundles
        
        # Generate assortments only for involved bundles
        predicted_assortments = []
        for bundle_id in predicted_bundles:
            bundle_binary = list(map(int, format(bundle_id, '0' + str(n) + 'b')))
            predicted_assortments.append(bundle_binary)
        predicted_assortments = np.array(predicted_assortments)
        
        # Calculate Rs only for involved bundles: Rs[customer, bundle]
        Rs_predicted = np.sqrt(unit_us.dot(predicted_assortments.T))  # shape: (m, len(predicted_bundles))
        
        # Calculate cs only for involved bundles: cs[customer, bundle]  
        cs_base = np.sum(predicted_assortments * unit_cs, axis=1)  # shape: (len(predicted_bundles),)
        cs_predicted = cs_base + ship_cs  # Broadcasting: (len(predicted_bundles),) + (m, 1) -> (m, len(predicted_bundles))
        cs_predicted = cs_predicted * 0.2
        
        # Create mapping from bundle_id to index in predicted arrays
        bundle_to_idx = {bundle_id: idx for idx, bundle_id in enumerate(predicted_bundles)}

    # Create LP model
    model = gp.Model("Bundle LP-IC")

    # DECISION VARIABLES: p_i (i ∈ F), s_k (k = 1,...,M)
    # Price variables: only create for bundles involved in the assignment
    p = model.addVars(predicted_bundles, vtype=GRB.CONTINUOUS, lb=0, name="p")

    # Consumer surplus variables: one for each customer segment
    s = model.addVars(m, vtype=GRB.CONTINUOUS, name="s")

    # OBJECTIVE FUNCTION (same as original MILP when θ is fixed)
    # max Σ_{k=1}^M N_k (p_{b_k} - c_{b_k})
    # Since θ is fixed, profit = Σ_k N_k * (p_{b_k} - c_{k,b_k})
    objective_expr = gp.LinExpr()
    for k in segment_ind:
        b_k = segment_bundle_assignment[k]  # bundle chosen by segment k
        if b_k in predicted_bundles:
            # Profit = price - cost for the assigned bundle
            objective_expr += Ns[k, 0] * (p[b_k] - cs_predicted[k, bundle_to_idx[b_k]])

    model.setObjective(objective_expr, GRB.MAXIMIZE)

    # CONSTRAINT 1: IC (Incentive Compatibility) - Individual rationality lower bounds
    # Mathematical formulation: s_k ≥ R_{ki} - p_i, ∀k, ∀i ∈ F
    # Ensures each segment's chosen bundle is optimal relative to all available bundles
    for k in segment_ind:
        for i in predicted_bundles:
            model.addConstr(s[k] >= Rs_predicted[k, bundle_to_idx[i]] - p[i],
                          name=f"IC_k{k}_i{i}")

    # CONSTRAINT 2: Upper bound constraint - Bind "assigned bundle" with surplus upper bound
    # Mathematical formulation: s_k ≤ R_{k,b_k} - p_{b_k}, ∀k
    # Derived from Hanson's "tightening + single price schedule" when θ is fixed
    # Together with Constraint 1, this ensures s_k = max_i∈F{R_{ki} - p_i} = R_{k,b_k} - p_{b_k}
    # This "locks in" the θ choice and eliminates binary variables
    for k in segment_ind:
        b_k = segment_bundle_assignment[k]  # bundle assigned to segment k
        if b_k in predicted_bundles:
            model.addConstr(s[k] <= Rs_predicted[k, bundle_to_idx[b_k]] - p[b_k],
                          name=f"Upper_bound_k{k}")

    # CONSTRAINT 3: Price subadditivity (improved implementation, consistent with MILP)
    # Mathematical formulation: p_i ≤ Σ_{j∈I} p_j, for all i∈F and covering family I⊆F
    # such that ⋃_{j∈I} B(j) = B(i)
    # Use improved set-based method instead of combinations for better performance
    
    # Pre-compute product sets for all bundles
    bundle_product_sets = {}
    for bundle_id in predicted_bundles:
        bundle_product_sets[bundle_id] = bundle_to_product_set(bundle_id, n)

    # Filter constraints
    for k in predicted_bundles:
        if k == 0:  # Skip empty set
            continue

        k_set = bundle_product_sets[k]
        if len(k_set) == 0:
            continue

        for i in predicted_bundles:
            for j in predicted_bundles:
                if i >= j:  # Avoid duplicates
                    continue

                i_set = bundle_product_sets[i]
                j_set = bundle_product_sets[j]
                union_set = i_set.union(j_set)

                # Check if it's a valid inclusion relationship
                if (k_set.issubset(union_set) and
                    k_set != i_set and
                    k_set != j_set):
                    model.addConstr(p[k] <= p[i] + p[j],
                                  name=f"Subadditivity_k{k}_i{i}_j{j}")

    # CONSTRAINT 4: Non-negativity and normalization
    # Mathematical formulation: p_i ≥ 0 (i ∈ F), p_0 = 0
    # Empty bundle price is zero (already enforced by variable bounds, but explicit for clarity)
    if 0 in predicted_bundles:
        model.addConstr(p[0] == 0, name="Empty_bundle_price")

    # Solver parameter settings optimized for small-scale LP problems
    model.setParam("OutputFlag", 0)  # Disable output
    # Use automatic method selection (often defaults to Simplex for small problems)
    # Barrier (Method=2) is optimized for large sparse problems, but Simplex is typically faster for small dense problems
    model.setParam("Method", -1)     # Auto method selection
    model.setParam("Presolve", 2)    # Aggressive presolving (default is 2, but explicit for clarity)
    model.setParam("Threads", 1)     # Use single thread for small problems (avoids overhead)
    model.Params.TimeLimit = 300     # Time limit

    # Solve
    model.optimize()

    lp_end_time = time.time()
    lp_time = lp_end_time - lp_start_time

    # Return results
    if model.Status == GRB.OPTIMAL:
        return model.ObjVal / opt_rev, lp_time
    elif model.Status == GRB.TIME_LIMIT and model.SolCount > 0:
        return model.ObjVal / opt_rev, lp_time
    else:
        return -np.inf, lp_time


def check_lp_feasibility_and_revenue(assignment, n, m, unit_cs, ship_cs, unit_us, Ns, opt_rev, stored_cs=None, stored_Rs=None):
    """
    Quickly check if given assignment is feasible under LP and return revenue

    Returns:
        tuple: (is_feasible, revenue_ratio, solve_time)
    """
    try:
        revenue_ratio, solve_time = revenue_ratio_LP(n, m, unit_cs, ship_cs, unit_us, Ns, opt_rev, assignment, stored_cs, stored_Rs)

        if revenue_ratio == -np.inf:
            return False, -np.inf, solve_time
        else:
            return True, revenue_ratio, solve_time

    except Exception as e:
        return False, -np.inf, 0.0


def generate_neighbor_assignments(current_assignment, prob, n, m):
    """
    Generate neighbor assignments for local search
    Based on add/drop operations guided by probability matrix

    Args:
        current_assignment: dict, current segment-bundle assignment
        prob: [m, n] probability matrix used to guide Add/Drop operations
        n: number of products
        m: number of customer segments

    Returns:
        tuple: (neighbors, timing_info)
            - neighbors: list of neighbor assignments
            - timing_info: dict with 'add_candidate_time', 'drop_candidate_time', 'neighbor_generation_time'
    """
    import time
    
    neighbors = []
    timing_info = {
        'add_candidate_time': 0.0,
        'drop_candidate_time': 0.0,
        'neighbor_generation_time': 0.0,
        'convert_time': 0.0
    }
    
    # Convert assignment to pred_assort for easier manipulation
    convert_start = time.time()
    current_pred_assort = assignment_to_pred_assort(current_assignment, n, m)
    timing_info['convert_time'] = time.time() - convert_start

    # Generate neighbors for each customer segment
    add_start = time.time()
    for k in range(m):
        pk = prob[k]  # Probability vector for this customer segment

        # Direction A: Add a product with highest probability among unselected products
        zero_idx = np.where(current_pred_assort[k] == 0)[0]
        if zero_idx.size > 0:  # Still have products that can be added
            add_j = zero_idx[np.argmax(pk[zero_idx])]
            neighbor_pred = current_pred_assort.copy()
            neighbor_pred[k, add_j] = 1
            neighbor_assignment = convert_pred_assort_to_assignment(neighbor_pred)
            neighbors.append(neighbor_assignment)
    timing_info['add_candidate_time'] = time.time() - add_start
    
    drop_start = time.time()
    for k in range(m):
        pk = prob[k]  # Probability vector for this customer segment

        # Direction B: Drop a product with lowest probability among selected products
        # Only consider products with prob >= 0.5 (consistent with Initial FCP threshold strategy)
        one_idx = np.where((current_pred_assort[k] == 1) & (pk >= 0.5))[0]
        if one_idx.size > 0:  # Still have products that can be dropped
            rm_j = one_idx[np.argmin(pk[one_idx])]
            neighbor_pred = current_pred_assort.copy()
            neighbor_pred[k, rm_j] = 0
            neighbor_assignment = convert_pred_assort_to_assignment(neighbor_pred)
            neighbors.append(neighbor_assignment)
    timing_info['drop_candidate_time'] = time.time() - drop_start
    
    # Neighbor generation time: time spent converting candidates to assignments
    # This is already included in add_candidate_time and drop_candidate_time,
    # so we set it to a minimal value for consistency with LS_Path_Test.py
    timing_info['neighbor_generation_time'] = 0.0

    return neighbors, timing_info


def local_search_with_lp(initial_pred_assort, prob, meta, max_iterations=50, tolerance=1e-3):
    """
    Main local search function based on LP solver

    Workflow:
    1. Initial MILP solve to get baseline assignment
    2. LP solve to get current best revenue
    3. Neighborhood search loop:
       - Generate all neighbors
       - LP feasibility check
       - Revenue improvement check
       - Update best solution
    4. Convert optimal assignment to pred_assort
    5. Final MILP solve (relaxed constraint space)

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

    # Step 1: Initial MILP solve to get feasible assignment
    print("Step 1: Initial MILP solve...")
    initial_milp_ratio, initial_milp_time, initial_assignment = revenue_ratio_with_optimal_bundle(
        n, m, unit_cs, ship_cs, unit_us, Ns, opt_rev, initial_pred_assort, stored_cs, stored_Rs)

    print(f"Initial MILP result: revenue ratio={initial_milp_ratio:.6f}, time={initial_milp_time:.4f}s")
    print(f"Initial assignment: {initial_assignment}")

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
        # Detailed timing breakdown
        'total_add_candidate_time': 0.0,
        'total_drop_candidate_time': 0.0,
        'total_neighbor_generation_time': 0.0,
        'total_lp_solve_time': 0.0,
        'total_neighbor_iteration_time': 0.0,  # Time spent in for loop (excluding LP)
    }

    # Step 3: Local Search loop
    print("Step 3: Local Search loop...")
    improved = True
    iteration = 0
    iteration_loop_start_time = time.time()  # Start timing iteration loop

    while improved and iteration < max_iterations:
        improved = False
        # iteration represents one search iteration
        iteration += 1
        iteration_start_time = time.time()  # Start timing this iteration

        # Generate neighbors
        neighbors, neighbor_timing = generate_neighbor_assignments(current_assignment, prob, n, m)
        
        # Accumulate candidate generation times
        search_info['total_add_candidate_time'] += neighbor_timing['add_candidate_time']
        search_info['total_drop_candidate_time'] += neighbor_timing['drop_candidate_time']
        search_info['total_neighbor_generation_time'] += neighbor_timing['neighbor_generation_time']

        # Evaluate each neighbor
        for neighbor_assignment in neighbors:
            # LP feasibility and revenue check
            is_feasible, neighbor_revenue, lp_time = check_lp_feasibility_and_revenue(
                neighbor_assignment, n, m, unit_cs, ship_cs, unit_us, Ns, opt_rev, stored_cs, stored_Rs)

            # lp_solver_calls represents one solve call
            search_info['lp_solver_calls'] += 1
            search_info['total_lp_solve_time'] += lp_time
            
            # Track non-LP time in the loop (variable assignment, condition check, etc.)
            search_info['total_neighbor_iteration_time'] += 0.000001  # Minimal overhead per iteration

            if is_feasible and neighbor_revenue > current_revenue + tolerance:
                current_assignment = neighbor_assignment
                current_revenue = neighbor_revenue
                improved = True
                search_info['improvements'] += 1
                search_info['search_path'].append(current_revenue)
                search_info['time_path'].append(time.time() - search_start_time)
                search_info['iteration_path'].append(iteration)

                print(f"Iteration {iteration}: Found improvement, revenue ratio={current_revenue:.6f}")
                break  # Greedy strategy: immediately accept improvement

        iteration_time = time.time() - iteration_start_time
        search_info['total_iteration_time'] += iteration_time  # Accumulate iteration time

        if not improved:
            print(f"Iteration {iteration}: No improvement found, search converged")

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
        n, m, unit_cs, ship_cs, unit_us, Ns, opt_rev, final_pred_assort, stored_cs, stored_Rs)[:2]  # Only take first two return values

    search_info['final_milp_revenue'] = final_milp_ratio
    search_info['final_milp_time'] = final_milp_time
    search_info['milp_solver_calls'] += 1
    search_info['total_improvement'] = final_milp_ratio - search_info['initial_milp_revenue']

    print(f"Final MILP result: revenue ratio={final_milp_ratio:.6f}, time={final_milp_time:.4f}s")
    print(f"Total improvement: {search_info['total_improvement']:.6f}")

    return final_pred_assort, final_milp_ratio, search_info


def predict_initial_bundles(dat, miscellaneous, model_path=None):
    """
    Use trained GCN model to generate initial pred_assort and probability matrix.
    model_path: optional; if None, uses script_dir/best_model_edge.pt.
    Supports two EdgeScoringGCN variants: this module's (l2r/r2l) and test_FCPLS_score's (convs/edge_updates).
    """
    n, segment_num, unit_cs, ship_cs, unit_us, Ns, opt_bundles, opt_prices, opt_rev, running_time, gap, stored_cs, stored_Rs = miscellaneous

    # Load trained GCN model
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if model_path is None:
        model_path = os.path.join(script_dir, "best_model_edge.pt")

    # Load checkpoint (may deserialize as test_FCP_LS.EdgeScoringGCN even when weights are convs/edge_updates)
    loaded = torch.load(model_path, map_location=device)

    # If checkpoint has convs/edge_updates but no l2r, it was saved by test_FCPLS_score-style model
    # (e.g. model_edge_4layer_seed10.pt: 4-layer EdgeScoringGCN with convs + edge_updates).
    # Rebuild that architecture and load state_dict so forward() runs correctly.
    if not getattr(loaded, 'l2r', None) and getattr(loaded, 'convs', None) is not None:
        try:
            import test_FCPLS_score as score_mod
        except ImportError:
            score_mod = None
        if score_mod is not None:
            state = loaded.state_dict()
            # Infer num_layers from state keys (e.g. convs.0.*, convs.1.*, ...); default 4 for 4-layer pt
            conv_keys = [k for k in state if k.startswith('convs.') and len(k.split('.')) >= 2]
            num_layers = 4  # model_edge_4layer_seed10.pt
            if conv_keys:
                indices = []
                for k in conv_keys:
                    part = k.split('.')[1]
                    if part.isdigit():
                        indices.append(int(part))
                if indices:
                    num_layers = max(indices) + 1
            model = score_mod.EdgeScoringGCN(
                in_channels=4,
                hidden_channels=128,
                num_layers=num_layers,
                edge_dim=1,
                dropout=0.5,
            )
            model.load_state_dict(state, strict=True)
            loaded = model

    model = loaded
    model.to(device)
    model.eval()

    # Move data to device
    dat = dat.to(device)

    # GCN inference (supports both node-level and edge-scoring models)
    raw_out = model(dat)

    if isinstance(raw_out, dict):
        # EdgeScoringGCN-style output
        if 'logit_matrix' in raw_out:
            # shape (n, m)
            logits_nm = raw_out['logit_matrix'].detach().cpu().numpy()
        elif 'edge_logits' in raw_out:
            s = raw_out['edge_logits'].detach().cpu().numpy()
            logits_nm = s.reshape(n, segment_num)
        else:
            raise ValueError('Unexpected model output keys for edge scoring: ' + ','.join(raw_out.keys()))

        # Convert logits to binary assortment per segment: shape (m, n)
        initial_pred_assort = (logits_nm.T >= 0.0).astype(int)
    
    logits_tensor = torch.tensor(logits_nm)       # Convert to tensor for computation
    prob = torch.sigmoid(logits_tensor).numpy()  # (n, m) probability matrix

    print(f"GCN generated pred_assort:")
    for k in range(segment_num):
        bundle_binary = ''.join(map(str, initial_pred_assort[k, :]))
        bundle_idx = int(bundle_binary, 2)
        print(f"  Segment {k}: {bundle_binary} (Bundle {bundle_idx})")

    return initial_pred_assort, prob.T



def solve_initial_milp(initial_pred, miscellaneous):
    """
    Use MILP solver to get initial revenue ratio
    """
    n, segment_num, unit_cs, ship_cs, unit_us, Ns, opt_bundles, opt_prices, opt_rev, running_time, gap, stored_cs, stored_Rs = miscellaneous

    initial_milp_ratio, _, _ = revenue_ratio_with_optimal_bundle(
        n, segment_num, unit_cs, ship_cs, unit_us, Ns, opt_rev, initial_pred, stored_cs, stored_Rs)

    return initial_milp_ratio


def plot_search_paths(all_search_paths, save_dir):
    """
    Plot average revenue ratio change charts for all samples (including iteration and time dimensions)
    """
    print("\n=== GENERATING AVERAGE SEARCH PATH PLOTS ===")

    # Filter out samples with improvements
    improved_paths = [path for path in all_search_paths if path['improvement'] > 0]

    if len(improved_paths) == 0:
        print("No samples with improvements found. Skipping plots.")
        return

    print(f"Computing average search paths from {len(improved_paths)} samples with improvements...")

    # Calculate average revenue ratio paths
    max_iterations = max(len(path['iteration_path']) for path in improved_paths)
    max_time = max(path['time_path'][-1] for path in improved_paths if len(path['time_path']) > 0)

    # Calculate average values for iteration dimension
    iteration_avg_revenue = []
    iteration_counts = []

    for iter_idx in range(max_iterations):
        revenues_at_iter = []
        for path in improved_paths:
            if iter_idx < len(path['iteration_path']):
                revenues_at_iter.append(path['revenue_path'][iter_idx])

        if revenues_at_iter:
            iteration_avg_revenue.append(np.mean(revenues_at_iter))
            iteration_counts.append(len(revenues_at_iter))
        else:
            break

    # Calculate average values for time dimension (using time intervals)
    time_intervals = np.linspace(0, max_time, 50)  # 50 time points
    time_avg_revenue = []

    for t in time_intervals:
        revenues_at_time = []
        for path in improved_paths:
            # Find revenue ratio closest to time t
            time_path = path['time_path']
            revenue_path = path['revenue_path']

            # Find the largest time point less than or equal to t
            valid_indices = [i for i, time_val in enumerate(time_path) if time_val <= t]
            if valid_indices:
                last_valid_idx = max(valid_indices)
                revenues_at_time.append(revenue_path[last_valid_idx])

        if revenues_at_time:
            time_avg_revenue.append(np.mean(revenues_at_time))
        else:
            time_avg_revenue.append(np.nan)

    # Create charts
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))

    # Chart 1: Average Revenue Ratio vs Iteration
    ax1.set_title('Average Revenue Ratio vs Iteration (Mixed MILP-LP)', fontsize=14, fontweight='bold')
    ax1.set_xlabel('Iteration', fontsize=12)
    ax1.set_ylabel('Average Revenue Ratio', fontsize=12)
    ax1.grid(True, alpha=0.3)

    iterations = list(range(len(iteration_avg_revenue)))
    ax1.plot(iterations, iteration_avg_revenue, 'o-', color='blue', linewidth=3,
             markersize=8, label=f'Average ({len(improved_paths)} samples)')

    iteration_std = []
    for iter_idx in range(len(iteration_avg_revenue)):
        revenues_at_iter = []
        for path in improved_paths:
            if iter_idx < len(path['iteration_path']):
                revenues_at_iter.append(path['revenue_path'][iter_idx])
        if len(revenues_at_iter) > 1:
            iteration_std.append(np.std(revenues_at_iter) / np.sqrt(len(revenues_at_iter)))
        else:
            iteration_std.append(0)

    ax1.fill_between(iterations,
                     np.array(iteration_avg_revenue) - np.array(iteration_std),
                     np.array(iteration_avg_revenue) + np.array(iteration_std),
                     alpha=0.3, color='blue', label='±1 SE')

    ax1.legend()

    # Chart 2: Average Revenue Ratio vs Time
    ax2.set_title('Average Revenue Ratio vs Time (Mixed MILP-LP)', fontsize=14, fontweight='bold')
    ax2.set_xlabel('Time (seconds)', fontsize=12)
    ax2.set_ylabel('Average Revenue Ratio', fontsize=12)
    ax2.grid(True, alpha=0.3)

    valid_mask = ~np.isnan(time_avg_revenue)
    valid_times = time_intervals[valid_mask]
    valid_revenues = np.array(time_avg_revenue)[valid_mask]

    ax2.plot(valid_times, valid_revenues, 'o-', color='red', linewidth=3,
             markersize=6, label=f'Average ({len(improved_paths)} samples)')

    ax2.legend()

    # Adjust layout
    plt.tight_layout()

    # Save chart
    plot_path = os.path.join(save_dir, 'local_search_mix_average_convergence_plots_small_n.png')
    plt.savefig(plot_path, dpi=300, bbox_inches='tight')
    print(f"Average search path plots saved to: {plot_path}")

    # Close chart to free memory
    plt.close()




def evaluate_single_dataset(test_data_path, dataset_name):

    print(f"\n=== Evaluating Dataset: {dataset_name} ===")
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
        # Windows compatible path joining
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

    # Limit each dataset to first 20 samples for testing
    max_samples_per_dataset = 1000
    actual_test_count = min(sample_num, max_samples_per_dataset)
    if sample_num > max_samples_per_dataset:
        print(f"Limiting test to first {actual_test_count} samples out of {sample_num} total samples.")
        test_dataset = test_dataset[:actual_test_count]
        miscellaneous_dataset = miscellaneous_dataset[:actual_test_count]

    # Evaluate model
    results = []
    all_search_paths = []  # Collect search paths from all samples for plotting
    # Timing collectors for averages
    initial_milp_times = []
    iteration_times = []
    final_milp_times = []
    iterations_counts = []
    per_iter_times = []
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

            # Step 3: Mixed MILP-LP local search optimization
            local_search_start = time.time()
            best_pred, best_rev, search_info = local_search_with_lp(
                initial_pred, prob, miscellaneous, max_iterations, tolerance
            )
            local_search_time = time.time() - local_search_start

            # Collect timing metrics for averages
            initial_milp_times.append(initial_milp_time)
            # Use total_iteration_time from search_info for accurate iteration time (excluding initial/final MILP and other overhead)
            total_iteration_time = search_info.get('total_iteration_time', local_search_time)
            iteration_times.append(total_iteration_time)
            final_milp_times.append(search_info.get('final_milp_time', 0.0))
            iterations_counts.append(search_info.get('iterations', 0))
            iters = max(1, search_info.get('iterations', 0))
            per_iter_times.append(total_iteration_time / iters)
            
            # Collect detailed timing breakdown
            add_times.append(search_info.get('total_add_candidate_time', 0.0))
            drop_times.append(search_info.get('total_drop_candidate_time', 0.0))
            neighbor_gen_times.append(search_info.get('total_neighbor_generation_time', 0.0))
            lp_solve_times.append(search_info.get('total_lp_solve_time', 0.0))
            neighbor_iter_times.append(search_info.get('total_neighbor_iteration_time', 0.0))

            # Total strategy time
            total_time = time.time() - strategy_start_time

            # Calculate time ratio with respect to default running time
            time_ratio = total_time / running_time if running_time > 0 else float('inf')

            # Store detailed results
            results.append([
                n, best_rev, time_ratio, total_time, running_time,
                threshold_time, initial_milp_time, local_search_time,
                initial_revenue, search_info['total_improvement'],
                search_info['iterations'], search_info['improvements'],
                search_info['lp_solver_calls'], search_info['milp_solver_calls'],
                # Detailed timing breakdown
                search_info.get('total_iteration_time', 0.0),
                search_info.get('total_add_candidate_time', 0.0),
                search_info.get('total_drop_candidate_time', 0.0),
                search_info.get('total_neighbor_generation_time', 0.0),
                search_info.get('total_lp_solve_time', 0.0),
                search_info.get('total_neighbor_iteration_time', 0.0)
            ])

            # Collect search path data for plotting
            search_path_data = {
                'sample_id': i,
                'n_products': n,
                'revenue_path': search_info['search_path'],
                'time_path': search_info['time_path'],
                'iteration_path': search_info['iteration_path'],
                'initial_revenue': search_info['initial_lp_revenue'],
                'final_revenue': best_rev,
                'improvement': search_info['total_improvement'],
                'dataset_name': dataset_name
            }
            all_search_paths.append(search_path_data)

        except Exception as e:
            print(f"Error evaluating sample {i}: {e}")
            continue

    # Compute averages (safe even if empty)
    def _avg(arr):
        return float(np.mean(arr)) if len(arr) > 0 else 0.0

    return {
        'dataset_name': dataset_name,
        'results': np.array(results) if results else np.array([]),
        'search_paths': all_search_paths,
        'sample_count': len(results),
        # Timing summaries
        'avg_initial_milp_time': _avg(initial_milp_times),
        'avg_iteration_time': _avg(iteration_times),
        'avg_final_milp_time': _avg(final_milp_times),
        'avg_iterations': _avg(iterations_counts),
        'avg_per_iter_time': _avg(per_iter_times),
        # Detailed timing breakdown
        'avg_add_candidate_time': _avg(add_times),
        'avg_drop_candidate_time': _avg(drop_times),
        'avg_neighbor_generation_time': _avg(neighbor_gen_times),
        'avg_lp_solve_time': _avg(lp_solve_times),
        'avg_neighbor_iteration_time': _avg(neighbor_iter_times),
    }


def plot_combined_search_paths(all_dataset_results, save_dir):
    print("\n=== GENERATING COMBINED SEARCH PATH PLOTS ===")

    # Filter out samples with improvements and group by dataset
    dataset_improved_paths = {}

    for dataset_result in all_dataset_results:
        if dataset_result is None:
            continue

        dataset_name = dataset_result['dataset_name']
        search_paths = dataset_result['search_paths']

        # Filter out samples with improvements
        improved_paths = [path for path in search_paths if path['improvement'] > 0]

        if len(improved_paths) > 0:
            dataset_improved_paths[dataset_name] = improved_paths
            print(f"{dataset_name}: {len(improved_paths)} samples with improvements")

    if len(dataset_improved_paths) == 0:
        print("No datasets with improvements found. Skipping plots.")
        return

    # Create charts
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(20, 8))

    # Define colors and marker styles
    colors = ['blue', 'red', 'green', 'orange', 'purple']
    markers = ['o', 's', '^', 'D', 'v']

    dataset_names = list(dataset_improved_paths.keys())

    # Chart 1: Average Revenue Ratio vs Iteration
    ax1.set_title('Average Revenue Ratio vs Iteration (Mixed MILP-LP)\nComparison Across Datasets',
                  fontsize=14, fontweight='bold')
    ax1.set_xlabel('Iteration', fontsize=12)
    ax1.set_ylabel('Average Revenue Ratio', fontsize=12)
    ax1.grid(True, alpha=0.3)

    # Chart 2: Average Revenue Ratio vs Time
    ax2.set_title('Average Revenue Ratio vs Time (Mixed MILP-LP)\nComparison Across Datasets',
                  fontsize=14, fontweight='bold')
    ax2.set_xlabel('Time (seconds)', fontsize=12)
    ax2.set_ylabel('Average Revenue Ratio', fontsize=12)
    ax2.grid(True, alpha=0.3)

    for idx, (dataset_name, improved_paths) in enumerate(dataset_improved_paths.items()):
        color = colors[idx % len(colors)]
        marker = markers[idx % len(markers)]

        # Calculate average revenue ratio path for this dataset
        max_iterations = max(len(path['iteration_path']) for path in improved_paths)
        max_time = max(path['time_path'][-1] for path in improved_paths if len(path['time_path']) > 0)

        # Calculate average values for iteration dimension
        iteration_avg_revenue = []
        for iter_idx in range(max_iterations):
            revenues_at_iter = []
            for path in improved_paths:
                if iter_idx < len(path['iteration_path']):
                    revenues_at_iter.append(path['revenue_path'][iter_idx])

            if revenues_at_iter:
                iteration_avg_revenue.append(np.mean(revenues_at_iter))
            else:
                break

        # Calculate average values for time dimension (using time intervals)
        time_intervals = np.linspace(0, max_time, 50)  # 50 time points
        time_avg_revenue = []

        for t in time_intervals:
            revenues_at_time = []
            for path in improved_paths:
                # Find revenue ratio closest to time t
                time_path = path['time_path']
                revenue_path = path['revenue_path']

                # Find the largest time point less than or equal to t
                valid_indices = [i for i, time_val in enumerate(time_path) if time_val <= t]
                if valid_indices:
                    last_valid_idx = max(valid_indices)
                    revenues_at_time.append(revenue_path[last_valid_idx])

            if revenues_at_time:
                time_avg_revenue.append(np.mean(revenues_at_time))
            else:
                time_avg_revenue.append(np.nan)

        # Plot iteration chart
        iterations = list(range(len(iteration_avg_revenue)))
        ax1.plot(iterations, iteration_avg_revenue, marker=marker, color=color, linewidth=2,
                 markersize=6, label=f'{dataset_name} ({len(improved_paths)} samples)')

        # Plot time chart
        valid_mask = ~np.isnan(time_avg_revenue)
        valid_times = time_intervals[valid_mask]
        valid_revenues = np.array(time_avg_revenue)[valid_mask]

        ax2.plot(valid_times, valid_revenues, marker=marker, color=color, linewidth=2,
                 markersize=4, label=f'{dataset_name} ({len(improved_paths)} samples)')

    # Add legends
    ax1.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    ax2.legend(bbox_to_anchor=(1.05, 1), loc='upper left')

    # Adjust layout
    plt.tight_layout()

    # Save chart
    plot_path = os.path.join(save_dir, 'combined_local_search_mix_convergence_plots.png')
    plt.savefig(plot_path, dpi=300, bbox_inches='tight')
    print(f"Combined search path plots saved to: {plot_path}")

    # Close chart to free memory
    plt.close()


def main():
    """
    Main function: evaluate mixed MILP-LP Local Search strategy on datasets and generate integrated charts
    """
    print("=" * 80)
    print("Mixed MILP-LP Local Search Strategy Evaluation - Multiple Datasets")
    print("=" * 80)

    # Set paths (Windows compatible)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = script_dir
    model_path = os.path.join(script_dir, "best_model_edge.pt")
    dataset_base_dir = os.path.join(script_dir, "dataset2_4_2026")

    datasets = {
        'test_m10n10_1e_3': os.path.join(dataset_base_dir, 'test_m10n10_1e_3'),
        'test_m20n10_1e_3': os.path.join(dataset_base_dir, 'test_m20n10_1e_3'),
        'test_m30n10_1e_3': os.path.join(dataset_base_dir, 'test_m30n10_1e_3'),
        'test_BSP_m10n20_1e_3': os.path.join(dataset_base_dir, 'test_BSP_m10n20_1e_3'),
        'test_BSP_m10n40_1e_3': os.path.join(dataset_base_dir, 'test_BSP_m10n40_1e_3'),
        'test_BSP_m20n20_1e_3': os.path.join(dataset_base_dir, 'test_BSP_m20n20_1e_3'),
    }

    print(f"Model path: {model_path}")
    print(f"Base directory: {base_dir}")
    print(f"Datasets to evaluate: {list(datasets.keys())}")

    # Evaluate each dataset
    all_dataset_results = []

    for dataset_name, test_data_path in datasets.items():
        dataset_result = evaluate_single_dataset(test_data_path, dataset_name)
        all_dataset_results.append(dataset_result)

        # Save results for individual dataset
        if dataset_result is not None and len(dataset_result['results']) > 0:
            results = dataset_result['results']
            result_path = os.path.join(base_dir, f'test_result_local_search_mix_{dataset_name}.csv')

            # Save with detailed headers
            header = ('n_products,revenue_ratio,runtime_ratio,total_time,base_running_time,'
                      'threshold_time,initial_milp_time,local_search_time,'
                      'initial_revenue,improvement,iterations,improvements,lp_solver_calls,milp_solver_calls,'
                      'total_iteration_time,add_candidate_time,drop_candidate_time,'
                      'neighbor_generation_time,lp_solve_time,neighbor_iteration_time')
            np.savetxt(result_path, results, delimiter=',', header=header, comments='')
            print(f"Results for {dataset_name} saved to: {result_path}")

    # Print timing summaries per dataset
    for dataset_result in all_dataset_results:
        if dataset_result is None:
            continue
        print(f"\n--- Timing Averages for {dataset_result['dataset_name']} ---")
        print(f"Avg initial MILP time: {dataset_result.get('avg_initial_milp_time', 0.0):.4f} s")
        print(f"Avg total iteration time: {dataset_result.get('avg_iteration_time', 0.0):.4f} s  (sum of all iterations, includes all neighbor LP calls)")
        print(f"Avg final MILP time:  {dataset_result.get('avg_final_milp_time', 0.0):.4f} s")
        print(f"Avg iterations:       {dataset_result.get('avg_iterations', 0.0):.2f}")
        print(f"Avg per-iter time:    {dataset_result.get('avg_per_iter_time', 0.0):.4f} s  (single iteration time, includes evaluating all neighbors until improvement found)")

    # Generate integrated search path charts
    plot_combined_search_paths(all_dataset_results, base_dir)

    # Print overall statistics
    print(f'\n=== OVERALL SUMMARY ===')
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

                improvement_rate = 100*improvements/sample_count if sample_count > 0 else 0
                print(f"{dataset_name}: {sample_count} samples, {improvements} with improvements "
                      f"({improvement_rate:.1f}%)")
                
                # Revenue ratio statistics
                print(f"  Average revenue ratio: {np.mean(results[:, 1]):.4f}")
                print(f"  Std revenue ratio: {np.std(results[:, 1]):.4f}")
                print(f"  Min revenue ratio: {np.min(results[:, 1]):.4f}")
                print(f"  Max revenue ratio: {np.max(results[:, 1]):.4f}")
                
                # Runtime ratio statistics
                print(f"  Average runtime ratio: {np.mean(results[:, 2]):.4f}")
                print(f"  Std runtime ratio: {np.std(results[:, 2]):.4f}")
                print(f"  Min runtime ratio: {np.min(results[:, 2]):.4f}")
                print(f"  Max runtime ratio: {np.max(results[:, 2]):.4f}")
                
                # Total time statistics
                print(f"  Average time: {np.mean(results[:, 3]):.3f} seconds")
                print(f"  Min time: {np.min(results[:, 3]):.3f} seconds")
                print(f"  Max time: {np.max(results[:, 3]):.3f} seconds")
                
                print(f"  Average improvement: {np.mean(results[:, 9]):.4f}")

    print(f"\nTotal samples evaluated: {total_samples}")
    print(f"Total samples with improvements: {total_improvements}")
    if total_samples > 0:
        print(f"Overall improvement rate: {100*total_improvements/total_samples:.1f}%")

    print("=== Mixed MILP-LP Local Search Multi-Dataset Test completed ===")


if __name__ == "__main__":
    main()
