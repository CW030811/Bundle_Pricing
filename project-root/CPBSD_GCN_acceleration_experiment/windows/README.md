# Windows Code Pack

该目录是核心代码的 Windows 版本（原始风格，最少改动）。

## 结构
- `src/data/`：MB/BSP 数据与求解
- `src/train/`：GCN 训练
- `src/test/`：FCP/PCP/BSP/LS 测试
- `src/utils/`：对比分析工具
- `src/report/`：报告生成

## 运行建议
- Python 3.10/3.11
- Gurobi + gurobipy
- PyTorch + PyG

> 该版本保留原习惯，便于回溯历史结果。