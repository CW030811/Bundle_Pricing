# Total Time 组成说明

## 一、Total Time 的定义

`total_time` 是从调用整个策略开始到结束的**总执行时间**，在 `evaluate_single_dataset()` 函数中计算。

## 二、Total Time 的组成

根据 `evaluate_single_dataset()` 函数的实现，`total_time` 包含以下3个主要步骤：

### Step 1: Threshold Time (GCN推理时间)
- **时间变量**: `threshold_time`
- **功能**: 使用训练好的GCN模型生成初始 pred_assort 和概率矩阵
- **代码位置**: 第361-363行
- **函数调用**: `predict_initial_bundles(dat, miscellaneous)`
- **说明**: 这是GCN模型的前向推理时间

### Step 2: Initial MILP Time (初始MILP求解时间)
- **时间变量**: `initial_milp_time`
- **功能**: 使用初始 pred_assort 求解初始MILP，获得初始收益比率
- **代码位置**: 第366-368行
- **函数调用**: `solve_initial_milp(initial_pred, miscellaneous)`
- **说明**: 这个步骤只获取初始revenue，不返回assignment

### Step 3: Local Search Time (局部搜索时间)
- **时间变量**: `local_search_time`
- **功能**: 执行全局Top-K局部搜索优化
- **代码位置**: 第371-375行
- **函数调用**: `local_search_with_lp_global_topk(initial_pred, prob, miscellaneous, ...)`
- **说明**: 这个函数内部包含：
  - Initial MILP solve (获取assignment)
  - Initial LP solve
  - 迭代循环
  - 转换assignment
  - Final MILP solve

## 三、时间关系式

```
Total Time = Threshold Time (GCN推理)
          + Initial MILP Time (evaluate中的)
          + Local Search Time
```

**注意**: 
- `Local Search Time` 内部也包含一个 Initial MILP solve（用于获取assignment）
- 所以实际上有两个 Initial MILP solve：
  1. `evaluate` 中的：只获取初始revenue
  2. `local_search` 函数内部的：获取assignment并开始搜索

## 四、实际数据验证

根据实验数据（m10_n10_sample_100）：

### Global Top-K策略
- **Total Time**: 0.3608s
- **Threshold Time**: ~0.0257s (7.1%)
- **Initial MILP Time**: ~0.0687s (19.0%)
- **Local Search Time**: ~0.2563s (71.0%)
- **其他开销**: ~0.0101s (2.8%)

### Original策略
- **Total Time**: 0.6253s
- **Threshold Time**: ~0.0250s (4.0%)
- **Initial MILP Time**: ~0.0903s (14.4%)
- **Local Search Time**: ~0.5200s (83.2%)
- **其他开销**: ~0.0100s (1.6%)

## 五、时间占比分析

### Global Top-K策略
| 时间项 | 平均时间 | 占比 |
|--------|----------|------|
| Threshold Time | 0.0257s | 7.1% |
| Initial MILP Time | 0.0687s | 19.0% |
| Local Search Time | 0.2563s | 71.0% |
| 其他开销 | 0.0101s | 2.8% |
| **Total Time** | **0.3608s** | **100%** |

### Original策略
| 时间项 | 平均时间 | 占比 |
|--------|----------|------|
| Threshold Time | 0.0250s | 4.0% |
| Initial MILP Time | 0.0903s | 14.4% |
| Local Search Time | 0.5200s | 83.2% |
| 其他开销 | 0.0100s | 1.6% |
| **Total Time** | **0.6253s** | **100%** |

## 六、关键发现

1. **Local Search Time 是 Total Time 的主要部分**
   - Global Top-K: 71.0%
   - Original: 83.2%

2. **Initial MILP Time 占比较大**
   - Global Top-K: 19.0%
   - Original: 14.4%
   - 注意：这还不包括 Local Search 内部的 Initial MILP

3. **Threshold Time (GCN推理) 占比较小**
   - Global Top-K: 7.1%
   - Original: 4.0%
   - 说明GCN推理相对较快

4. **其他开销很小**
   - 主要是函数调用、变量赋值等Python开销
   - 约占1-3%

## 七、完整时间分解图

```
Total Time (0.3608s for Global Top-K)
│
├─ Threshold Time (0.0257s, 7.1%)
│  └─ GCN模型推理
│
├─ Initial MILP Time (0.0687s, 19.0%)
│  └─ 获取初始revenue
│
└─ Local Search Time (0.2563s, 71.0%)
   │
   ├─ Initial MILP (获取assignment)
   ├─ Initial LP
   ├─ Iteration Time (0.1523s)
   │  ├─ Add Candidate构建
   │  ├─ Drop Candidate构建
   │  ├─ Neighbor生成
   │  ├─ LP求解 (97.8%)
   │  └─ 其他
   ├─ 转换assignment
   └─ Final MILP
```

## 八、总结

**Total Time = Threshold Time + Initial MILP Time + Local Search Time + 其他开销**

其中：
- **Threshold Time**: GCN推理时间（~7%）
- **Initial MILP Time**: 初始MILP求解时间（~15-20%）
- **Local Search Time**: 局部搜索时间（~70-80%，主要部分）
- **其他开销**: Python函数调用等（~2-3%）

**优化建议**:
1. Local Search Time 是主要瓶颈，应重点优化
2. Initial MILP Time 也有一定占比，可以考虑优化
3. Threshold Time 占比小，优化空间有限


