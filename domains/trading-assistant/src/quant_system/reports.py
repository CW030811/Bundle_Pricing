from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


def periods_per_year(equity_curve: pd.DataFrame) -> float:
    if equity_curve.empty or "ts" not in equity_curve or len(equity_curve) < 3:
        return 252.0
    ts = pd.to_datetime(equity_curve["ts"], utc=True, errors="coerce").dropna().sort_values()
    if len(ts) < 3:
        return 252.0
    median_seconds = ts.diff().dt.total_seconds().dropna().median()
    if not median_seconds or median_seconds <= 0:
        return 252.0
    return float((365.25 * 24 * 3600) / median_seconds)


def calculate_metrics(equity_curve: pd.DataFrame, trades: pd.DataFrame) -> dict[str, Any]:
    empty = {
        "total_return": 0.0,
        "annualized_return": 0.0,
        "max_drawdown": 0.0,
        "sharpe": 0.0,
        "win_rate": 0.0,
        "profit_loss_ratio": 0.0,
        "trade_count": 0,
    }
    if equity_curve.empty:
        return empty
    equity = equity_curve["equity"].astype(float)
    returns = equity.pct_change().fillna(0)
    total_return = equity.iloc[-1] / equity.iloc[0] - 1 if equity.iloc[0] else 0.0
    running_max = equity.cummax()
    drawdown = equity / running_max - 1
    annual_periods = periods_per_year(equity_curve)
    observed_periods = max(len(equity) - 1, 1)
    annualized_return = (1 + total_return) ** (annual_periods / observed_periods) - 1 if total_return > -1 else -1.0
    sharpe = 0.0 if returns.std() == 0 else (returns.mean() / returns.std()) * (annual_periods ** 0.5)
    win_rate = 0.0
    profit_loss_ratio = 0.0
    if not trades.empty and "realized_pnl" in trades:
        closed = trades[trades["realized_pnl"] != 0].copy()
        win_rate = float((closed["realized_pnl"] > 0).mean()) if not closed.empty else 0.0
        wins = closed.loc[closed["realized_pnl"] > 0, "realized_pnl"].astype(float)
        losses = closed.loc[closed["realized_pnl"] < 0, "realized_pnl"].astype(float).abs()
        if not wins.empty and not losses.empty and losses.mean() > 0:
            profit_loss_ratio = float(wins.mean() / losses.mean())
    return {
        "total_return": float(total_return),
        "annualized_return": float(annualized_return),
        "max_drawdown": float(drawdown.min()),
        "sharpe": float(sharpe),
        "win_rate": win_rate,
        "profit_loss_ratio": profit_loss_ratio,
        "trade_count": int(len(trades)),
        "fee_slippage_note": "Metrics include configured PaperBroker fee_rate and slippage_bps assumptions.",
    }


def calculate_regime_performance(equity_curve: pd.DataFrame, candles: pd.DataFrame, lookback: int = 72) -> dict[str, Any]:
    if equity_curve.empty or candles.empty:
        return {}
    eq = equity_curve.copy()
    eq["ts"] = pd.to_datetime(eq["ts"], utc=True, errors="coerce")
    regimes = classify_market_regimes(candles, lookback=lookback)
    if regimes.empty:
        return {}
    merged = pd.merge_asof(
        eq.sort_values("ts"),
        regimes[["ts", "primary_regime", "trend_regime", "volatility_regime", "liquidity_regime", "event_regime"]]
        .sort_values("ts"),
        on="ts",
        direction="backward",
    ).dropna(subset=["primary_regime"])
    return {
        "schema": "market_regime_v1",
        "coverage": market_regime_summary(candles, lookback=lookback),
        "by_primary_regime": _performance_by_regime(merged, "primary_regime"),
        "by_trend_regime": _performance_by_regime(merged, "trend_regime"),
        "by_volatility_regime": _performance_by_regime(merged, "volatility_regime"),
        "by_liquidity_regime": _performance_by_regime(merged, "liquidity_regime"),
        "by_event_regime": _performance_by_regime(merged, "event_regime"),
    }


