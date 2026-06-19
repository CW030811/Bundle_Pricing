# trading-assistant / CONFIG

## 当前配置

- 阶段：OKX 全流程量化系统 v1
- 主链路：`src/quant_system`
- 配置入口：`config/default.yaml`
- 纸交易覆盖：`config/paper.yaml`
- 实盘模板：`config/live.example.yaml`
- 默认模式：`paper`
- 默认 OKX 环境：Demo Trading header enabled
- 本机代理：可通过 `.env` 设置 `OKX_PROXY_URL`
- Demo 凭证变量：`OKX_DEMO_API_KEY`、`OKX_DEMO_API_SECRET`、`OKX_DEMO_PASSPHRASE`
- Production 凭证变量：`OKX_API_KEY`、`OKX_API_SECRET`、`OKX_PASSPHRASE`
- 默认标的：`BTC/USDT`、`ETH/USDT`
- 默认周期：`1H`

## 风控默认值

- 单笔风险上限：账户权益 `0.5%`
- 首次实盘资金上限：`50 USDT`
- 单品种最大暴露：账户权益 `20%`
- 单日最大亏损：账户权益 `2%`
- 连续亏损暂停：`3` 笔
- 永续默认最大杠杆：`1x`
- 永续保证金模式：全仓
- kill switch：`state/KILL_SWITCH`
- 交易服务心跳：`state/quant_service_heartbeat.json`
- watchdog 心跳：`state/quant_watchdog_heartbeat.json`
- 交易服务后台启动状态：`state/quant_service_launch.json`
- watchdog 后台启动状态：`state/quant_watchdog_launch.json`
- watchdog 判定心跳过期阈值：`300` 秒
- OKX 交易所级倒计时撤单：`service.okx_cancel_all_after_seconds`，默认 `0` 关闭
- 组合服务每轮刷新行情：`service.refresh_candles_before_iteration: true`
- 每轮刷新 K 线数量：`service.refresh_candles_limit: 300`
- 通知审计日志：`logs/quant_notifications.jsonl`
- 通知 webhook 环境变量：`QUANT_NOTIFICATION_WEBHOOK_URL`

## 实盘开启条件

真实下单必须同时满足：

1. `mode: live`
2. `execution.live_enabled: true`
3. CLI 传入 `--confirm-live`
4. OKX 凭证环境变量齐全
5. 风控审批通过

当前 `live run` 提供受控单轮 Production 组合交易入口，`service run-live-portfolio` / `service start-live-portfolio` 提供受控后台 live 服务入口；默认配置仍不会通过实盘门控，必须显式启用 live 并确认。

## 本地状态

- 行情：`data/candles/**`
- 资金费率：`data/funding/**`
- 审计库：`state/quant_system.sqlite`
- DataHub ODS：`ods_crypto_ohlcv_raw`、`ods_crypto_funding_rate_raw`
- DataHub 质量与采集：`data_ingestion_logs`、`data_quality_issues`
- DataHub 因子/ADS：`factor_registry`、`factor_calculation_logs`、`ads_crypto_backtest_results`、`ads_crypto_strategy_scores`
- 报表：`reports/*_latest.json`
- 日志目录：`logs/`
- 交易服务日志：`logs/quant_service.log`
- watchdog 日志：`logs/quant_watchdog.log`
- 事件日志：`logs/quant_events.jsonl`
- 通知日志：`logs/quant_notifications.jsonl`
