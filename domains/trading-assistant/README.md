# trading-assistant

通用量化研究与交易平台，当前已实现主线是 Crypto/OKX。系统覆盖数据抓取、因子研究、策略生成、回测、纸交易、风控、受控 live broker、日志审计和本地报表；股票、多资产和自动因子挖掘保留为后续扩展方向。

## 当前定位

- 当前已实现交易范围：OKX 现货 + USDT 永续
- 平台定位：通用量化平台，Crypto/OKX-first implementation
- 默认标的：`BTC/USDT`、`ETH/USDT`
- 研究标的池：可用 OKX 24h 成交额自动发现 USDT 现货 universe
- 默认执行：纸交易优先，实盘默认关闭
- 策略 v1：趋势 + 均值回归
- 风控默认：保守
- 首次实盘资金上限：`50 USDT`
- 永续杠杆：先按 `1x` 执行，`3x` 只作为后续上限候选
- 保证金模式：永续使用全仓参数
- 代理：可通过 `.env` 的 `OKX_PROXY_URL` 让 CLI 走本机代理
- 运行形态：本地 CLI + 本地文件/SQLite
- 架构索引：见 `ARCHITECTURE.md`

## 快速命令

```bash
PYTHONPATH=src python3 -m quant_system.cli data backfill --symbol BTC/USDT --instrument-type spot --limit 300
PYTHONPATH=src python3 -m quant_system.cli data history --symbol BTC/USDT --symbol ETH/USDT --instrument-type spot --pages 20
PYTHONPATH=src python3 -m quant_system.cli data universe --instrument-type spot --top-n 12 --write
PYTHONPATH=src python3 -m quant_system.cli backtest --use-synthetic --symbol BTC/USDT
PYTHONPATH=src python3 -m quant_system.cli paper run --symbol BTC/USDT --instrument-type spot
PYTHONPATH=src python3 -m quant_system.cli paper portfolio-run-once --symbol BTC/USDT --symbol ETH/USDT --lookback-bars 720 --top-n 2
PYTHONPATH=src python3 -m quant_system.cli okx diagnose
PYTHONPATH=src python3 -m quant_system.cli okx readiness
PYTHONPATH=src python3 -m quant_system.cli okx order-dry-run --symbol BTC/USDT --instrument-type spot
PYTHONPATH=src python3 -m quant_system.cli okx demo-smoke
PYTHONPATH=src python3 -m quant_system.cli okx demo-run-once --symbol BTC/USDT --instrument-type spot
PYTHONPATH=src python3 -m quant_system.cli okx demo-run-once --symbol BTC/USDT --instrument-type spot --confirm-demo-order
PYTHONPATH=src python3 -m quant_system.cli okx demo-loop --symbol BTC/USDT --instrument-type spot --max-iterations 10 --interval-seconds 60
PYTHONPATH=src python3 -m quant_system.cli service run-demo --symbol BTC/USDT --instrument-type spot --interval-seconds 60
PYTHONPATH=src python3 -m quant_system.cli service run-paper-portfolio --symbol BTC/USDT --symbol ETH/USDT --lookback-bars 720 --top-n 2 --interval-seconds 3600 --refresh-candles
PYTHONPATH=src python3 -m quant_system.cli service start-paper-portfolio --symbol BTC/USDT --symbol ETH/USDT --lookback-bars 720 --top-n 2 --interval-seconds 3600 --refresh-candles
PYTHONPATH=src python3 -m quant_system.cli service status
PYTHONPATH=src python3 -m quant_system.cli service health --max-heartbeat-age-seconds 3600
PYTHONPATH=src python3 -m quant_system.cli service report --max-heartbeat-age-seconds 5520 --require-running
PYTHONPATH=src python3 -m quant_system.cli service stability --max-heartbeat-age-seconds 5520 --require-running
PYTHONPATH=src python3 -m quant_system.cli service acceptance --symbol BTC/USDT --symbol ETH/USDT --iterations 3 --lookback-bars 24 --top-n 1 --max-heartbeat-age-seconds 3600
PYTHONPATH=src python3 -m quant_system.cli service stop
PYTHONPATH=src python3 -m quant_system.cli --config config/live.example.yaml live run --symbol BTC/USDT --symbol ETH/USDT --instrument-type spot --lookback-bars 720 --top-n 2 --confirm-live
PYTHONPATH=src python3 -m quant_system.cli --config config/live.example.yaml service run-live-portfolio --symbol BTC/USDT --symbol ETH/USDT --instrument-type spot --lookback-bars 720 --top-n 2 --confirm-live
PYTHONPATH=src python3 -m quant_system.cli research sweep --symbol BTC/USDT --symbol ETH/USDT --instrument-type spot --write-report
PYTHONPATH=src python3 -m quant_system.cli research xsmom --symbol BTC/USDT --symbol ETH/USDT --instrument-type spot --write-report
PYTHONPATH=src python3 -m quant_system.cli research xsmom-grid --symbol BTC/USDT --symbol ETH/USDT --instrument-type spot --write-report
PYTHONPATH=src python3 -m quant_system.cli research adaptive-trend --symbol BTC/USDT --symbol ETH/USDT --instrument-type spot --write-report
PYTHONPATH=src python3 -m quant_system.cli data funding --symbol BTC/USDT --symbol ETH/USDT --pages 10 --page-limit 100
PYTHONPATH=src python3 -m quant_system.cli data exchange-info --instrument-type spot --instrument-type swap
PYTHONPATH=src python3 -m quant_system.cli data open-interest --symbol BTC/USDT --symbol ETH/USDT
PYTHONPATH=src python3 -m quant_system.cli data basis --symbol BTC/USDT --symbol ETH/USDT
PYTHONPATH=src python3 -m quant_system.cli data long-short-ratio --symbol BTC/USDT --period 5m --limit 100
PYTHONPATH=src python3 -m quant_system.cli data orderbook --symbol BTC/USDT --instrument-type swap --depth 50
PYTHONPATH=src python3 -m quant_system.cli data trades --symbol BTC/USDT --instrument-type swap --limit 100
PYTHONPATH=src python3 -m quant_system.cli data liquidations --symbol BTC/USDT --limit 100
PYTHONPATH=src python3 -m quant_system.cli data schema
PYTHONPATH=src python3 -m quant_system.cli data quality --symbol BTC/USDT --instrument-type spot --write-report
PYTHONPATH=src python3 -m quant_system.cli research funding-carry --symbol BTC/USDT --symbol ETH/USDT --lookback-periods 3 --hold-periods 3 --top-n 2 --min-funding-rate 0.0001 --max-notional-pct 0.5 --write-report
PYTHONPATH=src python3 -m quant_system.cli research funding-carry-grid --symbol BTC/USDT --symbol ETH/USDT --write-report
PYTHONPATH=src python3 -m quant_system.cli research funding-carry-walk-forward --symbol BTC/USDT --symbol ETH/USDT --write-report
PYTHONPATH=src python3 -m quant_system.cli research funding-carry-costs --symbol BTC/USDT --symbol ETH/USDT --write-report
PYTHONPATH=src python3 -m quant_system.cli research btc-eth-cointegration --symbol BTC/USDT --symbol ETH/USDT --instrument-type spot --write-report
PYTHONPATH=src python3 -m quant_system.cli research factor-evaluate --factor crypto_momentum_24h --symbol BTC/USDT --symbol ETH/USDT --symbol SOL/USDT --instrument-type spot --horizon-bars 1 --horizon-bars 6 --horizon-bars 24 --write-report
PYTHONPATH=src python3 -m quant_system.cli research alpha-ensemble --spec config/alpha_ensemble.example.yaml --write-report
PYTHONPATH=src python3 -m quant_system.cli research shortlist --write-report
PYTHONPATH=src python3 -m quant_system.cli research promotion-scorecard --write-report
PYTHONPATH=src python3 -m quant_system.cli research multi-timeframe-sweep --symbol BTC/USDT --symbol ETH/USDT --bar 1H --bar 4H --strategy trend_mr --write-report
PYTHONPATH=src python3 -m quant_system.cli research knowledge-base --write-report
PYTHONPATH=src python3 -m quant_system.cli review queue --write-report
PYTHONPATH=src python3 -m quant_system.cli report latest --name strategy_sweep
PYTHONPATH=src python3 -m quant_system.cli report latest --name cross_sectional_momentum
PYTHONPATH=src python3 -m quant_system.cli risk status
PYTHONPATH=src python3 -m quant_system.cli kill
```

