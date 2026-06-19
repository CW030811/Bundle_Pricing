from pathlib import Path

import pandas as pd

from quant_system.broker import PaperBroker, target_signal_to_order
from quant_system.config import AppConfig
from quant_system.data import filter_confirmed_candles, synthetic_candles
from quant_system.data_quality import check_ohlcv_quality
from quant_system.models import InstrumentType, OrderIntent, Side
from quant_system.portfolio import cross_sectional_momentum_targets, load_close_matrix
from quant_system.risk import RiskManager
from quant_system.service import enforce_min_free_disk, service_health
from quant_system.storage import AuditStore, CandleStore, normalize_okx_candles
from quant_system.strategies import build_strategy


def test_normalize_okx_candles_dedupes_and_sorts():
    rows = [
        ["1710003600000", "10", "12", "9", "11", "100", "0", "0", "1"],
        ["1710000000000", "9", "11", "8", "10", "90", "0", "0", "1"],
        ["1710000000000", "9", "11", "8", "10", "90", "0", "0", "1"],
    ]
    df = normalize_okx_candles(rows, "BTC/USDT", "spot")
    assert list(df["close"]) == [10.0, 11.0]
    assert len(df) == 2


def test_candle_store_csv_fallback_when_parquet_engine_missing(tmp_path, monkeypatch):
    cfg = AppConfig(data_dir=tmp_path)
    store = CandleStore(cfg.data_dir)
    df = synthetic_candles("BTC/USDT", "spot", periods=3)

    def raise_import_error(*args, **kwargs):
        raise ImportError("no parquet engine")

    monkeypatch.setattr(pd.DataFrame, "to_parquet", raise_import_error)
    path = store.write(df, "BTC/USDT", "spot", "1H")
    assert path.suffix == ".csv"
    loaded = store.read("BTC/USDT", "spot", "1H")
    assert len(loaded) == 3


def test_datahub_schema_and_raw_ods_insert(tmp_path):
    audit = AuditStore(tmp_path / "state")
    status = audit.datahub_schema_status()
    assert status["missing_tables"] == []
    inserted = audit.insert_ods_crypto_ohlcv_raw(
        [["1710000000000", "9", "11", "8", "10", "90", "0", "0", "1"]],
        source="okx_test",
        exchange="okx",
        symbol="BTC/USDT",
        market_type="spot",
        interval="1H",
    )
    assert inserted == 1
    with audit.connect() as conn:
        row = conn.execute("SELECT source, symbol, raw_timestamp FROM ods_crypto_ohlcv_raw").fetchone()
    assert row["source"] == "okx_test"
    assert row["symbol"] == "BTC/USDT"
    assert row["raw_timestamp"] == "1710000000000"


def test_service_disk_guard_rejects_low_free_space(tmp_path, monkeypatch):
    cfg = AppConfig(state_dir=tmp_path / "state", log_dir=tmp_path / "logs", data_dir=tmp_path / "data")
    cfg.service.min_free_disk_bytes = 100

    monkeypatch.setattr(
        "quant_system.service.disk_status",
        lambda path: {"path": str(path), "total_bytes": 1000, "used_bytes": 950, "free_bytes": 50},
    )

    try:
        enforce_min_free_disk(cfg)
    except OSError as exc:
        assert "low disk space" in str(exc)
    else:
        raise AssertionError("expected low disk space guard to raise")


def test_service_health_reports_low_disk_without_crashing(tmp_path, monkeypatch):
    cfg = AppConfig(state_dir=tmp_path / "state", log_dir=tmp_path / "logs", data_dir=tmp_path / "data")
    cfg.service.min_free_disk_bytes = 100

    monkeypatch.setattr(
        "quant_system.service.disk_status",
        lambda path: {"path": str(path), "total_bytes": 1000, "used_bytes": 950, "free_bytes": 50},
    )

    health = service_health(cfg)

    assert health["healthy"] is False
    assert "low disk space" in health["issues"]
    assert health["disk"]["error_type"] == "OSError"


