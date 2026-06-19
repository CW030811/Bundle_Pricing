from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from .alpha import run_alpha_ensemble, run_alpha_ensemble_report
from .backtest import Backtester
from .config import load_config, okx_inst_id
from .data import (
    backfill_basis,
    backfill_candles,
    backfill_exchange_info,
    backfill_funding_rates,
    backfill_history_candles,
    backfill_liquidations,
    backfill_long_short_ratio,
    backfill_open_interest,
    backfill_orderbook,
    backfill_recent_trades,
    discover_usdt_universe,
    filter_date_range,
    load_candles,
    synthetic_candles,
    write_universe,
)
from .data_quality import run_ohlcv_quality_check, run_ohlcv_quality_report
from .diagnostics import diagnose_okx, readiness_summary, results_to_payload
from .factors import build_factor, run_factor_evaluation, run_factor_evaluation_report
from .knowledge import missing_strategy_cards, strategy_knowledge_report, strategy_knowledge_summary, sync_strategy_registry
from .live import (
    run_okx_demo_loop,
    run_okx_demo_once,
    run_okx_live_portfolio_once,
    run_paper_once,
    run_paper_portfolio_once,
    validate_live,
)
from .models import InstrumentType, dataclass_to_dict
from .okx import OkxRestClient, OkxWebSocketClient
from .reports import write_report
from .review import review_queue, review_queue_report
from .scaffold import scaffold_strategy_research
from .research import (
    DEFAULT_CANDIDATES,
    run_adaptive_trend,
    run_adaptive_trend_cost_sensitivity,
    run_adaptive_trend_cost_sensitivity_report,
    run_adaptive_trend_grid,
    run_adaptive_trend_grid_report,
    run_adaptive_trend_report,
    run_adaptive_trend_walk_forward,
    run_adaptive_trend_walk_forward_report,
    run_btc_eth_cointegration_pairs,
    run_btc_eth_cointegration_pairs_report,
    run_cross_sectional_momentum,
    run_cross_sectional_momentum_cost_sensitivity,
    run_cross_sectional_momentum_cost_sensitivity_report,
    run_cross_sectional_momentum_grid,
    run_cross_sectional_momentum_grid_report,
    run_cross_sectional_momentum_report,
    run_cross_sectional_momentum_walk_forward,
    run_cross_sectional_momentum_walk_forward_report,
    run_funding_carry,
    run_funding_carry_cost_sensitivity,
    run_funding_carry_cost_sensitivity_report,
    run_funding_carry_grid,
    run_funding_carry_grid_report,
    run_funding_carry_report,
    run_funding_carry_walk_forward,
    run_funding_carry_walk_forward_report,
    run_multi_timeframe_strategy_sweep,
    run_multi_timeframe_strategy_sweep_report,
    run_strategy_sweep,
    run_strategy_sweep_report,
    sanitize_for_json,
    strategy_promotion_scorecard,
    strategy_promotion_scorecard_report,
    strategy_shortlist,
    strategy_shortlist_report,
)
from .service import (
    activate_kill_switch,
    recover_paper_service,
    prepare_service_launch,
    request_service_stop,
    run_demo_service,
    run_live_gate_drill,
    run_live_portfolio_service,
    run_notification_drill,
    run_paper_portfolio_service,
    run_pre_live_check,
    run_unattended_acceptance,
    run_watchdog_service,
    launch_detached_command,
    service_health,
    service_status,
    watchdog_status,
    write_runtime_snapshot_report,
    write_service_observation_report,
    write_service_stability_report,
)
from .sizing import find_instrument, round_limit_price, round_order_quantity
from .storage import AuditStore


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", default=None, help="Path to YAML config overlay")


def cli_command_prefix(config_path: str | None) -> list[str]:
    command = [sys.executable, "-m", "quant_system.cli"]
    if config_path:
        command.extend(["--config", str(config_path)])
    return command


def add_optional(command: list[str], flag: str, value: object | None) -> None:
    if value is not None:
        command.extend([flag, str(value)])


def add_repeated(command: list[str], flag: str, values: Sequence[str] | None) -> None:
    for value in values or []:
        command.extend([flag, value])


def paper_portfolio_service_command(args: argparse.Namespace) -> list[str]:
    command = cli_command_prefix(args.config)
    command.extend(["service", "run-paper-portfolio", "--instrument-type", args.instrument_type])
    add_repeated(command, "--symbol", args.symbol)
    add_optional(command, "--interval-seconds", args.interval_seconds)
    add_optional(command, "--max-iterations", args.max_iterations)
    add_optional(command, "--lookback-bars", args.lookback_bars)
    add_optional(command, "--top-n", args.top_n)
    add_optional(command, "--min-momentum", args.min_momentum)
    add_repeated(command, "--allow-symbol", args.allow_symbol)
    add_repeated(command, "--block-symbol", args.block_symbol)
    add_optional(command, "--max-turnover-pct", args.max_turnover_pct)
    add_optional(command, "--max-portfolio-drawdown-pct", args.max_portfolio_drawdown_pct)
    add_optional(command, "--max-candle-age-seconds", args.max_candle_age_seconds)
    add_optional(command, "--rebalance-cooldown-seconds", args.rebalance_cooldown_seconds)
    if args.refresh_candles is True:
        command.append("--refresh-candles")
    if args.refresh_candles is False:
        command.append("--no-refresh-candles")
    add_optional(command, "--refresh-candles-limit", args.refresh_candles_limit)
    return command


def live_portfolio_service_command(args: argparse.Namespace) -> list[str]:
    command = cli_command_prefix(args.config)
    command.extend(["service", "run-live-portfolio", "--instrument-type", args.instrument_type])
    if args.confirm_live:
        command.append("--confirm-live")
    add_repeated(command, "--symbol", args.symbol)
    add_optional(command, "--interval-seconds", args.interval_seconds)
    add_optional(command, "--max-iterations", args.max_iterations)
    add_optional(command, "--lookback-bars", args.lookback_bars)
    add_optional(command, "--top-n", args.top_n)
    add_optional(command, "--min-momentum", args.min_momentum)
    add_repeated(command, "--allow-symbol", args.allow_symbol)
    add_repeated(command, "--block-symbol", args.block_symbol)
    add_optional(command, "--max-turnover-pct", args.max_turnover_pct)
    add_optional(command, "--max-candle-age-seconds", args.max_candle_age_seconds)
    add_optional(command, "--rebalance-cooldown-seconds", args.rebalance_cooldown_seconds)
    add_optional(command, "--order-type", args.order_type)
    if args.refresh_candles is True:
        command.append("--refresh-candles")
    if args.refresh_candles is False:
        command.append("--no-refresh-candles")
    add_optional(command, "--refresh-candles-limit", args.refresh_candles_limit)
    return command


def watchdog_service_command(
    config_path: str | None,
    interval_seconds: float | None,
    max_heartbeat_age_seconds: float | None,
    require_running: bool = True,
    trigger_kill_switch: bool = True,
    stop_service: bool = True,
    recover_paper: bool = False,
) -> list[str]:
    command = cli_command_prefix(config_path)
    command.extend(["service", "watchdog"])
    add_optional(command, "--interval-seconds", interval_seconds)
    add_optional(command, "--max-heartbeat-age-seconds", max_heartbeat_age_seconds)
    if not require_running:
        command.append("--no-require-running")
    if not trigger_kill_switch:
        command.append("--no-kill-switch")
    if not stop_service:
        command.append("--no-stop-service")
    if recover_paper:
        command.append("--recover-paper")
    return command


def effective_watchdog_max_heartbeat_age(interval_seconds: float, configured: float | None) -> float:
    if configured is not None:
        return configured
    return max(300.0, interval_seconds * 1.5 + 120.0)


def require_strategy_cards(strategy_names: list[str], allow_unregistered: bool = False) -> None:
    if allow_unregistered:
        return
    missing = missing_strategy_cards(strategy_names)
    if missing:
        raise SystemExit(
            "missing Strategy Card for strategy name(s): "
            + ", ".join(missing)
            + "; add them to knowledge/bitcoin_strategy_knowledge_base.yaml or pass --allow-unregistered-strategy"
        )


