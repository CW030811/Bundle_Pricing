from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd

from .config import AppConfig, okx_inst_id, symbol_from_okx_inst_id
from .data_quality import check_ohlcv_quality
from .okx import OkxRestClient
from .reproducibility import reproducibility_payload
from .storage import AuditStore, CandleStore, FundingRateStore, normalize_okx_candles, normalize_okx_funding_rates

EXCLUDED_BASE_ASSETS = {
    "USDT",
    "USDC",
    "DAI",
    "FDUSD",
    "TUSD",
    "PYUSD",
    "USDG",
    "USD1",
}


def backfill_candles(
    config: AppConfig,
    client: OkxRestClient,
    symbols: Iterable[str] | None = None,
    instrument_types: Iterable[str] | None = None,
    bar: str | None = None,
    limit: int = 300,
) -> list[Path]:
    store = CandleStore(config.data_dir)
    audit = AuditStore(config.state_dir)
    written: list[Path] = []
    selected_symbols = list(symbols or config.market.symbols)
    selected_types = list(instrument_types or config.market.instrument_types)
    selected_bar = bar or config.market.bar
    for instrument_type in selected_types:
        for symbol in selected_symbols:
            rows = client.get_candles(symbol, instrument_type, selected_bar, limit=limit)
            raw_inserted = audit.insert_ods_crypto_ohlcv_raw(
                rows,
                source="okx_rest_market_candles",
                exchange="okx",
                symbol=symbol,
                market_type=instrument_type,
                interval=selected_bar,
            )
            df = normalize_okx_candles(rows, symbol, instrument_type)
            issues = check_ohlcv_quality(
                df,
                exchange="okx",
                symbol=symbol,
                market_type=instrument_type,
                interval=selected_bar,
            )
            audit.insert_data_quality_issues(issues)
            if not df.empty:
                audit.upsert_dwd_crypto_ohlcv(df, exchange="okx", interval=selected_bar)
                written.append(store.write(df, symbol, instrument_type, selected_bar))
            audit.insert_ingestion_log(
                payload := _ingestion_payload(
                    source="okx",
                    exchange="okx",
                    symbol=symbol,
                    market_type=instrument_type,
                    data_type="ohlcv",
                    interval=selected_bar,
                    status="ok",
                    records_fetched=len(rows),
                    records_inserted=raw_inserted,
                    records_updated=len(df),
                    start_time=_df_time(df, "start"),
                    end_time=_df_time(df, "end"),
                )
            )
            audit.upsert_ingestion_task({**payload, "last_watermark": _df_time(df, "end")})
            audit.insert_reproducibility_record(
                reproducibility_payload(
                    config,
                    artifact_type="backfill",
                    artifact_name="ohlcv",
                    data_version="v1",
                    parameters={"symbol": symbol, "market_type": instrument_type, "interval": selected_bar, "limit": limit},
                )
            )
    return written


