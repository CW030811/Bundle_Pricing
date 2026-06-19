# 现有策略收益率表现图

生成时间：2026-06-05T03:58:37.845160+00:00

## 图表

- BTC 单标的技术策略：`strategy_performance_btc_spot_latest.png`
- 组合/研究型策略：`strategy_performance_portfolio_research_latest.png`
- 指标快照：`strategy_performance_metrics_latest.png`
- 曲线数据：`strategy_performance_curves_latest.csv`
- 指标数据：`strategy_performance_metrics_latest.csv`

## 口径说明

- 使用本地 OKX `1H` 已确认 K 线和 funding 数据，不联网刷新数据。
- 初始资金 `10000` USDT；手续费 `0.0008`；滑点 `2.0` bps。
- BTC 单标的策略使用项目 `Backtester`，信号来自已收盘 K 线，下一根 open 执行。
- 组合策略按现有研究逻辑重跑，并补充完整逐 bar mark-to-market 曲线用于绘图；因此可视化曲线比原 `*_latest.json` 的 tail 更完整。
- 不同策略的数据窗口不同：BTC 单标的最长；组合策略受 ETH/山寨币共同历史限制；funding 策略截至本地 funding 数据最后时间。

## 指标总览

| 策略 | 类型 | 窗口 | 总收益 | 最大回撤 | Sharpe | 交易数 |
|---|---:|---|---:|---:|---:|---:|
| `benchmark_btc_buy_hold` | benchmark | 2024-01-03 ~ 2026-06-05 | 53.46% | -31.60% | 1.193 | 0 |
| `cross_sectional_momentum` | portfolio_research | 2026-04-03 ~ 2026-06-05 | 43.09% | -28.09% | 2.354 | 18 |
| `benchmark_equal_weight_spot` | benchmark | 2026-04-03 ~ 2026-05-26 | 34.90% | -12.55% | 4.383 | 0 |
| `benchmark_btc_buy_hold_common` | benchmark | 2026-04-03 ~ 2026-05-26 | 16.39% | -9.58% | 3.188 | 0 |
| `funding_carry` | portfolio_research | 2026-02-21 ~ 2026-05-26 | 16.19% | -38.20% | 2.664 | 310 |
| `adaptive_trend` | portfolio_research | 2026-04-03 ~ 2026-06-05 | 9.78% | -4.21% | 2.804 | 34 |
| `btc_eth_cointegration_pairs` | portfolio_research | 2026-04-03 ~ 2026-06-05 | 0.38% | -2.67% | 0.385 | 417 |
| `trend` | btc_single_asset | 2024-01-03 ~ 2026-06-05 | 0.34% | -0.01% | 1.639 | 12 |
| `trend_mr` | btc_single_asset | 2024-01-03 ~ 2026-06-05 | 0.34% | -0.02% | 1.625 | 12 |
| `vol_trend` | btc_single_asset | 2024-01-03 ~ 2026-06-05 | 0.34% | -0.03% | 1.614 | 8 |
| `mean_reversion` | btc_single_asset | 2024-01-03 ~ 2026-06-05 | -0.00% | -0.00% | -0.830 | 8 |
| `rsi_bollinger_reversion` | btc_single_asset | 2024-01-03 ~ 2026-06-05 | -0.00% | -0.00% | -0.830 | 8 |
| `btc_volatility_breakout` | btc_single_asset | 2024-01-03 ~ 2026-06-05 | -0.00% | -0.00% | -2.028 | 7 |
| `donchian_breakout` | btc_single_asset | 2024-01-03 ~ 2026-06-05 | -0.00% | -0.00% | -1.503 | 4 |
| `btc_realized_volatility_targeting` | btc_single_asset | 2024-01-03 ~ 2026-06-05 | -0.00% | -0.01% | -2.551 | 4 |

## 快速解读

- 这次本地样本里总收益最高的是 `benchmark_btc_buy_hold`，总收益约 53.46%。
- 回撤最浅的是 `btc_volatility_breakout`，最大回撤约 -0.00%，但需要结合收益率一起看。
- Sharpe 最高的是 `benchmark_equal_weight_spot`，Sharpe 约 4.38。
