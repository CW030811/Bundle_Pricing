# Codex Prompts For Research Tracking

下面这些提示词可以直接发给 Codex 使用。

## 1. 周会后整理

```text
请在 revenue-management/research-tracker/ 下帮我完成会后整理：
1. 新建今天的 meeting note
2. 把会议里新增的探索方向写入 directions/
3. 更新 CURRENT.md，明确本周主线、负责人、下次会前交付物
4. 如果某些旧方向状态变化了，也一起更新

会议内容如下：
[把会议纪要或聊天记录贴在这里]
```

## 2. 实验结束后登记

```text
请根据下面的实验信息，在 revenue-management/research-tracker/experiment-logs/ 新建一条实验记录，
并同步更新对应的 direction 文件与 CURRENT.md。

要求：
1. 不要照抄原始终端日志，要提炼出关键信息
2. 必须写清楚脚本/命令、路径、结果产物路径、结论、下一步建议
3. 如果结果不足以支持当前方向，请明确写出“建议暂停/收缩”

实验信息如下：
[把你的实验过程、结果、路径、观察贴在这里]
```

## 3. 周报生成

```text
请读取 revenue-management/research-tracker/ 下本周相关记录，
生成本周周报到 weekly-reports/YYYY-Www.md。

汇总范围：
1. 本周 meetings/
2. 本周 experiment-logs/
3. 本周更新过的 directions/
4. CURRENT.md

输出要求：
1. 按“本周核心进展 / 关键实验结果 / 未解决问题 / 下周计划”组织
2. 不写空话，只保留真正能汇报的内容
3. 对每个结论附上来源记录路径
```

## 4. 防止迷失方向

```text
请读取 revenue-management/research-tracker/CURRENT.md、
directions/ 和最近一周的 experiment-logs/，
帮我判断：
1. 现在最应该优先推进的 3 个动作是什么
2. 哪些方向其实已经证据不足，应该暂停
3. 下一个最有信息增益的实验是什么
4. 如果我这周只能汇报 3 点，最值得讲什么
```

## 5. 周报后更新

```text
请根据这次组会/导师反馈，更新 revenue-management/research-tracker/：
1. 更新对应 meeting note
2. 更新相关 directions 的状态和下一步决策点
3. 更新 CURRENT.md
4. 如有必要，修订下周计划

反馈内容如下：
[把导师反馈贴在这里]
```