安装为命令后也可以使用：

```bash
quant data backfill
quant backtest --strategy trend_mr --from 2024-01-01 --to 2024-03-01
quant paper run
quant --config config/live.example.yaml live run --confirm-live
quant report latest
```

## DataHub 数据底座

系统当前使用本地轻量 DataHub：OKX 原始 OHLCV/funding/exchange-info/衍生品与微观结构数据返回写入 SQLite ODS 表，标准化行情继续写入 `data/candles/**`、`data/funding/**` 和 DWD 表。DWD 已覆盖 exchange-info、open interest、basis、long-short ratio、orderbook snapshot、trades、liquidations；采集日志写入 `data_ingestion_logs`，质量问题写入 `data_quality_issues`。因子报告会登记 `factor_registry` / `factor_calculation_logs` 并物化到 `dws_crypto_factor_values`，回测报告会索引到 ADS backtest 表，策略短名单和晋级评分会写入 ADS strategy score 表，复盘事项会进入 `review_tasks`。

查看 schema：

```bash
PYTHONPATH=src python3 -m quant_system.cli data schema
```

检查本地 OHLCV 质量：

```bash
PYTHONPATH=src python3 -m quant_system.cli data quality --symbol BTC/USDT --instrument-type spot --bar 1H --persist --write-report
```

