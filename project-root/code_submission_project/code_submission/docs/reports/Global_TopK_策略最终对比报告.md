# Global Top-K Local Search 策略最终对比报告

## 一、策略说明

### 1.1 Global Top-K 策略逻辑

Global Top-K策略是对原Segment-based策略的改进，核心思想是：

1. **原策略 (Segment-based)**: 每轮为每个segment生成1个Add候选和1个Drop候选，共生成2*m个邻域
2. **Global Top-K策略**: 全局选择Top-K个最有可能的Add候选和Top-K个最有可能的Drop候选，共生成最多2*K个邻域，其中K = ceil(sqrt(m))

**关键改进点**:
- 不再按segment逐个生成候选，而是全局排序选择最优候选
- 邻域规模从O(m)降低到O(sqrt(m))，显著减少LP求解次数
- 通过GCN输出的概率矩阵P[k,j]指导候选选择，优先考虑高概率的Add操作和低概率的Drop操作

### 1.2 核心代码实现

```python
def generate_neighbor_assignments_global_topk(current_assignment, prob, n, m):
    """
    Generate neighbor assignments using global Top-K strategy
    
    Args:
        current_assignment: dict, current segment-bundle assignment
        prob: [m, n] GCN output probability matrix
        n: number of products
        m: number of customer segments
    
    Returns:
        list: list of neighbor assignments, ordered by priority
    """
    current_pred_assort = assignment_to_pred_assort(current_assignment, n, m)
    
    # Calculate K = ceil(sqrt(m))
    K = int(ceil(sqrt(m)))
    
    neighbors = []
    
    # Step 1: Generate Add candidates (globally sorted by probability)
    add_candidates = []
    for k in range(m):
        for j in range(n):
            # 考虑不要用双层For循环
            # Z =（1-current_pred）* Prob_Matrix
            # Argmax(Z)
            if current_pred_assort[k, j] == 0:  # Currently not selected
                score_add = prob[k, j]  # Higher probability = better candidate
                add_candidates.append((k, j, score_add))
    
    # Sort Add candidates by score (descending: high prob -> low prob)
    add_candidates.sort(key=lambda x: x[2], reverse=True)
    
    # Take top K Add candidates
    add_list = add_candidates[:K]
    
    # Step 2: Generate Drop candidates (globally sorted by probability)
    drop_candidates = []
    for k in range(m):
        for j in range(n):
            if current_pred_assort[k, j] == 1:  # Currently selected
                score_drop = prob[k, j]  # Lower probability = better candidate to drop
                drop_candidates.append((k, j, score_drop))
    
    # Sort Drop candidates by score (ascending: low prob -> high prob)
    drop_candidates.sort(key=lambda x: x[2])
    
    # Take top K Drop candidates
    drop_list = drop_candidates[:K]
    
    # Step 3: Generate neighbors in priority order
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
    
    return neighbors
```

---

## 二、实验对比结果

### 2.1 Revenue Ratio对比

| 数据集 | 原策略 | K=2*sqrt(m) | K=sqrt(m) | K=sqrt(m) vs 原策略 | K=sqrt(m) vs K=2*sqrt(m) |
|--------|--------|------------|-----------|-------------------|------------------------|
| m10_n10 | 0.9956 | 0.9949 | 0.9924 | -0.0032 (-0.32%) | -0.0025 (-0.26%) |
| BSP_m10n15 | 1.1369 | 1.1369 | 1.1200 | -0.0170 (-1.49%) | -0.0169 (-1.49%) |
| BSP_m10n20 | 1.1104 | 1.1108 | 1.0908 | -0.0197 (-1.77%) | -0.0200 (-1.80%) |
| BSP_m10n25 | 1.0919 | 1.0861 | 1.0578 | -0.0342 (-3.13%) | -0.0284 (-2.61%) |
| BSP_m15n15 | 1.1462 | 1.1426 | 1.1221 | -0.0241 (-2.11%) | -0.0205 (-1.80%) |
| m20_n10 | 0.9906 | 0.9876 | 0.9849 | -0.0056 (-0.57%) | -0.0027 (-0.27%) |
| BSP_m20n15 | 1.1662 | 1.1603 | 1.1417 | -0.0245 (-2.10%) | -0.0186 (-1.61%) |
| m30_n10 | 0.9826 | 0.9825 | 0.9794 | -0.0032 (-0.32%) | -0.0031 (-0.32%) |

