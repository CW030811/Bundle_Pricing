# trading-assistant / TASKS

## 已实施

- Python 项目骨架与 CLI 入口
- OKX API v5 REST 签名、Demo Trading header、公共行情、账户和下单接口
- WebSocket 订阅消息构造
- YAML + Pydantic 配置校验
- K 线标准化、本地存储、SQLite 审计
- 趋势 + 均值回归策略
- EMA、ATR、RSI、布林带、波动率和成交量指标
- 保守风控门控
- PaperBroker
- gated OkxBroker
- 事件驱动回测和 JSON 报表
- CLI：data、backtest、paper、live、report、risk、kill
- 单元/集成测试
- OKX USDT 现货 universe 自动发现与本地输出
- 跨币种动量 `xsmom-grid` 参数网格回测
- 可恢复状态的跨币种动量组合纸交易
- `service run-paper-portfolio` 长期无人值守纸交易入口
- 回测性能优化：指标预计算，批量 sweep 可在合理时间完成
- 跨币种动量 walk-forward / OOS 验证报告
- 组合纸交易白名单/黑名单、换手预算、组合回撤熔断
- 跨币种动量手续费/滑点成本敏感性报告
- `service health` 无人值守健康检查
- 行情过期保护、调仓冷却和本地 JSONL 事件通知日志
- `service watchdog` 独立监督进程：健康失败时触发 kill switch 并请求服务停止
- OKX `cancel-all-after` 交易所级 dead man's switch 接口与 CLI
- `service start-paper-portfolio` 后台启动组合纸交易服务，并默认启动 watchdog
- 组合服务每轮交易前自动刷新 OKX 最新 K 线，长期运行不依赖过期本地数据
- 通用 webhook 通知层：默认本地 JSONL，配置 URL 后可接 Telegram/飞书/企业微信/自建告警
- `live run` 受控 Production 组合交易单轮入口：复用组合策略、风控、OKX broker、订单精度和本地审计
- `service run-live-portfolio` / `service start-live-portfolio` 受控 Production 组合交易长期运行入口，具备 heartbeat、PID 锁、stop、连续错误熔断和 watchdog
- `service recover-paper` 安全恢复最近一次 paper portfolio 后台服务：只接受 paper 启动记录，kill switch 或 live 命令会阻断
- watchdog paper-only 自动恢复选项：`--recover-paper` / `--watchdog-recover-paper` 只在 paper 服务未运行时恢复，其他故障仍升级到 kill switch/停机
- `service acceptance` 无人值守验收演练：隔离状态目录运行纸交易多轮、健康检查、watchdog 正常路径和 live 门控负测
- `service live-gate-drill` 实盘前门控演练：验证 live 配置、确认参数、凭证、kill switch 与 reduce-only 行为
- `service notification-drill` 通知链路演练：验证本地通知审计日志；配置 webhook 后验证外部告警发送
- `service pre-live-check` 实盘前聚合预检：默认刷新稳定性报告，并统一检查服务健康、watchdog、24h 稳定性、live gate、通知、Production 配置、凭证、operator 风控上限、kill switch 和策略短名单
- `service snapshot` 运行审计快照：记录当前配置、服务状态、watchdog、health、最近关键报告和凭证存在性，不落 API 密钥明文
- `service report` 服务观察报告：输出 `reports/service_observation_latest.json`
- `service stability` 长期稳定性聚合报告：统计启动以来运行时长、paper/watchdog 迭代、订单、失败事件和权益范围
- watchdog 启动时自动按交易循环间隔设置心跳过期阈值，避免小时级策略被默认 300 秒误杀
- 长期循环改为可中断 sleep，stop 文件或 SIGTERM 不再被 1h 交易间隔阻塞
- `adaptive_trend` 研究策略：滚动 Sharpe 选币 + EMA 趋势过滤 + 波动率目标仓位
- `adaptive_trend` 参数网格、walk-forward/OOS 和手续费/滑点成本敏感性报告
- OKX funding rate history 数据抓取与本地 funding 存储
- `funding_carry` delta-neutral 资金费率 carry 研究策略、参数网格、walk-forward 和成本敏感性报告
- `research shortlist` 策略短名单报告：汇总 OOS、成本敏感性、服务稳定性和 live_ready 状态
- 已收盘 K 线防线：paper/live/demo 信号和组合选币默认过滤 OKX 未确认 K 线
- 回测执行模型加严：单标的回测使用当前收盘 bar 生成信号、下一根 bar open 成交，并保留手续费/滑点
- 行情刷新容错：paper/live 组合服务按标的记录刷新错误，避免单个网络异常直接中断整轮交易； stale guard 继续负责阻断过期行情交易
- 服务启动竞态修复：start 命令写入 bootstrap heartbeat，清理旧 stop/heartbeat；paper start 清理 paper kill switch，避免 watchdog 误读旧心跳后误杀
- 默认路径隔离：自定义 `state_dir/log_dir` 时，默认 pid、heartbeat、kill switch 和日志路径跟随目录，避免测试/验收串到主运行状态
- BTC 策略知识库 v1：`knowledge/bitcoin_strategy_knowledge_base.yaml` 收录 12 个可复现候选/已实现策略，覆盖逻辑、数据、信号、进出场、仓位、风控、市场状态、失效条件、复现难度和建议
- `research knowledge-base` 覆盖度报告：统计策略总数、已实现数、已回测数、报告覆盖、缺实现/缺回测队列
- 新增 BTC 单标的策略：`btc_volatility_breakout` 和 `btc_realized_volatility_targeting`，已纳入 `research sweep` 默认候选和知识库状态
- 回测指标增强：单标的 backtest/sweep 报告现在包含 `annualized_return`、`profit_loss_ratio` 和 `regime_performance`
- `btc_eth_cointegration_pairs` 研究策略：BTC/ETH 滚动 hedge ratio + spread z-score，相对价值信号使用已确认 K 线，并按下一根 open 执行；已输出研究回测报告
- `research factor-evaluate` Crypto 因子研究统一管线：借鉴 Qlib 分层但不引入 qlib 依赖，支持 Python 因子 builder、forward return、IC/RankIC/ICIR、分位收益、多空收益、top 分位换手、覆盖率和缺失率报告
- 结构标准化：新增 `ARCHITECTURE.md`，将历史 `subprojects/` 归档到 `archive/subprojects/`，并在知识库中标注 strategy/factor/promotion pipeline 状态
- 旧策略因子迁移：`cross_sectional_momentum_720h`、`adaptive_trend_quality`、`altcoin_btc_residual_reversion`、`funding_carry_recent`、`btc_time_series_momentum_336h`、`volatility_adjusted_btc_trend` 已接入 `research factor-evaluate`
- DataHub v1：SQLite 新增 ODS、采集日志、质量问题、因子注册/计算日志和 ADS 回测/策略评分表；OHLCV/funding backfill 自动写 ODS 与 ingestion log
- `data schema` / `data quality`：可检查 DataHub schema 和本地 OHLCV 质量；质量问题可写入 `data_quality_issues`
- 回测、因子评估和策略短名单报告同步写入 ADS/registry 表，保留原 JSON report 流程