长期原则：策略和回测读取 DWD/DWS/ADS，不直接依赖 ODS 原始 API 结构；ODS 用于审计、重放和排查数据源漂移。

## 安全边界

真实下单必须同时满足：

1. `mode: live`
2. `execution.live_enabled: true`
3. 命令显式传入 `--confirm-live`
4. 环境变量中存在 OKX API key、secret、passphrase
5. 订单通过风控门控

默认配置不会真实下单。`paper` 模式只走 `PaperBroker`。

行情信号默认只使用已收盘 K 线。OKX 拉回来的最新未确认 K 线会被保存，但不会进入 paper/live/demo 信号生成。单标的回测也会先过滤未确认 K 线，并采用 `next_bar_open` 执行模型：用当前已收盘 bar 生成信号，在下一根 bar 的 open 成交，同时继续计入手续费和滑点。

`live run` 是受控 Production 组合交易单轮执行入口，会复用跨币种动量组合策略、风控门控、OKX 账户余额、OKX 下单接口、订单精度处理和本地审计。`config/live.example.yaml` 仍然把 `execution.live_enabled` 设为 `false`，所以必须复制配置并显式改为 `true` 后才可能通过门控。

`service run-live-portfolio` / `service start-live-portfolio` 是受控 Production 组合交易长期运行入口。它们复用同一套 live 组合策略和风控，并额外具备 heartbeat、PID 锁、stop 文件、连续错误熔断、watchdog 和可选 OKX `cancel-all-after`。默认仍不会通过门控，除非 live 配置显式启用并传入 `--confirm-live`。

`service acceptance` 是无人值守验收演练入口。它使用隔离目录 `state/acceptance` 和 `logs/acceptance`，不会污染正式纸交易状态；检查项包括 kill switch 预检查、纸交易服务多轮运行、服务健康检查、watchdog 正常巡检和 live 门控负测，并输出 `reports/unattended_acceptance_latest.json`。

`service live-gate-drill` 是实盘前门控演练入口，不访问 OKX、不下单。它验证 `live_enabled=false`、缺少 `--confirm-live`、缺少凭证时会阻断；同时验证全部条件满足时门控可通过，以及 kill switch 会阻断新订单但允许 reduce-only 订单。

