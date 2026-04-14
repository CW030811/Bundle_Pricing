# Neighbor生成逻辑分析

## 问题

为什么每次Iteration生成的neighbor会不一样？接受迭代并不会改变未被添加的Bundle的概率，因此每次接受一个迭代，其他未被选的Neighbor应该仍然留在后续Iteration的Neighbor中？

## 代码逻辑分析

### 核心函数：`generate_neighbor_assignments_global_topk`

```python
def generate_neighbor_assignments_global_topk(current_assignment, prob, n, m):
    current_pred_assort = assignment_to_pred_assort(current_assignment, n, m)
    K = int(ceil(sqrt(m)))
    
    # Step 1: Generate Add candidates
    add_candidates = []
    for k in range(m):
        for j in range(n):
            if current_pred_assort[k, j] == 0:  # 只考虑当前未选中的位置
                score_add = prob[k, j]
                add_candidates.append((k, j, score_add))
    
    add_candidates.sort(key=lambda x: x[2], reverse=True)
    add_list = add_candidates[:K]  # Top-K Add candidates
    
    # Step 2: Generate Drop candidates
    drop_candidates = []
    for k in range(m):
        for j in range(n):
            if current_pred_assort[k, j] == 1:  # 只考虑当前已选中的位置
                score_drop = prob[k, j]
                drop_candidates.append((k, j, score_drop))
    
    drop_candidates.sort(key=lambda x: x[2])  # 升序：低prob优先drop
    drop_list = drop_candidates[:K]  # Top-K Drop candidates
    
    return neighbors  # 总共2*K个neighbors
```

### 关键点

1. **prob矩阵不变**：GCN生成的prob矩阵在整个Local Search过程中保持不变
2. **current_pred_assort会改变**：每次接受一个neighbor后，assignment会更新，导致`current_pred_assort`改变
3. **候选集基于当前状态**：
   - Add candidates: 只考虑 `current_pred_assort[k, j] == 0` 的位置
   - Drop candidates: 只考虑 `current_pred_assort[k, j] == 1` 的位置

## 为什么Neighbors会变化？

### 示例：Iteration 1 → Iteration 2

**Iteration 1**:
- 当前状态：`current_pred_assort[9, 7] = 0` (未选中)
- Add candidates: 包含 (Seg9, Prod7, Score=0.4684) - 这是Top-K中的一个
- 接受：Neighbor 1 (Add): Seg9, Prod7
- 更新后：`current_pred_assort[9, 7] = 1` (已选中)

**Iteration 2**:
- 当前状态：`current_pred_assort[9, 7] = 1` (已选中)
- Add candidates: **不再包含** (Seg9, Prod7)，因为 `current_pred_assort[9, 7] == 1`，不满足Add条件
- Drop candidates: **现在包含** (Seg9, Prod7)，因为 `current_pred_assort[9, 7] == 1`，满足Drop条件

### 关键理解

**用户的理解是正确的**：
- prob矩阵不变 ✓
- 未被选中的neighbor的prob值不变 ✓

**但是**：
- **Add/Drop candidates的集合会改变**，因为它们是**基于当前assignment状态**生成的
- 当一个位置从0变成1（Add操作），它就会：
  - 从Add candidates中移除（因为不再是0）
  - 可能出现在Drop candidates中（因为现在是1）
- 当一个位置从1变成0（Drop操作），它就会：
  - 从Drop candidates中移除（因为不再是1）
  - 可能出现在Add candidates中（因为现在是0）

### 具体例子

假设Iteration 1的Top-K Add candidates是：
1. (Seg9, Prod7, Score=0.4684) ← 被接受
2. (Seg0, Prod0, Score=0.4653)
3. (Seg2, Prod9, Score=0.4019)
4. (Seg7, Prod7, Score=0.3791)

**Iteration 2**:
- (Seg9, Prod7) 不再在Add candidates中（因为现在是1）
- (Seg0, Prod0) **应该继续在Add candidates中**（如果它的prob值仍然在Top-K中）
- (Seg2, Prod9) **应该继续在Add candidates中**（如果它的prob值仍然在Top-K中）
- (Seg7, Prod7) **应该继续在Add candidates中**（如果它的prob值仍然在Top-K中）

**但是**，如果Iteration 1接受了(Seg9, Prod7)，那么：
- 新的Add candidates会重新排序，可能包含其他位置
- 如果(Seg0, Prod0)的prob值仍然很高，它**确实**会继续出现在Add candidates中

## 报告中的观察

从报告来看，每次迭代的neighbors确实会变化，这是因为：

1. **状态改变**：接受一个neighbor会改变assignment状态
2. **候选集重新计算**：基于新的状态重新计算Add/Drop candidates
3. **Top-K重新选择**：虽然prob不变，但候选集变了，所以Top-K可能不同

## 结论

**代码逻辑是正确的**：
- prob矩阵不变 ✓
- 但neighbors会变化，因为：
  - Add/Drop candidates是基于**当前assignment状态**生成的
  - 当assignment改变时，候选集会改变
  - 即使prob不变，Top-K也会因为候选集的变化而可能不同

**用户的期望**：
- 如果某个位置的状态未改变（比如一直是0），且prob值高，它**应该**继续在Top-K中
- 这个期望是**合理的**，代码逻辑也**确实满足**这个期望

**为什么报告中的neighbors看起来变化很大？**
- 可能是因为报告只显示了部分信息（比如只显示被接受的neighbor）
- 或者是因为每次迭代时，Top-K的排序会略有不同（虽然prob不变，但排序可能因为其他因素而不同）

## 建议

1. **验证代码逻辑**：检查`generate_neighbor_assignments_global_topk`函数，确认它确实基于当前状态生成candidates
2. **完整输出**：在报告中显示每轮迭代的所有8个neighbors，而不仅仅是接受的neighbor
3. **追踪特定neighbor**：追踪某个特定位置（比如Seg0, Prod0）是否在连续迭代中出现在Top-K中

