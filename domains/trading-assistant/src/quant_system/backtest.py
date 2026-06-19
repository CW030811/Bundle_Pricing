from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from .benchmarks import standard_backtest_benchmarks
from .broker import PaperBroker, target_signal_to_order
from .config import AppConfig
from .data import filter_confirmed_candles
from .indicators import add_indicators
from .models import InstrumentType, position_key
from .reports import calculate_metrics, calculate_regime_performance, write_report
from .reproducibility import reproducibility_payload
from .risk import RiskManager
from .storage import AuditStore
from .strategies import Strategy, build_strategy


class Backtester:
    def __init__(self, config: AppConfig, strategy: Optional[Strategy] = None):
        self.config = config
        self.strategy = strategy or build_strategy(config.strategy)
        self.broker = PaperBroker(config)
        self.risk = RiskManager(config.risk, config.execution)
        self.risk_events: list[dict[str, object]] = []

    def run(self, candles: pd.DataFrame, symbol: str, instrument_type: InstrumentType) -> dict[str, object]:
        candles = filter_confirmed_candles(candles, require_confirmed=True)
        warmup = max(self.config.strategy.slow_ema, self.config.strategy.bollinger_period, 20)
        candles = add_indicators(
            candles,
            self.config.strategy.fast_ema,
            self.config.strategy.slow_ema,
            self.config.strategy.rsi_period,
            self.config.strategy.atr_period,
            self.config.strategy.bollinger_period,
            self.config.strategy.bollinger_std,
        )
        equity_rows: list[dict[str, object]] = []
        trade_rows: list[dict[str, object]] = []

        for idx in range(warmup, max(len(candles) - 1, warmup)):
            window = candles.iloc[: idx + 1]
            signal_bar = window.iloc[-1]
            execution_bar = candles.iloc[idx + 1]
            execution_price = float(execution_bar.get("open", execution_bar["close"]))
            if pd.isna(execution_price):
                execution_price = float(execution_bar["close"])
            prices = {symbol: execution_price, position_key(symbol, instrument_type): execution_price}
            portfolio = self.broker.portfolio(prices)
            signal = self.strategy.generate(window, symbol, instrument_type)
            position = portfolio.position_for(symbol, instrument_type)
            intent = target_signal_to_order(
                signal.target_pct, symbol, instrument_type, position.quantity, portfolio.equity, execution_price
            )
            if intent:
                decision = self.risk.evaluate(intent, portfolio, execution_price)
                if not decision.approved:
                    self.risk_events.append(
                        {
                            "ts": execution_bar["ts"],
                            "signal_ts": signal_bar["ts"],
                            "symbol": symbol,
                            "reason": decision.reason,
                        }
                    )
                else:
                    if decision.adjusted_quantity:
                        intent = replace(intent, quantity=decision.adjusted_quantity)
                    before_pnl = position.realized_pnl
                    order = self.broker.submit_order(intent, execution_price)
                    after = self.broker.portfolio(prices).position_for(symbol, instrument_type)
                    trade_rows.append(
                        {
                            "ts": execution_bar["ts"],
                            "signal_ts": signal_bar["ts"],
                            "execution_ts": execution_bar["ts"],
                            "execution_price_source": "next_bar_open",
                            "symbol": symbol,
                            "side": intent.side.value,
                            "quantity": order.filled_quantity,
                            "price": order.average_price,
                            "status": order.status.value,
                            "realized_pnl": after.realized_pnl - before_pnl,
                        }
                    )
            equity_rows.append({"ts": execution_bar["ts"], "equity": self.broker.portfolio(prices).equity})

        equity_curve = pd.DataFrame(equity_rows)
        trades = pd.DataFrame(trade_rows)
        metrics = calculate_metrics(equity_curve, trades)
        regime_performance = calculate_regime_performance(equity_curve, candles)
        return {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "symbol": symbol,
            "instrument_type": instrument_type.value,
            "strategy": self.strategy.name,
            "execution_model": "next_bar_open",
            "confirmed_only": True,
            "metrics": metrics,
            "benchmarks": standard_backtest_benchmarks(
                candles,
                initial_cash=self.config.backtest.initial_cash,
                fee_rate=self.config.execution.fee_rate,
                slippage_bps=self.config.execution.slippage_bps,
            ),
            "regime_performance": regime_performance,
            "equity_curve": equity_curve,
            "trades": trades,
            "risk_events": self.risk_events,
        }

    def run_and_write(self, candles: pd.DataFrame, symbol: str, instrument_type: InstrumentType) -> Path:
        result = self.run(candles, symbol, instrument_type)
        serializable = {
            **{k: v for k, v in result.items() if k not in {"equity_curve", "trades"}},
            "equity_curve_tail": result["equity_curve"].tail(20).to_dict("records"),
            "trades": result["trades"].to_dict("records"),
        }
        serializable["reproducibility"] = reproducibility_payload(
            self.config,
            artifact_type="backtest",
            artifact_name=self.strategy.name,
            data_version="v1",
            factor_version=None,
            parameters={
                "symbol": symbol,
                "instrument_type": instrument_type.value,
                "strategy": self.strategy.name,
                "interval": self.config.market.bar,
            },
        )
        path = write_report(self.config.report_dir, "backtest", serializable)
        final_capital = None
        equity_curve = result["equity_curve"]
        if not equity_curve.empty and "equity" in equity_curve:
            final_capital = float(equity_curve["equity"].iloc[-1])
        audit = AuditStore(self.config.state_dir)
        backtest_id = audit.insert_backtest_result(
            result=result,
            interval=self.config.market.bar,
            initial_capital=self.config.backtest.initial_cash,
            final_capital=final_capital,
            fee_assumption=self.config.execution.fee_rate,
            slippage_assumption=self.config.execution.slippage_bps,
            report_path=path,
        )
        audit.insert_backtest_trades(
            backtest_id=backtest_id,
            strategy_id=self.strategy.name,
            exchange="okx",
            market_type=instrument_type.value,
            trades=result["trades"],
        )
        audit.insert_reproducibility_record(serializable["reproducibility"], artifact_path=path)
        return path