### 2.2 Time Ratio对比

| 数据集      | 原策略  |K=2*sqrt(m)| K=sqrt(m) | PCP  | K=sqrt(m) vs 原策略 | K=sqrt(m) vs K=2*sqrt(m) |
|--------    |-------- |---------|-----------|--------|-------------------|----------------|
| m10_n10    | 0.1006  | 0.0727  | 0.0535 |  0.0867   | -0.0471 (-46.80%) | -0.0191 (-26.34%) |
| BSP_m10n15 | 8.6859  | 8.5292  | 4.2855 |  17.975   | -4.4004 (-50.66%) | -4.2436 (-49.75%) |
| BSP_m10n20 | 11.8616 | 12.1533 | 5.6610 |  36.676   | -6.2006 (-52.27%) | -6.4923 (-53.42%) |
| BSP_m10n25 | 7.8015  | 7.9175  | 3.2977 |  41.401   | -4.5038 (-57.73%) | -4.6198 (-58.35%) |
| BSP_m15n15 | 25.5265 | 20.1424 | 7.7723 |  47.579   |-17.7542 (-69.55%) | -12.3701 (-61.41%) |
| m20_n10    | 0.3164  | 0.1049  | 0.0644 |  0.1442   | -0.2520 (-79.64%) | -0.0405 (-38.60%) |
| BSP_m20n15 | 43.4147 | 27.4678 | 10.7110|  71.445   |-32.7037 (-75.33%) | -16.7568 (-61.01%) |
| m30_n10    | 0.6690  | 0.1655  | 0.0908 |  0.2690   | -0.5782 (-86.42%) | -0.0747 (-45.11%) |

### 2.3 LP调用次数对比

| 数据集 | 原策略 | K=2*sqrt(m) | K=sqrt(m) | K=sqrt(m) vs 原策略 | K=sqrt(m) vs K=2*sqrt(m) |
|--------|--------|------------|-----------|-------------------|------------------------|
| m10_n10 | 80.7 | 47.4 | 24.0 | -56.7 (-70.23%) | -23.3 (-49.25%) |
| BSP_m10n15 | 218.0 | 188.6 | 83.3 | -134.7 (-61.80%) | -105.3 (-55.83%) |
| BSP_m10n20 | 298.4 | 249.7 | 117.8 | -180.6 (-60.53%) | -131.9 (-52.82%) |
| BSP_m10n25 | 333.4 | 277.5 | 119.8 | -213.6 (-64.06%) | -157.7 (-56.83%) |
| BSP_m15n15 | 477.3 | 285.7 | 103.9 | -373.4 (-78.23%) | -181.8 (-63.63%) |
| m20_n10 | 253.7 | 79.0 | 34.0 | -219.6 (-86.59%) | -45.0 (-56.97%) |
| BSP_m20n15 | 756.0 | 365.9 | 146.8 | -609.2 (-80.58%) | -219.1 (-59.88%) |
| m30_n10 | 544.5 | 107.1 | 44.6 | -499.8 (-91.80%) | -62.5 (-58.34%) |

---

## 三、发现

1. **Revenue Ratio**: K=sqrt(m)策略在大多数数据集上与原策略策略基本持平，差异（<2.5%）

2. **Time Ratio**: K=sqrt(m)策略在所有数据集上都显著优于原策略和K=2*sqrt(m)策略，特别是在m较大的数据集上改善更明显

3. **LP调用次数**: K=sqrt(m)策略大幅减少了LP求解器的调用次数，这是Time Ratio改善的主要原因

