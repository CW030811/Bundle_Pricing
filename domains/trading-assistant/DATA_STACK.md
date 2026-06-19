# trading-assistant / DATA_STACK

## 当前主链路

1. OKX REST API v5
- 历史/最新 K 线：`/api/v5/market/candles`、`/api/v5/market/history-candles`
- 交易品种信息：`/api/v5/public/instruments`
- 资金费率：`/api/v5/public/funding-rate`
- 未平仓量：`/api/v5/public/open-interest`
- 盘口快照：`/api/v5/market/books`
- 最近成交：`/api/v5/market/trades`
- basis 组件：`/api/v5/public/mark-price`、`/api/v5/market/index-tickers`
- 多空账户比：`/api/v5/rubik/stat/contracts/long-short-account-ratio`
- 清算订单：`/api/v5/public/liquidation-orders`
- 账户余额：`/api/v5/account/balance`
- 下单：`/api/v5/trade/order`

2. OKX WebSocket API v5
- 当前实现：公共/私有 WebSocket URL 与订阅消息构造
- 首版用途：ticker、kline、后续 order updates

3. 本地数据
- 行情：`data/candles/**`
- 审计：`state/quant_system.sqlite`
- 报表：`reports/*_latest.json`

## DataHub 分层

当前系统采用本地轻量 DataHub：

- ODS 原始数据层：`ods_crypto_ohlcv_raw`、`ods_crypto_funding_rate_raw`、`ods_crypto_exchange_info_raw`、`ods_crypto_market_data_raw` 保存 OKX 原始返回，保留 source、exchange、symbol、market_type、raw_timestamp、ingested_at、raw_data、data_version。
- DWD 标准化数据层：`data/candles/**`、`data/funding/**`、`dwd_crypto_exchange_info`、`dwd_crypto_open_interest`、`dwd_crypto_basis`、`dwd_crypto_long_short_ratio`、`dwd_crypto_orderbook_snapshot`、`dwd_crypto_trades`、`dwd_crypto_liquidations` 保存标准化 OHLCV / funding / exchange rules / 衍生品与微观结构数据，本地优先 Parquet，缺 engine 时回退 CSV。
- DWS 因子与特征层：`factor_registry`、`factor_calculation_logs` 记录因子版本、参数、来源表、计算状态；`dws_crypto_factor_values` 保存可复用因子值。
- ADS 策略服务层：`ads_crypto_backtest_results`、`ads_crypto_backtest_trades`、`ads_crypto_strategy_scores`、`review_tasks` 等表索引回测、交易明细、策略短名单、统一晋级评分和复盘任务。

采集链路要求：请求 OKX -> 写 ODS -> 标准化写 DWD -> 数据质量检查 -> 写 ingestion log。数据质量问题进入 `data_quality_issues`。

## 存储策略

- 优先写 Parquet。
- 如果本机缺少 Parquet engine，则自动回退为 CSV，保持 CLI 和测试可运行。
- SQLite 保存信号、订单、持仓、风控事件和运行状态。
- SQLite 同时保存 DataHub 治理元数据、ODS 原始留存、质量问题、因子日志和 ADS 结果索引。

## 待打通

- OKX Demo Trading 私有接口连通性
- 私有 WebSocket order/channel 消息消费循环
- 长期后台调度与日志轮转
- Telegram/外部通知
