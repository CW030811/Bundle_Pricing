# Research Tracker

这个目录用于管理 Revenue Management Bundle Pricing 相关科研工作的周会、研究方向、实验记录与周报输出。

目标不是替代 `experiments/` 下的原始结果目录，而是提供一个更稳定的“研究线程管理层”：

- `experiments/` 保留原始运行产物、脚本输出、图表、日志
- `research-tracker/` 负责记录为什么做、做了什么、结果如何、下一步是什么

## 目录结构

- `CURRENT.md`
  - 当前周状态总览
  - 你现在正在推进哪些方向
  - 哪些方向卡住了
  - 下次开会前最重要的输出是什么
- `meetings/`
  - 每次周会后的纪要与新增待探索方向
- `directions/`
  - 每个研究方向一份长期追踪文档
  - 用来防止做着做着失去主线
- `experiment-logs/`
  - 每次完成一个实验探索后记录过程、结论、产物路径
- `weekly-reports/`
  - 每周正式汇报材料
- `codex-prompts.md`
  - 直接可复制给 Codex 的提示词

## 推荐命名

- 周会记录：`meetings/YYYY-MM-DD_weekly-sync.md`
- 方向文档：`directions/<direction-slug>.md`
- 实验记录：`experiment-logs/YYYY-MM-DD_<direction-slug>_<short-tag>.md`
- 周报：`weekly-reports/YYYY-Www.md`

示例：

- `meetings/2026-03-30_weekly-sync.md`
- `directions/mb-generalization-gap.md`
- `experiment-logs/2026-03-31_mb-generalization-gap_validation-split-check.md`
- `weekly-reports/2026-W14.md`

## 最小工作流

### 1. 每次开会后

做两件事：

- 新建一份会议纪要
- 如果会议提出了新方向，为每个方向新建或更新 `directions/` 中的对应文件

同时更新 `CURRENT.md`：

- 本周重点方向
- 每个方向负责人
- 下次开会前必须交付的结果

### 2. 每次完成一个方向下的实验探索后

新建一份 `experiment-logs/` 记录，至少写清楚：

- 目标问题是什么
- 这次改了什么
- 哪些设置保持不变
- 实际运行是否成功
- 关键结果是什么
- 结果文件在哪
- 你的判断是什么
- 这个方向下一步应该继续、暂停还是收缩

然后同步更新对应的 `directions/<direction-slug>.md`：

- 补上最新结论
- 附上这次实验记录链接
- 更新下一步决策点

### 3. 每周汇报前

不要从零开始写周报。正确做法是让 Codex 根据：

- 本周 `meetings/`
- 本周 `experiment-logs/`
- 各 `directions/` 的最新状态
- `CURRENT.md`

自动汇总出 `weekly-reports/YYYY-Www.md`。

## 使用原则

- 一个研究问题一个 `direction` 文件，避免把不同问题混在一份周报里
- 一个重要实验一份 `experiment-log`，不要只把结果留在终端或脑子里
- 记录结论优先，不要粘贴大量原始日志
- 必须写明结果产物路径，保证之后能回查
- 每次实验记录最后都要写“下一步建议”，避免下周重新理解上下文

## 你和 Codex 的分工建议

- 你负责：提供实验意图、真实观察、判断标准
- Codex 负责：整理结构、生成记录、提炼结论、汇总周报、追踪未关闭事项

## 建议的固定节奏

- 周会后 10 分钟内：补 `meetings/` 和 `directions/`
- 每次实验结束后 10 分钟内：补 `experiment-logs/`
- 每周汇报前：用 Codex 自动生成 `weekly-reports/`
- 周报结束后：把导师或组员反馈回写到 `meetings/` 与 `CURRENT.md`

## 你迷失方向时怎么用

直接让 Codex 读取：

- `research-tracker/CURRENT.md`
- `research-tracker/directions/`
- 最近一周的 `research-tracker/experiment-logs/`

然后让它回答：

- 当前最应该推进的 1 到 3 个方向是什么
- 哪些方向已经证据不足，应该暂停
- 哪个实验最有信息增益
- 下次开会最值得汇报的内容是什么
