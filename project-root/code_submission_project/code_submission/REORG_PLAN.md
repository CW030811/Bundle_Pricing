# Reorganization Plan (Phase-2)

## 目标
在不破坏现有实验可复现性的前提下，完成目录结构收敛。

## Phase A（安全）
- [ ] 建立新目录骨架：`src/`, `results/csv/`, `results/figures/`, `docs/reports/`, `archive/legacy/`
- [ ] 保留原目录不动，仅复制（或软链）一份关键入口脚本到 `src/`
- [ ] 生成 `MANIFEST.csv`（文件->类别映射）

## Phase B（半自动迁移）
- [ ] 将根目录 `.csv` 批量迁移至 `results/csv/`
- [ ] 将根目录 `.png` 批量迁移至 `results/figures/`
- [ ] 将根目录 `.md` 报告迁移至 `docs/reports/`（保留 README/CLAUDE 在根目录）
- [ ] 将一次性脚本迁移至 `archive/legacy/`

## Phase C（验证）
- [ ] 执行最小回归：`test_BSP.py`, `test_FCP.py`, `test_PCP.py`
- [ ] 验证报告脚本可正常读取迁移后的 csv/png 路径
- [ ] 更新 `README` 中的路径引用

## 当前状态
- 已完成：first-pass inventory + 清理缓存文件（`__pycache__`, `.DS_Store`）
- 待你确认后执行：Phase A/B/C 实际迁移
