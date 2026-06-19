from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

import pandas as pd

from .models import Order, Position, RiskDecision, Signal, dataclass_to_dict, position_key


OKX_CANDLE_COLUMNS = [
    "ts",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "volume_ccy",
    "volume_quote",
    "confirm",
]


def normalize_okx_candles(rows: Iterable[list[str]], symbol: str, instrument_type: str) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for row in rows:
        padded = list(row) + [None] * (len(OKX_CANDLE_COLUMNS) - len(row))
        item = dict(zip(OKX_CANDLE_COLUMNS, padded))
        ts = pd.to_datetime(int(item["ts"]), unit="ms", utc=True)
        records.append(
            {
                "ts": ts,
                "symbol": symbol,
                "instrument_type": instrument_type,
                "open": float(item["open"]),
                "high": float(item["high"]),
                "low": float(item["low"]),
                "close": float(item["close"]),
                "volume": float(item["volume"]),
                "confirmed": str(item.get("confirm", "1")) == "1",
            }
        )
    df = pd.DataFrame(records)
    if df.empty:
        return df
    return (
        df.drop_duplicates(["ts", "symbol", "instrument_type"])
        .sort_values("ts")
        .reset_index(drop=True)
    )


def normalize_okx_funding_rates(rows: Iterable[dict[str, Any]], symbol: str) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for row in rows:
        funding_time = row.get("fundingTime") or row.get("fundingTimeMs")
        if funding_time is None:
            continue
        rate = row.get("realizedRate")
        if rate in (None, ""):
            rate = row.get("fundingRate")
        if rate in (None, ""):
            continue
        records.append(
            {
                "ts": pd.to_datetime(int(funding_time), unit="ms", utc=True),
                "symbol": symbol,
                "instrument_type": "swap",
                "inst_id": row.get("instId"),
                "funding_rate": float(rate),
                "raw_funding_rate": float(row.get("fundingRate", rate)),
                "method": row.get("method"),
            }
        )
    df = pd.DataFrame(records)
    if df.empty:
        return df
    return df.drop_duplicates(["ts", "symbol"]).sort_values("ts").reset_index(drop=True)


class CandleStore:
    def __init__(self, data_dir: Path):
        self.root = Path(data_dir) / "candles"
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, symbol: str, instrument_type: str, bar: str) -> Path:
        safe_symbol = symbol.replace("/", "-")
        return self.root / instrument_type / safe_symbol / f"{bar}.parquet"

    def write(self, df: pd.DataFrame, symbol: str, instrument_type: str, bar: str) -> Path:
        path = self.path_for(symbol, instrument_type, bar)
        path.parent.mkdir(parents=True, exist_ok=True)
        merged = self.merge_existing(df, symbol, instrument_type, bar)
        try:
            merged.to_parquet(path, index=False)
        except ImportError:
            fallback = path.with_suffix(".csv")
            merged.to_csv(fallback, index=False)
            path = fallback
        return path

    def merge_existing(self, df: pd.DataFrame, symbol: str, instrument_type: str, bar: str) -> pd.DataFrame:
        existing = self.read(symbol, instrument_type, bar)
        if existing.empty:
            return df.sort_values("ts").reset_index(drop=True)
        return (
            pd.concat([existing, df], ignore_index=True)
            .drop_duplicates(["ts", "symbol", "instrument_type"], keep="last")
            .sort_values("ts")
            .reset_index(drop=True)
        )

    def read(self, symbol: str, instrument_type: str, bar: str) -> pd.DataFrame:
        path = self.path_for(symbol, instrument_type, bar)
        if path.exists():
            return pd.read_parquet(path)
        fallback = path.with_suffix(".csv")
        if fallback.exists():
            df = pd.read_csv(fallback)
            df["ts"] = pd.to_datetime(df["ts"], utc=True, format="mixed")
            return df
        return pd.DataFrame()


class FundingRateStore:
    def __init__(self, data_dir: Path):
        self.root = Path(data_dir) / "funding"
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, symbol: str) -> Path:
        safe_symbol = symbol.replace("/", "-")
        return self.root / safe_symbol / "funding.parquet"

    def write(self, df: pd.DataFrame, symbol: str) -> Path:
        path = self.path_for(symbol)
        path.parent.mkdir(parents=True, exist_ok=True)
        merged = self.merge_existing(df, symbol)
        try:
            merged.to_parquet(path, index=False)
        except ImportError:
            fallback = path.with_suffix(".csv")
            merged.to_csv(fallback, index=False)
            path = fallback
        return path

    def merge_existing(self, df: pd.DataFrame, symbol: str) -> pd.DataFrame:
        existing = self.read(symbol)
        if existing.empty:
            return df.sort_values("ts").reset_index(drop=True)
        return (
            pd.concat([existing, df], ignore_index=True)
            .drop_duplicates(["ts", "symbol"], keep="last")
            .sort_values("ts")
            .reset_index(drop=True)
        )

    def read(self, symbol: str) -> pd.DataFrame:
        path = self.path_for(symbol)
        if path.exists():
            return pd.read_parquet(path)
        fallback = path.with_suffix(".csv")
        if fallback.exists():
            df = pd.read_csv(fallback)
            df["ts"] = pd.to_datetime(df["ts"], utc=True, format="mixed")
            return df
        return pd.DataFrame()


