import json

import pandas as pd
import pytest

from quant_system.config import AppConfig, OkxCredentials, load_local_env, okx_inst_id, symbol_from_okx_inst_id
from quant_system.data import discover_usdt_universe
from quant_system.diagnostics import CheckResult, readiness_summary
from quant_system.models import InstrumentType, OrderIntent, Side
from quant_system.knowledge import load_strategy_knowledge_base, strategy_knowledge_summary, sync_strategy_registry
from quant_system.storage import AuditStore
from quant_system.notifications import notify, tail_notifications
from quant_system.research import (
    aggregate_strategy_scores,
    cost_sensitivity_summary,
    overfitting_diagnostics,
    parameter_stability_summary,
    walk_forward_summary,
)
from quant_system.okx import OkxRestClient, OkxApiError, OkxWebSocketClient, okx_number, sign_message
from quant_system.reports import classify_market_regimes, market_regime_summary
from quant_system.sizing import find_instrument, round_limit_price, round_order_quantity


def test_default_config_validates_core_defaults():
    cfg = AppConfig()
    assert cfg.mode == "paper"
    assert cfg.okx.demo_trading is True
    assert cfg.execution.live_enabled is False
    assert "BTC/USDT" in cfg.market.symbols
    assert cfg.risk.max_risk_per_trade_pct == 0.005
    assert cfg.risk.live_trading_cap_usdt == 50.0
    assert cfg.risk.max_portfolio_drawdown_pct == 0.05
    assert cfg.risk.max_turnover_per_rebalance_pct == 0.50
    assert cfg.market.trade_allowlist == []
    assert cfg.market.trade_blocklist == []
    assert cfg.service.max_candle_age_seconds == 7200.0
    assert cfg.service.rebalance_cooldown_seconds == 3600.0
    assert cfg.service.watchdog_interval_seconds == 60.0
    assert cfg.service.watchdog_max_heartbeat_age_seconds == 300.0
    assert cfg.service.okx_cancel_all_after_seconds == 0
    assert cfg.service.refresh_candles_before_iteration is True
    assert cfg.service.refresh_candles_limit == 300
    assert cfg.service.launch_state_file.name == "quant_service_launch.json"
    assert cfg.service.watchdog_launch_state_file.name == "quant_watchdog_launch.json"
    assert cfg.service.notification_log_file.name == "quant_notifications.jsonl"
    assert cfg.service.notification_webhook_url_env == "QUANT_NOTIFICATION_WEBHOOK_URL"
    assert cfg.service.notify_on_orders is True


def test_order_client_id_is_okx_safe():
    intent = OrderIntent("BTC/USDT", InstrumentType.SPOT, Side.BUY, 1.0)
    assert intent.client_order_id.startswith("qa")
    assert intent.client_order_id.isalnum()
    assert len(intent.client_order_id) <= 32




def test_strategy_knowledge_base_has_required_coverage():
    cfg = AppConfig()
    summary = strategy_knowledge_summary(cfg)
    assert summary["valid"] is True
    assert summary["total_strategies"] >= 10
    assert "crypto_cross_sectional_momentum" in summary["implemented_strategy_ids"]
    assert "btc_eth_cointegration_pairs" in summary["implemented_strategy_ids"]
    assert "btc_eth_cointegration_pairs" in summary["backtested_strategy_ids"]
    assert "btc_eth_cointegration_pairs" not in summary["missing_backtest"]
    assert summary["pipeline_summary"]["strategy_pipeline_status"]["strategy_validated"] == 2
    assert summary["pipeline_summary"]["strategy_pipeline_status"]["strategy_validated_weak"] == 1
    assert summary["pipeline_summary"]["factor_pipeline_status"]["factor_pipeline_ready"] == 7
    assert "altcoin_btc_arbitrage_factor_reversion" in summary["pipeline_summary"]["factor_pipeline_ready"]
    assert all(not issues for issues in summary["validation"].values())


def test_strategy_knowledge_base_entries_include_required_reproduction_fields():
    payload = load_strategy_knowledge_base()
    for item in payload["strategies"]:
        assert item["logic"]
        assert item["data_requirements"]
        assert item["signal_construction"]
        assert item["entry_rules"]
        assert item["exit_rules"]
        assert item["position_sizing"]
        assert item["risk_management"]
        assert item["failure_conditions"]
        assert item["reproducibility_difficulty"]
        assert item["research_pipeline_stage"]
        assert item["factor_pipeline_status"]
        assert item["strategy_pipeline_status"]
        assert item["promotion_status"]
        assert item["pipeline_notes"]


