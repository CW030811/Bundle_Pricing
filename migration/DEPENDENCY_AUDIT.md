# Revenue-management Dependency Audit (Step5E)

## Overview
- 方法：扫描新主环境根目录源码的 import（排除 .venv），并尝试导出旧环境包列表。
- 结果：源码扫描得到第三方候选；旧环境包列表未能导出（旧 .venv 不在预期路径）。

## Source-scanned imports (third-party candidates)
- gurobipy
- numpy
- pandas
- torch
- torch_geometric
- msgpack
- msgpack_numpy
- matplotlib
- tqdm
- 可能为项目内脚本/测试：LS_Path_Test, LS_Path_Test_Matrix, generate_data_*, solve_* , test_*（可能不是第三方包）

## Old environment package inventory
- 旧环境路径：`/Users/sensen/.openclaw/workspace/revenue-management/.venv`
- 当前检查：该路径下未发现 `.venv/bin`，无法执行 `pip freeze`
- 结论：**旧环境包列表未能导出**（需要确认旧 .venv 是否仍存在/可用）

## Proposed minimal install set (core)
- numpy
- pandas
- torch
- torch_geometric
- gurobipy
- msgpack
- msgpack_numpy
- tqdm

## Optional / secondary packages
- matplotlib（可视化/分析辅助）

## High-risk packages
- gurobipy（需要许可证与本机配置）
- torch / torch_geometric（平台与版本敏感，可能涉及 CUDA/CPU 构建差异）

## Recommended next step
1) 先安装最小集合（优先 CPU 版本）
2) 验证最小脚本可运行（导入 + 简单执行）
3) 再补充可视化等辅助包
4) 若需要 GPU/CUDA，再单独规划 torch/torch_geometric 版本
