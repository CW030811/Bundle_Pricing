# LP-MILP Improvement Verification 策略日志

> 注：本文件记录的是历史实验日志。文中的 `pyg311`、Windows 编码设置和旧根目录脚本名不再代表当前默认入口；当前默认环境是 `code_submission/.venv`。

## 一、实验概述

**目的**: 验证 Local Search 过程中每次 LP-guided improvement 是否真实有效（即是否在 MILP Solver 下同样有提升）。

**相关文件**:
- `verify_lp_milp_improvement.py` - 验证脚本主程序
- `LP_MILP_verification_results.json` - 6 个样本的完整记录
- `LP_MILP_verification_plot.png` - 2×3 子图 LP vs MILP 路径对比
- `LP_MILP_verification_summary.md` - 总结报告

---

## 二、修改记录

### 2025-02-04

| 项目 | 内容 |
|------|------|
| **修改日期** | 2025-02-04 |
| **修改内容** | 新建 `verify_lp_milp_improvement.py`、`verify_lp_milp_improvement_策略日志.md`；新增 `local_search_with_lp_milp_verification()`，在每次 LP 发现改进时调用 MILP 校验 |
| **修改目的** | 验证 LP-guided improvements 是否成功转化为 MILP 提升，记录 lp_path、milp_path、lp_to_milp_translation |
| **实际变化效果** | 6 个样本运行完成。m20_n10_sample_100 存在 1 次 LP 改进未转化为 MILP 提升（第 3 次改进：LP 0.9838，MILP 0.9881 < prev 0.9884）；其余 5 个样本全部转化成功。整体结论：LP 引导在绝大多数情况下有效，偶发 MILP 因 bundle 集合内重分配导致单步未提升 |

---

## 三、可复现性配置

- **随机种子**: `np.random.seed(42)`, `torch.manual_seed(42)`
- **数据集**: m10_n10_sample_100, m20_n10_sample_100, m30_n10_sample_100, test_BSP_m10n15, test_BSP_m10n20, test_BSP_m10n25
- **样本选择**: sample_id=0（各数据集第一个样本）
- **Local Search 参数**: max_iterations=50, tolerance=1e-6
- **策略**: Global Top-K (K=ceil(sqrt(m)))

---

## 四、运行顺序

1. `chcp 65001` 然后 `conda activate pyg311`
2. `python verify_lp_milp_improvement.py`
3. 查看 `LP_MILP_verification_summary.md`、`LP_MILP_verification_plot.png`