## Demo Trading 凭证

Demo Trading 必须使用 OKX Demo Trading 页面创建的 API key。系统不会把 Production key 当作 Demo key 使用。

`.env` 变量：

```bash
OKX_DEMO_API_KEY=
OKX_DEMO_API_SECRET=
OKX_DEMO_PASSPHRASE=

OKX_API_KEY=
OKX_API_SECRET=
OKX_PASSPHRASE=
OKX_PROXY_URL=http://127.0.0.1:1082
```

验证顺序：

```bash
PYTHONPATH=src python3 -m quant_system.cli okx diagnose
PYTHONPATH=src python3 -m quant_system.cli okx readiness
PYTHONPATH=src python3 -m quant_system.cli okx order-dry-run --symbol BTC/USDT --instrument-type spot
PYTHONPATH=src python3 -m quant_system.cli okx demo-smoke
PYTHONPATH=src python3 -m quant_system.cli okx demo-smoke --place-test-order
PYTHONPATH=src python3 -m quant_system.cli okx demo-run-once --symbol BTC/USDT --instrument-type spot
PYTHONPATH=src python3 -m quant_system.cli okx cancel-all-after --timeout-seconds 60
```

`--place-test-order` 会使用账户可交易品种信息里的 `minSz`、`lotSz`、`tickSz` 计算测试限价单，并在返回订单号后尝试撤单。
`demo-run-once` 会执行一次真实 Demo 策略循环：拉 K 线、生成信号、过风控、计算订单；只有传 `--confirm-demo-order` 才向 OKX Demo Trading 发单。
`demo-loop` 会按固定间隔重复执行 Demo 策略循环，并把最近状态写入 SQLite。
`cancel-all-after` 会调用 OKX 交易所级倒计时撤单接口，用于无人值守时的 dead man's switch。

## 无人值守服务

`service run-demo` 是 OKX Demo 单标的长期运行入口，`service run-paper-portfolio` 是跨币种动量组合纸交易前台长期运行入口。`service start-paper-portfolio` 会在后台启动组合纸交易服务，并默认同时启动独立 watchdog。未显式传入 `--watchdog-max-heartbeat-age-seconds` 时，CLI 会按交易循环间隔自动放大心跳阈值，避免小时级策略被 300 秒默认值误杀。服务包含：

- PID 锁：防止重复启动
- heartbeat：`state/quant_service_heartbeat.json`
- SQLite 状态：`run_state.quant_service`
- 轮转日志：`logs/quant_service.log`
- stop 文件：`state/quant_service.stop`
- SIGTERM/SIGINT 处理
- 连续错误熔断
- 每轮交易前自动刷新 OKX 最新 K 线
- 刷新行情按标的独立容错：单个标的网络失败会记录 `refresh_errors`，不会直接中断整轮；若本地行情过期，stale guard 仍会阻断交易
- 启动前写入 bootstrap heartbeat 并清理旧 stop/heartbeat；paper 启动会清理 paper kill switch，避免 watchdog 读取旧状态误杀新服务
- 后台 launch 状态：`state/quant_service_launch.json`

默认不真实发 Demo 单；传 `--confirm-demo-order` 后才允许策略订单进入 OKX Demo Trading。

组合纸交易服务会把账户状态写入 SQLite 的 `run_state.paper_portfolio`，重启后继续沿用已有现金和持仓，不会从零开始重复建仓。目标暴露按 `risk.live_trading_cap_usdt` 和 `risk.max_symbol_exposure_pct` 计算，默认等价于每个选中标的最多约 `10 USDT`。

`service health` 用于巡检无人值守状态，会检查 heartbeat 是否过期、最近一轮是否失败、连续错误是否触发熔断，并返回组合权益、回撤、持仓、最近调仓选择和日志路径。监控进程可加 `--require-running` 要求服务必须正在运行。

`service report` 会把当前 service/watchdog 状态和 health 结果写入 `reports/service_observation_latest.json`，用于长期观察留痕。

