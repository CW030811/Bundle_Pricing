# test_FCP_LS.py 策略日志

> 注：本文件记录的是历史实验日志。文中的根目录 `test_FCP_LS.py`、`run_experiment.bat` 与 `pyg311` 命令属于旧工作流；当前默认环境是 `code_submission/.venv`，脚本路径应优先写成 `src/test/test_FCP_LS.py`。

## 一、代码结构

### 1.1 核心模块

**文件**: `test_FCP_LS.py` (1314行)

**主要组件**:

1. **EdgeScoringGCN 模型类** (第38-133行)
   - 边评分图卷积网络模型
   - 支持三种评分类型: 'bilinear', 'dot', 'mlp'
   - 使用双向 GENConv 进行消息传递

2. **数据处理函数**
   - `process_data()` (第137-226行): 处理 msgpack 数据文件，构建图数据
   - `bundle_to_product_set()` (第260-263行): Bundle ID 到产品集合的转换

3. **MILP 求解函数**
   - `revenue_ratio_with_optimal_bundle()` (第268-409行): 
     - 使用 MILP 求解器优化 bundle 分配
     - 仅计算预测 bundle 集合的 Rs 和成本矩阵
     - 返回收入比率、求解时间和最优 bundle 分配

4. **LP 求解函数**
   - `revenue_ratio_LP()` (第412-571行):
     - 使用 LP 求解器快速评估给定分配的收入
     - 固定 bundle 分配，仅优化价格变量
     - 用于 Local Search 中的邻域评估

5. **Local Search 核心函数**
   - `generate_neighbor_assignments()` (第592-633行): 
     - 基于概率矩阵生成邻域分配
     - 使用 Add/Drop 操作：添加最高概率的未选产品，移除最低概率的已选产品
   - `local_search_with_lp()` (第636-759行):
     - 混合 MILP-LP Local Search 主函数
     - 工作流程：初始 MILP → LP 评估 → 邻域搜索循环 → 最终 MILP 验证

6. **辅助函数**
   - `predict_initial_bundles()` (第762-808行): 使用 GCN 模型生成初始预测
   - `solve_initial_milp()` (第812-821行): 初始 MILP 求解
   - `check_lp_feasibility_and_revenue()` (第573-589行): LP 可行性和收入检查
   - `convert_pred_assort_to_assignment()` (第229-243行): 预测矩阵到分配的转换
   - `assignment_to_pred_assort()` (第246-257行): 分配到预测矩阵的转换

7. **评估和可视化**
   - `evaluate_single_dataset()` (第941-1085行): 单数据集评估函数
   - `plot_search_paths()` (第824-936行): 搜索路径可视化
   - `plot_combined_search_paths()` (第1088-1204行): 多数据集组合可视化
   - `main()` (第1207-1313行): 主函数，协调整个评估流程

### 1.2 工作流程

```
1. 数据加载
   └─> process_data(): 加载 msgpack 文件，构建图数据

2. 初始预测生成
   └─> predict_initial_bundles(): GCN 推理生成初始 bundle 预测和概率矩阵

3. 初始 MILP 求解
   └─> solve_initial_milp(): 对初始预测进行 MILP 优化，获得基准收入

4. Local Search 优化
   └─> local_search_with_lp():
       ├─> Step 1: 初始 MILP 求解获得可行分配
       ├─> Step 2: LP 求解获得当前最佳收入
       ├─> Step 3: 邻域搜索循环 (最多 max_iterations 次)
       │   ├─> generate_neighbor_assignments(): 生成邻域分配
       │   ├─> check_lp_feasibility_and_revenue(): LP 快速评估
       │   └─> 贪心策略：发现改进即接受
       ├─> Step 4: 转换最优分配到预测矩阵
       └─> Step 5: 最终 MILP 验证

5. 结果保存和可视化
   └─> 保存 CSV 结果文件，生成收敛图
```

## 二、基本参数设置

### 2.1 Local Search 参数

```python
max_iterations = 50          # 最大迭代次数
tolerance = 1e-6            # 收入改进容忍度
```

### 2.2 GCN 模型参数