def backfill_history_candles(
    config: AppConfig,
    client: OkxRestClient,
    symbols: Iterable[str] | None = None,
    instrument_types: Iterable[str] | None = None,
    bar: str | None = None,
    pages: int = 10,
    page_limit: int = 100,
) -> list[Path]:
    store = CandleStore(config.data_dir)
    audit = AuditStore(config.state_dir)
    written: list[Path] = []
    selected_symbols = list(symbols or config.market.symbols)
    selected_types = list(instrument_types or config.market.instrument_types)
    selected_bar = bar or config.market.bar
    for instrument_type in selected_types:
        for symbol in selected_symbols:
            all_rows: list[list[str]] = []
            after = None
            for _ in range(max(pages, 1)):
                rows = client.get_history_candles(
                    symbol,
                    instrument_type,
                    selected_bar,
                    after=after,
                    limit=page_limit,
                )
                if not rows:
                    break
                all_rows.extend(rows)
                oldest_ts = min(int(row[0]) for row in rows if row)
                next_after = str(oldest_ts)
                if next_after == after:
                    break
                after = next_after
            raw_inserted = audit.insert_ods_crypto_ohlcv_raw(
                all_rows,
                source="okx_rest_market_history_candles",
                exchange="okx",
                symbol=symbol,
                market_type=instrument_type,
                interval=selected_bar,
            )
            df = normalize_okx_candles(all_rows, symbol, instrument_type)
            issues = check_ohlcv_quality(
                df,
                exchange="okx",
                symbol=symbol,
                market_type=instrument_type,
                interval=selected_bar,
            )
            audit.insert_data_quality_issues(issues)
            if not df.empty:
                audit.upsert_dwd_crypto_ohlcv(df, exchange="okx", interval=selected_bar)
                written.append(store.write(df, symbol, instrument_type, selected_bar))
            audit.insert_ingestion_log(
                payload := _ingestion_payload(
                    source="okx",
                    exchange="okx",
                    symbol=symbol,
                    market_type=instrument_type,
                    data_type="ohlcv_history",
                    interval=selected_bar,
                    status="ok",
                    records_fetched=len(all_rows),
                    records_inserted=raw_inserted,
                    records_updated=len(df),
                    start_time=_df_time(df, "start"),
                    end_time=_df_time(df, "end"),
                )
            )
            audit.upsert_ingestion_task({**payload, "last_watermark": _df_time(df, "end")})
            audit.insert_reproducibility_record(
                reproducibility_payload(
                    config,
                    artifact_type="backfill",
                    artifact_name="ohlcv_history",
                    data_version="v1",
                    parameters={
                        "symbol": symbol,
                        "market_type": instrument_type,
                        "interval": selected_bar,
                        "pages": pages,
                        "page_limit": page_limit,
                    },
                )
            )
    return written


def backfill_funding_rates(
    config: AppConfig,
    client: OkxRestClient,
    symbols: Iterable[str] | None = None,
    pages: int = 10,
    page_limit: int = 100,
) -> list[Path]:
    store = FundingRateStore(config.data_dir)
    audit = AuditStore(config.state_dir)
    written: list[Path] = []
    selected_symbols = list(symbols or config.market.symbols)
    for symbol in selected_symbols:
        all_rows: list[dict[str, object]] = []
        after = None
        error_message = None
        for _ in range(max(pages, 1)):
            try:
                rows = client.get_funding_rate_history(symbol, after=after, limit=page_limit)
            except Exception as exc:
                error_message = f"{type(exc).__name__}: {exc}"
                break
            if not rows:
                break
            all_rows.extend(rows)
            oldest_ts = min(int(row["fundingTime"]) for row in rows if row.get("fundingTime"))
            next_after = str(oldest_ts)
            if next_after == after:
                break
            after = next_after
        raw_inserted = audit.insert_ods_crypto_funding_rate_raw(
            all_rows,
            source="okx_rest_public_funding_rate_history",
            exchange="okx",
            symbol=symbol,
        )
        df = normalize_okx_funding_rates(all_rows, symbol)
        if not df.empty:
            audit.upsert_dwd_crypto_funding_rate(df, exchange="okx")
            written.append(store.write(df, symbol))
        audit.insert_ingestion_log(
            payload := _ingestion_payload(
                source="okx",
                exchange="okx",
                symbol=symbol,
                market_type="swap",
                data_type="funding_rate",
                interval="8H",
                status="partial" if error_message else "ok",
                records_fetched=len(all_rows),
                records_inserted=raw_inserted,
                records_updated=len(df),
                start_time=_df_time(df, "start"),
                end_time=_df_time(df, "end"),
                error_message=error_message,
            )
        )
        audit.upsert_ingestion_task({**payload, "last_watermark": _df_time(df, "end")})
        audit.insert_reproducibility_record(
            reproducibility_payload(
                config,
                artifact_type="backfill",
                artifact_name="funding_rate",
                data_version="v1",
                parameters={"symbol": symbol, "market_type": "swap", "pages": pages, "page_limit": page_limit},
            )
        )
    return written