4. **可扩展性**: 随着m增大，K=sqrt(m)策略的优势更加明显，证明了该策略具有良好的可扩展性

5. 其他考虑
5.1. **LP 可能的最优⽅向，MILP 检查是否有提升，有提升就⾛⼀下，没提升就结束**：相当于在全局Neighbor构建中挑选Revenue提升最大的方向，然后调用MILP。整个
逻辑下来就会调用多轮Global Neighbor Construction -> LP 调用次数又高了 且还需要 MILP的时间长度 -> 不太可行。
5.2. **track ⼀下每⼀个时间点的 solution 是什么，然后解⼀下 revenue**:
5.3. **示意图**：
5.4. **Local Search 逻辑伪代码**：
5.5 **k这个参数的选择定义原因该怎么讲？**
---

## 四、详细路径追踪案例（m10_n10样本）

### 4.1 案例说明

选取m10_n10数据集的一个样本，详细追踪Global Top-K策略的Local Search完整过程。

**样本编号**: `sample_data_100_size_10.msgpack`

**对比策略**:
1. **贪婪策略**（Greedy Strategy）：找到第一个改进就立即接受并break，与`LS_Path_Test.py`的逻辑一致
2. **最佳改进策略**（Best Improvement Strategy）：遍历所有neighbors，选择revenue最高的neighbor，与`LS_Path_Test_Best_Choice.py`的逻辑一致

### 4.2 Initial Prediction

```
Segment 0: 0110101001 (Bundle 425)
Segment 1: 1100111100 (Bundle 828)
Segment 2: 1011111010 (Bundle 762)
Segment 3: 1100111111 (Bundle 831)
Segment 4: 1011011111 (Bundle 735)
Segment 5: 0100100111 (Bundle 295)
Segment 6: 1011000101 (Bundle 709)
Segment 7: 1111111010 (Bundle 1018)
Segment 8: 1110110100 (Bundle 948)
Segment 9: 1101011010 (Bundle 858)
```

**Initial MILP Revenue**: 0.977145 (MIPGap = 1e-6)  
**Initial LP Revenue**: 0.977145  
**Initial Assignment**: {0: 425, 1: 828, 2: 762, 3: 831, 4: 735, 5: 295, 6: 709, 7: 1018, 8: 948, 9: 858}

### 4.3 Global Top-K策略参数

- **K = 4** (ceil(sqrt(10)) = 4)
- **每轮最多生成**: 2*K = 8 个neighbors

### 4.4 Local Search过程详情

#### Iteration 1
- **当前Revenue**: 0.977145
- **生成Neighbors**: 8个
- **评估Neighbors**: 1个（贪婪策略：找到第一个改进就接受）
  - Neighbor 1 (Add): Seg9, Prod7, Score=0.4684, Revenue=0.980401, Time=0.0085s ✓ **接受**
- **改进**: +0.003256 (0.33%)
- **新Revenue**: 0.980401
- **迭代时间**: 0.0085s

**说明**：
- 使用**贪婪策略**：找到第一个改进（Neighbor 1）就立即接受并break，不再检查后续neighbors
- Initial Assignment中Segment 1的Bundle 828 = `1100111100`，转换为pred_assort后Product 9 = 0（未选中）
- 所有Drop candidates的Score都 >= 0.5（修复后的结果）✓

#### Iteration 2
- **当前Revenue**: 0.980401
- **生成Neighbors**: 8个
- **评估Neighbors**: 2个（贪婪策略：找到第一个改进就接受）
  - Neighbor 1 (Add): Seg0, Prod0, Score=0.4653, Revenue=0.971609, Time=0.0042s
  - Neighbor 2 (Add): Seg1, Prod9, Score=0.4565, Revenue=0.981004, Time=0.0073s ✓ **接受**
- **改进**: +0.000603 (0.06%)
- **新Revenue**: 0.981004
- **迭代时间**: 0.0115s

