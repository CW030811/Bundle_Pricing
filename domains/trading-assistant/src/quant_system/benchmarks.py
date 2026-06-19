from __future__ import annotations

import random
from typing import Any

import pandas as pd

from .reports import calculate_metrics


def standard_backtest_benchmarks(
    candles: pd.DataFrame,
    *,
    initial_cash: float,
    fee_rate: float,
    slippage_bps: float,
    fast_window: int = 24,
    slow_window: int = 72,
    random_seed: int = 17,
) -> dict[str, Any]:
    clean = candles.copy()
    if clean.empty:
        return {}
    clean["ts"] = pd.to_datetime(clean["ts"], utc=True, errors="coerce")
    clean = clean.dropna(subset=["ts", "close"]).sort_values("ts").reset_index(drop=True)
    if clean.empty:
        return {}
    return {
        "cash": _cash_benchmark(clean, initial_cash),
        "buy_and_hold": _buy_and_hold_benchmark(clean, initial_cash, fee_rate, slippage_bps),
        "simple_ma_trend": _simple_ma_trend_benchmark(clean, initial_cash, fee_rate, slippage_bps, fast_window, slow_window),
        "random_entry": _random_entry_benchmark(clean, initial_cash, fee_rate, slippage_bps, random_seed),
    }


def _cash_benchmark(candles: pd.DataFrame, initial_cash: float) -> dict[str, Any]:
    equity = pd.DataFrame({"ts": candles["ts"], "equity": [float(initial_cash)] * len(candles)})
    return {
        "description": "Stay in cash.",
        "metrics": calculate_metrics(equity, pd.DataFrame()),
    }


def _buy_and_hold_benchmark(candles: pd.DataFrame, initial_cash: float, fee_rate: float, slippage_bps: float) -> dict[str, Any]:
    entry = _price(candles.iloc[0], "open")
    if entry <= 0:
        entry = _price(candles.iloc[0], "close")
    entry_price = entry * (1 + _cost_rate(fee_rate, slippage_bps))
    quantity = initial_cash / entry_price if entry_price > 0 else 0.0
    equity = candles[["ts"]].copy()
    equity["equity"] = candles["close"].astype(float) * quantity
    return {
        "description": "Buy on first bar and hold through the backtest window.",
        "metrics": calculate_metrics(equity, pd.DataFrame()),
    }


def _simple_ma_trend_benchmark(
    candles: pd.DataFrame,
    initial_cash: float,
    fee_rate: float,
    slippage_bps: float,
    fast_window: int,
    slow_window: int,
) -> dict[str, Any]:
    df = candles.copy()
    df["fast_ma"] = df["close"].astype(float).rolling(fast_window).mean()
    df["slow_ma"] = df["close"].astype(float).rolling(slow_window).mean()
    desired = (df["fast_ma"] > df["slow_ma"]).fillna(False).astype(float)
    equity = _simulate_long_flat(df, desired, initial_cash, fee_rate, slippage_bps)
    return {
        "description": f"Long when {fast_window}-bar MA is above {slow_window}-bar MA, otherwise cash.",
        "metrics": calculate_metrics(equity, pd.DataFrame()),
    }


def _random_entry_benchmark(
    candles: pd.DataFrame,
    initial_cash: float,
    fee_rate: float,
    slippage_bps: float,
    random_seed: int,
) -> dict[str, Any]:
    rng = random.Random(random_seed)
    desired = pd.Series([1.0 if rng.random() >= 0.5 else 0.0 for _ in range(len(candles))])
    equity = _simulate_long_flat(candles, desired, initial_cash, fee_rate, slippage_bps)
    return {
        "description": f"Deterministic random long/flat baseline with seed {random_seed}.",
        "metrics": calculate_metrics(equity, pd.DataFrame()),
    }


def _simulate_long_flat(
    candles: pd.DataFrame,
    desired_exposure: pd.Series,
    initial_cash: float,
    fee_rate: float,
    slippage_bps: float,
) -> pd.DataFrame:
    cash = float(initial_cash)
    quantity = 0.0
    rows: list[dict[str, float | pd.Timestamp]] = []
    cost = _cost_rate(fee_rate, slippage_bps)
    for idx, row in candles.iterrows():
        price = _price(row, "close")
        target = float(desired_exposure.iloc[idx])
        equity = cash + quantity * price
        if target > 0 and quantity == 0 and price > 0:
            buy_price = price * (1 + cost)
            quantity = equity / buy_price
            cash = 0.0
        elif target <= 0 and quantity > 0 and price > 0:
            sell_price = price * (1 - cost)
            cash = quantity * sell_price
            quantity = 0.0
        rows.append({"ts": row["ts"], "equity": cash + quantity * price})
    return pd.DataFrame(rows)


def _price(row: pd.Series, column: str) -> float:
    value = row.get(column)
    try:
        if pd.isna(value):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _cost_rate(fee_rate: float, slippage_bps: float) -> float:
    return float(fee_rate) + float(slippage_bps) / 10_000.0