def backfill_exchange_info(
    config: AppConfig,
    client: OkxRestClient,
    instrument_types: Iterable[str] | None = None,
) -> dict[str, object]:
    audit = AuditStore(config.state_dir)
    selected_types = list(instrument_types or config.market.instrument_types)
    rows_written = 0
    raw_written = 0
    by_type: dict[str, int] = {}
    for instrument_type in selected_types:
        rows = client.get_instruments(instrument_type)
        raw_inserted = audit.insert_ods_crypto_exchange_info_raw(
            rows,
            source="okx_rest_public_instruments",
            exchange="okx",
            market_type=instrument_type,
        )
        normalized = normalize_okx_exchange_info(rows, instrument_type)
        dwd_inserted = audit.upsert_dwd_crypto_exchange_info(normalized)
        audit.insert_ingestion_log(
            payload := _ingestion_payload(
                source="okx",
                exchange="okx",
                symbol="*",
                market_type=instrument_type,
                data_type="exchange_info",
                interval=None,
                status="ok",
                records_fetched=len(rows),
                records_inserted=raw_inserted,
                records_updated=dwd_inserted,
            )
        )
        audit.upsert_ingestion_task({**payload, "last_watermark": datetime.now(timezone.utc).isoformat()})
        audit.insert_reproducibility_record(
            reproducibility_payload(
                config,
                artifact_type="backfill",
                artifact_name="exchange_info",
                data_version="v1",
                parameters={"market_type": instrument_type},
            )
        )
        raw_written += raw_inserted
        rows_written += dwd_inserted
        by_type[instrument_type] = dwd_inserted
    return {
        "raw_rows": raw_written,
        "dwd_rows": rows_written,
        "by_instrument_type": by_type,
    }


def backfill_open_interest(
    config: AppConfig,
    client: OkxRestClient,
    symbols: Iterable[str] | None = None,
) -> dict[str, object]:
    audit = AuditStore(config.state_dir)
    selected_symbols = list(symbols or config.market.symbols)
    return _backfill_symbol_market_data(
        config,
        audit,
        selected_symbols,
        "swap",
        "open_interest",
        "okx_rest_public_open_interest",
        lambda symbol: client.get_open_interest(symbol, "swap"),
        normalize_okx_open_interest,
        audit.upsert_dwd_crypto_open_interest,
    )


def backfill_basis(
    config: AppConfig,
    client: OkxRestClient,
    symbols: Iterable[str] | None = None,
) -> dict[str, object]:
    audit = AuditStore(config.state_dir)
    selected_symbols = list(symbols or config.market.symbols)
    return _backfill_symbol_market_data(
        config,
        audit,
        selected_symbols,
        "swap",
        "basis",
        "okx_rest_public_mark_price_index_ticker",
        lambda symbol: [build_okx_basis_raw(symbol, client.get_mark_price(symbol, "swap"), client.get_index_ticker(symbol))],
        normalize_okx_basis,
        audit.upsert_dwd_crypto_basis,
    )


def backfill_long_short_ratio(
    config: AppConfig,
    client: OkxRestClient,
    symbols: Iterable[str] | None = None,
    period: str = "5m",
    limit: int = 100,
) -> dict[str, object]:
    audit = AuditStore(config.state_dir)
    selected_symbols = list(symbols or config.market.symbols)
    return _backfill_symbol_market_data(
        config,
        audit,
        selected_symbols,
        "swap",
        "long_short_ratio",
        "okx_rest_rubik_contract_long_short_ratio",
        lambda symbol: client.get_contract_long_short_ratio(symbol, period=period, limit=limit),
        lambda rows, symbol, market_type: normalize_okx_long_short_ratio(rows, symbol, period),
        audit.upsert_dwd_crypto_long_short_ratio,
        interval=period,
        parameters={"period": period, "limit": limit},
    )