```python
# EdgeScoringGCN 模型配置
in_channels = 4             # 输入特征维度
hidden_channels = 128        # 隐藏层维度
num_layers = 2               # GCN 层数
edge_dim = 1                 # 边特征维度
score_type = 'bilinear'      # 评分类型: 'bilinear' | 'dot' | 'mlp'
use_edge_attr = True        # 是否使用边属性
dropout = 0.5                # Dropout 率
```

### 2.3 MILP 求解器参数 (Gurobi)

**位置**: `revenue_ratio_with_optimal_bundle()` 函数 (第331-334行)

```python
model = gp.Model("Bundle MILP")
model.Params.OutputFlag = 0      # 关闭输出
model.Params.MIPGap = 1e-2       # MIP 相对间隙: 0.01 (1%)
model.Params.TimeLimit = 600     # 时间限制: 600 秒 (10 分钟)
```

**变量类型**:
- `p[bundle]`: 连续变量，价格变量，下界为 0
- `theta[k, bundle]`: 二进制变量，客户 k 是否选择 bundle
- `s[k]`: 连续变量，客户 k 的剩余
- `S[k, bundle]`: 连续变量，客户 k 从 bundle 获得的剩余，下界为 0
- `Z[k, bundle]`: 连续变量，客户 k 选择 bundle 的利润
- `P[k, bundle]`: 连续变量，客户 k 为 bundle 支付的价格，下界为 0

**约束类型**:
- IC (激励相容) 约束
- 子可加性约束 (仅对预测 bundle 集合)
- 价格一致性约束
- 分配约束 (每个客户恰好选择一个 bundle)

### 2.4 LP 求解器参数 (Gurobi)

**位置**: `revenue_ratio_LP()` 函数 (第549-556行)

```python
model = gp.Model("Bundle LP-IC")
model.setParam("OutputFlag", 0)   # 关闭输出
model.setParam("Method", -1)      # 自动方法选择 (-1 = 自动)
                                  # 说明: 对于小规模问题通常默认使用 Simplex
                                  # Barrier (Method=2) 适用于大规模稀疏问题
model.setParam("Presolve", 2)     # 积极预处理 (默认值为 2，显式设置以确保清晰)
model.setParam("Threads", 1)      # 单线程 (避免小问题的开销)
model.Params.TimeLimit = 300      # 时间限制: 300 秒 (5 分钟)
```

**变量类型** (固定 bundle 分配后):
- `p[bundle]`: 连续变量，价格变量，下界为 0
- `s[k]`: 连续变量，客户 k 的剩余

**约束类型**:
- IC (激励相容) 约束: `s[k] >= R[k,i] - p[i]` 对所有 bundle i
- 上界约束: `s[k] <= R[k,b_k] - p[b_k]` (锁定分配 b_k)
- 子可加性约束 (仅对涉及的 bundle 集合)
- 空 bundle 价格约束: `p[0] == 0`

### 2.5 数据集处理参数

```python
max_samples_per_dataset = 1000    # 每个数据集最大处理样本数
```

### 2.6 阈值参数

```python
threshold = 0.0                   # GCN logits 转二进制的阈值
                                  # (logits >= 0.0 时选择产品)
```

## 三、测试数据集

### 3.1 数据集配置

**数据集路径**: `Dataset/` 目录下

| 数据集名称 | 路径 | 样本数 | 客户段数 (m) | 产品数 (n) |
|-----------|------|--------|-------------|-----------|
| m10_n10_sample_100 | `Dataset/m10_n10_sample_100/` | 100 | 10 | 10 |
| m20_n10_sample_100 | `Dataset/m20_n10_sample_100/` | 100 | 20 | 10 |
| m30_n10_sample_100 | `Dataset/m30_n10_sample_100/` | 100 | 30 | 10 |

### 3.2 数据格式

- **文件格式**: msgpack
- **文件命名**: `sample_data_*.msgpack`
- **数据字段**:
  - `product_num`: 产品数量
  - `segment_num`: 客户段数量
  - `unit_cs`: 单位成本
  - `ship_cs`: 运输成本
  - `unit_us`: 单位效用
  - `Ns`: 需求矩阵
  - `opt_bundles`: 最优 bundle 分配
  - `opt_prices`: 最优价格
  - `opt_rev`: 最优收入
  - `running_time`: 基准运行时间
  - `gap`: 最优性间隙

## 四、实验结果

### 4.1 数据集: m10_n10_sample_100

