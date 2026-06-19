import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from quant_system.backtest import Backtester
from quant_system.alpha import apply_factor_transform
from quant_system.cli import main
from quant_system.config import AppConfig
from quant_system.data import synthetic_candles
from quant_system.factors import (
    CryptoMomentumFactor,
    FactorDataset,
    FactorEvaluator,
    FactorSpec,
    available_factors,
    build_factor_dataset,
    compute_forward_returns,
)
from quant_system.models import InstrumentType, Signal
from quant_system.live import run_okx_live_portfolio_once, run_paper_portfolio_once
from quant_system.service import (
    interruptible_sleep,
    prepare_service_launch,
    recover_paper_service,
    refresh_candles_resilient,
    run_live_portfolio_service,
    run_paper_portfolio_service,
)
from quant_system.storage import AuditStore, CandleStore, FundingRateStore


def write_overlay(tmp_path: Path) -> Path:
    overlay = tmp_path / "paper.yaml"
    overlay.write_text(
        "\n".join(
            [
                "data_dir: " + str(tmp_path / "data"),
                "report_dir: " + str(tmp_path / "reports"),
                "state_dir: " + str(tmp_path / "state"),
                "log_dir: " + str(tmp_path / "logs"),
                "risk:",
                "  kill_switch_file: " + str(tmp_path / "state" / "KILL_SWITCH"),
                "service:",
                "  pid_file: " + str(tmp_path / "state" / "quant_service.pid"),
                "  watchdog_pid_file: " + str(tmp_path / "state" / "quant_watchdog.pid"),
                "  launch_state_file: " + str(tmp_path / "state" / "quant_service_launch.json"),
                "  watchdog_launch_state_file: " + str(tmp_path / "state" / "quant_watchdog_launch.json"),
                "  stop_file: " + str(tmp_path / "state" / "quant_service.stop"),
                "  heartbeat_file: " + str(tmp_path / "state" / "quant_service_heartbeat.json"),
                "  watchdog_heartbeat_file: " + str(tmp_path / "state" / "quant_watchdog_heartbeat.json"),
                "  log_file: " + str(tmp_path / "logs" / "quant_service.log"),
                "  watchdog_log_file: " + str(tmp_path / "logs" / "quant_watchdog.log"),
                "  retry_backoff_seconds: 0",
                "  max_candle_age_seconds: 0",
                "  rebalance_cooldown_seconds: 0",
                "  watchdog_interval_seconds: 0",
                "  refresh_candles_before_iteration: false",
                "  event_log_file: " + str(tmp_path / "logs" / "quant_events.jsonl"),
                "  notification_log_file: " + str(tmp_path / "logs" / "quant_notifications.jsonl"),
            ]
        ),
        encoding="utf-8",
    )
    return overlay


def synthetic_factor_candles(symbol: str, instrument_type: str, multiplier: float, periods: int = 96) -> pd.DataFrame:
    ts = pd.date_range("2024-01-01", periods=periods, freq="h", tz="UTC")
    base = 100.0 * multiplier
    rows = []
    for idx, item_ts in enumerate(ts):
        trend = 1.0 + idx * 0.001 * multiplier
        cycle = 1.0 + ((idx % 8) - 4) * 0.0005 * multiplier
        close = base * trend * cycle
        rows.append(
            {
                "ts": item_ts,
                "symbol": symbol,
                "instrument_type": instrument_type,
                "open": close * 0.999,
                "high": close * 1.002,
                "low": close * 0.998,
                "close": close,
                "volume": 1000 + idx * multiplier,
                "confirmed": True,
            }
        )
    return pd.DataFrame(rows)


def synthetic_bar_candles(
    symbol: str,
    instrument_type: str,
    multiplier: float,
    *,
    periods: int = 160,
    freq: str = "h",
) -> pd.DataFrame:
    ts = pd.date_range("2024-01-01", periods=periods, freq=freq, tz="UTC")
    rows = []
    for idx, item_ts in enumerate(ts):
        trend = 100.0 * multiplier * (1.0 + idx * 0.002)
        cycle = 1.0 + ((idx % 10) - 5) * 0.001
        close = trend * cycle
        rows.append(
            {
                "ts": item_ts,
                "symbol": symbol,
                "instrument_type": instrument_type,
                "open": close * 0.999,
                "high": close * 1.003,
                "low": close * 0.997,
                "close": close,
                "volume": 1000 + idx * 5,
                "confirmed": True,
            }
        )
    return pd.DataFrame(rows)






def test_prepare_service_launch_clears_stale_stop_heartbeat_and_paper_kill_switch(tmp_path):
    cfg = AppConfig(
        data_dir=tmp_path / "data",
        report_dir=tmp_path / "reports",
        state_dir=tmp_path / "state",
        log_dir=tmp_path / "logs",
    )
    cfg.service.stop_file = tmp_path / "state" / "quant_service.stop"
    cfg.service.heartbeat_file = tmp_path / "state" / "quant_service_heartbeat.json"
    cfg.service.event_log_file = tmp_path / "logs" / "quant_events.jsonl"
    cfg.risk.kill_switch_file = tmp_path / "state" / "KILL_SWITCH"
    cfg.service.stop_file.parent.mkdir(parents=True)
    cfg.service.stop_file.write_text("old stop", encoding="utf-8")
    cfg.service.heartbeat_file.write_text(json.dumps({"ts": "2000-01-01T00:00:00+00:00"}), encoding="utf-8")
    cfg.risk.kill_switch_file.write_text("old kill", encoding="utf-8")

    result = prepare_service_launch(cfg, clear_kill_switch=True)
    heartbeat = json.loads(cfg.service.heartbeat_file.read_text())

    assert not cfg.service.stop_file.exists()
    assert not cfg.risk.kill_switch_file.exists()
    assert heartbeat["starting"] is True
    assert heartbeat["consecutive_errors"] == 0
    assert str(cfg.service.stop_file) in result["removed"]


def test_refresh_candles_resilient_keeps_partial_success(tmp_path, monkeypatch):
    from quant_system import service

    cfg = AppConfig(data_dir=tmp_path / "data")

    def fake_backfill(config, client, symbols, instrument_types, bar, limit):
        if symbols == ["BAD/USDT"]:
            raise TimeoutError("temporary network timeout")
        return [tmp_path / "data" / symbols[0].replace("/", "-") / f"{bar}.csv"]

    monkeypatch.setattr(service, "backfill_candles", fake_backfill)
    result = refresh_candles_resilient(
        cfg,
        client=object(),
        symbols=["BTC/USDT", "BAD/USDT"],
        instrument_type="spot",
        bar="1H",
        limit=10,
    )

    assert result["paths"] == [str(tmp_path / "data" / "BTC-USDT" / "1H.csv")]
    assert result["errors"] == [
        {"symbol": "BAD/USDT", "error_type": "TimeoutError", "error": "temporary network timeout"}
    ]


def test_backtester_writes_report(tmp_path):
    cfg = AppConfig(
        data_dir=tmp_path / "data",
        report_dir=tmp_path / "reports",
        state_dir=tmp_path / "state",
        log_dir=tmp_path / "logs",
    )
    result = Backtester(cfg).run(synthetic_candles("BTC/USDT", "spot", periods=140), "BTC/USDT", InstrumentType.SPOT)
    assert result["metrics"]["trade_count"] >= 0
    assert "annualized_return" in result["metrics"]
    assert "profit_loss_ratio" in result["metrics"]
    assert "regime_performance" in result
    assert result["regime_performance"]["schema"] == "market_regime_v1"
    assert "by_primary_regime" in result["regime_performance"]
    assert not result["equity_curve"].empty


def test_factor_dataset_aligns_factors_and_forward_returns():
    ts = pd.date_range("2024-01-01", periods=4, freq="h", tz="UTC")
    panel = pd.DataFrame(
        [
            {"ts": item_ts, "symbol": symbol, "close": close, "volume": 100.0, "confirmed": True}
            for symbol, closes in {"AAA/USDT": [1, 2, 4, 8], "BBB/USDT": [2, 3, 5, 9], "CCC/USDT": [4, 4, 6, 12]}.items()
            for item_ts, close in zip(ts, closes)
        ]
    )

    returns = compute_forward_returns(panel, [1])
    dataset = build_factor_dataset(CryptoMomentumFactor(1), panel, [1], min_symbols=3)
    row = dataset.merged[(dataset.merged["symbol"] == "AAA/USDT") & (dataset.merged["ts"] == ts[1])].iloc[0]

    assert returns.loc[(returns["symbol"] == "AAA/USDT") & (returns["ts"] == ts[1]), "forward_return_1"].iloc[0] == 1.0
    assert row["factor"] == 1.0
    assert row["forward_return_1"] == 1.0
    assert dataset.metadata["symbols"] == ["AAA/USDT", "BBB/USDT", "CCC/USDT"]


def test_factor_evaluator_reports_ic_quantiles_turnover():
    ts = pd.date_range("2024-01-01", periods=2, freq="h", tz="UTC")
    merged = pd.DataFrame(
        [
            {"ts": ts[0], "symbol": "A/USDT", "factor": 1.0, "forward_return_1": 0.01},
            {"ts": ts[0], "symbol": "B/USDT", "factor": 2.0, "forward_return_1": 0.02},
            {"ts": ts[0], "symbol": "C/USDT", "factor": 3.0, "forward_return_1": 0.03},
            {"ts": ts[1], "symbol": "A/USDT", "factor": 3.0, "forward_return_1": 0.03},
            {"ts": ts[1], "symbol": "B/USDT", "factor": 2.0, "forward_return_1": 0.02},
            {"ts": ts[1], "symbol": "C/USDT", "factor": 1.0, "forward_return_1": 0.01},
        ]
    )
    dataset = FactorDataset(
        spec=FactorSpec(id="toy_factor", name="Toy factor", horizons=(1,)),
        factor_values=merged[["ts", "symbol", "factor"]],
        forward_returns=merged[["ts", "symbol", "forward_return_1"]],
        merged=merged,
        metadata={"row_count": 6, "factor_row_count": 6, "min_symbols": 3, "date_range": {}},
    )

    payload = FactorEvaluator(quantiles=3, min_symbols=3).evaluate(dataset)

    assert payload["status"] == "ok"
    assert payload["ic_summary"]["1"]["mean_rank_ic"] == 1.0
    assert payload["quantile_returns"]["1"]["top_bottom_mean"] > 0
    assert payload["turnover"]["1"]["top_quantile_turnover_mean"] == 1.0


def test_alpha_transform_ma_diff_generates_bounded_signals():
    ts = pd.date_range("2024-01-01", periods=4, freq="h", tz="UTC")
    values = pd.DataFrame(
        [
            {"ts": item_ts, "symbol": "BTC/USDT", "factor": value}
            for item_ts, value in zip(ts, [1.0, 2.0, 3.0, 2.0])
        ]
    )

    signals = apply_factor_transform(
        values,
        model="ma_diff",
        window=2,
        threshold=0.1,
        style="momentum",
        position_type="long_short",
    )

    assert set(signals["signal"].dropna().unique()).issubset({-1.0, 0.0, 1.0})
    assert signals.loc[signals["ts"] == ts[2], "signal"].iloc[0] == 1.0
    assert signals.loc[signals["ts"] == ts[3], "signal"].iloc[0] == -1.0


def test_cli_research_factor_evaluate_writes_report(tmp_path):
    overlay = write_overlay(tmp_path)
    store = CandleStore(tmp_path / "data")
    for symbol, multiplier in [("BTC/USDT", 1.0), ("ETH/USDT", 1.4), ("SOL/USDT", 1.9)]:
        store.write(synthetic_factor_candles(symbol, "spot", multiplier), symbol, "spot", "1H")

    code = main(
        [
            "--config",
            str(overlay),
            "research",
            "factor-evaluate",
            "--factor",
            "crypto_momentum_24h",
            "--symbol",
            "BTC/USDT",
            "--symbol",
            "ETH/USDT",
            "--symbol",
            "SOL/USDT",
            "--horizon-bars",
            "1",
            "--quantiles",
            "3",
            "--min-symbols",
            "3",
            "--write-report",
        ]
    )

    assert code == 0
    latest = tmp_path / "reports" / "factor_crypto_momentum_24h_latest.json"
    assert latest.exists()
    payload = json.loads(latest.read_text())
    assert payload["factor_id"] == "crypto_momentum_24h"
    assert payload["status"] == "ok"
    assert payload["horizons"] == [1]
    assert payload["coverage"]["valid_cross_sections"] > 0
    assert payload["ic_summary"]["1"]["observations"] > 0
    assert payload["market_regime"]["schema"] == "market_regime_v1"
    assert payload["reproducibility"]["factor_version"] == "v1"
    audit = AuditStore(tmp_path / "state")
    with audit.connect() as conn:
        registry_count = conn.execute("SELECT COUNT(*) AS count FROM factor_registry").fetchone()["count"]
        log_count = conn.execute("SELECT COUNT(*) AS count FROM factor_calculation_logs").fetchone()["count"]
        dws_count = conn.execute("SELECT COUNT(*) AS count FROM dws_crypto_factor_values").fetchone()["count"]
        repro_count = conn.execute("SELECT COUNT(*) AS count FROM reproducibility_records").fetchone()["count"]
    assert registry_count == 1
    assert log_count == 1
    assert dws_count > 0
    assert repro_count == 1
    assert payload["dws_materialized"]["row_count"] == dws_count


