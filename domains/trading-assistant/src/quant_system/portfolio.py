from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

import pandas as pd

from .config import AppConfig
from .data import filter_confirmed_candles, load_candles
from .models import InstrumentType, PortfolioState, Position, position_key
from .storage import AuditStore


PAPER_PORTFOLIO_STATE_KEY = "paper_portfolio"


def portfolio_to_payload(
    portfolio: PortfolioState,
    prices: dict[str, float] | None = None,
    metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    metadata = metadata or {}
    return {
        "cash": portfolio.cash,
        "equity": portfolio.equity,
        "high_watermark": metadata.get("high_watermark", portfolio.equity),
        "drawdown": metadata.get("drawdown", 0.0),
        "daily_realized_pnl": portfolio.daily_realized_pnl,
        "consecutive_losses": portfolio.consecutive_losses,
        "positions": [
            {
                "symbol": position.symbol,
                "instrument_type": position.instrument_type.value,
                "quantity": position.quantity,
                "average_entry": position.average_entry,
                "realized_pnl": position.realized_pnl,
                "mark_price": (prices or {}).get(key) or (prices or {}).get(position.symbol),
            }
            for key, position in portfolio.positions.items()
            if abs(position.quantity) > 0
        ],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def portfolio_from_payload(payload: dict[str, object] | None, initial_cash: float) -> PortfolioState:
    if not payload:
        return PortfolioState(cash=initial_cash, equity=initial_cash, positions={})
    positions: dict[str, Position] = {}
    for item in payload.get("positions", []):
        if not isinstance(item, dict):
            continue
        instrument_type = InstrumentType(str(item["instrument_type"]))
        position = Position(
            symbol=str(item["symbol"]),
            instrument_type=instrument_type,
            quantity=float(item.get("quantity", 0.0)),
            average_entry=float(item.get("average_entry", 0.0)),
            realized_pnl=float(item.get("realized_pnl", 0.0)),
        )
        positions[position_key(position.symbol, position.instrument_type)] = position
    return PortfolioState(
        cash=float(payload.get("cash", initial_cash)),
        equity=float(payload.get("equity", initial_cash)),
        positions=positions,
        daily_realized_pnl=float(payload.get("daily_realized_pnl", 0.0)),
        consecutive_losses=int(payload.get("consecutive_losses", 0)),
    )


def load_paper_portfolio(audit: AuditStore, initial_cash: float) -> PortfolioState:
    return portfolio_from_payload(audit.get_state(PAPER_PORTFOLIO_STATE_KEY), initial_cash)


def save_paper_portfolio(
    audit: AuditStore,
    portfolio: PortfolioState,
    prices: dict[str, float] | None = None,
    metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    payload = portfolio_to_payload(portfolio, prices, metadata=metadata)
    audit.set_state(PAPER_PORTFOLIO_STATE_KEY, payload)
    return payload


def filter_trade_symbols(
    symbols: Iterable[str],
    allowlist: Iterable[str] | None = None,
    blocklist: Iterable[str] | None = None,
) -> list[str]:
    allowed = set(allowlist or [])
    blocked = set(blocklist or [])
    result = []
    for symbol in symbols:
        if allowed and symbol not in allowed:
            continue
        if symbol in blocked:
            continue
        if symbol not in result:
            result.append(symbol)
    return result


def load_close_matrix(
    config: AppConfig,
    symbols: Iterable[str],
    instrument_type: str,
    confirmed_only: bool = True,
) -> pd.DataFrame:
    series: dict[str, pd.Series] = {}
    for symbol in symbols:
        df = filter_confirmed_candles(load_candles(config, symbol, instrument_type), confirmed_only)
        if df.empty:
            continue
        series[symbol] = df.set_index("ts")["close"].astype(float).rename(symbol)
    if not series:
        return pd.DataFrame()
    return pd.concat(series.values(), axis=1).dropna().sort_index()


def cross_sectional_momentum_targets(
    closes: pd.DataFrame,
    lookback_bars: int,
    top_n: int,
    min_momentum: float = 0.0,
) -> dict[str, object]:
    if len(closes) <= lookback_bars:
        raise RuntimeError(f"insufficient history: have {len(closes)} bars, need > {lookback_bars}")
    latest = closes.iloc[-1]
    past = closes.iloc[-lookback_bars - 1]
    rank = (latest / past - 1).sort_values(ascending=False)
    selected = [symbol for symbol, value in rank.head(max(top_n, 1)).items() if float(value) > min_momentum]
    return {
        "ts": closes.index[-1],
        "selected": selected,
        "rank": {symbol: float(value) for symbol, value in rank.items()},
        "prices": {symbol: float(value) for symbol, value in latest.items()},
    }
