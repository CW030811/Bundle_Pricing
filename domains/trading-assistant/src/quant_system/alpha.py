from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd
import yaml

from .config import AppConfig
from .data import filter_date_range
from .factors import build_factor, load_crypto_panel, load_funding_panel
from .reports import periods_per_year, write_report
from .reproducibility import reproducibility_payload
from .storage import AuditStore


SUPPORTED_TRANSFORMS = {"ma_diff", "z_score", "minmax", "robust_scaling", "box_cox", "rate_of_change"}
SUPPORTED_STYLES = {"momentum", "reversion"}
SUPPORTED_POSITION_TYPES = {"long_only", "short_only", "long_short", "binary_LS", "binary_SL"}


@dataclass(frozen=True)
class AlphaTransformSpec:
    model: str
    window: int
    threshold: float
    style: str = "momentum"
    position_type: str = "long_short"
    name: str | None = None

    @property
    def strategy_id(self) -> str:
        if self.name:
            return self.name
        threshold = str(self.threshold).replace(".", "p").replace("-", "neg")
        return f"{self.model}_{self.style}_{self.position_type}_w{self.window}_t{threshold}"


@dataclass(frozen=True)
class AlphaGroupSpec:
    group: str
    factor: str
    weight: float
    transforms: tuple[AlphaTransformSpec, ...]


@dataclass(frozen=True)
class ExternalFactorSpec:
    factor_id: str
    path: Path
    frequency: str = "1H"
    description: str = "External alpha factor"


@dataclass(frozen=True)
class AlphaEnsembleSpec:
    name: str
    version: str
    symbols: tuple[str, ...]
    instrument_type: str
    horizon_bars: int
    min_symbols: int
    groups: tuple[AlphaGroupSpec, ...]
    external_factors: tuple[ExternalFactorSpec, ...]


