# 数据集兼容性分析：test_BSP_m10n15

## 数据集结构检查结果

### 数据集位置
`D:\桌面\运筹优化\BP_Code\code_submission\Dataset\test_BSP_m10n15`

### 文件格式
- 文件格式：`.msgpack`
- 文件命名：`sample_data_X_size_15_sizepricing.msgpack` (X = 1-100)
- 样本数量：100个文件

### 数据字段检查

#### 必需字段（代码期望的字段）
根据 `test_FCP_LS.py` 中的 `process_data` 函数，代码期望以下字段：

1. ✅ **product_num** - 产品数量
2. ✅ **segment_num** - 客户段数量  
3. ✅ **unit_cs** - 单位成本
4. ✅ **ship_cs** - 运输成本
5. ✅ **unit_us** - 单位效用值 (m×n 矩阵)
6. ✅ **Ns** - 每个段的客户数量
7. ✅ **opt_bundles** - 最优bundle集合
8. ✅ **opt_prices** - 最优价格
9. ✅ **opt_rev** - 最优收益
10. ✅ **running_time** - 运行时间
11. ✅ **gap** - 最优性间隙

#### 可选字段
- **cs** - 成本矩阵（如果不存在，代码会动态计算）
- **Rs** - 收益矩阵（如果不存在，代码会动态计算）

#### 额外字段（代码不使用，但存在）
根据检查，数据集还包含以下额外字段：
- `obj_hist` - 目标值历史
- `solution_sizes` - 解的大小
- `size_prices` - 尺寸价格
- `customer_bundle_map` - 客户-bundle映射

## 兼容性结论

### ✅ **代码可以直接使用**

**原因：**
1. 所有必需字段都存在
2. 数据格式与代码期望的格式一致（msgpack格式）
3. `process_data` 函数已经设计为兼容新旧数据格式
4. 代码会自动处理缺失的 `cs` 和 `Rs` 字段（动态计算）

### 使用步骤

#### 方法1：修改 `LS_Path_Test.py` 的 main 函数

在 `LS_Path_Test.py` 的 `main()` 函数中，修改数据集配置：

```python
def main():
    # ... 现有代码 ...
    
    # 修改数据集配置
    datasets = {
        'test_BSP_m10n15': os.path.join(dataset_base_dir, 'test_BSP_m10n15'),
        # 可以添加其他数据集
    }
    
    # ... 其余代码保持不变 ...
```

#### 方法2：修改 `test_FCP_LS.py` 的 main 函数

在 `test_FCP_LS.py` 的 `main()` 函数中，修改数据集配置：

```python
def main():
    # ... 现有代码 ...
    
    datasets = {
        'test_BSP_m10n15': os.path.join(dataset_base_dir, 'test_BSP_m10n15'),
    }
    
    # ... 其余代码保持不变 ...
```

### 注意事项

1. **数据集参数**：
   - m = 10（客户段数）
   - n = 15（产品数）
   - 这与之前测试的 `m10_n10_sample_100` (m=10, n=10) 不同

2. **模型兼容性**：
   - 当前使用的模型 `best_model_edge.pt` 应该可以处理不同的产品数量（n）
   - 只要客户段数（m）相同，模型应该可以直接使用

3. **文件命名**：
   - 数据集文件命名格式为 `sample_data_X_size_15_sizepricing.msgpack`
   - 代码会自动读取目录下所有 `.msgpack` 文件（忽略 `.DS_Store`）

4. **结果文件命名**：
   - 结果将保存为 `test_result_global_topk_test_BSP_m10n15.csv`（如果使用 LS_Path_Test.py）
   - 或 `test_result_local_search_mix_test_BSP_m10n15.csv`（如果使用 test_FCP_LS.py）

### 验证建议

在正式运行前，建议：
1. 先用单个样本测试，确保数据加载正常
2. 检查模型输出维度是否匹配（特别是产品数量从10变为15）
3. 验证 MILP/LP 求解器是否能正确处理新的问题规模

## 总结

**当前代码可以直接在 `test_BSP_m10n15` 数据集上运行，无需修改数据加载逻辑。**

只需要：
1. 在脚本的 `main()` 函数中添加数据集路径配置
2. 运行脚本即可

