from __future__ import annotations

import pandas as pd

from .config import StrategySettings
from .indicators import add_indicators
from .models import InstrumentType, Signal

INDICATOR_COLUMNS = {"ema_fast", "ema_slow", "rsi", "atr", "bb_upper", "bb_lower"}


def with_indicators(candles: pd.DataFrame, settings: StrategySettings) -> pd.DataFrame:
    if INDICATOR_COLUMNS.issubset(candles.columns):
        return candles
    return add_indicators(
        candles,
        settings.fast_ema,
        settings.slow_ema,
        settings.rsi_period,
        settings.atr_period,
        settings.bollinger_period,
        settings.bollinger_std,
    )


class Strategy:
    name = "base"

    def generate(self, candles: pd.DataFrame, symbol: str, instrument_type: InstrumentType) -> Signal:
        raise NotImplementedError


class TrendStrategy(Strategy):
    name = "trend"

    def __init__(self, settings: StrategySettings):
        self.settings = settings

    def generate(self, candles: pd.DataFrame, symbol: str, instrument_type: InstrumentType) -> Signal:
        df = with_indicators(candles, self.settings)
        latest = df.iloc[-1]
        if len(df) < self.settings.slow_ema or latest["volume"] < self.settings.min_volume:
            target = 0.0
            reason = "insufficient history or volume"
            confidence = 0.1
        elif latest["ema_fast"] > latest["ema_slow"] and latest["rsi"] < 75:
            target = 0.15
            reason = "fast EMA above slow EMA with non-overbought RSI"
            confidence = 0.65
        elif latest["ema_fast"] < latest["ema_slow"] and instrument_type == InstrumentType.SWAP:
            target = -0.10
            reason = "fast EMA below slow EMA; swap can express short exposure"
            confidence = 0.55
        else:
            target = 0.0
            reason = "trend filter neutral"
            confidence = 0.35
        return Signal(symbol, instrument_type, latest["ts"].to_pydatetime(), target, confidence, reason, self.name)


class MeanReversionStrategy(Strategy):
    name = "mean_reversion"

    def __init__(self, settings: StrategySettings):
        self.settings = settings

    def generate(self, candles: pd.DataFrame, symbol: str, instrument_type: InstrumentType) -> Signal:
        df = with_indicators(candles, self.settings)
        latest = df.iloc[-1]
        if len(df) < self.settings.bollinger_period:
            target = 0.0
            reason = "insufficient history"
            confidence = 0.1
        elif latest["close"] < latest["bb_lower"] and latest["rsi"] < 35:
            target = 0.10
            reason = "price below lower Bollinger band with weak RSI"
            confidence = 0.60
        elif latest["close"] > latest["bb_upper"] and instrument_type == InstrumentType.SWAP:
            target = -0.08
            reason = "price above upper Bollinger band; swap can mean-revert short"
            confidence = 0.55
        else:
            target = 0.0
            reason = "mean-reversion filter neutral"
            confidence = 0.30
        return Signal(symbol, instrument_type, latest["ts"].to_pydatetime(), target, confidence, reason, self.name)


class TrendMeanReversionStrategy(Strategy):
    name = "trend_mr"

    def __init__(self, settings: StrategySettings):
        self.trend = TrendStrategy(settings)
        self.mean_reversion = MeanReversionStrategy(settings)

    def generate(self, candles: pd.DataFrame, symbol: str, instrument_type: InstrumentType) -> Signal:
        trend = self.trend.generate(candles, symbol, instrument_type)
        mr = self.mean_reversion.generate(candles, symbol, instrument_type)
        target = max(min((trend.target_pct * trend.confidence + mr.target_pct * mr.confidence), 0.20), -0.15)
        confidence = min(0.90, max(trend.confidence, mr.confidence))
        reason = f"trend={trend.reason}; mr={mr.reason}"
        return Signal(symbol, instrument_type, trend.ts, target, confidence, reason, self.name)


