from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Iterable

import pandas as pd

from .backtest import Backtester
from .config import AppConfig
from .data import filter_confirmed_candles, filter_date_range, load_candles, load_funding_rates
from .models import InstrumentType
from .portfolio import load_close_matrix
from .reports import calculate_metrics, calculate_regime_performance, write_report
from .storage import AuditStore


DEFAULT_CANDIDATES = [
    "trend_mr",
    "vol_trend",
    "donchian_breakout",
    "rsi_bollinger_reversion",
    "btc_volatility_breakout",
    "btc_realized_volatility_targeting",
]


PROMOTION_STAGE_ORDER = ["idea", "factor", "strategy", "paper", "small_live"]


def read_latest_report(config: AppConfig, name: str) -> dict[str, object] | None:
    path = config.report_dir / f"{name}_latest.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def strategy_shortlist(config: AppConfig) -> dict[str, object]:
    xsmom_wf = read_latest_report(config, "cross_sectional_momentum_walk_forward")
    xsmom_costs = read_latest_report(config, "cross_sectional_momentum_cost_sensitivity")
    adaptive_wf = read_latest_report(config, "adaptive_trend_walk_forward")
    adaptive_costs = read_latest_report(config, "adaptive_trend_cost_sensitivity")
    funding_wf = read_latest_report(config, "funding_carry_walk_forward")
    funding_costs = read_latest_report(config, "funding_carry_cost_sensitivity")
    service_stability = read_latest_report(config, "service_stability")
    live_gate_drill = read_latest_report(config, "live_gate_drill")
    notification_drill = read_latest_report(config, "notification_drill")

    candidates = [
        summarize_candidate(
            "cross_sectional_momentum",
            "primary_paper_candidate",
            xsmom_wf,
            xsmom_costs,
            "Best current return profile; already wired into paper/live portfolio service.",
        ),
        summarize_candidate(
            "adaptive_trend",
            "low_drawdown_backup",
            adaptive_wf,
            adaptive_costs,
            "Lower return but stronger OOS hit rate and drawdown profile.",
        ),
        summarize_candidate(
            "funding_carry",
            "research_only",
            funding_wf,
            funding_costs,
            "Sample-in strong, but walk-forward stability is weak; keep out of the main trading path.",
        ),
    ]
    ranked = sorted(candidates, key=lambda item: float(item.get("score", 0.0)), reverse=True)
    paper_ready = [item for item in ranked if item.get("decision") in {"primary_paper_candidate", "low_drawdown_backup"}]
    service_summary = service_stability.get("summary", {}) if isinstance(service_stability, dict) else {}
    observation_age = (
        float(service_stability.get("observation_age_seconds", 0.0) or 0.0)
        if isinstance(service_stability, dict)
        else 0.0
    )
    live_gate_passed = isinstance(live_gate_drill, dict) and live_gate_drill.get("status") == "passed"
    webhook_configured = bool(os.environ.get(config.service.notification_webhook_url_env))
    notification_webhook_ok = (
        isinstance(notification_drill, dict)
        and notification_drill.get("live_ready_contribution") is True
    )
    live_blockers = []
    if observation_age < 24 * 3600:
        live_blockers.append("24h+ paper stability window is not complete")
    if int(service_summary.get("failure_event_count") or 0) > 0:
        live_blockers.append("paper service stability report has failure events")
    if not live_gate_passed:
        live_blockers.append("live gate drill has not passed")
    if not webhook_configured:
        live_blockers.append("notification webhook is not configured")
    elif not notification_webhook_ok:
        live_blockers.append("notification webhook drill has not passed")
    live_blockers.append("production live config must still be explicitly enabled by operator")
    return {
        "strategy": "strategy_shortlist",
        "status": "ok" if any(item.get("evidence_complete") for item in candidates) else "missing_evidence",
        "primary": paper_ready[0]["name"] if paper_ready else None,
        "backup": paper_ready[1]["name"] if len(paper_ready) > 1 else None,
        "live_ready": False if live_blockers else True,
        "live_ready_reason": "; ".join(live_blockers) if live_blockers else "all pre-live checks passed",
        "service_stability": {
            "healthy": service_summary.get("healthy"),
            "service_running": service_summary.get("service_running"),
            "watchdog_running": service_summary.get("watchdog_running"),
            "observation_age_seconds": observation_age if isinstance(service_stability, dict) else None,
            "failure_event_count": service_summary.get("failure_event_count"),
        },
        "live_gate_drill": {
            "status": live_gate_drill.get("status") if isinstance(live_gate_drill, dict) else None,
            "check_count": len(live_gate_drill.get("checks", [])) if isinstance(live_gate_drill, dict) else 0,
        },
        "notification_drill": {
            "status": notification_drill.get("status") if isinstance(notification_drill, dict) else None,
            "local_log_ok": notification_drill.get("local_log_ok") if isinstance(notification_drill, dict) else None,
            "webhook_ok": notification_drill.get("webhook_ok") if isinstance(notification_drill, dict) else None,
            "webhook_configured": notification_drill.get("webhook_configured") if isinstance(notification_drill, dict) else None,
            "live_ready_contribution": notification_drill.get("live_ready_contribution")
            if isinstance(notification_drill, dict)
            else None,
        },
        "webhook_configured": webhook_configured,
        "ranked": ranked,
        "recommendations": [
            "Keep cross_sectional_momentum as the active paper-trading strategy.",
            "Keep adaptive_trend as a low-drawdown backup candidate; do not replace the active service until the paper observation window completes.",
            "Do not promote funding_carry to the main path yet; require longer history, walk-forward improvement, and execution/margin validation.",
        ],
    }


def summarize_candidate(
    name: str,
    default_decision: str,
    walk_forward: dict[str, object] | None,
    costs: dict[str, object] | None,
    note: str,
) -> dict[str, object]:
    wf_summary = walk_forward.get("summary", {}) if isinstance(walk_forward, dict) else {}
    cost_summary = costs.get("summary", {}) if isinstance(costs, dict) else {}
    oos_return = float(wf_summary.get("compounded_oos_return", 0.0) or 0.0)
    oos_sharpe = float(wf_summary.get("mean_oos_sharpe", 0.0) or 0.0)
    positive_oos_rate = float(wf_summary.get("positive_oos_fold_rate", 0.0) or 0.0)
    worst_oos_drawdown = float(wf_summary.get("worst_oos_drawdown", 0.0) or 0.0)
    cost_positive_rate = float(cost_summary.get("positive_scenario_rate", 0.0) or 0.0)
    worst_cost_return = float(cost_summary.get("worst_total_return", 0.0) or 0.0)
    evidence_complete = bool(wf_summary) and bool(cost_summary)
    score = (
        oos_return * 2.0
        + max(oos_sharpe, -5.0) * 0.05
        + positive_oos_rate
        + cost_positive_rate
        + min(abs(worst_oos_drawdown), 1.0) * -0.5
    )
    decision = default_decision
    blockers: list[str] = []
    if not evidence_complete:
        decision = "insufficient_evidence"
        blockers.append("missing walk-forward or cost-sensitivity report")
    if positive_oos_rate < 0.6:
        decision = "research_only"
        blockers.append("positive OOS fold rate below 60%")
    if worst_cost_return <= 0:
        decision = "research_only"
        blockers.append("not robust to tested cost scenarios")
    return {
        "name": name,
        "decision": decision,
        "score": score,
        "evidence_complete": evidence_complete,
        "oos": {
            "compounded_return": oos_return,
            "mean_sharpe": oos_sharpe,
            "positive_fold_rate": positive_oos_rate,
            "worst_drawdown": worst_oos_drawdown,
        },
        "costs": {
            "positive_scenario_rate": cost_positive_rate,
            "worst_total_return": worst_cost_return,
            "worst_drawdown": float(cost_summary.get("worst_drawdown", 0.0) or 0.0),
        },
        "blockers": blockers,
        "note": note,
    }


def strategy_shortlist_report(config: AppConfig) -> Path:
    payload = sanitize_for_json(strategy_shortlist(config))
    AuditStore(config.state_dir).insert_strategy_scores(payload)
    return write_report(config.report_dir, "strategy_shortlist", payload)


def strategy_promotion_scorecard(config: AppConfig) -> dict[str, object]:
    shortlist = strategy_shortlist(config)
    live_blockers = [
        item.strip()
        for item in str(shortlist.get("live_ready_reason") or "").split("; ")
        if item.strip() and item.strip() != "all pre-live checks passed"
    ]
    operator_blockers = [
        item for item in live_blockers if "explicitly enabled by operator" in item
    ]
    operational_live_blockers = [item for item in live_blockers if item not in operator_blockers]

    rows = [
        promotion_row(candidate, operational_live_blockers, operator_blockers)
        for candidate in shortlist.get("ranked", [])
        if isinstance(candidate, dict)
    ]
    ranked = sorted(
        rows,
        key=lambda row: (int(row.get("stage_rank", 0)), float(row.get("score", 0.0))),
        reverse=True,
    )
    ready_for_paper = [
        row["name"]
        for row in ranked
        if row.get("stage") in {"paper", "small_live"} and row.get("research_blocker_count") == 0
    ]
    ready_for_small_live = [
        row["name"]
        for row in ranked
        if row.get("stage") == "small_live" and row.get("promotion_status") == "operator_approval_required"
    ]
    blocked = [row["name"] for row in ranked if row.get("promotion_status") == "blocked"]
    return {
        "schema": "strategy_promotion_scorecard_v1",
        "source": "strategy_shortlist",
        "source_status": shortlist.get("status"),
        "stage_order": PROMOTION_STAGE_ORDER,
        "primary": shortlist.get("primary"),
        "backup": shortlist.get("backup"),
        "service_stability": shortlist.get("service_stability"),
        "live_gate_drill": shortlist.get("live_gate_drill"),
        "notification_drill": shortlist.get("notification_drill"),
        "live_blockers": live_blockers,
        "ranked": ranked,
        "summary": {
            "candidate_count": len(ranked),
            "ready_for_paper": ready_for_paper,
            "ready_for_small_live": ready_for_small_live,
            "blocked": blocked,
            "small_live_requires_operator_approval": bool(ready_for_small_live or operator_blockers),
        },
    }


def promotion_row(
    candidate: dict[str, object],
    operational_live_blockers: list[str],
    operator_blockers: list[str],
) -> dict[str, object]:
    score_components = promotion_score_components(candidate)
    evidence_complete = bool(candidate.get("evidence_complete"))
    decision = str(candidate.get("decision") or "insufficient_evidence")
    research_blockers = list(candidate.get("blockers", [])) if isinstance(candidate.get("blockers"), list) else []
    stage = promotion_stage(candidate, decision, evidence_complete, operational_live_blockers)
    stage_rank = PROMOTION_STAGE_ORDER.index(stage) if stage in PROMOTION_STAGE_ORDER else 0
    blockers = list(research_blockers)
    if stage == "paper":
        blockers.extend(operational_live_blockers)
    if stage == "small_live":
        blockers.extend(operator_blockers)
    promotion_status = "blocked" if blockers else "ready_for_paper"
    if stage == "small_live" and operator_blockers:
        promotion_status = "operator_approval_required"
    elif stage == "small_live":
        promotion_status = "ready_for_small_live"
    return {
        "name": candidate.get("name"),
        "decision": decision,
        "stage": stage,
        "stage_rank": stage_rank,
        "promotion_status": promotion_status,
        "score": score_components["total"],
        "score_components": score_components,
        "evidence_complete": evidence_complete,
        "requirements_met": not blockers,
        "research_blocker_count": len(research_blockers),
        "operational_live_blocker_count": len(operational_live_blockers),
        "operator_approval_required": bool(operator_blockers),
        "blockers": blockers,
        "oos": candidate.get("oos", {}),
        "costs": candidate.get("costs", {}),
        "note": candidate.get("note", ""),
    }