class AuditStore:
    def __init__(self, state_dir: Path):
        self.path = Path(state_dir) / "quant_system.sqlite"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.init_schema()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    instrument_type TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    target_pct REAL NOT NULL,
                    confidence REAL NOT NULL,
                    reason TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS orders (
                    client_order_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    instrument_type TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    order_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    filled_quantity REAL NOT NULL,
                    average_price REAL,
                    exchange_order_id TEXT,
                    message TEXT,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS positions (
                    key TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    instrument_type TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    average_entry REAL NOT NULL,
                    realized_pnl REAL NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS risk_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    instrument_type TEXT NOT NULL,
                    approved INTEGER NOT NULL,
                    reason TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS run_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ods_crypto_ohlcv_raw (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    exchange TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    market_type TEXT NOT NULL,
                    interval TEXT NOT NULL,
                    raw_timestamp TEXT,
                    ingested_at TEXT NOT NULL,
                    raw_data TEXT NOT NULL,
                    data_version TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ods_crypto_funding_rate_raw (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    exchange TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    market_type TEXT NOT NULL,
                    raw_timestamp TEXT,
                    ingested_at TEXT NOT NULL,
                    raw_data TEXT NOT NULL,
                    data_version TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ods_crypto_exchange_info_raw (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    exchange TEXT NOT NULL,
                    market_type TEXT NOT NULL,
                    raw_timestamp TEXT,
                    ingested_at TEXT NOT NULL,
                    raw_data TEXT NOT NULL,
                    data_version TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ods_crypto_market_data_raw (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    data_type TEXT NOT NULL,
                    source TEXT NOT NULL,
                    exchange TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    market_type TEXT NOT NULL,
                    interval TEXT,
                    raw_timestamp TEXT,
                    ingested_at TEXT NOT NULL,
                    raw_data TEXT NOT NULL,
                    data_version TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS dwd_crypto_exchange_info (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    exchange TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    market_type TEXT NOT NULL,
                    inst_id TEXT NOT NULL,
                    base_currency TEXT,
                    quote_currency TEXT,
                    state TEXT,
                    min_size REAL,
                    lot_size REAL,
                    tick_size REAL,
                    contract_value REAL,
                    raw_data TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(exchange, symbol, market_type, inst_id)
                );
                CREATE TABLE IF NOT EXISTS dwd_crypto_ohlcv (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    exchange TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    market_type TEXT NOT NULL,
                    interval TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume REAL NOT NULL,
                    quote_volume REAL,
                    trade_count INTEGER,
                    is_closed INTEGER NOT NULL,
                    source TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(exchange, symbol, market_type, interval, timestamp)
                );
                CREATE TABLE IF NOT EXISTS dwd_crypto_funding_rate (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    exchange TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    funding_rate REAL NOT NULL,
                    funding_time TEXT NOT NULL,
                    mark_price REAL,
                    index_price REAL,
                    source TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(exchange, symbol, timestamp)
                );
                CREATE TABLE IF NOT EXISTS dwd_crypto_open_interest (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    exchange TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    market_type TEXT NOT NULL,
                    inst_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    open_interest REAL,
                    open_interest_currency REAL,
                    source TEXT NOT NULL,
                    raw_data TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(exchange, symbol, market_type, timestamp)
                );
                CREATE TABLE IF NOT EXISTS dwd_crypto_basis (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    exchange TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    market_type TEXT NOT NULL,
                    inst_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    mark_price REAL,
                    index_price REAL,
                    basis REAL,
                    basis_pct REAL,
                    source TEXT NOT NULL,
                    raw_data TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(exchange, symbol, market_type, timestamp)
                );
                CREATE TABLE IF NOT EXISTS dwd_crypto_long_short_ratio (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    exchange TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    market_type TEXT NOT NULL,
                    period TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    long_short_ratio REAL,
                    source TEXT NOT NULL,
                    raw_data TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(exchange, symbol, market_type, period, timestamp)
                );
                CREATE TABLE IF NOT EXISTS dwd_crypto_orderbook_snapshot (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    exchange TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    market_type TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    depth INTEGER NOT NULL,
                    side TEXT NOT NULL,
                    price REAL NOT NULL,
                    size REAL NOT NULL,
                    order_count INTEGER,
                    source TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(exchange, symbol, market_type, timestamp, depth, side, price)
                );
                CREATE TABLE IF NOT EXISTS dwd_crypto_trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    exchange TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    market_type TEXT NOT NULL,
                    trade_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    side TEXT NOT NULL,
                    price REAL NOT NULL,
                    size REAL NOT NULL,
                    source TEXT NOT NULL,
                    raw_data TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(exchange, symbol, market_type, trade_id)
                );
                CREATE TABLE IF NOT EXISTS dwd_crypto_liquidations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    exchange TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    market_type TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    side TEXT,
                    price REAL,
                    size REAL,
                    source TEXT NOT NULL,
                    raw_data TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(exchange, symbol, market_type, timestamp, side, price, size)
                );
                CREATE TABLE IF NOT EXISTS data_ingestion_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    exchange TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    market_type TEXT NOT NULL,
                    data_type TEXT NOT NULL,
                    interval TEXT,
                    start_time TEXT,
                    end_time TEXT,
                    status TEXT NOT NULL,
                    records_fetched INTEGER NOT NULL,
                    records_inserted INTEGER NOT NULL,
                    records_updated INTEGER NOT NULL,
                    error_message TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS data_ingestion_tasks (
                    task_key TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    exchange TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    market_type TEXT NOT NULL,
                    data_type TEXT NOT NULL,
                    interval TEXT,
                    status TEXT NOT NULL,
                    retry_count INTEGER NOT NULL,
                    last_watermark TEXT,
                    last_error TEXT,
                    updated_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reproducibility_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    artifact_type TEXT NOT NULL,
                    artifact_name TEXT NOT NULL,
                    artifact_path TEXT,
                    data_version TEXT NOT NULL,
                    factor_version TEXT,
                    code_fingerprint TEXT NOT NULL,
                    config_fingerprint TEXT NOT NULL,
                    parameters TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS data_quality_issues (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    table_name TEXT NOT NULL,
                    exchange TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    market_type TEXT NOT NULL,
                    interval TEXT,
                    timestamp TEXT,
                    issue_type TEXT NOT NULL,
                    issue_detail TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    is_resolved INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS factor_registry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    factor_name TEXT NOT NULL,
                    factor_category TEXT NOT NULL,
                    version TEXT NOT NULL,
                    description TEXT NOT NULL,
                    formula TEXT,
                    parameters TEXT NOT NULL,
                    source_tables TEXT NOT NULL,
                    target_table TEXT NOT NULL,
                    is_active INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(factor_name, version)
                );
                CREATE TABLE IF NOT EXISTS factor_calculation_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    factor_name TEXT NOT NULL,
                    source_table TEXT NOT NULL,
                    target_table TEXT NOT NULL,
                    symbol TEXT,
                    interval TEXT,
                    start_time TEXT,
                    end_time TEXT,
                    parameters TEXT NOT NULL,
                    status TEXT NOT NULL,
                    records_calculated INTEGER NOT NULL,
                    error_message TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS dws_crypto_factor_values (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    factor_id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    exchange TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    market_type TEXT NOT NULL,
                    interval TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    factor_value REAL NOT NULL,
                    parameters TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(factor_id, version, exchange, symbol, market_type, interval, timestamp)
                );
                CREATE TABLE IF NOT EXISTS strategy_registry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    strategy_id TEXT NOT NULL UNIQUE,
                    strategy_name TEXT NOT NULL,
                    strategy_type TEXT NOT NULL,
                    source TEXT,
                    source_url TEXT,
                    description TEXT NOT NULL,
                    core_logic TEXT NOT NULL,
                    data_requirements TEXT NOT NULL,
                    factors_used TEXT NOT NULL,
                    entry_rules TEXT NOT NULL,
                    exit_rules TEXT NOT NULL,
                    position_sizing TEXT NOT NULL,
                    risk_management TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ads_crypto_strategy_signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    strategy_id TEXT,
                    strategy_name TEXT NOT NULL,
                    exchange TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    market_type TEXT NOT NULL,
                    interval TEXT,
                    timestamp TEXT NOT NULL,
                    signal TEXT NOT NULL,
                    signal_strength REAL,
                    signal_reason TEXT,
                    source_factors TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ads_crypto_target_positions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    strategy_id TEXT,
                    exchange TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    market_type TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    target_side TEXT NOT NULL,
                    target_position_ratio REAL NOT NULL,
                    target_leverage REAL,
                    stop_loss REAL,
                    take_profit REAL,
                    risk_limit TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ads_crypto_backtest_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    strategy_id TEXT NOT NULL,
                    strategy_name TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    market_type TEXT NOT NULL,
                    interval TEXT,
                    start_time TEXT,
                    end_time TEXT,
                    initial_capital REAL,
                    final_capital REAL,
                    total_return REAL,
                    annualized_return REAL,
                    max_drawdown REAL,
                    sharpe_ratio REAL,
                    sortino_ratio REAL,
                    calmar_ratio REAL,
                    win_rate REAL,
                    profit_factor REAL,
                    average_profit REAL,
                    average_loss REAL,
                    profit_loss_ratio REAL,
                    trade_count INTEGER,
                    fee_assumption REAL,
                    slippage_assumption REAL,
                    funding_fee_included INTEGER NOT NULL,
                    report_path TEXT,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ads_crypto_backtest_trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    backtest_id INTEGER,
                    strategy_id TEXT NOT NULL,
                    exchange TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    market_type TEXT NOT NULL,
                    entry_time TEXT,
                    exit_time TEXT,
                    side TEXT NOT NULL,
                    entry_price REAL,
                    exit_price REAL,
                    position_size REAL,
                    leverage REAL,
                    fee REAL,
                    slippage REAL,
                    funding_fee REAL,
                    gross_pnl REAL,
                    net_pnl REAL,
                    return_pct REAL,
                    holding_period TEXT,
                    exit_reason TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ads_crypto_strategy_scores (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    strategy_id TEXT NOT NULL,
                    strategy_name TEXT NOT NULL,
                    score_total REAL NOT NULL,
                    score_return REAL,
                    score_drawdown REAL,
                    score_sharpe REAL,
                    score_stability REAL,
                    score_cost_sensitivity REAL,
                    score_parameter_robustness REAL,
                    score_market_regime_robustness REAL,
                    recommendation TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ads_crypto_risk_status (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    strategy_id TEXT,
                    exchange TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    current_position REAL,
                    current_drawdown REAL,
                    daily_loss REAL,
                    weekly_loss REAL,
                    risk_level TEXT NOT NULL,
                    is_trading_allowed INTEGER NOT NULL,
                    stop_reason TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ads_crypto_service_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    service_name TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    strategy_id TEXT,
                    exchange TEXT NOT NULL,
                    symbols TEXT NOT NULL,
                    market_type TEXT NOT NULL,
                    interval TEXT,
                    started_at TEXT,
                    completed_at TEXT NOT NULL,
                    iteration INTEGER,
                    ok INTEGER NOT NULL,
                    order_count INTEGER NOT NULL,
                    message_count INTEGER NOT NULL,
                    selected_count INTEGER NOT NULL,
                    stale_data INTEGER,
                    cooldown_active INTEGER,
                    circuit_breaker INTEGER,
                    consecutive_errors INTEGER,
                    stop_reason TEXT,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS review_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_type TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    category TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    status TEXT NOT NULL,
                    title TEXT NOT NULL,
                    details TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(source_type, source_id)
                );
                """
            )

    def datahub_schema_status(self) -> dict[str, Any]:
        expected = [
            "ods_crypto_ohlcv_raw",
            "ods_crypto_funding_rate_raw",
            "ods_crypto_exchange_info_raw",
            "ods_crypto_market_data_raw",
            "dwd_crypto_exchange_info",
            "dwd_crypto_ohlcv",
            "dwd_crypto_funding_rate",
            "dwd_crypto_open_interest",
            "dwd_crypto_basis",
            "dwd_crypto_long_short_ratio",
            "dwd_crypto_orderbook_snapshot",
            "dwd_crypto_trades",
            "dwd_crypto_liquidations",
            "data_ingestion_logs",
            "data_ingestion_tasks",
            "reproducibility_records",
            "data_quality_issues",
            "factor_registry",
            "factor_calculation_logs",
            "dws_crypto_factor_values",
            "strategy_registry",
            "ads_crypto_strategy_signals",
            "ads_crypto_target_positions",
            "ads_crypto_backtest_results",
            "ads_crypto_backtest_trades",
            "ads_crypto_strategy_scores",
            "ads_crypto_risk_status",
            "ads_crypto_service_runs",
            "review_tasks",
        ]
        with self.connect() as conn:
            rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        present = {row["name"] for row in rows}
        return {
            "database": str(self.path),
            "expected_tables": expected,
            "present_tables": sorted(table for table in expected if table in present),
            "missing_tables": sorted(table for table in expected if table not in present),
        }

    def insert_ods_crypto_ohlcv_raw(
        self,
        rows: Iterable[Any],
        *,
        source: str,
        exchange: str,
        symbol: str,
        market_type: str,
        interval: str,
        data_version: str = "v1",
    ) -> int:
        ingested_at = _utc_now()
        payloads = []
        for row in rows:
            raw_timestamp = None
            if isinstance(row, (list, tuple)) and row:
                raw_timestamp = str(row[0])
            elif isinstance(row, dict):
                raw_timestamp = str(row.get("ts") or row.get("timestamp") or row.get("time") or "")
            payloads.append(
                (
                    source,
                    exchange,
                    symbol,
                    market_type,
                    interval,
                    raw_timestamp,
                    ingested_at,
                    json.dumps(row, ensure_ascii=False),
                    data_version,
                )
            )
        if not payloads:
            return 0
        with self.connect() as conn:
            conn.executemany(
                """
                INSERT INTO ods_crypto_ohlcv_raw
                (source, exchange, symbol, market_type, interval, raw_timestamp, ingested_at, raw_data, data_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                payloads,
            )
        return len(payloads)

    def insert_ods_crypto_funding_rate_raw(
        self,
        rows: Iterable[Any],
        *,
        source: str,
        exchange: str,
        symbol: str,
        market_type: str = "swap",
        data_version: str = "v1",
    ) -> int:
        ingested_at = _utc_now()
        payloads = []
        for row in rows:
            payloads.append(
                (
                    source,
                    exchange,
                    symbol,
                    market_type,
                    str(row.get("fundingTime") or row.get("fundingTimeMs") or row.get("ts") or ""),
                    ingested_at,
                    json.dumps(row, ensure_ascii=False),
                    data_version,
                )
            )
        if not payloads:
            return 0
        with self.connect() as conn:
            conn.executemany(
                """
                INSERT INTO ods_crypto_funding_rate_raw
                (source, exchange, symbol, market_type, raw_timestamp, ingested_at, raw_data, data_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                payloads,
            )
        return len(payloads)

    def insert_ods_crypto_exchange_info_raw(
        self,
        rows: Iterable[dict[str, Any]],
        *,
        source: str,
        exchange: str,
        market_type: str,
        data_version: str = "v1",
    ) -> int:
        ingested_at = _utc_now()
        payloads = [
            (
                source,
                exchange,
                market_type,
                str(row.get("uTime") or row.get("listTime") or ""),
                ingested_at,
                json.dumps(row, ensure_ascii=False),
                data_version,
            )
            for row in rows
        ]
        if not payloads:
            return 0
        with self.connect() as conn:
            conn.executemany(
                """
                INSERT INTO ods_crypto_exchange_info_raw
                (source, exchange, market_type, raw_timestamp, ingested_at, raw_data, data_version)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                payloads,
            )
        return len(payloads)

    def insert_ods_crypto_market_data_raw(
        self,
        rows: Iterable[dict[str, Any]],
        *,
        data_type: str,
        source: str,
        exchange: str,
        symbol: str,
        market_type: str,
        interval: str | None = None,
        data_version: str = "v1",
    ) -> int:
        ingested_at = _utc_now()
        payloads = []
        for row in rows:
            if isinstance(row, dict):
                raw_timestamp = row.get("ts") or row.get("uTime") or row.get("cTime") or row.get("time") or row.get("timestamp") or ""
            elif isinstance(row, (list, tuple)) and row:
                raw_timestamp = row[0]
            else:
                raw_timestamp = ""
            payloads.append(
                (
                    data_type,
                    source,
                    exchange,
                    symbol,
                    market_type,
                    interval,
                    str(raw_timestamp),
                    ingested_at,
                    json.dumps(row, ensure_ascii=False, default=str),
                    data_version,
                )
            )
        if not payloads:
            return 0
        with self.connect() as conn:
            conn.executemany(
                """
                INSERT INTO ods_crypto_market_data_raw
                (data_type, source, exchange, symbol, market_type, interval, raw_timestamp, ingested_at,
                 raw_data, data_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                payloads,
            )
        return len(payloads)

    def upsert_dwd_crypto_exchange_info(self, rows: Iterable[dict[str, Any]]) -> int:
        now = _utc_now()
        payloads = []
        for row in rows:
            payloads.append(
                (
                    row.get("exchange", "okx"),
                    row.get("symbol", ""),
                    row.get("market_type", ""),
                    row.get("inst_id", ""),
                    row.get("base_currency"),
                    row.get("quote_currency"),
                    row.get("state"),
                    _optional_float(row.get("min_size")),
                    _optional_float(row.get("lot_size")),
                    _optional_float(row.get("tick_size")),
                    _optional_float(row.get("contract_value")),
                    json.dumps(row.get("raw_data", row), ensure_ascii=False, default=str),
                    now,
                    now,
                )
            )
        if not payloads:
            return 0
        with self.connect() as conn:
            conn.executemany(
                """
                INSERT INTO dwd_crypto_exchange_info
                (exchange, symbol, market_type, inst_id, base_currency, quote_currency, state, min_size,
                 lot_size, tick_size, contract_value, raw_data, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(exchange, symbol, market_type, inst_id) DO UPDATE SET
                    base_currency=excluded.base_currency,
                    quote_currency=excluded.quote_currency,
                    state=excluded.state,
                    min_size=excluded.min_size,
                    lot_size=excluded.lot_size,
                    tick_size=excluded.tick_size,
                    contract_value=excluded.contract_value,
                    raw_data=excluded.raw_data,
                    updated_at=excluded.updated_at
                """,
                payloads,
            )
        return len(payloads)

    def upsert_dwd_crypto_ohlcv(
        self,
        df: pd.DataFrame,
        *,
        exchange: str,
        interval: str,
        source: str = "okx",
    ) -> int:
        if df.empty:
            return 0
        now = _utc_now()
        payloads = []
        for _, row in df.iterrows():
            timestamp = _value_to_iso(row.get("ts"))
            if timestamp is None:
                continue
            payloads.append(
                (
                    exchange,
                    row.get("symbol", ""),
                    row.get("instrument_type", ""),
                    interval,
                    timestamp,
                    float(row.get("open")),
                    float(row.get("high")),
                    float(row.get("low")),
                    float(row.get("close")),
                    float(row.get("volume", 0.0)),
                    _optional_float(row.get("volume_quote")),
                    None,
                    1 if row.get("confirmed", True) else 0,
                    source,
                    now,
                    now,
                )
            )
        if not payloads:
            return 0
        with self.connect() as conn:
            conn.executemany(
                """
                INSERT INTO dwd_crypto_ohlcv
                (exchange, symbol, market_type, interval, timestamp, open, high, low, close, volume,
                 quote_volume, trade_count, is_closed, source, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(exchange, symbol, market_type, interval, timestamp) DO UPDATE SET
                    open=excluded.open,
                    high=excluded.high,
                    low=excluded.low,
                    close=excluded.close,
                    volume=excluded.volume,
                    quote_volume=excluded.quote_volume,
                    trade_count=excluded.trade_count,
                    is_closed=excluded.is_closed,
                    source=excluded.source,
                    updated_at=excluded.updated_at
                """,
                payloads,
            )
        return len(payloads)

    def upsert_dwd_crypto_funding_rate(
        self,
        df: pd.DataFrame,
        *,
        exchange: str,
        source: str = "okx",
    ) -> int:
        if df.empty:
            return 0
        now = _utc_now()
        payloads = []
        for _, row in df.iterrows():
            timestamp = _value_to_iso(row.get("ts"))
            if timestamp is None:
                continue
            payloads.append(
                (
                    exchange,
                    row.get("symbol", ""),
                    timestamp,
                    float(row.get("funding_rate")),
                    timestamp,
                    _optional_float(row.get("mark_price")),
                    _optional_float(row.get("index_price")),
                    source,
                    now,
                    now,
                )
            )
        if not payloads:
            return 0
        with self.connect() as conn:
            conn.executemany(
                """
                INSERT INTO dwd_crypto_funding_rate
                (exchange, symbol, timestamp, funding_rate, funding_time, mark_price, index_price,
                 source, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(exchange, symbol, timestamp) DO UPDATE SET
                    funding_rate=excluded.funding_rate,
                    funding_time=excluded.funding_time,
                    mark_price=excluded.mark_price,
                    index_price=excluded.index_price,
                    source=excluded.source,
                    updated_at=excluded.updated_at
                """,
                payloads,
            )
        return len(payloads)

    def upsert_dwd_crypto_open_interest(self, rows: Iterable[dict[str, Any]], source: str = "okx") -> int:
        now = _utc_now()
        payloads = []
        for row in rows:
            timestamp = _value_to_iso(row.get("ts"))
            if timestamp is None:
                continue
            payloads.append(
                (
                    row.get("exchange", "okx"),
                    row.get("symbol", ""),
                    row.get("market_type", "swap"),
                    row.get("inst_id", ""),
                    timestamp,
                    _optional_float(row.get("open_interest")),
                    _optional_float(row.get("open_interest_currency")),
                    source,
                    json.dumps(row.get("raw_data", row), ensure_ascii=False, default=str),
                    now,
                    now,
                )
            )
        if not payloads:
            return 0
        with self.connect() as conn:
            conn.executemany(
                """
                INSERT INTO dwd_crypto_open_interest
                (exchange, symbol, market_type, inst_id, timestamp, open_interest, open_interest_currency,
                 source, raw_data, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(exchange, symbol, market_type, timestamp) DO UPDATE SET
                    inst_id=excluded.inst_id,
                    open_interest=excluded.open_interest,
                    open_interest_currency=excluded.open_interest_currency,
                    source=excluded.source,
                    raw_data=excluded.raw_data,
                    updated_at=excluded.updated_at
                """,
                payloads,
            )
        return len(payloads)

    def upsert_dwd_crypto_basis(self, rows: Iterable[dict[str, Any]], source: str = "okx") -> int:
        now = _utc_now()
        payloads = []
        for row in rows:
            timestamp = _value_to_iso(row.get("ts"))
            if timestamp is None:
                continue
            payloads.append(
                (
                    row.get("exchange", "okx"),
                    row.get("symbol", ""),
                    row.get("market_type", "swap"),
                    row.get("inst_id", ""),
                    timestamp,
                    _optional_float(row.get("mark_price")),
                    _optional_float(row.get("index_price")),
                    _optional_float(row.get("basis")),
                    _optional_float(row.get("basis_pct")),
                    source,
                    json.dumps(row.get("raw_data", row), ensure_ascii=False, default=str),
                    now,
                    now,
                )
            )
        if not payloads:
            return 0
        with self.connect() as conn:
            conn.executemany(
                """
                INSERT INTO dwd_crypto_basis
                (exchange, symbol, market_type, inst_id, timestamp, mark_price, index_price, basis, basis_pct,
                 source, raw_data, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(exchange, symbol, market_type, timestamp) DO UPDATE SET
                    inst_id=excluded.inst_id,
                    mark_price=excluded.mark_price,
                    index_price=excluded.index_price,
                    basis=excluded.basis,
                    basis_pct=excluded.basis_pct,
                    source=excluded.source,
                    raw_data=excluded.raw_data,
                    updated_at=excluded.updated_at
                """,
                payloads,
            )
        return len(payloads)

    def upsert_dwd_crypto_long_short_ratio(self, rows: Iterable[dict[str, Any]], source: str = "okx") -> int:
        now = _utc_now()
        payloads = []
        for row in rows:
            timestamp = _value_to_iso(row.get("ts"))
            if timestamp is None:
                continue
            payloads.append(
                (
                    row.get("exchange", "okx"),
                    row.get("symbol", ""),
                    row.get("market_type", "swap"),
                    row.get("period", ""),
                    timestamp,
                    _optional_float(row.get("long_short_ratio")),
                    source,
                    json.dumps(row.get("raw_data", row), ensure_ascii=False, default=str),
                    now,
                    now,
                )
            )
        if not payloads:
            return 0
        with self.connect() as conn:
            conn.executemany(
                """
                INSERT INTO dwd_crypto_long_short_ratio
                (exchange, symbol, market_type, period, timestamp, long_short_ratio, source, raw_data,
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(exchange, symbol, market_type, period, timestamp) DO UPDATE SET
                    long_short_ratio=excluded.long_short_ratio,
                    source=excluded.source,
                    raw_data=excluded.raw_data,
                    updated_at=excluded.updated_at
                """,
                payloads,
            )
        return len(payloads)

    def upsert_dwd_crypto_orderbook_snapshot(self, rows: Iterable[dict[str, Any]], source: str = "okx") -> int:
        now = _utc_now()
        payloads = []
        for row in rows:
            timestamp = _value_to_iso(row.get("ts"))
            if timestamp is None:
                continue
            payloads.append(
                (
                    row.get("exchange", "okx"),
                    row.get("symbol", ""),
                    row.get("market_type", ""),
                    timestamp,
                    int(row.get("depth", 0) or 0),
                    row.get("side", ""),
                    float(row.get("price")),
                    float(row.get("size")),
                    _optional_int(row.get("order_count")),
                    source,
                    now,
                    now,
                )
            )
        if not payloads:
            return 0
        with self.connect() as conn:
            conn.executemany(
                """
                INSERT INTO dwd_crypto_orderbook_snapshot
                (exchange, symbol, market_type, timestamp, depth, side, price, size, order_count,
                 source, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(exchange, symbol, market_type, timestamp, depth, side, price) DO UPDATE SET
                    size=excluded.size,
                    order_count=excluded.order_count,
                    source=excluded.source,
                    updated_at=excluded.updated_at
                """,
                payloads,
            )
        return len(payloads)

    def upsert_dwd_crypto_trades(self, rows: Iterable[dict[str, Any]], source: str = "okx") -> int:
        now = _utc_now()
        payloads = []
        for row in rows:
            timestamp = _value_to_iso(row.get("ts"))
            if timestamp is None:
                continue
            payloads.append(
                (
                    row.get("exchange", "okx"),
                    row.get("symbol", ""),
                    row.get("market_type", ""),
                    str(row.get("trade_id", "")),
                    timestamp,
                    row.get("side", ""),
                    float(row.get("price")),
                    float(row.get("size")),
                    source,
                    json.dumps(row.get("raw_data", row), ensure_ascii=False, default=str),
                    now,
                    now,
                )
            )
        if not payloads:
            return 0
        with self.connect() as conn:
            conn.executemany(
                """
                INSERT INTO dwd_crypto_trades
                (exchange, symbol, market_type, trade_id, timestamp, side, price, size, source, raw_data,
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(exchange, symbol, market_type, trade_id) DO UPDATE SET
                    timestamp=excluded.timestamp,
                    side=excluded.side,
                    price=excluded.price,
                    size=excluded.size,
                    source=excluded.source,
                    raw_data=excluded.raw_data,
                    updated_at=excluded.updated_at
                """,
                payloads,
            )
        return len(payloads)

    def upsert_dwd_crypto_liquidations(self, rows: Iterable[dict[str, Any]], source: str = "okx") -> int:
        now = _utc_now()
        payloads = []
        for row in rows:
            timestamp = _value_to_iso(row.get("ts"))
            if timestamp is None:
                continue
            payloads.append(
                (
                    row.get("exchange", "okx"),
                    row.get("symbol", ""),
                    row.get("market_type", "swap"),
                    timestamp,
                    row.get("side"),
                    _optional_float(row.get("price")),
                    _optional_float(row.get("size")),
                    source,
                    json.dumps(row.get("raw_data", row), ensure_ascii=False, default=str),
                    now,
                    now,
                )
            )
        if not payloads:
            return 0
        with self.connect() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO dwd_crypto_liquidations
                (exchange, symbol, market_type, timestamp, side, price, size, source, raw_data,
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                payloads,
            )
        return len(payloads)

    def insert_ingestion_log(self, payload: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO data_ingestion_logs
                (task_id, source, exchange, symbol, market_type, data_type, interval, start_time, end_time,
                 status, records_fetched, records_inserted, records_updated, error_message, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.get("task_id", f"ingest-{datetime.now(timezone.utc).timestamp()}"),
                    payload.get("source", "unknown"),
                    payload.get("exchange", "unknown"),
                    payload.get("symbol", ""),
                    payload.get("market_type", ""),
                    payload.get("data_type", ""),
                    payload.get("interval"),
                    payload.get("start_time"),
                    payload.get("end_time"),
                    payload.get("status", "unknown"),
                    int(payload.get("records_fetched", 0) or 0),
                    int(payload.get("records_inserted", 0) or 0),
                    int(payload.get("records_updated", 0) or 0),
                    payload.get("error_message"),
                    payload.get("created_at", _utc_now()),
                ),
            )

    def upsert_ingestion_task(self, payload: dict[str, Any]) -> None:
        now = payload.get("updated_at", _utc_now())
        task_key = payload.get("task_key") or _task_key(payload)
        with self.connect() as conn:
            current = conn.execute(
                "SELECT retry_count FROM data_ingestion_tasks WHERE task_key = ?",
                (task_key,),
            ).fetchone()
            previous_retry_count = int(current["retry_count"]) if current else 0
            status = str(payload.get("status", "unknown"))
            retry_count = previous_retry_count + 1 if status == "error" else int(payload.get("retry_count", 0) or 0)
            conn.execute(
                """
                INSERT INTO data_ingestion_tasks
                (task_key, source, exchange, symbol, market_type, data_type, interval, status, retry_count,
                 last_watermark, last_error, updated_at, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_key) DO UPDATE SET
                    status=excluded.status,
                    retry_count=excluded.retry_count,
                    last_watermark=excluded.last_watermark,
                    last_error=excluded.last_error,
                    updated_at=excluded.updated_at,
                    payload=excluded.payload
                """,
                (
                    task_key,
                    payload.get("source", "unknown"),
                    payload.get("exchange", "unknown"),
                    payload.get("symbol", ""),
                    payload.get("market_type", ""),
                    payload.get("data_type", ""),
                    payload.get("interval"),
                    status,
                    retry_count,
                    payload.get("last_watermark") or payload.get("end_time"),
                    payload.get("last_error") or payload.get("error_message"),
                    now,
                    json.dumps(payload, ensure_ascii=False, default=str),
                ),
            )

    def insert_reproducibility_record(self, payload: dict[str, Any], artifact_path: Path | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO reproducibility_records
                (artifact_type, artifact_name, artifact_path, data_version, factor_version, code_fingerprint,
                 config_fingerprint, parameters, payload, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.get("artifact_type", ""),
                    payload.get("artifact_name", ""),
                    str(artifact_path) if artifact_path else payload.get("artifact_path"),
                    payload.get("data_version", "v1"),
                    payload.get("factor_version"),
                    payload.get("code_fingerprint", ""),
                    payload.get("config_fingerprint", ""),
                    json.dumps(payload.get("parameters", {}), ensure_ascii=False, default=str),
                    json.dumps(payload, ensure_ascii=False, default=str),
                    payload.get("created_at", _utc_now()),
                ),
            )

    def insert_data_quality_issues(self, issues: Iterable[dict[str, Any]]) -> int:
        now = _utc_now()
        payloads = []
        for issue in issues:
            payloads.append(
                (
                    issue.get("table_name", ""),
                    issue.get("exchange", "unknown"),
                    issue.get("symbol", ""),
                    issue.get("market_type", ""),
                    issue.get("interval"),
                    issue.get("timestamp"),
                    issue.get("issue_type", "unknown"),
                    issue.get("issue_detail", ""),
                    issue.get("severity", "warning"),
                    1 if issue.get("is_resolved") else 0,
                    issue.get("created_at", now),
                    issue.get("updated_at", now),
                )
            )
        if not payloads:
            return 0
        with self.connect() as conn:
            conn.executemany(
                """
                INSERT INTO data_quality_issues
                (table_name, exchange, symbol, market_type, interval, timestamp, issue_type, issue_detail,
                 severity, is_resolved, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                payloads,
            )
        return len(payloads)

    def upsert_factor_registry(
        self,
        *,
        factor_name: str,
        factor_category: str,
        version: str,
        description: str,
        formula: str | None,
        parameters: dict[str, Any],
        source_tables: list[str],
        target_table: str,
        is_active: bool = True,
    ) -> None:
        now = _utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO factor_registry
                (factor_name, factor_category, version, description, formula, parameters, source_tables,
                 target_table, is_active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(factor_name, version) DO UPDATE SET
                    factor_category=excluded.factor_category,
                    description=excluded.description,
                    formula=excluded.formula,
                    parameters=excluded.parameters,
                    source_tables=excluded.source_tables,
                    target_table=excluded.target_table,
                    is_active=excluded.is_active,
                    updated_at=excluded.updated_at
                """,
                (
                    factor_name,
                    factor_category,
                    version,
                    description,
                    formula,
                    json.dumps(parameters, ensure_ascii=False, default=str),
                    json.dumps(source_tables, ensure_ascii=False),
                    target_table,
                    1 if is_active else 0,
                    now,
                    now,
                ),
            )

    def insert_factor_calculation_log(self, payload: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO factor_calculation_logs
                (factor_name, source_table, target_table, symbol, interval, start_time, end_time, parameters,
                 status, records_calculated, error_message, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.get("factor_name", ""),
                    payload.get("source_table", ""),
                    payload.get("target_table", ""),
                    payload.get("symbol"),
                    payload.get("interval"),
                    payload.get("start_time"),
                    payload.get("end_time"),
                    json.dumps(payload.get("parameters", {}), ensure_ascii=False, default=str),
                    payload.get("status", "unknown"),
                    int(payload.get("records_calculated", 0) or 0),
                    payload.get("error_message"),
                    payload.get("created_at", _utc_now()),
                ),
            )

    def upsert_factor_values(
        self,
        *,
        factor_id: str,
        version: str,
        exchange: str,
        market_type: str,
        interval: str,
        factor_values: pd.DataFrame,
        parameters: dict[str, Any],
    ) -> int:
        if factor_values.empty:
            return 0
        now = _utc_now()
        values = []
        params_json = json.dumps(parameters, ensure_ascii=False, default=str)
        for _, row in factor_values.iterrows():
            factor_value = _optional_float(row.get("factor"))
            timestamp = _value_to_iso(row.get("ts"))
            if factor_value is None or timestamp is None:
                continue
            values.append(
                (
                    factor_id,
                    version,
                    exchange,
                    str(row.get("symbol", "")),
                    market_type,
                    interval,
                    timestamp,
                    factor_value,
                    params_json,
                    now,
                    now,
                )
            )
        if not values:
            return 0
        with self.connect() as conn:
            conn.executemany(
                """
                INSERT INTO dws_crypto_factor_values
                (factor_id, version, exchange, symbol, market_type, interval, timestamp, factor_value,
                 parameters, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(factor_id, version, exchange, symbol, market_type, interval, timestamp)
                DO UPDATE SET
                    factor_value=excluded.factor_value,
                    parameters=excluded.parameters,
                    updated_at=excluded.updated_at
                """,
                values,
            )
        return len(values)

    def insert_backtest_result(
        self,
        *,
        result: dict[str, Any],
        interval: str | None,
        initial_capital: float,
        final_capital: float | None,
        fee_assumption: float,
        slippage_assumption: float,
        report_path: Path | None = None,
    ) -> int:
        now = _utc_now()
        metrics = result.get("metrics", {})
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO ads_crypto_backtest_results
                (strategy_id, strategy_name, symbol, market_type, interval, start_time, end_time, initial_capital,
                 final_capital, total_return, annualized_return, max_drawdown, sharpe_ratio, sortino_ratio,
                 calmar_ratio, win_rate, profit_factor, average_profit, average_loss, profit_loss_ratio,
                 trade_count, fee_assumption, slippage_assumption, funding_fee_included, report_path, payload,
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.get("strategy", ""),
                    result.get("strategy", ""),
                    result.get("symbol", ""),
                    result.get("instrument_type", ""),
                    interval,
                    _result_time(result, "start"),
                    _result_time(result, "end"),
                    initial_capital,
                    final_capital,
                    metrics.get("total_return"),
                    metrics.get("annualized_return"),
                    metrics.get("max_drawdown"),
                    metrics.get("sharpe"),
                    metrics.get("sortino"),
                    metrics.get("calmar"),
                    metrics.get("win_rate"),
                    metrics.get("profit_factor"),
                    metrics.get("average_profit"),
                    metrics.get("average_loss"),
                    metrics.get("profit_loss_ratio"),
                    metrics.get("trade_count"),
                    fee_assumption,
                    slippage_assumption,
                    0,
                    str(report_path) if report_path else None,
                    json.dumps(_json_safe_result(result), ensure_ascii=False, default=str),
                    now,
                    now,
                ),
            )
            return int(cursor.lastrowid)

    def insert_backtest_trades(
        self,
        *,
        backtest_id: int,
        strategy_id: str,
        exchange: str,
        market_type: str,
        trades: pd.DataFrame,
    ) -> int:
        if trades.empty:
            return 0
        now = _utc_now()
        payloads = []
        for _, row in trades.iterrows():
            payloads.append(
                (
                    backtest_id,
                    strategy_id,
                    exchange,
                    row.get("symbol", ""),
                    market_type,
                    _value_to_iso(row.get("signal_ts") or row.get("ts")),
                    _value_to_iso(row.get("execution_ts") or row.get("ts")),
                    row.get("side", ""),
                    _optional_float(row.get("price")),
                    _optional_float(row.get("price")),
                    _optional_float(row.get("quantity")),
                    1.0,
                    None,
                    None,
                    0.0,
                    _optional_float(row.get("realized_pnl")),
                    _optional_float(row.get("realized_pnl")),
                    None,
                    None,
                    row.get("status"),
                    now,
                    now,
                )
            )
        with self.connect() as conn:
            conn.executemany(
                """
                INSERT INTO ads_crypto_backtest_trades
                (backtest_id, strategy_id, exchange, symbol, market_type, entry_time, exit_time, side,
                 entry_price, exit_price, position_size, leverage, fee, slippage, funding_fee, gross_pnl,
                 net_pnl, return_pct, holding_period, exit_reason, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                payloads,
            )
        return len(payloads)

    def insert_strategy_scores(self, payload: dict[str, Any]) -> int:
        now = _utc_now()
        rows = payload.get("ranked", []) if isinstance(payload.get("ranked"), list) else []
        if not rows:
            return 0
        values = []
        for row in rows:
            values.append(
                (
                    row.get("name", ""),
                    row.get("name", ""),
                    float(row.get("score", 0.0) or 0.0),
                    _optional_float(row.get("oos", {}).get("compounded_return") if isinstance(row.get("oos"), dict) else None),
                    _optional_float(row.get("oos", {}).get("worst_drawdown") if isinstance(row.get("oos"), dict) else None),
                    _optional_float(row.get("oos", {}).get("mean_sharpe") if isinstance(row.get("oos"), dict) else None),
                    _optional_float(row.get("oos", {}).get("positive_fold_rate") if isinstance(row.get("oos"), dict) else None),
                    _optional_float(row.get("costs", {}).get("positive_scenario_rate") if isinstance(row.get("costs"), dict) else None),
                    None,
                    None,
                    row.get("decision", "research_more"),
                    json.dumps(row, ensure_ascii=False, default=str),
                    now,
                    now,
                )
            )
        with self.connect() as conn:
            conn.executemany(
                """
                INSERT INTO ads_crypto_strategy_scores
                (strategy_id, strategy_name, score_total, score_return, score_drawdown, score_sharpe,
                 score_stability, score_cost_sensitivity, score_parameter_robustness,
                 score_market_regime_robustness, recommendation, payload, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )
        return len(values)

    def insert_ads_strategy_signal(
        self,
        signal: Signal,
        *,
        exchange: str = "okx",
        interval: str | None = None,
        strategy_id: str | None = None,
        source_factors: Iterable[str] | None = None,
    ) -> int:
        now = _utc_now()
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO ads_crypto_strategy_signals
                (strategy_id, strategy_name, exchange, symbol, market_type, interval, timestamp, signal,
                 signal_strength, signal_reason, source_factors, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    strategy_id or signal.strategy,
                    signal.strategy,
                    exchange,
                    signal.symbol,
                    signal.instrument_type.value,
                    interval,
                    signal.ts.isoformat(),
                    _target_pct_to_side(signal.target_pct),
                    signal.confidence,
                    signal.reason,
                    json.dumps(list(source_factors or []), ensure_ascii=False),
                    now,
                    now,
                ),
            )
            return int(cursor.lastrowid)

    def insert_ads_target_position(
        self,
        signal: Signal,
        *,
        exchange: str = "okx",
        strategy_id: str | None = None,
        leverage: float = 1.0,
        risk_limit: dict[str, Any] | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> int:
        now = _utc_now()
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO ads_crypto_target_positions
                (strategy_id, exchange, symbol, market_type, timestamp, target_side, target_position_ratio,
                 target_leverage, stop_loss, take_profit, risk_limit, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    strategy_id or signal.strategy,
                    exchange,
                    signal.symbol,
                    signal.instrument_type.value,
                    signal.ts.isoformat(),
                    _target_pct_to_side(signal.target_pct),
                    signal.target_pct,
                    leverage,
                    stop_loss,
                    take_profit,
                    json.dumps(risk_limit or {}, ensure_ascii=False, default=str),
                    now,
                    now,
                ),
            )
            return int(cursor.lastrowid)

    def insert_ads_risk_status(
        self,
        *,
        strategy_id: str | None,
        exchange: str,
        symbol: str,
        timestamp: datetime | str | None = None,
        current_position: float | None = None,
        current_drawdown: float | None = None,
        daily_loss: float | None = None,
        weekly_loss: float | None = None,
        risk_level: str = "low",
        is_trading_allowed: bool = True,
        stop_reason: str | None = None,
    ) -> int:
        now = _utc_now()
        if timestamp is None:
            timestamp_value = now
        elif hasattr(timestamp, "isoformat"):
            timestamp_value = timestamp.isoformat()
        else:
            timestamp_value = str(timestamp)
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO ads_crypto_risk_status
                (strategy_id, exchange, symbol, timestamp, current_position, current_drawdown, daily_loss,
                 weekly_loss, risk_level, is_trading_allowed, stop_reason, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    strategy_id,
                    exchange,
                    symbol,
                    timestamp_value,
                    current_position,
                    current_drawdown,
                    daily_loss,
                    weekly_loss,
                    risk_level,
                    1 if is_trading_allowed else 0,
                    stop_reason,
                    now,
                    now,
                ),
            )
            return int(cursor.lastrowid)

    def insert_ads_service_run(
        self,
        *,
        service_name: str,
        mode: str,
        strategy_id: str | None,
        symbols: Iterable[str],
        market_type: str,
        interval: str | None,
        started_at: str | None,
        completed_at: str | None = None,
        iteration: int | None = None,
        ok: bool,
        result: dict[str, Any] | None = None,
        consecutive_errors: int | None = None,
        stop_reason: str | None = None,
        payload: dict[str, Any] | None = None,
        exchange: str = "okx",
    ) -> int:
        now = _utc_now()
        result = result or {}
        payload = payload or {}
        orders = result.get("orders", []) if isinstance(result.get("orders"), list) else []
        messages = result.get("messages", []) if isinstance(result.get("messages"), list) else []
        selected = result.get("selected", []) if isinstance(result.get("selected"), list) else []
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO ads_crypto_service_runs
                (service_name, mode, strategy_id, exchange, symbols, market_type, interval, started_at,
                 completed_at, iteration, ok, order_count, message_count, selected_count, stale_data,
                 cooldown_active, circuit_breaker, consecutive_errors, stop_reason, payload, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    service_name,
                    mode,
                    strategy_id,
                    exchange,
                    json.dumps(list(symbols), ensure_ascii=False),
                    market_type,
                    interval,
                    started_at,
                    completed_at or now,
                    iteration,
                    1 if ok else 0,
                    len(orders),
                    len(messages),
                    len(selected),
                    _optional_bool_int(result.get("stale_data")),
                    _optional_bool_int(result.get("cooldown_active")),
                    _optional_bool_int(result.get("circuit_breaker")),
                    consecutive_errors,
                    stop_reason,
                    json.dumps(payload, ensure_ascii=False, default=str),
                    now,
                    now,
                ),
            )
            return int(cursor.lastrowid)

    def upsert_review_tasks(self, tasks: Iterable[dict[str, Any]]) -> int:
        now = _utc_now()
        rows = []
        for task in tasks:
            rows.append(
                (
                    str(task.get("source_type", "")),
                    str(task.get("source_id", "")),
                    str(task.get("category", "general")),
                    str(task.get("severity", "info")),
                    str(task.get("status", "open")),
                    str(task.get("title", "")),
                    str(task.get("details", "")),
                    json.dumps(task, ensure_ascii=False, default=str),
                    now,
                    now,
                )
            )
        if not rows:
            return 0
        with self.connect() as conn:
            conn.executemany(
                """
                INSERT INTO review_tasks
                (source_type, source_id, category, severity, status, title, details, payload, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_type, source_id) DO UPDATE SET
                    category=excluded.category,
                    severity=excluded.severity,
                    status=excluded.status,
                    title=excluded.title,
                    details=excluded.details,
                    payload=excluded.payload,
                    updated_at=excluded.updated_at
                """,
                rows,
            )
        return len(rows)

    def upsert_strategy_registry(self, strategy: dict[str, Any]) -> None:
        now = _utc_now()
        sources = strategy.get("sources") if isinstance(strategy.get("sources"), list) else []
        first_source = sources[0] if sources and isinstance(sources[0], dict) else {}
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO strategy_registry
                (strategy_id, strategy_name, strategy_type, source, source_url, description, core_logic,
                 data_requirements, factors_used, entry_rules, exit_rules, position_sizing, risk_management,
                 status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(strategy_id) DO UPDATE SET
                    strategy_name=excluded.strategy_name,
                    strategy_type=excluded.strategy_type,
                    source=excluded.source,
                    source_url=excluded.source_url,
                    description=excluded.description,
                    core_logic=excluded.core_logic,
                    data_requirements=excluded.data_requirements,
                    factors_used=excluded.factors_used,
                    entry_rules=excluded.entry_rules,
                    exit_rules=excluded.exit_rules,
                    position_sizing=excluded.position_sizing,
                    risk_management=excluded.risk_management,
                    status=excluded.status,
                    updated_at=excluded.updated_at
                """,
                (
                    strategy.get("id", ""),
                    strategy.get("name", strategy.get("id", "")),
                    strategy.get("family", "unknown"),
                    strategy.get("source_type") or first_source.get("title"),
                    first_source.get("url"),
                    strategy.get("recommendation", ""),
                    strategy.get("logic", ""),
                    json.dumps(strategy.get("data_requirements", []), ensure_ascii=False, default=str),
                    json.dumps(strategy.get("factors_used", []), ensure_ascii=False, default=str),
                    strategy.get("entry_rules", ""),
                    strategy.get("exit_rules", ""),
                    strategy.get("position_sizing", ""),
                    json.dumps(strategy.get("risk_management", []), ensure_ascii=False, default=str),
                    strategy.get("promotion_status") or strategy.get("strategy_pipeline_status") or "unknown",
                    now,
                    now,
                ),
            )

    def insert_signal(self, signal: Signal) -> None:
        payload = dataclass_to_dict(signal)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO signals (ts, symbol, instrument_type, strategy, target_pct, confidence, reason, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal.ts.isoformat(),
                    signal.symbol,
                    signal.instrument_type.value,
                    signal.strategy,
                    signal.target_pct,
                    signal.confidence,
                    signal.reason,
                    json.dumps(payload, ensure_ascii=False),
                ),
            )

    def insert_order(self, order: Order) -> None:
        payload = dataclass_to_dict(order)
        intent = order.intent
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO orders
                (client_order_id, created_at, symbol, instrument_type, side, quantity, order_type, status,
                 filled_quantity, average_price, exchange_order_id, message, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    intent.client_order_id,
                    order.created_at.isoformat(),
                    intent.symbol,
                    intent.instrument_type.value,
                    intent.side.value,
                    intent.quantity,
                    intent.order_type.value,
                    order.status.value,
                    order.filled_quantity,
                    order.average_price,
                    order.exchange_order_id,
                    order.message,
                    json.dumps(payload, ensure_ascii=False),
                ),
            )

    def upsert_position(self, position: Position) -> None:
        key = position_key(position.symbol, position.instrument_type)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO positions
                (key, symbol, instrument_type, quantity, average_entry, realized_pnl, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    key,
                    position.symbol,
                    position.instrument_type.value,
                    position.quantity,
                    position.average_entry,
                    position.realized_pnl,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def insert_risk_event(self, signal_or_order: Any, decision: RiskDecision) -> None:
        symbol = getattr(signal_or_order, "symbol", getattr(signal_or_order, "intent", signal_or_order).symbol)
        instrument_type = getattr(
            signal_or_order, "instrument_type", getattr(signal_or_order, "intent", signal_or_order).instrument_type
        )
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO risk_events (ts, symbol, instrument_type, approved, reason, payload)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now(timezone.utc).isoformat(),
                    symbol,
                    instrument_type.value,
                    1 if decision.approved else 0,
                    decision.reason,
                    json.dumps(dataclass_to_dict(decision), ensure_ascii=False),
                ),
            )

    def latest_orders(self, limit: int = 10) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return list(conn.execute("SELECT * FROM orders ORDER BY created_at DESC LIMIT ?", (limit,)))

    def latest_risk_events(self, limit: int = 10) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return list(conn.execute("SELECT * FROM risk_events ORDER BY ts DESC LIMIT ?", (limit,)))

    def recent_rows(self, table: str, limit: int = 10) -> list[sqlite3.Row]:
        allowed = {
            "backtests": ("ads_crypto_backtest_results", "created_at"),
            "strategy_scores": ("ads_crypto_strategy_scores", "created_at"),
            "quality_issues": ("data_quality_issues", "created_at"),
            "reproducibility": ("reproducibility_records", "created_at"),
            "ingestion_tasks": ("data_ingestion_tasks", "updated_at"),
            "ingestion_logs": ("data_ingestion_logs", "created_at"),
            "service_runs": ("ads_crypto_service_runs", "created_at"),
            "review_tasks": ("review_tasks", "updated_at"),
            "raw_market_data": ("ods_crypto_market_data_raw", "ingested_at"),
            "open_interest": ("dwd_crypto_open_interest", "updated_at"),
            "basis": ("dwd_crypto_basis", "updated_at"),
            "long_short_ratio": ("dwd_crypto_long_short_ratio", "updated_at"),
            "orderbook": ("dwd_crypto_orderbook_snapshot", "updated_at"),
            "trades": ("dwd_crypto_trades", "updated_at"),
            "liquidations": ("dwd_crypto_liquidations", "updated_at"),
        }
        if table not in allowed:
            raise ValueError(f"unknown query table: {table}")
        sql_table, order_column = allowed[table]
        with self.connect() as conn:
            return list(conn.execute(f"SELECT * FROM {sql_table} ORDER BY {order_column} DESC LIMIT ?", (limit,)))

    def set_state(self, key: str, value: Any) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO run_state (key, value, updated_at) VALUES (?, ?, ?)",
                (key, json.dumps(value, ensure_ascii=False), datetime.now(timezone.utc).isoformat()),
            )

    def get_state(self, key: str, default: Any = None) -> Any:
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM run_state WHERE key = ?", (key,)).fetchone()
        if row is None:
            return default
        return json.loads(row["value"])


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _value_to_iso(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _optional_float(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    try:
        if value is None or pd.isna(value):
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _json_safe_result(result: dict[str, Any]) -> dict[str, Any]:
    safe = {}
    for key, value in result.items():
        if isinstance(value, pd.DataFrame):
            safe[key] = value.tail(50).to_dict("records")
        else:
            safe[key] = value
    return safe


def _result_time(result: dict[str, Any], edge: str) -> str | None:
    curve = result.get("equity_curve")
    if not isinstance(curve, pd.DataFrame) or curve.empty or "ts" not in curve:
        return None
    ts = curve["ts"].iloc[0] if edge == "start" else curve["ts"].iloc[-1]
    return _value_to_iso(ts)


def _task_key(payload: dict[str, Any]) -> str:
    parts = [
        payload.get("source", "unknown"),
        payload.get("exchange", "unknown"),
        payload.get("symbol", ""),
        payload.get("market_type", ""),
        payload.get("data_type", ""),
        payload.get("interval") or "",
    ]
    return "|".join(str(part) for part in parts)


def _target_pct_to_side(target_pct: float) -> str:
    if target_pct > 0:
        return "long"
    if target_pct < 0:
        return "short"
    return "flat"


def _optional_bool_int(value: Any) -> int | None:
    if value is None:
        return None
    return 1 if bool(value) else 0