`service snapshot` 会写入 `reports/runtime_snapshot_latest.json`，记录当前配置、服务状态、watchdog、health、最近关键报告和凭证存在性。该报告只记录环境变量名和凭证是否存在，不写入 API key、secret 或 passphrase。

`service stability` 会按当前服务启动时间聚合事件日志和服务日志，输出运行时长、paper 迭代次数、watchdog 迭代次数、订单数、失败事件数、权益范围和选币次数到 `reports/service_stability_latest.json`。长期运行循环使用可中断 sleep，收到 stop 文件或 SIGTERM 后不需要等完整交易间隔才退出。

`service watchdog` 是独立监督进程。它按固定间隔调用 `service health --require-running`；一旦发现服务未运行、心跳过期或最近迭代失败，会写入 `state/KILL_SWITCH`，请求服务停止，并记录到 `logs/quant_watchdog.log`、`state/quant_watchdog_heartbeat.json` 和 JSONL 事件日志。

paper 观察期可以给 watchdog 加 `--recover-paper`，或在后台启动时传 `--watchdog-recover-paper`。该恢复路径只在服务未运行时尝试恢复最近一次 `paper_portfolio_service`，不会恢复 live 命令；其他健康失败仍走 kill switch/停机路径。

`service recover-paper` 可基于 `state/quant_service_launch.json` 恢复最近一次 paper portfolio 后台服务。它只接受 `paper_portfolio_service` + `run-paper-portfolio` 的历史启动命令；如果 kill switch 存在、服务已经运行、或 launch state 指向 live 命令，则不会重启。

`service pre-live-check` 是实盘前聚合预检。它默认先刷新 `service_stability_latest.json`，再检查服务健康、watchdog、24h+ 纸交易稳定性、失败事件、live gate drill、通知 webhook、Production live 配置、Production 凭证、operator 风控上限、kill switch 和策略短名单。任何一项不通过都会返回非 0，并写入 `reports/pre_live_check_latest.json`。默认 operator 上限是首次实盘资金 `50 USDT`、最大杠杆 `3x`，同时要求单品种暴露不超过 20%、日亏不超过 2%、组合回撤熔断不超过 5%、单次调仓换手不超过 50%。

通知默认写入 `logs/quant_notifications.jsonl`。如需接入 Telegram、飞书、企业微信或自建告警服务，可把它们封装成 webhook，并设置：

```bash
export QUANT_NOTIFICATION_WEBHOOK_URL=https://example.com/your-webhook
```

当前会对 kill switch、watchdog 健康失败、过期行情和实际下单事件发通知。未设置 webhook 时不会联网，只保留本地通知审计日志。

实盘前可运行通知演练：

```bash
PYTHONPATH=src python3 -m quant_system.cli service notification-drill --level warning
```

未设置 webhook 时，报告状态为 `local_only`，表示本地审计日志可用但外部告警未验收；设置 `QUANT_NOTIFICATION_WEBHOOK_URL` 后，只有 webhook 发送成功才会标记为 `passed`。

实盘前聚合预检示例：

```bash
PYTHONPATH=src python3 -m quant_system.cli service pre-live-check \
  --min-observation-hours 24 \
  --max-live-cap-usdt 50 \
  --max-leverage 3 \
  --max-heartbeat-age-seconds 5520
```

运行审计快照示例：

```bash
PYTHONPATH=src python3 -m quant_system.cli service snapshot \
  --max-heartbeat-age-seconds 5520
```

后台启动示例：

```bash
PYTHONPATH=src python3 -m quant_system.cli service start-paper-portfolio \
  --instrument-type spot \
  --symbol BTC/USDT --symbol ETH/USDT \
  --lookback-bars 720 \
  --top-n 2 \
  --refresh-candles \
  --interval-seconds 3600
```

该命令立即返回 PID 和启动命令；运行状态用 `service status`、`service health --require-running` 查看，停止用 `service stop`。

组合纸交易支持生产防线：