def test_cli_research_alpha_ensemble_writes_report_and_materializes_external_factor(tmp_path):
    overlay = write_overlay(tmp_path)
    store = CandleStore(tmp_path / "data")
    periods = 80
    for symbol, multiplier in [("BTC/USDT", 1.0), ("ETH/USDT", 1.2)]:
        store.write(synthetic_factor_candles(symbol, "spot", multiplier, periods=periods), symbol, "spot", "1H")

    factor_dir = tmp_path / "data" / "alpha_factors"
    factor_dir.mkdir(parents=True)
    ts = pd.date_range("2024-01-01", periods=periods, freq="h", tz="UTC")
    external_rows = []
    for symbol, multiplier in [("BTC/USDT", 1.0), ("ETH/USDT", 1.2)]:
        for idx, item_ts in enumerate(ts):
            external_rows.append({"ts": item_ts.isoformat(), "symbol": symbol, "factor": idx * multiplier})
    external_path = factor_dir / "toy_external.csv"
    pd.DataFrame(external_rows).to_csv(external_path, index=False)

    spec = tmp_path / "alpha.yaml"
    spec.write_text(
        "\n".join(
            [
                "name: external_alpha_factor_ensemble",
                "version: v1",
                "symbols:",
                "  - BTC/USDT",
                "  - ETH/USDT",
                "instrument_type: spot",
                "horizon_bars: 1",
                "min_symbols: 2",
                "external_factors:",
                "  - factor_id: toy_external_alpha",
                "    path: alpha_factors/toy_external.csv",
                "    frequency: 1H",
                "    description: Toy external alpha",
                "groups:",
                "  - group: toy_group",
                "    factor: toy_external_alpha",
                "    weight: 1.0",
                "    transforms:",
                "      - model: ma_diff",
                "        window: 3",
                "        threshold: 0.01",
                "        style: momentum",
                "        position_type: long_only",
            ]
        ),
        encoding="utf-8",
    )

    code = main(
        [
            "--config",
            str(overlay),
            "research",
            "alpha-ensemble",
            "--spec",
            str(spec),
            "--write-report",
        ]
    )

    assert code == 0
    latest = tmp_path / "reports" / "alpha_ensemble_latest.json"
    assert latest.exists()
    payload = json.loads(latest.read_text())
    assert payload["schema"] == "alpha_ensemble_report_v1"
    assert payload["status"] == "ok"
    assert payload["promotion_status"] == "research_only"
    assert payload["ensemble"]["signal_row_count"] > 0
    assert payload["dws_materialized"]["ensemble_signal_rows"] > 0
    assert payload["dws_materialized"]["external_factor_count"] == 1
    audit = AuditStore(tmp_path / "state")
    with audit.connect() as conn:
        registry_names = {
            row["factor_name"]
            for row in conn.execute("SELECT factor_name FROM factor_registry").fetchall()
        }
        dws_count = conn.execute("SELECT COUNT(*) AS count FROM dws_crypto_factor_values").fetchone()["count"]
        repro_count = conn.execute("SELECT COUNT(*) AS count FROM reproducibility_records").fetchone()["count"]
    assert {"toy_external_alpha", "external_alpha_factor_ensemble_signal"}.issubset(registry_names)
    assert dws_count > periods
    assert repro_count == 1




def test_migrated_strategy_factor_builders_emit_standard_factor_values():
    periods = 1200
    panel = pd.concat(
        [
            synthetic_factor_candles("BTC/USDT", "spot", 1.0, periods=periods),
            synthetic_factor_candles("ETH/USDT", "spot", 1.4, periods=periods),
            synthetic_factor_candles("SOL/USDT", "spot", 1.9, periods=periods),
        ],
        ignore_index=True,
    )
    registry = available_factors()
    expected = {
        "cross_sectional_momentum_720h",
        "adaptive_trend_quality",
        "btc_time_series_momentum_336h",
        "volatility_adjusted_btc_trend",
        "altcoin_btc_residual_reversion",
    }

    assert expected.issubset(registry)
    for factor_id in expected:
        values = registry[factor_id].compute(panel)
        assert {"ts", "symbol", "factor"}.issubset(values.columns)
        assert not values.empty
        assert values["factor"].notna().all()


def test_cli_research_funding_factor_evaluate_writes_report(tmp_path):
    overlay = write_overlay(tmp_path)
    write_sample_funding_rates(tmp_path, periods=80)

    code = main(
        [
            "--config",
            str(overlay),
            "research",
            "factor-evaluate",
            "--factor",
            "funding_carry_recent",
            "--symbol",
            "BTC/USDT",
            "--symbol",
            "ETH/USDT",
            "--horizon-bars",
            "1",
            "--quantiles",
            "2",
            "--min-symbols",
            "2",
            "--write-report",
        ]
    )

    assert code == 0
    latest = tmp_path / "reports" / "factor_funding_carry_recent_latest.json"
    assert latest.exists()
    payload = json.loads(latest.read_text())
    assert payload["factor_id"] == "funding_carry_recent"
    assert payload["status"] == "ok"
    assert payload["coverage"]["valid_cross_sections"] > 0


def test_backtester_executes_signal_on_next_bar_open(tmp_path):
    cfg = AppConfig(
        data_dir=tmp_path / "data",
        report_dir=tmp_path / "reports",
        state_dir=tmp_path / "state",
        log_dir=tmp_path / "logs",
    )
    cfg.execution.slippage_bps = 0.0
    cfg.execution.fee_rate = 0.0
    candles = synthetic_candles("BTC/USDT", "spot", periods=90)
    warmup = max(cfg.strategy.slow_ema, cfg.strategy.bollinger_period, 20)

    class AlwaysLongStrategy:
        name = "always_long"

        def generate(self, window, symbol, instrument_type):
            latest = window.iloc[-1]
            return Signal(
                symbol=symbol,
                instrument_type=instrument_type,
                ts=latest["ts"].to_pydatetime(),
                target_pct=0.10,
                confidence=1.0,
                reason="test target",
                strategy=self.name,
            )

    result = Backtester(cfg, strategy=AlwaysLongStrategy()).run(candles, "BTC/USDT", InstrumentType.SPOT)
    first_trade = result["trades"].iloc[0]

    assert result["execution_model"] == "next_bar_open"
    assert result["confirmed_only"] is True
    assert {"cash", "buy_and_hold", "simple_ma_trend", "random_entry"}.issubset(result["benchmarks"])
    assert "metrics" in result["benchmarks"]["buy_and_hold"]
    assert first_trade["signal_ts"] == candles.iloc[warmup]["ts"]
    assert first_trade["execution_ts"] == candles.iloc[warmup + 1]["ts"]
    assert first_trade["price"] == candles.iloc[warmup + 1]["open"]
    assert first_trade["execution_price_source"] == "next_bar_open"


def test_backtester_writes_ads_backtest_result(tmp_path):
    cfg = AppConfig(
        data_dir=tmp_path / "data",
        report_dir=tmp_path / "reports",
        state_dir=tmp_path / "state",
        log_dir=tmp_path / "logs",
    )
    candles = synthetic_candles("BTC/USDT", "spot", periods=90)
    path = Backtester(cfg).run_and_write(candles, "BTC/USDT", InstrumentType.SPOT)
    audit = AuditStore(cfg.state_dir)

    assert path.exists()
    with audit.connect() as conn:
        result_count = conn.execute("SELECT COUNT(*) AS count FROM ads_crypto_backtest_results").fetchone()["count"]
        trade_count = conn.execute("SELECT COUNT(*) AS count FROM ads_crypto_backtest_trades").fetchone()["count"]
        repro_count = conn.execute("SELECT COUNT(*) AS count FROM reproducibility_records").fetchone()["count"]
    assert result_count == 1
    assert trade_count >= 0
    assert repro_count == 1


def test_backtester_ignores_unconfirmed_candles(tmp_path):
    cfg = AppConfig(
        data_dir=tmp_path / "data",
        report_dir=tmp_path / "reports",
        state_dir=tmp_path / "state",
        log_dir=tmp_path / "logs",
    )
    cfg.execution.slippage_bps = 0.0
    cfg.execution.fee_rate = 0.0
    candles = synthetic_candles("BTC/USDT", "spot", periods=90)
    candles.loc[len(candles) - 1, "confirmed"] = False

    class TrackingStrategy:
        name = "tracking"
        seen = []

        def generate(self, window, symbol, instrument_type):
            latest = window.iloc[-1]
            self.seen.append(latest["ts"])
            return Signal(
                symbol=symbol,
                instrument_type=instrument_type,
                ts=latest["ts"].to_pydatetime(),
                target_pct=0.0,
                confidence=1.0,
                reason="flat",
                strategy=self.name,
            )

    strategy = TrackingStrategy()
    Backtester(cfg, strategy=strategy).run(candles, "BTC/USDT", InstrumentType.SPOT)

    assert candles.iloc[-1]["ts"] not in strategy.seen

def test_cli_backtest_synthetic_writes_latest_report(tmp_path):
    overlay = write_overlay(tmp_path)
    code = main(["--config", str(overlay), "backtest", "--use-synthetic", "--symbol", "BTC/USDT"])
    assert code == 0
    latest = tmp_path / "reports" / "backtest_latest.json"
    assert latest.exists()
    payload = json.loads(latest.read_text())
    assert payload["strategy"] == "trend_mr"
    assert main(["--config", str(overlay), "report", "latest", "--name", "backtest"]) == 0
    assert main(["--config", str(overlay), "report", "index", "--name", "backtest"]) == 0
    assert main(["--config", str(overlay), "report", "ads", "--kind", "backtests"]) == 0
    assert main(["--config", str(overlay), "report", "ads", "--kind", "reproducibility"]) == 0


def test_cli_backtest_requires_strategy_card_by_default(tmp_path):
    overlay = write_overlay(tmp_path)
    with pytest.raises(SystemExit) as exc:
        main(
            [
                "--config",
                str(overlay),
                "backtest",
                "--use-synthetic",
                "--strategy",
                "unregistered_strategy",
                "--symbol",
                "BTC/USDT",
            ]
        )
    assert "missing Strategy Card" in str(exc.value)


def test_cli_research_sweep_quality_gate_blocks_missing_data(tmp_path):
    overlay = write_overlay(tmp_path)
    with pytest.raises(SystemExit) as exc:
        main(["--config", str(overlay), "research", "sweep", "--symbol", "BTC/USDT"])
    assert "data quality gate failed" in str(exc.value)


def test_cli_live_without_enabled_config_fails(tmp_path):
    overlay = write_overlay(tmp_path)
    with pytest.raises(PermissionError, match="live execution is disabled"):
        main(["--config", str(overlay), "live", "run", "--confirm-live"])


def test_interruptible_sleep_returns_when_stop_file_exists(tmp_path):
    stop_file = tmp_path / "stop"
    stop_file.write_text("stop", encoding="utf-8")
    interruptible_sleep(60, {"value": False}, stop_file)


def test_cli_service_run_live_without_enabled_config_fails(tmp_path):
    overlay = write_overlay(tmp_path)
    with pytest.raises(PermissionError, match="live execution is disabled"):
        main(["--config", str(overlay), "service", "run-live-portfolio", "--confirm-live", "--max-iterations", "1"])


def test_okx_live_portfolio_once_requires_confirm_live(tmp_path):
    cfg = AppConfig(
        mode="live",
        data_dir=tmp_path / "data",
        report_dir=tmp_path / "reports",
        state_dir=tmp_path / "state",
        log_dir=tmp_path / "logs",
    )
    cfg.execution.live_enabled = True
    cfg.okx.demo_trading = False
    cfg.service.event_log_file = tmp_path / "logs" / "quant_events.jsonl"
    cfg.service.notification_log_file = tmp_path / "logs" / "quant_notifications.jsonl"
    store = CandleStore(cfg.data_dir)
    store.write(synthetic_candles("BTC/USDT", "spot", periods=900), "BTC/USDT", "spot", "1H")
    store.write(synthetic_candles("ETH/USDT", "spot", periods=900), "ETH/USDT", "spot", "1H")

    class FakeCredentials:
        present = True

    class FakeClient:
        credentials = FakeCredentials()

        def get_balance(self):
            return {"data": [{"details": [{"ccy": "USDT", "eq": "50"}]}]}

        def get_account_instruments(self, instrument_type):
            return [{"instId": "BTC-USDT", "minSz": "0.00001", "lotSz": "0.00001", "tickSz": "0.1"}]

    with pytest.raises(PermissionError, match="--confirm-live"):
        run_okx_live_portfolio_once(
            cfg,
            ["BTC/USDT", "ETH/USDT"],
            lookback_bars=24,
            top_n=1,
            max_candle_age_seconds=0,
            rebalance_cooldown_seconds=0,
            confirm_live=False,
            client=FakeClient(),
        )