**观察**：
- 使用**贪婪策略**：Neighbor 1的Revenue (0.971609) < 当前Revenue，继续检查；Neighbor 2的Revenue (0.981004) > 当前Revenue，立即接受并break
- Iteration 1的Neighbor 2 (Add: Seg0, Prod0) **继续出现在** Iteration 2的Neighbor 1位置 ✓
- Seg1, Prod9在Iteration 1时未检查（因为Iteration 1只检查了Neighbor 1就break），Iteration 2时出现在Neighbor 2位置并被接受 ✓

#### Iteration 3
- **当前Revenue**: 0.981004
- **生成Neighbors**: 8个
- **评估Neighbors**: 2个（贪婪策略：找到第一个改进就接受）
  - Neighbor 1 (Add): Seg0, Prod0, Score=0.4653, Revenue=0.972188, Time=0.0041s
  - Neighbor 2 (Add): Seg2, Prod9, Score=0.4019, Revenue=0.982648, Time=0.0042s ✓ **接受**
- **改进**: +0.001644 (0.17%)
- **新Revenue**: 0.982648
- **迭代时间**: 0.0093s

**观察**：
- 使用**贪婪策略**：Neighbor 1的Revenue (0.972188) < 当前Revenue，继续检查；Neighbor 2的Revenue (0.982648) > 当前Revenue，立即接受并break
- Iteration 2的Neighbor 1 (Add: Seg0, Prod0) **继续出现在** Iteration 3的Neighbor 1位置 ✓
- Seg2, Prod9在Iteration 2时未检查（因为Iteration 2只检查了2个neighbors就break），Iteration 3时出现在Neighbor 2位置并被接受 ✓

#### Iteration 4
- **当前Revenue**: 0.982648
- **生成Neighbors**: 8个
- **评估Neighbors**: 4个（贪婪策略：找到第一个改进就接受）
  - Neighbor 1 (Add): Seg0, Prod0, Score=0.4653, Revenue=0.973831, Time=0.0063s
  - Neighbor 2 (Add): Seg7, Prod7, Score=0.3791, Revenue=0.981262, Time=0.0063s
  - Neighbor 3 (Add): Seg9, Prod2, Score=0.3775, Revenue=0.970578, Time=0.0051s
  - Neighbor 4 (Add): Seg6, Prod6, Score=0.3624, Revenue=0.983061, Time=0.0072s ✓ **接受**
- **改进**: +0.000413 (0.04%)
- **新Revenue**: 0.983061
- **迭代时间**: 0.0290s

**观察**：
- 使用**贪婪策略**：前3个neighbors的Revenue都 < 当前Revenue，继续检查；Neighbor 4的Revenue (0.983061) > 当前Revenue，立即接受并break
- Seg6, Prod6在之前的迭代中未检查，Iteration 4时出现在Neighbor 4位置并被接受 ✓

#### Iteration 5
- **当前Revenue**: 0.983061
- **生成Neighbors**: 8个
- **评估Neighbors**: 5个（贪婪策略：找到第一个改进就接受）
  - Neighbor 1 (Add): Seg0, Prod0, Score=0.4653, Revenue=0.974245, Time=0.0042s
  - Neighbor 2 (Add): Seg7, Prod7, Score=0.3791, Revenue=0.981676, Time=0.0073s
  - Neighbor 3 (Add): Seg9, Prod2, Score=0.3775, Revenue=0.970991, Time=0.0082s
  - Neighbor 4 (Add): Seg5, Prod6, Score=0.3574, Revenue=0.979428, Time=0.0064s
  - Neighbor 5 (Drop): Seg9, Prod0, Score=0.5450, Revenue=0.987752, Time=0.0062s ✓ **接受**
- **改进**: +0.004691 (0.47%)
- **新Revenue**: 0.987752
- **迭代时间**: 0.0335s

