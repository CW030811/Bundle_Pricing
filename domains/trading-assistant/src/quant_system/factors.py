from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd

from .config import AppConfig
from .data import filter_confirmed_candles, filter_date_range, load_candles, load_funding_rates
from .reports import market_regime_summary, write_report
from .reproducibility import reproducibility_payload
from .storage import AuditStore


@dataclass(frozen=True)
class FactorSpec:
    id: str
    name: str
    frequency: str = "1H"
    universe: str = "crypto_okx"
    horizons: tuple[int, ...] = (1, 6, 24)
    params: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FactorDataset:
    spec: FactorSpec
    factor_values: pd.DataFrame
    forward_returns: pd.DataFrame
    merged: pd.DataFrame
    metadata: dict[str, Any]


class FactorBuilder:
    spec: FactorSpec
    data_source = "candles"

    def compute(self, panel: pd.DataFrame) -> pd.DataFrame:
        raise NotImplementedError


class CryptoMomentumFactor(FactorBuilder):
    def __init__(self, lookback_bars: int = 24):
        self.lookback_bars = lookback_bars
        self.spec = FactorSpec(
            id=f"crypto_momentum_{lookback_bars}h",
            name=f"Crypto {lookback_bars} bar momentum",
            params={"lookback_bars": lookback_bars},
        )

    def compute(self, panel: pd.DataFrame) -> pd.DataFrame:
        return _close_pct_change(panel, self.lookback_bars)


class CryptoReversalFactor(FactorBuilder):
    def __init__(self, lookback_bars: int = 6):
        self.lookback_bars = lookback_bars
        self.spec = FactorSpec(
            id=f"crypto_reversal_{lookback_bars}h",
            name=f"Crypto {lookback_bars} bar reversal",
            params={"lookback_bars": lookback_bars},
        )

    def compute(self, panel: pd.DataFrame) -> pd.DataFrame:
        out = _close_pct_change(panel, self.lookback_bars)
        out["factor"] = -out["factor"]
        return out


class CryptoVolumePressureFactor(FactorBuilder):
    def __init__(self, lookback_bars: int = 24):
        self.lookback_bars = lookback_bars
        self.spec = FactorSpec(
            id="crypto_volume_pressure",
            name="Crypto volume pressure z-score",
            params={"lookback_bars": lookback_bars},
        )

    def compute(self, panel: pd.DataFrame) -> pd.DataFrame:
        out = _standard_panel(panel)
        grouped = out.groupby("symbol", group_keys=False)["volume"]
        mean = grouped.transform(lambda item: item.astype(float).rolling(self.lookback_bars).mean())
        std = grouped.transform(lambda item: item.astype(float).rolling(self.lookback_bars).std())
        std = std.mask(std == 0)
        out["factor"] = (out["volume"].astype(float) - mean) / std
        return out[["ts", "symbol", "factor"]].dropna(subset=["factor"]).reset_index(drop=True)


class CrossSectionalMomentumFactor(CryptoMomentumFactor):
    def __init__(self, lookback_bars: int = 24 * 30):
        super().__init__(lookback_bars)
        self.spec = FactorSpec(
            id="cross_sectional_momentum_720h",
            name="Cross-sectional crypto momentum 720h",
            params={"lookback_bars": lookback_bars, "migrated_strategy": "crypto_cross_sectional_momentum"},
        )


class AdaptiveTrendQualityFactor(FactorBuilder):
    def __init__(self, return_bars: int = 24 * 30, volatility_bars: int = 24 * 14, ema_span: int = 24 * 20):
        self.return_bars = return_bars
        self.volatility_bars = volatility_bars
        self.ema_span = ema_span
        self.spec = FactorSpec(
            id="adaptive_trend_quality",
            name="Adaptive trend quality",
            params={
                "return_bars": return_bars,
                "volatility_bars": volatility_bars,
                "ema_span": ema_span,
                "migrated_strategy": "adaptive_trend_portfolio",
            },
        )

    def compute(self, panel: pd.DataFrame) -> pd.DataFrame:
        out = _standard_panel(panel)
        grouped = out.groupby("symbol", group_keys=False)
        returns = grouped["close"].pct_change(self.return_bars)
        volatility = grouped["close"].pct_change().transform(
            lambda item: item.astype(float).rolling(self.volatility_bars).std()
        )
        ema = grouped["close"].transform(lambda item: item.astype(float).ewm(span=self.ema_span, adjust=False).mean())
        trend_filter = (out["close"].astype(float) / ema - 1.0).clip(lower=0.0)
        out["factor"] = (returns / volatility.mask(volatility == 0)) * trend_filter
        return out[["ts", "symbol", "factor"]].dropna(subset=["factor"]).reset_index(drop=True)