**实验日期**: 2024年 (根据文件修改时间)

**样本数**: 100

**结果文件**: `test_result_local_search_mix_m10_n10_sample_100.csv`

#### 4.1.1 Revenue Ratio 统计

| 指标 | 值 |
|------|-----|
| **平均值** | **0.9956** |
| **标准差** | 0.0080 |
| **最小值** | 0.9613 |
| **最大值** | 1.0059 |

**分析**:
- 平均收入比率达到 **99.56%**，接近最优解
- 标准差较小 (0.0080)，表明结果稳定
- 最小值 0.9613 表示最差情况下仍能达到 96.13% 的最优收入
- 最大值 1.0059 表示部分情况下甚至略微超过最优解（可能由于数值精度或求解器差异）

#### 4.1.2 Time Ratio 统计

| 指标 | 值 |
|------|-----|
| **平均值** | **0.1006** |
| **标准差** | 0.0367 |
| **最小值** | 0.0252 |
| **最大值** | 0.2025 |

**分析**:
- 平均时间比率仅为 **10.06%**，即运行时间仅为基准方法的约 1/10
- 标准差 0.0367 表明时间性能稳定
- 最快情况下仅需基准时间的 2.52%
- 最慢情况下也仅为基准时间的 20.25%

#### 4.1.3 详细性能指标 (基于 CSV 数据分析)

**平均迭代次数**: 7.18 次

**平均改进次数**: 6.18 次

**平均 LP 求解器调用次数**: **80.71 次**

**平均 MILP 求解器调用次数**: 2 次 (初始 + 最终)

**改进率**: 大部分样本 (约 95%+) 在 Local Search 过程中实现了收入改进

#### 4.1.4 m10_n10数据集策略对比总结

**测试数据集**: m10_n10_sample_100 (100个样本)

**重要说明**：时间统计说明
- **Local Search时间**：指整个 `local_search_with_lp_global_topk` 函数的执行时间，包括：
  - 初始MILP求解（在函数内部）
  - 初始LP求解（在函数内部）
  - 迭代循环（total_iteration_time）
  - 最终MILP求解（在函数内部）
  - 其他函数内部开销
- **迭代循环时间**：仅指迭代循环部分的时间（total_iteration_time），不包括初始/最终MILP和LP求解

| 指标 | 原策略（Segment-based） | Global Top-K策略（K=sqrt(m)） | 改善率 |
|------|------------------------|------------------------------|--------|
| **平均Local Search时间（整个函数）** | 0.4964s | 0.2195s | **55.77%** ↓ |
| **平均迭代循环时间** | - | 0.1223s | - |
| **平均迭代次数** | 6.88 | 5.56 | **19.19%** ↓ |
| **平均每轮迭代时间** | 0.0721s | 0.0395s | **45.27%** ↓ |
| **平均LP调用次数** | 77.58 | 24.89 | **67.92%** ↓ |
| **平均每次LP调用时间** | 6.40ms | 8.82ms | -37.85% ↑ |
| **平均Revenue Ratio** | 0.9959 | 0.9936 | -0.23% ↓ |

**标准差统计**:
- 原策略：Local Search时间标准差 0.1591s，迭代次数标准差 2.48，LP调用次数标准差 28.25
- Global Top-K策略：Local Search时间标准差 0.0568s，迭代次数标准差 2.27，LP调用次数标准差 9.48
- **Global Top-K策略的稳定性更好**（标准差更小）

**Global Top-K策略时间分解（Local Search总时间 0.2195s）**:
- 初始MILP时间：0.0491s (22.4%)
- 迭代循环时间：0.1223s (55.8%)
- 其他时间（初始LP + 最终MILP + 开销）：0.0482s (21.8%)

#### 4.1.5 LP 求解器性能分析（m10_n10数据集对比）

**关键发现**: 时间瓶颈主要在 **LP 调用次数**，而非每次 LP 调用时间

**原策略（Segment-based策略）统计**:
| 指标 | 值 |
|------|-----|
| **平均每次 LP 调用时间** | **6.40 毫秒** (0.006400 秒) |
| 平均 LP 调用次数 | 77.58 次 |
| 平均 Local Search 时间 | 0.4964 秒 |
| 平均迭代次数 | 6.88 次 |
| 平均每轮迭代时间 | 0.0721 秒 |