def backfill_orderbook(
    config: AppConfig,
    client: OkxRestClient,
    symbols: Iterable[str] | None = None,
    instrument_type: str = "spot",
    depth: int = 50,
) -> dict[str, object]:
    audit = AuditStore(config.state_dir)
    selected_symbols = list(symbols or config.market.symbols)
    return _backfill_symbol_market_data(
        config,
        audit,
        selected_symbols,
        instrument_type,
        "orderbook_snapshot",
        "okx_rest_market_books",
        lambda symbol: [client.get_orderbook(symbol, instrument_type, depth=depth)],
        lambda rows, symbol, market_type: normalize_okx_orderbook(rows, symbol, market_type, depth=depth),
        audit.upsert_dwd_crypto_orderbook_snapshot,
        parameters={"depth": depth},
    )


def backfill_recent_trades(
    config: AppConfig,
    client: OkxRestClient,
    symbols: Iterable[str] | None = None,
    instrument_type: str = "spot",
    limit: int = 100,
) -> dict[str, object]:
    audit = AuditStore(config.state_dir)
    selected_symbols = list(symbols or config.market.symbols)
    return _backfill_symbol_market_data(
        config,
        audit,
        selected_symbols,
        instrument_type,
        "trades",
        "okx_rest_market_trades",
        lambda symbol: client.get_recent_trades(symbol, instrument_type, limit=limit),
        normalize_okx_trades,
        audit.upsert_dwd_crypto_trades,
        parameters={"limit": limit},
    )


def backfill_liquidations(
    config: AppConfig,
    client: OkxRestClient,
    symbols: Iterable[str] | None = None,
    limit: int = 100,
) -> dict[str, object]:
    audit = AuditStore(config.state_dir)
    selected_symbols = list(symbols or config.market.symbols)
    return _backfill_symbol_market_data(
        config,
        audit,
        selected_symbols,
        "swap",
        "liquidations",
        "okx_rest_public_liquidation_orders",
        lambda symbol: client.get_liquidation_orders(symbol, "swap", limit=limit),
        normalize_okx_liquidations,
        audit.upsert_dwd_crypto_liquidations,
        parameters={"limit": limit},
    )


def _backfill_symbol_market_data(
    config: AppConfig,
    audit: AuditStore,
    symbols: list[str],
    market_type: str,
    data_type: str,
    source: str,
    fetcher,
    normalizer,
    writer,
    interval: str | None = None,
    parameters: dict[str, object] | None = None,
) -> dict[str, object]:
    raw_written = 0
    dwd_written = 0
    errors: dict[str, str] = {}
    by_symbol: dict[str, int] = {}
    parameters = parameters or {}
    for symbol in symbols:
        rows: list[dict[str, object]] = []
        error_message = None
        try:
            rows = [row for row in fetcher(symbol) if row]
        except Exception as exc:
            error_message = f"{type(exc).__name__}: {exc}"
            errors[symbol] = error_message
        raw_inserted = audit.insert_ods_crypto_market_data_raw(
            rows,
            data_type=data_type,
            source=source,
            exchange="okx",
            symbol=symbol,
            market_type=market_type,
            interval=interval,
        )
        normalized = normalizer(rows, symbol, market_type)
        dwd_inserted = writer(normalized)
        df = pd.DataFrame(normalized)
        audit.insert_ingestion_log(
            payload := _ingestion_payload(
                source="okx",
                exchange="okx",
                symbol=symbol,
                market_type=market_type,
                data_type=data_type,
                interval=interval,
                status="error" if error_message else "ok",
                records_fetched=len(rows),
                records_inserted=raw_inserted,
                records_updated=dwd_inserted,
                start_time=_df_time(df, "start"),
                end_time=_df_time(df, "end"),
                error_message=error_message,
            )
        )
        audit.upsert_ingestion_task({**payload, "last_watermark": _df_time(df, "end")})
        audit.insert_reproducibility_record(
            reproducibility_payload(
                config,
                artifact_type="backfill",
                artifact_name=data_type,
                data_version="v1",
                parameters={"symbol": symbol, "market_type": market_type, **parameters},
            )
        )
        raw_written += raw_inserted
        dwd_written += dwd_inserted
        by_symbol[symbol] = dwd_inserted
    return {
        "data_type": data_type,
        "market_type": market_type,
        "raw_rows": raw_written,
        "dwd_rows": dwd_written,
        "by_symbol": by_symbol,
        "errors": errors,
    }


