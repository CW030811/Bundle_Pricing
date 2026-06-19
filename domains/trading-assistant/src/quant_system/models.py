from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class InstrumentType(str, Enum):
    SPOT = "spot"
    SWAP = "swap"


class OrderStatus(str, Enum):
    NEW = "new"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"


@dataclass(frozen=True)
class Candle:
    ts: datetime
    symbol: str
    instrument_type: InstrumentType
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class Signal:
    symbol: str
    instrument_type: InstrumentType
    ts: datetime
    target_pct: float
    confidence: float
    reason: str
    strategy: str = "trend_mr"


@dataclass(frozen=True)
class OrderIntent:
    symbol: str
    instrument_type: InstrumentType
    side: Side
    quantity: float
    order_type: OrderType = OrderType.MARKET
    price: Optional[float] = None
    reduce_only: bool = False
    leverage: float = 1.0
    client_order_id: str = field(default_factory=lambda: f"qa{uuid4().hex[:24]}")
    source_signal: Optional[Signal] = None


@dataclass
class Order:
    intent: OrderIntent
    status: OrderStatus
    created_at: datetime
    filled_quantity: float = 0.0
    average_price: Optional[float] = None
    exchange_order_id: Optional[str] = None
    message: str = ""


@dataclass
class Position:
    symbol: str
    instrument_type: InstrumentType
    quantity: float = 0.0
    average_entry: float = 0.0
    realized_pnl: float = 0.0

    @property
    def side(self) -> str:
        if self.quantity > 0:
            return "long"
        if self.quantity < 0:
            return "short"
        return "flat"

    def market_value(self, price: float) -> float:
        return self.quantity * price


@dataclass
class PortfolioState:
    cash: float
    equity: float
    positions: dict[str, Position] = field(default_factory=dict)
    daily_realized_pnl: float = 0.0
    consecutive_losses: int = 0

    def position_for(self, symbol: str, instrument_type: InstrumentType) -> Position:
        key = position_key(symbol, instrument_type)
        if key not in self.positions:
            self.positions[key] = Position(symbol=symbol, instrument_type=instrument_type)
        return self.positions[key]


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    reason: str
    adjusted_quantity: Optional[float] = None


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def position_key(symbol: str, instrument_type: InstrumentType) -> str:
    return f"{instrument_type.value}:{symbol}"


def dataclass_to_dict(value: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name in getattr(value, "__dataclass_fields__", {}):
        item = getattr(value, name)
        if isinstance(item, Enum):
            result[name] = item.value
        elif isinstance(item, datetime):
            result[name] = item.isoformat()
        elif hasattr(item, "__dataclass_fields__"):
            result[name] = dataclass_to_dict(item)
        else:
            result[name] = item
    return result