**Global Top-K策略（K=sqrt(m)）统计**:
| 指标 | 值 |
|------|-----|
| **平均每次 LP 调用时间** | **8.82 毫秒** (0.008820 秒) |
| 平均 LP 调用次数 | 24.89 次 |
| 平均 Local Search 时间 | 0.2195 秒 |
| 平均迭代次数 | 5.56 次 |
| 平均每轮迭代时间 | 0.0395 秒 |

**策略对比**:
- **Local Search时间改善**: 55.77% (从0.4964s减少到0.2195s)
- **LP调用次数减少**: 67.92% (从77.58次减少到24.89次)
- **迭代次数减少**: 19.19% (从6.88次减少到5.56次)
- **每轮迭代时间改善**: 45.27% (从0.0721s减少到0.0395s)
- **Revenue Ratio差异**: -0.23% (从0.9959减少到0.9936，差异很小)

**时间瓶颈分析**:
- **LP 调用次数与 Local Search 时间的相关系数: 0.9673** (非常高的正相关)
- 每次 LP 调用时间与 Local Search 时间的相关系数: -0.3435 (负相关)
- **结论**: 时间瓶颈主要在 LP 调用次数上，而非每次 LP 调用时间
- **Global Top-K策略通过减少LP调用次数（67.92%）实现了显著的时间改善（55.77%）**

**时间组成** (基于m10_n10_sample_100数据集的实际测试结果):

**原策略（Segment-based策略）时间组成**:
- GCN 推理时间: 约 0.0206 秒 (3.76%)
- 初始 MILP 时间: 约 0.0503 秒 (8.53%)
- **Local Search 时间: 0.4964 秒 (87.71%)**
  - **LP 求解总时间**: 约 0.4964 秒 (100%)
    - 平均每次 LP 调用: 6.40 毫秒
    - LP 调用次数: 约 77.58 次
    - LP 求解时间 = 77.58 × 0.00640 ≈ 0.4965 秒
  - **其他开销**: 可忽略（Candidate构建、Neighbor生成等时间包含在LP调用中）

**Global Top-K策略（K=sqrt(m)）时间组成**:

**总体时间组成**（整个策略执行时间）:
- GCN 推理时间: 约 0.0206 秒 (3.76%)
- 初始 MILP 时间: 约 0.0497 秒 (8.53%)
- **Local Search 时间（整个函数）: 0.2195 秒 (87.71%)**
  - 初始MILP（函数内部）: 0.0491 秒 (22.4%)
  - 初始LP（函数内部）: 约 0.005 秒 (2.3%，估算)
  - **迭代循环时间: 0.1223 秒 (55.8%)**
  - 最终MILP（函数内部）: 约 0.043 秒 (19.6%，估算)
  - 其他开销: 约 0.0002 秒 (0.1%，估算)

**迭代循环时间详细分解**（0.1223秒，仅迭代循环部分）:
  - **Add Candidate 构建时间**: 0.000673 秒 (0.55%)
    - 包括：遍历所有 (k,j) 对，筛选 current_pred_assort[k,j]==0 的位置，计算score，排序取Top-K
  - **Drop Candidate 构建时间**: 0.000673 秒 (0.55%)
    - 包括：遍历所有 (k,j) 对，筛选 current_pred_assort[k,j]==1 且 prob[k,j]>=0.5 的位置，计算score，排序取Top-K
  - **Neighbor 生成时间**: 0.000559 秒 (0.45%)
    - 包括：将Top-K candidates转换为neighbor assignments（pred_assort复制、修改、转换）
  - **Neighbor 遍历时间（不包括LP）**: 0.000024 秒 (0.02%)
    - 包括：for循环开销、变量赋值、条件判断等（非常小）
  - **LP 求解总时间**: 0.119508 秒 (97.06%)
    - 平均每次 LP 调用: 4.80 毫秒
    - LP 调用次数: 约 24.89 次
    - LP 求解时间 = 24.89 × 0.00480 ≈ 0.1195 秒（与总时间基本一致）
  - **其他开销**: 0.002221 秒 (1.80%)
    - 包括：时间测量开销、函数调用开销、迭代控制等

