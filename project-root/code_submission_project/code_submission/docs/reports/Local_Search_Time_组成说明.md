# Local Search Time 组成说明

## 一、Local Search Time 的定义

`local_search_time` 是从调用 `local_search_with_lp_global_topk()` (或 `local_search_with_lp()`) 函数开始到结束的**整个函数执行时间**。

## 二、Local Search Time 的组成

根据 `local_search_with_lp_global_topk()` 函数的实现，`local_search_time` 包含以下5个步骤：

### Step 1: Initial MILP Solve
- **时间变量**: `initial_milp_time`
- **功能**: 使用初始 pred_assort 求解初始MILP，获得可行分配
- **代码位置**: 第158行

### Step 2: Initial LP Solve  
- **时间变量**: `initial_lp_time`
- **功能**: 对初始分配求解LP，获得当前最佳收益
- **代码位置**: 第167行

### Step 3: Local Search Loop (迭代循环)
- **时间变量**: `total_iteration_time` (累计所有迭代的时间)
- **功能**: 迭代搜索邻域，寻找改进解
- **代码位置**: 第201-249行
- **包含内容**:
  - 生成邻域 (Add/Drop candidates)
  - LP可行性检查
  - 收益改进检查
  - 更新最佳解

### Step 4: Convert Assignment to Pred_Assort
- **时间变量**: 未单独记录（包含在local_search_time中）
- **功能**: 将最优分配转换为pred_assort矩阵
- **代码位置**: 第257行
- **说明**: 这个步骤时间很短，通常可以忽略

### Step 5: Final MILP Solve
- **时间变量**: `final_milp_time`
- **功能**: 最终MILP求解，验证LP结果
- **代码位置**: 第263行

## 三、时间关系式

```
Local Search Time = Initial MILP Time 
                 + Initial LP Time 
                 + Iteration Time (total_iteration_time)
                 + 转换时间 (通常可忽略)
                 + Final MILP Time
```

## 四、Iteration Time 的详细组成

`total_iteration_time` 是 Step 3 中所有迭代循环的累计时间，包含：

1. **Add Candidate构建时间** (`total_add_candidate_time`)
2. **Drop Candidate构建时间** (`total_drop_candidate_time`)
3. **Neighbor生成时间** (`total_neighbor_generation_time`)
4. **LP求解总时间** (`total_lp_solve_time`) - **主要部分**
5. **Neighbor遍历时间** (`total_neighbor_iteration_time`) - 不包括LP
6. **其他开销** (循环控制、变量赋值等)

## 五、实际数据验证

根据实验数据（m10_n10_sample_100）：

### Global Top-K策略
- **Local Search Time**: 0.2563s
- **Iteration Time**: 0.1523s
- **差值**: 0.1040s

**差值包含**:
- Initial MILP Time: ~0.07s
- Initial LP Time: ~0.01s  
- Final MILP Time: ~0.02s
- 转换时间: <0.01s

### Original策略
- **Local Search Time**: 0.5200s
- **Iteration Time**: 0.4100s
- **差值**: 0.1100s

**差值包含**:
- Initial MILP Time: ~0.09s
- Initial LP Time: ~0.01s
- Final MILP Time: ~0.01s
- 转换时间: <0.01s

## 六、关键发现

1. **Iteration Time 是 Local Search Time 的主要部分**
   - Global Top-K: 59.4% (0.1523/0.2563)
   - Original: 78.8% (0.4100/0.5200)

2. **Local Search Time 中非迭代部分约占 20-40%**
   - 主要是 Initial MILP 和 Final MILP 的时间

3. **Iteration Time 中 LP 求解占 97-98%**
   - 这是性能优化的关键瓶颈

## 七、总结

**Local Search Time = Iteration Time + 其他步骤时间**

其中：
- **Iteration Time**: 迭代循环的累计时间（主要部分）
- **其他步骤时间**: Initial MILP + Initial LP + Final MILP + 转换时间


