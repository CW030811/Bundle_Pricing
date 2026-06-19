from __future__ import annotations

from pathlib import Path

from .config import ExecutionSettings, RiskSettings
from .models import OrderIntent, PortfolioState, RiskDecision


class RiskManager:
    def __init__(self, settings: RiskSettings, execution: ExecutionSettings):
        self.settings = settings
        self.execution = execution

    def kill_switch_active(self) -> bool:
        return Path(self.settings.kill_switch_file).exists()

    def evaluate(self, intent: OrderIntent, portfolio: PortfolioState, mark_price: float) -> RiskDecision:
        if self.kill_switch_active():
            if intent.reduce_only:
                return RiskDecision(True, "approved reduce-only order while kill switch is active")
            return RiskDecision(False, "kill switch is active")
        if intent.quantity <= 0:
            return RiskDecision(False, "order quantity must be positive")
        if intent.leverage > self.settings.max_leverage:
            return RiskDecision(False, f"leverage {intent.leverage} exceeds max {self.settings.max_leverage}")
        if intent.reduce_only:
            return RiskDecision(True, "approved reduce-only order")
        if portfolio.consecutive_losses >= self.settings.max_consecutive_losses:
            return RiskDecision(False, "consecutive loss limit reached")
        effective_equity = min(portfolio.equity, self.settings.live_trading_cap_usdt)
        if portfolio.daily_realized_pnl <= -effective_equity * self.settings.max_daily_loss_pct:
            return RiskDecision(False, "daily loss limit reached")

        notional = intent.quantity * mark_price
        max_exposure = effective_equity * self.settings.max_symbol_exposure_pct
        if notional > max_exposure:
            adjusted = max_exposure / mark_price
            if adjusted <= 0:
                return RiskDecision(False, "symbol exposure limit leaves no tradable quantity")
            return RiskDecision(True, "quantity reduced to symbol exposure limit", adjusted_quantity=adjusted)

        max_trade_risk = effective_equity * self.settings.max_risk_per_trade_pct
        assumed_stop_distance = max(mark_price * 0.02, 1e-9)
        risk_amount = intent.quantity * assumed_stop_distance
        if risk_amount > max_trade_risk:
            adjusted = max_trade_risk / assumed_stop_distance
            if adjusted <= 0:
                return RiskDecision(False, "per-trade risk limit leaves no tradable quantity")
            return RiskDecision(True, "quantity reduced to per-trade risk limit", adjusted_quantity=adjusted)

        return RiskDecision(True, "approved")

    def validate_live_allowed(self, mode: str, credentials_present: bool, confirm_live: bool) -> None:
        if mode != "live":
            return
        if not self.execution.live_enabled:
            raise PermissionError("live execution is disabled in config")
        if self.execution.require_confirm_live and not confirm_live:
            raise PermissionError("live execution requires --confirm-live")
        if not credentials_present:
            raise PermissionError("OKX credentials are required for live execution")