- `market.trade_allowlist` / `market.trade_blocklist`：实盘候选白名单/黑名单
- `risk.max_portfolio_drawdown_pct`：组合高水位回撤熔断，触发后停止新开仓并尝试降风险
- `risk.max_turnover_per_rebalance_pct`：单次调仓换手预算，超出时缩小或跳过新增仓位
- `service.max_candle_age_seconds`：行情过期保护，K 线太旧时不调仓
- `service.refresh_candles_before_iteration`：每轮组合交易前刷新 OKX 最新 K 线
- `service.rebalance_cooldown_seconds`：调仓冷却，避免短时间重复开仓
- `service.watchdog_max_heartbeat_age_seconds`：watchdog 判定心跳过期的阈值
- `service.okx_cancel_all_after_seconds`：Demo 服务每轮刷新 OKX 交易所级倒计时撤单；默认 `0` 关闭
- `service.event_log_file`：本地 JSONL 事件日志，记录调仓、熔断、过期数据等事件
- `service.notification_log_file`：本地通知审计日志
- `service.notification_webhook_url_env`：外部 webhook URL 环境变量名，默认 `QUANT_NOTIFICATION_WEBHOOK_URL`

受控运行示例：

```bash
PYTHONPATH=src python3 -m quant_system.cli service run-paper-portfolio \
  --instrument-type spot \
  --symbol OKB/USDT --symbol FLOKI/USDT --symbol WLD/USDT --symbol PEPE/USDT \
  --symbol LTC/USDT --symbol NEAR/USDT --symbol BTC/USDT --symbol INJ/USDT \
  --symbol OP/USDT --symbol ETH/USDT \
  --block-symbol OKB/USDT \
  --block-symbol FLOKI/USDT \
  --block-symbol PEPE/USDT \
  --lookback-bars 720 \
  --top-n 2 \
  --max-turnover-pct 0.25 \
  --max-portfolio-drawdown-pct 0.05 \
  --max-candle-age-seconds 7200 \
  --rebalance-cooldown-seconds 3600 \
  --refresh-candles \
  --interval-seconds 3600
```

监督进程示例：

```bash
PYTHONPATH=src python3 -m quant_system.cli service watchdog \
  --max-heartbeat-age-seconds 3900 \
  --interval-seconds 60
```

## 策略候选

当前可回测候选：

- `trend_mr`：趋势 + RSI/布林均值回归组合
- `vol_trend`：波动率调整 EMA 趋势
- `donchian_breakout`：Donchian 突破
- `rsi_bollinger_reversion`：RSI + 布林均值回归
- `adaptive_trend`：滚动 Sharpe 选币 + EMA 趋势过滤 + 波动率目标仓位

一键回测：

```bash
PYTHONPATH=src python3 -m quant_system.cli research sweep \
  --symbol BTC/USDT \
  --symbol ETH/USDT \
  --instrument-type spot \
  --write-report
```

横截面动量：

```bash
PYTHONPATH=src python3 -m quant_system.cli research xsmom \
  --symbol BTC/USDT \
  --symbol ETH/USDT \
  --instrument-type spot \
  --lookback-bars 720 \
  --hold-bars 168 \
  --write-report
```

Adaptive trend：

```bash
PYTHONPATH=src python3 -m quant_system.cli research adaptive-trend \
  --symbol BTC/USDT \
  --symbol ETH/USDT \
  --instrument-type spot \
  --lookback-bars 720 \
  --hold-bars 72 \
  --top-n 2 \
  --ema-span 480 \
  --volatility-bars 336 \
  --write-report
```

参数网格筛选：

```bash
PYTHONPATH=src python3 -m quant_system.cli research xsmom-grid \
  --symbol BTC/USDT \
  --symbol ETH/USDT \
  --instrument-type spot \
  --lookback-bars 168 \
  --lookback-bars 336 \
  --lookback-bars 720 \
  --hold-bars 24 \
  --hold-bars 72 \
  --hold-bars 168 \
  --top-n 1 \
  --top-n 2 \
  --write-report
```

Walk-forward / OOS 验证：