def normalize_okx_exchange_info(rows: Iterable[dict[str, object]], instrument_type: str) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    for row in rows:
        inst_id = str(row.get("instId", ""))
        try:
            symbol, parsed_type = symbol_from_okx_inst_id(inst_id)
        except ValueError:
            symbol, parsed_type = inst_id, instrument_type
        normalized.append(
            {
                "exchange": "okx",
                "symbol": symbol,
                "market_type": parsed_type or instrument_type,
                "inst_id": inst_id,
                "base_currency": row.get("baseCcy") or row.get("uly"),
                "quote_currency": row.get("quoteCcy") or row.get("settleCcy"),
                "state": row.get("state"),
                "min_size": row.get("minSz"),
                "lot_size": row.get("lotSz"),
                "tick_size": row.get("tickSz"),
                "contract_value": row.get("ctVal"),
                "raw_data": row,
            }
        )
    return normalized


def normalize_okx_open_interest(
    rows: Iterable[dict[str, object]],
    symbol: str,
    market_type: str,
) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    for row in rows:
        ts = _okx_ms_to_timestamp(row.get("ts"))
        if ts is None:
            continue
        normalized.append(
            {
                "exchange": "okx",
                "symbol": symbol,
                "market_type": market_type,
                "inst_id": row.get("instId") or okx_inst_id(symbol, market_type),
                "ts": ts,
                "open_interest": row.get("oi"),
                "open_interest_currency": row.get("oiCcy"),
                "source": "okx",
                "raw_data": row,
            }
        )
    return normalized


def build_okx_basis_raw(symbol: str, mark: dict[str, object], index: dict[str, object]) -> dict[str, object]:
    return {
        "symbol": symbol,
        "mark": mark,
        "index": index,
        "ts": mark.get("ts") or index.get("ts"),
    }


def normalize_okx_basis(
    rows: Iterable[dict[str, object]],
    symbol: str,
    market_type: str,
) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    for row in rows:
        mark = row.get("mark") if isinstance(row.get("mark"), dict) else {}
        index = row.get("index") if isinstance(row.get("index"), dict) else {}
        ts = _okx_ms_to_timestamp(row.get("ts") or mark.get("ts") or index.get("ts"))
        if ts is None:
            continue
        mark_price = _safe_optional_float(mark.get("markPx"))
        index_price = _safe_optional_float(index.get("idxPx") or index.get("indexPx"))
        basis = mark_price - index_price if mark_price is not None and index_price is not None else None
        basis_pct = basis / index_price if basis is not None and index_price not in (None, 0) else None
        normalized.append(
            {
                "exchange": "okx",
                "symbol": symbol,
                "market_type": market_type,
                "inst_id": mark.get("instId") or okx_inst_id(symbol, market_type),
                "ts": ts,
                "mark_price": mark_price,
                "index_price": index_price,
                "basis": basis,
                "basis_pct": basis_pct,
                "source": "okx",
                "raw_data": row,
            }
        )
    return normalized