class VolatilityAdjustedTrendStrategy(Strategy):
    name = "vol_trend"

    def __init__(self, settings: StrategySettings):
        self.settings = settings

    def generate(self, candles: pd.DataFrame, symbol: str, instrument_type: InstrumentType) -> Signal:
        df = with_indicators(candles, self.settings)
        latest = df.iloc[-1]
        if len(df) < max(self.settings.slow_ema, self.settings.atr_period):
            target = 0.0
            reason = "insufficient history"
            confidence = 0.1
        else:
            trend_strength = (latest["ema_fast"] - latest["ema_slow"]) / latest["close"]
            atr_pct = max(float(latest["atr"]) / float(latest["close"]), 0.005)
            raw = trend_strength / atr_pct
            target = max(min(raw * 0.10, 0.20), -0.15)
            if instrument_type == InstrumentType.SPOT:
                target = max(target, 0.0)
            confidence = min(0.85, 0.35 + abs(target) * 2.5)
            reason = f"volatility-adjusted EMA trend strength={trend_strength:.6f}, atr_pct={atr_pct:.6f}"
        return Signal(symbol, instrument_type, latest["ts"].to_pydatetime(), target, confidence, reason, self.name)


class DonchianBreakoutStrategy(Strategy):
    name = "donchian_breakout"

    def __init__(self, settings: StrategySettings, lookback: int = 55, exit_lookback: int = 20):
        self.settings = settings
        self.lookback = lookback
        self.exit_lookback = exit_lookback

    def generate(self, candles: pd.DataFrame, symbol: str, instrument_type: InstrumentType) -> Signal:
        df = with_indicators(candles, self.settings)
        latest = df.iloc[-1]
        if len(df) <= self.lookback:
            target = 0.0
            reason = "insufficient history"
            confidence = 0.1
        else:
            previous = df.iloc[:-1]
            upper = previous["high"].tail(self.lookback).max()
            lower = previous["low"].tail(self.lookback).min()
            exit_low = previous["low"].tail(self.exit_lookback).min()
            exit_high = previous["high"].tail(self.exit_lookback).max()
            if latest["close"] > upper:
                target = 0.18
                reason = f"close broke {self.lookback}-bar high"
                confidence = 0.70
            elif latest["close"] < lower and instrument_type == InstrumentType.SWAP:
                target = -0.12
                reason = f"close broke {self.lookback}-bar low"
                confidence = 0.65
            elif latest["close"] < exit_low or (instrument_type == InstrumentType.SWAP and latest["close"] > exit_high):
                target = 0.0
                reason = "exit channel hit"
                confidence = 0.45
            else:
                target = 0.0
                reason = "inside Donchian channel"
                confidence = 0.30
        return Signal(symbol, instrument_type, latest["ts"].to_pydatetime(), target, confidence, reason, self.name)


class RsiBollingerReversionStrategy(Strategy):
    name = "rsi_bollinger_reversion"

    def __init__(self, settings: StrategySettings):
        self.inner = MeanReversionStrategy(settings)

    def generate(self, candles: pd.DataFrame, symbol: str, instrument_type: InstrumentType) -> Signal:
        signal = self.inner.generate(candles, symbol, instrument_type)
        return Signal(
            signal.symbol,
            signal.instrument_type,
            signal.ts,
            signal.target_pct,
            signal.confidence,
            signal.reason,
            self.name,
        )