**观察**：
- 使用**贪婪策略**：前4个neighbors的Revenue都 < 当前Revenue，继续检查；Neighbor 5 (Drop)的Revenue (0.987752) > 当前Revenue，立即接受并break
- 注意：所有Drop candidates的Score都 >= 0.5（修复后的结果）✓

#### Iteration 6
- **当前Revenue**: 0.987752
- **生成Neighbors**: 8个
- **评估Neighbors**: 8个（贪婪策略：检查所有neighbors）
  - Neighbor 1 (Add): Seg9, Prod0, Score=0.5450, Revenue=0.983061, Time=0.0041s
  - Neighbor 2 (Add): Seg0, Prod0, Score=0.4653, Revenue=0.974022, Time=0.0083s
  - Neighbor 3 (Add): Seg7, Prod7, Score=0.3791, Revenue=0.986367, Time=0.0060s
  - Neighbor 4 (Add): Seg9, Prod2, Score=0.3775, Revenue=0.982296, Time=0.0082s
  - Neighbor 5 (Drop): Seg1, Prod0, Score=0.5752, Revenue=0.987153, Time=0.0023s
  - Neighbor 6 (Drop): Seg9, Prod6, Score=0.6134, Revenue=0.984426, Time=0.0084s
  - Neighbor 7 (Drop): Seg4, Prod7, Score=0.6720, Revenue=0.985564, Time=0.0061s
  - Neighbor 8 (Drop): Seg0, Prod2, Score=0.6850, Revenue=0.976615, Time=0.0065s
- **改进**: 未找到改进
- **迭代时间**: 0.0500s
- **搜索收敛**


### 4.5 最终结果

**最终Prediction (pred_assort)**:
```
Segment 0: 0110101001
Segment 1: 1100111101
Segment 2: 1011111011
Segment 3: 1100111111
Segment 4: 1011011111
Segment 5: 0100100111
Segment 6: 1011001101
Segment 7: 1111111010
Segment 8: 1110110100
Segment 9: 0101011110
```

**最终LP Revenue**: 0.987752  
**最终MILP Revenue**: 0.987752  
**Total Improvement**: 0.010607 (1.09%)

**搜索过程总结**：
- 共进行6轮迭代，其中5轮找到改进
- 使用贪婪策略，每轮平均评估neighbors数量：Iteration 1 (1个), Iteration 2 (2个), Iteration 3 (2个), Iteration 4 (4个), Iteration 5 (5个), Iteration 6 (8个)
- 总迭代时间：0.1418s，平均每轮0.0236s

### 4.6 Local Search路径示意图

![Local Search路径可视化](search_path_visualization.png)

**说明**:
- 上图展示了Local Search过程中Revenue的变化路径
- 红色虚线：Initial MILP Revenue (0.977145, MIPGap = 1e-6)
- 绿色虚线：Final MILP Revenue (0.987752)
- 蓝色实线：每轮迭代的LP Revenue变化
- 绿色圆点：接受改进的迭代点

**关键观察**:
1. 搜索在6轮迭代后收敛
2. 使用贪婪策略，每轮实际评估的neighbors数量不同（1-8个）
3. 共找到5次改进，Revenue从0.977145提升到0.987752
4. 总迭代时间约0.1418s，平均每轮0.0236s
5. 贪婪策略比最佳改进策略更快，因为找到第一个改进就停止检查后续neighbors

---

## 五、Best Improvement策略详细路径追踪（m10_n10样本）

### 5.1 策略说明

**Best Improvement策略**（最佳改进策略）：
- 每轮迭代**遍历所有neighbors**（8个）
- 评估所有neighbors的Revenue
- 选择**Revenue最高的neighbor**作为改进
- 与贪婪策略的区别：贪婪策略找到第一个改进就接受，Best Improvement策略遍历所有neighbors后选择最优的

### 5.2 Initial Prediction