class FundingCarryFactor(FactorBuilder):
    data_source = "funding"

    def __init__(self, lookback_periods: int = 3):
        self.lookback_periods = lookback_periods
        self.spec = FactorSpec(
            id="funding_carry_recent",
            name="Recent funding carry",
            frequency="8H",
            params={"lookback_periods": lookback_periods, "migrated_strategy": "funding_rate_carry_btc_perp"},
        )

    def compute(self, panel: pd.DataFrame) -> pd.DataFrame:
        out = _standard_funding_panel(panel)
        out["factor"] = out.groupby("symbol", group_keys=False)["funding_rate"].transform(
            lambda item: item.astype(float).rolling(self.lookback_periods).mean()
        )
        return out[["ts", "symbol", "factor"]].dropna(subset=["factor"]).reset_index(drop=True)


class BtcTimeSeriesMomentumFactor(CryptoMomentumFactor):
    def __init__(self, lookback_bars: int = 24 * 14):
        super().__init__(lookback_bars)
        self.spec = FactorSpec(
            id="btc_time_series_momentum_336h",
            name="BTC time-series momentum 336h",
            params={"lookback_bars": lookback_bars, "migrated_strategy": "btc_time_series_momentum"},
        )


class VolatilityAdjustedBtcTrendFactor(FactorBuilder):
    def __init__(self, lookback_bars: int = 24 * 14, volatility_bars: int = 24 * 14):
        self.lookback_bars = lookback_bars
        self.volatility_bars = volatility_bars
        self.spec = FactorSpec(
            id="volatility_adjusted_btc_trend",
            name="Volatility-adjusted BTC trend",
            params={
                "lookback_bars": lookback_bars,
                "volatility_bars": volatility_bars,
                "migrated_strategy": "volatility_adjusted_btc_trend",
            },
        )

    def compute(self, panel: pd.DataFrame) -> pd.DataFrame:
        out = _standard_panel(panel)
        grouped = out.groupby("symbol", group_keys=False)
        momentum = grouped["close"].pct_change(self.lookback_bars)
        realized_vol = grouped["close"].pct_change().transform(
            lambda item: item.astype(float).rolling(self.volatility_bars).std()
        )
        out["factor"] = momentum / realized_vol.mask(realized_vol == 0)
        return out[["ts", "symbol", "factor"]].dropna(subset=["factor"]).reset_index(drop=True)


class AltcoinBtcResidualReversionFactor(FactorBuilder):
    def __init__(self, lookback_bars: int = 24 * 14, beta_window: int = 24 * 30, btc_symbol: str = "BTC/USDT"):
        self.lookback_bars = lookback_bars
        self.beta_window = beta_window
        self.btc_symbol = btc_symbol
        self.spec = FactorSpec(
            id="altcoin_btc_residual_reversion",
            name="Altcoin BTC residual reversion",
            params={
                "lookback_bars": lookback_bars,
                "beta_window": beta_window,
                "btc_symbol": btc_symbol,
                "migrated_strategy": "altcoin_btc_arbitrage_factor_reversion",
            },
        )

    def compute(self, panel: pd.DataFrame) -> pd.DataFrame:
        out = _standard_panel(panel)
        closes = out.pivot(index="ts", columns="symbol", values="close").sort_index()
        if self.btc_symbol not in closes:
            return pd.DataFrame(columns=["ts", "symbol", "factor"])
        btc_returns = closes[self.btc_symbol].pct_change()
        rows: list[dict[str, object]] = []
        for symbol in closes.columns:
            if symbol == self.btc_symbol:
                continue
            asset_returns = closes[symbol].pct_change()
            covariance = asset_returns.rolling(self.beta_window).cov(btc_returns)
            variance = btc_returns.rolling(self.beta_window).var()
            beta = covariance / variance.mask(variance == 0)
            residual = asset_returns - beta * btc_returns
            residual_return = residual.rolling(self.lookback_bars).sum()
            factor = -residual_return
            for ts, value in factor.dropna().items():
                rows.append({"ts": ts, "symbol": symbol, "factor": float(value)})
        return pd.DataFrame(rows).sort_values(["symbol", "ts"]).reset_index(drop=True) if rows else pd.DataFrame(columns=["ts", "symbol", "factor"])