class BtcVolatilityBreakoutStrategy(Strategy):
    name = "btc_volatility_breakout"

    def __init__(self, settings: StrategySettings, range_lookback: int = 72, compression_lookback: int = 120):
        self.settings = settings
        self.range_lookback = range_lookback
        self.compression_lookback = compression_lookback

    def generate(self, candles: pd.DataFrame, symbol: str, instrument_type: InstrumentType) -> Signal:
        df = with_indicators(candles, self.settings)
        latest = df.iloc[-1]
        needed = max(self.range_lookback + 1, self.compression_lookback, self.settings.slow_ema)
        if len(df) <= needed:
            target = 0.0
            reason = "insufficient history"
            confidence = 0.1
        else:
            previous = df.iloc[:-1]
            upper = float(previous["high"].tail(self.range_lookback).max())
            lower = float(previous["low"].tail(self.range_lookback).min())
            atr_pct = max(float(latest["atr"]) / float(latest["close"]), 0.0001)
            recent_vol = float(df["close"].pct_change().tail(self.range_lookback).std() or 0.0)
            baseline_vol = float(df["close"].pct_change().tail(self.compression_lookback).std() or recent_vol or 0.0)
            compressed = recent_vol <= baseline_vol * 1.15 if baseline_vol > 0 else False
            trend_ok = latest["ema_fast"] >= latest["ema_slow"]
            if latest["close"] > upper and compressed and trend_ok:
                target = min(0.20, max(0.08, 0.16 / max(atr_pct / 0.02, 1.0)))
                reason = (
                    f"volatility breakout: close above {self.range_lookback}-bar high; "
                    f"recent_vol={recent_vol:.6f}, baseline_vol={baseline_vol:.6f}, atr_pct={atr_pct:.6f}"
                )
                confidence = 0.68
            elif latest["close"] < lower or latest["ema_fast"] < latest["ema_slow"]:
                target = -0.08 if instrument_type == InstrumentType.SWAP else 0.0
                reason = f"breakout failed or trend turned down; close below channel={latest['close'] < lower}"
                confidence = 0.45
            else:
                target = 0.0
                reason = "no confirmed volatility breakout"
                confidence = 0.30
        return Signal(symbol, instrument_type, latest["ts"].to_pydatetime(), target, confidence, reason, self.name)


class BtcRealizedVolatilityTargetingStrategy(Strategy):
    name = "btc_realized_volatility_targeting"

    def __init__(self, settings: StrategySettings, volatility_bars: int = 24 * 14, target_annual_vol: float = 0.25):
        self.settings = settings
        self.volatility_bars = volatility_bars
        self.target_annual_vol = target_annual_vol

    def generate(self, candles: pd.DataFrame, symbol: str, instrument_type: InstrumentType) -> Signal:
        df = with_indicators(candles, self.settings)
        latest = df.iloc[-1]
        needed = max(self.volatility_bars + 1, self.settings.slow_ema)
        if len(df) <= needed:
            target = 0.0
            reason = "insufficient history"
            confidence = 0.1
        else:
            hourly_returns = df["close"].pct_change().tail(self.volatility_bars)
            annualized_vol = float(hourly_returns.std() * (24 * 365) ** 0.5)
            annualized_vol = max(annualized_vol, 0.05)
            trend_score = (float(latest["ema_fast"]) / float(latest["ema_slow"]) - 1.0) if latest["ema_slow"] else 0.0
            raw_exposure = self.target_annual_vol / annualized_vol
            target = min(raw_exposure * 0.20, 0.25) if trend_score > 0 else 0.0
            if instrument_type == InstrumentType.SWAP and trend_score < -0.01:
                target = -min(raw_exposure * 0.10, 0.12)
            confidence = min(0.80, 0.35 + abs(target) * 2.0)
            reason = (
                f"realized-vol targeting: annualized_vol={annualized_vol:.4f}, "
                f"target_annual_vol={self.target_annual_vol:.4f}, trend_score={trend_score:.6f}"
            )
        return Signal(symbol, instrument_type, latest["ts"].to_pydatetime(), target, confidence, reason, self.name)


def build_strategy(settings: StrategySettings) -> Strategy:
    if settings.name == "trend":
        return TrendStrategy(settings)
    if settings.name in {"mean_reversion", "mr"}:
        return MeanReversionStrategy(settings)
    if settings.name == "trend_mr":
        return TrendMeanReversionStrategy(settings)
    if settings.name == "vol_trend":
        return VolatilityAdjustedTrendStrategy(settings)
    if settings.name == "donchian_breakout":
        return DonchianBreakoutStrategy(settings)
    if settings.name in {"rsi_bollinger_reversion", "bollinger_rsi"}:
        return RsiBollingerReversionStrategy(settings)
    if settings.name in {"btc_volatility_breakout", "volatility_breakout"}:
        return BtcVolatilityBreakoutStrategy(settings)
    if settings.name in {"btc_realized_volatility_targeting", "realized_volatility_targeting", "vol_target"}:
        return BtcRealizedVolatilityTargetingStrategy(settings)
    raise ValueError(f"unknown strategy: {settings.name}")
