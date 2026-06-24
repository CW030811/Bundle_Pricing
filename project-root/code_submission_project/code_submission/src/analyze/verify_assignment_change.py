"""
验证Iteration 1到Iteration 2的assignment变化
根据逻辑，只应该改变Seg9, Prod7从0到1，其他不应该变化
"""
import os
import numpy as np
import msgpack
import msgpack_numpy as mnp
import torch
from math import ceil, sqrt
from test_FCP_LS import (
    EdgeScoringGCN,
    process_data,
    convert_pred_assort_to_assignment,
    assignment_to_pred_assort,
    predict_initial_bundles,
    revenue_ratio_with_optimal_bundle,
    revenue_ratio_LP,
)

def generate_neighbor_assignments_global_topk(current_assignment, prob, n, m):
    """Generate neighbor assignments using global Top-K strategy"""
    current_pred_assort = assignment_to_pred_assort(current_assignment, n, m)
    K = int(ceil(sqrt(m)))
    
    neighbor_info = []
    
    # Step 1: Generate Add candidates
    add_candidates = []
    for k in range(m):
        for j in range(n):
            if current_pred_assort[k, j] == 0:
                score_add = prob[k, j]
                add_candidates.append((k, j, score_add))
    
    add_candidates.sort(key=lambda x: x[2], reverse=True)
    add_list = add_candidates[:K]
    
    return add_list, current_pred_assort

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 加载数据
    sample_file = os.path.join(script_dir, "Dataset", "m10_n10", "sample_data_100_size_10.msgpack")
    with open(sample_file, 'rb') as f:
        data = msgpack.load(f, object_hook=mnp.decode, strict_map_key=False)
    
    dat = data['data']
    meta = data['miscellaneous']
    n, segment_num, unit_cs, ship_cs, unit_us, Ns, opt_bundles, opt_prices, opt_rev, running_time, gap, stored_cs, stored_Rs = meta
    
    # 加载模型
    model_path = os.path.join(script_dir, "best_model_edge.pt")
    model = EdgeScoringGCN(10, 64, 1)
    model.load_state_dict(torch.load(model_path, map_location='cpu'))
    model.eval()
    
    # 生成初始预测
    initial_pred_assort, prob = predict_initial_bundles(dat, model, n, segment_num)
    
    print("=" * 80)
    print("验证Iteration 1到Iteration 2的assignment变化")
    print("=" * 80)
    
    # Initial MILP
    print(f"\n1. Initial MILP求解...")
    initial_milp_ratio, initial_milp_time, initial_assignment = revenue_ratio_with_optimal_bundle(
        n, segment_num, unit_cs, ship_cs, unit_us, Ns, opt_rev, initial_pred_assort, stored_cs, stored_Rs)
    
    initial_assignment_pred_assort = assignment_to_pred_assort(initial_assignment, n, segment_num)
    
    print(f"  Initial Assignment: {initial_assignment}")
    print(f"  Segment 1 Bundle: {initial_assignment[1]} = {format(initial_assignment[1], '010b')}")
    print(f"  Segment 1, Product 9: {initial_assignment_pred_assort[1, 9]} (prob={prob[1, 9]:.4f})")
    
    # Initial LP
    print(f"\n2. Initial LP求解...")
    current_revenue, initial_lp_time = revenue_ratio_LP(n, segment_num, unit_cs, ship_cs, unit_us, Ns, opt_rev, initial_assignment, stored_cs, stored_Rs)
    current_assignment = initial_assignment.copy()
    
    print(f"  Current Revenue: {current_revenue:.6f}")
    print(f"  Current Assignment: {current_assignment}")
    
    # Iteration 1: 检查Add candidates
    print(f"\n3. Iteration 1: 检查Add candidates...")
    add_list_1, pred_assort_1 = generate_neighbor_assignments_global_topk(current_assignment, prob, n, segment_num)
    print(f"  Segment 1, Product 9在current_pred_assort中的状态: {pred_assort_1[1, 9]}")
    print(f"  Top-4 Add candidates:")
    for idx, (k, j, score) in enumerate(add_list_1):
        print(f"    {idx+1}. Seg{k}, Prod{j}, Score={score:.4f}")
    
    seg1_prod9_in_list_1 = any((k == 1 and j == 9) for k, j, _ in add_list_1)
    print(f"  Seg1, Prod9在Add candidates中: {seg1_prod9_in_list_1}")
    
    # 模拟Iteration 1接受Neighbor 1 (Add: Seg9, Prod7)
    print(f"\n4. 模拟Iteration 1接受Neighbor 1 (Add: Seg9, Prod7)...")
    new_pred_assort = pred_assort_1.copy()
    new_pred_assort[9, 7] = 1
    new_assignment = convert_pred_assort_to_assignment(new_pred_assort)
    
    print(f"  更新后的Assignment: {new_assignment}")
    print(f"  Segment 1 Bundle: {new_assignment[1]} = {format(new_assignment[1], '010b')}")
    print(f"  Segment 1, Product 9: {new_pred_assort[1, 9]}")
    print(f"  Segment 9, Product 7: {new_pred_assort[9, 7]}")
    
    # 检查变化
    print(f"\n5. 检查assignment变化:")
    for k in range(segment_num):
        if initial_assignment[k] != new_assignment[k]:
            print(f"  Segment {k}: {initial_assignment[k]} -> {new_assignment[k]}")
            print(f"    {format(initial_assignment[k], '010b')} -> {format(new_assignment[k], '010b')}")
    
    # Iteration 2: 检查Add candidates
    print(f"\n6. Iteration 2: 检查Add candidates...")
    add_list_2, pred_assort_2 = generate_neighbor_assignments_global_topk(new_assignment, prob, n, segment_num)
    print(f"  Segment 1, Product 9在current_pred_assort中的状态: {pred_assort_2[1, 9]}")
    print(f"  Top-4 Add candidates:")
    for idx, (k, j, score) in enumerate(add_list_2):
        print(f"    {idx+1}. Seg{k}, Prod{j}, Score={score:.4f}")
    
    seg1_prod9_in_list_2 = any((k == 1 and j == 9) for k, j, _ in add_list_2)
    print(f"  Seg1, Prod9在Add candidates中: {seg1_prod9_in_list_2}")
    
    # 结论
    print(f"\n7. 结论:")
    if initial_assignment_pred_assort[1, 9] == 1:
        if pred_assort_2[1, 9] == 0:
            print(f"  ✗ 错误：Seg1, Prod9从1变成了0，但逻辑上只应该改变Seg9, Prod7")
        else:
            print(f"  ✓ 正确：Seg1, Prod9保持为1，不会出现在Add candidates中")
    else:
        print(f"  ✓ 正确：Seg1, Prod9在Initial Assignment中就是0，所以会出现在Add candidates中")


if __name__ == "__main__":
    main()