```bash
PYTHONPATH=src python3 -m quant_system.cli research xsmom-walk-forward \
  --symbol BTC/USDT \
  --symbol ETH/USDT \
  --instrument-type spot \
  --lookback-bars 168 \
  --lookback-bars 336 \
  --lookback-bars 720 \
  --hold-bars 24 \
  --hold-bars 72 \
  --hold-bars 168 \
  --top-n 1 \
  --top-n 2 \
  --train-bars 1000 \
  --test-bars 240 \
  --step-bars 240 \
  --write-report
```

成本敏感性测试：

```bash
PYTHONPATH=src python3 -m quant_system.cli research xsmom-costs \
  --symbol BTC/USDT \
  --symbol ETH/USDT \
  --instrument-type spot \
  --lookback-bars 720 \
  --hold-bars 168 \
  --top-n 2 \
  --fee-rate 0.0008 \
  --fee-rate 0.0015 \
  --fee-rate 0.003 \
  --slippage-bps 2 \
  --slippage-bps 5 \
  --slippage-bps 10 \
  --write-report
```

Adaptive trend 的同类验证入口：

```bash
PYTHONPATH=src python3 -m quant_system.cli research adaptive-trend-grid --write-report
PYTHONPATH=src python3 -m quant_system.cli research adaptive-trend-walk-forward --write-report
PYTHONPATH=src python3 -m quant_system.cli research adaptive-trend-costs --write-report
```

当前本地 10 个 OKX USDT 现货标的初筛里，跨币种动量优于单标的技术指标策略。最新 walk-forward 样本外结果为 4 折、3 折正收益、累计 OOS 约 `36.9%`，最差 OOS 回撤约 `-14.0%`。当前 9 组手续费/滑点场景全部为正，最差收益约 `43.8%`、最差回撤约 `-8.0%`。

`adaptive_trend` 已完成参数网格、walk-forward 和成本敏感性验证。当前网格最优参数为 `lookback=720`、`hold=168`、`top_n=2`、`ema_span=480`、`volatility_bars=168`、`target_volatility=0.15`、`max_weight=0.35`，样本内收益约 `10.2%`、最大回撤约 `-1.0%`。walk-forward 样本外 4/4 折为正，累计 OOS 约 `9.6%`，最差 OOS 回撤约 `-1.6%`；9 组手续费/滑点场景全部为正，最差收益约 `9.0%`。结论：它更像低回撤候选，收益弹性明显低于跨币种动量；当前仍优先纸交易观察，不是实盘建议。

资金费率 / carry 方向已接入 OKX `funding-rate-history` 数据和 `funding_carry` 回测，并完成参数网格、walk-forward 和成本敏感性初验。当前 8 个 OKX USDT 永续标的样本内网格最优为 `lookback_periods=9`、`hold_periods=3`、`top_n=1`、`min_funding_rate=0.0001`、`max_notional_pct=0.5`，收益约 `108.6%`、最大回撤约 `-4.1%`、Sharpe 约 `7.73`。但 walk-forward 结果明显不稳：5 折仅 1 折正收益，累计 OOS 约 `10.4%`，平均 OOS Sharpe 为负。结论：funding carry 保留为研究候选，但当前不能列为优质主策略，必须继续做更长历史、跨交易所 funding、执行可行性和保证金风控验证。

`research shortlist` 会把当前策略验证报告汇总成机器可读短名单。`research promotion-scorecard` 在短名单之上输出统一晋级评分：idea、factor、strategy、paper、small live 阶段，评分拆解，研究阻断项，运营阻断项和人工启用要求。当前结论：`cross_sectional_momentum` 是主纸交易策略，`adaptive_trend` 是低回撤备选，`funding_carry` 仅保留研究。`live_ready=false`，当前阻断项是 24h+ 纸交易稳定性尚未完成、通知 webhook 未配置、Production live 配置仍需人工显式启用；live gate drill 已通过。

`research multi-timeframe-sweep` 是多周期研究入口，可对同一策略池、同一标的池在多个 bar 上重复执行标准 sweep，并输出 `multi_timeframe_strategy_sweep_latest.json`。它会继承 Strategy Card 门禁和 OHLCV 质量门禁，用于在正式深入研究前检查策略是否只在单一周期偶然有效。