def test_strategy_knowledge_syncs_registry(tmp_path):
    cfg = AppConfig(state_dir=tmp_path / "state")
    result = sync_strategy_registry(cfg)
    audit = AuditStore(cfg.state_dir)

    assert result["synced_count"] >= 10
    with audit.connect() as conn:
        count = conn.execute("SELECT COUNT(*) AS count FROM strategy_registry").fetchone()["count"]
        primary = conn.execute(
            "SELECT strategy_name, status FROM strategy_registry WHERE strategy_id = ?",
            ("crypto_cross_sectional_momentum",),
        ).fetchone()
    assert count == result["synced_count"]
    assert primary["strategy_name"] == "Cross-sectional crypto momentum"
    assert primary["status"] == "primary_paper_candidate"


def test_parameter_stability_summary_flags_single_point_fragility():
    rows = [
        {
            "status": "ok",
            "lookback_bars": 24,
            "hold_bars": 24,
            "top_n": 1,
            "total_return": 0.10,
            "sharpe": 1.2,
            "max_drawdown": -0.05,
            "trade_count": 10,
        },
        {
            "status": "ok",
            "lookback_bars": 48,
            "hold_bars": 24,
            "top_n": 1,
            "total_return": -0.02,
            "sharpe": -0.2,
            "max_drawdown": -0.08,
            "trade_count": 10,
        },
    ]
    summary = parameter_stability_summary(rows, ["lookback_bars", "hold_bars", "top_n"], min_trades=1)
    assert summary["candidate_count"] == 2
    assert summary["status"] == "fragile"
    assert summary["parameter_ranges"]["lookback_bars"]["tested_values"] == [24, 48]


def test_walk_forward_summary_tracks_parameter_drift():
    folds = [
        {
            "status": "ok",
            "selected_params": {"lookback_bars": 24, "top_n": 1},
            "test_metrics": {"total_return": 0.10, "sharpe": 1.0, "max_drawdown": -0.02, "trade_count": 3},
        },
        {
            "status": "ok",
            "selected_params": {"lookback_bars": 48, "top_n": 1},
            "test_metrics": {"total_return": -0.01, "sharpe": -0.2, "max_drawdown": -0.04, "trade_count": 2},
        },
    ]
    summary = walk_forward_summary(folds, ["lookback_bars", "top_n"])
    assert summary["schema"] == "rolling_walk_forward_v1"
    assert summary["parameter_drift"]["lookback_bars"]["transition_count"] == 1
    assert summary["parameter_drift"]["top_n"]["transition_count"] == 0
    assert summary["total_oos_activity"] == 5


def test_cost_sensitivity_summary_marks_fragile_costs_research_only():
    rows = [
        {"status": "ok", "total_return": 0.05, "sharpe": 1.0, "max_drawdown": -0.02},
        {"status": "ok", "total_return": -0.01, "sharpe": -0.1, "max_drawdown": -0.04},
    ]
    summary = cost_sensitivity_summary(rows)
    assert summary["schema"] == "cost_sensitivity_v1"
    assert summary["recommendation"] == "research_only"
    assert summary["positive_scenario_rate"] == 0.5


def test_market_regime_classifier_emits_standard_dimensions():
    ts = pd.date_range("2026-01-01", periods=120, freq="h", tz="UTC")
    candles = pd.DataFrame(
        {
            "ts": ts,
            "close": [100 + idx * 0.5 for idx in range(120)],
            "volume": [100.0] * 120,
        }
    )
    regimes = classify_market_regimes(candles, lookback=24)
    summary = market_regime_summary(candles, lookback=24)
    assert {"primary_regime", "trend_regime", "volatility_regime", "liquidity_regime", "event_regime"}.issubset(
        regimes.columns
    )
    assert summary["schema"] == "market_regime_v1"
    assert summary["row_count"] == 120


