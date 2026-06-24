# Codex 实验尝试记录

> 注：本文件记录的是一轮历史排障与实验尝试。文中的 Windows 绝对路径、`pyg311` 解释器与旧根目录脚本名不代表当前默认工作流；当前建议以 `code_submission/.venv` 和 `src/...` 目录结构为准。

## 1. 你的目标

你要求我完成以下工作：

1. 统一实验参数口径：
- `tolerance = 1e-3`
- `MIPGap = 1e-3`

2. 运行一轮 `K_Justify` 对比实验，比较：
- `k = 2m`
- `k = m`
- `k = sqrt(m)`
- `k = 2sqrt(m)`

3. 数据集使用 `dataset2_4_2026` 中指定子集：
- `test_m10n10_1e_3`
- `test_m20n10_1e_3`
- `test_m30n10_1e_3`
- `test_BSP_m10n20_1e_3`
- `test_BSP_m20n20_1e_3`

4. 模型指定为：
- `D:\桌面\运筹优化\BP_Code\code_submission\models_multi_layer_edge_update\model_edge_4layer_seed10.pt`

5. 结果输出到：
- `D:\桌面\运筹优化\BP_Code\code_submission\Local_Search_Exper`

---

## 2. 我做过的尝试

## 2.1 参数口径与数据集切换

我先对主实验链路做了参数统一和数据集切换（包括 `LS_Path_Test.py`、`LS_Path_Test_K_Justify.py`、`test_FCP_LS.py` 等），把 `tolerance` 与 `MIPGap` 调整到 `1e-3`，并将数据目录切换到 `dataset2_4_2026`。

## 2.2 K_Justify 方案改造

为了匹配你的 K 定义，我在 `LS_Path_Test_K_Justify.py` 里尝试改成：
- `k_2m_original`（映射原始策略）
- `k_m`
- `k_sqrt_m`
- `k_2sqrt_m`

并增加输出目录参数（`--output-dir`），让结果落到 `Local_Search_Exper`。

## 2.3 环境排查

Linux 默认 `python3` 无法运行（缺少 `numpy`），后切换到你提供的环境解释器：
- `D:\12.2\conda\envs\pyg311\python.exe`

并验证依赖可用：
- `numpy` 可用
- `torch` 可用
- `gurobipy` 可用（12.0.2）

## 2.4 实验实际执行

我用该解释器启动了 `LS_Path_Test_K_Justify.py`（30样本试跑，5数据集 × 4策略）。程序表面上完成了所有轮次。

---

## 3. 遇到的问题

## 3.1 首个关键问题：结果文件未生成

尽管主程序打印“完成”，但 `Local_Search_Exper` 下没有输出 CSV。  
追查发现脚本内部对单样本异常做了静默吞掉（`verbose=False`），导致“全部样本失败但主程序仍结束”。

## 3.2 第二个关键问题：模型反序列化兼容

在单样本调试中出现：
- `Can't get attribute 'EdgeScoringGCN' on <module '__main__'>`

说明 `seed10` 模型在序列化时绑定了 `__main__.EdgeScoringGCN`，与当前运行入口不一致。

## 3.3 第三个关键问题：模型结构不匹配

进一步兼容后出现：
- `'EdgeScoringGCN' object has no attribute 'l2r'`
- 随后又有维度错误：`mat1 and mat2 shapes cannot be multiplied`

这表明：
- `model_edge_4layer_seed10.pt` 的内部网络结构与当前 `test_FCP_LS.py` 的 `EdgeScoringGCN` 定义不一致（checkpoint 属于不同版本结构）。

---

## 4. 当前状态

按你的后续要求（防止污染主代码）我已执行：

1. **保存当前改动快照**为新文件（后缀 `_codexTest`）：
- `LS_Path_Test_K_Justify_codexTest.py`
- `test_FCP_LS_codexTest.py`

2. **恢复主文件**到改动前状态：
- `LS_Path_Test_K_Justify.py`
- `test_FCP_LS.py`

当前主分支代码未被此次实验尝试污染；可继续在 `_codexTest` 文件上独立调试。

---

## 5. 结论

此次未能产出有效的 K_Justify 结果 CSV，根因不是求解器或环境依赖，而是**指定 seed10 模型文件与当前推理代码结构不兼容**。  
后续若继续推进，建议只在 `_codexTest` 文件上做“模型结构兼容加载”专项修复，再重跑实验。