def load_alpha_ensemble_spec(path: str | Path, config: AppConfig) -> AlphaEnsembleSpec:
    spec_path = Path(path)
    raw = yaml.safe_load(spec_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError("alpha ensemble spec must be a YAML mapping")

    symbols = tuple(str(item) for item in raw.get("symbols", config.market.symbols))
    groups = tuple(_parse_group(item) for item in raw.get("groups", []))
    external = tuple(_parse_external_factor(item, spec_path.parent, config) for item in raw.get("external_factors", []))
    if not groups:
        raise ValueError("alpha ensemble spec requires at least one group")
    if not symbols:
        raise ValueError("alpha ensemble spec requires at least one symbol")
    return AlphaEnsembleSpec(
        name=str(raw.get("name") or "alpha_ensemble"),
        version=str(raw.get("version") or "v1"),
        symbols=symbols,
        instrument_type=str(raw.get("instrument_type") or "spot"),
        horizon_bars=int(raw.get("horizon_bars") or 1),
        min_symbols=int(raw.get("min_symbols") or 1),
        groups=groups,
        external_factors=external,
    )


def apply_factor_transform(
    factor_values: pd.DataFrame,
    *,
    model: str,
    window: int,
    threshold: float,
    style: str = "momentum",
    position_type: str = "long_short",
) -> pd.DataFrame:
    if model not in SUPPORTED_TRANSFORMS:
        raise ValueError(f"unsupported transform model '{model}'")
    if style not in SUPPORTED_STYLES:
        raise ValueError(f"unsupported transform style '{style}'")
    if position_type not in SUPPORTED_POSITION_TYPES:
        raise ValueError(f"unsupported position_type '{position_type}'")
    if int(window) <= 0:
        raise ValueError("window must be positive")

    frame = _standard_factor_values(factor_values)
    if frame.empty:
        return pd.DataFrame(columns=["ts", "symbol", "signal"])
    parts = []
    for symbol, group in frame.groupby("symbol", sort=False):
        transformed = _apply_single_symbol_transform(
            group.sort_values("ts").reset_index(drop=True),
            model=model,
            window=int(window),
            threshold=float(threshold),
            style=style,
            position_type=position_type,
        )
        transformed["symbol"] = symbol
        parts.append(transformed[["ts", "symbol", "signal"]])
    if not parts:
        return pd.DataFrame(columns=["ts", "symbol", "signal"])
    return pd.concat(parts, ignore_index=True).dropna(subset=["signal"]).sort_values(["symbol", "ts"]).reset_index(drop=True)


def run_alpha_ensemble(
    config: AppConfig,
    spec_path: str | Path,
    *,
    symbols: Iterable[str] | None = None,
    instrument_type: str | None = None,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    spec = load_alpha_ensemble_spec(spec_path, config)
    symbol_list = list(symbols or spec.symbols)
    market_type = instrument_type or spec.instrument_type
    price_panel = load_crypto_panel(config, symbol_list, market_type, start=start, end=end)
    external_values = _load_external_factors(spec.external_factors, symbols=symbol_list, start=start, end=end)
    builtin_values = _load_builtin_factors(config, spec, symbol_list, market_type, start=start, end=end)
    factor_values_by_id = {**builtin_values, **external_values}

    if price_panel.empty:
        return {
            "schema": "alpha_ensemble_report_v1",
            "name": spec.name,
            "status": "missing_data",
            "promotion_status": "research_only",
            "symbols": symbol_list,
            "instrument_type": market_type,
            "skipped": [{"reason": "missing confirmed candle panel"}],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    forward_returns = _forward_trade_returns(price_panel, spec.horizon_bars)
    candidates: list[dict[str, Any]] = []
    group_signals: dict[str, pd.DataFrame] = {}
    skipped: list[dict[str, Any]] = []

    for group in spec.groups:
        base_values = factor_values_by_id.get(group.factor)
        if base_values is None or base_values.empty:
            skipped.append({"group": group.group, "factor": group.factor, "reason": "missing factor values"})
            continue
        transformed_frames = []
        for transform in group.transforms:
            try:
                signal = apply_factor_transform(
                    base_values,
                    model=transform.model,
                    window=transform.window,
                    threshold=transform.threshold,
                    style=transform.style,
                    position_type=transform.position_type,
                )
            except ValueError as exc:
                skipped.append(
                    {
                        "group": group.group,
                        "factor": group.factor,
                        "strategy": transform.strategy_id,
                        "reason": str(exc),
                    }
                )
                continue
            if signal.empty:
                skipped.append(
                    {
                        "group": group.group,
                        "factor": group.factor,
                        "strategy": transform.strategy_id,
                        "reason": "transform produced no signal rows",
                    }
                )
                continue
            signal = signal.rename(columns={"signal": transform.strategy_id})
            transformed_frames.append(signal)
            metrics = _signal_metrics(
                signal.rename(columns={transform.strategy_id: "signal"}),
                forward_returns,
                config=config,
                horizon_bars=spec.horizon_bars,
            )
            candidates.append(
                {
                    "group": group.group,
                    "factor": group.factor,
                    "strategy": transform.strategy_id,
                    "model": transform.model,
                    "style": transform.style,
                    "position_type": transform.position_type,
                    "window": transform.window,
                    "threshold": transform.threshold,
                    "metrics": metrics,
                }
            )
        if transformed_frames:
            group_signal = _mean_signal(transformed_frames, output_column="signal")
            group_signals[group.group] = group_signal

    group_rows = []
    for group in spec.groups:
        signal = group_signals.get(group.group)
        if signal is None or signal.empty:
            continue
        group_rows.append(
            {
                "group": group.group,
                "factor": group.factor,
                "weight": float(group.weight),
                "metrics": _signal_metrics(signal, forward_returns, config=config, horizon_bars=spec.horizon_bars),
            }
        )

    ensemble_signal = _weighted_group_signal(spec.groups, group_signals)
    ensemble_metrics = _signal_metrics(ensemble_signal, forward_returns, config=config, horizon_bars=spec.horizon_bars)
    status = "ok" if not ensemble_signal.empty and ensemble_metrics["observations"] > 0 else "insufficient_signals"

    return {
        "schema": "alpha_ensemble_report_v1",
        "name": spec.name,
        "version": spec.version,
        "status": status,
        "promotion_status": "research_only",
        "recommendation": "Keep research-only until walk-forward, cost sensitivity, paper stability, and operator gates pass.",
        "symbols": symbol_list,
        "instrument_type": market_type,
        "horizon_bars": spec.horizon_bars,
        "min_symbols": spec.min_symbols,
        "groups": group_rows,
        "candidates": candidates,
        "ensemble": {
            "metrics": ensemble_metrics,
            "signal_row_count": int(len(ensemble_signal)),
            "weight_policy": "explicit group weights normalized across available groups per timestamp and symbol",
        },
        "skipped": skipped,
        "external_factors": [
            {
                "factor_id": item.factor_id,
                "path": str(item.path),
                "frequency": item.frequency,
                "row_count": int(len(external_values.get(item.factor_id, pd.DataFrame()))),
            }
            for item in spec.external_factors
        ],
        "parameter_stability": _parameter_stability(candidates),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "_ensemble_signal": ensemble_signal,
        "_external_factor_values": external_values,
    }


def run_alpha_ensemble_report(
    config: AppConfig,
    spec_path: str | Path,
    *,
    symbols: Iterable[str] | None = None,
    instrument_type: str | None = None,
    start: str | None = None,
    end: str | None = None,
) -> Path:
    payload = run_alpha_ensemble(
        config,
        spec_path,
        symbols=symbols,
        instrument_type=instrument_type,
        start=start,
        end=end,
    )
    spec = load_alpha_ensemble_spec(spec_path, config)
    audit = AuditStore(config.state_dir)
    external_values = payload.pop("_external_factor_values", {})
    ensemble_signal = payload.pop("_ensemble_signal", pd.DataFrame())

    for external in spec.external_factors:
        values = external_values.get(external.factor_id, pd.DataFrame(columns=["ts", "symbol", "factor"]))
        audit.upsert_factor_registry(
            factor_name=external.factor_id,
            factor_category="external_alpha",
            version=spec.version,
            description=external.description,
            formula="external CSV with columns ts,symbol,factor",
            parameters={"path": str(external.path), "frequency": external.frequency},
            source_tables=[str(external.path)],
            target_table="dws_crypto_factor_values",
            is_active=True,
        )
        audit.insert_factor_calculation_log(
            {
                "factor_name": external.factor_id,
                "source_table": str(external.path),
                "target_table": "dws_crypto_factor_values",
                "symbol": ",".join(sorted(values["symbol"].astype(str).unique())) if not values.empty else None,
                "interval": external.frequency,
                "start_time": _first_ts(values),
                "end_time": _last_ts(values),
                "parameters": {"path": str(external.path), "frequency": external.frequency},
                "status": "ok" if not values.empty else "missing_data",
                "records_calculated": len(values),
                "error_message": None if not values.empty else "external factor file produced no valid rows",
            }
        )
        audit.upsert_factor_values(
            factor_id=external.factor_id,
            version=spec.version,
            exchange="external",
            market_type=instrument_type or spec.instrument_type,
            interval=external.frequency,
            factor_values=values,
            parameters={"path": str(external.path), "frequency": external.frequency},
        )

    signal_factor_id = f"{spec.name}_signal"
    audit.upsert_factor_registry(
        factor_name=signal_factor_id,
        factor_category="alpha_ensemble_signal",
        version=spec.version,
        description=f"Alpha ensemble research signal for {spec.name}",
        formula="weighted group ensemble of factor transform signals",
        parameters={"spec_path": str(spec_path), "horizon_bars": spec.horizon_bars},
        source_tables=["dws_crypto_factor_values"],
        target_table="dws_crypto_factor_values",
        is_active=True,
    )
    materialized_count = audit.upsert_factor_values(
        factor_id=signal_factor_id,
        version=spec.version,
        exchange="research",
        market_type=instrument_type or spec.instrument_type,
        interval="signal",
        factor_values=ensemble_signal.rename(columns={"signal": "factor"}),
        parameters={"spec_path": str(spec_path)},
    )
    payload["dws_materialized"] = {
        "table": "dws_crypto_factor_values",
        "ensemble_signal_rows": materialized_count,
        "external_factor_count": len(spec.external_factors),
        "version": spec.version,
    }
    payload["reproducibility"] = reproducibility_payload(
        config,
        artifact_type="alpha_ensemble",
        artifact_name=spec.name,
        data_version="v1",
        factor_version=spec.version,
        parameters={
            "spec_path": str(spec_path),
            "symbols": list(symbols or spec.symbols),
            "instrument_type": instrument_type or spec.instrument_type,
            "start": start,
            "end": end,
        },
    )
    path = write_report(config.report_dir, "alpha_ensemble", payload)
    audit.insert_reproducibility_record(payload["reproducibility"], artifact_path=path)
    return path


def _parse_group(raw: Mapping[str, Any]) -> AlphaGroupSpec:
    transforms = tuple(_parse_transform(item) for item in raw.get("transforms", []))
    if not transforms:
        raise ValueError(f"alpha group {raw.get('group') or raw.get('id')} requires at least one transform")
    return AlphaGroupSpec(
        group=str(raw.get("group") or raw.get("id")),
        factor=str(raw["factor"]),
        weight=float(raw.get("weight", 1.0)),
        transforms=transforms,
    )


def _parse_transform(raw: Mapping[str, Any]) -> AlphaTransformSpec:
    return AlphaTransformSpec(
        name=str(raw["name"]) if raw.get("name") else None,
        model=str(raw["model"]),
        window=int(raw["window"]),
        threshold=float(raw["threshold"]),
        style=str(raw.get("style") or "momentum"),
        position_type=str(raw.get("position_type") or raw.get("strategy_type") or "long_short"),
    )


def _parse_external_factor(raw: Mapping[str, Any], spec_dir: Path, config: AppConfig) -> ExternalFactorSpec:
    path = Path(str(raw["path"]))
    if not path.is_absolute():
        candidates = [config.data_dir / path, Path.cwd() / path, spec_dir / path]
        path = next((candidate for candidate in candidates if candidate.exists()), config.data_dir / path)
    return ExternalFactorSpec(
        factor_id=str(raw.get("factor_id") or raw.get("id")),
        path=path,
        frequency=str(raw.get("frequency") or "1H"),
        description=str(raw.get("description") or "External alpha factor"),
    )


def _apply_single_symbol_transform(
    frame: pd.DataFrame,
    *,
    model: str,
    window: int,
    threshold: float,
    style: str,
    position_type: str,
) -> pd.DataFrame:
    value = frame["factor"].astype(float)
    if model == "ma_diff":
        ma = value.rolling(window).mean()
        if style == "reversion":
            long_cond = value < ma * (1 - threshold)
            short_cond = value > ma * (1 + threshold)
        else:
            long_cond = value > ma * (1 + threshold)
            short_cond = value < ma * (1 - threshold)
    elif model == "z_score":
        roll = value.rolling(window)
        z = (value - roll.mean()) / roll.std().replace(0, np.nan)
        if style == "reversion":
            long_cond = z < -threshold
            short_cond = z > threshold
        else:
            long_cond = z > threshold
            short_cond = z < -threshold
    elif model == "minmax":
        roll = value.rolling(window)
        low = roll.min()
        high = roll.max()
        normalized = (value - low) / (high - low).replace(0, np.nan)
        if style == "reversion":
            long_cond = normalized < threshold
            short_cond = normalized > 1 - threshold
        else:
            long_cond = normalized > threshold
            short_cond = normalized < 1 - threshold
    elif model == "robust_scaling":
        roll = value.rolling(window)
        median = roll.median()
        iqr = roll.quantile(0.75) - roll.quantile(0.25)
        scaled = (value - median) / (iqr + 1e-10)
        if style == "reversion":
            long_cond = scaled < -threshold
            short_cond = scaled > threshold
        else:
            long_cond = scaled > threshold
            short_cond = scaled < -threshold
    elif model == "box_cox":
        adjusted = value.copy()
        min_value = adjusted.min()
        if min_value <= 0:
            adjusted = adjusted - min_value + 1e-3
        transformed = (adjusted**0.3 - 1) / 0.3
        roll = transformed.rolling(window)
        z = (transformed - roll.mean()) / roll.std().replace(0, np.nan)
        if style == "reversion":
            long_cond = z < -threshold
            short_cond = z > threshold
        else:
            long_cond = z > threshold
            short_cond = z < -threshold
    elif model == "rate_of_change":
        roc = value.pct_change(window) * 100
        if style == "reversion":
            long_cond = roc < -threshold
            short_cond = roc > threshold
        else:
            long_cond = roc > threshold
            short_cond = roc < -threshold
    else:
        raise ValueError(f"unsupported transform model '{model}'")

    out = frame[["ts"]].copy()
    out["signal"] = _generate_signal(long_cond.fillna(False), short_cond.fillna(False), position_type)
    return out


def _generate_signal(long_cond: pd.Series, short_cond: pd.Series, position_type: str) -> pd.Series:
    if position_type == "long_only":
        return pd.Series(np.where(long_cond, 1.0, 0.0), index=long_cond.index)
    if position_type == "short_only":
        return pd.Series(np.where(short_cond, -1.0, 0.0), index=long_cond.index)
    if position_type == "binary_LS":
        return pd.Series(np.where(long_cond, 1.0, -1.0), index=long_cond.index)
    if position_type == "binary_SL":
        return pd.Series(np.where(short_cond, -1.0, 1.0), index=long_cond.index)
    return pd.Series(np.select([long_cond, short_cond], [1.0, -1.0], 0.0), index=long_cond.index)


def _standard_factor_values(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["ts", "symbol", "factor"])
    required = {"ts", "symbol", "factor"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"factor values missing required columns: {', '.join(sorted(missing))}")
    out = frame[["ts", "symbol", "factor"]].copy()
    out["ts"] = pd.to_datetime(out["ts"], utc=True, errors="coerce")
    out["symbol"] = out["symbol"].astype(str)
    out["factor"] = pd.to_numeric(out["factor"], errors="coerce")
    return out.dropna(subset=["ts", "symbol", "factor"]).sort_values(["symbol", "ts"]).reset_index(drop=True)


def _load_builtin_factors(
    config: AppConfig,
    spec: AlphaEnsembleSpec,
    symbols: list[str],
    instrument_type: str,
    start: str | None,
    end: str | None,
) -> dict[str, pd.DataFrame]:
    result = {}
    requested = {group.factor for group in spec.groups}
    external_ids = {item.factor_id for item in spec.external_factors}
    for factor_id in sorted(requested - external_ids):
        try:
            builder = build_factor(factor_id)
        except ValueError:
            continue
        panel = (
            load_funding_panel(config, symbols, start=start, end=end)
            if builder.data_source == "funding"
            else load_crypto_panel(config, symbols, instrument_type, start=start, end=end)
        )
        result[factor_id] = builder.compute(panel) if not panel.empty else pd.DataFrame(columns=["ts", "symbol", "factor"])
    return result


def _load_external_factors(
    specs: Iterable[ExternalFactorSpec],
    *,
    symbols: list[str],
    start: str | None,
    end: str | None,
) -> dict[str, pd.DataFrame]:
    result = {}
    allowed = set(symbols)
    for spec in specs:
        if not spec.path.exists():
            result[spec.factor_id] = pd.DataFrame(columns=["ts", "symbol", "factor"])
            continue
        frame = pd.read_csv(spec.path)
        values = _standard_factor_values(frame)
        if allowed:
            values = values[values["symbol"].isin(allowed)].copy()
        values = filter_date_range(values, start, end)
        result[spec.factor_id] = values.reset_index(drop=True)
    return result


def _forward_trade_returns(panel: pd.DataFrame, horizon_bars: int) -> pd.DataFrame:
    out = panel[["ts", "symbol", "close"]].copy()
    out["ts"] = pd.to_datetime(out["ts"], utc=True, errors="coerce")
    out["close"] = pd.to_numeric(out["close"], errors="coerce")
    out = out.dropna(subset=["ts", "symbol", "close"]).sort_values(["symbol", "ts"]).reset_index(drop=True)
    grouped = out.groupby("symbol", group_keys=False)["close"]
    future = grouped.shift(-int(horizon_bars))
    out["forward_return"] = future / out["close"] - 1.0
    return out[["ts", "symbol", "forward_return"]].dropna(subset=["forward_return"]).reset_index(drop=True)


def _mean_signal(frames: list[pd.DataFrame], *, output_column: str) -> pd.DataFrame:
    merged = None
    for frame in frames:
        merged = frame.copy() if merged is None else merged.merge(frame, on=["ts", "symbol"], how="outer")
    if merged is None or merged.empty:
        return pd.DataFrame(columns=["ts", "symbol", output_column])
    value_cols = [col for col in merged.columns if col not in {"ts", "symbol"}]
    merged[output_column] = merged[value_cols].mean(axis=1)
    return merged[["ts", "symbol", output_column]].dropna(subset=[output_column]).reset_index(drop=True)


def _weighted_group_signal(groups: tuple[AlphaGroupSpec, ...], group_signals: dict[str, pd.DataFrame]) -> pd.DataFrame:
    weighted = []
    for group in groups:
        signal = group_signals.get(group.group)
        if signal is None or signal.empty:
            continue
        tmp = signal.copy()
        tmp["weighted_signal"] = tmp["signal"].astype(float) * float(group.weight)
        tmp["weight"] = abs(float(group.weight))
        weighted.append(tmp[["ts", "symbol", "weighted_signal", "weight"]])
    if not weighted:
        return pd.DataFrame(columns=["ts", "symbol", "signal"])
    frame = pd.concat(weighted, ignore_index=True)
    grouped = frame.groupby(["ts", "symbol"], as_index=False).agg({"weighted_signal": "sum", "weight": "sum"})
    grouped["signal"] = grouped["weighted_signal"] / grouped["weight"].replace(0, np.nan)
    grouped["signal"] = grouped["signal"].clip(-1.0, 1.0)
    return grouped[["ts", "symbol", "signal"]].dropna(subset=["signal"]).reset_index(drop=True)


def _signal_metrics(signal: pd.DataFrame, forward_returns: pd.DataFrame, *, config: AppConfig, horizon_bars: int) -> dict[str, Any]:
    if signal.empty or forward_returns.empty:
        return _empty_signal_metrics()
    merged = signal.merge(forward_returns, on=["ts", "symbol"], how="inner").dropna(subset=["signal", "forward_return"])
    if merged.empty:
        return _empty_signal_metrics()
    merged = merged.sort_values(["symbol", "ts"]).reset_index(drop=True)
    cost_rate = float(config.execution.fee_rate) + float(config.execution.slippage_bps) / 10_000
    merged["trade"] = merged.groupby("symbol")["signal"].diff().abs().fillna(merged["signal"].abs())
    merged["pnl"] = merged["signal"].astype(float) * merged["forward_return"].astype(float) - merged["trade"] * cost_rate
    by_ts = merged.groupby("ts", as_index=False)["pnl"].mean().sort_values("ts")
    equity_curve = pd.DataFrame({"ts": by_ts["ts"], "equity": 1.0 + by_ts["pnl"].cumsum()})
    returns = by_ts["pnl"].astype(float)
    running_max = equity_curve["equity"].cummax()
    drawdown = equity_curve["equity"] / running_max - 1
    annual_periods = periods_per_year(equity_curve) / max(int(horizon_bars), 1)
    sharpe = 0.0 if returns.std(ddof=0) == 0 else float(returns.mean() / returns.std(ddof=0) * annual_periods**0.5)
    return {
        "observations": int(len(merged)),
        "cross_sections": int(by_ts["ts"].nunique()),
        "mean_pnl": float(returns.mean()),
        "total_pnl": float(returns.sum()),
        "annualized_pnl": float(returns.mean() * annual_periods),
        "sharpe": sharpe,
        "max_drawdown": float(drawdown.min()) if not drawdown.empty else 0.0,
        "turnover_mean": float(merged.groupby("ts")["trade"].mean().mean()) if not merged.empty else 0.0,
        "coverage_symbols": int(merged["symbol"].nunique()),
        "cost_rate": cost_rate,
    }


def _empty_signal_metrics() -> dict[str, Any]:
    return {
        "observations": 0,
        "cross_sections": 0,
        "mean_pnl": 0.0,
        "total_pnl": 0.0,
        "annualized_pnl": 0.0,
        "sharpe": 0.0,
        "max_drawdown": 0.0,
        "turnover_mean": 0.0,
        "coverage_symbols": 0,
        "cost_rate": 0.0,
    }


def _parameter_stability(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    if not candidates:
        return {"status": "no_candidates", "positive_candidate_rate": 0.0, "best_strategy": None}
    positive = [item for item in candidates if float(item.get("metrics", {}).get("total_pnl", 0.0)) > 0]
    best = max(candidates, key=lambda item: float(item.get("metrics", {}).get("sharpe", 0.0)))
    by_group = {}
    for item in candidates:
        group = str(item.get("group"))
        by_group.setdefault(group, {"candidate_count": 0, "positive_count": 0})
        by_group[group]["candidate_count"] += 1
        if float(item.get("metrics", {}).get("total_pnl", 0.0)) > 0:
            by_group[group]["positive_count"] += 1
    for item in by_group.values():
        item["positive_rate"] = item["positive_count"] / item["candidate_count"] if item["candidate_count"] else 0.0
    return {
        "status": "ok",
        "candidate_count": len(candidates),
        "positive_candidate_rate": len(positive) / len(candidates),
        "best_strategy": best.get("strategy"),
        "by_group": by_group,
    }


def _first_ts(frame: pd.DataFrame) -> str | None:
    if frame.empty or "ts" not in frame:
        return None
    ts = pd.to_datetime(frame["ts"], utc=True, errors="coerce").dropna()
    return None if ts.empty else ts.min().isoformat()


def _last_ts(frame: pd.DataFrame) -> str | None:
    if frame.empty or "ts" not in frame:
        return None
    ts = pd.to_datetime(frame["ts"], utc=True, errors="coerce").dropna()
    return None if ts.empty else ts.max().isoformat()