def test_okx_live_portfolio_once_places_gated_order_with_fake_client(tmp_path):
    cfg = AppConfig(
        mode="live",
        data_dir=tmp_path / "data",
        report_dir=tmp_path / "reports",
        state_dir=tmp_path / "state",
        log_dir=tmp_path / "logs",
    )
    cfg.execution.live_enabled = True
    cfg.execution.default_order_type = "limit"
    cfg.okx.demo_trading = False
    cfg.service.event_log_file = tmp_path / "logs" / "quant_events.jsonl"
    cfg.service.notification_log_file = tmp_path / "logs" / "quant_notifications.jsonl"
    store = CandleStore(cfg.data_dir)
    store.write(synthetic_candles("BTC/USDT", "spot", periods=900), "BTC/USDT", "spot", "1H")
    store.write(synthetic_candles("ETH/USDT", "spot", periods=900), "ETH/USDT", "spot", "1H")

    class FakeCredentials:
        present = True

    class FakeClient:
        credentials = FakeCredentials()

        def __init__(self):
            self.orders = []

        def get_balance(self):
            return {"data": [{"details": [{"ccy": "USDT", "eq": "50"}]}]}

        def get_account_instruments(self, instrument_type):
            return [
                {"instId": "BTC-USDT", "minSz": "0.00001", "lotSz": "0.00001", "tickSz": "0.1"},
                {"instId": "ETH-USDT", "minSz": "0.0001", "lotSz": "0.0001", "tickSz": "0.01"},
            ]

        def place_order(self, **kwargs):
            self.orders.append(kwargs)
            return {"data": [{"sCode": "0", "ordId": "live-test-order", "sMsg": ""}]}

    client = FakeClient()
    result = run_okx_live_portfolio_once(
        cfg,
        ["BTC/USDT", "ETH/USDT"],
        lookback_bars=24,
        top_n=1,
        max_candle_age_seconds=0,
        rebalance_cooldown_seconds=0,
        confirm_live=True,
        client=client,
    )
    assert result["orders"]
    assert client.orders
    assert client.orders[0]["order_type"] == "limit"
    assert client.orders[0]["quantity"]


def test_live_portfolio_service_records_heartbeat_with_fake_runner(tmp_path, monkeypatch):
    from quant_system import service

    monkeypatch.setenv("TEST_OKX_KEY", "key")
    monkeypatch.setenv("TEST_OKX_SECRET", "secret")
    monkeypatch.setenv("TEST_OKX_PASSPHRASE", "pass")
    cfg = AppConfig(
        mode="live",
        data_dir=tmp_path / "data",
        report_dir=tmp_path / "reports",
        state_dir=tmp_path / "state",
        log_dir=tmp_path / "logs",
    )
    cfg.execution.live_enabled = True
    cfg.okx.demo_trading = False
    cfg.okx.api_key_env = "TEST_OKX_KEY"
    cfg.okx.api_secret_env = "TEST_OKX_SECRET"
    cfg.okx.passphrase_env = "TEST_OKX_PASSPHRASE"
    cfg.service.event_log_file = tmp_path / "logs" / "quant_events.jsonl"
    cfg.service.notification_log_file = tmp_path / "logs" / "quant_notifications.jsonl"
    cfg.service.log_file = tmp_path / "logs" / "quant_service.log"
    cfg.service.heartbeat_file = tmp_path / "state" / "quant_service_heartbeat.json"
    cfg.service.pid_file = tmp_path / "state" / "quant_service.pid"

    def fake_runner(*args, **kwargs):
        return {"selected": ["BTC/USDT"], "orders": [], "messages": []}

    monkeypatch.setattr(service, "run_okx_live_portfolio_once", fake_runner)
    result = run_live_portfolio_service(
        cfg,
        ["BTC/USDT", "ETH/USDT"],
        "spot",
        interval_seconds=0,
        confirm_live=True,
        refresh_candles=False,
        max_iterations=1,
    )
    assert result["iterations"] == 1
    heartbeat = json.loads((tmp_path / "state" / "quant_service_heartbeat.json").read_text())
    assert heartbeat["stop_reason"] == "completed"


def test_cli_kill_creates_kill_switch(tmp_path):
    overlay = write_overlay(tmp_path)
    code = main(["--config", str(overlay), "kill"])
    assert code == 0
    assert (tmp_path / "state" / "KILL_SWITCH").exists()


def test_cli_paper_synthetic_does_not_require_okx_network(tmp_path):
    overlay = write_overlay(tmp_path)
    code = main(
        [
            "--config",
            str(overlay),
            "paper",
            "run",
            "--symbol",
            "BTC/USDT",
            "--instrument-type",
            "spot",
            "--use-synthetic",
        ]
    )
    assert code == 0
    assert (tmp_path / "state" / "quant_system.sqlite").exists()


def test_cli_okx_demo_smoke_requires_demo_mode(tmp_path):
    overlay = tmp_path / "liveish.yaml"
    overlay.write_text(
        "\n".join(
            [
                "data_dir: " + str(tmp_path / "data"),
                "report_dir: " + str(tmp_path / "reports"),
                "state_dir: " + str(tmp_path / "state"),
                "log_dir: " + str(tmp_path / "logs"),
                "okx:",
                "  demo_trading: false",
            ]
        ),
        encoding="utf-8",
    )
    with pytest.raises(PermissionError, match="demo-smoke requires"):
        main(["--config", str(overlay), "okx", "demo-smoke"])