def test_overfitting_diagnostics_reports_multiple_testing_haircut():
    rows = [
        {
            "status": "ok",
            "lookback_bars": idx,
            "hold_bars": 24,
            "top_n": 1,
            "total_return": 0.01 * idx,
            "sharpe": 0.1 * idx,
            "max_drawdown": -0.02,
            "trade_count": 5,
        }
        for idx in range(1, 6)
    ]
    diagnostics = overfitting_diagnostics(rows, ["lookback_bars", "hold_bars", "top_n"], min_trades=1)
    assert diagnostics["schema"] == "overfitting_diagnostics_v1"
    assert diagnostics["tried_configuration_count"] == 5
    assert diagnostics["deflated_sharpe_proxy"] < diagnostics["best_sharpe"]

def test_demo_mode_uses_demo_specific_credentials(monkeypatch):
    monkeypatch.setenv("OKX_API_KEY", "prod-key")
    monkeypatch.setenv("OKX_API_SECRET", "prod-secret")
    monkeypatch.setenv("OKX_PASSPHRASE", "prod-pass")
    monkeypatch.setenv("OKX_DEMO_API_KEY", "demo-key")
    monkeypatch.setenv("OKX_DEMO_API_SECRET", "demo-secret")
    monkeypatch.setenv("OKX_DEMO_PASSPHRASE", "demo-pass")
    cfg = AppConfig()
    creds = cfg.okx.credentials()
    assert creds.environment == "demo"
    assert creds.api_key == "demo-key"


def test_production_mode_uses_production_credentials(monkeypatch):
    monkeypatch.setenv("OKX_API_KEY", "prod-key")
    monkeypatch.setenv("OKX_API_SECRET", "prod-secret")
    monkeypatch.setenv("OKX_PASSPHRASE", "prod-pass")
    cfg = AppConfig()
    cfg.okx.demo_trading = False
    creds = cfg.okx.credentials()
    assert creds.environment == "production"
    assert creds.api_key == "prod-key"


