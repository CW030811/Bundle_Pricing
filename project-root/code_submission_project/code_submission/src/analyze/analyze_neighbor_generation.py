"""
分析为什么每次迭代生成的neighbors会变化
"""
import os
import numpy as np
import msgpack
import msgpack_numpy as mnp
from math import ceil, sqrt

# 导入必要的函数
from test_FCP_LS import (
    EdgeScoringGCN,
    process_data,
    convert_pred_assort_to_assignment,
    assignment_to_pred_assort,
    predict_initial_bundles,
)

def generate_neighbor_assignments_global_topk(current_assignment, prob, n, m):
    """
    Generate neighbor assignments using global Top-K strategy
    """
    current_pred_assort = assignment_to_pred_assort(current_assignment, n, m)
    K = int(ceil(sqrt(m)))
    
    neighbors = []
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
    
    # Step 2: Generate Drop candidates
    drop_candidates = []
    for k in range(m):
        for j in range(n):
            if current_pred_assort[k, j] == 1:
                score_drop = prob[k, j]
                drop_candidates.append((k, j, score_drop))
    
    drop_candidates.sort(key=lambda x: x[2])
    drop_list = drop_candidates[:K]
    
    # Step 3: Generate neighbors
    for idx, (k, j, score) in enumerate(add_list):
        neighbor_info.append({
            'type': 'Add',
            'segment': k,
            'product': j,
            'score': score,
        })
    
    for idx, (k, j, score) in enumerate(drop_list):
        neighbor_info.append({
            'type': 'Drop',
            'segment': k,
            'product': j,
            'score': score,
        })
    
    return neighbor_info


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
    
    # 初始assignment（模拟MILP结果）
    initial_assignment = convert_pred_assort_to_assignment(initial_pred_assort)
    
    print("=" * 80)
    print("分析Neighbor生成逻辑")
    print("=" * 80)
    print(f"K = {int(ceil(sqrt(segment_num)))}, 每轮最多生成 {2*int(ceil(sqrt(segment_num)))} 个neighbor\n")
    
    # 模拟3轮迭代
    current_assignment = initial_assignment.copy()
    
    for iteration in range(3):
        print(f"\n{'='*80}")
        print(f"Iteration {iteration + 1}")
        print(f"{'='*80}")
        
        # 显示当前assignment状态
        current_pred_assort = assignment_to_pred_assort(current_assignment, n, segment_num)
        print(f"\n当前Assignment状态 (前5个segments):")
        for k in range(min(5, segment_num)):
            bundle_str = ''.join(str(int(current_pred_assort[k, j])) for j in range(n))
            print(f"  Segment {k}: {bundle_str}")
        
        # 生成neighbors
        neighbor_info = generate_neighbor_assignments_global_topk(current_assignment, prob, n, segment_num)
        
        print(f"\n生成的Neighbors ({len(neighbor_info)}个):")
        for idx, info in enumerate(neighbor_info):
            print(f"  Neighbor {idx+1} ({info['type']}): Seg{info['segment']}, Prod{info['product']}, Score={info['score']:.4f}")
        
        # 模拟接受第一个Add neighbor（如果存在）
        if neighbor_info and neighbor_info[0]['type'] == 'Add':
            accepted = neighbor_info[0]
            print(f"\n✓ 接受: Neighbor 1 ({accepted['type']}): Seg{accepted['segment']}, Prod{accepted['product']}")
            
            # 更新current_assignment
            new_pred_assort = current_pred_assort.copy()
            new_pred_assort[accepted['segment'], accepted['product']] = 1
            current_assignment = convert_pred_assort_to_assignment(new_pred_assort)
            
            print(f"  更新后: Segment {accepted['segment']}, Product {accepted['product']} 从 0 -> 1")
        elif neighbor_info and neighbor_info[0]['type'] == 'Drop':
            # 如果第一个是Drop，接受第一个Drop
            accepted = neighbor_info[0]
            print(f"\n✓ 接受: Neighbor 1 ({accepted['type']}): Seg{accepted['segment']}, Prod{accepted['product']}")
            
            # 更新current_assignment
            new_pred_assort = current_pred_assort.copy()
            new_pred_assort[accepted['segment'], accepted['product']] = 0
            current_assignment = convert_pred_assort_to_assignment(new_pred_assort)
            
            print(f"  更新后: Segment {accepted['segment']}, Product {accepted['product']} 从 1 -> 0")
        
        # 分析：哪些neighbors会在下一轮继续出现？
        print(f"\n分析下一轮可能的变化:")
        print(f"  - prob矩阵: 不变（固定）")
        print(f"  - current_pred_assort: 已改变（接受了neighbor）")
        print(f"  - Add candidates: 只考虑 current_pred_assort[k,j]==0 的位置")
        print(f"  - Drop candidates: 只考虑 current_pred_assort[k,j]==1 的位置")
        
        # 检查哪些neighbors会在下一轮继续出现
        if iteration < 2:
            next_pred_assort = assignment_to_pred_assort(current_assignment, n, segment_num)
            print(f"\n下一轮预测:")
            print(f"  - 如果某个位置的状态未改变，且prob值高，它应该继续在Top-K中")
            print(f"  - 如果某个位置的状态改变了（0->1或1->0），它会从Add/Drop candidates中移除/加入")


if __name__ == "__main__":
    import torch
    main()

