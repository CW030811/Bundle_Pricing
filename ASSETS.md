# revenue-management / ASSETS

## Overview
这是 revenue-management domain 的统一资产地图，用于跨目录定位相关资产。

## Primary control-plane path
- `domains/revenue-management/`
- 负责导航、边界、长期记忆与任务状态。

## Legacy memory paths
- `domains/revenue-management/legacy-memory/project-memory/`
- `domains/revenue-management/legacy-memory/revenue-management.md`
- 说明：历史记忆来源，仅作回溯参考；新的结构化更新优先写入 `domains/revenue-management/`。

## Working project path
- `domains/revenue-management/project-root/`
- 资产类型概括：研究文档与总结、代码、数据、结果、模型、日志、论文与参考库、配置记录。
- 说明：当前主工作资产汇聚处，逻辑上属于 revenue-management domain。

## Experiment asset path
- `domains/revenue-management/experiments/`
- 说明：当前实验资产总入口。不同实验子目录（如 `cpbsd_baselines_v2/`, `cpbsd_main_n5/`, `mb_bundle_coverage_v2/` 等）共享这一层级。
- 补充：部分旧实验目录已在清理过程中移出工作区做桌面备份，不应再默认假设 `cpbsd_baselines/` 仍在工作区内。

## Recommended access order
1. domains/revenue-management/DOMAIN.md
2. domains/revenue-management/TASKS.md
3. domains/revenue-management/MEMORY.md
4. domains/revenue-management/ASSETS.md
5. 视需要进入 `domains/revenue-management/project-root/` 或 `domains/revenue-management/experiments/`

## Migration notes
- 现阶段保留原位（仅遗留环境项）：`revenue-management/.venv`、`.DS_Store`。
- 已收拢为主入口：`domains/revenue-management/project-root/`。
- 实验资产当前统一从 `domains/revenue-management/experiments/` 进入。
- 历史记忆收拢：`domains/revenue-management/legacy-memory/`。