def test_dwd_sql_ohlcv_and_funding_upserts(tmp_path):
    audit = AuditStore(tmp_path / "state")
    candles = synthetic_candles("BTC/USDT", "spot", periods=3)
    funding = pd.DataFrame(
        {
            "ts": pd.date_range("2026-01-01", periods=2, freq="8h", tz="UTC"),
            "symbol": ["BTC/USDT", "BTC/USDT"],
            "funding_rate": [0.0001, 0.0002],
        }
    )

    assert audit.upsert_dwd_crypto_ohlcv(candles, exchange="okx", interval="1H") == 3
    assert audit.upsert_dwd_crypto_funding_rate(funding, exchange="okx") == 2
    assert audit.upsert_dwd_crypto_ohlcv(candles, exchange="okx", interval="1H") == 3

    with audit.connect() as conn:
        candle_count = conn.execute("SELECT COUNT(*) AS count FROM dwd_crypto_ohlcv").fetchone()["count"]
        funding_count = conn.execute("SELECT COUNT(*) AS count FROM dwd_crypto_funding_rate").fetchone()["count"]
    assert candle_count == 3
    assert funding_count == 2


def test_ohlcv_quality_check_flags_invalid_rows():
    df = synthetic_candles("BTC/USDT", "spot", periods=3)
    df.loc[1, "high"] = df.loc[1, "low"] - 1
    df.loc[2, "volume"] = -1
    df = pd.concat([df, df.iloc[[0]]], ignore_index=True)
    issues = check_ohlcv_quality(df, exchange="okx", symbol="BTC/USDT", market_type="spot", interval="1H")
    issue_types = {issue["issue_type"] for issue in issues}
    assert {"duplicate", "invalid_ohlc", "negative_volume"}.issubset(issue_types)




def test_filter_confirmed_candles_drops_unclosed_latest_bar():
    df = synthetic_candles("BTC/USDT", "spot", periods=3)
    df.loc[2, "confirmed"] = False
    filtered = filter_confirmed_candles(df)
    assert len(filtered) == 2
    assert bool(filtered["confirmed"].all()) is True
    assert filtered.iloc[-1]["ts"] == df.iloc[1]["ts"]


def test_load_close_matrix_ignores_unconfirmed_last_bar_for_selection(tmp_path):
    cfg = AppConfig(data_dir=tmp_path / "data")
    ts = pd.date_range("2026-01-01", periods=3, freq="h", tz="UTC")

    def frame(symbol: str, closes: list[float], confirmed: list[bool]) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "ts": ts,
                "symbol": symbol,
                "instrument_type": "spot",
                "open": closes,
                "high": closes,
                "low": closes,
                "close": closes,
                "volume": [100.0, 100.0, 100.0],
                "confirmed": confirmed,
            }
        )

    store = CandleStore(cfg.data_dir)
    store.write(frame("BTC/USDT", [100.0, 100.0, 200.0], [True, True, False]), "BTC/USDT", "spot", "1H")
    store.write(frame("ETH/USDT", [100.0, 101.0, 50.0], [True, True, False]), "ETH/USDT", "spot", "1H")

    closes = load_close_matrix(cfg, ["BTC/USDT", "ETH/USDT"], "spot")
    target = cross_sectional_momentum_targets(closes, lookback_bars=1, top_n=1)

    assert closes.index[-1] == ts[1]
    assert target["selected"] == ["ETH/USDT"]

def test_strategy_generates_bounded_signal():
    cfg = AppConfig()
    for name in [
        "trend_mr",
        "vol_trend",
        "donchian_breakout",
        "rsi_bollinger_reversion",
        "btc_volatility_breakout",
        "btc_realized_volatility_targeting",
    ]:
        cfg.strategy.name = name
        strategy = build_strategy(cfg.strategy)
        signal = strategy.generate(synthetic_candles("BTC/USDT", "spot", periods=100), "BTC/USDT", InstrumentType.SPOT)
        assert -0.15 <= signal.target_pct <= 0.20
        assert signal.strategy == name