def test_cli_okx_demo_smoke_requires_demo_credentials(tmp_path, monkeypatch):
    overlay = tmp_path / "missing_demo.yaml"
    overlay.write_text(
        "\n".join(
            [
                "data_dir: " + str(tmp_path / "data"),
                "report_dir: " + str(tmp_path / "reports"),
                "state_dir: " + str(tmp_path / "state"),
                "log_dir: " + str(tmp_path / "logs"),
                "okx:",
                "  demo_api_key_env: MISSING_OKX_DEMO_API_KEY",
                "  demo_api_secret_env: MISSING_OKX_DEMO_API_SECRET",
                "  demo_passphrase_env: MISSING_OKX_DEMO_PASSPHRASE",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("OKX_DEMO_API_KEY", raising=False)
    monkeypatch.delenv("OKX_DEMO_API_SECRET", raising=False)
    monkeypatch.delenv("OKX_DEMO_PASSPHRASE", raising=False)
    with pytest.raises(PermissionError, match="OKX_DEMO_API_KEY"):
        main(["--config", str(overlay), "okx", "demo-smoke"])


def test_cli_okx_demo_run_requires_demo_credentials(tmp_path, monkeypatch):
    overlay = tmp_path / "missing_demo.yaml"
    overlay.write_text(
        "\n".join(
            [
                "data_dir: " + str(tmp_path / "data"),
                "report_dir: " + str(tmp_path / "reports"),
                "state_dir: " + str(tmp_path / "state"),
                "log_dir: " + str(tmp_path / "logs"),
                "okx:",
                "  demo_api_key_env: MISSING_OKX_DEMO_API_KEY",
                "  demo_api_secret_env: MISSING_OKX_DEMO_API_SECRET",
                "  demo_passphrase_env: MISSING_OKX_DEMO_PASSPHRASE",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("OKX_DEMO_API_KEY", raising=False)
    monkeypatch.delenv("OKX_DEMO_API_SECRET", raising=False)
    monkeypatch.delenv("OKX_DEMO_PASSPHRASE", raising=False)
    with pytest.raises(PermissionError, match="OKX_DEMO_API_KEY"):
        main(["--config", str(overlay), "okx", "demo-run-once"])


def test_cli_okx_demo_loop_records_missing_credentials(tmp_path, monkeypatch):
    overlay = write_overlay(tmp_path)
    monkeypatch.delenv("OKX_DEMO_API_KEY", raising=False)
    monkeypatch.delenv("OKX_DEMO_API_SECRET", raising=False)
    monkeypatch.delenv("OKX_DEMO_PASSPHRASE", raising=False)
    code = main(
        [
            "--config",
            str(overlay),
            "okx",
            "demo-loop",
            "--max-iterations",
            "1",
            "--interval-seconds",
            "0",
        ]
    )
    assert code == 0
    assert (tmp_path / "state" / "quant_system.sqlite").exists()


def test_cli_okx_cancel_all_after_command_exists(tmp_path, monkeypatch):
    from quant_system import cli

    overlay = write_overlay(tmp_path)

    class FakeClient:
        class Credentials:
            present = True

        credentials = Credentials()

        def __init__(self, _settings):
            pass

        def cancel_all_after(self, timeout_seconds):
            return {"code": "0", "data": [{"timeout": timeout_seconds}]}

    monkeypatch.setattr(cli, "OkxRestClient", FakeClient)
    code = main(["--config", str(overlay), "okx", "cancel-all-after", "--timeout-seconds", "60"])
    assert code == 0


def test_cli_service_run_demo_records_heartbeat_on_missing_credentials(tmp_path):
    overlay = tmp_path / "service_missing_demo.yaml"
    overlay.write_text(
        "\n".join(
            [
                "data_dir: " + str(tmp_path / "data"),
                "report_dir: " + str(tmp_path / "reports"),
                "state_dir: " + str(tmp_path / "state"),
                "log_dir: " + str(tmp_path / "logs"),
                "okx:",
                "  demo_api_key_env: MISSING_OKX_DEMO_API_KEY",
                "  demo_api_secret_env: MISSING_OKX_DEMO_API_SECRET",
                "  demo_passphrase_env: MISSING_OKX_DEMO_PASSPHRASE",
                "service:",
                "  pid_file: " + str(tmp_path / "state" / "quant_service.pid"),
                "  stop_file: " + str(tmp_path / "state" / "quant_service.stop"),
                "  heartbeat_file: " + str(tmp_path / "state" / "quant_service_heartbeat.json"),
                "  log_file: " + str(tmp_path / "logs" / "quant_service.log"),
                "  max_consecutive_errors: 1",
                "  retry_backoff_seconds: 0",
            ]
        ),
        encoding="utf-8",
    )
    code = main(
        [
            "--config",
            str(overlay),
            "service",
            "run-demo",
            "--max-iterations",
            "1",
            "--interval-seconds",
            "0",
        ]
    )
    assert code == 0
    assert (tmp_path / "state" / "quant_service_heartbeat.json").exists()
    assert (tmp_path / "logs" / "quant_service.log").exists()


def test_cli_service_status(tmp_path):
    overlay = write_overlay(tmp_path)
    code = main(["--config", str(overlay), "service", "status"])
    assert code == 0


def test_cli_research_sweep_reports_missing_data(tmp_path):
    overlay = write_overlay(tmp_path)
    code = main(
        [
            "--config",
            str(overlay),
            "research",
            "sweep",
            "--symbol",
            "BTC/USDT",
            "--allow-quality-issues",
        ]
    )
    assert code == 0


def test_cli_research_xsmom_reports_insufficient_data(tmp_path):
    overlay = write_overlay(tmp_path)
    code = main(["--config", str(overlay), "research", "xsmom", "--symbol", "BTC/USDT", "--symbol", "ETH/USDT"])
    assert code == 0


def test_cli_research_scaffold_writes_strategy_research_template(tmp_path):
    overlay = write_overlay(tmp_path)
    output_dir = tmp_path / "scaffolds"
    code = main(
        [
            "--config",
            str(overlay),
            "research",
            "scaffold",
            "--strategy-id",
            "crypto_cross_sectional_momentum",
            "--output-dir",
            str(output_dir),
        ]
    )
    path = output_dir / "crypto_cross_sectional_momentum_research_scaffold.md"
    assert code == 0
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "Cross-sectional crypto momentum" in text
    assert "Implementation Checklist" in text


def test_cli_data_history_command_exists(tmp_path, monkeypatch):
    from quant_system import cli

    overlay = write_overlay(tmp_path)
    monkeypatch.setattr(cli, "backfill_history_candles", lambda *args, **kwargs: [])
    code = main(["--config", str(overlay), "data", "history", "--symbol", "BTC/USDT", "--pages", "1"])
    assert code == 0


def test_cli_data_exchange_info_writes_ods_and_dwd(tmp_path, monkeypatch):
    from quant_system import cli

    overlay = write_overlay(tmp_path)

    class FakeClient:
        def __init__(self, settings):
            self.settings = settings

        def get_instruments(self, instrument_type):
            return [
                {
                    "instId": "BTC-USDT" if instrument_type == "spot" else "BTC-USDT-SWAP",
                    "baseCcy": "BTC",
                    "quoteCcy": "USDT",
                    "settleCcy": "USDT",
                    "state": "live",
                    "minSz": "0.00001",
                    "lotSz": "0.00001",
                    "tickSz": "0.1",
                    "ctVal": "0.01",
                }
            ]

    monkeypatch.setattr(cli, "OkxRestClient", FakeClient)
    code = main(["--config", str(overlay), "data", "exchange-info", "--instrument-type", "spot"])
    audit = AuditStore(tmp_path / "state")
    with audit.connect() as conn:
        raw_count = conn.execute("SELECT COUNT(*) AS count FROM ods_crypto_exchange_info_raw").fetchone()["count"]
        dwd_count = conn.execute("SELECT COUNT(*) AS count FROM dwd_crypto_exchange_info").fetchone()["count"]
        task_count = conn.execute("SELECT COUNT(*) AS count FROM data_ingestion_tasks").fetchone()["count"]
        repro_count = conn.execute("SELECT COUNT(*) AS count FROM reproducibility_records").fetchone()["count"]
    assert code == 0
    assert raw_count == 1
    assert dwd_count == 1
    assert task_count == 1
    assert repro_count == 1


def test_cli_data_derivative_market_tables_write_ods_and_dwd(tmp_path, monkeypatch):
    from quant_system import cli

    overlay = write_overlay(tmp_path)

    class FakeClient:
        def __init__(self, settings):
            self.settings = settings

        def get_open_interest(self, symbol, instrument_type="swap"):
            return [{"instId": "BTC-USDT-SWAP", "ts": "1710000000000", "oi": "123.4", "oiCcy": "12.34"}]

        def get_mark_price(self, symbol, instrument_type="swap"):
            return {"instId": "BTC-USDT-SWAP", "ts": "1710000000000", "markPx": "101.5"}

        def get_index_ticker(self, symbol):
            return {"instId": "BTC-USDT", "ts": "1710000000000", "idxPx": "100.0"}

        def get_contract_long_short_ratio(self, symbol, period="5m", limit=100):
            return [["1710000000000", "1.25"]]

        def get_orderbook(self, symbol, instrument_type, depth=50):
            return {
                "ts": "1710000000000",
                "asks": [["101", "2", "0", "1"]],
                "bids": [["100", "3", "0", "2"]],
            }

        def get_recent_trades(self, symbol, instrument_type, limit=100):
            return [{"tradeId": "t1", "ts": "1710000000000", "side": "buy", "px": "100.5", "sz": "0.1"}]

        def get_liquidation_orders(self, symbol, instrument_type="swap", limit=100):
            return [
                {
                    "instType": "SWAP",
                    "details": [
                        {"instId": "BTC-USDT-SWAP", "ts": "1710000000000", "side": "sell", "bkPx": "99", "sz": "10"}
                    ],
                }
            ]

    monkeypatch.setattr(cli, "OkxRestClient", FakeClient)
    commands = [
        ["data", "open-interest", "--symbol", "BTC/USDT"],
        ["data", "basis", "--symbol", "BTC/USDT"],
        ["data", "long-short-ratio", "--symbol", "BTC/USDT", "--period", "5m", "--limit", "1"],
        ["data", "orderbook", "--symbol", "BTC/USDT", "--instrument-type", "swap", "--depth", "1"],
        ["data", "trades", "--symbol", "BTC/USDT", "--instrument-type", "swap", "--limit", "1"],
        ["data", "liquidations", "--symbol", "BTC/USDT", "--limit", "1"],
    ]
    for command in commands:
        assert main(["--config", str(overlay), *command]) == 0

    audit = AuditStore(tmp_path / "state")
    with audit.connect() as conn:
        raw_count = conn.execute("SELECT COUNT(*) AS count FROM ods_crypto_market_data_raw").fetchone()["count"]
        open_interest_count = conn.execute("SELECT COUNT(*) AS count FROM dwd_crypto_open_interest").fetchone()["count"]
        basis_count = conn.execute("SELECT COUNT(*) AS count FROM dwd_crypto_basis").fetchone()["count"]
        ratio_count = conn.execute("SELECT COUNT(*) AS count FROM dwd_crypto_long_short_ratio").fetchone()["count"]
        book_count = conn.execute("SELECT COUNT(*) AS count FROM dwd_crypto_orderbook_snapshot").fetchone()["count"]
        trade_count = conn.execute("SELECT COUNT(*) AS count FROM dwd_crypto_trades").fetchone()["count"]
        liquidation_count = conn.execute("SELECT COUNT(*) AS count FROM dwd_crypto_liquidations").fetchone()["count"]
    assert raw_count == 6
    assert open_interest_count == 1
    assert basis_count == 1
    assert ratio_count == 1
    assert book_count == 2
    assert trade_count == 1
    assert liquidation_count == 1


def test_cli_data_universe_command_writes_file(tmp_path, monkeypatch):
    from quant_system import cli

    overlay = write_overlay(tmp_path)
    monkeypatch.setattr(
        cli,
        "discover_usdt_universe",
        lambda *args, **kwargs: [
            {
                "symbol": "BTC/USDT",
                "inst_id": "BTC-USDT",
                "instrument_type": "spot",
                "quote_volume_24h": 100.0,
                "last": 100000.0,
                "base": "BTC",
                "quote": "USDT",
            }
        ],
    )
    code = main(["--config", str(overlay), "data", "universe", "--top-n", "1", "--write"])
    assert code == 0
    assert (tmp_path / "data" / "universe" / "okx_spot_usdt_top1.json").exists()


def test_cli_research_xsmom_grid_command_exists(tmp_path):
    overlay = write_overlay(tmp_path)
    code = main(
        [
            "--config",
            str(overlay),
            "research",
            "xsmom-grid",
            "--symbol",
            "BTC/USDT",
            "--symbol",
            "ETH/USDT",
            "--lookback-bars",
            "24",
            "--hold-bars",
            "24",
        ]
    )
    assert code == 0


def test_cli_research_xsmom_walk_forward_writes_report(tmp_path):
    overlay = write_overlay(tmp_path)
    store = CandleStore(tmp_path / "data")
    store.write(synthetic_candles("BTC/USDT", "spot", periods=500), "BTC/USDT", "spot", "1H")
    store.write(synthetic_candles("ETH/USDT", "spot", periods=500), "ETH/USDT", "spot", "1H")
    code = main(
        [
            "--config",
            str(overlay),
            "research",
            "xsmom-walk-forward",
            "--symbol",
            "BTC/USDT",
            "--symbol",
            "ETH/USDT",
            "--lookback-bars",
            "24",
            "--hold-bars",
            "24",
            "--top-n",
            "1",
            "--train-bars",
            "180",
            "--test-bars",
            "96",
            "--min-trades",
            "1",
            "--write-report",
        ]
    )
    assert code == 0
    payload = json.loads((tmp_path / "reports" / "cross_sectional_momentum_walk_forward_latest.json").read_text())
    assert payload["summary"]["schema"] == "rolling_walk_forward_v1"
    assert "parameter_drift" in payload["summary"]


def test_cli_research_xsmom_costs_writes_report(tmp_path):
    overlay = write_overlay(tmp_path)
    store = CandleStore(tmp_path / "data")
    store.write(synthetic_candles("BTC/USDT", "spot", periods=900), "BTC/USDT", "spot", "1H")
    store.write(synthetic_candles("ETH/USDT", "spot", periods=900), "ETH/USDT", "spot", "1H")
    code = main(
        [
            "--config",
            str(overlay),
            "research",
            "xsmom-costs",
            "--symbol",
            "BTC/USDT",
            "--symbol",
            "ETH/USDT",
            "--lookback-bars",
            "24",
            "--hold-bars",
            "24",
            "--top-n",
            "1",
            "--fee-rate",
            "0.0008",
            "--slippage-bps",
            "2",
            "--write-report",
        ]
    )
    assert code == 0
    payload = json.loads((tmp_path / "reports" / "cross_sectional_momentum_cost_sensitivity_latest.json").read_text())
    assert payload["summary"]["schema"] == "cost_sensitivity_v1"
    assert "recommendation" in payload["summary"]


def test_cli_research_adaptive_trend_writes_report(tmp_path):
    overlay = write_overlay(tmp_path)
    store = CandleStore(tmp_path / "data")
    store.write(synthetic_candles("BTC/USDT", "spot", periods=900), "BTC/USDT", "spot", "1H")
    store.write(synthetic_candles("ETH/USDT", "spot", periods=900), "ETH/USDT", "spot", "1H")
    code = main(
        [
            "--config",
            str(overlay),
            "research",
            "adaptive-trend",
            "--symbol",
            "BTC/USDT",
            "--symbol",
            "ETH/USDT",
            "--lookback-bars",
            "24",
            "--hold-bars",
            "24",
            "--top-n",
            "1",
            "--ema-span",
            "24",
            "--volatility-bars",
            "24",
            "--write-report",
        ]
    )
    assert code == 0
    assert (tmp_path / "reports" / "adaptive_trend_latest.json").exists()


def test_cli_research_adaptive_trend_grid_command_exists(tmp_path):
    overlay = write_overlay(tmp_path)
    store = CandleStore(tmp_path / "data")
    store.write(synthetic_candles("BTC/USDT", "spot", periods=300), "BTC/USDT", "spot", "1H")
    store.write(synthetic_candles("ETH/USDT", "spot", periods=300), "ETH/USDT", "spot", "1H")
    code = main(
        [
            "--config",
            str(overlay),
            "research",
            "adaptive-trend-grid",
            "--symbol",
            "BTC/USDT",
            "--symbol",
            "ETH/USDT",
            "--lookback-bars",
            "24",
            "--hold-bars",
            "24",
            "--top-n",
            "1",
            "--ema-span",
            "24",
            "--volatility-bars",
            "24",
            "--target-volatility",
            "0.20",
            "--max-weight",
            "0.50",
            "--min-trades",
            "1",
        ]
    )
    assert code == 0


def test_adaptive_trend_grid_report_includes_parameter_stability(tmp_path):
    overlay = write_overlay(tmp_path)
    store = CandleStore(tmp_path / "data")
    store.write(synthetic_candles("BTC/USDT", "spot", periods=300), "BTC/USDT", "spot", "1H")
    store.write(synthetic_candles("ETH/USDT", "spot", periods=300), "ETH/USDT", "spot", "1H")
    code = main(
        [
            "--config",
            str(overlay),
            "research",
            "adaptive-trend-grid",
            "--symbol",
            "BTC/USDT",
            "--symbol",
            "ETH/USDT",
            "--lookback-bars",
            "24",
            "--hold-bars",
            "24",
            "--top-n",
            "1",
            "--ema-span",
            "24",
            "--volatility-bars",
            "24",
            "--target-volatility",
            "0.20",
            "--max-weight",
            "0.50",
            "--min-trades",
            "1",
            "--write-report",
        ]
    )
    assert code == 0
    payload = json.loads((tmp_path / "reports" / "adaptive_trend_grid_latest.json").read_text())
    assert "parameter_stability" in payload
    assert "candidate_count" in payload["parameter_stability"]
    assert payload["overfitting_diagnostics"]["schema"] == "overfitting_diagnostics_v1"


def test_cli_research_adaptive_trend_walk_forward_writes_report(tmp_path):
    overlay = write_overlay(tmp_path)
    store = CandleStore(tmp_path / "data")
    store.write(synthetic_candles("BTC/USDT", "spot", periods=500), "BTC/USDT", "spot", "1H")
    store.write(synthetic_candles("ETH/USDT", "spot", periods=500), "ETH/USDT", "spot", "1H")
    code = main(
        [
            "--config",
            str(overlay),
            "research",
            "adaptive-trend-walk-forward",
            "--symbol",
            "BTC/USDT",
            "--symbol",
            "ETH/USDT",
            "--lookback-bars",
            "24",
            "--hold-bars",
            "24",
            "--top-n",
            "1",
            "--ema-span",
            "24",
            "--volatility-bars",
            "24",
            "--target-volatility",
            "0.20",
            "--max-weight",
            "0.50",
            "--train-bars",
            "180",
            "--test-bars",
            "96",
            "--min-trades",
            "1",
            "--write-report",
        ]
    )
    assert code == 0
    payload = json.loads((tmp_path / "reports" / "adaptive_trend_walk_forward_latest.json").read_text())
    assert payload["summary"]["schema"] == "rolling_walk_forward_v1"
    assert "parameter_drift" in payload["summary"]


def test_cli_research_adaptive_trend_costs_writes_report(tmp_path):
    overlay = write_overlay(tmp_path)
    store = CandleStore(tmp_path / "data")
    store.write(synthetic_candles("BTC/USDT", "spot", periods=900), "BTC/USDT", "spot", "1H")
    store.write(synthetic_candles("ETH/USDT", "spot", periods=900), "ETH/USDT", "spot", "1H")
    code = main(
        [
            "--config",
            str(overlay),
            "research",
            "adaptive-trend-costs",
            "--symbol",
            "BTC/USDT",
            "--symbol",
            "ETH/USDT",
            "--lookback-bars",
            "24",
            "--hold-bars",
            "24",
            "--top-n",
            "1",
            "--ema-span",
            "24",
            "--volatility-bars",
            "24",
            "--target-volatility",
            "0.20",
            "--max-weight",
            "0.50",
            "--fee-rate",
            "0.0008",
            "--slippage-bps",
            "2",
            "--write-report",
        ]
    )
    assert code == 0
    payload = json.loads((tmp_path / "reports" / "adaptive_trend_cost_sensitivity_latest.json").read_text())
    assert payload["summary"]["schema"] == "cost_sensitivity_v1"
    assert "recommendation" in payload["summary"]


def test_cli_research_btc_eth_cointegration_writes_report(tmp_path):
    overlay = write_overlay(tmp_path)
    store = CandleStore(tmp_path / "data")
    btc = synthetic_candles("BTC/USDT", "spot", periods=260)
    eth = synthetic_candles("ETH/USDT", "spot", periods=260)
    factors = [1.0 + (0.03 if (idx // 24) % 2 == 0 else -0.03) for idx in range(len(eth))]
    eth["close"] = eth["close"] * factors
    eth["open"] = eth["open"] * factors
    store.write(btc, "BTC/USDT", "spot", "1H")
    store.write(eth, "ETH/USDT", "spot", "1H")

    code = main(
        [
            "--config",
            str(overlay),
            "research",
            "btc-eth-cointegration",
            "--symbol",
            "BTC/USDT",
            "--symbol",
            "ETH/USDT",
            "--lookback-bars",
            "48",
            "--max-hold-bars",
            "24",
            "--entry-z",
            "1.0",
            "--write-report",
        ]
    )

    report_path = tmp_path / "reports" / "btc_eth_cointegration_pairs_latest.json"
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert code == 0
    assert payload["status"] == "ok"
    assert payload["confirmed_only"] is True
    assert payload["execution_model"] == "next_bar_open"
    assert "annualized_return" in payload["metrics"]


def test_cli_research_funding_carry_writes_report(tmp_path):
    overlay = write_overlay(tmp_path)
    write_sample_funding_rates(tmp_path)
    code = main(
        [
            "--config",
            str(overlay),
            "research",
            "funding-carry",
            "--symbol",
            "BTC/USDT",
            "--symbol",
            "ETH/USDT",
            "--lookback-periods",
            "3",
            "--hold-periods",
            "1",
            "--top-n",
            "1",
            "--write-report",
        ]
    )
    assert code == 0
    assert (tmp_path / "reports" / "funding_carry_latest.json").exists()


def write_sample_funding_rates(tmp_path: Path, periods: int = 160) -> None:
    store = FundingRateStore(tmp_path / "data")
    ts = pd.date_range("2024-01-01", periods=periods, freq="8h", tz="UTC")
    btc = pd.DataFrame(
        {
            "ts": ts,
            "symbol": "BTC/USDT",
            "instrument_type": "swap",
            "inst_id": "BTC-USDT-SWAP",
            "funding_rate": [0.0001 + (i % 5) * 0.00001 for i in range(len(ts))],
            "raw_funding_rate": [0.0001 + (i % 5) * 0.00001 for i in range(len(ts))],
            "method": ["current_period"] * len(ts),
        }
    )
    eth = btc.copy()
    eth["symbol"] = "ETH/USDT"
    eth["inst_id"] = "ETH-USDT-SWAP"
    eth["funding_rate"] = [0.00005 + (i % 3) * 0.00001 for i in range(len(ts))]
    eth["raw_funding_rate"] = eth["funding_rate"]
    store.write(btc, "BTC/USDT")
    store.write(eth, "ETH/USDT")


def test_cli_research_funding_carry_grid_writes_report(tmp_path):
    overlay = write_overlay(tmp_path)
    write_sample_funding_rates(tmp_path)
    code = main(
        [
            "--config",
            str(overlay),
            "research",
            "funding-carry-grid",
            "--symbol",
            "BTC/USDT",
            "--symbol",
            "ETH/USDT",
            "--lookback-periods",
            "3",
            "--hold-periods",
            "1",
            "--top-n",
            "1",
            "--min-funding-rate",
            "0",
            "--max-notional-pct",
            "0.5",
            "--min-rebalances",
            "1",
            "--write-report",
        ]
    )
    assert code == 0
    assert (tmp_path / "reports" / "funding_carry_grid_latest.json").exists()


def test_cli_research_funding_carry_walk_forward_writes_report(tmp_path):
    overlay = write_overlay(tmp_path)
    write_sample_funding_rates(tmp_path, periods=220)
    code = main(
        [
            "--config",
            str(overlay),
            "research",
            "funding-carry-walk-forward",
            "--symbol",
            "BTC/USDT",
            "--symbol",
            "ETH/USDT",
            "--lookback-periods",
            "3",
            "--hold-periods",
            "1",
            "--top-n",
            "1",
            "--min-funding-rate",
            "0",
            "--max-notional-pct",
            "0.5",
            "--train-periods",
            "80",
            "--test-periods",
            "40",
            "--min-rebalances",
            "1",
            "--write-report",
        ]
    )
    assert code == 0
    payload = json.loads((tmp_path / "reports" / "funding_carry_walk_forward_latest.json").read_text())
    assert payload["summary"]["schema"] == "rolling_walk_forward_v1"
    assert "parameter_drift" in payload["summary"]


def test_cli_research_funding_carry_costs_writes_report(tmp_path):
    overlay = write_overlay(tmp_path)
    write_sample_funding_rates(tmp_path)
    code = main(
        [
            "--config",
            str(overlay),
            "research",
            "funding-carry-costs",
            "--symbol",
            "BTC/USDT",
            "--symbol",
            "ETH/USDT",
            "--lookback-periods",
            "3",
            "--hold-periods",
            "1",
            "--top-n",
            "1",
            "--min-funding-rate",
            "0",
            "--max-notional-pct",
            "0.5",
            "--fee-rate",
            "0.0008",
            "--slippage-bps",
            "2",
            "--write-report",
        ]
    )
    assert code == 0
    payload = json.loads((tmp_path / "reports" / "funding_carry_cost_sensitivity_latest.json").read_text())
    assert payload["summary"]["schema"] == "cost_sensitivity_v1"
    assert "recommendation" in payload["summary"]


def test_cli_research_shortlist_writes_ranked_decisions(tmp_path):
    overlay = write_overlay(tmp_path)
    reports = tmp_path / "reports"
    reports.mkdir(parents=True, exist_ok=True)

    def write_report_file(name, payload):
        (reports / f"{name}_latest.json").write_text(json.dumps(payload), encoding="utf-8")

    write_report_file(
        "cross_sectional_momentum_walk_forward",
        {"summary": {"compounded_oos_return": 0.3, "mean_oos_sharpe": 4, "positive_oos_fold_rate": 0.75, "worst_oos_drawdown": -0.1}},
    )
    write_report_file(
        "cross_sectional_momentum_cost_sensitivity",
        {"summary": {"positive_scenario_rate": 1.0, "worst_total_return": 0.2, "worst_drawdown": -0.1}},
    )
    write_report_file(
        "adaptive_trend_walk_forward",
        {"summary": {"compounded_oos_return": 0.1, "mean_oos_sharpe": 5, "positive_oos_fold_rate": 1.0, "worst_oos_drawdown": -0.02}},
    )
    write_report_file(
        "adaptive_trend_cost_sensitivity",
        {"summary": {"positive_scenario_rate": 1.0, "worst_total_return": 0.08, "worst_drawdown": -0.02}},
    )
    write_report_file(
        "funding_carry_walk_forward",
        {"summary": {"compounded_oos_return": 0.1, "mean_oos_sharpe": -0.5, "positive_oos_fold_rate": 0.2, "worst_oos_drawdown": -0.03}},
    )
    write_report_file(
        "funding_carry_cost_sensitivity",
        {"summary": {"positive_scenario_rate": 1.0, "worst_total_return": 0.3, "worst_drawdown": -0.1}},
    )
    write_report_file(
        "service_stability",
        {"observation_age_seconds": 100, "summary": {"healthy": True, "service_running": True, "watchdog_running": True, "failure_event_count": 0}},
    )
    write_report_file(
        "live_gate_drill",
        {"status": "passed", "checks": [{"name": "config_live_enabled_false_blocks", "passed": True}]},
    )

    code = main(["--config", str(overlay), "research", "shortlist", "--write-report"])
    assert code == 0
    latest = reports / "strategy_shortlist_latest.json"
    assert latest.exists()
    payload = json.loads(latest.read_text())
    assert payload["primary"] in {"cross_sectional_momentum", "adaptive_trend"}
    assert payload["live_gate_drill"]["status"] == "passed"
    assert payload["live_ready"] is False
    assert "24h+ paper stability window is not complete" in payload["live_ready_reason"]
    funding = next(item for item in payload["ranked"] if item["name"] == "funding_carry")
    assert funding["decision"] == "research_only"
    assert "positive OOS fold rate below 60%" in funding["blockers"]


def test_cli_research_promotion_scorecard_writes_unified_stages(tmp_path):
    overlay = write_overlay(tmp_path)
    reports = tmp_path / "reports"
    reports.mkdir(parents=True, exist_ok=True)

    def write_report_file(name, payload):
        (reports / f"{name}_latest.json").write_text(json.dumps(payload), encoding="utf-8")

    write_report_file(
        "cross_sectional_momentum_walk_forward",
        {"summary": {"compounded_oos_return": 0.3, "mean_oos_sharpe": 3.0, "positive_oos_fold_rate": 0.8, "worst_oos_drawdown": -0.1}},
    )
    write_report_file(
        "cross_sectional_momentum_cost_sensitivity",
        {"summary": {"positive_scenario_rate": 1.0, "worst_total_return": 0.2, "worst_drawdown": -0.1}},
    )
    write_report_file(
        "adaptive_trend_walk_forward",
        {"summary": {"compounded_oos_return": 0.1, "mean_oos_sharpe": 2.0, "positive_oos_fold_rate": 0.75, "worst_oos_drawdown": -0.05}},
    )
    write_report_file(
        "adaptive_trend_cost_sensitivity",
        {"summary": {"positive_scenario_rate": 1.0, "worst_total_return": 0.08, "worst_drawdown": -0.04}},
    )
    write_report_file(
        "funding_carry_walk_forward",
        {"summary": {"compounded_oos_return": 0.1, "mean_oos_sharpe": 0.2, "positive_oos_fold_rate": 0.25, "worst_oos_drawdown": -0.03}},
    )
    write_report_file(
        "funding_carry_cost_sensitivity",
        {"summary": {"positive_scenario_rate": 1.0, "worst_total_return": 0.2, "worst_drawdown": -0.04}},
    )
    write_report_file(
        "service_stability",
        {
            "observation_age_seconds": 48 * 3600,
            "summary": {"healthy": True, "service_running": True, "watchdog_running": True, "failure_event_count": 0},
        },
    )
    write_report_file(
        "live_gate_drill",
        {"status": "passed", "checks": [{"name": "config_live_enabled_false_blocks", "passed": True}]},
    )

    code = main(["--config", str(overlay), "research", "promotion-scorecard", "--write-report"])

    assert code == 0
    payload = json.loads((reports / "strategy_promotion_scorecard_latest.json").read_text())
    assert payload["schema"] == "strategy_promotion_scorecard_v1"
    assert payload["stage_order"] == ["idea", "factor", "strategy", "paper", "small_live"]
    xsmom = next(item for item in payload["ranked"] if item["name"] == "cross_sectional_momentum")
    funding = next(item for item in payload["ranked"] if item["name"] == "funding_carry")
    assert xsmom["stage"] == "paper"
    assert xsmom["score_components"]["total"] > funding["score_components"]["total"]
    assert funding["stage"] == "strategy"
    assert funding["promotion_status"] == "blocked"


def test_cli_research_multi_timeframe_sweep_writes_report(tmp_path):
    overlay = write_overlay(tmp_path)
    store = CandleStore(tmp_path / "data")
    for symbol, multiplier in [("BTC/USDT", 1.0), ("ETH/USDT", 1.3), ("SOL/USDT", 1.6)]:
        store.write(synthetic_bar_candles(symbol, "spot", multiplier, periods=180, freq="h"), symbol, "spot", "1H")
        store.write(synthetic_bar_candles(symbol, "spot", multiplier, periods=180, freq="4h"), symbol, "spot", "4H")

    code = main(
        [
            "--config",
            str(overlay),
            "research",
            "multi-timeframe-sweep",
            "--symbol",
            "BTC/USDT",
            "--symbol",
            "ETH/USDT",
            "--symbol",
            "SOL/USDT",
            "--bar",
            "1H",
            "--bar",
            "4H",
            "--strategy",
            "trend_mr",
            "--write-report",
        ]
    )

    assert code == 0
    payload = json.loads((tmp_path / "reports" / "multi_timeframe_strategy_sweep_latest.json").read_text())
    assert payload["schema"] == "multi_timeframe_strategy_sweep_v1"
    assert payload["bars"] == ["1H", "4H"]
    assert {row["bar"] for row in payload["rows"] if row["status"] == "ok"} == {"1H", "4H"}
    assert payload["aggregate"][0]["timeframe_count"] == 2


def test_cli_review_queue_collects_quality_and_promotion_tasks(tmp_path):
    overlay = write_overlay(tmp_path)
    audit = AuditStore(tmp_path / "state")
    audit.insert_data_quality_issues(
        [
            {
                "table_name": "dwd_crypto_ohlcv",
                "exchange": "okx",
                "symbol": "BTC/USDT",
                "market_type": "spot",
                "interval": "1H",
                "issue_type": "missing_data",
                "issue_detail": "No local OHLCV rows",
                "severity": "error",
            }
        ]
    )
    reports = tmp_path / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "strategy_promotion_scorecard_latest.json").write_text(
        json.dumps(
            {
                "schema": "strategy_promotion_scorecard_v1",
                "ranked": [
                    {
                        "name": "cross_sectional_momentum",
                        "stage": "paper",
                        "promotion_status": "blocked",
                        "research_blocker_count": 0,
                        "blockers": ["notification webhook is not configured"],
                    },
                    {
                        "name": "funding_carry",
                        "stage": "strategy",
                        "promotion_status": "blocked",
                        "research_blocker_count": 1,
                        "blockers": ["positive OOS fold rate below 60%"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    code = main(["--config", str(overlay), "review", "queue", "--write-report"])

    assert code == 0
    payload = json.loads((reports / "review_queue_latest.json").read_text())
    assert payload["schema"] == "review_queue_v1"
    assert payload["summary"]["by_category"]["data_quality"] == 1
    assert payload["summary"]["by_category"]["strategy_promotion"] == 1
    assert payload["summary"]["by_category"]["strategy_review"] == 1
    rows = [dict(row) for row in audit.recent_rows("review_tasks", limit=10)]
    assert {row["category"] for row in rows} >= {"data_quality", "strategy_promotion", "strategy_review"}


def test_cli_paper_portfolio_run_once_persists_state(tmp_path):
    overlay = write_overlay(tmp_path)
    store = CandleStore(tmp_path / "data")
    store.write(synthetic_candles("BTC/USDT", "spot", periods=900), "BTC/USDT", "spot", "1H")
    store.write(synthetic_candles("ETH/USDT", "spot", periods=900), "ETH/USDT", "spot", "1H")
    code = main(
        [
            "--config",
            str(overlay),
            "paper",
            "portfolio-run-once",
            "--symbol",
            "BTC/USDT",
            "--symbol",
            "ETH/USDT",
            "--lookback-bars",
            "24",
            "--top-n",
            "1",
        ]
    )
    assert code == 0
    assert (tmp_path / "state" / "quant_system.sqlite").exists()


def test_cli_service_notification_drill_local_only_writes_report(tmp_path, monkeypatch):
    overlay = write_overlay(tmp_path)
    monkeypatch.delenv("QUANT_NOTIFICATION_WEBHOOK_URL", raising=False)
    code = main(
        [
            "--config",
            str(overlay),
            "service",
            "notification-drill",
            "--level",
            "warning",
        ]
    )
    assert code == 0
    latest = tmp_path / "reports" / "notification_drill_latest.json"
    assert latest.exists()
    payload = json.loads(latest.read_text(encoding="utf-8"))
    assert payload["status"] == "local_only"
    assert payload["level"] == "warning"
    assert payload["local_log_ok"] is True
    assert payload["webhook_configured"] is False
    assert payload["webhook_ok"] is False
    assert payload["live_ready_contribution"] is False
    rows = (tmp_path / "logs" / "quant_notifications.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(rows[-1])["event"] == "notification_drill"


def test_cli_service_snapshot_writes_redacted_runtime_report(tmp_path, monkeypatch):
    overlay = write_overlay(tmp_path)
    monkeypatch.setenv("OKX_API_KEY", "prod-key-secret-value")
    monkeypatch.setenv("OKX_API_SECRET", "prod-secret-value")
    monkeypatch.setenv("OKX_PASSPHRASE", "prod-passphrase-value")
    monkeypatch.setenv("OKX_DEMO_API_KEY", "demo-key-secret-value")
    monkeypatch.setenv("OKX_DEMO_API_SECRET", "demo-secret-value")
    monkeypatch.setenv("OKX_DEMO_PASSPHRASE", "demo-passphrase-value")
    code = main(
        [
            "--config",
            str(overlay),
            "service",
            "snapshot",
            "--max-heartbeat-age-seconds",
            "999",
        ]
    )
    assert code == 0
    latest = tmp_path / "reports" / "runtime_snapshot_latest.json"
    assert latest.exists()
    raw = latest.read_text(encoding="utf-8")
    assert "prod-key-secret-value" not in raw
    assert "prod-secret-value" not in raw
    assert "prod-passphrase-value" not in raw
    assert "demo-key-secret-value" not in raw
    assert "demo-secret-value" not in raw
    assert "demo-passphrase-value" not in raw
    payload = json.loads(raw)
    assert payload["strategy"] == "runtime_snapshot"
    assert payload["config_path"] == str(overlay)
    assert payload["okx"]["production_credentials_present"] is True
    assert payload["okx"]["demo_credentials_present"] is True
    assert payload["risk"]["live_trading_cap_usdt"] == 50.0
    assert payload["service_config"]["notification_webhook_configured"] is False


def test_cli_service_pre_live_check_fails_with_missing_gates(tmp_path, monkeypatch):
    overlay = tmp_path / "paper.yaml"
    overlay.write_text(
        "\n".join(
            [
                "data_dir: " + str(tmp_path / "data"),
                "report_dir: " + str(tmp_path / "reports"),
                "state_dir: " + str(tmp_path / "state"),
                "log_dir: " + str(tmp_path / "logs"),
                "okx:",
                "  api_key_env: MISSING_TEST_OKX_KEY",
                "  api_secret_env: MISSING_TEST_OKX_SECRET",
                "  passphrase_env: MISSING_TEST_OKX_PASSPHRASE",
                "risk:",
                "  kill_switch_file: " + str(tmp_path / "state" / "KILL_SWITCH"),
                "service:",
                "  event_log_file: " + str(tmp_path / "logs" / "quant_events.jsonl"),
                "  notification_log_file: " + str(tmp_path / "logs" / "quant_notifications.jsonl"),
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("QUANT_NOTIFICATION_WEBHOOK_URL", raising=False)
    code = main(
        [
            "--config",
            str(overlay),
            "service",
            "pre-live-check",
            "--no-require-running",
            "--no-refresh-stability",
            "--min-observation-hours",
            "0",
        ]
    )
    assert code == 1
    latest = tmp_path / "reports" / "pre_live_check_latest.json"
    assert latest.exists()
    payload = json.loads(latest.read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    failed = set(payload["summary"]["failed_checks"])
    assert "notification_webhook_configured" in failed
    assert "production_live_config_enabled" in failed
    assert "production_credentials_present" in failed


def test_cli_service_pre_live_check_passes_with_all_local_evidence(tmp_path, monkeypatch):
    overlay = tmp_path / "live.yaml"
    overlay.write_text(
        "\n".join(
            [
                "mode: live",
                "data_dir: " + str(tmp_path / "data"),
                "report_dir: " + str(tmp_path / "reports"),
                "state_dir: " + str(tmp_path / "state"),
                "log_dir: " + str(tmp_path / "logs"),
                "okx:",
                "  demo_trading: false",
                "  api_key_env: TEST_OKX_KEY",
                "  api_secret_env: TEST_OKX_SECRET",
                "  passphrase_env: TEST_OKX_PASSPHRASE",
                "execution:",
                "  live_enabled: true",
                "service:",
                "  heartbeat_file: " + str(tmp_path / "state" / "quant_service_heartbeat.json"),
                "  watchdog_heartbeat_file: " + str(tmp_path / "state" / "quant_watchdog_heartbeat.json"),
                "  event_log_file: " + str(tmp_path / "logs" / "quant_events.jsonl"),
                "  notification_log_file: " + str(tmp_path / "logs" / "quant_notifications.jsonl"),
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TEST_OKX_KEY", "key")
    monkeypatch.setenv("TEST_OKX_SECRET", "secret")
    monkeypatch.setenv("TEST_OKX_PASSPHRASE", "pass")
    monkeypatch.setenv("QUANT_NOTIFICATION_WEBHOOK_URL", "https://example.test/webhook")
    now = datetime.now(timezone.utc).isoformat()
    reports = tmp_path / "reports"
    state = tmp_path / "state"
    reports.mkdir(parents=True)
    state.mkdir(parents=True)
    (state / "quant_service_heartbeat.json").write_text(json.dumps({"ts": now, "consecutive_errors": 0}), encoding="utf-8")
    (state / "quant_watchdog_heartbeat.json").write_text(json.dumps({"ts": now, "healthy": True}), encoding="utf-8")
    (reports / "service_stability_latest.json").write_text(
        json.dumps({"observation_age_seconds": 25 * 3600, "summary": {"failure_event_count": 0}}),
        encoding="utf-8",
    )
    (reports / "live_gate_drill_latest.json").write_text(json.dumps({"status": "passed", "checks": []}), encoding="utf-8")
    (reports / "notification_drill_latest.json").write_text(
        json.dumps({"status": "passed", "local_log_ok": True, "webhook_ok": True, "live_ready_contribution": True}),
        encoding="utf-8",
    )
    (reports / "strategy_shortlist_latest.json").write_text(
        json.dumps({"primary": "cross_sectional_momentum", "backup": "adaptive_trend"}),
        encoding="utf-8",
    )
    code = main(
        [
            "--config",
            str(overlay),
            "service",
            "pre-live-check",
            "--no-require-running",
            "--no-refresh-stability",
            "--min-observation-hours",
            "24",
        ]
    )
    assert code == 0
    payload = json.loads((reports / "pre_live_check_latest.json").read_text(encoding="utf-8"))
    assert payload["status"] == "passed"
    assert payload["summary"]["failed_checks"] == []


def test_cli_service_pre_live_check_blocks_operator_risk_overrides(tmp_path, monkeypatch):
    overlay = tmp_path / "live.yaml"
    overlay.write_text(
        "\n".join(
            [
                "mode: live",
                "data_dir: " + str(tmp_path / "data"),
                "report_dir: " + str(tmp_path / "reports"),
                "state_dir: " + str(tmp_path / "state"),
                "log_dir: " + str(tmp_path / "logs"),
                "okx:",
                "  demo_trading: false",
                "  api_key_env: TEST_OKX_KEY",
                "  api_secret_env: TEST_OKX_SECRET",
                "  passphrase_env: TEST_OKX_PASSPHRASE",
                "execution:",
                "  live_enabled: true",
                "risk:",
                "  live_trading_cap_usdt: 75",
                "  max_leverage: 5",
                "service:",
                "  heartbeat_file: " + str(tmp_path / "state" / "quant_service_heartbeat.json"),
                "  watchdog_heartbeat_file: " + str(tmp_path / "state" / "quant_watchdog_heartbeat.json"),
                "  event_log_file: " + str(tmp_path / "logs" / "quant_events.jsonl"),
                "  notification_log_file: " + str(tmp_path / "logs" / "quant_notifications.jsonl"),
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TEST_OKX_KEY", "key")
    monkeypatch.setenv("TEST_OKX_SECRET", "secret")
    monkeypatch.setenv("TEST_OKX_PASSPHRASE", "pass")
    monkeypatch.setenv("QUANT_NOTIFICATION_WEBHOOK_URL", "https://example.test/webhook")
    now = datetime.now(timezone.utc).isoformat()
    reports = tmp_path / "reports"
    state = tmp_path / "state"
    reports.mkdir(parents=True)
    state.mkdir(parents=True)
    (state / "quant_service_heartbeat.json").write_text(json.dumps({"ts": now, "consecutive_errors": 0}), encoding="utf-8")
    (state / "quant_watchdog_heartbeat.json").write_text(json.dumps({"ts": now, "healthy": True}), encoding="utf-8")
    (reports / "service_stability_latest.json").write_text(
        json.dumps({"observation_age_seconds": 25 * 3600, "summary": {"failure_event_count": 0}}),
        encoding="utf-8",
    )
    (reports / "live_gate_drill_latest.json").write_text(json.dumps({"status": "passed", "checks": []}), encoding="utf-8")
    (reports / "notification_drill_latest.json").write_text(
        json.dumps({"status": "passed", "local_log_ok": True, "webhook_ok": True, "live_ready_contribution": True}),
        encoding="utf-8",
    )
    (reports / "strategy_shortlist_latest.json").write_text(
        json.dumps({"primary": "cross_sectional_momentum", "backup": "adaptive_trend"}),
        encoding="utf-8",
    )
    code = main(
        [
            "--config",
            str(overlay),
            "service",
            "pre-live-check",
            "--no-require-running",
            "--no-refresh-stability",
            "--min-observation-hours",
            "24",
        ]
    )
    assert code == 1
    payload = json.loads((reports / "pre_live_check_latest.json").read_text(encoding="utf-8"))
    assert "risk_limits_within_operator_bounds" in payload["summary"]["failed_checks"]
    risk_check = next(check for check in payload["checks"] if check["name"] == "risk_limits_within_operator_bounds")
    assert risk_check["details"]["live_trading_cap_usdt"] == 75
    assert risk_check["details"]["max_leverage"] == 5


def test_cli_service_pre_live_check_refreshes_stability_report(tmp_path, monkeypatch):
    overlay = tmp_path / "paper.yaml"
    old_ts = datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat()
    launch_ts = datetime(2025, 12, 31, tzinfo=timezone.utc).isoformat()
    overlay.write_text(
        "\n".join(
            [
                "data_dir: " + str(tmp_path / "data"),
                "report_dir: " + str(tmp_path / "reports"),
                "state_dir: " + str(tmp_path / "state"),
                "log_dir: " + str(tmp_path / "logs"),
                "risk:",
                "  kill_switch_file: " + str(tmp_path / "state" / "KILL_SWITCH"),
                "service:",
                "  heartbeat_file: " + str(tmp_path / "state" / "quant_service_heartbeat.json"),
                "  launch_state_file: " + str(tmp_path / "state" / "quant_service_launch.json"),
                "  event_log_file: " + str(tmp_path / "logs" / "quant_events.jsonl"),
                "  log_file: " + str(tmp_path / "logs" / "quant_service.log"),
                "  watchdog_log_file: " + str(tmp_path / "logs" / "quant_watchdog.log"),
                "  notification_log_file: " + str(tmp_path / "logs" / "quant_notifications.jsonl"),
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("QUANT_NOTIFICATION_WEBHOOK_URL", raising=False)
    reports = tmp_path / "reports"
    state = tmp_path / "state"
    reports.mkdir(parents=True)
    state.mkdir(parents=True)
    (reports / "service_stability_latest.json").write_text(
        json.dumps({"ts": old_ts, "observation_age_seconds": 0, "summary": {"failure_event_count": 0}}),
        encoding="utf-8",
    )
    (state / "quant_service_launch.json").write_text(
        json.dumps({"ts": launch_ts, "pid": 12345, "name": "paper_portfolio_service"}),
        encoding="utf-8",
    )
    code = main(
        [
            "--config",
            str(overlay),
            "service",
            "pre-live-check",
            "--no-require-running",
            "--min-observation-hours",
            "0",
        ]
    )
    assert code == 1
    payload = json.loads((reports / "pre_live_check_latest.json").read_text(encoding="utf-8"))
    assert payload["refresh_stability"] is True
    assert payload["refreshed_stability_report"]
    refreshed = json.loads((reports / "service_stability_latest.json").read_text(encoding="utf-8"))
    assert refreshed["ts"] != old_ts


def test_paper_portfolio_turnover_limit_scales_new_exposure(tmp_path):
    cfg = AppConfig(
        data_dir=tmp_path / "data",
        report_dir=tmp_path / "reports",
        state_dir=tmp_path / "state",
        log_dir=tmp_path / "logs",
    )
    cfg.service.event_log_file = tmp_path / "logs" / "quant_events.jsonl"
    cfg.service.notification_log_file = tmp_path / "logs" / "quant_notifications.jsonl"
    store = CandleStore(cfg.data_dir)
    store.write(synthetic_candles("BTC/USDT", "spot", periods=900), "BTC/USDT", "spot", "1H")
    store.write(synthetic_candles("ETH/USDT", "spot", periods=900), "ETH/USDT", "spot", "1H")
    result = run_paper_portfolio_once(
        cfg,
        ["BTC/USDT", "ETH/USDT"],
        lookback_bars=24,
        top_n=1,
        max_turnover_pct=0.10,
        max_candle_age_seconds=0,
        rebalance_cooldown_seconds=0,
    )
    assert result["turnover_used"] <= cfg.risk.live_trading_cap_usdt * 0.10
    with AuditStore(cfg.state_dir).connect() as conn:
        signal_count = conn.execute("SELECT COUNT(*) AS count FROM ads_crypto_strategy_signals").fetchone()["count"]
        target_count = conn.execute("SELECT COUNT(*) AS count FROM ads_crypto_target_positions").fetchone()["count"]
        risk_count = conn.execute("SELECT COUNT(*) AS count FROM ads_crypto_risk_status").fetchone()["count"]
        target = conn.execute(
            """
            SELECT strategy_id, exchange, symbol, target_side, target_position_ratio, risk_limit
            FROM ads_crypto_target_positions
            WHERE target_position_ratio > 0
            LIMIT 1
            """
        ).fetchone()
    assert signal_count >= 1
    assert target_count >= 1
    assert risk_count >= 1
    assert target["strategy_id"] == "cross_sectional_momentum_portfolio"
    assert target["exchange"] == "okx"
    assert target["target_side"] == "long"
    assert json.loads(target["risk_limit"])["max_symbol_exposure_pct"] == cfg.risk.max_symbol_exposure_pct


def test_paper_portfolio_drawdown_breaker_blocks_new_entries(tmp_path):
    cfg = AppConfig(data_dir=tmp_path / "data", report_dir=tmp_path / "reports", state_dir=tmp_path / "state")
    cfg.service.event_log_file = tmp_path / "logs" / "quant_events.jsonl"
    cfg.service.notification_log_file = tmp_path / "logs" / "quant_notifications.jsonl"
    store = CandleStore(cfg.data_dir)
    store.write(synthetic_candles("BTC/USDT", "spot", periods=900), "BTC/USDT", "spot", "1H")
    store.write(synthetic_candles("ETH/USDT", "spot", periods=900), "ETH/USDT", "spot", "1H")
    AuditStore(cfg.state_dir).set_state(
        "paper_portfolio",
        {"cash": 9000, "equity": 9000, "high_watermark": 10000, "positions": []},
    )
    result = run_paper_portfolio_once(
        cfg,
        ["BTC/USDT", "ETH/USDT"],
        lookback_bars=24,
        top_n=1,
        max_portfolio_drawdown_pct=0.01,
        max_candle_age_seconds=0,
        rebalance_cooldown_seconds=0,
    )
    assert result["circuit_breaker"] is True
    assert result["orders"] == []


def test_paper_portfolio_stale_data_guard_blocks_trading(tmp_path):
    cfg = AppConfig(data_dir=tmp_path / "data", report_dir=tmp_path / "reports", state_dir=tmp_path / "state")
    cfg.service.event_log_file = tmp_path / "logs" / "quant_events.jsonl"
    cfg.service.notification_log_file = tmp_path / "logs" / "quant_notifications.jsonl"
    store = CandleStore(cfg.data_dir)
    store.write(synthetic_candles("BTC/USDT", "spot", periods=900), "BTC/USDT", "spot", "1H")
    store.write(synthetic_candles("ETH/USDT", "spot", periods=900), "ETH/USDT", "spot", "1H")
    result = run_paper_portfolio_once(
        cfg,
        ["BTC/USDT", "ETH/USDT"],
        lookback_bars=24,
        top_n=1,
        max_candle_age_seconds=1,
    )
    assert result["stale_data"] is True
    assert result["orders"] == []
    assert cfg.service.event_log_file.exists()


def test_paper_portfolio_rebalance_cooldown_blocks_new_entries(tmp_path):
    cfg = AppConfig(data_dir=tmp_path / "data", report_dir=tmp_path / "reports", state_dir=tmp_path / "state")
    cfg.service.event_log_file = tmp_path / "logs" / "quant_events.jsonl"
    cfg.service.notification_log_file = tmp_path / "logs" / "quant_notifications.jsonl"
    store = CandleStore(cfg.data_dir)
    store.write(synthetic_candles("BTC/USDT", "spot", periods=900), "BTC/USDT", "spot", "1H")
    store.write(synthetic_candles("ETH/USDT", "spot", periods=900), "ETH/USDT", "spot", "1H")
    first = run_paper_portfolio_once(
        cfg,
        ["BTC/USDT", "ETH/USDT"],
        lookback_bars=24,
        top_n=1,
        max_candle_age_seconds=0,
        rebalance_cooldown_seconds=3600,
    )
    second = run_paper_portfolio_once(
        cfg,
        ["BTC/USDT", "ETH/USDT"],
        lookback_bars=24,
        top_n=2,
        max_candle_age_seconds=0,
        rebalance_cooldown_seconds=3600,
    )
    assert first["orders"]
    assert second["cooldown_active"] is True
    assert all(order["side"] != "buy" for order in second["orders"])
    with AuditStore(cfg.state_dir).connect() as conn:
        blocked = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM ads_crypto_risk_status
            WHERE risk_level = 'blocked' AND stop_reason = 'rebalance cooldown active'
            """
        ).fetchone()["count"]
    assert blocked >= 1


def test_cli_service_run_paper_portfolio_records_heartbeat(tmp_path):
    overlay = write_overlay(tmp_path)
    store = CandleStore(tmp_path / "data")
    store.write(synthetic_candles("BTC/USDT", "spot", periods=900), "BTC/USDT", "spot", "1H")
    store.write(synthetic_candles("ETH/USDT", "spot", periods=900), "ETH/USDT", "spot", "1H")
    code = main(
        [
            "--config",
            str(overlay),
            "service",
            "run-paper-portfolio",
            "--symbol",
            "BTC/USDT",
            "--symbol",
            "ETH/USDT",
            "--lookback-bars",
            "24",
            "--top-n",
            "1",
            "--max-iterations",
            "1",
            "--interval-seconds",
            "0",
        ]
    )
    assert code == 0
    assert (tmp_path / "state" / "quant_service_heartbeat.json").exists()
    with AuditStore(tmp_path / "state").connect() as conn:
        row = conn.execute(
            """
            SELECT service_name, mode, strategy_id, ok, order_count, selected_count, payload
            FROM ads_crypto_service_runs
            """
        ).fetchone()
    assert row["service_name"] == "paper_portfolio_service"
    assert row["mode"] == "paper"
    assert row["strategy_id"] == "cross_sectional_momentum_portfolio"
    assert row["ok"] == 1
    assert row["selected_count"] == 1
    assert "paper_portfolio_iteration" in row["payload"]


def test_paper_portfolio_service_can_refresh_candles_before_iteration(tmp_path, monkeypatch):
    from quant_system import service

    cfg = AppConfig(
        data_dir=tmp_path / "data",
        report_dir=tmp_path / "reports",
        state_dir=tmp_path / "state",
        log_dir=tmp_path / "logs",
    )
    cfg.service.event_log_file = tmp_path / "logs" / "quant_events.jsonl"
    cfg.service.log_file = tmp_path / "logs" / "quant_service.log"
    cfg.service.heartbeat_file = tmp_path / "state" / "quant_service_heartbeat.json"
    cfg.service.pid_file = tmp_path / "state" / "quant_service.pid"
    cfg.service.refresh_candles_before_iteration = True
    store = CandleStore(cfg.data_dir)
    store.write(synthetic_candles("BTC/USDT", "spot", periods=900), "BTC/USDT", "spot", "1H")
    store.write(synthetic_candles("ETH/USDT", "spot", periods=900), "ETH/USDT", "spot", "1H")
    calls = []

    def fake_backfill(config, client, symbols=None, instrument_types=None, bar=None, limit=300):
        calls.append({"symbols": list(symbols or []), "instrument_types": list(instrument_types or []), "bar": bar, "limit": limit})
        return [tmp_path / "data" / "refreshed.csv"]

    monkeypatch.setattr(service, "backfill_candles", fake_backfill)
    result = run_paper_portfolio_service(
        cfg,
        ["BTC/USDT", "ETH/USDT"],
        "spot",
        interval_seconds=0,
        lookback_bars=24,
        top_n=1,
        max_candle_age_seconds=0,
        rebalance_cooldown_seconds=0,
        refresh_candles=True,
        refresh_limit=123,
        max_iterations=1,
    )
    assert result["iterations"] == 1
    assert calls == [
        {"symbols": ["BTC/USDT"], "instrument_types": ["spot"], "bar": "1H", "limit": 123},
        {"symbols": ["ETH/USDT"], "instrument_types": ["spot"], "bar": "1H", "limit": 123},
    ]


def test_cli_service_start_paper_portfolio_launches_service_and_watchdog(tmp_path, monkeypatch):
    from quant_system import cli

    overlay = write_overlay(tmp_path)
    launches = []

    def fake_launch(config, name, command, log_file, launch_state_file):
        payload = {
            "name": name,
            "pid": 1234 + len(launches),
            "command": command,
            "log_file": str(log_file),
        }
        launches.append(payload)
        launch_state_file.parent.mkdir(parents=True, exist_ok=True)
        launch_state_file.write_text(json.dumps(payload), encoding="utf-8")
        return payload

    monkeypatch.setattr(cli, "launch_detached_command", fake_launch)
    code = main(
        [
            "--config",
            str(overlay),
            "service",
            "start-paper-portfolio",
            "--symbol",
            "BTC/USDT",
            "--symbol",
            "ETH/USDT",
            "--lookback-bars",
            "24",
            "--top-n",
            "1",
            "--interval-seconds",
            "0",
            "--refresh-candles",
        ]
    )
    assert code == 0
    assert [item["name"] for item in launches] == ["paper_portfolio_service", "watchdog_service"]
    assert "run-paper-portfolio" in launches[0]["command"]
    assert "--refresh-candles" in launches[0]["command"]
    assert "watchdog" in launches[1]["command"]
    assert "--max-heartbeat-age-seconds" in launches[1]["command"]
    assert "300.0" in launches[1]["command"]
    assert "--recover-paper" not in launches[1]["command"]
    assert (tmp_path / "state" / "quant_service_launch.json").exists()
    assert (tmp_path / "state" / "quant_watchdog_launch.json").exists()


def test_cli_service_start_paper_portfolio_can_launch_recovery_watchdog(tmp_path, monkeypatch):
    from quant_system import cli

    overlay = write_overlay(tmp_path)
    launches = []

    def fake_launch(config, name, command, log_file, launch_state_file):
        payload = {"name": name, "pid": 3000 + len(launches), "command": command, "log_file": str(log_file)}
        launches.append(payload)
        launch_state_file.parent.mkdir(parents=True, exist_ok=True)
        launch_state_file.write_text(json.dumps(payload), encoding="utf-8")
        return payload

    monkeypatch.setattr(cli, "launch_detached_command", fake_launch)
    code = main(
        [
            "--config",
            str(overlay),
            "service",
            "start-paper-portfolio",
            "--symbol",
            "BTC/USDT",
            "--symbol",
            "ETH/USDT",
            "--interval-seconds",
            "0",
            "--watchdog-recover-paper",
        ]
    )
    assert code == 0
    assert "--recover-paper" in launches[1]["command"]


def test_recover_paper_service_relaunches_last_safe_paper_command(tmp_path, monkeypatch):
    from quant_system import service

    cfg = AppConfig(data_dir=tmp_path / "data", report_dir=tmp_path / "reports", state_dir=tmp_path / "state", log_dir=tmp_path / "logs")
    cfg.service.pid_file = tmp_path / "state" / "quant_service.pid"
    cfg.service.launch_state_file = tmp_path / "state" / "quant_service_launch.json"
    cfg.service.event_log_file = tmp_path / "logs" / "quant_events.jsonl"
    cfg.service.notification_log_file = tmp_path / "logs" / "quant_notifications.jsonl"
    cfg.risk.kill_switch_file = tmp_path / "state" / "KILL_SWITCH"
    cfg.service.launch_state_file.parent.mkdir(parents=True, exist_ok=True)
    command = ["python", "-m", "quant_system.cli", "service", "run-paper-portfolio", "--symbol", "BTC/USDT"]
    cfg.service.launch_state_file.write_text(
        json.dumps({"name": "paper_portfolio_service", "pid": 999, "command": command}),
        encoding="utf-8",
    )
    monkeypatch.setattr(service, "process_alive", lambda pid: False)
    launches = []

    def fake_launcher(config, name, launch_command, log_file, launch_state_file):
        payload = {"name": name, "pid": 2222, "command": launch_command, "log_file": str(log_file)}
        launches.append(payload)
        return payload

    result = recover_paper_service(cfg, launcher=fake_launcher)
    assert result["status"] == "recovered"
    assert launches[0]["command"] == command
    assert (tmp_path / "logs" / "quant_notifications.jsonl").exists()


def test_recover_paper_service_refuses_live_or_kill_switch(tmp_path, monkeypatch):
    from quant_system import service

    cfg = AppConfig(data_dir=tmp_path / "data", report_dir=tmp_path / "reports", state_dir=tmp_path / "state", log_dir=tmp_path / "logs")
    cfg.service.pid_file = tmp_path / "state" / "quant_service.pid"
    cfg.service.launch_state_file = tmp_path / "state" / "quant_service_launch.json"
    cfg.service.event_log_file = tmp_path / "logs" / "quant_events.jsonl"
    cfg.service.notification_log_file = tmp_path / "logs" / "quant_notifications.jsonl"
    cfg.risk.kill_switch_file = tmp_path / "state" / "KILL_SWITCH"
    cfg.service.launch_state_file.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(service, "process_alive", lambda pid: False)
    cfg.service.launch_state_file.write_text(
        json.dumps({"name": "live_portfolio_service", "command": ["python", "-m", "quant_system.cli", "service", "run-live-portfolio"]}),
        encoding="utf-8",
    )
    result = recover_paper_service(cfg, launcher=lambda *args: pytest.fail("should not launch"))
    assert result["status"] == "blocked"
    assert "not a paper portfolio service" in result["reason"]
    Path(cfg.risk.kill_switch_file).parent.mkdir(parents=True, exist_ok=True)
    Path(cfg.risk.kill_switch_file).write_text("stop", encoding="utf-8")
    result = recover_paper_service(cfg, launcher=lambda *args: pytest.fail("should not launch"))
    assert result["status"] == "blocked"
    assert result["reason"] == "kill switch is active"


def test_recover_paper_service_returns_already_running(tmp_path, monkeypatch):
    from quant_system import service

    cfg = AppConfig(data_dir=tmp_path / "data", report_dir=tmp_path / "reports", state_dir=tmp_path / "state", log_dir=tmp_path / "logs")
    cfg.service.pid_file = tmp_path / "state" / "quant_service.pid"
    cfg.service.pid_file.parent.mkdir(parents=True, exist_ok=True)
    cfg.service.pid_file.write_text("1234", encoding="utf-8")
    monkeypatch.setattr(service, "process_alive", lambda pid: True)
    result = recover_paper_service(cfg, launcher=lambda *args: pytest.fail("should not launch"))
    assert result["status"] == "already_running"


def test_cli_service_start_live_portfolio_launches_gated_service(tmp_path, monkeypatch):
    from quant_system import cli

    overlay = tmp_path / "live.yaml"
    overlay.write_text(
        "\n".join(
            [
                "mode: live",
                "data_dir: " + str(tmp_path / "data"),
                "report_dir: " + str(tmp_path / "reports"),
                "state_dir: " + str(tmp_path / "state"),
                "log_dir: " + str(tmp_path / "logs"),
                "okx:",
                "  demo_trading: false",
                "  api_key_env: TEST_OKX_KEY",
                "  api_secret_env: TEST_OKX_SECRET",
                "  passphrase_env: TEST_OKX_PASSPHRASE",
                "execution:",
                "  live_enabled: true",
                "service:",
                "  pid_file: " + str(tmp_path / "state" / "quant_service.pid"),
                "  watchdog_pid_file: " + str(tmp_path / "state" / "quant_watchdog.pid"),
                "  launch_state_file: " + str(tmp_path / "state" / "quant_service_launch.json"),
                "  watchdog_launch_state_file: " + str(tmp_path / "state" / "quant_watchdog_launch.json"),
                "  log_file: " + str(tmp_path / "logs" / "quant_service.log"),
                "  watchdog_log_file: " + str(tmp_path / "logs" / "quant_watchdog.log"),
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TEST_OKX_KEY", "key")
    monkeypatch.setenv("TEST_OKX_SECRET", "secret")
    monkeypatch.setenv("TEST_OKX_PASSPHRASE", "pass")
    launches = []

    def fake_launch(config, name, command, log_file, launch_state_file):
        payload = {"name": name, "pid": 2000 + len(launches), "command": command, "log_file": str(log_file)}
        launches.append(payload)
        launch_state_file.parent.mkdir(parents=True, exist_ok=True)
        launch_state_file.write_text(json.dumps(payload), encoding="utf-8")
        return payload

    monkeypatch.setattr(cli, "launch_detached_command", fake_launch)
    code = main(
        [
            "--config",
            str(overlay),
            "service",
            "start-live-portfolio",
            "--confirm-live",
            "--symbol",
            "BTC/USDT",
            "--symbol",
            "ETH/USDT",
            "--no-refresh-candles",
        ]
    )
    assert code == 0
    assert [item["name"] for item in launches] == ["live_portfolio_service", "watchdog_service"]
    assert "run-live-portfolio" in launches[0]["command"]
    assert "--confirm-live" in launches[0]["command"]
    assert "--max-heartbeat-age-seconds" in launches[1]["command"]
    assert "5520.0" in launches[1]["command"]


def test_cli_service_health_reports_heartbeat(tmp_path):
    overlay = write_overlay(tmp_path)
    store = CandleStore(tmp_path / "data")
    store.write(synthetic_candles("BTC/USDT", "spot", periods=900), "BTC/USDT", "spot", "1H")
    store.write(synthetic_candles("ETH/USDT", "spot", periods=900), "ETH/USDT", "spot", "1H")
    assert (
        main(
            [
                "--config",
                str(overlay),
                "service",
                "run-paper-portfolio",
                "--symbol",
                "BTC/USDT",
                "--symbol",
                "ETH/USDT",
                "--lookback-bars",
                "24",
                "--top-n",
                "1",
                "--max-iterations",
                "1",
                "--interval-seconds",
                "0",
            ]
        )
        == 0
    )
    assert main(["--config", str(overlay), "service", "health", "--max-heartbeat-age-seconds", "3600"]) == 0
    assert main(["--config", str(overlay), "service", "report", "--max-heartbeat-age-seconds", "3600"]) == 0
    assert (tmp_path / "reports" / "service_observation_latest.json").exists()
    assert main(["--config", str(overlay), "service", "stability", "--max-heartbeat-age-seconds", "3600"]) == 0
    stability = tmp_path / "reports" / "service_stability_latest.json"
    assert stability.exists()
    payload = json.loads(stability.read_text())
    assert payload["summary"]["paper_run_count"] >= 1
    assert "failure_event_count" in payload["summary"]


def test_cli_service_watchdog_activates_kill_switch_on_missing_heartbeat(tmp_path):
    overlay = write_overlay(tmp_path)
    code = main(
        [
            "--config",
            str(overlay),
            "service",
            "watchdog",
            "--max-iterations",
            "1",
            "--interval-seconds",
            "0",
            "--max-heartbeat-age-seconds",
            "1",
        ]
    )
    assert code == 0
    assert (tmp_path / "state" / "KILL_SWITCH").exists()
    assert (tmp_path / "state" / "quant_watchdog_heartbeat.json").exists()
    assert (tmp_path / "logs" / "quant_watchdog.log").exists()


def test_watchdog_recovers_missing_paper_service_without_kill_switch(tmp_path, monkeypatch):
    from quant_system import service

    cfg = AppConfig(data_dir=tmp_path / "data", report_dir=tmp_path / "reports", state_dir=tmp_path / "state", log_dir=tmp_path / "logs")
    cfg.service.pid_file = tmp_path / "state" / "quant_service.pid"
    cfg.service.watchdog_pid_file = tmp_path / "state" / "quant_watchdog.pid"
    cfg.service.launch_state_file = tmp_path / "state" / "quant_service_launch.json"
    cfg.service.watchdog_heartbeat_file = tmp_path / "state" / "quant_watchdog_heartbeat.json"
    cfg.service.event_log_file = tmp_path / "logs" / "quant_events.jsonl"
    cfg.service.notification_log_file = tmp_path / "logs" / "quant_notifications.jsonl"
    cfg.service.watchdog_log_file = tmp_path / "logs" / "quant_watchdog.log"
    cfg.risk.kill_switch_file = tmp_path / "state" / "KILL_SWITCH"
    cfg.service.launch_state_file.parent.mkdir(parents=True, exist_ok=True)
    command = ["python", "-m", "quant_system.cli", "service", "run-paper-portfolio", "--symbol", "BTC/USDT"]
    cfg.service.launch_state_file.write_text(
        json.dumps({"name": "paper_portfolio_service", "pid": 99, "command": command}),
        encoding="utf-8",
    )
    monkeypatch.setattr(service, "process_alive", lambda pid: False)

    def fake_launcher(config, name, launch_command, log_file, launch_state_file):
        return {"name": name, "pid": 4321, "command": launch_command, "log_file": str(log_file)}

    result = service.run_watchdog_service(
        cfg,
        interval_seconds=0,
        max_heartbeat_age_seconds=1,
        max_iterations=1,
        recover_paper=True,
        recovery_launcher=fake_launcher,
    )
    assert result["stop_reason"] == "paper_recovered"
    assert result["actions"]["paper_recovery"]["status"] == "recovered"
    assert not Path(cfg.risk.kill_switch_file).exists()


def test_cli_service_acceptance_writes_report(tmp_path):
    overlay = write_overlay(tmp_path)
    store = CandleStore(tmp_path / "data")
    store.write(synthetic_candles("BTC/USDT", "spot", periods=900), "BTC/USDT", "spot", "1H")
    store.write(synthetic_candles("ETH/USDT", "spot", periods=900), "ETH/USDT", "spot", "1H")
    code = main(
        [
            "--config",
            str(overlay),
            "service",
            "acceptance",
            "--symbol",
            "BTC/USDT",
            "--symbol",
            "ETH/USDT",
            "--iterations",
            "2",
            "--lookback-bars",
            "24",
            "--top-n",
            "1",
            "--max-heartbeat-age-seconds",
            "3600",
        ]
    )
    assert code == 0
    latest = tmp_path / "reports" / "unattended_acceptance_latest.json"
    assert latest.exists()
    payload = json.loads(latest.read_text())
    assert payload["status"] == "passed"
    assert {check["name"] for check in payload["checks"]} == {
        "kill_switch_precheck",
        "paper_service_iterations",
        "service_health_after_run",
        "watchdog_healthy_path",
        "live_gate_blocks_unconfirmed_or_missing_credentials",
    }


def test_cli_service_acceptance_fails_when_kill_switch_active(tmp_path):
    overlay = write_overlay(tmp_path)
    kill = tmp_path / "state" / "KILL_SWITCH"
    kill.parent.mkdir(parents=True, exist_ok=True)
    kill.write_text("{}", encoding="utf-8")
    code = main(
        [
            "--config",
            str(overlay),
            "service",
            "acceptance",
            "--symbol",
            "BTC/USDT",
            "--symbol",
            "ETH/USDT",
            "--lookback-bars",
            "24",
        ]
    )
    assert code == 1
    payload = json.loads((tmp_path / "reports" / "unattended_acceptance_latest.json").read_text())
    assert payload["status"] == "failed"
    assert payload["checks"][0]["name"] == "kill_switch_precheck"


def test_cli_service_live_gate_drill_writes_report(tmp_path):
    overlay = write_overlay(tmp_path)
    code = main(["--config", str(overlay), "service", "live-gate-drill"])
    assert code == 0
    latest = tmp_path / "reports" / "live_gate_drill_latest.json"
    assert latest.exists()
    payload = json.loads(latest.read_text())
    assert payload["status"] == "passed"
    assert payload["live_ready"] is False
    assert not (tmp_path / "logs" / "quant_events.jsonl").exists()
    assert (tmp_path / "logs" / "live_gate_drill" / "quant_events.jsonl").exists()
    assert {check["name"] for check in payload["checks"]} == {
        "config_live_enabled_false_blocks",
        "missing_confirm_live_blocks",
        "missing_credentials_blocks",
        "all_live_gates_pass_when_enabled_confirmed_and_credentialed",
        "kill_switch_blocks_new_orders",
        "kill_switch_allows_reduce_only_orders",
    }