def require_clean_ohlcv_data(
    config,
    *,
    symbols: list[str],
    instrument_types: list[str],
    interval: str | None = None,
    allow_quality_issues: bool = False,
) -> dict[str, object]:
    payload = run_ohlcv_quality_check(
        config,
        symbols=symbols,
        instrument_types=instrument_types,
        interval=interval,
        persist=True,
    )
    error_count = int(payload.get("summary", {}).get("by_severity", {}).get("error", 0))
    if error_count and not allow_quality_issues:
        raise SystemExit(
            f"data quality gate failed with {error_count} error issue(s); "
            "run `quant data quality --persist --write-report` for details or pass --allow-quality-issues"
        )
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="quant", description="OKX-first quantitative trading system")
    add_common(parser)
    sub = parser.add_subparsers(dest="command", required=True)

    data = sub.add_parser("data")
    data_sub = data.add_subparsers(dest="data_command", required=True)
    backfill = data_sub.add_parser("backfill")
    backfill.add_argument("--symbol", action="append", help="BASE/QUOTE symbol; repeatable")
    backfill.add_argument("--instrument-type", choices=["spot", "swap"], action="append")
    backfill.add_argument("--bar", default=None)
    backfill.add_argument("--limit", type=int, default=300)
    history = data_sub.add_parser("history")
    history.add_argument("--symbol", action="append", help="BASE/QUOTE symbol; repeatable")
    history.add_argument("--instrument-type", choices=["spot", "swap"], action="append")
    history.add_argument("--bar", default=None)
    history.add_argument("--pages", type=int, default=10)
    history.add_argument("--page-limit", type=int, default=100)
    funding = data_sub.add_parser("funding")
    funding.add_argument("--symbol", action="append", help="BASE/QUOTE symbol; repeatable")
    funding.add_argument("--pages", type=int, default=10)
    funding.add_argument("--page-limit", type=int, default=100)
    exchange_info = data_sub.add_parser("exchange-info")
    exchange_info.add_argument("--instrument-type", choices=["spot", "swap"], action="append")
    open_interest = data_sub.add_parser("open-interest")
    open_interest.add_argument("--symbol", action="append", help="BASE/QUOTE symbol; repeatable")
    basis = data_sub.add_parser("basis")
    basis.add_argument("--symbol", action="append", help="BASE/QUOTE symbol; repeatable")
    long_short = data_sub.add_parser("long-short-ratio")
    long_short.add_argument("--symbol", action="append", help="BASE/QUOTE symbol; repeatable")
    long_short.add_argument("--period", default="5m")
    long_short.add_argument("--limit", type=int, default=100)
    orderbook = data_sub.add_parser("orderbook")
    orderbook.add_argument("--symbol", action="append", help="BASE/QUOTE symbol; repeatable")
    orderbook.add_argument("--instrument-type", choices=["spot", "swap"], default="spot")
    orderbook.add_argument("--depth", type=int, default=50)
    trades = data_sub.add_parser("trades")
    trades.add_argument("--symbol", action="append", help="BASE/QUOTE symbol; repeatable")
    trades.add_argument("--instrument-type", choices=["spot", "swap"], default="spot")
    trades.add_argument("--limit", type=int, default=100)
    liquidations = data_sub.add_parser("liquidations")
    liquidations.add_argument("--symbol", action="append", help="BASE/QUOTE symbol; repeatable")
    liquidations.add_argument("--limit", type=int, default=100)
    data_sub.add_parser("schema")
    quality = data_sub.add_parser("quality")
    quality.add_argument("--symbol", action="append", help="BASE/QUOTE symbol; repeatable")
    quality.add_argument("--instrument-type", choices=["spot", "swap"], action="append")
    quality.add_argument("--bar", default=None)
    quality.add_argument("--persist", action="store_true", help="Persist issues into SQLite data_quality_issues")
    quality.add_argument("--write-report", action="store_true")
    universe = data_sub.add_parser("universe")
    universe.add_argument("--instrument-type", choices=["spot", "swap"], default="spot")
    universe.add_argument("--top-n", type=int, default=20)
    universe.add_argument("--min-quote-volume", type=float, default=0.0)
    universe.add_argument("--write", action="store_true")
    stream = data_sub.add_parser("stream")
    stream.add_argument("--symbol", action="append")
    stream.add_argument("--instrument-type", choices=["spot", "swap"], default="spot")

    backtest = sub.add_parser("backtest")
    backtest.add_argument("--strategy", default=None)
    backtest.add_argument("--from", dest="start", default=None)
    backtest.add_argument("--to", dest="end", default=None)
    backtest.add_argument("--symbol", default="BTC/USDT")
    backtest.add_argument("--instrument-type", choices=["spot", "swap"], default="spot")
    backtest.add_argument("--use-synthetic", action="store_true")
    backtest.add_argument("--allow-quality-issues", action="store_true")
    backtest.add_argument("--allow-unregistered-strategy", action="store_true")

    paper = sub.add_parser("paper")
    paper_sub = paper.add_subparsers(dest="paper_command", required=True)
    paper_run = paper_sub.add_parser("run")
    paper_run.add_argument("--symbol", default="BTC/USDT")
    paper_run.add_argument("--instrument-type", choices=["spot", "swap"], default="spot")
    paper_run.add_argument("--use-synthetic", action="store_true")
    paper_portfolio = paper_sub.add_parser("portfolio-run-once")
    paper_portfolio.add_argument("--symbol", action="append", help="BASE/QUOTE symbol; repeatable")
    paper_portfolio.add_argument("--instrument-type", choices=["spot", "swap"], default="spot")
    paper_portfolio.add_argument("--lookback-bars", type=int, default=24 * 30)
    paper_portfolio.add_argument("--top-n", type=int, default=2)
    paper_portfolio.add_argument("--min-momentum", type=float, default=0.0)
    paper_portfolio.add_argument("--allow-symbol", action="append", default=None)
    paper_portfolio.add_argument("--block-symbol", action="append", default=None)
    paper_portfolio.add_argument("--max-turnover-pct", type=float, default=None)
    paper_portfolio.add_argument("--max-portfolio-drawdown-pct", type=float, default=None)
    paper_portfolio.add_argument("--max-candle-age-seconds", type=float, default=None)
    paper_portfolio.add_argument("--rebalance-cooldown-seconds", type=float, default=None)

    live = sub.add_parser("live")
    live_sub = live.add_subparsers(dest="live_command", required=True)
    live_run = live_sub.add_parser("run")
    live_run.add_argument("--confirm-live", action="store_true")
    live_run.add_argument("--symbol", action="append", help="BASE/QUOTE symbol; repeatable")
    live_run.add_argument("--instrument-type", choices=["spot", "swap"], default="spot")
    live_run.add_argument("--lookback-bars", type=int, default=24 * 30)
    live_run.add_argument("--top-n", type=int, default=2)
    live_run.add_argument("--min-momentum", type=float, default=0.0)
    live_run.add_argument("--allow-symbol", action="append", default=None)
    live_run.add_argument("--block-symbol", action="append", default=None)
    live_run.add_argument("--max-turnover-pct", type=float, default=None)
    live_run.add_argument("--max-candle-age-seconds", type=float, default=None)
    live_run.add_argument("--rebalance-cooldown-seconds", type=float, default=None)
    live_run.add_argument("--order-type", choices=["market", "limit"], default=None)
    live_run.add_argument("--refresh-candles", dest="refresh_candles", action="store_true", default=None)
    live_run.add_argument("--no-refresh-candles", dest="refresh_candles", action="store_false")
    live_run.add_argument("--refresh-candles-limit", type=int, default=None)

    report = sub.add_parser("report")
    report_sub = report.add_subparsers(dest="report_command", required=True)
    report_latest = report_sub.add_parser("latest")
    report_latest.add_argument("--name", default=None, help="Report prefix, e.g. strategy_sweep")
    report_index = report_sub.add_parser("index")
    report_index.add_argument("--name", default=None, help="Optional report prefix")
    report_index.add_argument("--limit", type=int, default=20)
    report_ads = report_sub.add_parser("ads")
    report_ads.add_argument(
        "--kind",
        choices=[
            "backtests",
            "strategy_scores",
            "quality_issues",
            "reproducibility",
            "ingestion_tasks",
            "ingestion_logs",
            "service_runs",
            "review_tasks",
            "raw_market_data",
            "open_interest",
            "basis",
            "long_short_ratio",
            "orderbook",
            "trades",
            "liquidations",
        ],
        default="backtests",
    )
    report_ads.add_argument("--limit", type=int, default=10)

    risk = sub.add_parser("risk")
    risk_sub = risk.add_subparsers(dest="risk_command", required=True)
    risk_sub.add_parser("status")

    okx = sub.add_parser("okx")
    okx_sub = okx.add_subparsers(dest="okx_command", required=True)
    okx_sub.add_parser("diagnose")
    okx_sub.add_parser("readiness")
    dry_run = okx_sub.add_parser("order-dry-run")
    dry_run.add_argument("--symbol", default="BTC/USDT")
    dry_run.add_argument("--instrument-type", choices=["spot", "swap"], default="spot")
    dry_run.add_argument("--test-notional-usdt", type=float, default=5.0)
    smoke = okx_sub.add_parser("demo-smoke")
    smoke.add_argument("--symbol", default="BTC/USDT")
    smoke.add_argument("--instrument-type", choices=["spot", "swap"], default="spot")
    smoke.add_argument("--place-test-order", action="store_true")
    smoke.add_argument("--test-notional-usdt", type=float, default=5.0)
    smoke.add_argument("--set-swap-leverage", action="store_true")
    demo_run = okx_sub.add_parser("demo-run-once")
    demo_run.add_argument("--symbol", default="BTC/USDT")
    demo_run.add_argument("--instrument-type", choices=["spot", "swap"], default="spot")
    demo_run.add_argument("--order-type", choices=["limit", "market"], default="limit")
    demo_run.add_argument("--confirm-demo-order", action="store_true")
    demo_run.add_argument("--cancel-after-place", action="store_true")
    demo_loop = okx_sub.add_parser("demo-loop")
    demo_loop.add_argument("--symbol", default="BTC/USDT")
    demo_loop.add_argument("--instrument-type", choices=["spot", "swap"], default="spot")
    demo_loop.add_argument("--order-type", choices=["limit", "market"], default="limit")
    demo_loop.add_argument("--interval-seconds", type=float, default=60.0)
    demo_loop.add_argument("--max-iterations", type=int, default=1)
    demo_loop.add_argument("--confirm-demo-order", action="store_true")
    demo_loop.add_argument("--cancel-after-place", action="store_true")
    cancel_all_after = okx_sub.add_parser("cancel-all-after")
    cancel_all_after.add_argument("--timeout-seconds", type=int, required=True)

    service = sub.add_parser("service")
    service_sub = service.add_subparsers(dest="service_command", required=True)
    service_run = service_sub.add_parser("run-demo")
    service_run.add_argument("--symbol", default="BTC/USDT")
    service_run.add_argument("--instrument-type", choices=["spot", "swap"], default="spot")
    service_run.add_argument("--order-type", choices=["limit", "market"], default="limit")
    service_run.add_argument("--interval-seconds", type=float, default=60.0)
    service_run.add_argument("--max-iterations", type=int, default=None)
    service_run.add_argument("--confirm-demo-order", action="store_true")
    service_run.add_argument("--cancel-after-place", action="store_true")
    service_paper_portfolio = service_sub.add_parser("run-paper-portfolio")
    service_paper_portfolio.add_argument("--symbol", action="append", help="BASE/QUOTE symbol; repeatable")
    service_paper_portfolio.add_argument("--instrument-type", choices=["spot", "swap"], default="spot")
    service_paper_portfolio.add_argument("--interval-seconds", type=float, default=3600.0)
    service_paper_portfolio.add_argument("--max-iterations", type=int, default=None)
    service_paper_portfolio.add_argument("--lookback-bars", type=int, default=24 * 30)
    service_paper_portfolio.add_argument("--top-n", type=int, default=2)
    service_paper_portfolio.add_argument("--min-momentum", type=float, default=0.0)
    service_paper_portfolio.add_argument("--allow-symbol", action="append", default=None)
    service_paper_portfolio.add_argument("--block-symbol", action="append", default=None)
    service_paper_portfolio.add_argument("--max-turnover-pct", type=float, default=None)
    service_paper_portfolio.add_argument("--max-portfolio-drawdown-pct", type=float, default=None)
    service_paper_portfolio.add_argument("--max-candle-age-seconds", type=float, default=None)
    service_paper_portfolio.add_argument("--rebalance-cooldown-seconds", type=float, default=None)
    service_paper_portfolio.add_argument("--refresh-candles", dest="refresh_candles", action="store_true", default=None)
    service_paper_portfolio.add_argument("--no-refresh-candles", dest="refresh_candles", action="store_false")
    service_paper_portfolio.add_argument("--refresh-candles-limit", type=int, default=None)
    service_live_portfolio = service_sub.add_parser("run-live-portfolio")
    service_live_portfolio.add_argument("--confirm-live", action="store_true")
    service_live_portfolio.add_argument("--symbol", action="append", help="BASE/QUOTE symbol; repeatable")
    service_live_portfolio.add_argument("--instrument-type", choices=["spot", "swap"], default="spot")
    service_live_portfolio.add_argument("--interval-seconds", type=float, default=3600.0)
    service_live_portfolio.add_argument("--max-iterations", type=int, default=None)
    service_live_portfolio.add_argument("--lookback-bars", type=int, default=24 * 30)
    service_live_portfolio.add_argument("--top-n", type=int, default=2)
    service_live_portfolio.add_argument("--min-momentum", type=float, default=0.0)
    service_live_portfolio.add_argument("--allow-symbol", action="append", default=None)
    service_live_portfolio.add_argument("--block-symbol", action="append", default=None)
    service_live_portfolio.add_argument("--max-turnover-pct", type=float, default=None)
    service_live_portfolio.add_argument("--max-candle-age-seconds", type=float, default=None)
    service_live_portfolio.add_argument("--rebalance-cooldown-seconds", type=float, default=None)
    service_live_portfolio.add_argument("--order-type", choices=["market", "limit"], default=None)
    service_live_portfolio.add_argument("--refresh-candles", dest="refresh_candles", action="store_true", default=None)
    service_live_portfolio.add_argument("--no-refresh-candles", dest="refresh_candles", action="store_false")
    service_live_portfolio.add_argument("--refresh-candles-limit", type=int, default=None)
    service_start_paper = service_sub.add_parser("start-paper-portfolio")
    service_start_paper.add_argument("--symbol", action="append", help="BASE/QUOTE symbol; repeatable")
    service_start_paper.add_argument("--instrument-type", choices=["spot", "swap"], default="spot")
    service_start_paper.add_argument("--interval-seconds", type=float, default=3600.0)
    service_start_paper.add_argument("--max-iterations", type=int, default=None)
    service_start_paper.add_argument("--lookback-bars", type=int, default=24 * 30)
    service_start_paper.add_argument("--top-n", type=int, default=2)
    service_start_paper.add_argument("--min-momentum", type=float, default=0.0)
    service_start_paper.add_argument("--allow-symbol", action="append", default=None)
    service_start_paper.add_argument("--block-symbol", action="append", default=None)
    service_start_paper.add_argument("--max-turnover-pct", type=float, default=None)
    service_start_paper.add_argument("--max-portfolio-drawdown-pct", type=float, default=None)
    service_start_paper.add_argument("--max-candle-age-seconds", type=float, default=None)
    service_start_paper.add_argument("--rebalance-cooldown-seconds", type=float, default=None)
    service_start_paper.add_argument("--refresh-candles", dest="refresh_candles", action="store_true", default=None)
    service_start_paper.add_argument("--no-refresh-candles", dest="refresh_candles", action="store_false")
    service_start_paper.add_argument("--refresh-candles-limit", type=int, default=None)
    service_start_paper.add_argument("--no-watchdog", action="store_true")
    service_start_paper.add_argument("--watchdog-interval-seconds", type=float, default=None)
    service_start_paper.add_argument("--watchdog-max-heartbeat-age-seconds", type=float, default=None)
    service_start_paper.add_argument("--watchdog-recover-paper", action="store_true")
    service_start_live = service_sub.add_parser("start-live-portfolio")
    service_start_live.add_argument("--confirm-live", action="store_true")
    service_start_live.add_argument("--symbol", action="append", help="BASE/QUOTE symbol; repeatable")
    service_start_live.add_argument("--instrument-type", choices=["spot", "swap"], default="spot")
    service_start_live.add_argument("--interval-seconds", type=float, default=3600.0)
    service_start_live.add_argument("--max-iterations", type=int, default=None)
    service_start_live.add_argument("--lookback-bars", type=int, default=24 * 30)
    service_start_live.add_argument("--top-n", type=int, default=2)
    service_start_live.add_argument("--min-momentum", type=float, default=0.0)
    service_start_live.add_argument("--allow-symbol", action="append", default=None)
    service_start_live.add_argument("--block-symbol", action="append", default=None)
    service_start_live.add_argument("--max-turnover-pct", type=float, default=None)
    service_start_live.add_argument("--max-candle-age-seconds", type=float, default=None)
    service_start_live.add_argument("--rebalance-cooldown-seconds", type=float, default=None)
    service_start_live.add_argument("--order-type", choices=["market", "limit"], default=None)
    service_start_live.add_argument("--refresh-candles", dest="refresh_candles", action="store_true", default=None)
    service_start_live.add_argument("--no-refresh-candles", dest="refresh_candles", action="store_false")
    service_start_live.add_argument("--refresh-candles-limit", type=int, default=None)
    service_start_live.add_argument("--no-watchdog", action="store_true")
    service_start_live.add_argument("--watchdog-interval-seconds", type=float, default=None)
    service_start_live.add_argument("--watchdog-max-heartbeat-age-seconds", type=float, default=None)
    service_start_watchdog = service_sub.add_parser("start-watchdog")
    service_start_watchdog.add_argument("--interval-seconds", type=float, default=None)
    service_start_watchdog.add_argument("--max-heartbeat-age-seconds", type=float, default=None)
    service_start_watchdog.add_argument("--no-require-running", action="store_true")
    service_start_watchdog.add_argument("--no-kill-switch", action="store_true")
    service_start_watchdog.add_argument("--no-stop-service", action="store_true")
    service_start_watchdog.add_argument("--recover-paper", action="store_true")
    service_sub.add_parser("status")
    service_sub.add_parser("recover-paper")
    service_health_parser = service_sub.add_parser("health")
    service_health_parser.add_argument("--max-heartbeat-age-seconds", type=float, default=300.0)
    service_health_parser.add_argument("--require-running", action="store_true")
    service_snapshot = service_sub.add_parser("snapshot")
    service_snapshot.add_argument("--max-heartbeat-age-seconds", type=float, default=300.0)
    service_snapshot.add_argument("--require-running", action="store_true")
    service_report = service_sub.add_parser("report")
    service_report.add_argument("--max-heartbeat-age-seconds", type=float, default=300.0)
    service_report.add_argument("--require-running", action="store_true")
    service_stability = service_sub.add_parser("stability")
    service_stability.add_argument("--max-heartbeat-age-seconds", type=float, default=300.0)
    service_stability.add_argument("--require-running", action="store_true")
    service_stability.add_argument("--since-hours", type=float, default=None)
    service_watchdog = service_sub.add_parser("watchdog")
    service_watchdog.add_argument("--interval-seconds", type=float, default=None)
    service_watchdog.add_argument("--max-heartbeat-age-seconds", type=float, default=None)
    service_watchdog.add_argument("--max-iterations", type=int, default=None)
    service_watchdog.add_argument("--no-require-running", action="store_true")
    service_watchdog.add_argument("--no-kill-switch", action="store_true")
    service_watchdog.add_argument("--no-stop-service", action="store_true")
    service_watchdog.add_argument("--recover-paper", action="store_true")
    service_acceptance = service_sub.add_parser("acceptance")
    service_acceptance.add_argument("--symbol", action="append", help="BASE/QUOTE symbol; repeatable")
    service_acceptance.add_argument("--instrument-type", choices=["spot", "swap"], default="spot")
    service_acceptance.add_argument("--iterations", type=int, default=3)
    service_acceptance.add_argument("--lookback-bars", type=int, default=24 * 30)
    service_acceptance.add_argument("--top-n", type=int, default=2)
    service_acceptance.add_argument("--max-heartbeat-age-seconds", type=float, default=300.0)
    service_acceptance.add_argument("--no-report", action="store_true")
    service_live_gate_drill = service_sub.add_parser("live-gate-drill")
    service_live_gate_drill.add_argument("--no-report", action="store_true")
    service_notification_drill = service_sub.add_parser("notification-drill")
    service_notification_drill.add_argument("--level", choices=["info", "warning", "critical"], default="info")
    service_notification_drill.add_argument("--no-report", action="store_true")
    service_pre_live = service_sub.add_parser("pre-live-check")
    service_pre_live.add_argument("--min-observation-hours", type=float, default=24.0)
    service_pre_live.add_argument("--max-live-cap-usdt", type=float, default=50.0)
    service_pre_live.add_argument("--max-leverage", type=float, default=3.0)
    service_pre_live.add_argument("--max-heartbeat-age-seconds", type=float, default=None)
    service_pre_live.add_argument("--no-require-running", action="store_true")
    service_pre_live.add_argument("--no-refresh-stability", action="store_true")
    service_pre_live.add_argument("--no-report", action="store_true")
    service_sub.add_parser("stop")

    research = sub.add_parser("research")
    research_sub = research.add_subparsers(dest="research_command", required=True)
    sweep = research_sub.add_parser("sweep")
    sweep.add_argument("--symbol", action="append", help="BASE/QUOTE symbol; repeatable")
    sweep.add_argument("--instrument-type", choices=["spot", "swap"], default="spot")
    sweep.add_argument("--strategy", action="append", choices=DEFAULT_CANDIDATES)
    sweep.add_argument("--from", dest="start", default=None)
    sweep.add_argument("--to", dest="end", default=None)
    sweep.add_argument("--write-report", action="store_true")
    sweep.add_argument("--allow-quality-issues", action="store_true")
    sweep.add_argument("--allow-unregistered-strategy", action="store_true")
    multi_tf_sweep = research_sub.add_parser("multi-timeframe-sweep")
    multi_tf_sweep.add_argument("--symbol", action="append", help="BASE/QUOTE symbol; repeatable")
    multi_tf_sweep.add_argument("--instrument-type", choices=["spot", "swap"], default="spot")
    multi_tf_sweep.add_argument("--bar", action="append", default=None, help="Bar interval; repeatable, for example 1H or 4H")
    multi_tf_sweep.add_argument("--strategy", action="append", choices=DEFAULT_CANDIDATES)
    multi_tf_sweep.add_argument("--from", dest="start", default=None)
    multi_tf_sweep.add_argument("--to", dest="end", default=None)
    multi_tf_sweep.add_argument("--write-report", action="store_true")
    multi_tf_sweep.add_argument("--allow-quality-issues", action="store_true")
    multi_tf_sweep.add_argument("--allow-unregistered-strategy", action="store_true")
    xsmom = research_sub.add_parser("xsmom")
    xsmom.add_argument("--symbol", action="append", help="BASE/QUOTE symbol; repeatable")
    xsmom.add_argument("--instrument-type", choices=["spot", "swap"], default="spot")
    xsmom.add_argument("--lookback-bars", type=int, default=24 * 30)
    xsmom.add_argument("--hold-bars", type=int, default=24 * 7)
    xsmom.add_argument("--top-n", type=int, default=1)
    xsmom.add_argument("--from", dest="start", default=None)
    xsmom.add_argument("--to", dest="end", default=None)
    xsmom.add_argument("--write-report", action="store_true")
    xsmom_grid = research_sub.add_parser("xsmom-grid")
    xsmom_grid.add_argument("--symbol", action="append", help="BASE/QUOTE symbol; repeatable")
    xsmom_grid.add_argument("--instrument-type", choices=["spot", "swap"], default="spot")
    xsmom_grid.add_argument("--lookback-bars", type=int, action="append", default=None)
    xsmom_grid.add_argument("--hold-bars", type=int, action="append", default=None)
    xsmom_grid.add_argument("--top-n", type=int, action="append", default=None)
    xsmom_grid.add_argument("--min-trades", type=int, default=6)
    xsmom_grid.add_argument("--from", dest="start", default=None)
    xsmom_grid.add_argument("--to", dest="end", default=None)
    xsmom_grid.add_argument("--write-report", action="store_true")
    xsmom_wf = research_sub.add_parser("xsmom-walk-forward")
    xsmom_wf.add_argument("--symbol", action="append", help="BASE/QUOTE symbol; repeatable")
    xsmom_wf.add_argument("--instrument-type", choices=["spot", "swap"], default="spot")
    xsmom_wf.add_argument("--lookback-bars", type=int, action="append", default=None)
    xsmom_wf.add_argument("--hold-bars", type=int, action="append", default=None)
    xsmom_wf.add_argument("--top-n", type=int, action="append", default=None)
    xsmom_wf.add_argument("--train-bars", type=int, default=24 * 60)
    xsmom_wf.add_argument("--test-bars", type=int, default=24 * 14)
    xsmom_wf.add_argument("--step-bars", type=int, default=None)
    xsmom_wf.add_argument("--min-trades", type=int, default=4)
    xsmom_wf.add_argument("--write-report", action="store_true")
    xsmom_costs = research_sub.add_parser("xsmom-costs")
    xsmom_costs.add_argument("--symbol", action="append", help="BASE/QUOTE symbol; repeatable")
    xsmom_costs.add_argument("--instrument-type", choices=["spot", "swap"], default="spot")
    xsmom_costs.add_argument("--lookback-bars", type=int, default=720)
    xsmom_costs.add_argument("--hold-bars", type=int, default=168)
    xsmom_costs.add_argument("--top-n", type=int, default=2)
    xsmom_costs.add_argument("--fee-rate", type=float, action="append", default=None)
    xsmom_costs.add_argument("--slippage-bps", type=float, action="append", default=None)
    xsmom_costs.add_argument("--from", dest="start", default=None)
    xsmom_costs.add_argument("--to", dest="end", default=None)
    xsmom_costs.add_argument("--write-report", action="store_true")
    adaptive = research_sub.add_parser("adaptive-trend")
    adaptive.add_argument("--symbol", action="append", help="BASE/QUOTE symbol; repeatable")
    adaptive.add_argument("--instrument-type", choices=["spot", "swap"], default="spot")
    adaptive.add_argument("--lookback-bars", type=int, default=24 * 30)
    adaptive.add_argument("--hold-bars", type=int, default=24 * 7)
    adaptive.add_argument("--top-n", type=int, default=2)
    adaptive.add_argument("--ema-span", type=int, default=24 * 20)
    adaptive.add_argument("--volatility-bars", type=int, default=24 * 14)
    adaptive.add_argument("--target-volatility", type=float, default=0.20)
    adaptive.add_argument("--max-weight", type=float, default=0.50)
    adaptive.add_argument("--from", dest="start", default=None)
    adaptive.add_argument("--to", dest="end", default=None)
    adaptive.add_argument("--write-report", action="store_true")
    adaptive_grid = research_sub.add_parser("adaptive-trend-grid")
    adaptive_grid.add_argument("--symbol", action="append", help="BASE/QUOTE symbol; repeatable")
    adaptive_grid.add_argument("--instrument-type", choices=["spot", "swap"], default="spot")
    adaptive_grid.add_argument("--lookback-bars", type=int, action="append", default=None)
    adaptive_grid.add_argument("--hold-bars", type=int, action="append", default=None)
    adaptive_grid.add_argument("--top-n", type=int, action="append", default=None)
    adaptive_grid.add_argument("--ema-span", type=int, action="append", default=None)
    adaptive_grid.add_argument("--volatility-bars", type=int, action="append", default=None)
    adaptive_grid.add_argument("--target-volatility", type=float, action="append", default=None)
    adaptive_grid.add_argument("--max-weight", type=float, action="append", default=None)
    adaptive_grid.add_argument("--min-trades", type=int, default=6)
    adaptive_grid.add_argument("--from", dest="start", default=None)
    adaptive_grid.add_argument("--to", dest="end", default=None)
    adaptive_grid.add_argument("--write-report", action="store_true")
    adaptive_wf = research_sub.add_parser("adaptive-trend-walk-forward")
    adaptive_wf.add_argument("--symbol", action="append", help="BASE/QUOTE symbol; repeatable")
    adaptive_wf.add_argument("--instrument-type", choices=["spot", "swap"], default="spot")
    adaptive_wf.add_argument("--lookback-bars", type=int, action="append", default=None)
    adaptive_wf.add_argument("--hold-bars", type=int, action="append", default=None)
    adaptive_wf.add_argument("--top-n", type=int, action="append", default=None)
    adaptive_wf.add_argument("--ema-span", type=int, action="append", default=None)
    adaptive_wf.add_argument("--volatility-bars", type=int, action="append", default=None)
    adaptive_wf.add_argument("--target-volatility", type=float, action="append", default=None)
    adaptive_wf.add_argument("--max-weight", type=float, action="append", default=None)
    adaptive_wf.add_argument("--train-bars", type=int, default=24 * 60)
    adaptive_wf.add_argument("--test-bars", type=int, default=24 * 14)
    adaptive_wf.add_argument("--step-bars", type=int, default=None)
    adaptive_wf.add_argument("--min-trades", type=int, default=4)
    adaptive_wf.add_argument("--write-report", action="store_true")
    adaptive_costs = research_sub.add_parser("adaptive-trend-costs")
    adaptive_costs.add_argument("--symbol", action="append", help="BASE/QUOTE symbol; repeatable")
    adaptive_costs.add_argument("--instrument-type", choices=["spot", "swap"], default="spot")
    adaptive_costs.add_argument("--lookback-bars", type=int, default=720)
    adaptive_costs.add_argument("--hold-bars", type=int, default=168)
    adaptive_costs.add_argument("--top-n", type=int, default=2)
    adaptive_costs.add_argument("--ema-span", type=int, default=480)
    adaptive_costs.add_argument("--volatility-bars", type=int, default=168)
    adaptive_costs.add_argument("--target-volatility", type=float, default=0.15)
    adaptive_costs.add_argument("--max-weight", type=float, default=0.35)
    adaptive_costs.add_argument("--fee-rate", type=float, action="append", default=None)
    adaptive_costs.add_argument("--slippage-bps", type=float, action="append", default=None)
    adaptive_costs.add_argument("--from", dest="start", default=None)
    adaptive_costs.add_argument("--to", dest="end", default=None)
    adaptive_costs.add_argument("--write-report", action="store_true")
    cointegration = research_sub.add_parser("btc-eth-cointegration")
    cointegration.add_argument("--symbol", action="append", help="Pair symbols; defaults to BTC/USDT and ETH/USDT")
    cointegration.add_argument("--instrument-type", choices=["spot", "swap"], default="spot")
    cointegration.add_argument("--lookback-bars", type=int, default=24 * 30)
    cointegration.add_argument("--entry-z", type=float, default=2.0)
    cointegration.add_argument("--exit-z", type=float, default=0.5)
    cointegration.add_argument("--max-hold-bars", type=int, default=24 * 7)
    cointegration.add_argument("--max-gross-exposure", type=float, default=0.50)
    cointegration.add_argument("--from", dest="start", default=None)
    cointegration.add_argument("--to", dest="end", default=None)
    cointegration.add_argument("--write-report", action="store_true")
    funding_carry = research_sub.add_parser("funding-carry")
    funding_carry.add_argument("--symbol", action="append", help="BASE/QUOTE symbol; repeatable")
    funding_carry.add_argument("--lookback-periods", type=int, default=3)
    funding_carry.add_argument("--hold-periods", type=int, default=1)
    funding_carry.add_argument("--top-n", type=int, default=2)
    funding_carry.add_argument("--min-funding-rate", type=float, default=0.0)
    funding_carry.add_argument("--max-notional-pct", type=float, default=1.0)
    funding_carry.add_argument("--from", dest="start", default=None)
    funding_carry.add_argument("--to", dest="end", default=None)
    funding_carry.add_argument("--write-report", action="store_true")
    funding_grid = research_sub.add_parser("funding-carry-grid")
    funding_grid.add_argument("--symbol", action="append", help="BASE/QUOTE symbol; repeatable")
    funding_grid.add_argument("--lookback-periods", type=int, action="append", default=None)
    funding_grid.add_argument("--hold-periods", type=int, action="append", default=None)
    funding_grid.add_argument("--top-n", type=int, action="append", default=None)
    funding_grid.add_argument("--min-funding-rate", type=float, action="append", default=None)
    funding_grid.add_argument("--max-notional-pct", type=float, action="append", default=None)
    funding_grid.add_argument("--min-rebalances", type=int, default=6)
    funding_grid.add_argument("--from", dest="start", default=None)
    funding_grid.add_argument("--to", dest="end", default=None)
    funding_grid.add_argument("--write-report", action="store_true")
    funding_wf = research_sub.add_parser("funding-carry-walk-forward")
    funding_wf.add_argument("--symbol", action="append", help="BASE/QUOTE symbol; repeatable")
    funding_wf.add_argument("--lookback-periods", type=int, action="append", default=None)
    funding_wf.add_argument("--hold-periods", type=int, action="append", default=None)
    funding_wf.add_argument("--top-n", type=int, action="append", default=None)
    funding_wf.add_argument("--min-funding-rate", type=float, action="append", default=None)
    funding_wf.add_argument("--max-notional-pct", type=float, action="append", default=None)
    funding_wf.add_argument("--train-periods", type=int, default=360)
    funding_wf.add_argument("--test-periods", type=int, default=90)
    funding_wf.add_argument("--step-periods", type=int, default=None)
    funding_wf.add_argument("--min-rebalances", type=int, default=4)
    funding_wf.add_argument("--write-report", action="store_true")
    funding_costs = research_sub.add_parser("funding-carry-costs")
    funding_costs.add_argument("--symbol", action="append", help="BASE/QUOTE symbol; repeatable")
    funding_costs.add_argument("--lookback-periods", type=int, default=3)
    funding_costs.add_argument("--hold-periods", type=int, default=3)
    funding_costs.add_argument("--top-n", type=int, default=2)
    funding_costs.add_argument("--min-funding-rate", type=float, default=0.0001)
    funding_costs.add_argument("--max-notional-pct", type=float, default=0.5)
    funding_costs.add_argument("--fee-rate", type=float, action="append", default=None)
    funding_costs.add_argument("--slippage-bps", type=float, action="append", default=None)
    funding_costs.add_argument("--from", dest="start", default=None)
    funding_costs.add_argument("--to", dest="end", default=None)
    funding_costs.add_argument("--write-report", action="store_true")
    factor_evaluate = research_sub.add_parser("factor-evaluate")
    factor_evaluate.add_argument("--factor", required=True, help="Factor id, for example crypto_momentum_24h")
    factor_evaluate.add_argument("--symbol", action="append", help="BASE/QUOTE symbol; repeatable")
    factor_evaluate.add_argument("--instrument-type", choices=["spot", "swap"], default="spot")
    factor_evaluate.add_argument("--horizon-bars", type=int, action="append", default=None)
    factor_evaluate.add_argument("--quantiles", type=int, default=5)
    factor_evaluate.add_argument("--min-symbols", type=int, default=3)
    factor_evaluate.add_argument("--from", dest="start", default=None)
    factor_evaluate.add_argument("--to", dest="end", default=None)
    factor_evaluate.add_argument("--write-report", action="store_true")
    factor_evaluate.add_argument("--allow-quality-issues", action="store_true")
    alpha_ensemble = research_sub.add_parser("alpha-ensemble")
    alpha_ensemble.add_argument("--spec", required=True, help="Path to alpha ensemble YAML spec")
    alpha_ensemble.add_argument("--symbol", action="append", help="BASE/QUOTE symbol override; repeatable")
    alpha_ensemble.add_argument("--instrument-type", choices=["spot", "swap"], default=None)
    alpha_ensemble.add_argument("--from", dest="start", default=None)
    alpha_ensemble.add_argument("--to", dest="end", default=None)
    alpha_ensemble.add_argument("--write-report", action="store_true")
    alpha_ensemble.add_argument("--allow-quality-issues", action="store_true")
    shortlist = research_sub.add_parser("shortlist")
    shortlist.add_argument("--write-report", action="store_true")
    promotion = research_sub.add_parser("promotion-scorecard")
    promotion.add_argument("--write-report", action="store_true")
    knowledge = research_sub.add_parser("knowledge-base")
    knowledge.add_argument("--path", default=None, help="Path to strategy knowledge base YAML")
    knowledge.add_argument("--write-report", action="store_true")
    knowledge.add_argument("--sync-registry", action="store_true")
    scaffold = research_sub.add_parser("scaffold")
    scaffold.add_argument("--strategy-id", required=True)
    scaffold.add_argument("--name", default=None)
    scaffold.add_argument("--family", default=None)
    scaffold.add_argument("--output-dir", default=None)

    review = sub.add_parser("review")
    review_sub = review.add_subparsers(dest="review_command", required=True)
    review_queue_parser = review_sub.add_parser("queue")
    review_queue_parser.add_argument("--write-report", action="store_true")
    review_queue_parser.add_argument("--notify", action="store_true")
    review_queue_parser.add_argument("--limit", type=int, default=50)

    sub.add_parser("kill")
    return parser