def normalize_okx_long_short_ratio(
    rows: Iterable[dict[str, object] | list[object]],
    symbol: str,
    period: str,
) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    for row in rows:
        if isinstance(row, (list, tuple)):
            ts_raw = row[0] if row else None
            ratio = row[1] if len(row) > 1 else None
            raw = {"ts": ts_raw, "longShortRatio": ratio}
        else:
            ts_raw = row.get("ts")
            ratio = row.get("longShortRatio") or row.get("ratio")
            raw = row
        ts = _okx_ms_to_timestamp(ts_raw)
        if ts is None:
            continue
        normalized.append(
            {
                "exchange": "okx",
                "symbol": symbol,
                "market_type": "swap",
                "period": period,
                "ts": ts,
                "long_short_ratio": ratio,
                "source": "okx",
                "raw_data": raw,
            }
        )
    return normalized


def normalize_okx_orderbook(
    rows: Iterable[dict[str, object]],
    symbol: str,
    market_type: str,
    depth: int,
) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    for row in rows:
        ts = _okx_ms_to_timestamp(row.get("ts"))
        if ts is None:
            continue
        for side_name, levels in [("ask", row.get("asks", [])), ("bid", row.get("bids", []))]:
            if not isinstance(levels, list):
                continue
            for level_idx, level in enumerate(levels[:depth], start=1):
                if not isinstance(level, (list, tuple)) or len(level) < 2:
                    continue
                normalized.append(
                    {
                        "exchange": "okx",
                        "symbol": symbol,
                        "market_type": market_type,
                        "ts": ts,
                        "depth": level_idx,
                        "side": side_name,
                        "price": level[0],
                        "size": level[1],
                        "order_count": level[3] if len(level) > 3 else None,
                        "source": "okx",
                    }
                )
    return normalized


def normalize_okx_trades(
    rows: Iterable[dict[str, object]],
    symbol: str,
    market_type: str,
) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    for row in rows:
        ts = _okx_ms_to_timestamp(row.get("ts"))
        if ts is None:
            continue
        normalized.append(
            {
                "exchange": "okx",
                "symbol": symbol,
                "market_type": market_type,
                "trade_id": row.get("tradeId") or f"{symbol}-{row.get('ts')}-{row.get('px')}-{row.get('sz')}",
                "ts": ts,
                "side": row.get("side"),
                "price": row.get("px"),
                "size": row.get("sz"),
                "source": "okx",
                "raw_data": row,
            }
        )
    return normalized


def normalize_okx_liquidations(
    rows: Iterable[dict[str, object]],
    symbol: str,
    market_type: str,
) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    for row in rows:
        detail_rows = row.get("details") if isinstance(row.get("details"), list) else [row]
        for detail in detail_rows:
            if not isinstance(detail, dict):
                continue
            inst_id = str(detail.get("instId") or row.get("instId") or "")
            try:
                parsed_symbol, parsed_type = symbol_from_okx_inst_id(inst_id) if inst_id else (symbol, market_type)
            except ValueError:
                parsed_symbol, parsed_type = symbol, market_type
            if parsed_symbol != symbol:
                continue
            ts = _okx_ms_to_timestamp(detail.get("ts") or detail.get("bkTime") or row.get("ts"))
            if ts is None:
                continue
            normalized.append(
                {
                    "exchange": "okx",
                    "symbol": parsed_symbol,
                    "market_type": parsed_type,
                    "ts": ts,
                    "side": detail.get("side") or row.get("side"),
                    "price": detail.get("bkPx") or detail.get("px") or detail.get("price"),
                    "size": detail.get("sz") or detail.get("size"),
                    "source": "okx",
                    "raw_data": {"parent": row, "detail": detail},
                }
            )
    return normalized


def _okx_ms_to_timestamp(value: object) -> pd.Timestamp | None:
    if value in (None, ""):
        return None
    try:
        return pd.to_datetime(int(value), unit="ms", utc=True)
    except (TypeError, ValueError):
        return None


def _safe_optional_float(value: object) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def load_candles(config: AppConfig, symbol: str, instrument_type: str, bar: str | None = None) -> pd.DataFrame:
    return CandleStore(config.data_dir).read(symbol, instrument_type, bar or config.market.bar)


