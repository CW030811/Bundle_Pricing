# K 值选择 Justify 实验 策略日志

> 注：本文件记录的是历史实验日志。文中的 `pyg311`、Windows 编码设置和根目录 `LS_Path_Test*.py` 命令不再代表当前默认入口；当前默认环境是 `code_submission/.venv`，脚本路径应优先写成 `src/test/...`。

## 一、实验概述

**目的**: 通过控制变量实验，对比不同 K 值策略（常数 K、K=sqrt(m)、K=sqrt(m*n)、原策略 2*m）在 Revenue Ratio 与 Time Ratio 上的表现，论证 K = ceil(sqrt(m)) 的合理性。

**相关文件**:
- `LS_Path_Test_K_Justify.py` - 参数化 K 策略的实验主脚本
- `generate_K_justify_report.py` - 汇总 CSV 并生成 Markdown 报告
- `justify_K_{strategy}_{dataset}.csv` - 各策略×数据集的实验结果

---

## 二、修改记录

### 2025-02-03

| 项目 | 内容 |
|------|------|
| **修改日期** | 2025-02-03 |
| **修改内容** | 新建 `LS_Path_Test_K_Justify.py`、`generate_K_justify_report.py`、`K_Justify_策略日志.md` |
| **修改目的** | 实现 K 值选择 Justify 实验方案，系统对比 5 种 K 策略以论证 K=sqrt(m) 的合理性 |
| **实际变化效果** | 待运行实验后填写。预期：K=sqrt(m) 在 Revenue 上与原策略接近（差异<2%），在 Time Ratio 上显著优于原策略（m 较大时 LP 调用减少约 60-80%） |

---

## 三、可复现性配置

- **随机种子**: `np.random.seed(42)`, `torch.manual_seed(42)`
- **数据集**: m10_n10_sample_100, m20_n10_sample_100, m30_n10_sample_100, test_BSP_m10n15, test_BSP_m20n15
- **每数据集样本数**: max_samples=100
- **Local Search 参数**: max_iterations=50, tolerance=1e-6
- **K 策略**: original, K_const_5, K_const_10, K_sqrt_m, K_sqrt_mn

---

## 四、运行顺序

1. `chcp 65001 && conda activate pyg311`
2. `python LS_Path_Test_K_Justify.py`
3. `python generate_K_justify_report.py`
4. 查看 `K值选择Justify实验报告.md`