**注意**：迭代循环时间（0.1223s）的详细分解加起来应该等于0.1223s，这是迭代循环部分的时间，不包括函数内部的初始/最终MILP和LP求解。

**优化潜力**:
- 如果减少 20% LP 调用次数: 可节省 **0.0998 秒 (20.39%)**
- 如果减少 20% 每次 LP 调用时间: 可节省 **0.0998 秒 (20.39%)**
- 组合优化: 可节省 **0.1996 秒 (40.78%)**

**详细时间分解说明** (基于m10_n10_sample_100数据集的实际测试结果):

Local Search 时间主要由以下部分组成：

1. **Candidate 构建阶段** (约 1.1%):
   - Add Candidate 构建：0.000673秒 (0.55%)
     - 遍历 m×n 个位置，筛选未选中的位置，计算score，排序取Top-K
   - Drop Candidate 构建：0.000673秒 (0.55%)
     - 遍历 m×n 个位置，筛选已选中且prob>=0.5的位置，计算score，排序取Top-K
   - **优化潜力**：可以使用向量化操作（NumPy）替代双层for循环，可能减少50%构建时间，但总体影响较小（<1%）

2. **Neighbor 生成阶段** (约 0.45%):
   - 将Top-K candidates转换为neighbor assignments
   - 包括：pred_assort矩阵复制、修改、转换为assignment字典
   - **优化潜力**：较小，已相对高效

3. **Neighbor 遍历阶段** (约 0.02%):
   - for循环开销、变量赋值、条件判断等
   - **优化潜力**：极小，主要是Python解释器开销，可忽略

4. **LP 求解阶段** (约 97.06%):
   - 这是时间瓶颈的主要来源
   - 每次LP调用约4.80毫秒，调用次数平均24.89次（Global Top-K策略显著减少了LP调用次数）
   - **优化潜力**：最大，通过进一步减少LP调用次数可以显著提升性能

**优化建议**:
1. **优先级 1**: 减少 LP 调用次数（早停、邻域筛选、优先级排序）
   - 当前平均LP调用次数：24.89次（Global Top-K策略已显著减少）
   - 预期效果：进一步减少20% LP调用次数可节省约19.4% Local Search时间
   - 实际效果：Global Top-K策略（K=sqrt(m)）相比原策略已减少约70% LP调用次数

2. **优先级 2**: 优化 Candidate 构建（向量化操作替代for循环）
   - 当前Candidate构建时间：0.001346秒（Add+Drop，占1.1%）
   - 预期效果：减少50% Candidate构建时间，但总体影响较小（<0.6%）
   - 实际价值：较小，因为Candidate构建时间占比很低

3. **优先级 3**: 优化每次 LP 调用时间（模型简化、参数优化）
   - 当前平均每次LP调用时间：4.80毫秒
   - 预期效果：减少20%每次LP调用时间可节省约19.4% Local Search时间
   - 实际价值：中等，但LP求解器本身已相对高效

**关键发现**（基于m10_n10_sample_100数据集，100个样本）:
- **Global Top-K策略（K=sqrt(m)）已显著优化了时间性能**：
  - LP调用次数从77.58次减少到24.89次（减少67.92%）
  - Local Search时间从0.4964秒减少到0.2195秒（减少55.77%）
  - 迭代次数从6.88次减少到5.56次（减少19.19%）
  - 每轮迭代时间从0.0721秒减少到0.0395秒（减少45.27%）
  - Revenue Ratio差异很小（从0.9959到0.9936，仅-0.23%）
- **时间瓶颈确认**：
  - 原策略：LP求解时间占Local Search时间的100%（所有时间都在LP求解上）
  - Global Top-K策略：LP求解时间占Local Search时间的97.06%，是绝对的主要瓶颈
- **Candidate构建时间占比很小**（1.1%），优化价值有限
- **平均每次LP调用时间略有增加**（从6.40ms到8.82ms），但通过大幅减少调用次数，总体时间显著改善

### 4.2 数据集: m20_n10_sample_100

**状态**: ⏳ 待运行实验

**预期配置**:
- 样本数: 100
- 客户段数: 20
- 产品数: 10

**预期结果文件**: `test_result_local_search_mix_m20_n10_sample_100.csv`

### 4.3 数据集: m30_n10_sample_100

**状态**: ⏳ 待运行实验