def test_load_local_env_does_not_overwrite_existing(monkeypatch, tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("OKX_API_KEY=from-file\nCUSTOM_VALUE=loaded\n", encoding="utf-8")
    monkeypatch.setenv("OKX_API_KEY", "already-set")
    load_local_env(env_path)
    import os

    assert os.environ["OKX_API_KEY"] == "already-set"
    assert os.environ["CUSTOM_VALUE"] == "loaded"


def test_notify_writes_local_log_without_webhook(monkeypatch, tmp_path):
    cfg = AppConfig(log_dir=tmp_path / "logs")
    cfg.service.notification_log_file = tmp_path / "logs" / "quant_notifications.jsonl"
    monkeypatch.delenv(cfg.service.notification_webhook_url_env, raising=False)
    item = notify(cfg, "unit_event", "info", {"value": 1})
    assert item["webhook_sent"] is False
    rows = tail_notifications(cfg)
    assert rows[-1]["event"] == "unit_event"


def test_notify_posts_to_webhook_when_configured(monkeypatch, tmp_path):
    from quant_system import notifications

    cfg = AppConfig(log_dir=tmp_path / "logs")
    cfg.service.notification_log_file = tmp_path / "logs" / "quant_notifications.jsonl"
    monkeypatch.setenv(cfg.service.notification_webhook_url_env, "https://example.test/webhook")
    calls = []

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_urlopen(request, timeout):
        calls.append({"url": request.full_url, "timeout": timeout, "body": request.data})
        return FakeResponse()

    monkeypatch.setattr(notifications, "urlopen", fake_urlopen)
    item = notify(cfg, "unit_webhook", "critical", {"value": 2})
    assert item["webhook_sent"] is True
    assert calls[0]["url"] == "https://example.test/webhook"


def test_okx_inst_id_roundtrip():
    assert okx_inst_id("BTC/USDT", "spot") == "BTC-USDT"
    assert okx_inst_id("BTC/USDT", "swap") == "BTC-USDT-SWAP"
    assert symbol_from_okx_inst_id("ETH-USDT-SWAP") == ("ETH/USDT", "swap")


def test_okx_signature_is_deterministic():
    signature = sign_message("secret", "2026-05-26T00:00:00.000Z", "GET", "/api/v5/account/balance", "")
    assert signature == sign_message("secret", "2026-05-26T00:00:00.000Z", "GET", "/api/v5/account/balance", "")
    assert signature


def test_okx_number_avoids_scientific_notation():
    assert okx_number(0.0000651) == "0.000065"
    assert okx_number("0.00006510") == "0.00006510"


def test_discover_usdt_universe_filters_and_sorts_by_quote_volume():
    class FakeClient:
        def get_instruments(self, instrument_type):
            assert instrument_type == "spot"
            return [
                {"instId": "ETH-USDT", "state": "live"},
                {"instId": "BTC-USDT", "state": "live"},
                {"instId": "USDC-USDT", "state": "live"},
                {"instId": "OLD-USDT", "state": "suspend"},
                {"instId": "BTC-USDT-SWAP", "state": "live"},
            ]

        def get_tickers(self, instrument_type):
            assert instrument_type == "spot"
            return [
                {"instId": "ETH-USDT", "volCcy24h": "10", "last": "3000"},
                {"instId": "BTC-USDT", "volCcy24h": "20", "last": "100000"},
                {"instId": "USDC-USDT", "volCcy24h": "999", "last": "1"},
            ]

    rows = discover_usdt_universe(AppConfig(), FakeClient(), top_n=2)
    assert [row["symbol"] for row in rows] == ["BTC/USDT", "ETH/USDT"]


def test_demo_header_added_without_auth():
    client = OkxRestClient(AppConfig().okx)
    headers = client._headers("GET", "/api/v5/market/candles", "", auth=False)
    assert headers["x-simulated-trading"] == "1"
    assert headers["User-Agent"].startswith("curl/")
    assert "OK-ACCESS-KEY" not in headers


def test_demo_websocket_urls_use_paper_host():
    ws = OkxWebSocketClient(AppConfig().okx)
    assert ws.public_url == "wss://wspap.okx.com:8443/ws/v5/public"
    assert ws.private_url == "wss://wspap.okx.com:8443/ws/v5/private"


def test_auth_endpoint_requires_credentials():
    client = OkxRestClient(AppConfig().okx, credentials=OkxCredentials())
    with pytest.raises(OkxApiError):
        client._headers("GET", "/api/v5/account/balance", "", auth=True)


def test_cancel_all_after_uses_okx_dead_mans_switch_endpoint():
    client = OkxRestClient(AppConfig().okx, credentials=OkxCredentials(api_key="key", api_secret="secret", passphrase="pass"))
    calls = []

    def fake_request(method, path, params=None, payload=None, auth=False):
        calls.append({"method": method, "path": path, "params": params, "payload": payload, "auth": auth})
        return {"code": "0", "data": [{"result": True}]}

    client.request = fake_request
    response = client.cancel_all_after(60)
    assert response["code"] == "0"
    assert calls == [
        {
            "method": "POST",
            "path": "/api/v5/trade/cancel-all-after",
            "params": None,
            "payload": {"timeOut": "60"},
            "auth": True,
        }
    ]


def test_order_sizing_respects_lot_min_and_tick():
    instrument = {"instId": "BTC-USDT", "minSz": "0.00001", "lotSz": "0.00001", "tickSz": "0.1"}
    assert round_order_quantity(0.000001, instrument) == "0.00001"
    assert round_order_quantity(0.000014, instrument) == "0.00002"
    assert round_limit_price(123.456, instrument) == "123.4"
    assert find_instrument([instrument], "BTC-USDT") == instrument


def test_readiness_summary_requires_public_and_demo_auth():
    payload = readiness_summary(
        [
            CheckResult("public_time", True, {}),
            CheckResult("demo_private_auth", False, {"error": "missing"}),
            CheckResult("production_private_auth_readonly", True, {}),
        ]
    )
    assert payload["ready_for_demo_trading"] is False
    assert payload["public_api_ok"] is True
    assert payload["demo_private_auth_ok"] is False
    assert payload["blockers"] == ["Demo Trading API credentials are missing or invalid"]


def test_aggregate_strategy_scores_filters_low_trade_count():
    rows = [
        {"strategy": "a", "status": "ok", "trade_count": 3, "sharpe": 1.0, "total_return": 0.1, "max_drawdown": -0.1},
        {"strategy": "b", "status": "ok", "trade_count": 1, "sharpe": 9.0, "total_return": 0.9, "max_drawdown": -0.9},
    ]
    scores = aggregate_strategy_scores(rows)
    assert [item["strategy"] for item in scores] == ["a"]
