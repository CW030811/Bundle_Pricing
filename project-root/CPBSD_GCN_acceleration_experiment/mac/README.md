# Mac Code Pack

该目录是核心代码的 macOS 适配版本。

## 适配说明
1. 保留 Python 主体逻辑（与 Windows 结果口径一致）
2. 补充 mac 运行脚本（bash）
3. 统一建议从项目根目录运行，避免相对路径错位

## 快速运行
```bash
cd domains/revenue-management/project-root/CPBSD_GCN_acceleration_experiment/mac
bash scripts/run_mac_checks.sh
```

## 结构
- `src/data/`：MB/BSP 求解相关
- `src/train/`：GCN 训练
- `src/test/`：FCP/PCP/BSP/LS 测试
- `src/utils/`：分析工具
- `src/report/`：报告生成
- `scripts/`：mac 运行脚本