def test_btc_volatility_breakout_uses_prior_channel_only():
    cfg = AppConfig()
    cfg.strategy.name = "btc_volatility_breakout"
    candles = synthetic_candles("BTC/USDT", "spot", periods=220)
    candles.loc[len(candles) - 1, "close"] = candles["high"].iloc[:-1].max() * 1.05
    candles.loc[len(candles) - 1, "high"] = candles.loc[len(candles) - 1, "close"]
    strategy = build_strategy(cfg.strategy)
    signal = strategy.generate(candles, "BTC/USDT", InstrumentType.SPOT)
    assert signal.strategy == "btc_volatility_breakout"
    assert signal.target_pct >= 0.0


def test_realized_volatility_targeting_scales_exposure():
    cfg = AppConfig()
    cfg.strategy.name = "btc_realized_volatility_targeting"
    strategy = build_strategy(cfg.strategy)
    signal = strategy.generate(synthetic_candles("BTC/USDT", "spot", periods=420), "BTC/USDT", InstrumentType.SPOT)
    assert signal.strategy == "btc_realized_volatility_targeting"
    assert 0.0 <= signal.target_pct <= 0.25
    assert "annualized_vol" in signal.reason

def test_risk_rejects_kill_switch(tmp_path):
    cfg = AppConfig()
    cfg.risk.kill_switch_file = tmp_path / "KILL_SWITCH"
    cfg.risk.kill_switch_file.write_text("active")
    risk = RiskManager(cfg.risk, cfg.execution)
    broker = PaperBroker(cfg)
    intent = OrderIntent("BTC/USDT", InstrumentType.SPOT, Side.BUY, quantity=0.01)
    decision = risk.evaluate(intent, broker.portfolio(), 40_000)
    assert decision.approved is False
    assert "kill switch" in decision.reason


def test_risk_allows_reduce_only_exit_when_kill_switch_active(tmp_path):
    cfg = AppConfig()
    cfg.risk.kill_switch_file = tmp_path / "KILL_SWITCH"
    cfg.risk.kill_switch_file.write_text("active")
    risk = RiskManager(cfg.risk, cfg.execution)
    broker = PaperBroker(cfg)
    intent = OrderIntent("BTC/USDT", InstrumentType.SPOT, Side.SELL, quantity=0.01, reduce_only=True)
    decision = risk.evaluate(intent, broker.portfolio(), 40_000)
    assert decision.approved is True
    assert "reduce-only" in decision.reason


def test_risk_adjusts_oversized_order(tmp_path):
    cfg = AppConfig(state_dir=tmp_path / "state")
    risk = RiskManager(cfg.risk, cfg.execution)
    broker = PaperBroker(cfg)
    intent = OrderIntent("BTC/USDT", InstrumentType.SPOT, Side.BUY, quantity=10)
    decision = risk.evaluate(intent, broker.portfolio(), 40_000)
    assert decision.approved is True
    assert decision.adjusted_quantity is not None
    assert decision.adjusted_quantity * 40_000 <= cfg.risk.live_trading_cap_usdt * cfg.risk.max_symbol_exposure_pct


def test_paper_broker_fills_without_okx_client():
    cfg = AppConfig()
    broker = PaperBroker(cfg)
    order = broker.submit_order(OrderIntent("BTC/USDT", InstrumentType.SPOT, Side.BUY, 0.01), 40_000)
    assert order.status.value == "filled"
    assert broker.portfolio({"BTC/USDT": 41_000}).equity > 0


def test_target_signal_to_order_uses_equity_delta():
    intent = target_signal_to_order(0.10, "BTC/USDT", InstrumentType.SPOT, 0.0, 10_000, 50_000)
    assert intent is not None
    assert intent.side == Side.BUY
    assert round(intent.quantity, 6) == 0.02