def promotion_stage(
    candidate: dict[str, object],
    decision: str,
    evidence_complete: bool,
    operational_live_blockers: list[str],
) -> str:
    if not evidence_complete:
        return "idea"
    if decision in {"insufficient_evidence", "research_only"}:
        return "strategy"
    if decision in {"primary_paper_candidate", "low_drawdown_backup"}:
        return "paper" if operational_live_blockers else "small_live"
    if float(candidate.get("score", 0.0) or 0.0) > 0:
        return "factor"
    return "idea"


def promotion_score_components(candidate: dict[str, object]) -> dict[str, float]:
    oos = candidate.get("oos", {}) if isinstance(candidate.get("oos"), dict) else {}
    costs = candidate.get("costs", {}) if isinstance(candidate.get("costs"), dict) else {}
    oos_return = float(oos.get("compounded_return", 0.0) or 0.0)
    mean_sharpe = float(oos.get("mean_sharpe", 0.0) or 0.0)
    positive_fold_rate = float(oos.get("positive_fold_rate", 0.0) or 0.0)
    worst_drawdown = abs(float(oos.get("worst_drawdown", 0.0) or 0.0))
    cost_positive_rate = float(costs.get("positive_scenario_rate", 0.0) or 0.0)
    worst_cost_return = float(costs.get("worst_total_return", 0.0) or 0.0)
    evidence = 10.0 if bool(candidate.get("evidence_complete")) else 0.0
    return_component = _bounded_score(oos_return, target=0.30, weight=20.0)
    sharpe_component = _bounded_score(mean_sharpe, target=2.0, weight=20.0)
    stability_component = max(0.0, min(positive_fold_rate, 1.0)) * 20.0
    cost_component = max(0.0, min(cost_positive_rate, 1.0)) * 15.0 + _bounded_score(
        worst_cost_return,
        target=0.10,
        weight=5.0,
    )
    drawdown_component = max(0.0, 1.0 - min(worst_drawdown / 0.25, 1.0)) * 10.0
    total = evidence + return_component + sharpe_component + stability_component + cost_component + drawdown_component
    return {
        "evidence": round(evidence, 4),
        "return": round(return_component, 4),
        "sharpe": round(sharpe_component, 4),
        "stability": round(stability_component, 4),
        "cost": round(cost_component, 4),
        "drawdown": round(drawdown_component, 4),
        "total": round(total, 4),
    }


def _bounded_score(value: float, *, target: float, weight: float) -> float:
    if target == 0:
        return 0.0
    return max(-weight, min(value / target, 1.0)) * weight


def strategy_promotion_scorecard_report(config: AppConfig) -> Path:
    payload = sanitize_for_json(strategy_promotion_scorecard(config))
    AuditStore(config.state_dir).insert_strategy_scores(payload)
    return write_report(config.report_dir, "strategy_promotion_scorecard", payload)


