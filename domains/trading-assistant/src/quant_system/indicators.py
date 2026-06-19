from __future__ import annotations

import pandas as pd


def add_indicators(
    candles: pd.DataFrame,
    fast_ema: int,
    slow_ema: int,
    rsi_period: int,
    atr_period: int,
    bollinger_period: int,
    bollinger_std: float,
) -> pd.DataFrame:
    df = candles.copy().sort_values("ts").reset_index(drop=True)
    close = df["close"]
    high = df["high"]
    low = df["low"]
    prev_close = close.shift(1)

    df["ema_fast"] = close.ewm(span=fast_ema, adjust=False).mean()
    df["ema_slow"] = close.ewm(span=slow_ema, adjust=False).mean()

    delta = close.diff()
    gain = delta.clip(lower=0).rolling(rsi_period).mean()
    loss = (-delta.clip(upper=0)).rolling(rsi_period).mean()
    rs = gain / loss.replace(0, float("nan"))
    df["rsi"] = (100 - (100 / (1 + rs))).fillna(50)

    true_range = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    df["atr"] = true_range.rolling(atr_period).mean().bfill()

    mid = close.rolling(bollinger_period).mean()
    std = close.rolling(bollinger_period).std()
    df["bb_mid"] = mid
    df["bb_upper"] = mid + bollinger_std * std
    df["bb_lower"] = mid - bollinger_std * std
    df["volatility"] = close.pct_change().rolling(bollinger_period).std().fillna(0)
    df["volume_ma"] = df["volume"].rolling(bollinger_period).mean().fillna(df["volume"])
    return df
