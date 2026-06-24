"""
检查为什么Iteration 1中没有出现Seg1, Prod9，但Iteration 2中出现了
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
    
    print(f"  Add candidates (Top-{K}):")
    for idx, (k, j, score) in enumerate(add_list):
        print(f"    {idx+1}. Seg{k}, Prod{j}, Score={score:.4f}")
    
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
    print("检查Seg1, Prod9在Iteration 1和Iteration 2中的状态")
    print("=" * 80)
    
    print(f"\n1. Initial Prediction (GCN预测):")
    print(f"  Segment 1: {''.join(str(int(initial_pred_assort[1, j])) for j in range(n))}")
    print(f"  Segment 1, Product 9: {initial_pred_assort[1, 9]} (prob={prob[1, 9]:.4f})")
    
    # Initial MILP
    print(f"\n2. Initial MILP求解...")
    initial_milp_ratio, initial_milp_time, initial_assignment = revenue_ratio_with_optimal_bundle(
        n, segment_num, unit_cs, ship_cs, unit_us, Ns, opt_rev, initial_pred_assort, stored_cs, stored_Rs)
    
    initial_assignment_pred_assort = assignment_to_pred_assort(initial_assignment, n, segment_num)
    
    print(f"  Initial Assignment (MILP结果):")
    print(f"  Segment 1: {''.join(str(int(initial_assignment_pred_assort[1, j])) for j in range(n))}")
    print(f"  Segment 1, Product 9: {initial_assignment_pred_assort[1, 9]} (prob={prob[1, 9]:.4f})")
    
    # 检查差异
    if initial_pred_assort[1, 9] != initial_assignment_pred_assort[1, 9]:
        print(f"  ⚠️ 差异：Initial Prediction中Seg1, Prod9={initial_pred_assort[1, 9]}，但Initial Assignment中={initial_assignment_pred_assort[1, 9]}")
    
    # Iteration 1: 使用initial_assignment
    print(f"\n3. Iteration 1 (使用Initial Assignment):")
    add_list_1, pred_assort_1 = generate_neighbor_assignments_global_topk(initial_assignment, prob, n, segment_num)
    print(f"  Segment 1, Product 9在current_pred_assort中的状态: {pred_assort_1[1, 9]}")
    print(f"  Segment 1, Product 9的prob: {prob[1, 9]:.4f}")
    
    # 检查Seg1, Prod9是否在Add candidates中
    seg1_prod9_in_list = any((k == 1 and j == 9) for k, j, _ in add_list_1)
    if seg1_prod9_in_list:
        idx = next(i for i, (k, j, _) in enumerate(add_list_1) if k == 1 and j == 9)
        print(f"  ✓ Seg1, Prod9在Add candidates中，排名: {idx+1}")
    else:
        print(f"  ✗ Seg1, Prod9不在Add candidates中")
        if pred_assort_1[1, 9] == 1:
            print(f"    原因：Seg1, Prod9已经在current_pred_assort中（值为1），所以不在Add candidates中")
        else:
            # 检查所有Add candidates，看看Seg1, Prod9的prob排名
            all_add_candidates = []
            for k in range(segment_num):
                for j in range(n):
                    if pred_assort_1[k, j] == 0:
                        all_add_candidates.append((k, j, prob[k, j]))
            all_add_candidates.sort(key=lambda x: x[2], reverse=True)
            seg1_prod9_rank = next((i+1 for i, (k, j, _) in enumerate(all_add_candidates) if k == 1 and j == 9), None)
            K = int(ceil(sqrt(segment_num)))
            if seg1_prod9_rank:
                print(f"    原因：Seg1, Prod9的prob排名是{seg1_prod9_rank}，但只取Top-{K}，所以不在Add candidates中")
            else:
                print(f"    原因：无法找到Seg1, Prod9在Add candidates中的排名")
    
    # 模拟Iteration 1接受Neighbor 1 (Add: Seg9, Prod7)
    print(f"\n4. 模拟Iteration 1接受Neighbor 1 (Add: Seg9, Prod7)...")
    new_pred_assort = pred_assort_1.copy()
    new_pred_assort[9, 7] = 1
    new_assignment = convert_pred_assort_to_assignment(new_pred_assort)
    
    # Iteration 2: 使用更新后的assignment
    print(f"\n5. Iteration 2 (使用更新后的Assignment):")
    add_list_2, pred_assort_2 = generate_neighbor_assignments_global_topk(new_assignment, prob, n, segment_num)
    print(f"  Segment 1, Product 9在current_pred_assort中的状态: {pred_assort_2[1, 9]}")
    
    # 检查Seg1, Prod9是否在Add candidates中
    seg1_prod9_in_list_2 = any((k == 1 and j == 9) for k, j, _ in add_list_2)
    if seg1_prod9_in_list_2:
        idx = next(i for i, (k, j, _) in enumerate(add_list_2) if k == 1 and j == 9)
        print(f"  ✓ Seg1, Prod9在Add candidates中，排名: {idx+1}")
        print(f"    原因：Seg1, Prod9在Iteration 2时状态为0，且prob值足够高，进入了Top-{K}")
    else:
        print(f"  ✗ Seg1, Prod9不在Add candidates中")


if __name__ == "__main__":
    main()

