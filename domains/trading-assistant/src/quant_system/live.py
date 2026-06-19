from __future__ import annotations

from dataclasses import replace
import time
from datetime import datetime, timezone
from typing import Iterable

from .broker import OkxBroker, PaperBroker, target_signal_to_order
from .config import AppConfig, okx_inst_id
from .data import filter_confirmed_candles, synthetic_candles
from .events import append_event
from .models import InstrumentType, Order, OrderStatus, OrderType, PortfolioState, Signal, position_key
from .notifications import notify
from .okx import OkxRestClient
from .portfolio import (
    PAPER_PORTFOLIO_STATE_KEY,
    cross_sectional_momentum_targets,
    filter_trade_symbols,
    load_close_matrix,
    load_paper_portfolio,
    save_paper_portfolio,
)
from .risk import RiskManager
from .sizing import find_instrument, round_limit_price, round_order_quantity
from .storage import AuditStore, CandleStore, normalize_okx_candles
from .strategies import build_strategy


def _record_ads_signal_target(audit: AuditStore, config: AppConfig, signal: Signal) -> None:
    risk_limit = {
        "max_symbol_exposure_pct": config.risk.max_symbol_exposure_pct,
        "max_daily_loss_pct": config.risk.max_daily_loss_pct,
        "max_portfolio_drawdown_pct": config.risk.max_portfolio_drawdown_pct,
        "live_trading_cap_usdt": config.risk.live_trading_cap_usdt,
    }
    audit.insert_ads_strategy_signal(signal, interval=config.market.bar)
    audit.insert_ads_target_position(
        signal,
        leverage=config.risk.max_leverage,
        risk_limit=risk_limit,
    )


def _record_ads_risk_status(
    audit: AuditStore,
    signal: Signal,
    decision: object,
    portfolio: PortfolioState,
    current_position: float,
    *,
    drawdown: float | None = None,
    stop_reason: str | None = None,
) -> None:
    approved = bool(getattr(decision, "approved", True)) and stop_reason is None
    reason = stop_reason or str(getattr(decision, "reason", ""))
    daily_loss = abs(portfolio.daily_realized_pnl) if portfolio.daily_realized_pnl < 0 else 0.0
    audit.insert_ads_risk_status(
        strategy_id=signal.strategy,
        exchange="okx",
        symbol=signal.symbol,
        timestamp=datetime.now(timezone.utc),
        current_position=current_position,
        current_drawdown=drawdown,
        daily_loss=daily_loss,
        risk_level="low" if approved else "blocked",
        is_trading_allowed=approved,
        stop_reason=None if approved else reason,
    )


def run_paper_once(config: AppConfig, symbol: str, instrument_type: str, use_synthetic: bool = False) -> dict[str, object]:
    store = CandleStore(config.data_dir)
    candles = store.read(symbol, instrument_type, config.market.bar)
    if candles.empty and use_synthetic:
        candles = synthetic_candles(symbol, instrument_type)
        store.write(candles, symbol, instrument_type, config.market.bar)
    if candles.empty:
        client = OkxRestClient(config.okx)
        candles = normalize_okx_candles(
            client.get_candles(symbol, instrument_type, config.market.bar, 120),
            symbol,
            instrument_type,
        )
        if not candles.empty:
            store.write(candles, symbol, instrument_type, config.market.bar)
    if candles.empty:
        raise RuntimeError("no candles available for paper run")
    candles = filter_confirmed_candles(candles, require_confirmed=True)
    if candles.empty:
        raise RuntimeError("no confirmed candles available for paper run")

    audit = AuditStore(config.state_dir)
    strategy = build_strategy(config.strategy)
    broker = PaperBroker(config)
    risk = RiskManager(config.risk, config.execution)
    latest = candles.iloc[-1]
    mark = float(latest["close"])
    inst_type = InstrumentType(instrument_type)
    signal = strategy.generate(candles, symbol, inst_type)
    audit.insert_signal(signal)
    _record_ads_signal_target(audit, config, signal)
    portfolio = broker.portfolio({symbol: mark, position_key(symbol, inst_type): mark})
    position = portfolio.position_for(symbol, inst_type)
    intent = target_signal_to_order(signal.target_pct, symbol, inst_type, position.quantity, portfolio.equity, mark)
    if intent is None:
        _record_ads_risk_status(audit, signal, object(), portfolio, position.quantity)
        return {"signal": signal, "order": None, "message": "target already satisfied or below minimum size"}
    decision = risk.evaluate(intent, portfolio, mark)
    audit.insert_risk_event(intent, decision)
    _record_ads_risk_status(audit, signal, decision, portfolio, position.quantity)
    if not decision.approved:
        return {"signal": signal, "order": None, "message": decision.reason}
    if decision.adjusted_quantity:
        intent = replace(intent, quantity=decision.adjusted_quantity)
    order = broker.submit_order(intent, mark)
    audit.insert_order(order)
    audit.upsert_position(broker.portfolio({symbol: mark}).position_for(symbol, inst_type))
    return {"signal": signal, "order": order, "message": "paper order submitted"}