def filter_confirmed_candles(df: pd.DataFrame, require_confirmed: bool = True) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    out["ts"] = pd.to_datetime(out["ts"], utc=True)
    if require_confirmed and "confirmed" in out.columns:
        out = out[out["confirmed"].fillna(False).astype(bool)]
    return out.sort_values("ts").drop_duplicates("ts").reset_index(drop=True)


def load_funding_rates(config: AppConfig, symbol: str) -> pd.DataFrame:
    return FundingRateStore(config.data_dir).read(symbol)


def safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def discover_usdt_universe(
    config: AppConfig,
    client: OkxRestClient,
    instrument_type: str = "spot",
    top_n: int = 20,
    min_quote_volume: float = 0.0,
) -> list[dict[str, object]]:
    instruments = client.get_instruments(instrument_type)
    tickers = {row.get("instId"): row for row in client.get_tickers(instrument_type)}
    rows: list[dict[str, object]] = []
    for instrument in instruments:
        inst_id = str(instrument.get("instId", ""))
        symbol, parsed_type = symbol_from_okx_inst_id(inst_id)
        if parsed_type != instrument_type:
            continue
        base, quote = symbol.split("/", 1)
        if quote != config.market.base_currency:
            continue
        if base in EXCLUDED_BASE_ASSETS:
            continue
        if instrument.get("state") and instrument.get("state") != "live":
            continue
        ticker = tickers.get(inst_id, {})
        quote_volume = safe_float(ticker.get("volCcy24h"), safe_float(ticker.get("vol24h")))
        if quote_volume < min_quote_volume:
            continue
        rows.append(
            {
                "symbol": symbol,
                "inst_id": inst_id,
                "instrument_type": instrument_type,
                "quote_volume_24h": quote_volume,
                "last": safe_float(ticker.get("last")),
                "base": base,
                "quote": quote,
            }
        )
    rows.sort(key=lambda row: float(row["quote_volume_24h"]), reverse=True)
    return rows[: max(top_n, 1)]


def write_universe(config: AppConfig, rows: list[dict[str, object]], name: str = "okx_usdt_universe") -> Path:
    path = config.data_dir / "universe" / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "count": len(rows),
        "symbols": [row["symbol"] for row in rows],
        "rows": rows,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def filter_date_range(df: pd.DataFrame, start: str | None, end: str | None) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    out["ts"] = pd.to_datetime(out["ts"], utc=True)
    if start:
        out = out[out["ts"] >= pd.to_datetime(start, utc=True)]
    if end:
        out = out[out["ts"] <= pd.to_datetime(end, utc=True)]
    return out.reset_index(drop=True)


def synthetic_candles(symbol: str, instrument_type: str, periods: int = 160) -> pd.DataFrame:
    ts = pd.date_range("2024-01-01", periods=periods, freq="h", tz="UTC")
    base = 40_000 if symbol.startswith("BTC") else 2_000
    rows = []
    for i, item_ts in enumerate(ts):
        drift = i * base * 0.0005
        cycle = ((i % 24) - 12) * base * 0.0004
        close = base + drift + cycle
        rows.append(
            {
                "ts": item_ts,
                "symbol": symbol,
                "instrument_type": instrument_type,
                "open": close * 0.999,
                "high": close * 1.005,
                "low": close * 0.995,
                "close": close,
                "volume": 100 + i,
                "confirmed": True,
            }
        )
    return pd.DataFrame(rows)


def _ingestion_payload(**kwargs: object) -> dict[str, object]:
    payload = dict(kwargs)
    payload.setdefault("task_id", f"ingest-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}")
    payload.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    payload.setdefault("error_message", None)
    return payload


def _df_time(df: pd.DataFrame, edge: str) -> str | None:
    if df.empty or "ts" not in df:
        return None
    ts = pd.to_datetime(df["ts"], utc=True, errors="coerce").dropna().sort_values()
    if ts.empty:
        return None
    value = ts.iloc[0] if edge == "start" else ts.iloc[-1]
    return value.isoformat()
