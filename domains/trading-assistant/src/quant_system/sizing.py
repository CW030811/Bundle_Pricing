from __future__ import annotations

from decimal import Decimal, ROUND_DOWN, ROUND_UP


def decimal_from(value: object, default: str = "0") -> Decimal:
    if value is None or value == "":
        return Decimal(default)
    return Decimal(str(value))


def round_step(value: Decimal, step: Decimal, rounding: str) -> Decimal:
    if step <= 0:
        return value
    units = (value / step).to_integral_value(rounding=rounding)
    return units * step


def round_order_quantity(raw_quantity: float, instrument: dict[str, object]) -> str:
    min_size = decimal_from(instrument.get("minSz"), "0")
    lot_size = decimal_from(instrument.get("lotSz"), "0.00000001")
    quantity = max(Decimal(str(raw_quantity)), min_size)
    quantity = round_step(quantity, lot_size, ROUND_UP)
    return format(quantity.normalize(), "f")


def round_limit_price(raw_price: float, instrument: dict[str, object]) -> str:
    tick_size = decimal_from(instrument.get("tickSz"), "0.01")
    price = round_step(Decimal(str(raw_price)), tick_size, ROUND_DOWN)
    if price <= 0:
        price = tick_size
    return format(price.normalize(), "f")


def find_instrument(instruments: list[dict[str, object]], inst_id: str) -> dict[str, object]:
    for instrument in instruments:
        if instrument.get("instId") == inst_id:
            return instrument
    raise LookupError(f"instrument not available for account: {inst_id}")
