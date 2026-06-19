# Quant Platform Architecture

## Positioning

This workspace is a general quantitative research and trading platform with a
Crypto/OKX-first implementation. The current production-quality path is crypto
market data, factor research, strategy research, backtesting, paper trading, and
gated live execution. Equity, multi-asset, and automated alpha-mining work are
future extensions unless explicitly marked otherwise.

## Layers

- Data Layer: OKX candles, funding rates, exchange rules, derivative statistics,
  orderbook/trade/liquidation snapshots, discovered universes, DataHub ODS/DWD
  storage, ingestion logs, quality checks, and confirmed-candle filtering.
- Factor Research Layer: Python factor builders, forward returns, IC/RankIC,
  ICIR, quantile returns, top-bottom spread, turnover, coverage, and factor
  reports.
- Strategy Research Layer: strategy-specific research commands, grid search,
  walk-forward validation, cost sensitivity, multi-timeframe sweep, shortlist,
  and promotion scorecard reports.
- Backtest Layer: event-style backtesting with confirmed signals and next-bar
  open execution for single-asset strategies.
- Execution Layer: paper, demo, and gated live execution through shared broker,
  risk, service, watchdog, notification, and kill-switch boundaries.
- Knowledge/Reporting Layer: strategy knowledge base, reproducibility state,
  pipeline status, latest reports, review queue, and machine-readable summaries.

## DataHub Model

- ODS keeps raw OKX/API payloads immutable enough for replay and debugging.
- DWD keeps standardized OHLCV/funding data in reusable local Parquet/CSV files.
- DWS records factor definitions, parameters, versions, and calculation logs.
- ADS indexes strategy-facing outputs such as backtests, trades, strategy scores,
  target positions, signals, risk status, and review tasks.

Backtests and paper/live services should consume DWD/DWS/ADS surfaces, not raw API
payloads. ODS exists for audit, replay, and data-source drift checks.

## Standard Research Flow

1. Capture a paper or strategy idea in the strategy knowledge base.
2. Write or update a Strategy Card before coding: hypothesis, market mechanism,
   data requirements, rules, costs, risks, regimes, and failure modes.
3. If it is factor-like, implement it first as a factor builder and run
   `research factor-evaluate`.
4. Promote only promising factors into strategy research with position sizing,
   costs, and portfolio construction.
5. Run grid, walk-forward, cost sensitivity, parameter stability, and regime
   decomposition where applicable.
6. Use `research shortlist`, `research promotion-scorecard`, service stability,
   and pre-live checks before any paper/live promotion.

## Current Boundaries

- Current main code lives in `src/quant_system/`.
- Current research state lives in `knowledge/` and `reports/`.
- Current runtime state lives in `state/` and `logs/`.
- Historical reference assets live in `archive/` and are not part of the main
  execution path.