def available_factors() -> dict[str, FactorBuilder]:
    builders = [
        CryptoMomentumFactor(24),
        CryptoReversalFactor(6),
        CryptoVolumePressureFactor(24),
        CrossSectionalMomentumFactor(),
        AdaptiveTrendQualityFactor(),
        FundingCarryFactor(),
        BtcTimeSeriesMomentumFactor(),
        VolatilityAdjustedBtcTrendFactor(),
        AltcoinBtcResidualReversionFactor(),
    ]
    return {builder.spec.id: builder for builder in builders}


def build_factor(factor_id: str) -> FactorBuilder:
    registry = available_factors()
    if factor_id not in registry:
        raise ValueError(f"unknown factor '{factor_id}'. Available factors: {', '.join(sorted(registry))}")
    return registry[factor_id]


def load_crypto_panel(
    config: AppConfig,
    symbols: Iterable[str],
    instrument_type: str,
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for symbol in symbols:
        candles = load_candles(config, symbol, instrument_type)
        candles = filter_confirmed_candles(candles, require_confirmed=True)
        candles = filter_date_range(candles, start, end)
        if not candles.empty:
            frames.append(candles)
    if not frames:
        return pd.DataFrame()
    return _standard_panel(pd.concat(frames, ignore_index=True))


def load_funding_panel(
    config: AppConfig,
    symbols: Iterable[str],
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for symbol in symbols:
        funding = load_funding_rates(config, symbol)
        funding = filter_date_range(funding, start, end)
        if not funding.empty:
            frames.append(funding)
    if not frames:
        return pd.DataFrame()
    return _standard_funding_panel(pd.concat(frames, ignore_index=True))


def build_factor_dataset(
    builder: FactorBuilder,
    panel: pd.DataFrame,
    horizons: Iterable[int],
    min_symbols: int = 3,
) -> FactorDataset:
    horizon_values = tuple(sorted({int(value) for value in horizons if int(value) > 0}))
    if not horizon_values:
        raise ValueError("at least one positive horizon is required")
    factor_values = builder.compute(panel)
    forward_returns = compute_forward_returns(panel, horizon_values)
    merged = factor_values.merge(forward_returns, on=["ts", "symbol"], how="left")
    metadata = {
        "symbols": sorted(panel["symbol"].dropna().astype(str).unique().tolist()) if not panel.empty else [],
        "row_count": int(len(panel)),
        "factor_row_count": int(len(factor_values)),
        "merged_row_count": int(len(merged)),
        "min_symbols": int(min_symbols),
        "date_range": _date_range(panel),
    }
    spec = FactorSpec(
        id=builder.spec.id,
        name=builder.spec.name,
        frequency=builder.spec.frequency,
        universe=builder.spec.universe,
        horizons=horizon_values,
        params=builder.spec.params,
    )
    return FactorDataset(spec, factor_values, forward_returns, merged, metadata)


def compute_forward_returns(panel: pd.DataFrame, horizons: Iterable[int]) -> pd.DataFrame:
    if "funding_rate" in panel.columns:
        return compute_forward_funding(panel, horizons)
    out = _standard_return_panel(panel)
    result = out[["ts", "symbol"]].copy()
    grouped = out.groupby("symbol", group_keys=False)["close"]
    for horizon in horizons:
        close = out["close"].astype(float)
        future = grouped.shift(-int(horizon))
        result[f"forward_return_{int(horizon)}"] = future.astype(float) / close - 1.0
    return result


def compute_forward_funding(panel: pd.DataFrame, horizons: Iterable[int]) -> pd.DataFrame:
    out = _standard_funding_panel(panel)
    result = out[["ts", "symbol"]].copy()
    grouped = out.groupby("symbol", group_keys=False)["funding_rate"]
    for horizon in horizons:
        result[f"forward_return_{int(horizon)}"] = grouped.transform(
            lambda item: item.astype(float).shift(-1).iloc[::-1].rolling(int(horizon)).sum().iloc[::-1]
        )
    return result


class FactorEvaluator:
    def __init__(self, quantiles: int = 5, min_symbols: int = 3):
        if quantiles < 2:
            raise ValueError("quantiles must be at least 2")
        self.quantiles = int(quantiles)
        self.min_symbols = int(min_symbols)

    def evaluate(self, dataset: FactorDataset) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "factor_id": dataset.spec.id,
            "factor_name": dataset.spec.name,
            "frequency": dataset.spec.frequency,
            "universe": dataset.spec.universe,
            "params": dict(dataset.spec.params),
            "horizons": list(dataset.spec.horizons),
            "quantiles": self.quantiles,
            "min_symbols": self.min_symbols,
            "metadata": dataset.metadata,
            "coverage": self.coverage(dataset),
            "ic_summary": {},
            "quantile_returns": {},
            "turnover": {},
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        for horizon in dataset.spec.horizons:
            column = f"forward_return_{horizon}"
            payload["ic_summary"][str(horizon)] = self.ic_summary(dataset.merged, column)
            payload["quantile_returns"][str(horizon)] = self.quantile_returns(dataset.merged, column)
            payload["turnover"][str(horizon)] = self.turnover(dataset.merged, column)
        payload["status"] = self.status(payload)
        payload["recommendation"] = self.recommendation(payload)
        return payload

    def coverage(self, dataset: FactorDataset) -> dict[str, Any]:
        panel_rows = int(dataset.metadata.get("row_count", 0))
        factor_rows = int(dataset.metadata.get("factor_row_count", 0))
        merged = dataset.merged
        valid_factor_rows = int(merged["factor"].notna().sum()) if "factor" in merged else 0
        per_ts = merged.dropna(subset=["factor"]).groupby("ts")["symbol"].nunique() if not merged.empty else pd.Series(dtype=int)
        valid_cross_sections = int((per_ts >= self.min_symbols).sum()) if not per_ts.empty else 0
        return {
            "panel_rows": panel_rows,
            "factor_rows": factor_rows,
            "valid_factor_rows": valid_factor_rows,
            "factor_coverage": float(valid_factor_rows / panel_rows) if panel_rows else 0.0,
            "missing_rate": float(1.0 - valid_factor_rows / panel_rows) if panel_rows else 1.0,
            "valid_cross_sections": valid_cross_sections,
            "total_cross_sections": int(per_ts.count()) if not per_ts.empty else 0,
        }

    def ic_summary(self, merged: pd.DataFrame, return_column: str) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        for ts, group in merged.dropna(subset=["factor", return_column]).groupby("ts"):
            if group["symbol"].nunique() < self.min_symbols:
                continue
            if group["factor"].nunique() < 2 or group[return_column].nunique() < 2:
                continue
            factor = group["factor"].astype(float)
            forward_return = group[return_column].astype(float)
            ic = factor.corr(forward_return, method="pearson")
            rank_ic = factor.rank(method="average").corr(forward_return.rank(method="average"), method="pearson")
            if pd.notna(ic) and pd.notna(rank_ic):
                rows.append({"ts": ts, "ic": float(ic), "rank_ic": float(rank_ic), "n": int(len(group))})
        if not rows:
            return _empty_ic_summary()
        frame = pd.DataFrame(rows)
        return {
            "observations": int(len(frame)),
            "mean_ic": float(frame["ic"].mean()),
            "mean_rank_ic": float(frame["rank_ic"].mean()),
            "ic_std": float(frame["ic"].std(ddof=0)),
            "rank_ic_std": float(frame["rank_ic"].std(ddof=0)),
            "icir": _ratio(frame["ic"].mean(), frame["ic"].std(ddof=0)),
            "rank_icir": _ratio(frame["rank_ic"].mean(), frame["rank_ic"].std(ddof=0)),
            "positive_ic_rate": float((frame["ic"] > 0).mean()),
            "positive_rank_ic_rate": float((frame["rank_ic"] > 0).mean()),
            "average_symbols": float(frame["n"].mean()),
        }

    def quantile_returns(self, merged: pd.DataFrame, return_column: str) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        for ts, group in merged.dropna(subset=["factor", return_column]).groupby("ts"):
            if group["symbol"].nunique() < self.min_symbols or group["factor"].nunique() < 2:
                continue
            assigned = _assign_quantiles(group, self.quantiles)
            if assigned.empty:
                continue
            for quantile, q_group in assigned.groupby("quantile"):
                rows.append(
                    {
                        "ts": ts,
                        "quantile": int(quantile),
                        "return": float(q_group[return_column].astype(float).mean()),
                        "count": int(len(q_group)),
                    }
                )
        if not rows:
            return {"observations": 0, "by_quantile": {}, "top_bottom_mean": 0.0, "top_bottom_positive_rate": 0.0}
        frame = pd.DataFrame(rows)
        by_quantile: dict[str, dict[str, Any]] = {}
        for quantile, q_group in frame.groupby("quantile"):
            by_quantile[str(int(quantile))] = {
                "mean_return": float(q_group["return"].mean()),
                "positive_rate": float((q_group["return"] > 0).mean()),
                "average_count": float(q_group["count"].mean()),
            }
        spread_rows = []
        for ts, ts_group in frame.groupby("ts"):
            values = ts_group.set_index("quantile")["return"]
            bottom = int(values.index.min())
            top = int(values.index.max())
            if bottom != top:
                spread_rows.append(float(values[top] - values[bottom]))
        return {
            "observations": int(frame["ts"].nunique()),
            "by_quantile": by_quantile,
            "top_bottom_mean": float(pd.Series(spread_rows).mean()) if spread_rows else 0.0,
            "top_bottom_positive_rate": float((pd.Series(spread_rows) > 0).mean()) if spread_rows else 0.0,
        }

    def turnover(self, merged: pd.DataFrame, return_column: str) -> dict[str, Any]:
        top_sets: list[set[str]] = []
        for _, group in merged.dropna(subset=["factor", return_column]).groupby("ts"):
            if group["symbol"].nunique() < self.min_symbols or group["factor"].nunique() < 2:
                continue
            assigned = _assign_quantiles(group, self.quantiles)
            top_quantile = int(assigned["quantile"].max())
            top_symbols = set(assigned.loc[assigned["quantile"] == top_quantile, "symbol"].astype(str))
            if top_symbols:
                top_sets.append(top_symbols)
        if len(top_sets) < 2:
            return {"observations": len(top_sets), "top_quantile_turnover_mean": 0.0}
        turnovers = []
        previous = top_sets[0]
        for current in top_sets[1:]:
            turnovers.append(1.0 - len(previous & current) / max(len(previous), 1))
            previous = current
        return {
            "observations": len(top_sets),
            "top_quantile_turnover_mean": float(pd.Series(turnovers).mean()) if turnovers else 0.0,
        }

    def status(self, payload: Mapping[str, Any]) -> str:
        coverage = payload.get("coverage", {})
        if int(coverage.get("valid_cross_sections", 0)) == 0:
            return "insufficient_cross_section"
        if not any(int(item.get("observations", 0)) > 0 for item in payload.get("ic_summary", {}).values()):
            return "insufficient_forward_returns"
        return "ok"

    def recommendation(self, payload: Mapping[str, Any]) -> str:
        if payload.get("status") != "ok":
            return "Collect a wider crypto universe or longer candle history before using this factor."
        rank_ics = [
            float(item.get("mean_rank_ic", 0.0))
            for item in payload.get("ic_summary", {}).values()
            if int(item.get("observations", 0)) > 0
        ]
        best_abs = max((abs(value) for value in rank_ics), default=0.0)
        if best_abs >= 0.03:
            return "Promising research signal; validate with walk-forward factor stability and tradable portfolio costs."
        return "Weak standalone factor evidence; keep as research input only."


def run_factor_evaluation(
    config: AppConfig,
    factor_id: str,
    symbols: Iterable[str],
    instrument_type: str = "spot",
    horizons: Iterable[int] = (1, 6, 24),
    quantiles: int = 5,
    min_symbols: int = 3,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    symbol_list = list(symbols)
    builder = build_factor(factor_id)
    if builder.data_source == "funding":
        panel = load_funding_panel(config, symbol_list, start=start, end=end)
    else:
        panel = load_crypto_panel(config, symbol_list, instrument_type, start=start, end=end)
    if panel.empty:
        return {
            "factor_id": factor_id,
            "status": "missing_data",
            "symbols": symbol_list,
            "instrument_type": instrument_type,
            "horizons": list(horizons),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "recommendation": "Backfill confirmed candles before evaluating this factor.",
        }
    dataset = build_factor_dataset(builder, panel, horizons, min_symbols=min_symbols)
    payload = FactorEvaluator(quantiles=quantiles, min_symbols=min_symbols).evaluate(dataset)
    payload["symbols"] = symbol_list
    payload["instrument_type"] = instrument_type
    if builder.data_source != "funding":
        payload["market_regime"] = market_regime_summary(panel)
    return payload


def run_factor_evaluation_report(
    config: AppConfig,
    factor_id: str,
    symbols: Iterable[str],
    instrument_type: str = "spot",
    horizons: Iterable[int] = (1, 6, 24),
    quantiles: int = 5,
    min_symbols: int = 3,
    start: str | None = None,
    end: str | None = None,
) -> Path:
    symbol_list = list(symbols)
    payload = run_factor_evaluation(
        config,
        factor_id,
        symbol_list,
        instrument_type=instrument_type,
        horizons=horizons,
        quantiles=quantiles,
        min_symbols=min_symbols,
        start=start,
        end=end,
    )
    audit = AuditStore(config.state_dir)
    builder = build_factor(factor_id)
    source_table = "dwd_crypto_funding_rate" if builder.data_source == "funding" else "dwd_crypto_ohlcv"
    audit.upsert_factor_registry(
        factor_name=factor_id,
        factor_category="funding" if builder.data_source == "funding" else "price",
        version="v1",
        description=builder.spec.name,
        formula=builder.spec.name,
        parameters=dict(builder.spec.params),
        source_tables=[source_table],
        target_table="dws_crypto_factor_funding" if builder.data_source == "funding" else "dws_crypto_factor_price",
        is_active=True,
    )
    metadata = payload.get("metadata", {}) if isinstance(payload.get("metadata"), dict) else {}
    date_range = metadata.get("date_range", {}) if isinstance(metadata.get("date_range"), dict) else {}
    audit.insert_factor_calculation_log(
        {
            "factor_name": factor_id,
            "source_table": source_table,
            "target_table": "dws_crypto_factor_funding"
            if builder.data_source == "funding"
            else "dws_crypto_factor_price",
            "symbol": ",".join(symbol_list),
            "interval": builder.spec.frequency,
            "start_time": date_range.get("start"),
            "end_time": date_range.get("end"),
            "parameters": dict(builder.spec.params),
            "status": payload.get("status", "unknown"),
            "records_calculated": metadata.get("factor_row_count", 0),
            "error_message": None if payload.get("status") == "ok" else payload.get("recommendation"),
        }
    )
    factor_values = _factor_values_for_report(
        config,
        builder,
        symbol_list,
        instrument_type,
        horizons,
        min_symbols,
        start,
        end,
    )
    materialized_count = audit.upsert_factor_values(
        factor_id=factor_id,
        version="v1",
        exchange="okx",
        market_type="swap" if builder.data_source == "funding" else instrument_type,
        interval=builder.spec.frequency,
        factor_values=factor_values,
        parameters=dict(builder.spec.params),
    )
    payload["dws_materialized"] = {
        "table": "dws_crypto_factor_values",
        "row_count": materialized_count,
        "version": "v1",
    }
    payload["reproducibility"] = reproducibility_payload(
        config,
        artifact_type="factor_evaluation",
        artifact_name=factor_id,
        data_version="v1",
        factor_version="v1",
        parameters={
            "factor_id": factor_id,
            "symbols": symbol_list,
            "instrument_type": instrument_type,
            "horizons": list(horizons),
            "quantiles": quantiles,
            "min_symbols": min_symbols,
            "start": start,
            "end": end,
        },
    )
    path = write_report(config.report_dir, f"factor_{factor_id}", payload)
    audit.insert_reproducibility_record(payload["reproducibility"], artifact_path=path)
    return path


def _factor_values_for_report(
    config: AppConfig,
    builder: FactorBuilder,
    symbols: list[str],
    instrument_type: str,
    horizons: Iterable[int],
    min_symbols: int,
    start: str | None,
    end: str | None,
) -> pd.DataFrame:
    if builder.data_source == "funding":
        panel = load_funding_panel(config, symbols, start=start, end=end)
    else:
        panel = load_crypto_panel(config, symbols, instrument_type, start=start, end=end)
    if panel.empty:
        return pd.DataFrame(columns=["ts", "symbol", "factor"])
    return build_factor_dataset(builder, panel, horizons, min_symbols=min_symbols).factor_values


def _standard_panel(panel: pd.DataFrame) -> pd.DataFrame:
    if panel.empty:
        return panel.copy()
    required = {"ts", "symbol", "close"}
    missing = required - set(panel.columns)
    if missing:
        raise ValueError(f"panel missing required columns: {', '.join(sorted(missing))}")
    out = panel.copy()
    out["ts"] = pd.to_datetime(out["ts"], utc=True, errors="coerce")
    out["symbol"] = out["symbol"].astype(str)
    out["close"] = pd.to_numeric(out["close"], errors="coerce")
    if "volume" not in out:
        out["volume"] = 0.0
    out["volume"] = pd.to_numeric(out["volume"], errors="coerce")
    return out.dropna(subset=["ts", "symbol", "close"]).sort_values(["symbol", "ts"]).reset_index(drop=True)


def _standard_funding_panel(panel: pd.DataFrame) -> pd.DataFrame:
    if panel.empty:
        return panel.copy()
    required = {"ts", "symbol", "funding_rate"}
    missing = required - set(panel.columns)
    if missing:
        raise ValueError(f"funding panel missing required columns: {', '.join(sorted(missing))}")
    out = panel.copy()
    out["ts"] = pd.to_datetime(out["ts"], utc=True, errors="coerce")
    out["symbol"] = out["symbol"].astype(str)
    out["funding_rate"] = pd.to_numeric(out["funding_rate"], errors="coerce")
    out["close"] = out["funding_rate"]
    return out.dropna(subset=["ts", "symbol", "funding_rate"]).sort_values(["symbol", "ts"]).reset_index(drop=True)


def _standard_return_panel(panel: pd.DataFrame) -> pd.DataFrame:
    if "close" in panel.columns:
        return _standard_panel(panel)
    if "funding_rate" in panel.columns:
        return _standard_funding_panel(panel)
    return _standard_panel(panel)


def _close_pct_change(panel: pd.DataFrame, lookback_bars: int) -> pd.DataFrame:
    out = _standard_panel(panel)
    out["factor"] = out.groupby("symbol", group_keys=False)["close"].pct_change(lookback_bars)
    return out[["ts", "symbol", "factor"]].dropna(subset=["factor"]).reset_index(drop=True)


def _date_range(panel: pd.DataFrame) -> dict[str, str | None]:
    if panel.empty or "ts" not in panel:
        return {"start": None, "end": None}
    ts = pd.to_datetime(panel["ts"], utc=True, errors="coerce").dropna()
    if ts.empty:
        return {"start": None, "end": None}
    return {"start": ts.min().isoformat(), "end": ts.max().isoformat()}


def _ratio(numerator: float, denominator: float) -> float:
    if not denominator or pd.isna(denominator):
        return 0.0
    return float(numerator / denominator)


def _empty_ic_summary() -> dict[str, Any]:
    return {
        "observations": 0,
        "mean_ic": 0.0,
        "mean_rank_ic": 0.0,
        "ic_std": 0.0,
        "rank_ic_std": 0.0,
        "icir": 0.0,
        "rank_icir": 0.0,
        "positive_ic_rate": 0.0,
        "positive_rank_ic_rate": 0.0,
        "average_symbols": 0.0,
    }


def _assign_quantiles(group: pd.DataFrame, quantiles: int) -> pd.DataFrame:
    ranked = group.copy()
    if len(ranked) < quantiles:
        labels = pd.qcut(ranked["factor"].rank(method="first"), q=len(ranked), labels=False, duplicates="drop")
        ranked["quantile"] = labels.astype(int) + 1
        ranked["quantile"] = ranked["quantile"].clip(upper=quantiles)
        return ranked
    try:
        ranked["quantile"] = pd.qcut(
            ranked["factor"].rank(method="first"),
            q=quantiles,
            labels=False,
            duplicates="drop",
        ).astype(int) + 1
    except ValueError:
        return pd.DataFrame()
    return ranked.dropna(subset=["quantile"])
