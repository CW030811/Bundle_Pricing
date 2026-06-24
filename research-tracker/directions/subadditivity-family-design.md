# Research Direction

## 基本信息

- Direction ID：`subadditivity-family-design`
- 标题：`Subadditivity Family 设计与 Formulation 等价性诊断`
- 状态：`queued`
- 负责人：`shared`
- 创建日期：`2026-03-31`
- 来源会议：`research-tracker/meetings/2026-03-29_weekly-sync.md`

## 核心研究问题

`当前 solver 与论文 literal formulation 的差异是否真的重要，以及 subadditivity 相关约束家族怎样设计才更有利于 OOS 和理论解释。`

## 假设

- `Appendix C 的逐字复现不是当前偏差的主要根因`
- `subadditivity family 比 outside/envy family 更值得继续保留或扩展`
- `objective 接近但 price table 差异大，说明问题里存在多重近等价最优解或 replay/tie-breaking 敏感性`

## 为什么这个方向重要

- `它关系到复现实验该继续往“逐字对齐”还是往“机制性修正”投入`
- `这也是当前实验结果和理论写作之间最自然的连接点之一`

## 成功标准

- `明确哪些约束家族真正影响 OOS 与 runtime`
- `解释 literal solver 与 current solver 价格差异的来源`
- `把 subadditivity 结论转成理论或机制层面的可表达观点`

## 当前实验设计

- 自变量：`constraint family ablation / literal vs current formulation`
- 控制变量：`代表性实例、统一 OOS replay 口径`
- 评价指标：`objective delta, OOS delta, price-table distance, runtime`
- 参考脚本 / 路径：`experiments/mb_literal_appendix_c_check/`

## 最新结论

- 日期：`2026-03-31`
- 结论摘要：`现有证据表明，literal solver 与 current solver 的 objective 往往接近，但 price table 可以相差很大，因此 Appendix C 的字面复现不是当前核心问题。ablation 里只有 subadd_only 显示出正向 OOS 信号，说明 subadditivity family 比 outside/envy family 更值得继续系统研究。`

## 已完成实验记录

- `experiments/mb_literal_appendix_c_check/README.md`
- `experiments/mb_literal_appendix_c_check/RESULTS.md`
- `experiments/mb_literal_appendix_c_check/ablation/ABLATION_RESULTS.md`

## 当前判断

- `值得继续，但需要和 theory 线一起推进`

## 下一步决策点

- `细化 subadditivity family 的 ablation 口径`
- `解释 objective 接近但价格表差异大的机制`
- `将 subadditivity remark/counterexample 纳入下一次汇报材料`

## 相关产物路径

- 代码：`project-root/code_submission_project/code_submission/src/data/`
- 输出目录：`experiments/mb_literal_appendix_c_check/`
- 图表 / 报告：`experiments/mb_literal_appendix_c_check/ablation/`
