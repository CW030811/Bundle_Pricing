from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd

from .config import AppConfig
from .reports import write_report
from .storage import AuditStore


INTERVAL_SECONDS = {
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1H": 3600,
    "2H": 7200,
    "4H": 14400,
    "6H": 21600,
    "12H": 43200,
    "1D": 86400,
}


def check_ohlcv_quality(
    candles: pd.DataFrame,
    *,
    exchange: str,
    symbol: str,
    market_type: str,
    interval: str,
    table_name: str = "dwd_crypto_ohlcv",
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc).isoformat()
    if candles.empty:
        issues.append(
            _issue(table_name, exchange, symbol, market_type, interval, None, "missing_data", "No local OHLCV rows", "error", now)
        )
        return issues

    df = candles.copy()
    df["ts"] = pd.to_datetime(df["ts"], utc=True, errors="coerce") if "ts" in df else pd.NaT
    missing_ts = df["ts"].isna()
    if missing_ts.any():
        issues.append(
            _issue(
                table_name,
                exchange,
                symbol,
                market_type,
                interval,
                None,
                "null_value",
                f"{int(missing_ts.sum())} rows have missing or invalid ts",
                "error",
                now,
            )
        )
    df = df.dropna(subset=["ts"]).sort_values("ts")

    duplicates = df[df.duplicated(["ts"], keep=False)]
    for ts, group in duplicates.groupby("ts"):
        issues.append(
            _issue(
                table_name,
                exchange,
                symbol,
                market_type,
                interval,
                ts.isoformat(),
                "duplicate",
                f"{len(group)} duplicate rows for timestamp",
                "warning",
                now,
            )
        )

    numeric_columns = ["open", "high", "low", "close", "volume"]
    for column in numeric_columns:
        if column not in df:
            issues.append(
                _issue(
                    table_name,
                    exchange,
                    symbol,
                    market_type,
                    interval,
                    None,
                    "null_value",
                    f"Required column {column} is missing",
                    "error",
                    now,
                )
            )
            continue
        df[column] = pd.to_numeric(df[column], errors="coerce")
        missing = df[df[column].isna()]
        if not missing.empty:
            issues.append(
                _issue(
                    table_name,
                    exchange,
                    symbol,
                    market_type,
                    interval,
                    _first_ts(missing),
                    "null_value",
                    f"{len(missing)} rows have null {column}",
                    "error",
                    now,
                )
            )

    if {"open", "high", "low", "close"}.issubset(df.columns):
        price_invalid = df[(df["open"] <= 0) | (df["high"] <= 0) | (df["low"] <= 0) | (df["close"] <= 0)]
        if not price_invalid.empty:
            issues.append(
                _issue(
                    table_name,
                    exchange,
                    symbol,
                    market_type,
                    interval,
                    _first_ts(price_invalid),
                    "abnormal_price",
                    f"{len(price_invalid)} rows have non-positive OHLC prices",
                    "error",
                    now,
                )
            )
        invalid_ohlc = df[
            (df["high"] < df["open"])
            | (df["high"] < df["close"])
            | (df["high"] < df["low"])
            | (df["low"] > df["open"])
            | (df["low"] > df["close"])
        ]
        if not invalid_ohlc.empty:
            issues.append(
                _issue(
                    table_name,
                    exchange,
                    symbol,
                    market_type,
                    interval,
                    _first_ts(invalid_ohlc),
                    "invalid_ohlc",
                    f"{len(invalid_ohlc)} rows violate OHLC high/low constraints",
                    "error",
                    now,
                )
            )

    if "volume" in df:
        negative_volume = df[df["volume"] < 0]
        if not negative_volume.empty:
            issues.append(
                _issue(
                    table_name,
                    exchange,
                    symbol,
                    market_type,
                    interval,
                    _first_ts(negative_volume),
                    "negative_volume",
                    f"{len(negative_volume)} rows have negative volume",
                    "error",
                    now,
                )
            )

    if "confirmed" in df:
        unclosed = df[df["confirmed"].fillna(False).astype(bool) == False]  # noqa: E712
        if not unclosed.empty:
            issues.append(
                _issue(
                    table_name,
                    exchange,
                    symbol,
                    market_type,
                    interval,
                    _first_ts(unclosed),
                    "unclosed_bar",
                    f"{len(unclosed)} rows are not confirmed closed bars",
                    "info",
                    now,
                )
            )

    expected_seconds = INTERVAL_SECONDS.get(interval)
    if expected_seconds and len(df) > 1:
        diffs = df["ts"].diff().dt.total_seconds()
        gaps = df.loc[diffs > expected_seconds]
        for _, row in gaps.iterrows():
            issues.append(
                _issue(
                    table_name,
                    exchange,
                    symbol,
                    market_type,
                    interval,
                    row["ts"].isoformat(),
                    "data_gap",
                    f"Previous timestamp gap is {int(diffs.loc[row.name])} seconds, expected {expected_seconds}",
                    "warning",
                    now,
                )
            )
    return issues


