# Core Files Manifest

已迁移核心代码到双版本目录：

- `windows/src/...`
- `mac/src/...`

## 已迁移文件（10）
1. `data/generate_data_MB.py`  (MB 求解)
2. `data/generate_data_BSP.py` (BSP 求解)
3. `train/Training_edge-final.py` (GCN 训练)
4. `test/test_BSP.py`
5. `test/test_FCP.py`
6. `test/test_PCP.py`
7. `test/test_FCP_LS.py`
8. `test/LS_Path_Test.py`
9. `utils/compare_FCP_PCP_cutoff.py`
10. `report/generate_final_report.py`

## 备注
- mac 版本当前保持与 windows 版本算法逻辑一致，保证结果口径可对齐。
- 平台差异主要通过运行方式与依赖环境处理（bash 脚本 + Python3 环境）。
