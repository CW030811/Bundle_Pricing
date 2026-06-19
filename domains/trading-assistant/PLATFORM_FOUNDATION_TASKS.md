# trading-assistant / PLATFORM FOUNDATION TASKS

## 采纳评估

两份参考文档的核心建议值得作为本域长期方向接近 100% 采纳，但执行范围按当前 Crypto/OKX-first 平台裁剪：

- 必须采纳：假设驱动研究、Strategy Card、可复现数据链路、ODS/DWD/DWS/ADS、数据质量、交易成本、样本外、参数稳定性、市场状态分解、paper/small-live 晋级门槛。
- 暂不采纳为当前主线：股票专用表、A 股/Tushare 字段、非 OKX 数据源的完整实现、新闻舆情和宏观数据中台。
- 当前目标：先把“正式高效做策略研究”的底座补齐，再扩大数据源和策略复杂度。

## P0：研究前必须完成

1. Strategy Registry 同步 [done]
- 从 `knowledge/bitcoin_strategy_knowledge_base.yaml` 同步到 SQLite `strategy_registry`。
- `research knowledge-base --sync-registry` 可显式执行。
- `research knowledge-base --write-report` 默认也应同步。

2. 标准回测基准 [done]
- 每个单标的回测报告必须包含 cash、buy-and-hold、简单均线趋势、固定随机入场基准。
- 策略评估不得只看自身收益曲线。

3. DWS 因子物化 [done-v1]
- 因子评估除 JSON report 外，应把因子值写入可查询 DWS 表。
- 至少支持统一长表：factor_id、version、exchange、symbol、market_type、interval、timestamp、factor_value、parameters。

4. 数据质量门禁 [done-v1]
- backtest/research/paper 默认检查 DWD 数据质量摘要。
- 严重质量问题应进入报告并可选择阻断研究。

5. Strategy Card 门禁 [done-v1]
- 新策略进入 `research sweep` 或 portfolio research 前，必须有知识库条目或显式 `--allow-unregistered-strategy`。
- 策略条目必须包含假设、数据、信号、进出场、仓位、风控、适用市场、失效条件。

## P1：提升研究可靠性

6. 参数稳定性报告 [done-v1]
- 网格搜索输出不只给最优点，还要给相邻参数稳定性、收益/回撤热力数据、脆弱参数提示。

7. Walk-forward 标准化 [done-v1]
- 所有候选策略统一 train/validation/test 或 rolling walk-forward 报告格式。
- 报告必须包含每折 OOS、正收益折数、最差 OOS 回撤、参数漂移。

8. 成本敏感性标准化 [done-v1]
- 所有候选策略统一手续费、滑点、延迟执行、资金费率压力场景。
- 成本稍变即失效的策略标记为 `research_only`。

9. 市场状态分解升级 [done-v1]
- bull、bear、sideways、high volatility、low volatility、crash、rebound、liquidity poor 至少形成统一标签。
- 回测、因子、策略短名单都引用同一套 regime 标签。

10. 反过拟合工具 [done-v1]
- 增加多重测试/参数搜索惩罚提示。
- 后续实现 PBO、Deflated Sharpe、purged/embargo CV。

## P2：数据中台扩展

11. 扩展 ODS/DWD 数据类型 [done-v1]
- OKX instruments/exchange rules、open interest、basis、long-short ratio、orderbook snapshot、trades、liquidations 均已进入 ODS/DWD。
- V1 覆盖 snapshot/recent/public 数据采集；深历史分页、跨交易所 basis 和更完整成交/清算回放仍可继续升级。

12. DWD SQL 化 [done-v1]
- 当前 Parquet/CSV DWD 保留，但为核心 OHLCV/funding 增加可查询 SQLite/DuckDB 标准表或视图。

13. ADS 全覆盖 [done-v1]
- paper/live 信号、目标仓位、风险状态、服务运行摘要都写入 ADS。
- JSON report 继续保留作为人读/机器读快照。

14. 数据版本与重放 [done-v1]
- 每次 backfill、清洗、因子计算、回测都记录 data_version、factor_version、code/config fingerprint。

15. 采集重试与任务状态 [done-v1]
- 采集任务支持失败重试、增量水位、失败队列、可恢复任务日志。

## P3：进入高效研究平台

16. 研究命令模板化 [done-v1]
- 新策略从 Strategy Card 生成 factor/research/backtest skeleton。

17. 统一晋级评分 [done-v1]
- `research promotion-scorecard` 统一输出 idea -> factor -> strategy -> paper -> small live 阶段、评分拆解、研究阻断项、运营阻断项和人工启用要求，并写入 ADS strategy score。

18. 报告索引与查询 [done-v1]
- CLI 可按 strategy/factor/date/status 查询历史报告、ADS 结果和质量问题。

19. 更大 universe 与多周期 [done-v1]
- `research multi-timeframe-sweep` 可对同一策略池、多标的和多个 bar 统一回测并输出跨周期聚合报告；标的池可复用 OKX universe discovery。后续仍可把流动性过滤升级为所有研究命令的硬门禁。

20. 外部通知与复盘闭环 [done-v1]
- `review queue` 汇总质量问题、服务异常、pre-live 阻断、通知演练、策略降级和晋级候选，写入 `review_tasks` 与 `review_queue_latest.json`；可选 `--notify` 复用现有 webhook/本地通知日志。