def classify_market_regimes(candles: pd.DataFrame, lookback: int = 72) -> pd.DataFrame:
    required = {"ts", "close"}
    if candles.empty or not required.issubset(candles.columns):
        return pd.DataFrame()
    prices = candles.copy()
    prices["ts"] = pd.to_datetime(prices["ts"], utc=True, errors="coerce")
    prices["close"] = pd.to_numeric(prices["close"], errors="coerce")
    if "volume" not in prices:
        prices["volume"] = 0.0
    prices["volume"] = pd.to_numeric(prices["volume"], errors="coerce").fillna(0.0)
    prices = prices.sort_values("ts").dropna(subset=["ts", "close"]).reset_index(drop=True)
    if prices.empty:
        return pd.DataFrame()

    returns = prices["close"].pct_change()
    rolling_return = prices["close"].pct_change(lookback)
    realized_vol = returns.rolling(lookback).std() * (lookback ** 0.5)
    trend_threshold = realized_vol.fillna(0.0)
    volume_ma = prices["volume"].rolling(lookback).median()
    vol_quantile_low = realized_vol.rolling(lookback * 3, min_periods=lookback).quantile(0.35)
    vol_quantile_high = realized_vol.rolling(lookback * 3, min_periods=lookback).quantile(0.65)

    out = prices[["ts"]].copy()
    out["trend_regime"] = "sideways"
    out.loc[rolling_return > trend_threshold, "trend_regime"] = "bull"
    out.loc[rolling_return < -trend_threshold, "trend_regime"] = "bear"

    out["volatility_regime"] = "normal_volatility"
    out.loc[realized_vol <= vol_quantile_low, "volatility_regime"] = "low_volatility"
    out.loc[realized_vol >= vol_quantile_high, "volatility_regime"] = "high_volatility"

    out["liquidity_regime"] = "liquidity_rich"
    out.loc[(volume_ma > 0) & (prices["volume"] < volume_ma * 0.5), "liquidity_regime"] = "liquidity_poor"

    out["event_regime"] = "normal"
    out.loc[returns <= -realized_vol.fillna(0.0) * 2.0, "event_regime"] = "crash"
    out.loc[returns >= realized_vol.fillna(0.0) * 2.0, "event_regime"] = "rebound"

    out["primary_regime"] = out["trend_regime"]
    out.loc[out["event_regime"].isin(["crash", "rebound"]), "primary_regime"] = out["event_regime"]
    out.loc[
        (out["primary_regime"] == "sideways") & (out["volatility_regime"] == "high_volatility"),
        "primary_regime",
    ] = "high_volatility"
    out.loc[
        (out["primary_regime"] == "sideways") & (out["volatility_regime"] == "low_volatility"),
        "primary_regime",
    ] = "low_volatility"
    out.loc[
        (out["liquidity_regime"] == "liquidity_poor") & (out["primary_regime"] == "sideways"),
        "primary_regime",
    ] = "liquidity_poor"
    return out


def market_regime_summary(candles: pd.DataFrame, lookback: int = 72) -> dict[str, Any]:
    regimes = classify_market_regimes(candles, lookback=lookback)
    if regimes.empty:
        return {"schema": "market_regime_v1", "row_count": 0, "primary_regime_counts": {}}
    return {
        "schema": "market_regime_v1",
        "row_count": int(len(regimes)),
        "primary_regime_counts": _value_counts(regimes, "primary_regime"),
        "trend_regime_counts": _value_counts(regimes, "trend_regime"),
        "volatility_regime_counts": _value_counts(regimes, "volatility_regime"),
        "liquidity_regime_counts": _value_counts(regimes, "liquidity_regime"),
        "event_regime_counts": _value_counts(regimes, "event_regime"),
    }


def _performance_by_regime(frame: pd.DataFrame, column: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if column not in frame:
        return result
    for regime, group in frame.groupby(column):
        if len(group) < 2:
            continue
        sub_curve = group[["ts", "equity"]].reset_index(drop=True)
        result[str(regime)] = {
            "observations": int(len(sub_curve)),
            "total_return": calculate_metrics(sub_curve, pd.DataFrame())["total_return"],
            "max_drawdown": calculate_metrics(sub_curve, pd.DataFrame())["max_drawdown"],
        }
    return result


def _value_counts(frame: pd.DataFrame, column: str) -> dict[str, int]:
    if column not in frame:
        return {}
    return {str(key): int(value) for key, value in frame[column].value_counts(dropna=False).sort_index().items()}


def write_report(report_dir: Path, name: str, payload: dict[str, Any]) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = report_dir / f"{name}_{ts}.json"
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False, default=str)
    latest = report_dir / f"{name}_latest.json"
    with latest.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False, default=str)
    return path
