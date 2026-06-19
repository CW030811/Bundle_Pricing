from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from .config import AppConfig
from .models import InstrumentType, Order, OrderIntent, OrderStatus, PortfolioState, Side, Position, position_key
from .okx import OkxRestClient
from .risk import RiskManager


class Broker:
    def submit_order(self, intent: OrderIntent, mark_price: float) -> Order:
        raise NotImplementedError

    def portfolio(self, prices: Optional[dict[str, float]] = None) -> PortfolioState:
        raise NotImplementedError


class PaperBroker(Broker):
    def __init__(self, config: AppConfig, initial_portfolio: Optional[PortfolioState] = None):
        self.config = config
        self._portfolio = initial_portfolio or PortfolioState(
            cash=config.backtest.initial_cash,
            equity=config.backtest.initial_cash,
            positions={},
        )
        self.orders: list[Order] = []

    def portfolio(self, prices: Optional[dict[str, float]] = None) -> PortfolioState:
        equity = self._portfolio.cash
        prices = prices or {}
        for key, position in self._portfolio.positions.items():
            mark = prices.get(key) or prices.get(position.symbol) or position.average_entry
            equity += position.quantity * mark
        self._portfolio.equity = equity
        return self._portfolio

    def submit_order(self, intent: OrderIntent, mark_price: float) -> Order:
        fill_price = self._fill_price(intent.side, mark_price)
        fee = abs(intent.quantity * fill_price) * self.config.execution.fee_rate
        position = self._portfolio.position_for(intent.symbol, intent.instrument_type)

        realized = 0.0
        if intent.side == Side.BUY:
            self._portfolio.cash -= intent.quantity * fill_price + fee
            if position.quantity < 0:
                close_qty = min(abs(position.quantity), intent.quantity)
                realized = (position.average_entry - fill_price) * close_qty
            new_qty = position.quantity + intent.quantity
        else:
            self._portfolio.cash += intent.quantity * fill_price - fee
            if position.quantity > 0:
                close_qty = min(position.quantity, intent.quantity)
                realized = (fill_price - position.average_entry) * close_qty
            new_qty = position.quantity - intent.quantity

        if position.quantity == 0 or (position.quantity > 0) == (new_qty > 0):
            old_notional = abs(position.quantity) * position.average_entry
            new_notional = intent.quantity * fill_price
            total_qty = abs(position.quantity) + intent.quantity
            position.average_entry = (old_notional + new_notional) / total_qty if total_qty else 0.0
        elif new_qty == 0:
            position.average_entry = 0.0
        else:
            position.average_entry = fill_price

        position.quantity = new_qty
        position.realized_pnl += realized - fee
        self._portfolio.daily_realized_pnl += realized - fee
        if realized - fee < 0:
            self._portfolio.consecutive_losses += 1
        elif realized - fee > 0:
            self._portfolio.consecutive_losses = 0

        order = Order(
            intent=intent,
            status=OrderStatus.FILLED,
            created_at=datetime.now(timezone.utc),
            filled_quantity=intent.quantity,
            average_price=fill_price,
            message="paper fill",
        )
        self.orders.append(order)
        self.portfolio({intent.symbol: mark_price})
        return order

    def _fill_price(self, side: Side, mark_price: float) -> float:
        slippage = self.config.execution.slippage_bps / 10_000
        return mark_price * (1 + slippage if side == Side.BUY else 1 - slippage)


class OkxBroker(Broker):
    def __init__(self, config: AppConfig, client: OkxRestClient, risk: RiskManager, confirm_live: bool = False):
        self.config = config
        self.client = client
        risk.validate_live_allowed(config.mode, client.credentials.present, confirm_live)

    def portfolio(self, prices: Optional[dict[str, float]] = None) -> PortfolioState:
        prices = prices or {}
        balance = self.client.get_balance()
        details = balance.get("data", [{}])[0].get("details", [])
        cash = 0.0
        positions: dict[str, Position] = {}
        for item in details:
            currency = str(item.get("ccy") or "")
            quantity = float(item.get("eq", 0) or item.get("cashBal", 0) or item.get("availBal", 0) or 0)
            if currency == self.config.market.base_currency:
                cash = quantity
                continue
            for symbol, mark in prices.items():
                if ":" in symbol:
                    continue
                base, quote = symbol.split("/", 1)
                if quote == self.config.market.base_currency and base == currency and quantity:
                    key = position_key(symbol, InstrumentType.SPOT)
                    positions[key] = Position(
                        symbol=symbol,
                        instrument_type=InstrumentType.SPOT,
                        quantity=quantity,
                        average_entry=float(mark),
                    )
        equity = cash
        for key, position in positions.items():
            mark = prices.get(key) or prices.get(position.symbol) or position.average_entry
            equity += position.quantity * mark
        return PortfolioState(cash=cash, equity=equity, positions=positions)

    def submit_order(self, intent: OrderIntent, mark_price: float) -> Order:
        response = self.client.place_order(
            symbol=intent.symbol,
            instrument_type=intent.instrument_type.value,
            side=intent.side.value,
            quantity=intent.quantity,
            order_type=intent.order_type.value,
            price=intent.price,
            client_order_id=intent.client_order_id,
            reduce_only=intent.reduce_only,
            margin_mode=self.config.execution.margin_mode,
        )
        data = response.get("data", [{}])[0]
        status = OrderStatus.REJECTED if data.get("sCode") not in (None, "0") else OrderStatus.NEW
        return Order(
            intent=intent,
            status=status,
            created_at=datetime.now(timezone.utc),
            exchange_order_id=data.get("ordId"),
            message=data.get("sMsg", ""),
        )


def target_signal_to_order(
    signal_target_pct: float,
    symbol: str,
    instrument_type: InstrumentType,
    current_quantity: float,
    equity: float,
    mark_price: float,
) -> Optional[OrderIntent]:
    target_notional = equity * signal_target_pct
    target_quantity = target_notional / mark_price
    delta = target_quantity - current_quantity
    min_notional = 1.0 if signal_target_pct == 0 and current_quantity else max(5.0, equity * 0.001)
    if abs(delta) * mark_price < min_notional:
        return None
    side = Side.BUY if delta > 0 else Side.SELL
    return OrderIntent(
        symbol=symbol,
        instrument_type=instrument_type,
        side=side,
        quantity=abs(delta),
        reduce_only=(current_quantity > 0 and side == Side.SELL) or (current_quantity < 0 and side == Side.BUY),
    )