def run_strategy_sweep(
    config: AppConfig,
    symbols: Iterable[str],
    instrument_type: str,
    strategies: Iterable[str] | None = None,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    selected_strategies = list(strategies or DEFAULT_CANDIDATES)
    bar = config.market.bar
    for symbol in symbols:
        candles = filter_date_range(load_candles(config, symbol, instrument_type), start, end)
        if candles.empty:
            rows.append({"symbol": symbol, "instrument_type": instrument_type, "bar": bar, "status": "missing_data"})
            continue
        for strategy_name in selected_strategies:
            cfg = config.model_copy(deep=True)
            cfg.strategy.name = strategy_name
            result = Backtester(cfg).run(candles, symbol, InstrumentType(instrument_type))
            metrics = result["metrics"]
            rows.append(
                {
                    "symbol": symbol,
                    "instrument_type": instrument_type,
                    "bar": bar,
                    "strategy": strategy_name,
                    "status": "ok",
                    **metrics,
                }
            )
    ranked = sorted(
        [row for row in rows if row.get("status") == "ok"],
        key=lambda row: (float(row.get("sharpe", 0)), float(row.get("total_return", 0))),
        reverse=True,
    )
    return {
        "candidates": selected_strategies,
        "instrument_type": instrument_type,
        "bar": bar,
        "rows": rows,
        "ranked": ranked,
        "aggregate": aggregate_strategy_scores(rows),
        "best": ranked[0] if ranked else None,
    }


def run_multi_timeframe_strategy_sweep(
    config: AppConfig,
    symbols: Iterable[str],
    instrument_type: str,
    bars: Iterable[str],
    strategies: Iterable[str] | None = None,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, object]:
    selected_bars = list(bars) or [config.market.bar]
    selected_symbols = list(symbols)
    selected_strategies = list(strategies or DEFAULT_CANDIDATES)
    timeframe_reports: list[dict[str, object]] = []
    rows: list[dict[str, object]] = []
    for bar in selected_bars:
        cfg = config.model_copy(deep=True)
        cfg.market.bar = bar
        payload = run_strategy_sweep(
            cfg,
            selected_symbols,
            instrument_type,
            strategies=selected_strategies,
            start=start,
            end=end,
        )
        timeframe_reports.append(
            {
                "bar": bar,
                "best": payload.get("best"),
                "aggregate": payload.get("aggregate", []),
                "row_count": len(payload.get("rows", [])) if isinstance(payload.get("rows"), list) else 0,
            }
        )
        if isinstance(payload.get("rows"), list):
            rows.extend(payload["rows"])
    ranked = sorted(
        [row for row in rows if row.get("status") == "ok"],
        key=lambda row: (float(row.get("sharpe", 0)), float(row.get("total_return", 0))),
        reverse=True,
    )
    aggregate = aggregate_strategy_scores(rows)
    for item in aggregate:
        strategy_rows = [
            row
            for row in rows
            if row.get("status") == "ok" and row.get("strategy") == item.get("strategy")
        ]
        item["timeframe_count"] = len({row.get("bar") for row in strategy_rows})
        item["symbol_count"] = len({row.get("symbol") for row in strategy_rows})
    return {
        "schema": "multi_timeframe_strategy_sweep_v1",
        "instrument_type": instrument_type,
        "bars": selected_bars,
        "symbols": selected_symbols,
        "candidates": selected_strategies,
        "timeframes": timeframe_reports,
        "rows": rows,
        "ranked": ranked,
        "aggregate": aggregate,
        "best": ranked[0] if ranked else None,
    }


def load_funding_matrix(
    config: AppConfig,
    symbols: Iterable[str],
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame:
    series: dict[str, pd.Series] = {}
    for symbol in symbols:
        df = load_funding_rates(config, symbol)
        if df.empty:
            continue
        df = df.sort_values("ts").drop_duplicates("ts")
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
        if start:
            df = df[df["ts"] >= pd.to_datetime(start, utc=True)]
        if end:
            df = df[df["ts"] <= pd.to_datetime(end, utc=True)]
        if not df.empty:
            series[symbol] = df.set_index("ts")["funding_rate"].astype(float).rename(symbol)
    if not series:
        return pd.DataFrame()
    return pd.concat(series.values(), axis=1).dropna(how="all").sort_index()


def run_funding_carry(
    config: AppConfig,
    symbols: Iterable[str],
    lookback_periods: int = 3,
    hold_periods: int = 1,
    top_n: int = 2,
    min_funding_rate: float = 0.0,
    max_notional_pct: float = 1.0,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, object]:
    symbol_list = list(symbols)
    funding = load_funding_matrix(config, symbol_list, start=start, end=end)
    if funding.empty:
        return {"strategy": "funding_carry", "status": "missing_data", "symbols": symbol_list}
    if len(funding) <= lookback_periods + hold_periods:
        return {
            "strategy": "funding_carry",
            "status": "insufficient_history",
            "symbols": symbol_list,
            "bars": len(funding),
            "required_bars": lookback_periods + hold_periods + 1,
        }

    equity = config.backtest.initial_cash
    selected: list[str] = []
    weights: dict[str, float] = {}
    equity_rows: list[dict[str, object]] = []
    trade_rows: list[dict[str, object]] = []
    two_leg_cost_rate = 2 * (config.execution.fee_rate + config.execution.slippage_bps / 10_000)

    for idx in range(lookback_periods, len(funding), hold_periods):
        now = funding.index[idx]
        score = funding.iloc[idx - lookback_periods : idx].mean(skipna=True)
        ranked = score.dropna().sort_values(ascending=False)
        next_selected = [
            symbol
            for symbol, value in ranked.head(max(top_n, 1)).items()
            if float(value) > min_funding_rate
        ]
        next_weights = {
            symbol: max_notional_pct / len(next_selected)
            for symbol in next_selected
        } if next_selected else {}
        changed_symbols = set(selected).symmetric_difference(next_selected)
        turnover_weight = sum(weights.get(symbol, 0.0) for symbol in changed_symbols) + sum(
            next_weights.get(symbol, 0.0) for symbol in changed_symbols
        )
        if turnover_weight > 0:
            cost = equity * turnover_weight * two_leg_cost_rate
            equity -= cost
            trade_rows.append(
                {
                    "ts": now,
                    "symbol": ",".join(sorted(changed_symbols)),
                    "side": "rebalance",
                    "quantity": turnover_weight,
                    "price": 1.0,
                    "realized_pnl": -cost,
                }
            )
        selected = next_selected
        weights = next_weights

        period_rates = funding.iloc[idx : min(idx + hold_periods, len(funding))]
        funding_pnl = 0.0
        for _, row in period_rates.iterrows():
            for symbol, weight in weights.items():
                rate = row.get(symbol)
                if pd.notna(rate):
                    funding_pnl += equity * weight * float(rate)
        equity += funding_pnl
        equity_rows.append(
            {
                "ts": now,
                "equity": equity,
                "selected": selected,
                "rank": ranked.to_dict(),
                "funding_pnl": funding_pnl,
                "turnover_weight": turnover_weight,
            }
        )

    equity_curve = pd.DataFrame(equity_rows)
    trades = pd.DataFrame(trade_rows)
    funding_pnls = [float(row.get("funding_pnl", 0.0)) for row in equity_rows]
    return {
        "strategy": "funding_carry",
        "status": "ok",
        "symbols": symbol_list,
        "parameters": {
            "lookback_periods": lookback_periods,
            "hold_periods": hold_periods,
            "top_n": top_n,
            "min_funding_rate": min_funding_rate,
            "max_notional_pct": max_notional_pct,
        },
        "metrics": calculate_metrics(equity_curve, trades),
        "carry_stats": {
            "funding_period_count": len(equity_rows),
            "positive_funding_period_rate": sum(1 for value in funding_pnls if value > 0) / len(funding_pnls)
            if funding_pnls
            else 0.0,
            "total_funding_pnl": sum(funding_pnls),
            "average_funding_pnl": sum(funding_pnls) / len(funding_pnls) if funding_pnls else 0.0,
            "rebalance_count": len(trade_rows),
        },
        "equity_curve_tail": equity_curve.tail(20).to_dict("records"),
        "trades": trades.to_dict("records"),
    }


def run_funding_carry_report(
    config: AppConfig,
    symbols: Iterable[str],
    lookback_periods: int = 3,
    hold_periods: int = 1,
    top_n: int = 2,
    min_funding_rate: float = 0.0,
    max_notional_pct: float = 1.0,
    start: str | None = None,
    end: str | None = None,
) -> Path:
    payload = run_funding_carry(
        config,
        symbols,
        lookback_periods=lookback_periods,
        hold_periods=hold_periods,
        top_n=top_n,
        min_funding_rate=min_funding_rate,
        max_notional_pct=max_notional_pct,
        start=start,
        end=end,
    )
    return write_report(config.report_dir, "funding_carry", sanitize_for_json(payload))


def load_pair_ohlc(
    config: AppConfig,
    base_symbol: str,
    hedge_symbol: str,
    instrument_type: str,
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for prefix, symbol in [("base", base_symbol), ("hedge", hedge_symbol)]:
        candles = filter_confirmed_candles(load_candles(config, symbol, instrument_type), require_confirmed=True)
        candles = filter_date_range(candles, start, end)
        if candles.empty:
            continue
        frames.append(
            candles[["ts", "open", "close"]]
            .rename(columns={"open": f"{prefix}_open", "close": f"{prefix}_close"})
            .set_index("ts")
        )
    if len(frames) != 2:
        return pd.DataFrame()
    return pd.concat(frames, axis=1).dropna().sort_index()


def pair_regime_performance(equity_curve: pd.DataFrame, pair_ohlc: pd.DataFrame) -> dict[str, object]:
    if pair_ohlc.empty:
        return {}
    base_candles = pair_ohlc.reset_index()[["ts", "base_close"]].rename(columns={"base_close": "close"})
    return calculate_regime_performance(equity_curve, base_candles)


def run_btc_eth_cointegration_pairs(
    config: AppConfig,
    symbols: Iterable[str],
    instrument_type: str = "spot",
    lookback_bars: int = 24 * 30,
    entry_z: float = 2.0,
    exit_z: float = 0.5,
    max_hold_bars: int = 24 * 7,
    max_gross_exposure: float = 0.50,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, object]:
    symbol_list = list(symbols)
    base_symbol = symbol_list[0] if symbol_list else "BTC/USDT"
    hedge_symbol = symbol_list[1] if len(symbol_list) > 1 else "ETH/USDT"
    pair = load_pair_ohlc(config, base_symbol, hedge_symbol, instrument_type, start=start, end=end)
    required_bars = lookback_bars + max_hold_bars + 2
    if pair.empty:
        return {
            "strategy": "btc_eth_cointegration_pairs",
            "status": "missing_data",
            "symbols": [base_symbol, hedge_symbol],
            "instrument_type": instrument_type,
        }
    if len(pair) < required_bars:
        return {
            "strategy": "btc_eth_cointegration_pairs",
            "status": "insufficient_history",
            "symbols": [base_symbol, hedge_symbol],
            "instrument_type": instrument_type,
            "bars": len(pair),
            "required_bars": required_bars,
        }

    log_base = pair["base_close"].astype(float).map(math.log)
    log_hedge = pair["hedge_close"].astype(float).map(math.log)
    rolling_cov = log_base.rolling(lookback_bars).cov(log_hedge)
    rolling_var = log_hedge.rolling(lookback_bars).var().replace(0.0, float("nan"))
    hedge_ratio = (rolling_cov / rolling_var).fillna(1.0).clip(lower=0.1, upper=5.0)
    spread = log_base - hedge_ratio * log_hedge
    spread_mean = spread.rolling(lookback_bars).mean()
    spread_std = spread.rolling(lookback_bars).std().replace(0.0, float("nan"))
    zscore = ((spread - spread_mean) / spread_std).fillna(0.0)

    fee_slippage_rate = config.execution.fee_rate + config.execution.slippage_bps / 10_000
    equity = config.backtest.initial_cash
    current_side = 0
    current_weights = {"base": 0.0, "hedge": 0.0}
    entry_exec_idx: int | None = None
    entry_equity = equity
    equity_rows = [{"ts": pair.index[lookback_bars + 1], "equity": equity, "side": current_side}]
    trade_rows: list[dict[str, object]] = []

    for signal_idx in range(lookback_bars, len(pair) - 1):
        exec_idx = signal_idx + 1
        signal_ts = pair.index[signal_idx]
        exec_ts = pair.index[exec_idx]
        z_value = float(zscore.iloc[signal_idx])
        beta = max(float(hedge_ratio.iloc[signal_idx]), 0.1)
        next_side = current_side
        holding_bars = signal_idx - entry_exec_idx + 1 if entry_exec_idx is not None else 0
        if current_side == 0:
            if z_value >= entry_z:
                next_side = -1
            elif z_value <= -entry_z:
                next_side = 1
        elif abs(z_value) <= exit_z or holding_bars >= max_hold_bars:
            next_side = 0

        denominator = 1.0 + beta
        next_weights = {
            "base": next_side * max_gross_exposure / denominator,
            "hedge": -next_side * max_gross_exposure * beta / denominator,
        }
        turnover = abs(next_weights["base"] - current_weights["base"]) + abs(
            next_weights["hedge"] - current_weights["hedge"]
        )
        if turnover > 0:
            equity -= equity * turnover * fee_slippage_rate
            if current_side != 0 and (next_side == 0 or next_side != current_side):
                trade_rows.append(
                    {
                        "ts": exec_ts,
                        "signal_ts": signal_ts,
                        "execution_ts": exec_ts,
                        "execution_price_source": "next_bar_open",
                        "symbol": f"{base_symbol}/{hedge_symbol}",
                        "side": "exit" if next_side == 0 else "reverse",
                        "quantity": turnover,
                        "price": 1.0,
                        "realized_pnl": equity - entry_equity,
                        "zscore": z_value,
                        "hedge_ratio": beta,
                    }
                )
            if next_side != 0 and next_side != current_side:
                entry_exec_idx = exec_idx
                entry_equity = equity
                trade_rows.append(
                    {
                        "ts": exec_ts,
                        "signal_ts": signal_ts,
                        "execution_ts": exec_ts,
                        "execution_price_source": "next_bar_open",
                        "symbol": f"{base_symbol}/{hedge_symbol}",
                        "side": "long_spread" if next_side > 0 else "short_spread",
                        "quantity": turnover,
                        "price": 1.0,
                        "realized_pnl": 0.0,
                        "zscore": z_value,
                        "hedge_ratio": beta,
                    }
                )
            elif next_side != 0:
                trade_rows.append(
                    {
                        "ts": exec_ts,
                        "signal_ts": signal_ts,
                        "execution_ts": exec_ts,
                        "execution_price_source": "next_bar_open",
                        "symbol": f"{base_symbol}/{hedge_symbol}",
                        "side": "rebalance",
                        "quantity": turnover,
                        "price": 1.0,
                        "realized_pnl": 0.0,
                        "zscore": z_value,
                        "hedge_ratio": beta,
                    }
                )
            elif next_side == 0:
                entry_exec_idx = None
            current_side = next_side
            current_weights = next_weights

        if exec_idx + 1 >= len(pair):
            continue
        base_return = float(pair["base_open"].iloc[exec_idx + 1] / pair["base_open"].iloc[exec_idx] - 1.0)
        hedge_return = float(pair["hedge_open"].iloc[exec_idx + 1] / pair["hedge_open"].iloc[exec_idx] - 1.0)
        portfolio_return = current_weights["base"] * base_return + current_weights["hedge"] * hedge_return
        equity *= 1.0 + portfolio_return
        equity_rows.append(
            {
                "ts": pair.index[exec_idx + 1],
                "equity": equity,
                "side": current_side,
                "zscore": z_value,
                "hedge_ratio": beta,
            }
        )

    if current_side != 0:
        final_ts = pair.index[-1]
        equity -= equity * (abs(current_weights["base"]) + abs(current_weights["hedge"])) * fee_slippage_rate
        trade_rows.append(
            {
                "ts": final_ts,
                "execution_ts": final_ts,
                "execution_price_source": "final_open_closeout",
                "symbol": f"{base_symbol}/{hedge_symbol}",
                "side": "exit",
                "quantity": abs(current_weights["base"]) + abs(current_weights["hedge"]),
                "price": 1.0,
                "realized_pnl": equity - entry_equity,
                "zscore": float(zscore.iloc[-1]),
                "hedge_ratio": float(hedge_ratio.iloc[-1]),
            }
        )
        equity_rows.append({"ts": final_ts, "equity": equity, "side": 0})

    equity_curve = pd.DataFrame(equity_rows).drop_duplicates("ts", keep="last")
    trades = pd.DataFrame(trade_rows)
    return {
        "strategy": "btc_eth_cointegration_pairs",
        "status": "ok",
        "symbols": [base_symbol, hedge_symbol],
        "instrument_type": instrument_type,
        "confirmed_only": True,
        "execution_model": "next_bar_open",
        "parameters": {
            "lookback_bars": lookback_bars,
            "entry_z": entry_z,
            "exit_z": exit_z,
            "max_hold_bars": max_hold_bars,
            "max_gross_exposure": max_gross_exposure,
        },
        "metrics": calculate_metrics(equity_curve, trades),
        "regime_performance": pair_regime_performance(equity_curve, pair),
        "pair_stats": {
            "bars": len(pair),
            "mean_abs_zscore": float(zscore.abs().mean()),
            "latest_zscore": float(zscore.iloc[-1]),
            "latest_hedge_ratio": float(hedge_ratio.iloc[-1]),
            "entry_count": sum(1 for row in trade_rows if row.get("side") in {"long_spread", "short_spread"}),
            "closed_trade_count": sum(1 for row in trade_rows if row.get("realized_pnl", 0.0) != 0.0),
        },
        "strengths": [
            "Uses a rolling hedge ratio instead of fixed BTC/ETH beta.",
            "Dollar-neutral spread exposure reduces broad crypto market beta.",
            "Signals are generated from confirmed closed bars and executed on next-bar opens.",
        ],
        "weaknesses": [
            "No formal p-value gate is implemented yet; hedge stability is approximated by rolling beta and z-score.",
            "Short/borrow and margin constraints are represented by costs but not exchange-specific borrow availability.",
            "BTC/ETH relationship can structurally break during regime shifts.",
        ],
        "recommendation": "Keep as a reproducible research strategy; add walk-forward and cointegration stability gates before paper/live consideration.",
        "equity_curve_tail": equity_curve.tail(20).to_dict("records"),
        "trades": trades.to_dict("records"),
    }


def run_btc_eth_cointegration_pairs_report(
    config: AppConfig,
    symbols: Iterable[str],
    instrument_type: str = "spot",
    lookback_bars: int = 24 * 30,
    entry_z: float = 2.0,
    exit_z: float = 0.5,
    max_hold_bars: int = 24 * 7,
    max_gross_exposure: float = 0.50,
    start: str | None = None,
    end: str | None = None,
) -> Path:
    payload = run_btc_eth_cointegration_pairs(
        config,
        symbols,
        instrument_type=instrument_type,
        lookback_bars=lookback_bars,
        entry_z=entry_z,
        exit_z=exit_z,
        max_hold_bars=max_hold_bars,
        max_gross_exposure=max_gross_exposure,
        start=start,
        end=end,
    )
    return write_report(config.report_dir, "btc_eth_cointegration_pairs", sanitize_for_json(payload))


def run_funding_carry_grid(
    config: AppConfig,
    symbols: Iterable[str],
    lookback_periods_values: Iterable[int],
    hold_periods_values: Iterable[int],
    top_n_values: Iterable[int],
    min_funding_rate_values: Iterable[float],
    max_notional_pct_values: Iterable[float],
    start: str | None = None,
    end: str | None = None,
    min_rebalances: int = 6,
) -> dict[str, object]:
    symbol_list = list(symbols)
    lookback_list = list(lookback_periods_values)
    hold_list = list(hold_periods_values)
    top_n_list = list(top_n_values)
    min_rate_list = list(min_funding_rate_values)
    notional_list = list(max_notional_pct_values)
    rows: list[dict[str, object]] = []

    for lookback in lookback_list:
        for hold in hold_list:
            for top_n in top_n_list:
                for min_rate in min_rate_list:
                    for notional in notional_list:
                        result = run_funding_carry(
                            config,
                            symbol_list,
                            lookback_periods=lookback,
                            hold_periods=hold,
                            top_n=top_n,
                            min_funding_rate=min_rate,
                            max_notional_pct=notional,
                            start=start,
                            end=end,
                        )
                        metrics = result.get("metrics", {}) if result.get("status") == "ok" else {}
                        carry_stats = result.get("carry_stats", {}) if result.get("status") == "ok" else {}
                        rows.append(
                            {
                                "strategy": "funding_carry",
                                "status": result.get("status"),
                                "symbols_tested": len(result.get("symbols", [])),
                                "lookback_periods": lookback,
                                "hold_periods": hold,
                                "top_n": top_n,
                                "min_funding_rate": min_rate,
                                "max_notional_pct": notional,
                                **metrics,
                                "funding_period_count": carry_stats.get("funding_period_count"),
                                "positive_funding_period_rate": carry_stats.get("positive_funding_period_rate"),
                                "total_funding_pnl": carry_stats.get("total_funding_pnl"),
                                "rebalance_count": carry_stats.get("rebalance_count"),
                            }
                        )

    ranked = sorted(
        [
            row
            for row in rows
            if row.get("status") == "ok" and int(row.get("rebalance_count") or 0) >= min_rebalances
        ],
        key=lambda row: (
            float(row.get("sharpe", 0)),
            float(row.get("total_return", 0)),
            -abs(float(row.get("max_drawdown", 0))),
        ),
        reverse=True,
    )
    return {
        "strategy": "funding_carry_grid",
        "symbols": symbol_list,
        "parameters": {
            "lookback_periods": lookback_list,
            "hold_periods": hold_list,
            "top_n": top_n_list,
            "min_funding_rate": min_rate_list,
            "max_notional_pct": notional_list,
            "min_rebalances": min_rebalances,
        },
        "rows": rows,
        "ranked": ranked,
        "best": ranked[0] if ranked else None,
        "parameter_stability": parameter_stability_summary(
            rows,
            ["lookback_periods", "hold_periods", "top_n", "min_funding_rate", "max_notional_pct"],
            min_trades=min_rebalances,
        ),
        "overfitting_diagnostics": overfitting_diagnostics(
            rows,
            ["lookback_periods", "hold_periods", "top_n", "min_funding_rate", "max_notional_pct"],
            min_trades=min_rebalances,
        ),
    }


def run_funding_carry_grid_report(
    config: AppConfig,
    symbols: Iterable[str],
    lookback_periods_values: Iterable[int],
    hold_periods_values: Iterable[int],
    top_n_values: Iterable[int],
    min_funding_rate_values: Iterable[float],
    max_notional_pct_values: Iterable[float],
    start: str | None = None,
    end: str | None = None,
    min_rebalances: int = 6,
) -> Path:
    payload = run_funding_carry_grid(
        config,
        symbols,
        lookback_periods_values=lookback_periods_values,
        hold_periods_values=hold_periods_values,
        top_n_values=top_n_values,
        min_funding_rate_values=min_funding_rate_values,
        max_notional_pct_values=max_notional_pct_values,
        start=start,
        end=end,
        min_rebalances=min_rebalances,
    )
    return write_report(config.report_dir, "funding_carry_grid", sanitize_for_json(payload))


def run_funding_carry_walk_forward(
    config: AppConfig,
    symbols: Iterable[str],
    lookback_periods_values: Iterable[int],
    hold_periods_values: Iterable[int],
    top_n_values: Iterable[int],
    min_funding_rate_values: Iterable[float],
    max_notional_pct_values: Iterable[float],
    train_periods: int = 360,
    test_periods: int = 90,
    step_periods: int | None = None,
    min_rebalances: int = 4,
) -> dict[str, object]:
    symbol_list = list(symbols)
    lookback_list = list(lookback_periods_values)
    hold_list = list(hold_periods_values)
    top_n_list = list(top_n_values)
    min_rate_list = list(min_funding_rate_values)
    notional_list = list(max_notional_pct_values)
    funding = load_funding_matrix(config, symbol_list)
    if funding.empty:
        return {"strategy": "funding_carry_walk_forward", "status": "missing_data", "symbols": symbol_list}

    step = step_periods or test_periods
    folds: list[dict[str, object]] = []
    fold_index = 0
    start_idx = 0
    while start_idx + train_periods + test_periods <= len(funding):
        train_start = funding.index[start_idx]
        train_end = funding.index[start_idx + train_periods - 1]
        test_start = funding.index[start_idx + train_periods]
        test_end = funding.index[start_idx + train_periods + test_periods - 1]
        train = run_funding_carry_grid(
            config,
            symbol_list,
            lookback_periods_values=lookback_list,
            hold_periods_values=hold_list,
            top_n_values=top_n_list,
            min_funding_rate_values=min_rate_list,
            max_notional_pct_values=notional_list,
            start=str(train_start),
            end=str(train_end),
            min_rebalances=min_rebalances,
        )
        best = train.get("best")
        if not best:
            folds.append(
                {
                    "fold": fold_index,
                    "status": "no_train_candidate",
                    "train_start": str(train_start),
                    "train_end": str(train_end),
                    "test_start": str(test_start),
                    "test_end": str(test_end),
                }
            )
        else:
            warmup = int(best["lookback_periods"])
            test_data_start_idx = max(start_idx + train_periods - warmup, 0)
            test_data_start = funding.index[test_data_start_idx]
            test = run_funding_carry(
                config,
                symbol_list,
                lookback_periods=int(best["lookback_periods"]),
                hold_periods=int(best["hold_periods"]),
                top_n=int(best["top_n"]),
                min_funding_rate=float(best["min_funding_rate"]),
                max_notional_pct=float(best["max_notional_pct"]),
                start=str(test_data_start),
                end=str(test_end),
            )
            metrics = test.get("metrics", {}) if test.get("status") == "ok" else {}
            carry_stats = test.get("carry_stats", {}) if test.get("status") == "ok" else {}
            folds.append(
                {
                    "fold": fold_index,
                    "status": test.get("status"),
                    "train_start": str(train_start),
                    "train_end": str(train_end),
                    "test_start": str(test_start),
                    "test_end": str(test_end),
                    "test_data_start": str(test_data_start),
                    "selected_params": {
                        "lookback_periods": best["lookback_periods"],
                        "hold_periods": best["hold_periods"],
                        "top_n": best["top_n"],
                        "min_funding_rate": best["min_funding_rate"],
                        "max_notional_pct": best["max_notional_pct"],
                    },
                    "train_metrics": {
                        "total_return": best.get("total_return"),
                        "max_drawdown": best.get("max_drawdown"),
                        "sharpe": best.get("sharpe"),
                        "rebalance_count": best.get("rebalance_count"),
                    },
                    "test_metrics": metrics,
                    "test_carry_stats": carry_stats,
                }
            )
        fold_index += 1
        start_idx += step

    summary = walk_forward_summary(
        folds,
        ["lookback_periods", "hold_periods", "top_n", "min_funding_rate", "max_notional_pct"],
        activity_metric="rebalance_count",
    )
    ok_folds = [fold for fold in folds if fold.get("status") == "ok" and fold.get("test_metrics")]
    summary["total_oos_rebalances"] = sum(
        int(fold["test_carry_stats"].get("rebalance_count", 0)) for fold in ok_folds
    )
    return {
        "strategy": "funding_carry_walk_forward",
        "status": "ok" if ok_folds else "no_ok_folds",
        "symbols": symbol_list,
        "bars": len(funding),
        "parameters": {
            "lookback_periods": lookback_list,
            "hold_periods": hold_list,
            "top_n": top_n_list,
            "min_funding_rate": min_rate_list,
            "max_notional_pct": notional_list,
            "train_periods": train_periods,
            "test_periods": test_periods,
            "step_periods": step,
            "min_rebalances": min_rebalances,
        },
        "summary": summary,
        "folds": folds,
    }


def run_funding_carry_walk_forward_report(
    config: AppConfig,
    symbols: Iterable[str],
    lookback_periods_values: Iterable[int],
    hold_periods_values: Iterable[int],
    top_n_values: Iterable[int],
    min_funding_rate_values: Iterable[float],
    max_notional_pct_values: Iterable[float],
    train_periods: int = 360,
    test_periods: int = 90,
    step_periods: int | None = None,
    min_rebalances: int = 4,
) -> Path:
    payload = run_funding_carry_walk_forward(
        config,
        symbols,
        lookback_periods_values=lookback_periods_values,
        hold_periods_values=hold_periods_values,
        top_n_values=top_n_values,
        min_funding_rate_values=min_funding_rate_values,
        max_notional_pct_values=max_notional_pct_values,
        train_periods=train_periods,
        test_periods=test_periods,
        step_periods=step_periods,
        min_rebalances=min_rebalances,
    )
    return write_report(config.report_dir, "funding_carry_walk_forward", sanitize_for_json(payload))


def run_funding_carry_cost_sensitivity(
    config: AppConfig,
    symbols: Iterable[str],
    lookback_periods: int,
    hold_periods: int,
    top_n: int,
    min_funding_rate: float,
    max_notional_pct: float,
    fee_rates: Iterable[float],
    slippage_bps_values: Iterable[float],
    start: str | None = None,
    end: str | None = None,
) -> dict[str, object]:
    symbol_list = list(symbols)
    fee_list = list(fee_rates)
    slippage_list = list(slippage_bps_values)
    rows: list[dict[str, object]] = []
    for fee_rate in fee_list:
        for slippage_bps in slippage_list:
            cfg = config.model_copy(deep=True)
            cfg.execution.fee_rate = fee_rate
            cfg.execution.slippage_bps = slippage_bps
            result = run_funding_carry(
                cfg,
                symbol_list,
                lookback_periods=lookback_periods,
                hold_periods=hold_periods,
                top_n=top_n,
                min_funding_rate=min_funding_rate,
                max_notional_pct=max_notional_pct,
                start=start,
                end=end,
            )
            metrics = result.get("metrics", {}) if result.get("status") == "ok" else {}
            carry_stats = result.get("carry_stats", {}) if result.get("status") == "ok" else {}
            rows.append(
                {
                    "status": result.get("status"),
                    "fee_rate": fee_rate,
                    "slippage_bps": slippage_bps,
                    **metrics,
                    "positive_funding_period_rate": carry_stats.get("positive_funding_period_rate"),
                    "rebalance_count": carry_stats.get("rebalance_count"),
                }
            )
    return {
        "strategy": "funding_carry_cost_sensitivity",
        "symbols": symbol_list,
        "parameters": {
            "lookback_periods": lookback_periods,
            "hold_periods": hold_periods,
            "top_n": top_n,
            "min_funding_rate": min_funding_rate,
            "max_notional_pct": max_notional_pct,
            "fee_rates": fee_list,
            "slippage_bps": slippage_list,
        },
        "summary": cost_sensitivity_summary(rows),
        "rows": rows,
    }


def run_funding_carry_cost_sensitivity_report(
    config: AppConfig,
    symbols: Iterable[str],
    lookback_periods: int,
    hold_periods: int,
    top_n: int,
    min_funding_rate: float,
    max_notional_pct: float,
    fee_rates: Iterable[float],
    slippage_bps_values: Iterable[float],
    start: str | None = None,
    end: str | None = None,
) -> Path:
    payload = run_funding_carry_cost_sensitivity(
        config,
        symbols,
        lookback_periods=lookback_periods,
        hold_periods=hold_periods,
        top_n=top_n,
        min_funding_rate=min_funding_rate,
        max_notional_pct=max_notional_pct,
        fee_rates=fee_rates,
        slippage_bps_values=slippage_bps_values,
        start=start,
        end=end,
    )
    return write_report(config.report_dir, "funding_carry_cost_sensitivity", sanitize_for_json(payload))


def aggregate_strategy_scores(rows: list[dict[str, object]], min_trades: int = 3) -> list[dict[str, object]]:
    usable = [row for row in rows if row.get("status") == "ok" and int(row.get("trade_count", 0)) >= min_trades]
    by_strategy: dict[str, list[dict[str, object]]] = {}
    for row in usable:
        by_strategy.setdefault(str(row["strategy"]), []).append(row)
    aggregates: list[dict[str, object]] = []
    for strategy, items in by_strategy.items():
        sharpes = [float(item.get("sharpe", 0)) for item in items]
        returns = [float(item.get("total_return", 0)) for item in items]
        drawdowns = [float(item.get("max_drawdown", 0)) for item in items]
        aggregates.append(
            {
                "strategy": strategy,
                "sample_count": len(items),
                "mean_sharpe": sum(sharpes) / len(sharpes),
                "mean_total_return": sum(returns) / len(returns),
                "worst_drawdown": min(drawdowns),
                "positive_return_rate": sum(1 for value in returns if value > 0) / len(returns),
                "total_trades": sum(int(item.get("trade_count", 0)) for item in items),
            }
        )
    return sorted(
        aggregates,
        key=lambda item: (
            float(item["mean_sharpe"]),
            float(item["positive_return_rate"]),
            float(item["mean_total_return"]),
        ),
        reverse=True,
    )


def parameter_stability_summary(
    rows: list[dict[str, object]],
    parameter_names: list[str],
    min_trades: int = 3,
) -> dict[str, object]:
    usable = [
        row
        for row in rows
        if row.get("status") == "ok" and int(row.get("trade_count", 0) or 0) >= min_trades
    ]
    if not usable:
        return {
            "status": "insufficient_candidates",
            "candidate_count": 0,
            "robust_candidate_count": 0,
            "positive_return_rate": 0.0,
            "positive_sharpe_rate": 0.0,
            "top_cluster": [],
            "parameter_ranges": {},
            "fragility_flags": ["no usable grid candidates"],
        }
    scored = sorted(
        usable,
        key=lambda row: (
            float(row.get("sharpe", 0) or 0),
            float(row.get("total_return", 0) or 0),
            -abs(float(row.get("max_drawdown", 0) or 0)),
        ),
        reverse=True,
    )
    robust = [
        row
        for row in usable
        if float(row.get("total_return", 0) or 0) > 0 and float(row.get("sharpe", 0) or 0) > 0
    ]
    top_n = max(1, min(len(scored), max(3, len(scored) // 5)))
    top_cluster = scored[:top_n]
    parameter_ranges: dict[str, dict[str, object]] = {}
    fragility_flags: list[str] = []
    for name in parameter_names:
        all_values = sorted({row.get(name) for row in usable if row.get(name) is not None})
        top_values = sorted({row.get(name) for row in top_cluster if row.get(name) is not None})
        parameter_ranges[name] = {
            "tested_values": all_values,
            "top_cluster_values": top_values,
            "top_cluster_unique_count": len(top_values),
        }
        if len(all_values) > 1 and len(top_values) == 1:
            fragility_flags.append(f"top cluster uses a single {name} value")
    positive_return_rate = sum(1 for row in usable if float(row.get("total_return", 0) or 0) > 0) / len(usable)
    positive_sharpe_rate = sum(1 for row in usable if float(row.get("sharpe", 0) or 0) > 0) / len(usable)
    if positive_return_rate < 0.5:
        fragility_flags.append("less than half of usable candidates have positive return")
    if len(robust) < max(2, len(usable) * 0.2):
        fragility_flags.append("few candidates are positive on both return and Sharpe")
    return {
        "status": "ok" if not fragility_flags else "fragile",
        "candidate_count": len(usable),
        "robust_candidate_count": len(robust),
        "positive_return_rate": positive_return_rate,
        "positive_sharpe_rate": positive_sharpe_rate,
        "top_cluster": [
            {name: row.get(name) for name in parameter_names}
            | {
                "total_return": row.get("total_return"),
                "sharpe": row.get("sharpe"),
                "max_drawdown": row.get("max_drawdown"),
                "trade_count": row.get("trade_count"),
            }
            for row in top_cluster
        ],
        "parameter_ranges": parameter_ranges,
        "fragility_flags": fragility_flags,
    }


def walk_forward_summary(
    folds: list[dict[str, object]],
    parameter_names: list[str],
    activity_metric: str = "trade_count",
) -> dict[str, object]:
    ok_folds = [fold for fold in folds if fold.get("status") == "ok" and fold.get("test_metrics")]
    returns = [float(fold["test_metrics"].get("total_return", 0.0)) for fold in ok_folds]
    sharpes = [float(fold["test_metrics"].get("sharpe", 0.0)) for fold in ok_folds]
    drawdowns = [float(fold["test_metrics"].get("max_drawdown", 0.0)) for fold in ok_folds]
    compounded = 1.0
    for value in returns:
        compounded *= 1 + value
    parameter_drift: dict[str, dict[str, object]] = {}
    for name in parameter_names:
        selected_values = [
            fold.get("selected_params", {}).get(name)
            for fold in ok_folds
            if isinstance(fold.get("selected_params"), dict) and fold.get("selected_params", {}).get(name) is not None
        ]
        transition_count = sum(
            1 for previous, current in zip(selected_values, selected_values[1:]) if previous != current
        )
        parameter_drift[name] = {
            "selected_values": selected_values,
            "unique_values": sorted({value for value in selected_values}, key=str),
            "transition_count": transition_count,
        }
    fragility_flags: list[str] = []
    if not ok_folds:
        fragility_flags.append("no successful out-of-sample folds")
    positive_oos_fold_rate = sum(1 for value in returns if value > 0) / len(returns) if returns else 0.0
    if ok_folds and positive_oos_fold_rate < 0.5:
        fragility_flags.append("less than half of OOS folds are positive")
    if ok_folds and len(ok_folds) < max(2, len(folds) // 2):
        fragility_flags.append("less than half of all folds produced valid OOS metrics")
    return {
        "schema": "rolling_walk_forward_v1",
        "fold_count": len(folds),
        "ok_fold_count": len(ok_folds),
        "compounded_oos_return": compounded - 1,
        "mean_oos_return": sum(returns) / len(returns) if returns else 0.0,
        "mean_oos_sharpe": sum(sharpes) / len(sharpes) if sharpes else 0.0,
        "worst_oos_drawdown": min(drawdowns) if drawdowns else 0.0,
        "positive_oos_fold_rate": positive_oos_fold_rate,
        "parameter_drift": parameter_drift,
        "fragility_flags": fragility_flags,
        "status": "ok" if ok_folds and not fragility_flags else "fragile",
        "total_oos_activity": sum(
            int(fold["test_metrics"].get(activity_metric, 0)) for fold in ok_folds if fold.get("test_metrics")
        ),
    }


def cost_sensitivity_summary(rows: list[dict[str, object]]) -> dict[str, object]:
    ok_rows = [row for row in rows if row.get("status") == "ok"]
    returns = [float(row.get("total_return", 0.0) or 0.0) for row in ok_rows]
    sharpes = [float(row.get("sharpe", 0.0) or 0.0) for row in ok_rows]
    drawdowns = [float(row.get("max_drawdown", 0.0) or 0.0) for row in ok_rows]
    positive_rate = sum(1 for value in returns if value > 0) / len(returns) if returns else 0.0
    pass_rate = sum(
        1
        for row in ok_rows
        if float(row.get("total_return", 0.0) or 0.0) > 0 and float(row.get("sharpe", 0.0) or 0.0) > 0
    ) / len(ok_rows) if ok_rows else 0.0
    worst_return = min(returns) if returns else 0.0
    fragility_flags: list[str] = []
    if not ok_rows:
        fragility_flags.append("no valid cost scenarios")
    if ok_rows and positive_rate < 1.0:
        fragility_flags.append("at least one cost scenario has non-positive return")
    if ok_rows and pass_rate < 0.75:
        fragility_flags.append("less than 75% of cost scenarios pass return and Sharpe checks")
    if worst_return <= 0:
        fragility_flags.append("worst cost scenario is not profitable")
    recommendation = "research_only" if fragility_flags else "cost_robust_candidate"
    return {
        "schema": "cost_sensitivity_v1",
        "scenario_count": len(rows),
        "ok_scenario_count": len(ok_rows),
        "best_total_return": max(returns) if returns else 0.0,
        "worst_total_return": worst_return,
        "best_sharpe": max(sharpes) if sharpes else 0.0,
        "worst_sharpe": min(sharpes) if sharpes else 0.0,
        "worst_drawdown": min(drawdowns) if drawdowns else 0.0,
        "positive_scenario_rate": positive_rate,
        "pass_scenario_rate": pass_rate,
        "fragility_flags": fragility_flags,
        "recommendation": recommendation,
    }


def overfitting_diagnostics(
    rows: list[dict[str, object]],
    parameter_names: list[str],
    min_trades: int = 3,
) -> dict[str, object]:
    usable = [
        row
        for row in rows
        if row.get("status") == "ok" and int(row.get("trade_count", 0) or row.get("rebalance_count", 0) or 0) >= min_trades
    ]
    tried_count = len(rows)
    candidate_count = len(usable)
    sharpes = [float(row.get("sharpe", 0.0) or 0.0) for row in usable]
    returns = [float(row.get("total_return", 0.0) or 0.0) for row in usable]
    best_sharpe = max(sharpes) if sharpes else 0.0
    best_return = max(returns) if returns else 0.0
    # A lightweight multiple-testing haircut: more tried configurations require
    # stronger apparent Sharpe before promotion. This is not a formal DSR/PBO.
    multiple_testing_penalty = (2.0 * math.log(max(tried_count, 1))) ** 0.5 * 0.10
    deflated_sharpe_proxy = best_sharpe - multiple_testing_penalty
    parameter_space = {
        name: sorted({row.get(name) for row in rows if row.get(name) is not None}, key=str)
        for name in parameter_names
    }
    fragility_flags: list[str] = []
    if tried_count >= 20:
        fragility_flags.append("large parameter search requires stronger OOS evidence")
    if candidate_count < max(3, tried_count * 0.2):
        fragility_flags.append("few parameter candidates satisfy minimum activity requirements")
    if deflated_sharpe_proxy <= 0:
        fragility_flags.append("best Sharpe does not survive multiple-testing haircut")
    if best_return <= 0:
        fragility_flags.append("best candidate return is non-positive")
    return {
        "schema": "overfitting_diagnostics_v1",
        "method": "multiple_testing_haircut_proxy",
        "tried_configuration_count": tried_count,
        "usable_candidate_count": candidate_count,
        "parameter_count": len(parameter_names),
        "parameter_space": parameter_space,
        "best_sharpe": best_sharpe,
        "best_total_return": best_return,
        "multiple_testing_penalty": multiple_testing_penalty,
        "deflated_sharpe_proxy": deflated_sharpe_proxy,
        "fragility_flags": fragility_flags,
        "recommendation": "research_only" if fragility_flags else "eligible_for_walk_forward",
    }


def run_cross_sectional_momentum(
    config: AppConfig,
    symbols: Iterable[str],
    instrument_type: str,
    lookback_bars: int = 24 * 30,
    hold_bars: int = 24 * 7,
    top_n: int = 1,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, object]:
    series: dict[str, pd.DataFrame] = {}
    for symbol in symbols:
        df = filter_date_range(load_candles(config, symbol, instrument_type), start, end)
        if not df.empty:
            series[symbol] = df.sort_values("ts").reset_index(drop=True)
    if len(series) < 2:
        return {
            "strategy": "cross_sectional_momentum",
            "status": "insufficient_symbols",
            "symbols": list(series),
            "lookback_bars": lookback_bars,
            "hold_bars": hold_bars,
        }

    closes = pd.concat(
        [df.set_index("ts")["close"].rename(symbol) for symbol, df in series.items()],
        axis=1,
    ).dropna()
    if len(closes) <= lookback_bars + hold_bars:
        return {
            "strategy": "cross_sectional_momentum",
            "status": "insufficient_history",
            "symbols": list(series),
            "bars": len(closes),
            "required_bars": lookback_bars + hold_bars + 1,
        }

    cash = config.backtest.initial_cash
    equity = cash
    equity_rows: list[dict[str, object]] = []
    trade_rows: list[dict[str, object]] = []
    holdings: dict[str, float] = {}
    cost_basis: dict[str, float] = {}
    slippage = config.execution.slippage_bps / 10_000

    for idx in range(lookback_bars, len(closes), hold_bars):
        now = closes.index[idx]
        lookback_return = closes.iloc[idx] / closes.iloc[idx - lookback_bars] - 1
        ranked = lookback_return.sort_values(ascending=False)
        selected = list(ranked.head(top_n).index)
        if not selected:
            continue

        if holdings:
            proceeds_total = 0.0
            for symbol, quantity in holdings.items():
                exit_price = float(closes.iloc[idx][symbol]) * (1 - slippage)
                proceeds = quantity * exit_price * (1 - config.execution.fee_rate)
                realized = proceeds - cost_basis.get(symbol, 0.0)
                proceeds_total += proceeds
                trade_rows.append(
                    {
                        "ts": now,
                        "symbol": symbol,
                        "side": "sell",
                        "quantity": quantity,
                        "price": exit_price,
                        "realized_pnl": realized,
                    }
                )
            equity = proceeds_total
            holdings = {}
            cost_basis = {}

        allocation = equity / len(selected)
        for chosen in selected:
            price = float(closes.iloc[idx][chosen]) * (1 + slippage)
            quantity = allocation * (1 - config.execution.fee_rate) / price
            holdings[chosen] = quantity
            cost_basis[chosen] = allocation
            trade_rows.append(
                {
                    "ts": now,
                    "symbol": chosen,
                    "side": "buy",
                    "quantity": quantity,
                    "price": price,
                    "realized_pnl": 0.0,
                }
            )
        mark_to_market = sum(quantity * float(closes.iloc[idx][symbol]) for symbol, quantity in holdings.items())
        equity_rows.append({"ts": now, "equity": mark_to_market, "selected": selected, "rank": ranked.to_dict()})

    if holdings:
        final_ts = closes.index[-1]
        final_equity = 0.0
        for symbol, quantity in holdings.items():
            final_price = float(closes.iloc[-1][symbol]) * (1 - slippage)
            proceeds = quantity * final_price * (1 - config.execution.fee_rate)
            final_equity += proceeds
            trade_rows.append(
                {
                    "ts": final_ts,
                    "symbol": symbol,
                    "side": "sell",
                    "quantity": quantity,
                    "price": final_price,
                    "realized_pnl": proceeds - cost_basis.get(symbol, 0.0),
                }
            )
        equity_rows.append({"ts": final_ts, "equity": final_equity, "selected": list(holdings)})

    equity_curve = pd.DataFrame(equity_rows)
    trades = pd.DataFrame(trade_rows)
    return {
        "strategy": "cross_sectional_momentum",
        "status": "ok",
        "symbols": list(series),
        "lookback_bars": lookback_bars,
        "hold_bars": hold_bars,
        "top_n": top_n,
        "metrics": calculate_metrics(equity_curve, trades),
        "equity_curve_tail": equity_curve.tail(20).to_dict("records"),
        "trades": trades.to_dict("records"),
    }


def run_adaptive_trend(
    config: AppConfig,
    symbols: Iterable[str],
    instrument_type: str,
    lookback_bars: int = 24 * 30,
    hold_bars: int = 24 * 7,
    top_n: int = 2,
    ema_span: int = 24 * 20,
    volatility_bars: int = 24 * 14,
    target_volatility: float = 0.20,
    max_weight: float = 0.50,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, object]:
    symbol_list = list(symbols)
    closes = load_close_matrix(config, symbol_list, instrument_type)
    if closes.empty:
        return {"strategy": "adaptive_trend", "status": "missing_data", "symbols": symbol_list}
    if start:
        closes = closes[closes.index >= pd.to_datetime(start, utc=True)]
    if end:
        closes = closes[closes.index <= pd.to_datetime(end, utc=True)]
    if len(closes) <= max(lookback_bars, ema_span, volatility_bars) + hold_bars:
        return {
            "strategy": "adaptive_trend",
            "status": "insufficient_history",
            "symbols": symbol_list,
            "bars": len(closes),
            "required_bars": max(lookback_bars, ema_span, volatility_bars) + hold_bars + 1,
        }

    returns = closes.pct_change().fillna(0.0)
    rolling_mean = returns.rolling(lookback_bars).mean()
    rolling_std = returns.rolling(lookback_bars).std().replace(0, float("nan"))
    rolling_sharpe = (rolling_mean / rolling_std).fillna(0.0)
    ema = closes.ewm(span=ema_span, adjust=False).mean()
    realized_vol = returns.rolling(volatility_bars).std().fillna(0.0) * math.sqrt(24 * 365)
    slippage = config.execution.slippage_bps / 10_000

    cash = config.backtest.initial_cash
    equity = cash
    cash_reserve = cash
    holdings: dict[str, float] = {}
    cost_basis: dict[str, float] = {}
    equity_rows: list[dict[str, object]] = []
    trade_rows: list[dict[str, object]] = []

    start_idx = max(lookback_bars, ema_span, volatility_bars)
    for idx in range(start_idx, len(closes), hold_bars):
        now = closes.index[idx]
        current_prices = closes.iloc[idx]
        if holdings:
            proceeds_total = 0.0
            for symbol, quantity in holdings.items():
                exit_price = float(current_prices[symbol]) * (1 - slippage)
                proceeds = quantity * exit_price * (1 - config.execution.fee_rate)
                proceeds_total += proceeds
                trade_rows.append(
                    {
                        "ts": now,
                        "symbol": symbol,
                        "side": "sell",
                        "quantity": quantity,
                        "price": exit_price,
                        "realized_pnl": proceeds - cost_basis.get(symbol, 0.0),
                    }
                )
            equity = proceeds_total + cash_reserve
            holdings = {}
            cost_basis = {}
            cash_reserve = equity

        scores = rolling_sharpe.iloc[idx].copy()
        trend_ok = current_prices > ema.iloc[idx]
        scores = scores[(scores > 0) & trend_ok]
        ranked = scores.sort_values(ascending=False)
        selected = list(ranked.head(max(top_n, 1)).index)
        if not selected:
            equity_rows.append({"ts": now, "equity": equity, "selected": [], "rank": ranked.to_dict()})
            cash_reserve = equity
            continue

        raw_weights: dict[str, float] = {}
        for symbol in selected:
            vol = max(float(realized_vol.iloc[idx][symbol]), 1e-6)
            raw_weights[symbol] = min(target_volatility / vol / len(selected), max_weight)
        total_weight = min(sum(raw_weights.values()), 1.0)
        if total_weight <= 0:
            equity_rows.append({"ts": now, "equity": equity, "selected": [], "rank": ranked.to_dict()})
            cash_reserve = equity
            continue
        scale = total_weight / sum(raw_weights.values())
        for symbol, raw_weight in raw_weights.items():
            allocation = equity * raw_weight * scale
            price = float(current_prices[symbol]) * (1 + slippage)
            quantity = allocation * (1 - config.execution.fee_rate) / price
            holdings[symbol] = quantity
            cost_basis[symbol] = allocation
            trade_rows.append(
                {
                    "ts": now,
                    "symbol": symbol,
                    "side": "buy",
                    "quantity": quantity,
                    "price": price,
                    "realized_pnl": 0.0,
                    "weight": raw_weight * scale,
                    "score": float(ranked.get(symbol, 0.0)),
                }
            )
        cash_reserve = equity * (1 - total_weight)
        mark_to_market = cash_reserve + sum(
            quantity * float(current_prices[symbol]) for symbol, quantity in holdings.items()
        )
        equity_rows.append(
            {
                "ts": now,
                "equity": mark_to_market,
                "selected": selected,
                "rank": ranked.to_dict(),
                "gross_weight": total_weight,
            }
        )

    if holdings:
        final_ts = closes.index[-1]
        final_prices = closes.iloc[-1]
        final_equity = cash_reserve
        for symbol, quantity in holdings.items():
            final_price = float(final_prices[symbol]) * (1 - slippage)
            proceeds = quantity * final_price * (1 - config.execution.fee_rate)
            final_equity += proceeds
            trade_rows.append(
                {
                    "ts": final_ts,
                    "symbol": symbol,
                    "side": "sell",
                    "quantity": quantity,
                    "price": final_price,
                    "realized_pnl": proceeds - cost_basis.get(symbol, 0.0),
                }
            )
        equity_rows.append({"ts": final_ts, "equity": final_equity, "selected": list(holdings)})

    equity_curve = pd.DataFrame(equity_rows)
    trades = pd.DataFrame(trade_rows)
    return {
        "strategy": "adaptive_trend",
        "status": "ok",
        "symbols": symbol_list,
        "instrument_type": instrument_type,
        "parameters": {
            "lookback_bars": lookback_bars,
            "hold_bars": hold_bars,
            "top_n": top_n,
            "ema_span": ema_span,
            "volatility_bars": volatility_bars,
            "target_volatility": target_volatility,
            "max_weight": max_weight,
        },
        "metrics": calculate_metrics(equity_curve, trades),
        "equity_curve_tail": equity_curve.tail(20).to_dict("records"),
        "trades": trades.to_dict("records"),
    }


def run_adaptive_trend_report(
    config: AppConfig,
    symbols: Iterable[str],
    instrument_type: str,
    lookback_bars: int = 24 * 30,
    hold_bars: int = 24 * 7,
    top_n: int = 2,
    ema_span: int = 24 * 20,
    volatility_bars: int = 24 * 14,
    target_volatility: float = 0.20,
    max_weight: float = 0.50,
    start: str | None = None,
    end: str | None = None,
) -> Path:
    payload = run_adaptive_trend(
        config,
        symbols,
        instrument_type,
        lookback_bars=lookback_bars,
        hold_bars=hold_bars,
        top_n=top_n,
        ema_span=ema_span,
        volatility_bars=volatility_bars,
        target_volatility=target_volatility,
        max_weight=max_weight,
        start=start,
        end=end,
    )
    return write_report(config.report_dir, "adaptive_trend", sanitize_for_json(payload))


def run_adaptive_trend_grid(
    config: AppConfig,
    symbols: Iterable[str],
    instrument_type: str,
    lookback_bars: Iterable[int],
    hold_bars: Iterable[int],
    top_n_values: Iterable[int],
    ema_spans: Iterable[int],
    volatility_bars_values: Iterable[int],
    target_volatilities: Iterable[float],
    max_weights: Iterable[float],
    start: str | None = None,
    end: str | None = None,
    min_trades: int = 6,
) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    symbol_list = list(symbols)
    lookback_list = list(lookback_bars)
    hold_list = list(hold_bars)
    top_n_list = list(top_n_values)
    ema_span_list = list(ema_spans)
    volatility_bars_list = list(volatility_bars_values)
    target_volatility_list = list(target_volatilities)
    max_weight_list = list(max_weights)

    for lookback in lookback_list:
        for hold in hold_list:
            for top_n in top_n_list:
                for ema_span in ema_span_list:
                    for volatility_bars in volatility_bars_list:
                        for target_volatility in target_volatility_list:
                            for max_weight in max_weight_list:
                                result = run_adaptive_trend(
                                    config,
                                    symbol_list,
                                    instrument_type,
                                    lookback_bars=lookback,
                                    hold_bars=hold,
                                    top_n=top_n,
                                    ema_span=ema_span,
                                    volatility_bars=volatility_bars,
                                    target_volatility=target_volatility,
                                    max_weight=max_weight,
                                    start=start,
                                    end=end,
                                )
                                metrics = result.get("metrics", {}) if result.get("status") == "ok" else {}
                                rows.append(
                                    {
                                        "strategy": "adaptive_trend",
                                        "status": result.get("status"),
                                        "symbols_tested": len(result.get("symbols", [])),
                                        "lookback_bars": lookback,
                                        "hold_bars": hold,
                                        "top_n": top_n,
                                        "ema_span": ema_span,
                                        "volatility_bars": volatility_bars,
                                        "target_volatility": target_volatility,
                                        "max_weight": max_weight,
                                        **metrics,
                                    }
                                )

    ranked = sorted(
        [
            row
            for row in rows
            if row.get("status") == "ok" and int(row.get("trade_count", 0)) >= min_trades
        ],
        key=lambda row: (
            float(row.get("sharpe", 0)),
            float(row.get("total_return", 0)),
            -abs(float(row.get("max_drawdown", 0))),
        ),
        reverse=True,
    )
    return {
        "strategy": "adaptive_trend_grid",
        "instrument_type": instrument_type,
        "symbols": symbol_list,
        "parameters": {
            "lookback_bars": lookback_list,
            "hold_bars": hold_list,
            "top_n": top_n_list,
            "ema_span": ema_span_list,
            "volatility_bars": volatility_bars_list,
            "target_volatility": target_volatility_list,
            "max_weight": max_weight_list,
            "min_trades": min_trades,
        },
        "rows": rows,
        "ranked": ranked,
        "best": ranked[0] if ranked else None,
        "parameter_stability": parameter_stability_summary(
            rows,
            [
                "lookback_bars",
                "hold_bars",
                "top_n",
                "ema_span",
                "volatility_bars",
                "target_volatility",
                "max_weight",
            ],
            min_trades=min_trades,
        ),
        "overfitting_diagnostics": overfitting_diagnostics(
            rows,
            [
                "lookback_bars",
                "hold_bars",
                "top_n",
                "ema_span",
                "volatility_bars",
                "target_volatility",
                "max_weight",
            ],
            min_trades=min_trades,
        ),
    }


def run_adaptive_trend_grid_report(
    config: AppConfig,
    symbols: Iterable[str],
    instrument_type: str,
    lookback_bars: Iterable[int],
    hold_bars: Iterable[int],
    top_n_values: Iterable[int],
    ema_spans: Iterable[int],
    volatility_bars_values: Iterable[int],
    target_volatilities: Iterable[float],
    max_weights: Iterable[float],
    start: str | None = None,
    end: str | None = None,
    min_trades: int = 6,
) -> Path:
    payload = run_adaptive_trend_grid(
        config,
        symbols,
        instrument_type,
        lookback_bars=lookback_bars,
        hold_bars=hold_bars,
        top_n_values=top_n_values,
        ema_spans=ema_spans,
        volatility_bars_values=volatility_bars_values,
        target_volatilities=target_volatilities,
        max_weights=max_weights,
        start=start,
        end=end,
        min_trades=min_trades,
    )
    return write_report(config.report_dir, "adaptive_trend_grid", sanitize_for_json(payload))


def run_adaptive_trend_walk_forward(
    config: AppConfig,
    symbols: Iterable[str],
    instrument_type: str,
    lookback_bars: Iterable[int],
    hold_bars: Iterable[int],
    top_n_values: Iterable[int],
    ema_spans: Iterable[int],
    volatility_bars_values: Iterable[int],
    target_volatilities: Iterable[float],
    max_weights: Iterable[float],
    train_bars: int = 24 * 60,
    test_bars: int = 24 * 14,
    step_bars: int | None = None,
    min_trades: int = 4,
) -> dict[str, object]:
    symbol_list = list(symbols)
    lookback_list = list(lookback_bars)
    hold_list = list(hold_bars)
    top_n_list = list(top_n_values)
    ema_span_list = list(ema_spans)
    volatility_bars_list = list(volatility_bars_values)
    target_volatility_list = list(target_volatilities)
    max_weight_list = list(max_weights)
    closes = load_close_matrix(config, symbol_list, instrument_type)
    if closes.empty:
        return {"strategy": "adaptive_trend_walk_forward", "status": "missing_data", "symbols": symbol_list}

    step = step_bars or test_bars
    folds: list[dict[str, object]] = []
    fold_index = 0
    start_idx = 0
    while start_idx + train_bars + test_bars <= len(closes):
        train_start = closes.index[start_idx]
        train_end = closes.index[start_idx + train_bars - 1]
        test_start = closes.index[start_idx + train_bars]
        test_end = closes.index[start_idx + train_bars + test_bars - 1]
        train = run_adaptive_trend_grid(
            config,
            symbol_list,
            instrument_type,
            lookback_bars=lookback_list,
            hold_bars=hold_list,
            top_n_values=top_n_list,
            ema_spans=ema_span_list,
            volatility_bars_values=volatility_bars_list,
            target_volatilities=target_volatility_list,
            max_weights=max_weight_list,
            start=str(train_start),
            end=str(train_end),
            min_trades=min_trades,
        )
        best = train.get("best")
        if not best:
            folds.append(
                {
                    "fold": fold_index,
                    "status": "no_train_candidate",
                    "train_start": str(train_start),
                    "train_end": str(train_end),
                    "test_start": str(test_start),
                    "test_end": str(test_end),
                }
            )
        else:
            warmup = max(int(best["lookback_bars"]), int(best["ema_span"]), int(best["volatility_bars"]))
            test_data_start_idx = max(start_idx + train_bars - warmup, 0)
            test_data_start = closes.index[test_data_start_idx]
            test = run_adaptive_trend(
                config,
                symbol_list,
                instrument_type,
                lookback_bars=int(best["lookback_bars"]),
                hold_bars=int(best["hold_bars"]),
                top_n=int(best["top_n"]),
                ema_span=int(best["ema_span"]),
                volatility_bars=int(best["volatility_bars"]),
                target_volatility=float(best["target_volatility"]),
                max_weight=float(best["max_weight"]),
                start=str(test_data_start),
                end=str(test_end),
            )
            metrics = test.get("metrics", {}) if test.get("status") == "ok" else {}
            folds.append(
                {
                    "fold": fold_index,
                    "status": test.get("status"),
                    "train_start": str(train_start),
                    "train_end": str(train_end),
                    "test_start": str(test_start),
                    "test_end": str(test_end),
                    "test_data_start": str(test_data_start),
                    "selected_params": {
                        "lookback_bars": best["lookback_bars"],
                        "hold_bars": best["hold_bars"],
                        "top_n": best["top_n"],
                        "ema_span": best["ema_span"],
                        "volatility_bars": best["volatility_bars"],
                        "target_volatility": best["target_volatility"],
                        "max_weight": best["max_weight"],
                    },
                    "train_metrics": {
                        "total_return": best.get("total_return"),
                        "max_drawdown": best.get("max_drawdown"),
                        "sharpe": best.get("sharpe"),
                        "trade_count": best.get("trade_count"),
                    },
                    "test_metrics": metrics,
                }
            )
        fold_index += 1
        start_idx += step

    summary = walk_forward_summary(
        folds,
        [
            "lookback_bars",
            "hold_bars",
            "top_n",
            "ema_span",
            "volatility_bars",
            "target_volatility",
            "max_weight",
        ],
    )
    summary["total_oos_trades"] = summary["total_oos_activity"]
    return {
        "strategy": "adaptive_trend_walk_forward",
        "status": "ok" if int(summary.get("ok_fold_count", 0)) else "no_ok_folds",
        "instrument_type": instrument_type,
        "symbols": symbol_list,
        "bars": len(closes),
        "parameters": {
            "lookback_bars": lookback_list,
            "hold_bars": hold_list,
            "top_n": top_n_list,
            "ema_span": ema_span_list,
            "volatility_bars": volatility_bars_list,
            "target_volatility": target_volatility_list,
            "max_weight": max_weight_list,
            "train_bars": train_bars,
            "test_bars": test_bars,
            "step_bars": step,
            "min_trades": min_trades,
        },
        "summary": summary,
        "folds": folds,
    }


def run_adaptive_trend_walk_forward_report(
    config: AppConfig,
    symbols: Iterable[str],
    instrument_type: str,
    lookback_bars: Iterable[int],
    hold_bars: Iterable[int],
    top_n_values: Iterable[int],
    ema_spans: Iterable[int],
    volatility_bars_values: Iterable[int],
    target_volatilities: Iterable[float],
    max_weights: Iterable[float],
    train_bars: int = 24 * 60,
    test_bars: int = 24 * 14,
    step_bars: int | None = None,
    min_trades: int = 4,
) -> Path:
    payload = run_adaptive_trend_walk_forward(
        config,
        symbols,
        instrument_type,
        lookback_bars=lookback_bars,
        hold_bars=hold_bars,
        top_n_values=top_n_values,
        ema_spans=ema_spans,
        volatility_bars_values=volatility_bars_values,
        target_volatilities=target_volatilities,
        max_weights=max_weights,
        train_bars=train_bars,
        test_bars=test_bars,
        step_bars=step_bars,
        min_trades=min_trades,
    )
    return write_report(config.report_dir, "adaptive_trend_walk_forward", sanitize_for_json(payload))


def run_adaptive_trend_cost_sensitivity(
    config: AppConfig,
    symbols: Iterable[str],
    instrument_type: str,
    lookback_bars: int,
    hold_bars: int,
    top_n: int,
    ema_span: int,
    volatility_bars: int,
    target_volatility: float,
    max_weight: float,
    fee_rates: Iterable[float],
    slippage_bps_values: Iterable[float],
    start: str | None = None,
    end: str | None = None,
) -> dict[str, object]:
    symbol_list = list(symbols)
    fee_list = list(fee_rates)
    slippage_list = list(slippage_bps_values)
    rows: list[dict[str, object]] = []
    for fee_rate in fee_list:
        for slippage_bps in slippage_list:
            cfg = config.model_copy(deep=True)
            cfg.execution.fee_rate = fee_rate
            cfg.execution.slippage_bps = slippage_bps
            result = run_adaptive_trend(
                cfg,
                symbol_list,
                instrument_type,
                lookback_bars=lookback_bars,
                hold_bars=hold_bars,
                top_n=top_n,
                ema_span=ema_span,
                volatility_bars=volatility_bars,
                target_volatility=target_volatility,
                max_weight=max_weight,
                start=start,
                end=end,
            )
            metrics = result.get("metrics", {}) if result.get("status") == "ok" else {}
            rows.append(
                {
                    "status": result.get("status"),
                    "fee_rate": fee_rate,
                    "slippage_bps": slippage_bps,
                    **metrics,
                }
            )
    return {
        "strategy": "adaptive_trend_cost_sensitivity",
        "instrument_type": instrument_type,
        "symbols": symbol_list,
        "parameters": {
            "lookback_bars": lookback_bars,
            "hold_bars": hold_bars,
            "top_n": top_n,
            "ema_span": ema_span,
            "volatility_bars": volatility_bars,
            "target_volatility": target_volatility,
            "max_weight": max_weight,
            "fee_rates": fee_list,
            "slippage_bps": slippage_list,
        },
        "summary": cost_sensitivity_summary(rows),
        "rows": rows,
    }


def run_adaptive_trend_cost_sensitivity_report(
    config: AppConfig,
    symbols: Iterable[str],
    instrument_type: str,
    lookback_bars: int,
    hold_bars: int,
    top_n: int,
    ema_span: int,
    volatility_bars: int,
    target_volatility: float,
    max_weight: float,
    fee_rates: Iterable[float],
    slippage_bps_values: Iterable[float],
    start: str | None = None,
    end: str | None = None,
) -> Path:
    payload = run_adaptive_trend_cost_sensitivity(
        config,
        symbols,
        instrument_type,
        lookback_bars=lookback_bars,
        hold_bars=hold_bars,
        top_n=top_n,
        ema_span=ema_span,
        volatility_bars=volatility_bars,
        target_volatility=target_volatility,
        max_weight=max_weight,
        fee_rates=fee_rates,
        slippage_bps_values=slippage_bps_values,
        start=start,
        end=end,
    )
    return write_report(config.report_dir, "adaptive_trend_cost_sensitivity", sanitize_for_json(payload))


def sanitize_for_json(value: object) -> object:
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): sanitize_for_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_for_json(item) for item in value]
    return value


def run_cross_sectional_momentum_grid(
    config: AppConfig,
    symbols: Iterable[str],
    instrument_type: str,
    lookback_bars: Iterable[int],
    hold_bars: Iterable[int],
    top_n_values: Iterable[int],
    start: str | None = None,
    end: str | None = None,
    min_trades: int = 6,
) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    symbol_list = list(symbols)
    lookback_list = list(lookback_bars)
    hold_list = list(hold_bars)
    top_n_list = list(top_n_values)
    for lookback in lookback_list:
        for hold in hold_list:
            for top_n in top_n_list:
                result = run_cross_sectional_momentum(
                    config,
                    symbol_list,
                    instrument_type,
                    lookback_bars=lookback,
                    hold_bars=hold,
                    top_n=top_n,
                    start=start,
                    end=end,
                )
                metrics = result.get("metrics", {}) if result.get("status") == "ok" else {}
                rows.append(
                    {
                        "strategy": "cross_sectional_momentum",
                        "status": result.get("status"),
                        "symbols_tested": len(result.get("symbols", [])),
                        "lookback_bars": lookback,
                        "hold_bars": hold,
                        "top_n": top_n,
                        **metrics,
                    }
                )
    ranked = sorted(
        [
            row
            for row in rows
            if row.get("status") == "ok" and int(row.get("trade_count", 0)) >= min_trades
        ],
        key=lambda row: (
            float(row.get("sharpe", 0)),
            float(row.get("total_return", 0)),
            -abs(float(row.get("max_drawdown", 0))),
        ),
        reverse=True,
    )
    return {
        "strategy": "cross_sectional_momentum_grid",
        "instrument_type": instrument_type,
        "symbols": symbol_list,
        "parameters": {
            "lookback_bars": lookback_list,
            "hold_bars": hold_list,
            "top_n": top_n_list,
            "min_trades": min_trades,
        },
        "rows": rows,
        "ranked": ranked,
        "best": ranked[0] if ranked else None,
        "parameter_stability": parameter_stability_summary(
            rows,
            ["lookback_bars", "hold_bars", "top_n"],
            min_trades=min_trades,
        ),
        "overfitting_diagnostics": overfitting_diagnostics(
            rows,
            ["lookback_bars", "hold_bars", "top_n"],
            min_trades=min_trades,
        ),
    }


def run_cross_sectional_momentum_grid_report(
    config: AppConfig,
    symbols: Iterable[str],
    instrument_type: str,
    lookback_bars: Iterable[int],
    hold_bars: Iterable[int],
    top_n_values: Iterable[int],
    start: str | None = None,
    end: str | None = None,
    min_trades: int = 6,
) -> Path:
    payload = run_cross_sectional_momentum_grid(
        config,
        symbols,
        instrument_type,
        lookback_bars,
        hold_bars,
        top_n_values,
        start=start,
        end=end,
        min_trades=min_trades,
    )
    return write_report(config.report_dir, "cross_sectional_momentum_grid", sanitize_for_json(payload))


def run_cross_sectional_momentum_walk_forward(
    config: AppConfig,
    symbols: Iterable[str],
    instrument_type: str,
    lookback_bars: Iterable[int],
    hold_bars: Iterable[int],
    top_n_values: Iterable[int],
    train_bars: int = 24 * 60,
    test_bars: int = 24 * 14,
    step_bars: int | None = None,
    min_trades: int = 4,
) -> dict[str, object]:
    symbol_list = list(symbols)
    lookback_list = list(lookback_bars)
    hold_list = list(hold_bars)
    top_n_list = list(top_n_values)
    closes = load_close_matrix(config, symbol_list, instrument_type)
    if closes.empty:
        return {"strategy": "cross_sectional_momentum_walk_forward", "status": "missing_data", "symbols": symbol_list}
    step = step_bars or test_bars
    folds: list[dict[str, object]] = []
    fold_index = 0
    start_idx = 0
    while start_idx + train_bars + test_bars <= len(closes):
        train_start = closes.index[start_idx]
        train_end = closes.index[start_idx + train_bars - 1]
        test_start = closes.index[start_idx + train_bars]
        test_end = closes.index[start_idx + train_bars + test_bars - 1]
        train = run_cross_sectional_momentum_grid(
            config,
            symbol_list,
            instrument_type,
            lookback_bars=lookback_list,
            hold_bars=hold_list,
            top_n_values=top_n_list,
            start=str(train_start),
            end=str(train_end),
            min_trades=min_trades,
        )
        best = train.get("best")
        if not best:
            folds.append(
                {
                    "fold": fold_index,
                    "status": "no_train_candidate",
                    "train_start": str(train_start),
                    "train_end": str(train_end),
                    "test_start": str(test_start),
                    "test_end": str(test_end),
                }
            )
        else:
            test_data_start_idx = max(start_idx + train_bars - int(best["lookback_bars"]), 0)
            test_data_start = closes.index[test_data_start_idx]
            test = run_cross_sectional_momentum(
                config,
                symbol_list,
                instrument_type,
                lookback_bars=int(best["lookback_bars"]),
                hold_bars=int(best["hold_bars"]),
                top_n=int(best["top_n"]),
                start=str(test_data_start),
                end=str(test_end),
            )
            metrics = test.get("metrics", {}) if test.get("status") == "ok" else {}
            folds.append(
                {
                    "fold": fold_index,
                    "status": test.get("status"),
                    "train_start": str(train_start),
                    "train_end": str(train_end),
                    "test_start": str(test_start),
                    "test_end": str(test_end),
                    "test_data_start": str(test_data_start),
                    "selected_params": {
                        "lookback_bars": best["lookback_bars"],
                        "hold_bars": best["hold_bars"],
                        "top_n": best["top_n"],
                    },
                    "train_metrics": {
                        "total_return": best.get("total_return"),
                        "max_drawdown": best.get("max_drawdown"),
                        "sharpe": best.get("sharpe"),
                        "trade_count": best.get("trade_count"),
                    },
                    "test_metrics": metrics,
                }
            )
        fold_index += 1
        start_idx += step
    summary = walk_forward_summary(folds, ["lookback_bars", "hold_bars", "top_n"])
    summary["total_oos_trades"] = summary["total_oos_activity"]
    return {
        "strategy": "cross_sectional_momentum_walk_forward",
        "status": "ok" if int(summary.get("ok_fold_count", 0)) else "no_ok_folds",
        "instrument_type": instrument_type,
        "symbols": symbol_list,
        "bars": len(closes),
        "parameters": {
            "lookback_bars": lookback_list,
            "hold_bars": hold_list,
            "top_n": top_n_list,
            "train_bars": train_bars,
            "test_bars": test_bars,
            "step_bars": step,
            "min_trades": min_trades,
        },
        "summary": summary,
        "folds": folds,
    }


def run_cross_sectional_momentum_walk_forward_report(
    config: AppConfig,
    symbols: Iterable[str],
    instrument_type: str,
    lookback_bars: Iterable[int],
    hold_bars: Iterable[int],
    top_n_values: Iterable[int],
    train_bars: int = 24 * 60,
    test_bars: int = 24 * 14,
    step_bars: int | None = None,
    min_trades: int = 4,
) -> Path:
    payload = run_cross_sectional_momentum_walk_forward(
        config,
        symbols,
        instrument_type,
        lookback_bars=lookback_bars,
        hold_bars=hold_bars,
        top_n_values=top_n_values,
        train_bars=train_bars,
        test_bars=test_bars,
        step_bars=step_bars,
        min_trades=min_trades,
    )
    return write_report(config.report_dir, "cross_sectional_momentum_walk_forward", sanitize_for_json(payload))


def run_cross_sectional_momentum_cost_sensitivity(
    config: AppConfig,
    symbols: Iterable[str],
    instrument_type: str,
    lookback_bars: int,
    hold_bars: int,
    top_n: int,
    fee_rates: Iterable[float],
    slippage_bps_values: Iterable[float],
    start: str | None = None,
    end: str | None = None,
) -> dict[str, object]:
    symbol_list = list(symbols)
    fee_list = list(fee_rates)
    slippage_list = list(slippage_bps_values)
    rows: list[dict[str, object]] = []
    for fee_rate in fee_list:
        for slippage_bps in slippage_list:
            cfg = config.model_copy(deep=True)
            cfg.execution.fee_rate = fee_rate
            cfg.execution.slippage_bps = slippage_bps
            result = run_cross_sectional_momentum(
                cfg,
                symbol_list,
                instrument_type,
                lookback_bars=lookback_bars,
                hold_bars=hold_bars,
                top_n=top_n,
                start=start,
                end=end,
            )
            metrics = result.get("metrics", {}) if result.get("status") == "ok" else {}
            rows.append(
                {
                    "status": result.get("status"),
                    "fee_rate": fee_rate,
                    "slippage_bps": slippage_bps,
                    **metrics,
                }
            )
    return {
        "strategy": "cross_sectional_momentum_cost_sensitivity",
        "instrument_type": instrument_type,
        "symbols": symbol_list,
        "parameters": {
            "lookback_bars": lookback_bars,
            "hold_bars": hold_bars,
            "top_n": top_n,
            "fee_rates": fee_list,
            "slippage_bps": slippage_list,
        },
        "summary": cost_sensitivity_summary(rows),
        "rows": rows,
    }


def run_cross_sectional_momentum_cost_sensitivity_report(
    config: AppConfig,
    symbols: Iterable[str],
    instrument_type: str,
    lookback_bars: int,
    hold_bars: int,
    top_n: int,
    fee_rates: Iterable[float],
    slippage_bps_values: Iterable[float],
    start: str | None = None,
    end: str | None = None,
) -> Path:
    payload = run_cross_sectional_momentum_cost_sensitivity(
        config,
        symbols,
        instrument_type,
        lookback_bars=lookback_bars,
        hold_bars=hold_bars,
        top_n=top_n,
        fee_rates=fee_rates,
        slippage_bps_values=slippage_bps_values,
        start=start,
        end=end,
    )
    return write_report(config.report_dir, "cross_sectional_momentum_cost_sensitivity", sanitize_for_json(payload))


def run_cross_sectional_momentum_report(
    config: AppConfig,
    symbols: Iterable[str],
    instrument_type: str,
    lookback_bars: int = 24 * 30,
    hold_bars: int = 24 * 7,
    top_n: int = 1,
    start: str | None = None,
    end: str | None = None,
) -> Path:
    payload = run_cross_sectional_momentum(
        config,
        symbols,
        instrument_type,
        lookback_bars=lookback_bars,
        hold_bars=hold_bars,
        top_n=top_n,
        start=start,
        end=end,
    )
    return write_report(config.report_dir, "cross_sectional_momentum", sanitize_for_json(payload))


def run_strategy_sweep_report(
    config: AppConfig,
    symbols: Iterable[str],
    instrument_type: str,
    strategies: Iterable[str] | None = None,
    start: str | None = None,
    end: str | None = None,
) -> Path:
    payload = run_strategy_sweep(config, symbols, instrument_type, strategies, start, end)
    return write_report(config.report_dir, "strategy_sweep", payload)


def run_multi_timeframe_strategy_sweep_report(
    config: AppConfig,
    symbols: Iterable[str],
    instrument_type: str,
    bars: Iterable[str],
    strategies: Iterable[str] | None = None,
    start: str | None = None,
    end: str | None = None,
) -> Path:
    payload = run_multi_timeframe_strategy_sweep(
        config,
        symbols,
        instrument_type,
        bars,
        strategies=strategies,
        start=start,
        end=end,
    )
    return write_report(config.report_dir, "multi_timeframe_strategy_sweep", sanitize_for_json(payload))
