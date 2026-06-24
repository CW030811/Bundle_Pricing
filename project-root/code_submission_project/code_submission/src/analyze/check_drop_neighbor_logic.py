"""
检查Drop Neighbor逻辑：为什么会出现prob < 0.5的product？
"""
import os
import numpy as np
import msgpack
import msgpack_numpy as mnp
import torch
from test_FCP_LS import (
    EdgeScoringGCN,
    process_data,
    convert_pred_assort_to_assignment,
    assignment_to_pred_assort,
    predict_initial_bundles,
    revenue_ratio_with_optimal_bundle,
)

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
    print("检查Drop Neighbor逻辑")
    print("=" * 80)
    
    print(f"\n1. Initial pred_assort (基于logit >= 0.0，即prob >= 0.5):")
    for k in range(segment_num):
        bundle_binary = ''.join(str(int(initial_pred_assort[k, j])) for j in range(n))
        bundle_idx = int(bundle_binary, 2)
        print(f"  Segment {k}: {bundle_binary} (Bundle {bundle_idx})")
        # 检查每个product的prob
        for j in range(n):
            if initial_pred_assort[k, j] == 1:
                print(f"    Product {j}: prob={prob[k, j]:.4f} {'✓' if prob[k, j] >= 0.5 else '✗ ERROR!'}")
    
    # Initial MILP
    print(f"\n2. Initial MILP求解...")
    initial_milp_ratio, initial_milp_time, initial_assignment = revenue_ratio_with_optimal_bundle(
        n, segment_num, unit_cs, ship_cs, unit_us, Ns, opt_rev, initial_pred_assort, stored_cs, stored_Rs)
    
    print(f"  Initial Assignment: {initial_assignment}")
    
    # 转换为pred_assort
    initial_assignment_pred_assort = assignment_to_pred_assort(initial_assignment, n, segment_num)
    
    print(f"\n3. Initial Assignment对应的pred_assort:")
    for k in range(segment_num):
        bundle_binary = ''.join(str(int(initial_assignment_pred_assort[k, j])) for j in range(n))
        bundle_idx = int(bundle_binary, 2)
        print(f"  Segment {k}: {bundle_binary} (Bundle {bundle_idx})")
        # 检查每个product的prob
        for j in range(n):
            if initial_assignment_pred_assort[k, j] == 1:
                prob_val = prob[k, j]
                status = '✓' if prob_val >= 0.5 else '✗ ERROR!'
                print(f"    Product {j}: prob={prob_val:.4f} {status}")
    
    # 检查是否有prob < 0.5的product出现在assignment中
    print(f"\n4. 检查是否有prob < 0.5的product出现在Initial Assignment中:")
    found_low_prob = False
    for k in range(segment_num):
        for j in range(n):
            if initial_assignment_pred_assort[k, j] == 1 and prob[k, j] < 0.5:
                print(f"  ✗ Segment {k}, Product {j}: prob={prob[k, j]:.4f} < 0.5")
                found_low_prob = True
    
    if not found_low_prob:
        print(f"  ✓ 所有在Initial Assignment中的product的prob都 >= 0.5")
    else:
        print(f"\n  问题：MILP选择的bundle包含prob < 0.5的product！")
        print(f"  这可能是因为MILP从predicted_bundles中选择，而predicted_bundles可能包含")
        print(f"  不在initial_pred_assort中的bundle（如果多个segment有相同的bundle）。")
    
    # 检查predicted_bundles
    print(f"\n5. 检查predicted_bundles的生成逻辑:")
    bundle_dic = {}
    for k in range(segment_num):
        bundle_binary = initial_pred_assort[k, :]
        bundle_idx = int(''.join(map(str, bundle_binary.tolist())), 2)
        if bundle_idx in bundle_dic:
            bundle_dic[bundle_idx].append(k)
        else:
            bundle_dic[bundle_idx] = [k]
    
    predicted_bundles = list(bundle_dic.keys())
    print(f"  predicted_bundles数量: {len(predicted_bundles)}")
    print(f"  predicted_bundles: {predicted_bundles}")
    
    # 检查每个predicted_bundle是否包含prob < 0.5的product
    print(f"\n6. 检查每个predicted_bundle是否包含prob < 0.5的product:")
    for bundle_idx in predicted_bundles:
        bundle_binary = format(bundle_idx, f'0{n}b')
        bundle_array = np.array([int(x) for x in bundle_binary])
        
        # 检查这个bundle是否包含prob < 0.5的product
        low_prob_products = []
        for j in range(n):
            if bundle_array[j] == 1:
                # 检查所有segment中这个product的prob
                min_prob = min(prob[k, j] for k in range(segment_num))
                if min_prob < 0.5:
                    low_prob_products.append((j, min_prob))
        
        if low_prob_products:
            print(f"  Bundle {bundle_idx} ({bundle_binary}): 包含prob < 0.5的product:")
            for j, min_p in low_prob_products:
                print(f"    Product {j}: min_prob={min_p:.4f}")
        else:
            print(f"  Bundle {bundle_idx} ({bundle_binary}): ✓ 所有product的prob都 >= 0.5")


if __name__ == "__main__":
    main()

