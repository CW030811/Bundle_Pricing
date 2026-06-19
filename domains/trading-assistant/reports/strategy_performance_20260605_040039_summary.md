# 现有策略收益率表现图

生成时间：2026-06-05T04:00:46.486858+00:00

## 图表

- BTC 单标的技术策略：`strategy_performance_btc_spot_latest.png`
- 组合/研究型策略：`strategy_performance_portfolio_research_latest.png`
- 指标快照：`strategy_performance_metrics_latest.png`
- 曲线数据：`strategy_performance_curves_latest.csv`
- 指标数据：`strategy_performance_metrics_latest.csv`

## 口径说明

- 使用本地 OKX `1H` 已确认 K 线和 funding 数据，不联网刷新数据。
- 初始资金 `10000` USDT；手续费 `0.0008`；滑点 `2.0` bps。
- BTC 文件存在 2024-01-07 15:00 UTC 到 2026-01-21 11:00 UTC 的长断档；本次 BTC 单标的图和指标只使用最大连续段。
- 组合策略按现有研究逻辑重跑/保留完整 mark-to-market 曲线；不同策略的数据窗口不同。

## 指标总览

| 策略 | 类型 | 窗口 | 总收益 | 最大回撤 | Sharpe | 交易数 |
|---|---:|---|---:|---:|---:|---:|
| `cross_sectional_momentum` | portfolio_research | 2026-04-03 ~ 2026-06-05 | 43.09% | -28.09% | 2.354 | 18 |
| `benchmark_equal_weight_spot` | benchmark | 2026-04-03 ~ 2026-05-26 | 34.90% | -12.55% | 4.383 | 0 |
| `benchmark_btc_buy_hold_common` | benchmark | 2026-04-03 ~ 2026-05-26 | 16.39% | -9.58% | 3.188 | 0 |
| `funding_carry` | portfolio_research | 2026-02-21 ~ 2026-05-26 | 16.19% | -38.20% | 2.664 | 310 |
| `adaptive_trend` | portfolio_research | 2026-04-03 ~ 2026-06-05 | 9.78% | -4.21% | 2.804 | 34 |
| `btc_eth_cointegration_pairs` | portfolio_research | 2026-04-03 ~ 2026-06-05 | 0.38% | -2.67% | 0.385 | 417 |
| `btc_volatility_breakout` | btc_single_asset | 2026-01-23 ~ 2026-06-05 | -0.00% | -0.00% | -2.079 | 7 |
| `donchian_breakout` | btc_single_asset | 2026-01-23 ~ 2026-06-05 | -0.00% | -0.00% | -2.310 | 8 |
| `mean_reversion` | btc_single_asset | 2026-01-23 ~ 2026-06-05 | -0.00% | -0.00% | -2.715 | 4 |
| `rsi_bollinger_reversion` | btc_single_asset | 2026-01-23 ~ 2026-06-05 | -0.00% | -0.00% | -2.715 | 4 |
| `trend` | btc_single_asset | 2026-01-23 ~ 2026-06-05 | -0.00% | -0.01% | -2.070 | 4 |
| `trend_mr` | btc_single_asset | 2026-01-23 ~ 2026-06-05 | -0.00% | -0.01% | -2.070 | 4 |
| `vol_trend` | btc_single_asset | 2026-01-23 ~ 2026-06-05 | -0.00% | -0.01% | -2.070 | 4 |
| `btc_realized_volatility_targeting` | btc_single_asset | 2026-01-23 ~ 2026-06-05 | -0.01% | -0.01% | -1.894 | 4 |
| `benchmark_btc_buy_hold` | benchmark | 2026-01-23 ~ 2026-06-05 | -29.85% | -31.60% | -1.767 | 0 |

## 数据断档提示

- BTC/USDT spot 1H: `2024-01-07T15:00:00+00:00` -> `2026-01-21T11:00:00+00:00`，约 17876 小时。

## 快速解读

- 本地样本总收益最高：`cross_sectional_momentum`，约 43.09%。
- 回撤最浅：`donchian_breakout`，最大回撤约 -0.00%，但收益也要一起看。
- Sharpe 最高：`benchmark_equal_weight_spot`，约 4.38。