## 下一步

1. 把组合纸交易 + watchdog 跑 24h+ 真实时间稳定性观察，检查 heartbeat、日志、SQLite 状态和重复调仓行为。
2. 将 `QUANT_NOTIFICATION_WEBHOOK_URL` 指向实际 Telegram/飞书/企业微信 webhook，并把 `service notification-drill` 从 `local_only` 跑到 `passed`。
3. 扩展更干净的实盘白名单：剔除稳定币、交易所币、meme/主题币，单独保留研究池。
4. 对后台 live 服务做只读/无凭证/未确认/风控拦截演练，并在纸交易稳定后小额手动验收。
5. 对 `funding_carry` 增加更长历史、跨交易所 funding、执行可行性、保证金占用和资金费率突变风控。
6. 基于已迁移因子的 factor reports，筛选哪些因子值得升级为标准 strategy research 模板。
7. 继续复现 BTC 相对价值缺口策略，并对 `btc_eth_cointegration_pairs` 增加 walk-forward 与 cointegration 稳定性门控。
8. 扩展 DataHub 数据源到 open interest、basis、orderbook snapshot、trades、liquidations 和交易规则/手续费表。
9. 增加更长历史、多周期和更大 universe 测试。
10. 在纸交易和 Demo Trading 稳定后，再评估小额 Production 实盘开关。

