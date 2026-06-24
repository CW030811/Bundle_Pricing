# Code Submission Project Inventory (First-pass整理)

更新时间：自动梳理（first pass）

## 1) 总体规模
- 文件总数：**4233**
- 主要类型：
  - `.msgpack`：3400（数据集样本）
  - `.log`：451（Gurobi日志）
  - `.csv`：113（实验结果）
  - `.pt`：61（模型权重）
  - `.py`：59（代码脚本）
  - `.md`：43（项目文档）

## 2) 顶层目录职能
- `dataset2_4_2026/`：主实验数据集（大量 msgpack）
- `Dataset/`：历史/补充数据集
- `gurobi_stats_logs/`：求解器日志
- `models_multi_layer_edge_update/`：多层边更新模型权重
- `Local_Search_Exper/`：本地搜索实验中间结果
- `Paper/`、`PaperLibrary/`：论文与参考材料
- 根目录散落：脚本、报告、图表、csv结果（当前最混乱）

## 3) 关键入口脚本（可作为后续收敛入口）
- 数据生成：
  - `generate_data_MB.py`
  - `generate_data_BSP.py`
- 训练：
  - `Training_edge-final.py`
- 主要测试：
  - `test_BSP.py`
  - `test_FCP.py`
  - `test_PCP.py`
  - `test_FCP_LS.py`
- 分析报告：
  - `analyze_solution_space.py`
  - `generate_comparison_report.py`
  - `generate_final_report.py`

## 4) 当前混乱点（已识别）
1. 根目录混放大量结果文件（csv/png/md/脚本混在一起）
2. 同主题文件多套命名（global_topk / sqrtm / matrix / loop 并行）
3. 历史实验产物与最终版本未分层
4. `__pycache__/`、`.DS_Store` 等可清理文件存在

## 5) 建议的后续整理分层（下一步执行）
建议将根目录文件按功能迁移到：
- `src/`：核心可复现代码（.py）
- `results/csv/`：结果表
- `results/figures/`：图表
- `results/logs/`：求解日志（可链接到 `gurobi_stats_logs`）
- `docs/reports/`：实验报告与中文日志
- `artifacts/models/`：模型权重（可链接到 `models_multi_layer_edge_update`）
- `archive/legacy/`：历史脚本与一次性分析

> 注：本轮先做“阅读+梳理+索引”，未进行大规模移动，避免打断现有代码引用路径。