`review queue` 是复盘闭环入口，会汇总数据质量问题、服务异常、pre-live 阻断、通知演练状态、策略降级和晋级候选，写入 `review_queue_latest.json` 与 SQLite `review_tasks`。传 `--notify` 时会复用现有 webhook/本地通知日志，把复盘队列摘要发到外部告警或本地审计。

`knowledge/bitcoin_strategy_knowledge_base.yaml` 是 BTC 策略知识库。`research knowledge-base` 会校验每条策略是否包含逻辑、数据要求、信号、进出场、仓位、风控、适用市场、失效条件、复现难度和当前复现/回测状态，并输出覆盖度报告。最新覆盖为 13 个条目、10 个已实现/回测；单标的 backtest/sweep 报告包含年化收益、最大回撤、Sharpe、胜率、盈亏比、交易次数和市场状态表现。`btc-eth-cointegration` 是研究型 BTC/ETH 相对价值回测，使用已确认 K 线、滚动 hedge ratio、spread z-score 和下一根 open 执行。

`research factor-evaluate` 是 Crypto 因子研究统一管线入口，借鉴 Qlib 的数据/因子/记录分层但不依赖 qlib 包。V1 支持 Python 因子 builder，内置 `crypto_momentum_24h`、`crypto_reversal_6h` 和 `crypto_volume_pressure`，使用本地已确认 OKX K 线生成因子、forward return、IC、RankIC、ICIR、分位收益、多空收益、top 分位换手、覆盖率和缺失率报告。因子报告只用于研究，不会自动进入 paper/live 候选。

`research alpha-ensemble` 是外部 alpha/CTA 因子接入的研究入口。它读取 YAML spec，把平台内置因子或 `data/alpha_factors/**` 下的外部 CSV 因子通过 `ma_diff`、`z_score`、`minmax`、`robust_scaling`、`box_cox`、`rate_of_change` 等滚动 transform 转成 bounded signal，再按 group 等权、group 权重合成研究组合。输出始终标记为 `research_only`，不会自动进入 paper/live。

已迁移到标准 FactorBuilder 的旧策略因子：

- `cross_sectional_momentum_720h`
- `adaptive_trend_quality`
- `altcoin_btc_residual_reversion`
- `funding_carry_recent`
- `btc_time_series_momentum_336h`
- `volatility_adjusted_btc_trend`

这些迁移只表示因子层可用；是否升级成策略仍需经过 strategy research、walk-forward、cost sensitivity、shortlist 和 paper/live 门控。

## 目录

- `src/quant_system/`：主系统代码
- `config/`：默认、纸交易、实盘示例配置
- `tests/`：安全边界、策略、风控、回测、CLI 测试
- `data/`：本地行情数据
- `state/`：SQLite 审计库和 kill switch
- `reports/`：回测/运行报告
- `archive/`：历史 Longbridge、旧 quant-system 和 RD-Agent 实验资产，当前不是主链路

## 需要你后续提供

- OKX API Key
- OKX Secret Key
- OKX Passphrase
- Demo Trading 还是 Production Trading
- API domain：全球站默认 `openapi.okx.com`，或区域域名 `us.okx.com` / `eea.okx.com`
- API 权限：read + trade，不需要 withdraw
- 是否绑定 IP 白名单
- OKX 账户模式、子账户、首次实盘资金上限、永续杠杆和保证金模式

当前已收到：Demo Trading、子账户优先、首次实盘资金上限 `50 USDT`、允许永续、杠杆范围 `1-3x`、全仓。安全默认仍按 `1x`。

## 当前连通性诊断

- 本机 OKX 需要走系统代理，已通过 `.env` 的 `OKX_PROXY_URL` 支持。
- Production 只读 key 和 Demo Trading key 已分别验证。
- Demo Trading 测试下单与撤单已跑通；策略循环默认仍只计划订单，必须显式传确认参数才会发 Demo 单。