## 待你提供

- 若要进入 Production：确认 Production API 权限包含 read + trade，且不包含 withdraw。
- 若绑定 IP 白名单：确认本机/服务器出口 IP。
- 首次实盘白名单与是否排除 meme/平台币。

## 已收到的用户偏好

- Demo Trading：是
- 子账户：是
- 首次实盘资金上限：`50 USDT`
- 永续：允许
- 杠杆范围：`1-3x`，当前安全默认 `1x`
- 保证金模式：全仓

## 当前诊断结果

- OKX 公共接口：已通过本机代理连通。
- OKX 历史 K 线 backfill：已能写入 `data/candles/spot/BTC-USDT/1H.csv`。
- 当前 API key：Production 私有接口只读可用。
- 当前 Demo Trading key：私有接口可用。
- 当前系统：Demo 模式只读取 `OKX_DEMO_*`，Production 模式只读取 `OKX_API_*`，避免环境串用。
- 当前系统：Demo 测试下单按 `minSz`、`lotSz`、`tickSz` 处理数量和价格精度。
- 当前系统：Demo Trading 测试下单与撤单已跑通。
- 当前系统：`quant okx readiness` 会生成 `reports/okx_readiness_latest.json`。
- 当前系统：`quant okx order-dry-run` 可在没有 Demo 私钥时先验证测试单数量/价格精度。
- 当前系统：`quant okx demo-run-once` 可执行一次真实 Demo 策略循环；默认只计划，传 `--confirm-demo-order` 后才发 Demo 单。
- 当前系统：`quant okx demo-loop` 可按固定间隔持续执行 Demo 策略循环，并保存最近循环状态。
- 当前系统：`quant service run-demo` 是无人值守入口，具备 PID 锁、heartbeat、日志轮转、stop、信号处理和连续错误熔断。
- 当前系统：`quant service run-paper-portfolio` 是跨币种动量组合纸交易无人值守入口，具备可恢复组合状态。
- 当前系统：`quant service start-paper-portfolio` 可后台启动组合纸交易服务，并写入 launch 状态文件。
- 当前系统：组合纸交易服务支持 `--refresh-candles`，默认配置也会在每轮迭代前拉取最新 OKX K 线。
- 当前系统：`quant service health` 可检查心跳过期、最近错误、熔断状态、组合权益/回撤/持仓。
- 当前系统：`quant service report` 可写入当前观察报告到 `reports/service_observation_latest.json`。
- 当前系统：`quant service stability` 可写入当前稳定性聚合报告到 `reports/service_stability_latest.json`。
- 当前系统：`quant service watchdog` 可独立监督交易服务，服务死亡、心跳过期或健康失败时会触发 kill switch 并请求停止服务。
- 当前系统：`quant service acceptance` 已通过本地验收，最新报告为 `reports/unattended_acceptance_latest.json`；验收使用 `state/acceptance` 和 `logs/acceptance`，不污染正式纸交易状态。
- 当前系统：`quant service live-gate-drill` 已通过，最新报告为 `reports/live_gate_drill_latest.json`；演练日志隔离在 `logs/live_gate_drill/`，不会污染主服务稳定性统计；Production live 仍未开启。
- 当前系统：`quant service notification-drill` 可验证通知链路；未配置 webhook 时状态为 `local_only`，配置外部 webhook 并发送成功后才算实盘前通知门槛通过。
- 当前系统：`quant service pre-live-check` 可执行实盘前总闸预检；任何缺失项都会返回非 0 并写入 `reports/pre_live_check_latest.json`。
- 当前 24h 纸交易观察：因补齐 confirmed-only、next-bar、刷新容错和启动竞态修复，已于 `2026-05-27T09:49:11Z` 重新启动观察窗口，paper service PID `35594`，watchdog PID `35595`，10 个 OKX USDT 现货标的，`lookback=720`、`top_n=2`、每小时循环，watchdog 心跳阈值 `5520s`。最新 `service stability` 显示 healthy=true、service/watchdog running=true、failure_event_count=0、paper_run_count=1。
- 当前系统：`quant okx cancel-all-after` 可设置 OKX 交易所级倒计时撤单，`service.okx_cancel_all_after_seconds` 可让 Demo 服务每轮刷新。
- 当前系统：组合纸交易支持白名单/黑名单、换手预算和组合高水位回撤熔断。
- 当前系统：组合纸交易支持 stale candle guard、rebalance cooldown、本地 JSONL 事件日志。
- 当前系统：kill switch、watchdog 失败、过期行情和实际下单事件会写本地通知日志；配置 webhook 后会外发通知。
- 当前研究结果：10 个 OKX USDT 现货标的里，跨币种动量显著强于单标的趋势/均值回归候选。
- 当前 OOS 结果：4 折 walk-forward，3 折正收益，累计 OOS 约 `36.9%`，最差 OOS 回撤约 `-14.0%`；仍需更长历史和 24h+ 纸交易验证。
- 当前成本敏感性结果：9 组手续费/滑点场景全部为正，最差收益约 `43.8%`，最差回撤约 `-8.0%`。
- 当前 adaptive trend 网格最优：收益约 `10.2%`，最大回撤约 `-1.0%`，Sharpe 约 `9.33`。
- 当前 adaptive trend OOS：4 折 walk-forward，4 折正收益，累计 OOS 约 `9.6%`，最差 OOS 回撤约 `-1.6%`。
- 当前 adaptive trend 成本敏感性：9 组手续费/滑点场景全部为正，最差收益约 `9.0%`，最差回撤约 `-1.0%`。
- 当前 funding carry 样本内网格最优：8 个 OKX USDT 永续标的，`lookback_periods=9`、`hold_periods=3`、`top_n=1`、`min_funding_rate=0.0001`、`max_notional_pct=0.5`，收益约 `108.6%`，最大回撤约 `-4.1%`，Sharpe 约 `7.73`。
- 当前 funding carry OOS：5 折 walk-forward，1 折正收益，累计 OOS 约 `10.4%`，平均 OOS Sharpe 为负，最差 OOS 回撤约 `-3.4%`；结论是不够稳健，不能列为当前优质主策略。
- 当前 funding carry 成本敏感性：9 组手续费/滑点场景全部为正，最差收益约 `37.1%`，最差回撤约 `-14.1%`；成本鲁棒性尚可，但 OOS 稳健性不足。
- 当前策略短名单：`cross_sectional_momentum` 为主纸交易策略，`adaptive_trend` 为低回撤备选，`funding_carry` 暂列 research_only；`live_ready=false`，阻断项为 24h+ 纸交易稳定性未完成、通知 webhook 未配置、Production live 配置仍需人工显式启用。
- 当前系统：DataHub 已覆盖 OKX exchange-info、open interest、basis、long-short ratio、orderbook snapshot、trades 和 liquidations，新增数据统一写入 `ods_crypto_market_data_raw` 和对应 DWD 表。
- 当前系统：`quant research promotion-scorecard` 输出统一晋级评分和 idea/factor/strategy/paper/small live 阶段；`quant research multi-timeframe-sweep` 支持同一策略池在多个 bar 上做标准 sweep 聚合。
- 当前系统：`quant review queue` 汇总质量问题、服务异常、pre-live 阻断、通知演练、策略降级和晋级候选，写入 `review_tasks` 与 `reports/review_queue_latest.json`，可选 `--notify` 外发/本地记录复盘摘要。
- 当前 BTC 策略知识库覆盖：共 `13` 个策略条目，已实现/回测 `10` 个；仍缺 `btc_grid_trading`、`altcoin_btc_arbitrage_factor_reversion`、`btc_orderbook_market_making`。最新报告为 `reports/strategy_knowledge_base_latest.json`。