**预期配置**:
- 样本数: 100
- 客户段数: 30
- 产品数: 10

**预期结果文件**: `test_result_local_search_mix_m30_n10_sample_100.csv`

## 五、策略优势分析

### 5.1 混合 MILP-LP 策略的优势

1. **计算效率**
   - LP 求解速度远快于 MILP (通常快 10-100 倍)
   - 仅在初始和最终阶段使用 MILP，中间使用 LP 快速评估
   - 平均时间比率仅 10.06%，大幅提升效率

2. **解质量**
   - 平均收入比率达到 99.56%，接近最优解
   - Local Search 能够持续改进初始解
   - 最终 MILP 验证确保解的可行性

3. **可扩展性**
   - 仅计算预测 bundle 集合的 Rs 和成本矩阵，而非全部 2^n 个 bundle
   - 邻域搜索策略限制搜索空间
   - 适用于中等规模问题 (n=10, m=10-30)

### 5.2 贪心策略的优势

- **快速收敛**: 发现改进即接受，避免过度搜索
- **计算资源高效**: 减少不必要的邻域评估
- **实际效果**: 大部分样本在 6-7 次迭代内收敛

### 5.3 概率引导的邻域生成

- **智能搜索**: 基于 GCN 输出的概率矩阵指导 Add/Drop 操作
- **高质量邻域**: 优先考虑高概率产品，提高改进可能性
- **平衡探索**: Add 和 Drop 操作确保搜索空间覆盖

## 六、实验运行记录

### 6.1 已完成的实验

- ✅ **m10_n10_sample_100**: 已完成，结果已保存

### 6.2 待完成的实验

- ⏳ **m20_n10_sample_100**: 待运行
- ⏳ **m30_n10_sample_100**: 待运行

### 6.3 运行命令

```bash
cd code_submission
python test_FCP_LS.py
```

或使用批处理文件:
```bash
cd code_submission
run_experiment.bat
```

## 七、输出文件说明

### 7.1 结果文件

每个数据集生成一个 CSV 文件，包含以下列:

1. `n_products`: 产品数量
2. `revenue_ratio`: 收入比率 (相对于最优解)
3. `runtime_ratio`: 运行时间比率 (相对于基准方法)
4. `total_time`: 总运行时间 (秒)
5. `base_running_time`: 基准运行时间 (秒)
6. `threshold_time`: GCN 推理时间 (秒)
7. `initial_milp_time`: 初始 MILP 求解时间 (秒)
8. `local_search_time`: Local Search 总时间 (秒)
9. `initial_revenue`: 初始收入比率
10. `improvement`: 改进幅度 (最终收入 - 初始收入)
11. `iterations`: 迭代次数
12. `improvements`: 改进次数
13. `lp_solver_calls`: LP 求解器调用次数
14. `milp_solver_calls`: MILP 求解器调用次数

### 7.2 可视化文件

- `combined_local_search_mix_convergence_plots.png`: 多数据集组合收敛图
  - 包含两个子图: 收入比率 vs 迭代次数, 收入比率 vs 时间

## 八、关键参数总结表

| 参数类别 | 参数名 | 值 | 说明 |
|---------|--------|-----|------|
| **Local Search** | max_iterations | 50 | 最大迭代次数 |
| | tolerance | 1e-6 | 收入改进容忍度 |
| **MILP 求解器** | OutputFlag | 0 | 关闭输出 |
| | MIPGap | 1e-2 | MIP 相对间隙 1% |
| | TimeLimit | 600 | 时间限制 600 秒 |
| **LP 求解器** | OutputFlag | 0 | 关闭输出 |
| | Method | -1 | 自动方法选择 |
| | Presolve | 2 | 积极预处理 |
| | Threads | 1 | 单线程 |
| | TimeLimit | 300 | 时间限制 300 秒 |
| **数据集** | max_samples_per_dataset | 1000 | 最大处理样本数 |
| **GCN 模型** | hidden_channels | 128 | 隐藏层维度 |
| | num_layers | 2 | GCN 层数 |
| | score_type | 'bilinear' | 评分类型 |
| | threshold | 0.0 | Logits 转二进制阈值 |

---

**日志更新日期**: 2024年
**最后更新**: 完成 m10_n10_sample_100 数据集实验，待完成 m20 和 m30 数据集实验