def validate_live(config: AppConfig, confirm_live: bool) -> None:
    client = OkxRestClient(config.okx)
    risk = RiskManager(config.risk, config.execution)
    OkxBroker(config, client, risk, confirm_live=confirm_live)


def run_okx_live_portfolio_once(
    config: AppConfig,
    symbols: Iterable[str],
    instrument_type: str = "spot",
    lookback_bars: int = 24 * 30,
    top_n: int = 2,
    min_momentum: float = 0.0,
    allowlist: Iterable[str] | None = None,
    blocklist: Iterable[str] | None = None,
    max_turnover_pct: float | None = None,
    max_candle_age_seconds: float | None = None,
    rebalance_cooldown_seconds: float | None = None,
    confirm_live: bool = False,
    order_type: str | None = None,
    client: OkxRestClient | None = None,
) -> dict[str, object]:
    config.mode = "live"
    config.okx.demo_trading = False
    audit = AuditStore(config.state_dir)
    inst_type = InstrumentType(instrument_type)
    symbol_list = filter_trade_symbols(
        symbols,
        allowlist=allowlist or config.market.trade_allowlist,
        blocklist=blocklist or config.market.trade_blocklist,
    )
    if len(symbol_list) < 2:
        raise RuntimeError("live portfolio requires at least two tradable symbols after filters")
    client = client or OkxRestClient(config.okx)
    risk = RiskManager(config.risk, config.execution)
    broker = OkxBroker(config, client, risk, confirm_live=confirm_live)
    closes = load_close_matrix(config, symbol_list, instrument_type, confirmed_only=True)
    target_info = cross_sectional_momentum_targets(closes, lookback_bars, top_n, min_momentum=min_momentum)
    latest_ts = target_info["ts"].to_pydatetime()
    if latest_ts.tzinfo is None:
        latest_ts = latest_ts.replace(tzinfo=timezone.utc)
    latest_ts = latest_ts.astimezone(timezone.utc)
    candle_age_seconds = (datetime.now(timezone.utc) - latest_ts).total_seconds()
    stale_limit = config.service.max_candle_age_seconds if max_candle_age_seconds is None else max_candle_age_seconds
    if stale_limit and candle_age_seconds > stale_limit:
        result = {
            "strategy": "cross_sectional_momentum_live_portfolio",
            "instrument_type": instrument_type,
            "selected": [],
            "orders": [],
            "messages": [f"stale candle data: age={candle_age_seconds:.1f}s, limit={stale_limit:.1f}s"],
            "stale_data": True,
            "confirmed_only": True,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        audit.set_state("live_portfolio_last_run", result)
        append_event(config, "live_portfolio_stale_data", result)
        notify(config, "live_portfolio_stale_data", "warning", result)
        return result

    prices = dict(target_info["prices"])
    for symbol, price in list(prices.items()):
        prices[position_key(symbol, inst_type)] = price
    account_instruments = client.get_account_instruments(instrument_type)
    portfolio = broker.portfolio(prices)
    effective_capital = min(portfolio.equity, config.risk.live_trading_cap_usdt)
    max_symbol_notional = effective_capital * config.risk.max_symbol_exposure_pct

    cooldown_seconds = (
        config.service.rebalance_cooldown_seconds if rebalance_cooldown_seconds is None else rebalance_cooldown_seconds
    )
    last_rebalance = audit.get_state("live_portfolio_last_rebalance", {})
    cooldown_active = False
    cooldown_remaining_seconds = 0.0
    if cooldown_seconds and isinstance(last_rebalance, dict) and last_rebalance.get("ts"):
        last_ts = datetime.fromisoformat(str(last_rebalance["ts"]).replace("Z", "+00:00"))
        if last_ts.tzinfo is None:
            last_ts = last_ts.replace(tzinfo=timezone.utc)
        elapsed = (datetime.now(timezone.utc) - last_ts.astimezone(timezone.utc)).total_seconds()
        cooldown_remaining_seconds = max(cooldown_seconds - elapsed, 0.0)
        cooldown_active = cooldown_remaining_seconds > 0

    selected = list(target_info["selected"])
    target_pct_by_symbol = {
        symbol: (max_symbol_notional / portfolio.equity if portfolio.equity else 0.0) for symbol in selected
    }
    turnover_limit = max_turnover_pct if max_turnover_pct is not None else config.risk.max_turnover_per_rebalance_pct
    turnover_budget = max(effective_capital * max(turnover_limit, 0.0), 0.0)
    turnover_used = 0.0
    order_mode = order_type or config.execution.default_order_type
    orders: list[dict[str, object]] = []
    messages: list[str] = []
    if cooldown_active:
        messages.append(f"rebalance cooldown active: remaining={cooldown_remaining_seconds:.1f}s")

    held_symbols = [position.symbol for position in portfolio.positions.values() if abs(position.quantity) > 0]
    exit_symbols = sorted(symbol for symbol in held_symbols if symbol not in selected)
    entry_symbols = sorted(symbol for symbol in selected if symbol not in exit_symbols)
    other_symbols = sorted((set(symbol_list) | set(held_symbols)) - set(exit_symbols) - set(entry_symbols))
    for symbol in exit_symbols + entry_symbols + other_symbols:
        if symbol not in prices:
            continue
        mark = float(prices[symbol])
        target_pct = target_pct_by_symbol.get(symbol, 0.0)
        signal = Signal(
            symbol=symbol,
            instrument_type=inst_type,
            ts=target_info["ts"].to_pydatetime(),
            target_pct=target_pct,
            confidence=0.70 if symbol in selected else 0.50,
            reason=(
                f"cross-sectional momentum selected rank={target_info['rank'].get(symbol):.6f}"
                if symbol in selected
                else "not selected by cross-sectional momentum"
            ),
            strategy="cross_sectional_momentum_live_portfolio",
        )
        audit.insert_signal(signal)
        _record_ads_signal_target(audit, config, signal)
        current = broker.portfolio(prices).position_for(symbol, inst_type)
        intent = target_signal_to_order(target_pct, symbol, inst_type, current.quantity, portfolio.equity, mark)
        if intent is None:
            _record_ads_risk_status(audit, signal, object(), broker.portfolio(prices), current.quantity)
            continue
        intent = replace(intent, source_signal=signal)
        if cooldown_active and not intent.reduce_only:
            messages.append(f"{symbol}: skipped by rebalance cooldown")
            _record_ads_risk_status(
                audit,
                signal,
                object(),
                broker.portfolio(prices),
                current.quantity,
                stop_reason="rebalance cooldown active",
            )
            continue
        order_notional = intent.quantity * mark
        increases_exposure = not intent.reduce_only and target_pct > 0
        if increases_exposure:
            remaining_turnover = max(turnover_budget - turnover_used, 0.0)
            if remaining_turnover <= 0:
                messages.append(f"{symbol}: skipped by turnover budget")
                _record_ads_risk_status(
                    audit,
                    signal,
                    object(),
                    broker.portfolio(prices),
                    current.quantity,
                    stop_reason="turnover budget exhausted",
                )
                continue
            if order_notional > remaining_turnover:
                intent = replace(intent, quantity=remaining_turnover / mark)
                order_notional = remaining_turnover
        decision = risk.evaluate(intent, broker.portfolio(prices), mark)
        audit.insert_risk_event(intent, decision)
        _record_ads_risk_status(audit, signal, decision, broker.portfolio(prices), current.quantity)
        if not decision.approved:
            messages.append(f"{symbol}: {decision.reason}")
            continue
        if decision.adjusted_quantity:
            intent = replace(intent, quantity=decision.adjusted_quantity)
        instrument = find_instrument(account_instruments, okx_inst_id(symbol, instrument_type))
        quantity = round_order_quantity(intent.quantity, instrument)
        api_price = None
        if order_mode == "limit":
            api_price = round_limit_price(mark * (0.995 if intent.side.value == "buy" else 1.005), instrument)
            intent = replace(intent, order_type=OrderType.LIMIT, price=float(api_price), quantity=float(quantity))
        else:
            intent = replace(intent, order_type=OrderType.MARKET, quantity=float(quantity))
        order = broker.submit_order(intent, mark)
        if increases_exposure:
            turnover_used += order_notional
        audit.insert_order(order)
        orders.append(
            {
                "symbol": symbol,
                "side": intent.side.value,
                "quantity": quantity,
                "order_type": intent.order_type.value,
                "price": api_price,
                "status": order.status.value,
                "exchange_order_id": order.exchange_order_id,
                "message": order.message,
            }
        )

    result = {
        "strategy": "cross_sectional_momentum_live_portfolio",
        "instrument_type": instrument_type,
        "lookback_bars": lookback_bars,
        "top_n": top_n,
        "selected": selected,
        "orders": orders,
        "messages": messages,
        "turnover_budget": turnover_budget,
        "turnover_used": turnover_used,
        "stale_data": False,
        "confirmed_only": True,
        "cooldown_active": cooldown_active,
        "cooldown_remaining_seconds": cooldown_remaining_seconds,
        "portfolio_equity": portfolio.equity,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    audit.set_state("live_portfolio_last_run", result)
    if orders:
        audit.set_state("live_portfolio_last_rebalance", {"ts": result["ts"], "orders": orders})
    append_event(config, "live_portfolio_run", result)
    if orders and config.service.notify_on_orders:
        notify(config, "live_portfolio_orders", "critical", result)
    return result


def run_paper_portfolio_once(
    config: AppConfig,
    symbols: Iterable[str],
    instrument_type: str = "spot",
    lookback_bars: int = 24 * 30,
    top_n: int = 2,
    min_momentum: float = 0.0,
    allowlist: Iterable[str] | None = None,
    blocklist: Iterable[str] | None = None,
    max_turnover_pct: float | None = None,
    max_portfolio_drawdown_pct: float | None = None,
    max_candle_age_seconds: float | None = None,
    rebalance_cooldown_seconds: float | None = None,
) -> dict[str, object]:
    audit = AuditStore(config.state_dir)
    inst_type = InstrumentType(instrument_type)
    symbol_list = filter_trade_symbols(
        symbols,
        allowlist=allowlist or config.market.trade_allowlist,
        blocklist=blocklist or config.market.trade_blocklist,
    )
    if len(symbol_list) < 2:
        raise RuntimeError("paper portfolio requires at least two tradable symbols after filters")
    closes = load_close_matrix(config, symbol_list, instrument_type, confirmed_only=True)
    target_info = cross_sectional_momentum_targets(closes, lookback_bars, top_n, min_momentum=min_momentum)
    latest_ts = target_info["ts"].to_pydatetime()
    if latest_ts.tzinfo is None:
        latest_ts = latest_ts.replace(tzinfo=timezone.utc)
    latest_ts = latest_ts.astimezone(timezone.utc)
    candle_age_seconds = (datetime.now(timezone.utc) - latest_ts).total_seconds()
    stale_limit = config.service.max_candle_age_seconds if max_candle_age_seconds is None else max_candle_age_seconds
    if stale_limit and candle_age_seconds > stale_limit:
        result = {
            "strategy": "cross_sectional_momentum_portfolio",
            "instrument_type": instrument_type,
            "lookback_bars": lookback_bars,
            "top_n": top_n,
            "selected": [],
            "orders": [],
            "messages": [f"stale candle data: age={candle_age_seconds:.1f}s, limit={stale_limit:.1f}s"],
            "stale_data": True,
            "confirmed_only": True,
            "candle_age_seconds": candle_age_seconds,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        audit.set_state("paper_portfolio_last_run", result)
        append_event(config, "paper_portfolio_stale_data", result)
        notify(config, "paper_portfolio_stale_data", "warning", result)
        return result
    prices = dict(target_info["prices"])
    for symbol, price in list(prices.items()):
        prices[position_key(symbol, inst_type)] = price

    state_payload = audit.get_state(PAPER_PORTFOLIO_STATE_KEY, {})
    state = load_paper_portfolio(audit, config.backtest.initial_cash)
    broker = PaperBroker(config, initial_portfolio=state)
    risk = RiskManager(config.risk, config.execution)
    portfolio = broker.portfolio(prices)
    cooldown_seconds = (
        config.service.rebalance_cooldown_seconds if rebalance_cooldown_seconds is None else rebalance_cooldown_seconds
    )
    last_rebalance = audit.get_state("paper_portfolio_last_rebalance", {})
    cooldown_active = False
    cooldown_remaining_seconds = 0.0
    if cooldown_seconds and isinstance(last_rebalance, dict) and last_rebalance.get("ts"):
        last_ts = datetime.fromisoformat(str(last_rebalance["ts"]).replace("Z", "+00:00"))
        if last_ts.tzinfo is None:
            last_ts = last_ts.replace(tzinfo=timezone.utc)
        elapsed = (datetime.now(timezone.utc) - last_ts.astimezone(timezone.utc)).total_seconds()
        cooldown_remaining_seconds = max(cooldown_seconds - elapsed, 0.0)
        cooldown_active = cooldown_remaining_seconds > 0
    prior_high_watermark = float(state_payload.get("high_watermark", portfolio.equity)) if state_payload else portfolio.equity
    high_watermark = max(prior_high_watermark, portfolio.equity)
    drawdown = portfolio.equity / high_watermark - 1 if high_watermark else 0.0
    drawdown_limit = max_portfolio_drawdown_pct
    if drawdown_limit is None:
        drawdown_limit = config.risk.max_portfolio_drawdown_pct
    effective_capital = min(portfolio.equity, config.risk.live_trading_cap_usdt)
    max_symbol_notional = effective_capital * config.risk.max_symbol_exposure_pct
    selected = list(target_info["selected"])
    circuit_breaker = drawdown <= -abs(drawdown_limit)
    if circuit_breaker:
        selected = []
    target_pct_by_symbol = {
        symbol: (max_symbol_notional / portfolio.equity if portfolio.equity else 0.0) for symbol in selected
    }
    turnover_limit = max_turnover_pct
    if turnover_limit is None:
        turnover_limit = config.risk.max_turnover_per_rebalance_pct
    turnover_budget = max(effective_capital * max(turnover_limit, 0.0), 0.0)
    turnover_used = 0.0

    orders: list[dict[str, object]] = []
    messages: list[str] = []
    if cooldown_active:
        messages.append(f"rebalance cooldown active: remaining={cooldown_remaining_seconds:.1f}s")
    if circuit_breaker:
        messages.append(f"portfolio drawdown breaker active: drawdown={drawdown:.4f}, limit={-abs(drawdown_limit):.4f}")
    held_symbols = [position.symbol for position in portfolio.positions.values() if abs(position.quantity) > 0]
    exit_symbols = sorted(symbol for symbol in held_symbols if symbol not in selected)
    entry_symbols = sorted(symbol for symbol in selected if symbol not in exit_symbols)
    other_symbols = sorted((set(symbol_list) | set(held_symbols)) - set(exit_symbols) - set(entry_symbols))
    trade_symbols = exit_symbols + entry_symbols + other_symbols
    for symbol in trade_symbols:
        if symbol not in prices:
            continue
        mark = float(prices[symbol])
        target_pct = target_pct_by_symbol.get(symbol, 0.0)
        signal = Signal(
            symbol=symbol,
            instrument_type=inst_type,
            ts=target_info["ts"].to_pydatetime(),
            target_pct=target_pct,
            confidence=0.70 if symbol in selected else 0.50,
            reason=(
                f"cross-sectional momentum selected rank={target_info['rank'].get(symbol):.6f}"
                if symbol in selected
                else "not selected by cross-sectional momentum"
            ),
            strategy="cross_sectional_momentum_portfolio",
        )
        audit.insert_signal(signal)
        _record_ads_signal_target(audit, config, signal)
        position = broker.portfolio(prices).position_for(symbol, inst_type)
        intent = target_signal_to_order(target_pct, symbol, inst_type, position.quantity, portfolio.equity, mark)
        if intent is None:
            _record_ads_risk_status(audit, signal, object(), broker.portfolio(prices), position.quantity, drawdown=drawdown)
            continue
        intent = replace(intent, source_signal=signal)
        if cooldown_active and not intent.reduce_only:
            messages.append(f"{symbol}: skipped by rebalance cooldown")
            _record_ads_risk_status(
                audit,
                signal,
                object(),
                broker.portfolio(prices),
                position.quantity,
                drawdown=drawdown,
                stop_reason="rebalance cooldown active",
            )
            continue
        order_notional = intent.quantity * mark
        increases_exposure = not intent.reduce_only and target_pct > 0
        if increases_exposure:
            remaining_turnover = max(turnover_budget - turnover_used, 0.0)
            if remaining_turnover <= 0:
                messages.append(f"{symbol}: skipped by turnover budget")
                _record_ads_risk_status(
                    audit,
                    signal,
                    object(),
                    broker.portfolio(prices),
                    position.quantity,
                    drawdown=drawdown,
                    stop_reason="turnover budget exhausted",
                )
                continue
            if order_notional > remaining_turnover:
                adjusted_quantity = remaining_turnover / mark
                if adjusted_quantity <= 0:
                    messages.append(f"{symbol}: turnover budget leaves no tradable quantity")
                    _record_ads_risk_status(
                        audit,
                        signal,
                        object(),
                        broker.portfolio(prices),
                        position.quantity,
                        drawdown=drawdown,
                        stop_reason="turnover budget leaves no tradable quantity",
                    )
                    continue
                intent = replace(intent, quantity=adjusted_quantity)
                order_notional = remaining_turnover
        decision = risk.evaluate(intent, broker.portfolio(prices), mark)
        audit.insert_risk_event(intent, decision)
        _record_ads_risk_status(audit, signal, decision, broker.portfolio(prices), position.quantity, drawdown=drawdown)
        if not decision.approved:
            messages.append(f"{symbol}: {decision.reason}")
            continue
        if decision.adjusted_quantity:
            intent = replace(intent, quantity=decision.adjusted_quantity)
        order = broker.submit_order(intent, mark)
        if increases_exposure:
            turnover_used += order_notional
        audit.insert_order(order)
        audit.upsert_position(broker.portfolio(prices).position_for(symbol, inst_type))
        orders.append(
            {
                "symbol": symbol,
                "side": intent.side.value,
                "quantity": order.filled_quantity,
                "average_price": order.average_price,
                "status": order.status.value,
                "message": order.message,
            }
        )

    final_portfolio = broker.portfolio(prices)
    final_high_watermark = max(high_watermark, final_portfolio.equity)
    final_drawdown = final_portfolio.equity / final_high_watermark - 1 if final_high_watermark else 0.0
    portfolio_payload = save_paper_portfolio(
        audit,
        final_portfolio,
        prices,
        metadata={
            "high_watermark": final_high_watermark,
            "drawdown": final_drawdown,
        },
    )
    result = {
        "strategy": "cross_sectional_momentum_portfolio",
        "instrument_type": instrument_type,
        "lookback_bars": lookback_bars,
        "top_n": top_n,
        "min_momentum": min_momentum,
        "allowlist": list(allowlist or config.market.trade_allowlist),
        "blocklist": list(blocklist or config.market.trade_blocklist),
        "max_turnover_pct": turnover_limit,
        "turnover_budget": turnover_budget,
        "turnover_used": turnover_used,
        "drawdown": drawdown,
        "max_portfolio_drawdown_pct": drawdown_limit,
        "circuit_breaker": circuit_breaker,
        "stale_data": False,
        "confirmed_only": True,
        "candle_age_seconds": candle_age_seconds,
        "cooldown_active": cooldown_active,
        "cooldown_remaining_seconds": cooldown_remaining_seconds,
        "selected": selected,
        "rank": target_info["rank"],
        "orders": orders,
        "messages": messages,
        "portfolio": portfolio_payload,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    audit.set_state("paper_portfolio_last_run", result)
    if orders:
        audit.set_state("paper_portfolio_last_rebalance", {"ts": result["ts"], "orders": orders})
    append_event(
        config,
        "paper_portfolio_run",
        {
            "selected": selected,
            "orders": orders,
            "messages": messages,
            "circuit_breaker": circuit_breaker,
            "stale_data": False,
            "cooldown_active": cooldown_active,
            "portfolio_equity": portfolio_payload.get("equity"),
        },
    )
    if orders and config.service.notify_on_orders:
        notify(
            config,
            "paper_portfolio_orders",
            "info",
            {
                "selected": selected,
                "orders": orders,
                "portfolio_equity": portfolio_payload.get("equity"),
                "turnover_used": turnover_used,
            },
        )
    return result


def demo_portfolio_from_balance(client: OkxRestClient, config: AppConfig) -> PortfolioState:
    balance = client.get_balance()
    details = balance.get("data", [{}])[0].get("details", [])
    equity = 0.0
    for item in details:
        if item.get("ccy") == config.market.base_currency:
            equity = float(item.get("eq", 0) or item.get("cashBal", 0) or 0)
            break
    if equity <= 0:
        equity = config.risk.live_trading_cap_usdt
    return PortfolioState(cash=equity, equity=equity)


def current_swap_quantity(client: OkxRestClient, symbol: str, instrument_type: InstrumentType) -> float:
    if instrument_type != InstrumentType.SWAP:
        return 0.0
    positions = client.get_positions(symbol, instrument_type.value)
    quantity = 0.0
    for position in positions:
        pos = float(position.get("pos", 0) or 0)
        pos_side = position.get("posSide")
        if pos_side == "short":
            quantity -= abs(pos)
        else:
            quantity += pos
    return quantity


def run_okx_demo_once(
    config: AppConfig,
    symbol: str,
    instrument_type: str,
    confirm_demo_order: bool = False,
    order_type: str = "limit",
    cancel_after_place: bool = False,
) -> dict[str, object]:
    config.okx.demo_trading = True
    client = OkxRestClient(config.okx)
    if not client.credentials.present:
        raise PermissionError("demo run requires OKX_DEMO_API_KEY, OKX_DEMO_API_SECRET, and OKX_DEMO_PASSPHRASE")

    store = CandleStore(config.data_dir)
    rows = client.get_candles(symbol, instrument_type, config.market.bar, 160)
    candles = normalize_okx_candles(rows, symbol, instrument_type)
    if candles.empty:
        raise RuntimeError("no OKX candles available for demo run")
    store.write(candles, symbol, instrument_type, config.market.bar)
    signal_candles = filter_confirmed_candles(candles, require_confirmed=True)
    if signal_candles.empty:
        raise RuntimeError("no confirmed OKX candles available for demo run")

    audit = AuditStore(config.state_dir)
    strategy = build_strategy(config.strategy)
    risk = RiskManager(config.risk, config.execution)
    inst_type = InstrumentType(instrument_type)
    signal = strategy.generate(signal_candles, symbol, inst_type)
    audit.insert_signal(signal)
    _record_ads_signal_target(audit, config, signal)

    latest = signal_candles.iloc[-1]
    mark = float(latest["close"])
    portfolio = demo_portfolio_from_balance(client, config)
    current_quantity = current_swap_quantity(client, symbol, inst_type)
    intent = target_signal_to_order(signal.target_pct, symbol, inst_type, current_quantity, portfolio.equity, mark)
    if intent is None:
        _record_ads_risk_status(audit, signal, object(), portfolio, current_quantity)
        return {"signal": signal, "order": None, "message": "target already satisfied or below minimum size"}

    decision = risk.evaluate(intent, portfolio, mark)
    audit.insert_risk_event(intent, decision)
    _record_ads_risk_status(audit, signal, decision, portfolio, current_quantity)
    if not decision.approved:
        return {"signal": signal, "order": None, "message": decision.reason}
    if decision.adjusted_quantity:
        intent = replace(intent, quantity=decision.adjusted_quantity)

    account_instruments = client.get_account_instruments(instrument_type)
    instrument = find_instrument(account_instruments, okx_inst_id(symbol, instrument_type))
    quantity = round_order_quantity(intent.quantity, instrument)
    api_price = None
    if order_type == "limit":
        price_multiplier = 0.995 if intent.side.value == "buy" else 1.005
        api_price = round_limit_price(mark * price_multiplier, instrument)
        intent = replace(intent, order_type=OrderType.LIMIT, price=float(api_price), quantity=float(quantity))
    else:
        intent = replace(intent, order_type=OrderType.MARKET, quantity=float(quantity))

    planned = {
        "symbol": symbol,
        "instrument_type": instrument_type,
        "side": intent.side.value,
        "order_type": intent.order_type.value,
        "quantity": quantity,
        "price": api_price,
        "mark_price": mark,
        "target_pct": signal.target_pct,
        "confidence": signal.confidence,
        "reason": signal.reason,
        "confirm_required": not confirm_demo_order,
        "confirmed_only": True,
        "signal_ts": latest["ts"].isoformat(),
    }
    if not confirm_demo_order:
        return {"signal": signal, "order": None, "planned_order": planned, "message": "demo order planned only"}

    response = client.place_order(
        symbol=symbol,
        instrument_type=instrument_type,
        side=intent.side.value,
        quantity=quantity,
        order_type=intent.order_type.value,
        price=api_price,
        client_order_id=intent.client_order_id,
        reduce_only=intent.reduce_only,
        margin_mode=config.execution.margin_mode,
    )
    data = response.get("data", [{}])[0]
    order = Order(
        intent=intent,
        status=OrderStatus.REJECTED if data.get("sCode") not in (None, "0") else OrderStatus.NEW,
        created_at=datetime.now(timezone.utc),
        exchange_order_id=data.get("ordId"),
        message=data.get("sMsg", ""),
    )
    audit.insert_order(order)
    cancel_response = None
    if cancel_after_place and order.exchange_order_id:
        cancel_response = client.cancel_order(symbol, instrument_type, order_id=order.exchange_order_id)
    return {
        "signal": signal,
        "order": order,
        "planned_order": planned,
        "place_response": response,
        "cancel_response": cancel_response,
        "message": "demo order submitted",
    }


def run_okx_demo_loop(
    config: AppConfig,
    symbol: str,
    instrument_type: str,
    interval_seconds: float,
    max_iterations: int,
    confirm_demo_order: bool = False,
    order_type: str = "limit",
    cancel_after_place: bool = False,
) -> list[dict[str, object]]:
    if max_iterations < 1:
        raise ValueError("max_iterations must be >= 1")
    if interval_seconds < 0:
        raise ValueError("interval_seconds must be >= 0")
    audit = AuditStore(config.state_dir)
    results: list[dict[str, object]] = []
    for index in range(max_iterations):
        started_at = datetime.now(timezone.utc).isoformat()
        try:
            result = run_okx_demo_once(
                config,
                symbol,
                instrument_type,
                confirm_demo_order=confirm_demo_order,
                order_type=order_type,
                cancel_after_place=cancel_after_place,
            )
            item = {
                "iteration": index + 1,
                "started_at": started_at,
                "ok": True,
                "message": result.get("message"),
                "planned_order": result.get("planned_order"),
            }
        except Exception as exc:
            item = {
                "iteration": index + 1,
                "started_at": started_at,
                "ok": False,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
        results.append(item)
        audit.set_state(
            "okx_demo_loop",
            {
                "symbol": symbol,
                "instrument_type": instrument_type,
                "last_iteration": index + 1,
                "last_result": item,
                "confirm_demo_order": confirm_demo_order,
            },
        )
        if index < max_iterations - 1 and interval_seconds:
            time.sleep(interval_seconds)
    return results