与贪婪策略相同：
```
Segment 0: 0110101001 (Bundle 425)
Segment 1: 1100111100 (Bundle 828)
Segment 2: 1011111010 (Bundle 762)
Segment 3: 1100111111 (Bundle 831)
Segment 4: 1011011111 (Bundle 735)
Segment 5: 0100100111 (Bundle 295)
Segment 6: 1011000101 (Bundle 709)
Segment 7: 1111111010 (Bundle 1018)
Segment 8: 1110110100 (Bundle 948)
Segment 9: 1101011010 (Bundle 858)
```

**Initial MILP Revenue**: 0.977145 (MIPGap = 1e-6)  
**Initial LP Revenue**: 0.977145  
**Initial Assignment**: {0: 425, 1: 828, 2: 762, 3: 831, 4: 735, 5: 295, 6: 709, 7: 1018, 8: 948, 9: 858}

### 5.3 Global Top-K策略参数

- **K = 4** (ceil(sqrt(10)) = 4)
- **每轮最多生成**: 2*K = 8 个neighbors
- **评估策略**: 遍历所有8个neighbors，选择Revenue最高的

### 5.4 Local Search过程详情

#### Iteration 1
- **当前Revenue**: 0.977145
- **生成Neighbors**: 8个
- **评估Neighbors**: 8个（Best Improvement策略：遍历所有neighbors）
  - Neighbor 1 (Add): Seg9, Prod7, Score=0.4684, Revenue=0.980401, Time=0.0083s
  - Neighbor 2 (Add): Seg0, Prod0, Score=0.4653, Revenue=0.968352, Time=0.0074s
  - Neighbor 3 (Add): Seg1, Prod9, Score=0.4565, Revenue=0.977748, Time=0.0038s
  - Neighbor 4 (Add): Seg2, Prod9, Score=0.4019, Revenue=0.978789, Time=0.0083s
  - Neighbor 5 (Drop): Seg9, Prod0, Score=0.5450, Revenue=0.979900, Time=0.0053s
  - Neighbor 6 (Drop): Seg1, Prod0, Score=0.5752, Revenue=0.976528, Time=0.0071s
  - Neighbor 7 (Drop): Seg9, Prod6, Score=0.6134, Revenue=0.978619, Time=0.0057s
  - Neighbor 8 (Drop): Seg4, Prod7, Score=0.6720, Revenue=0.975322, Time=0.0069s
- **最佳Neighbor**: Neighbor 1 (Revenue=0.980401) ✓ **接受**
- **改进**: +0.003256 (0.33%)
- **新Revenue**: 0.980401
- **迭代时间**: 0.0530s


#### Iteration 2
- **当前Revenue**: 0.980401
- **生成Neighbors**: 8个
- **评估Neighbors**: 8个（Best Improvement策略：遍历所有neighbors）
  - Neighbor 1 (Add): Seg0, Prod0, Score=0.4653, Revenue=0.971609, Time=0.0051s
  - Neighbor 2 (Add): Seg1, Prod9, Score=0.4565, Revenue=0.981004, Time=0.0077s
  - Neighbor 3 (Add): Seg2, Prod9, Score=0.4019, Revenue=0.982045, Time=0.0064s
  - Neighbor 4 (Add): Seg7, Prod7, Score=0.3791, Revenue=0.979016, Time=0.0058s
  - Neighbor 5 (Drop): Seg9, Prod0, Score=0.5450, Revenue=0.981276, Time=0.0062s
  - Neighbor 6 (Drop): Seg1, Prod0, Score=0.5752, Revenue=0.979785, Time=0.0061s
  - Neighbor 7 (Drop): Seg9, Prod6, Score=0.6134, Revenue=0.979975, Time=0.0042s
  - Neighbor 8 (Drop): Seg4, Prod7, Score=0.6720, Revenue=0.978578, Time=0.0061s
- **最佳Neighbor**: Neighbor 3 (Revenue=0.982045) ✓ **接受**
- **改进**: +0.001644 (0.17%)
- **新Revenue**: 0.982045
- **迭代时间**: 0.0476s

