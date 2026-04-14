# revenue-management / file-ingest-log

## 2026-03-03 记录

- 目标文件：`Paper.zip`
- 现象：Telegram 聊天中显示收到 document，但 `~/.openclaw/media/inbound/` 未出现实体 `zip` 文件，导致无法直接解压。
- 判断：入站附件同步失败（与网络波动/大文件相关）。
- 可行替代：Windows -> Mac 使用 SCP 直传。
- 已验证命令：
  - `scp "D:\桌面\运筹优化\BP_Code\Paper.zip" sensen@home-macmini:~/.openclaw/workspace/revenue-management/papers/`
- 结论：当前阶段优先采用 SCP 处理大包；Telegram 继续用于小中型文件。