def data_quality_summary(issues: list[dict[str, Any]]) -> dict[str, Any]:
    by_type: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    for issue in issues:
        by_type[str(issue["issue_type"])] = by_type.get(str(issue["issue_type"]), 0) + 1
        by_severity[str(issue["severity"])] = by_severity.get(str(issue["severity"]), 0) + 1
    return {
        "issue_count": len(issues),
        "by_type": by_type,
        "by_severity": by_severity,
    }


def run_ohlcv_quality_check(
    config: AppConfig,
    *,
    symbols: list[str],
    instrument_types: list[str],
    interval: str | None = None,
    persist: bool = False,
) -> dict[str, Any]:
    from .data import load_candles

    selected_interval = interval or config.market.bar
    all_issues: list[dict[str, Any]] = []
    checked: list[dict[str, Any]] = []
    for market_type in instrument_types:
        for symbol in symbols:
            candles = load_candles(config, symbol, market_type, selected_interval)
            issues = check_ohlcv_quality(
                candles,
                exchange="okx",
                symbol=symbol,
                market_type=market_type,
                interval=selected_interval,
            )
            all_issues.extend(issues)
            checked.append(
                {
                    "symbol": symbol,
                    "market_type": market_type,
                    "interval": selected_interval,
                    "row_count": int(len(candles)),
                    "issue_count": len(issues),
                }
            )
    if persist:
        AuditStore(config.state_dir).insert_data_quality_issues(all_issues)
    return {
        "status": "ok" if not any(item.get("severity") == "error" for item in all_issues) else "issues_found",
        "checked": checked,
        "summary": data_quality_summary(all_issues),
        "issues": all_issues,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def run_ohlcv_quality_report(
    config: AppConfig,
    *,
    symbols: list[str],
    instrument_types: list[str],
    interval: str | None = None,
    persist: bool = True,
) -> Any:
    payload = run_ohlcv_quality_check(
        config,
        symbols=symbols,
        instrument_types=instrument_types,
        interval=interval,
        persist=persist,
    )
    return write_report(config.report_dir, "data_quality_ohlcv", payload)


def _issue(
    table_name: str,
    exchange: str,
    symbol: str,
    market_type: str,
    interval: str,
    timestamp: str | None,
    issue_type: str,
    issue_detail: str,
    severity: str,
    now: str,
) -> dict[str, Any]:
    return {
        "table_name": table_name,
        "exchange": exchange,
        "symbol": symbol,
        "market_type": market_type,
        "interval": interval,
        "timestamp": timestamp,
        "issue_type": issue_type,
        "issue_detail": issue_detail,
        "severity": severity,
        "is_resolved": False,
        "created_at": now,
        "updated_at": now,
    }


def _first_ts(frame: pd.DataFrame) -> str | None:
    if frame.empty or "ts" not in frame:
        return None
    value = frame.iloc[0]["ts"]
    return value.isoformat() if hasattr(value, "isoformat") else str(value)