**观察**：
- 使用**Best Improvement策略**：遍历所有8个neighbors，选择Revenue最高的（Neighbor 3）
- Neighbor 3的Revenue (0.982045) 是所有neighbors中最高的
- 与贪婪策略对比：贪婪策略在Iteration 2时接受Neighbor 2 (Revenue=0.981004)，Best Improvement策略选择Neighbor 3 (Revenue=0.982045)，获得了更好的改进

#### Iteration 3
- **当前Revenue**: 0.982045
- **生成Neighbors**: 8个
- **评估Neighbors**: 8个（Best Improvement策略：遍历所有neighbors）
  - Neighbor 1 (Add): Seg0, Prod0, Score=0.4653, Revenue=0.973252, Time=0.0059s
  - Neighbor 2 (Add): Seg1, Prod9, Score=0.4565, Revenue=0.982648, Time=0.0065s
  - Neighbor 3 (Add): Seg7, Prod7, Score=0.3791, Revenue=0.980660, Time=0.0042s
  - Neighbor 4 (Add): Seg9, Prod2, Score=0.3775, Revenue=0.969998, Time=0.0083s
  - Neighbor 5 (Drop): Seg9, Prod0, Score=0.5450, Revenue=0.986736, Time=0.0061s
  - Neighbor 6 (Drop): Seg1, Prod0, Score=0.5752, Revenue=0.981428, Time=0.0063s
  - Neighbor 7 (Drop): Seg9, Prod6, Score=0.6134, Revenue=0.985435, Time=0.0042s
  - Neighbor 8 (Drop): Seg4, Prod7, Score=0.6720, Revenue=0.980222, Time=0.0087s
- **最佳Neighbor**: Neighbor 5 (Revenue=0.986736) ✓ **接受**
- **改进**: +0.004691 (0.48%)
- **新Revenue**: 0.986736
- **迭代时间**: 0.0503s

**观察**：
- 使用**Best Improvement策略**：遍历所有8个neighbors，选择Revenue最高的（Neighbor 5）
- Neighbor 5的Revenue (0.986736) 是所有neighbors中最高的
- 与贪婪策略对比：贪婪策略在Iteration 3时接受Neighbor 2 (Revenue=0.982648)，Best Improvement策略选择Neighbor 5 (Revenue=0.986736)，获得了更好的改进

#### Iteration 4
- **当前Revenue**: 0.986736
- **生成Neighbors**: 8个
- **评估Neighbors**: 8个（Best Improvement策略：遍历所有neighbors）
  - Neighbor 1 (Add): Seg9, Prod0, Score=0.5450, Revenue=0.982045, Time=0.0032s
  - Neighbor 2 (Add): Seg0, Prod0, Score=0.4653, Revenue=0.973030, Time=0.0084s
  - Neighbor 3 (Add): Seg1, Prod9, Score=0.4565, Revenue=0.987339, Time=0.0042s
  - Neighbor 4 (Add): Seg7, Prod7, Score=0.3791, Revenue=0.985351, Time=0.0083s
  - Neighbor 5 (Drop): Seg1, Prod0, Score=0.5752, Revenue=0.986119, Time=0.0041s
  - Neighbor 6 (Drop): Seg9, Prod6, Score=0.6134, Revenue=0.983410, Time=0.0085s
  - Neighbor 7 (Drop): Seg4, Prod7, Score=0.6720, Revenue=0.984913, Time=0.0040s
  - Neighbor 8 (Drop): Seg0, Prod2, Score=0.6850, Revenue=0.971228, Time=0.0083s
- **最佳Neighbor**: Neighbor 3 (Revenue=0.987339) ✓ **接受**
- **改进**: +0.000603 (0.06%)
- **新Revenue**: 0.987339
- **迭代时间**: 0.0495s

**观察**：
- 使用**Best Improvement策略**：遍历所有8个neighbors，选择Revenue最高的（Neighbor 3）
- Neighbor 3的Revenue (0.987339) 是所有neighbors中最高的