def command_data(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    config.ensure_dirs()
    if args.data_command == "backfill":
        paths = backfill_candles(
            config,
            OkxRestClient(config.okx),
            symbols=args.symbol,
            instrument_types=args.instrument_type,
            bar=args.bar,
            limit=args.limit,
        )
        print(json.dumps({"written": [str(path) for path in paths]}, indent=2, ensure_ascii=False))
        return 0
    if args.data_command == "history":
        paths = backfill_history_candles(
            config,
            OkxRestClient(config.okx),
            symbols=args.symbol,
            instrument_types=args.instrument_type,
            bar=args.bar,
            pages=args.pages,
            page_limit=args.page_limit,
        )
        print(json.dumps({"written": [str(path) for path in paths]}, indent=2, ensure_ascii=False))
        return 0
    if args.data_command == "funding":
        paths = backfill_funding_rates(
            config,
            OkxRestClient(config.okx),
            symbols=args.symbol or config.market.symbols,
            pages=args.pages,
            page_limit=args.page_limit,
        )
        print(json.dumps({"written": [str(path) for path in paths]}, indent=2, ensure_ascii=False))
        return 0
    if args.data_command == "exchange-info":
        payload = backfill_exchange_info(
            config,
            OkxRestClient(config.okx),
            instrument_types=args.instrument_type,
        )
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    if args.data_command == "open-interest":
        payload = backfill_open_interest(
            config,
            OkxRestClient(config.okx),
            symbols=args.symbol or config.market.symbols,
        )
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    if args.data_command == "basis":
        payload = backfill_basis(
            config,
            OkxRestClient(config.okx),
            symbols=args.symbol or config.market.symbols,
        )
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    if args.data_command == "long-short-ratio":
        payload = backfill_long_short_ratio(
            config,
            OkxRestClient(config.okx),
            symbols=args.symbol or config.market.symbols,
            period=args.period,
            limit=args.limit,
        )
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    if args.data_command == "orderbook":
        payload = backfill_orderbook(
            config,
            OkxRestClient(config.okx),
            symbols=args.symbol or config.market.symbols,
            instrument_type=args.instrument_type,
            depth=args.depth,
        )
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    if args.data_command == "trades":
        payload = backfill_recent_trades(
            config,
            OkxRestClient(config.okx),
            symbols=args.symbol or config.market.symbols,
            instrument_type=args.instrument_type,
            limit=args.limit,
        )
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    if args.data_command == "liquidations":
        payload = backfill_liquidations(
            config,
            OkxRestClient(config.okx),
            symbols=args.symbol or config.market.symbols,
            limit=args.limit,
        )
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    if args.data_command == "schema":
        payload = AuditStore(config.state_dir).datahub_schema_status()
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    if args.data_command == "quality":
        symbols = args.symbol or config.market.symbols
        instrument_types = args.instrument_type or config.market.instrument_types
        if args.write_report:
            path = run_ohlcv_quality_report(
                config,
                symbols=symbols,
                instrument_types=instrument_types,
                interval=args.bar,
                persist=True if args.persist else False,
            )
            print(json.dumps({"report_path": str(path)}, indent=2, ensure_ascii=False))
        else:
            payload = run_ohlcv_quality_check(
                config,
                symbols=symbols,
                instrument_types=instrument_types,
                interval=args.bar,
                persist=args.persist,
            )
            print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        return 0
    if args.data_command == "universe":
        rows = discover_usdt_universe(
            config,
            OkxRestClient(config.okx),
            instrument_type=args.instrument_type,
            top_n=args.top_n,
            min_quote_volume=args.min_quote_volume,
        )
        payload = {
            "count": len(rows),
            "symbols": [row["symbol"] for row in rows],
            "rows": rows,
        }
        if args.write:
            payload["path"] = str(write_universe(config, rows, f"okx_{args.instrument_type}_usdt_top{args.top_n}"))
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    if args.data_command == "stream":
        ws = OkxWebSocketClient(config.okx)
        symbols = args.symbol or config.market.symbols
        channels = ws.ticker_channels(symbols, args.instrument_type)
        print(json.dumps({"url": ws.public_url, "subscribe": ws.subscribe_message(channels)}, indent=2))
        return 0
    raise ValueError(args.data_command)


def command_backtest(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    config.ensure_dirs()
    if args.strategy:
        config.strategy.name = args.strategy
    require_strategy_cards([config.strategy.name], allow_unregistered=args.allow_unregistered_strategy)
    candles = synthetic_candles(args.symbol, args.instrument_type) if args.use_synthetic else load_candles(
        config, args.symbol, args.instrument_type
    )
    candles = filter_date_range(candles, args.start, args.end)
    if candles.empty:
        raise SystemExit("no local candles found; run `quant data backfill` or pass --use-synthetic")
    if not args.use_synthetic:
        require_clean_ohlcv_data(
            config,
            symbols=[args.symbol],
            instrument_types=[args.instrument_type],
            interval=config.market.bar,
            allow_quality_issues=args.allow_quality_issues,
        )
    path = Backtester(config).run_and_write(candles, args.symbol, InstrumentType(args.instrument_type))
    print(f"backtest report: {path}")
    return 0


def command_paper(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    config.mode = "paper"
    config.ensure_dirs()
    if args.paper_command == "run":
        result = run_paper_once(config, args.symbol, args.instrument_type, use_synthetic=args.use_synthetic)
        out = {
            "signal": dataclass_to_dict(result["signal"]),
            "order": dataclass_to_dict(result["order"]) if result["order"] else None,
            "message": result["message"],
        }
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0
    if args.paper_command == "portfolio-run-once":
        symbols = args.symbol or config.market.symbols
        result = run_paper_portfolio_once(
            config,
            symbols,
            instrument_type=args.instrument_type,
            lookback_bars=args.lookback_bars,
            top_n=args.top_n,
            min_momentum=args.min_momentum,
            allowlist=args.allow_symbol,
            blocklist=args.block_symbol,
            max_turnover_pct=args.max_turnover_pct,
            max_portfolio_drawdown_pct=args.max_portfolio_drawdown_pct,
            max_candle_age_seconds=args.max_candle_age_seconds,
            rebalance_cooldown_seconds=args.rebalance_cooldown_seconds,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        return 0
    raise ValueError(args.paper_command)


def command_live(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    config.mode = "live"
    config.ensure_dirs()
    if args.live_command == "run":
        validate_live(config, confirm_live=args.confirm_live)
        refresh_enabled = config.service.refresh_candles_before_iteration if args.refresh_candles is None else args.refresh_candles
        if refresh_enabled:
            backfill_candles(
                config,
                OkxRestClient(config.okx),
                symbols=args.symbol or config.market.symbols,
                instrument_types=[args.instrument_type],
                bar=config.market.bar,
                limit=args.refresh_candles_limit or config.service.refresh_candles_limit,
            )
        result = run_okx_live_portfolio_once(
            config,
            args.symbol or config.market.symbols,
            instrument_type=args.instrument_type,
            lookback_bars=args.lookback_bars,
            top_n=args.top_n,
            min_momentum=args.min_momentum,
            allowlist=args.allow_symbol,
            blocklist=args.block_symbol,
            max_turnover_pct=args.max_turnover_pct,
            max_candle_age_seconds=args.max_candle_age_seconds,
            rebalance_cooldown_seconds=args.rebalance_cooldown_seconds,
            confirm_live=args.confirm_live,
            order_type=args.order_type,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        return 0
    raise ValueError(args.live_command)


def command_report(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    if args.report_command == "latest":
        pattern = f"{args.name}_latest.json" if args.name else "*_latest.json"
        reports = sorted(Path(config.report_dir).glob(pattern))
        if not reports:
            raise SystemExit("no latest report found")
        print(reports[-1].read_text(encoding="utf-8"))
        return 0
    if args.report_command == "index":
        pattern = f"{args.name}_*.json" if args.name else "*.json"
        reports = sorted(Path(config.report_dir).glob(pattern), key=lambda path: path.stat().st_mtime, reverse=True)
        rows = [
            {
                "name": path.name,
                "path": str(path),
                "size_bytes": path.stat().st_size,
                "modified_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
            }
            for path in reports[: args.limit]
        ]
        print(json.dumps({"count": len(rows), "rows": rows}, indent=2, ensure_ascii=False))
        return 0
    if args.report_command == "ads":
        audit = AuditStore(config.state_dir)
        rows = [dict(row) for row in audit.recent_rows(args.kind, limit=args.limit)]
        print(json.dumps({"kind": args.kind, "count": len(rows), "rows": rows}, indent=2, ensure_ascii=False, default=str))
        return 0
    raise ValueError(args.report_command)


def command_risk(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    audit = AuditStore(config.state_dir)
    payload = {
        "kill_switch_active": Path(config.risk.kill_switch_file).exists(),
        "latest_risk_events": [dict(row) for row in audit.latest_risk_events()],
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def command_review(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    config.ensure_dirs()
    if args.review_command == "queue":
        if args.write_report:
            path = review_queue_report(config, send_notification=args.notify, limit=args.limit)
            print(json.dumps({"report_path": str(path)}, indent=2, ensure_ascii=False))
        else:
            payload = review_queue(config, limit=args.limit)
            print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        return 0
    raise ValueError(args.review_command)


def command_okx(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    config.ensure_dirs()
    if args.okx_command == "diagnose":
        payload = results_to_payload(diagnose_okx(config))
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    if args.okx_command == "readiness":
        payload = readiness_summary(diagnose_okx(config))
        report_path = write_report(config.report_dir, "okx_readiness", payload)
        payload["report_path"] = str(report_path)
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    if args.okx_command == "order-dry-run":
        client = OkxRestClient(config.okx)
        ticker = client.get_ticker(args.symbol, args.instrument_type)
        last = float(ticker.get("last") or ticker.get("askPx") or ticker.get("bidPx") or 0)
        if last <= 0:
            raise RuntimeError(f"cannot derive mark price for {args.symbol}")
        instruments = client.get_instruments(args.instrument_type)
        inst_id = okx_inst_id(args.symbol, args.instrument_type)
        instrument = find_instrument(instruments, inst_id)
        quantity = round_order_quantity(args.test_notional_usdt / last, instrument)
        price = round_limit_price(last * (0.50 if args.instrument_type == "spot" else 0.75), instrument)
        payload = {
            "symbol": args.symbol,
            "instrument_type": args.instrument_type,
            "inst_id": inst_id,
            "last": last,
            "quantity": quantity,
            "limit_price": price,
            "requested_notional_usdt": args.test_notional_usdt,
            "minSz": instrument.get("minSz"),
            "lotSz": instrument.get("lotSz"),
            "tickSz": instrument.get("tickSz"),
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    if args.okx_command == "demo-smoke":
        if not config.okx.demo_trading:
            raise PermissionError("demo-smoke requires okx.demo_trading: true")
        client = OkxRestClient(config.okx)
        if not client.credentials.present:
            raise PermissionError(
                "demo-smoke requires OKX_DEMO_API_KEY, OKX_DEMO_API_SECRET, and OKX_DEMO_PASSPHRASE"
            )
        account = client.get_account_config()
        spot = client.get_account_instruments("spot")
        swap = client.get_account_instruments("swap")
        payload = {
            "demo_private_auth": True,
            "account": {
                "acctLv": (account.get("data") or [{}])[0].get("acctLv"),
                "posMode": (account.get("data") or [{}])[0].get("posMode"),
                "uid_present": bool((account.get("data") or [{}])[0].get("uid")),
            },
            "spot_instruments": len(spot),
            "swap_instruments": len(swap),
            "set_leverage": None,
            "test_order": None,
        }
        if args.set_swap_leverage:
            payload["set_leverage"] = client.set_leverage(
                args.symbol,
                "swap",
                config.risk.max_leverage,
                margin_mode=config.execution.margin_mode,
            )
        if args.place_test_order:
            ticker = client.get_ticker(args.symbol, args.instrument_type)
            last = float(ticker.get("last") or ticker.get("askPx") or ticker.get("bidPx") or 0)
            if last <= 0:
                raise RuntimeError(f"cannot derive mark price for {args.symbol}")
            account_instruments = spot if args.instrument_type == "spot" else swap
            instrument = find_instrument(account_instruments, okx_inst_id(args.symbol, args.instrument_type))
            quantity = round_order_quantity(args.test_notional_usdt / last, instrument)
            # Use a deep passive limit price so the order validates trade permission
            # while minimizing accidental immediate execution in demo.
            price = round_limit_price(last * (0.50 if args.instrument_type == "spot" else 0.75), instrument)
            order = client.place_order(
                symbol=args.symbol,
                instrument_type=args.instrument_type,
                side="buy",
                quantity=quantity,
                order_type="limit",
                price=price,
                client_order_id=None,
                margin_mode=config.execution.margin_mode,
            )
            payload["test_order"] = {"place_response": order}
            data = order.get("data") or []
            if data and data[0].get("ordId"):
                payload["test_order"]["cancel_response"] = client.cancel_order(
                    args.symbol, args.instrument_type, order_id=data[0].get("ordId")
                )
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    if args.okx_command == "demo-run-once":
        result = run_okx_demo_once(
            config,
            args.symbol,
            args.instrument_type,
            confirm_demo_order=args.confirm_demo_order,
            order_type=args.order_type,
            cancel_after_place=args.cancel_after_place,
        )
        out = {
            "signal": dataclass_to_dict(result["signal"]),
            "order": dataclass_to_dict(result["order"]) if result.get("order") else None,
            "planned_order": result.get("planned_order"),
            "place_response": result.get("place_response"),
            "cancel_response": result.get("cancel_response"),
            "message": result["message"],
        }
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0
    if args.okx_command == "demo-loop":
        results = run_okx_demo_loop(
            config,
            args.symbol,
            args.instrument_type,
            interval_seconds=args.interval_seconds,
            max_iterations=args.max_iterations,
            confirm_demo_order=args.confirm_demo_order,
            order_type=args.order_type,
            cancel_after_place=args.cancel_after_place,
        )
        print(json.dumps({"iterations": results}, indent=2, ensure_ascii=False))
        return 0
    if args.okx_command == "cancel-all-after":
        client = OkxRestClient(config.okx)
        if not client.credentials.present:
            raise PermissionError("cancel-all-after requires OKX API credentials for the selected environment")
        response = client.cancel_all_after(args.timeout_seconds)
        print(json.dumps(response, indent=2, ensure_ascii=False))
        return 0
    raise ValueError(args.okx_command)


def command_service(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    config.ensure_dirs()
    if args.service_command == "start-live-portfolio":
        config.mode = "live"
        config.okx.demo_trading = False
        validate_live(config, confirm_live=args.confirm_live)
        if service_status(config).get("running"):
            raise RuntimeError("live portfolio service is already running")
        prepare_service_launch(config, clear_kill_switch=False)
        service_launch = launch_detached_command(
            config,
            "live_portfolio_service",
            live_portfolio_service_command(args),
            config.service.log_file,
            config.service.launch_state_file,
        )
        watchdog_launch = None
        if not args.no_watchdog:
            if watchdog_status(config).get("running"):
                raise RuntimeError("watchdog service is already running")
            watchdog_launch = launch_detached_command(
                config,
                "watchdog_service",
                watchdog_service_command(
                    args.config,
                    args.watchdog_interval_seconds,
                    effective_watchdog_max_heartbeat_age(
                        args.interval_seconds,
                        args.watchdog_max_heartbeat_age_seconds,
                    ),
                    recover_paper=False,
                ),
                config.service.watchdog_log_file,
                config.service.watchdog_launch_state_file,
            )
        print(
            json.dumps(
                {"service": service_launch, "watchdog": watchdog_launch},
                indent=2,
                ensure_ascii=False,
                default=str,
            )
        )
        return 0
    if args.service_command == "start-paper-portfolio":
        if service_status(config).get("running"):
            raise RuntimeError("paper portfolio service is already running")
        prepare_service_launch(config, clear_kill_switch=True)
        service_launch = launch_detached_command(
            config,
            "paper_portfolio_service",
            paper_portfolio_service_command(args),
            config.service.log_file,
            config.service.launch_state_file,
        )
        watchdog_launch = None
        if not args.no_watchdog:
            if watchdog_status(config).get("running"):
                raise RuntimeError("watchdog service is already running")
            watchdog_launch = launch_detached_command(
                config,
                "watchdog_service",
                watchdog_service_command(
                    args.config,
                    args.watchdog_interval_seconds,
                    effective_watchdog_max_heartbeat_age(
                        args.interval_seconds,
                        args.watchdog_max_heartbeat_age_seconds,
                    ),
                    recover_paper=args.watchdog_recover_paper,
                ),
                config.service.watchdog_log_file,
                config.service.watchdog_launch_state_file,
            )
        print(
            json.dumps(
                {"service": service_launch, "watchdog": watchdog_launch},
                indent=2,
                ensure_ascii=False,
                default=str,
            )
        )
        return 0
    if args.service_command == "start-watchdog":
        if watchdog_status(config).get("running"):
            raise RuntimeError("watchdog service is already running")
        payload = launch_detached_command(
            config,
            "watchdog_service",
            watchdog_service_command(
                args.config,
                args.interval_seconds,
                args.max_heartbeat_age_seconds,
                require_running=not args.no_require_running,
                trigger_kill_switch=not args.no_kill_switch,
                stop_service=not args.no_stop_service,
                recover_paper=args.recover_paper,
            ),
            config.service.watchdog_log_file,
            config.service.watchdog_launch_state_file,
        )
        print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        return 0
    if args.service_command == "run-demo":
        payload = run_demo_service(
            config,
            args.symbol,
            args.instrument_type,
            interval_seconds=args.interval_seconds,
            confirm_demo_order=args.confirm_demo_order,
            order_type=args.order_type,
            cancel_after_place=args.cancel_after_place,
            max_iterations=args.max_iterations,
        )
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    if args.service_command == "run-paper-portfolio":
        payload = run_paper_portfolio_service(
            config,
            args.symbol or config.market.symbols,
            args.instrument_type,
            interval_seconds=args.interval_seconds,
            lookback_bars=args.lookback_bars,
            top_n=args.top_n,
            min_momentum=args.min_momentum,
            allowlist=args.allow_symbol,
            blocklist=args.block_symbol,
            max_turnover_pct=args.max_turnover_pct,
            max_portfolio_drawdown_pct=args.max_portfolio_drawdown_pct,
            max_candle_age_seconds=args.max_candle_age_seconds,
            rebalance_cooldown_seconds=args.rebalance_cooldown_seconds,
            refresh_candles=args.refresh_candles,
            refresh_limit=args.refresh_candles_limit,
            max_iterations=args.max_iterations,
        )
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    if args.service_command == "run-live-portfolio":
        payload = run_live_portfolio_service(
            config,
            args.symbol or config.market.symbols,
            args.instrument_type,
            interval_seconds=args.interval_seconds,
            confirm_live=args.confirm_live,
            lookback_bars=args.lookback_bars,
            top_n=args.top_n,
            min_momentum=args.min_momentum,
            allowlist=args.allow_symbol,
            blocklist=args.block_symbol,
            max_turnover_pct=args.max_turnover_pct,
            max_candle_age_seconds=args.max_candle_age_seconds,
            rebalance_cooldown_seconds=args.rebalance_cooldown_seconds,
            order_type=args.order_type,
            refresh_candles=args.refresh_candles,
            refresh_limit=args.refresh_candles_limit,
            max_iterations=args.max_iterations,
        )
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    if args.service_command == "status":
        print(
            json.dumps(
                {"service": service_status(config), "watchdog": watchdog_status(config)},
                indent=2,
                ensure_ascii=False,
                default=str,
            )
        )
        return 0
    if args.service_command == "recover-paper":
        payload = recover_paper_service(config)
        print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        return 0 if payload.get("status") in {"recovered", "already_running"} else 1
    if args.service_command == "health":
        print(
            json.dumps(
                service_health(
                    config,
                    max_heartbeat_age_seconds=args.max_heartbeat_age_seconds,
                    require_running=args.require_running,
                ),
                indent=2,
                ensure_ascii=False,
                default=str,
            )
        )
        return 0
    if args.service_command == "snapshot":
        path = write_runtime_snapshot_report(
            config,
            config_path=args.config,
            max_heartbeat_age_seconds=args.max_heartbeat_age_seconds,
            require_running=args.require_running,
        )
        print(json.dumps({"report_path": str(path)}, indent=2, ensure_ascii=False))
        return 0
    if args.service_command == "report":
        path = write_service_observation_report(
            config,
            max_heartbeat_age_seconds=args.max_heartbeat_age_seconds,
            require_running=args.require_running,
        )
        print(json.dumps({"report_path": str(path)}, indent=2, ensure_ascii=False))
        return 0
    if args.service_command == "stability":
        path = write_service_stability_report(
            config,
            max_heartbeat_age_seconds=args.max_heartbeat_age_seconds,
            require_running=args.require_running,
            since_hours=args.since_hours,
        )
        print(json.dumps({"report_path": str(path)}, indent=2, ensure_ascii=False))
        return 0
    if args.service_command == "watchdog":
        print(
            json.dumps(
                run_watchdog_service(
                    config,
                    interval_seconds=args.interval_seconds,
                    max_heartbeat_age_seconds=args.max_heartbeat_age_seconds,
                    require_running=not args.no_require_running,
                    trigger_kill_switch=not args.no_kill_switch,
                    stop_service=not args.no_stop_service,
                    max_iterations=args.max_iterations,
                    recover_paper=args.recover_paper,
                ),
                indent=2,
                ensure_ascii=False,
                default=str,
            )
        )
        return 0
    if args.service_command == "acceptance":
        payload = run_unattended_acceptance(
            config,
            args.symbol or config.market.symbols,
            instrument_type=args.instrument_type,
            iterations=args.iterations,
            lookback_bars=args.lookback_bars,
            top_n=args.top_n,
            max_heartbeat_age_seconds=args.max_heartbeat_age_seconds,
            write_report_file=not args.no_report,
        )
        print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        return 0 if payload.get("status") == "passed" else 1
    if args.service_command == "live-gate-drill":
        payload = run_live_gate_drill(config, write_report_file=not args.no_report)
        print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        return 0 if payload.get("status") == "passed" else 1
    if args.service_command == "notification-drill":
        payload = run_notification_drill(config, level=args.level, write_report_file=not args.no_report)
        print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        return 0 if payload.get("status") in {"passed", "local_only"} else 1
    if args.service_command == "pre-live-check":
        payload = run_pre_live_check(
            config,
            min_observation_hours=args.min_observation_hours,
            max_live_cap_usdt=args.max_live_cap_usdt,
            max_leverage=args.max_leverage,
            max_heartbeat_age_seconds=args.max_heartbeat_age_seconds,
            require_running=not args.no_require_running,
            refresh_stability=not args.no_refresh_stability,
            write_report_file=not args.no_report,
        )
        print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        return 0 if payload.get("status") == "passed" else 1
    if args.service_command == "stop":
        print(json.dumps(request_service_stop(config), indent=2, ensure_ascii=False))
        return 0
    raise ValueError(args.service_command)


def command_research(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    config.ensure_dirs()
    if args.research_command == "sweep":
        symbols = args.symbol or config.market.symbols
        selected_strategies = args.strategy or DEFAULT_CANDIDATES
        require_strategy_cards(selected_strategies, allow_unregistered=args.allow_unregistered_strategy)
        require_clean_ohlcv_data(
            config,
            symbols=symbols,
            instrument_types=[args.instrument_type],
            interval=config.market.bar,
            allow_quality_issues=args.allow_quality_issues,
        )
        if args.write_report:
            path = run_strategy_sweep_report(
                config,
                symbols,
                args.instrument_type,
                strategies=selected_strategies,
                start=args.start,
                end=args.end,
            )
            print(json.dumps({"report_path": str(path)}, indent=2, ensure_ascii=False))
        else:
            payload = run_strategy_sweep(
                config,
                symbols,
                args.instrument_type,
                strategies=selected_strategies,
                start=args.start,
                end=args.end,
            )
            print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        return 0
    if args.research_command == "multi-timeframe-sweep":
        symbols = args.symbol or config.market.symbols
        selected_bars = args.bar or [config.market.bar]
        selected_strategies = args.strategy or DEFAULT_CANDIDATES
        require_strategy_cards(selected_strategies, allow_unregistered=args.allow_unregistered_strategy)
        for bar in selected_bars:
            require_clean_ohlcv_data(
                config,
                symbols=symbols,
                instrument_types=[args.instrument_type],
                interval=bar,
                allow_quality_issues=args.allow_quality_issues,
            )
        if args.write_report:
            path = run_multi_timeframe_strategy_sweep_report(
                config,
                symbols,
                args.instrument_type,
                selected_bars,
                strategies=selected_strategies,
                start=args.start,
                end=args.end,
            )
            print(json.dumps({"report_path": str(path)}, indent=2, ensure_ascii=False))
        else:
            payload = run_multi_timeframe_strategy_sweep(
                config,
                symbols,
                args.instrument_type,
                selected_bars,
                strategies=selected_strategies,
                start=args.start,
                end=args.end,
            )
            print(json.dumps(sanitize_for_json(payload), indent=2, ensure_ascii=False, default=str))
        return 0
    if args.research_command == "xsmom":
        symbols = args.symbol or config.market.symbols
        if args.write_report:
            path = run_cross_sectional_momentum_report(
                config,
                symbols,
                args.instrument_type,
                lookback_bars=args.lookback_bars,
                hold_bars=args.hold_bars,
                top_n=args.top_n,
                start=args.start,
                end=args.end,
            )
            print(json.dumps({"report_path": str(path)}, indent=2, ensure_ascii=False))
        else:
            payload = run_cross_sectional_momentum(
                config,
                symbols,
                args.instrument_type,
                lookback_bars=args.lookback_bars,
                hold_bars=args.hold_bars,
                top_n=args.top_n,
                start=args.start,
                end=args.end,
            )
            print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        return 0
    if args.research_command == "xsmom-grid":
        symbols = args.symbol or config.market.symbols
        lookbacks = args.lookback_bars or [24 * 7, 24 * 14, 24 * 30]
        holds = args.hold_bars or [24, 24 * 3, 24 * 7]
        top_ns = args.top_n or [1]
        if args.write_report:
            path = run_cross_sectional_momentum_grid_report(
                config,
                symbols,
                args.instrument_type,
                lookback_bars=lookbacks,
                hold_bars=holds,
                top_n_values=top_ns,
                start=args.start,
                end=args.end,
                min_trades=args.min_trades,
            )
            print(json.dumps({"report_path": str(path)}, indent=2, ensure_ascii=False))
        else:
            payload = run_cross_sectional_momentum_grid(
                config,
                symbols,
                args.instrument_type,
                lookback_bars=lookbacks,
                hold_bars=holds,
                top_n_values=top_ns,
                start=args.start,
                end=args.end,
                min_trades=args.min_trades,
            )
            print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        return 0
    if args.research_command == "xsmom-walk-forward":
        symbols = args.symbol or config.market.symbols
        lookbacks = args.lookback_bars or [24 * 7, 24 * 14, 24 * 30]
        holds = args.hold_bars or [24, 24 * 3, 24 * 7]
        top_ns = args.top_n or [1, 2]
        if args.write_report:
            path = run_cross_sectional_momentum_walk_forward_report(
                config,
                symbols,
                args.instrument_type,
                lookback_bars=lookbacks,
                hold_bars=holds,
                top_n_values=top_ns,
                train_bars=args.train_bars,
                test_bars=args.test_bars,
                step_bars=args.step_bars,
                min_trades=args.min_trades,
            )
            print(json.dumps({"report_path": str(path)}, indent=2, ensure_ascii=False))
        else:
            payload = run_cross_sectional_momentum_walk_forward(
                config,
                symbols,
                args.instrument_type,
                lookback_bars=lookbacks,
                hold_bars=holds,
                top_n_values=top_ns,
                train_bars=args.train_bars,
                test_bars=args.test_bars,
                step_bars=args.step_bars,
                min_trades=args.min_trades,
            )
            print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        return 0
    if args.research_command == "xsmom-costs":
        symbols = args.symbol or config.market.symbols
        fee_rates = args.fee_rate or [config.execution.fee_rate, 0.0015, 0.003]
        slippage_values = args.slippage_bps or [config.execution.slippage_bps, 5.0, 10.0]
        if args.write_report:
            path = run_cross_sectional_momentum_cost_sensitivity_report(
                config,
                symbols,
                args.instrument_type,
                lookback_bars=args.lookback_bars,
                hold_bars=args.hold_bars,
                top_n=args.top_n,
                fee_rates=fee_rates,
                slippage_bps_values=slippage_values,
                start=args.start,
                end=args.end,
            )
            print(json.dumps({"report_path": str(path)}, indent=2, ensure_ascii=False))
        else:
            payload = run_cross_sectional_momentum_cost_sensitivity(
                config,
                symbols,
                args.instrument_type,
                lookback_bars=args.lookback_bars,
                hold_bars=args.hold_bars,
                top_n=args.top_n,
                fee_rates=fee_rates,
                slippage_bps_values=slippage_values,
                start=args.start,
                end=args.end,
            )
            print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        return 0
    if args.research_command == "adaptive-trend":
        symbols = args.symbol or config.market.symbols
        if args.write_report:
            path = run_adaptive_trend_report(
                config,
                symbols,
                args.instrument_type,
                lookback_bars=args.lookback_bars,
                hold_bars=args.hold_bars,
                top_n=args.top_n,
                ema_span=args.ema_span,
                volatility_bars=args.volatility_bars,
                target_volatility=args.target_volatility,
                max_weight=args.max_weight,
                start=args.start,
                end=args.end,
            )
            print(json.dumps({"report_path": str(path)}, indent=2, ensure_ascii=False))
        else:
            payload = run_adaptive_trend(
                config,
                symbols,
                args.instrument_type,
                lookback_bars=args.lookback_bars,
                hold_bars=args.hold_bars,
                top_n=args.top_n,
                ema_span=args.ema_span,
                volatility_bars=args.volatility_bars,
                target_volatility=args.target_volatility,
                max_weight=args.max_weight,
                start=args.start,
                end=args.end,
            )
            print(json.dumps(sanitize_for_json(payload), indent=2, ensure_ascii=False, default=str))
        return 0
    if args.research_command == "adaptive-trend-grid":
        symbols = args.symbol or config.market.symbols
        lookbacks = args.lookback_bars or [24 * 14, 24 * 30]
        holds = args.hold_bars or [24 * 3, 24 * 7]
        top_ns = args.top_n or [1, 2]
        ema_spans = args.ema_span or [24 * 10, 24 * 20]
        volatility_bars = args.volatility_bars or [24 * 7, 24 * 14]
        target_volatilities = args.target_volatility or [0.15, 0.20]
        max_weights = args.max_weight or [0.35, 0.50]
        if args.write_report:
            path = run_adaptive_trend_grid_report(
                config,
                symbols,
                args.instrument_type,
                lookback_bars=lookbacks,
                hold_bars=holds,
                top_n_values=top_ns,
                ema_spans=ema_spans,
                volatility_bars_values=volatility_bars,
                target_volatilities=target_volatilities,
                max_weights=max_weights,
                start=args.start,
                end=args.end,
                min_trades=args.min_trades,
            )
            print(json.dumps({"report_path": str(path)}, indent=2, ensure_ascii=False))
        else:
            payload = run_adaptive_trend_grid(
                config,
                symbols,
                args.instrument_type,
                lookback_bars=lookbacks,
                hold_bars=holds,
                top_n_values=top_ns,
                ema_spans=ema_spans,
                volatility_bars_values=volatility_bars,
                target_volatilities=target_volatilities,
                max_weights=max_weights,
                start=args.start,
                end=args.end,
                min_trades=args.min_trades,
            )
            print(json.dumps(sanitize_for_json(payload), indent=2, ensure_ascii=False, default=str))
        return 0
    if args.research_command == "adaptive-trend-walk-forward":
        symbols = args.symbol or config.market.symbols
        lookbacks = args.lookback_bars or [24 * 14, 24 * 30]
        holds = args.hold_bars or [24 * 3, 24 * 7]
        top_ns = args.top_n or [1, 2]
        ema_spans = args.ema_span or [24 * 10, 24 * 20]
        volatility_bars = args.volatility_bars or [24 * 7, 24 * 14]
        target_volatilities = args.target_volatility or [0.15, 0.20]
        max_weights = args.max_weight or [0.35, 0.50]
        if args.write_report:
            path = run_adaptive_trend_walk_forward_report(
                config,
                symbols,
                args.instrument_type,
                lookback_bars=lookbacks,
                hold_bars=holds,
                top_n_values=top_ns,
                ema_spans=ema_spans,
                volatility_bars_values=volatility_bars,
                target_volatilities=target_volatilities,
                max_weights=max_weights,
                train_bars=args.train_bars,
                test_bars=args.test_bars,
                step_bars=args.step_bars,
                min_trades=args.min_trades,
            )
            print(json.dumps({"report_path": str(path)}, indent=2, ensure_ascii=False))
        else:
            payload = run_adaptive_trend_walk_forward(
                config,
                symbols,
                args.instrument_type,
                lookback_bars=lookbacks,
                hold_bars=holds,
                top_n_values=top_ns,
                ema_spans=ema_spans,
                volatility_bars_values=volatility_bars,
                target_volatilities=target_volatilities,
                max_weights=max_weights,
                train_bars=args.train_bars,
                test_bars=args.test_bars,
                step_bars=args.step_bars,
                min_trades=args.min_trades,
            )
            print(json.dumps(sanitize_for_json(payload), indent=2, ensure_ascii=False, default=str))
        return 0
    if args.research_command == "adaptive-trend-costs":
        symbols = args.symbol or config.market.symbols
        fee_rates = args.fee_rate or [config.execution.fee_rate, 0.0015, 0.003]
        slippage_values = args.slippage_bps or [config.execution.slippage_bps, 5.0, 10.0]
        if args.write_report:
            path = run_adaptive_trend_cost_sensitivity_report(
                config,
                symbols,
                args.instrument_type,
                lookback_bars=args.lookback_bars,
                hold_bars=args.hold_bars,
                top_n=args.top_n,
                ema_span=args.ema_span,
                volatility_bars=args.volatility_bars,
                target_volatility=args.target_volatility,
                max_weight=args.max_weight,
                fee_rates=fee_rates,
                slippage_bps_values=slippage_values,
                start=args.start,
                end=args.end,
            )
            print(json.dumps({"report_path": str(path)}, indent=2, ensure_ascii=False))
        else:
            payload = run_adaptive_trend_cost_sensitivity(
                config,
                symbols,
                args.instrument_type,
                lookback_bars=args.lookback_bars,
                hold_bars=args.hold_bars,
                top_n=args.top_n,
                ema_span=args.ema_span,
                volatility_bars=args.volatility_bars,
                target_volatility=args.target_volatility,
                max_weight=args.max_weight,
                fee_rates=fee_rates,
                slippage_bps_values=slippage_values,
                start=args.start,
                end=args.end,
            )
            print(json.dumps(sanitize_for_json(payload), indent=2, ensure_ascii=False, default=str))
        return 0
    if args.research_command == "btc-eth-cointegration":
        symbols = args.symbol or ["BTC/USDT", "ETH/USDT"]
        if args.write_report:
            path = run_btc_eth_cointegration_pairs_report(
                config,
                symbols,
                instrument_type=args.instrument_type,
                lookback_bars=args.lookback_bars,
                entry_z=args.entry_z,
                exit_z=args.exit_z,
                max_hold_bars=args.max_hold_bars,
                max_gross_exposure=args.max_gross_exposure,
                start=args.start,
                end=args.end,
            )
            print(json.dumps({"report_path": str(path)}, indent=2, ensure_ascii=False))
        else:
            payload = run_btc_eth_cointegration_pairs(
                config,
                symbols,
                instrument_type=args.instrument_type,
                lookback_bars=args.lookback_bars,
                entry_z=args.entry_z,
                exit_z=args.exit_z,
                max_hold_bars=args.max_hold_bars,
                max_gross_exposure=args.max_gross_exposure,
                start=args.start,
                end=args.end,
            )
            print(json.dumps(sanitize_for_json(payload), indent=2, ensure_ascii=False, default=str))
        return 0
    if args.research_command == "funding-carry":
        symbols = args.symbol or config.market.symbols
        if args.write_report:
            path = run_funding_carry_report(
                config,
                symbols,
                lookback_periods=args.lookback_periods,
                hold_periods=args.hold_periods,
                top_n=args.top_n,
                min_funding_rate=args.min_funding_rate,
                max_notional_pct=args.max_notional_pct,
                start=args.start,
                end=args.end,
            )
            print(json.dumps({"report_path": str(path)}, indent=2, ensure_ascii=False))
        else:
            payload = run_funding_carry(
                config,
                symbols,
                lookback_periods=args.lookback_periods,
                hold_periods=args.hold_periods,
                top_n=args.top_n,
                min_funding_rate=args.min_funding_rate,
                max_notional_pct=args.max_notional_pct,
                start=args.start,
                end=args.end,
            )
            print(json.dumps(sanitize_for_json(payload), indent=2, ensure_ascii=False, default=str))
        return 0
    if args.research_command == "funding-carry-grid":
        symbols = args.symbol or config.market.symbols
        lookbacks = args.lookback_periods or [3, 6, 9]
        holds = args.hold_periods or [1, 3]
        top_ns = args.top_n or [1, 2]
        min_rates = args.min_funding_rate or [0.0, 0.00005, 0.0001]
        notionals = args.max_notional_pct or [0.5, 1.0]
        if args.write_report:
            path = run_funding_carry_grid_report(
                config,
                symbols,
                lookback_periods_values=lookbacks,
                hold_periods_values=holds,
                top_n_values=top_ns,
                min_funding_rate_values=min_rates,
                max_notional_pct_values=notionals,
                start=args.start,
                end=args.end,
                min_rebalances=args.min_rebalances,
            )
            print(json.dumps({"report_path": str(path)}, indent=2, ensure_ascii=False))
        else:
            payload = run_funding_carry_grid(
                config,
                symbols,
                lookback_periods_values=lookbacks,
                hold_periods_values=holds,
                top_n_values=top_ns,
                min_funding_rate_values=min_rates,
                max_notional_pct_values=notionals,
                start=args.start,
                end=args.end,
                min_rebalances=args.min_rebalances,
            )
            print(json.dumps(sanitize_for_json(payload), indent=2, ensure_ascii=False, default=str))
        return 0
    if args.research_command == "funding-carry-walk-forward":
        symbols = args.symbol or config.market.symbols
        lookbacks = args.lookback_periods or [3, 6, 9]
        holds = args.hold_periods or [1, 3]
        top_ns = args.top_n or [1, 2]
        min_rates = args.min_funding_rate or [0.0, 0.00005, 0.0001]
        notionals = args.max_notional_pct or [0.5, 1.0]
        if args.write_report:
            path = run_funding_carry_walk_forward_report(
                config,
                symbols,
                lookback_periods_values=lookbacks,
                hold_periods_values=holds,
                top_n_values=top_ns,
                min_funding_rate_values=min_rates,
                max_notional_pct_values=notionals,
                train_periods=args.train_periods,
                test_periods=args.test_periods,
                step_periods=args.step_periods,
                min_rebalances=args.min_rebalances,
            )
            print(json.dumps({"report_path": str(path)}, indent=2, ensure_ascii=False))
        else:
            payload = run_funding_carry_walk_forward(
                config,
                symbols,
                lookback_periods_values=lookbacks,
                hold_periods_values=holds,
                top_n_values=top_ns,
                min_funding_rate_values=min_rates,
                max_notional_pct_values=notionals,
                train_periods=args.train_periods,
                test_periods=args.test_periods,
                step_periods=args.step_periods,
                min_rebalances=args.min_rebalances,
            )
            print(json.dumps(sanitize_for_json(payload), indent=2, ensure_ascii=False, default=str))
        return 0
    if args.research_command == "funding-carry-costs":
        symbols = args.symbol or config.market.symbols
        fee_rates = args.fee_rate or [config.execution.fee_rate, 0.0015, 0.003]
        slippage_values = args.slippage_bps or [config.execution.slippage_bps, 5.0, 10.0]
        if args.write_report:
            path = run_funding_carry_cost_sensitivity_report(
                config,
                symbols,
                lookback_periods=args.lookback_periods,
                hold_periods=args.hold_periods,
                top_n=args.top_n,
                min_funding_rate=args.min_funding_rate,
                max_notional_pct=args.max_notional_pct,
                fee_rates=fee_rates,
                slippage_bps_values=slippage_values,
                start=args.start,
                end=args.end,
            )
            print(json.dumps({"report_path": str(path)}, indent=2, ensure_ascii=False))
        else:
            payload = run_funding_carry_cost_sensitivity(
                config,
                symbols,
                lookback_periods=args.lookback_periods,
                hold_periods=args.hold_periods,
                top_n=args.top_n,
                min_funding_rate=args.min_funding_rate,
                max_notional_pct=args.max_notional_pct,
                fee_rates=fee_rates,
                slippage_bps_values=slippage_values,
                start=args.start,
                end=args.end,
            )
            print(json.dumps(sanitize_for_json(payload), indent=2, ensure_ascii=False, default=str))
        return 0
    if args.research_command == "factor-evaluate":
        symbols = args.symbol or config.market.symbols
        horizons = args.horizon_bars or [1, 6, 24]
        factor_builder = build_factor(args.factor)
        if factor_builder.data_source != "funding":
            require_clean_ohlcv_data(
                config,
                symbols=symbols,
                instrument_types=[args.instrument_type],
                interval=config.market.bar,
                allow_quality_issues=args.allow_quality_issues,
            )
        if args.write_report:
            path = run_factor_evaluation_report(
                config,
                args.factor,
                symbols,
                instrument_type=args.instrument_type,
                horizons=horizons,
                quantiles=args.quantiles,
                min_symbols=args.min_symbols,
                start=args.start,
                end=args.end,
            )
            print(json.dumps({"report_path": str(path)}, indent=2, ensure_ascii=False))
        else:
            payload = run_factor_evaluation(
                config,
                args.factor,
                symbols,
                instrument_type=args.instrument_type,
                horizons=horizons,
                quantiles=args.quantiles,
                min_symbols=args.min_symbols,
                start=args.start,
                end=args.end,
            )
            print(json.dumps(sanitize_for_json(payload), indent=2, ensure_ascii=False, default=str))
        return 0
    if args.research_command == "alpha-ensemble":
        symbols = args.symbol or None
        instrument_type = args.instrument_type
        if symbols:
            require_clean_ohlcv_data(
                config,
                symbols=symbols,
                instrument_types=[instrument_type or config.market.instrument_types[0]],
                interval=config.market.bar,
                allow_quality_issues=args.allow_quality_issues,
            )
        if args.write_report:
            path = run_alpha_ensemble_report(
                config,
                args.spec,
                symbols=symbols,
                instrument_type=instrument_type,
                start=args.start,
                end=args.end,
            )
            print(json.dumps({"report_path": str(path)}, indent=2, ensure_ascii=False))
        else:
            payload = run_alpha_ensemble(
                config,
                args.spec,
                symbols=symbols,
                instrument_type=instrument_type,
                start=args.start,
                end=args.end,
            )
            payload.pop("_ensemble_signal", None)
            payload.pop("_external_factor_values", None)
            print(json.dumps(sanitize_for_json(payload), indent=2, ensure_ascii=False, default=str))
        return 0
    if args.research_command == "shortlist":
        if args.write_report:
            path = strategy_shortlist_report(config)
            print(json.dumps({"report_path": str(path)}, indent=2, ensure_ascii=False))
        else:
            print(json.dumps(sanitize_for_json(strategy_shortlist(config)), indent=2, ensure_ascii=False, default=str))
        return 0
    if args.research_command == "promotion-scorecard":
        if args.write_report:
            path = strategy_promotion_scorecard_report(config)
            print(json.dumps({"report_path": str(path)}, indent=2, ensure_ascii=False))
        else:
            print(json.dumps(sanitize_for_json(strategy_promotion_scorecard(config)), indent=2, ensure_ascii=False, default=str))
        return 0
    if args.research_command == "knowledge-base":
        kb_path = Path(args.path) if args.path else None
        if args.sync_registry and not args.write_report:
            payload = sync_strategy_registry(config, kb_path)
            print(json.dumps(sanitize_for_json(payload), indent=2, ensure_ascii=False, default=str))
        elif args.write_report:
            path = strategy_knowledge_report(config, kb_path)
            print(json.dumps({"report_path": str(path)}, indent=2, ensure_ascii=False))
        else:
            print(json.dumps(sanitize_for_json(strategy_knowledge_summary(config, kb_path)), indent=2, ensure_ascii=False, default=str))
        return 0
    if args.research_command == "scaffold":
        payload = scaffold_strategy_research(
            config,
            strategy_id=args.strategy_id,
            name=args.name,
            family=args.family,
            output_dir=Path(args.output_dir) if args.output_dir else None,
        )
        print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        return 0
    raise ValueError(args.research_command)


def command_kill(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    config.ensure_dirs()
    activate_kill_switch(config, "manual CLI kill switch", source="cli")
    print(f"kill switch active: {config.risk.kill_switch_file}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "data":
        return command_data(args)
    if args.command == "backtest":
        return command_backtest(args)
    if args.command == "paper":
        return command_paper(args)
    if args.command == "live":
        return command_live(args)
    if args.command == "report":
        return command_report(args)
    if args.command == "risk":
        return command_risk(args)
    if args.command == "review":
        return command_review(args)
    if args.command == "okx":
        return command_okx(args)
    if args.command == "service":
        return command_service(args)
    if args.command == "research":
        return command_research(args)
    if args.command == "kill":
        return command_kill(args)
    raise ValueError(args.command)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
