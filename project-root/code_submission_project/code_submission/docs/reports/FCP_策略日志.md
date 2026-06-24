# FCP 策略日志

> 注：本文件记录的是历史实验日志。文中的 `pyg311`、Windows 编码设置和根目录 `test_FCP.py` 命令不再代表当前默认入口；当前默认环境是 `code_submission/.venv`，脚本路径应优先写成 `src/test/test_FCP.py`。

## 一、策略概述

**策略**: Fixed Choice Prediction (FCP) — 基于 GCN 阈值预测 + 单次 MILP 求解

**相关文件**:
- `test_FCP.py` - FCP 主脚本
- `sensitivity_cutoff_FCP.py` - Cutoff 敏感性实验脚本

---

## 二、修改记录

### 2025-02-05

| 项目 | 内容 |
|------|------|
| **修改日期** | 2025-02-05 |
| **修改内容** | 1) 模型路径切换为 `model_edge_4layer_seed1.pt`；2) 数据集切换为 `dataset2_4_2026`（MB 子目录结构）；3) 修复 process_data 中 cs 相关冗余代码；4) 新建 `sensitivity_cutoff_FCP.py` 进行 Cutoff 敏感性实验 |
| **修改目的** | 对 FCP 中 Cutoff=0.5 的选择做 Sensitivity Test，验证阈值选取的合理性 |
| **实际变化效果** | 待运行实验后填写。预期：Cutoff=0.5 附近 revenue ratio 较优；过低 cutoff 导致 Error Rate/FNR 升高，过高 cutoff 可能导致漏选 |

---

## 三、可复现性配置

- **随机种子**: `np.random.seed(42)`（sensitivity 脚本）
- **模型路径**: `D:\桌面\运筹优化\BP_Code\code_submission\models_multi_layer_edge_update\model_edge_4layer_seed1.pt`
- **数据集**: `dataset2_4_2026` 下 `test_m10n10_1e_3`, `test_m20n10_1e_3`, `test_m30n10_1e_3`
- **Cutoff 敏感性**: 0.1, 0.2, ..., 0.9；每数据集 30 样本

---

## 四、运行方式

```bash
chcp 65001
conda activate pyg311
python test_FCP.py
python sensitivity_cutoff_FCP.py
```