#### Iteration 5
- **当前Revenue**: 0.987339
- **生成Neighbors**: 8个
- **评估Neighbors**: 8个（Best Improvement策略：遍历所有neighbors）
  - Neighbor 1 (Add): Seg9, Prod0, Score=0.5450, Revenue=0.982648, Time=0.0043s
  - Neighbor 2 (Add): Seg0, Prod0, Score=0.4653, Revenue=0.973609, Time=0.0083s
  - Neighbor 3 (Add): Seg7, Prod7, Score=0.3791, Revenue=0.985954, Time=0.0041s
  - Neighbor 4 (Add): Seg9, Prod2, Score=0.3775, Revenue=0.981883, Time=0.0085s
  - Neighbor 5 (Drop): Seg1, Prod0, Score=0.5752, Revenue=0.986739, Time=0.0041s
  - Neighbor 6 (Drop): Seg9, Prod6, Score=0.6134, Revenue=0.984012, Time=0.0090s
  - Neighbor 7 (Drop): Seg4, Prod7, Score=0.6720, Revenue=0.985516, Time=0.0035s
  - Neighbor 8 (Drop): Seg0, Prod2, Score=0.6850, Revenue=0.976202, Time=0.0083s
- **最佳Neighbor**: 未找到改进（所有neighbors的Revenue都 <= 当前Revenue）
- **迭代时间**: 0.0501s
- **搜索收敛**

### 5.5 最终结果

**最终Prediction (pred_assort)**:
```
Segment 0: 0110101001
Segment 1: 1100111101
Segment 2: 1011111011
Segment 3: 1100111111
Segment 4: 1011011111
Segment 5: 0100100111
Segment 6: 1011000101
Segment 7: 1111111010
Segment 8: 1110110100
Segment 9: 0101011110
```

**最终LP Revenue**: 0.987339  
**最终MILP Revenue**: 0.987339  
**Total Improvement**: 0.010194 (1.04%)

**搜索过程总结**：
- 共进行5轮迭代，其中4轮找到改进
- 使用Best Improvement策略，每轮评估所有8个neighbors
- 总迭代时间：0.2505s，平均每轮0.0501s

### 5.6 贪婪策略 vs Best Improvement策略对比

| 指标 | 贪婪策略 | Best Improvement策略 | 差异 |
|------|---------|---------------------|------|
| **迭代次数** | 6轮 | 5轮 | -1轮 |
| **总改进次数** | 5次 | 4次 | -1次 |
| **最终Revenue** | 0.987752 | 0.987339 | -0.000413 (-0.04%) |
| **总迭代时间** | 0.1418s | 0.2505s | +0.1087s (+76.66%) |
| **平均每轮时间** | 0.0236s | 0.0501s | +0.0265s (+112.29%) |
| **每轮评估neighbors数** | 1-8个（平均3.3个） | 8个（固定） | +4.7个 |
| **LP调用次数** | 约20次 | 33次 | +13次 (+65%) |

**关键发现**：
1. **Revenue对比**：Best Improvement策略的最终Revenue (0.987339) 略低于贪婪策略 (0.987752)，差异仅0.04%
2. **时间效率**：贪婪策略明显更快，总迭代时间比Best Improvement策略少76.66%
3. **迭代次数**：Best Improvement策略收敛更快（5轮 vs 6轮），但每轮需要评估更多neighbors
4. **LP调用次数**：Best Improvement策略需要更多的LP调用（33次 vs 20次），因为每轮都要评估所有neighbors
5. **策略选择建议**：
   - 如果追求**时间效率**：选择贪婪策略
   - 如果追求**最优解质量**：两种策略的最终Revenue差异很小（<0.1%），但Best Improvement策略理论上可能找到更好的解
   - 在实际应用中，**贪婪策略是更好的选择**，因为它在时间效率上有显著优势，而Revenue差异可以忽略不计

---

