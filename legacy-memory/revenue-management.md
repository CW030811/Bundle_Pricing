# revenue management 科研群技能调用手册

更新时间：2026-02-27

## 目标

用于提升科研生产力：
- 找文献更快
- 读论文更深
- 写论文更稳
- 复盘归档更清晰

## 推荐技能清单（按场景）

### 1) 文献发现与追踪
- `arxiv-watcher`：按关键词/方向持续跟踪 arXiv 新论文
- `paper-recommendation`：根据主题推荐相关论文
- `daily-paper-digest`：自动生成每日论文摘要
- `scholar` / `google-scholar-search-skill`：补充 Scholar 检索

### 2) 论文精读与信息抽取
- `paper-parse`：解析论文结构、方法、实验与结论
- `agentic-paper-digest-skill`：生成结构化精读摘要
- `arxiv-paper-reviews`：偏“review 风格”的论文评价与对比

### 3) 写作与润色
- `research-paper-writer`：从大纲到初稿生成
- `academic-writing`：学术写作表达优化、逻辑改写

### 4) 参考文献与知识库
- `zotero-paper`：连接 Zotero 文献库
- `zotero-scholar`：学术搜索与 Zotero 工作流联动
- `feishu-doc`（已安装）：把摘要/周报沉淀到飞书文档
- `feishu-drive`（已安装）：资料归档与共享

## 推荐工作流（群内可直接触发）

1. **每周追踪**：`arxiv-watcher` + `daily-paper-digest`
2. **选题前调研**：`paper-recommendation` + `paper-parse`
3. **写作阶段**：`research-paper-writer` + `academic-writing`
4. **投稿前检查**：`arxiv-paper-reviews`（对比同类方法）
5. **沉淀归档**：`zotero-paper` + `feishu-doc`

## 群内触发示例

- “帮我追踪本周 revenue management + assortment optimization 的新论文，并做 10 条摘要。”
- “把这篇论文做成结构化精读：问题定义、方法、创新点、可复现性、可改进点。”
- “把这个实验结果写成论文里的 Results 小节，英文，学术风格。”
- “把今天讨论结论同步到飞书文档，并附 3 条下周行动项。”

## 注意事项

- `--force` 安装的技能需谨慎：先用于只读任务，再逐步开放写入/外部操作。
- 写作生成内容务必人工校对，尤其是引用、公式、实验设置与结论强度。
