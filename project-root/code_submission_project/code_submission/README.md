# code_submission

重组后的目录约定：

- `src/`：主要 Python 脚本（已二级细分）
  - `src/train/`：训练脚本
  - `src/test/`：测试与实验运行脚本
  - `src/analyze/`：分析/验证脚本
  - `src/data/`：数据生成脚本
  - `src/report/`：报告与绘图生成脚本
  - `src/utils/`：工具与对比脚本
  - `src/legacy/`：暂未归类的历史脚本
- `results/csv/`：实验结果表
- `results/figures/`：可视化图
- `docs/reports/`：实验报告与日志
- `dataset2_4_2026/`, `Dataset/`：数据集
- `gurobi_stats_logs/`：求解器日志
- `models_multi_layer_edge_update/`：模型权重

说明：本次为自动归档，脚本内若使用相对路径，请优先从 `code_submission` 根目录运行；后续可逐步统一到 `src/config.py` 管理路径。

## Current Workflow

- 当前推荐环境：`.venv`
- 激活方式：`source .venv/bin/activate`
- 当前主要脚本位置：
  - `src/test/`：Local Search / FCP / PCP / BSP 旧主线实验
  - `src/data/`：CPBSD / GCN / label / training / coverage / compare 新主线脚本
  - `src/analyze/`、`src/report/`：分析与报告生成

当前仍在使用的实验根目录以 `domains/revenue-management/experiments/` 为主，不要默认使用 `code_submission/experiments/` 下的镜像副本。

历史 Windows 批处理和 `pyg311` 相关说明仅用于回溯旧工作流，不再作为当前默认入口。
