from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal, Optional

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


OKX_DOMAINS = {
    "global": "https://openapi.okx.com",
    "us": "https://us.okx.com",
    "au": "https://us.okx.com",
    "eu": "https://eea.okx.com",
}


class OkxSettings(BaseModel):
    domain: Literal["global", "us", "au", "eu"] = "global"
    demo_trading: bool = True
    timeout_seconds: int = 20
    proxy_url: str = ""
    proxy_url_env: str = "OKX_PROXY_URL"
    api_key_env: str = "OKX_API_KEY"
    api_secret_env: str = "OKX_API_SECRET"
    passphrase_env: str = "OKX_PASSPHRASE"
    demo_api_key_env: str = "OKX_DEMO_API_KEY"
    demo_api_secret_env: str = "OKX_DEMO_API_SECRET"
    demo_passphrase_env: str = "OKX_DEMO_PASSPHRASE"

    @property
    def base_url(self) -> str:
        return OKX_DOMAINS[self.domain]

    @property
    def effective_proxy_url(self) -> str:
        return self.proxy_url or os.getenv(self.proxy_url_env, "")

    def credentials(self) -> "OkxCredentials":
        if self.demo_trading:
            return OkxCredentials(
                api_key=os.getenv(self.demo_api_key_env, ""),
                api_secret=os.getenv(self.demo_api_secret_env, ""),
                passphrase=os.getenv(self.demo_passphrase_env, ""),
                environment="demo",
            )
        return OkxCredentials(
            api_key=os.getenv(self.api_key_env, ""),
            api_secret=os.getenv(self.api_secret_env, ""),
            passphrase=os.getenv(self.passphrase_env, ""),
            environment="production",
        )


class OkxCredentials(BaseModel):
    api_key: str = ""
    api_secret: str = ""
    passphrase: str = ""
    environment: Literal["demo", "production", "custom"] = "custom"

    @property
    def present(self) -> bool:
        return bool(self.api_key and self.api_secret and self.passphrase)


class MarketSettings(BaseModel):
    base_currency: str = "USDT"
    bar: str = "1H"
    symbols: list[str] = Field(default_factory=lambda: ["BTC/USDT", "ETH/USDT"])
    instrument_types: list[Literal["spot", "swap"]] = Field(default_factory=lambda: ["spot", "swap"])
    trade_allowlist: list[str] = Field(default_factory=list)
    trade_blocklist: list[str] = Field(default_factory=list)

    @field_validator("symbols")
    @classmethod
    def validate_symbols(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("at least one symbol is required")
        for symbol in value:
            if "/" not in symbol:
                raise ValueError(f"symbol must use BASE/QUOTE format: {symbol}")
        return value


class StrategySettings(BaseModel):
    name: str = "trend_mr"
    fast_ema: int = 12
    slow_ema: int = 48
    rsi_period: int = 14
    atr_period: int = 14
    bollinger_period: int = 20
    bollinger_std: float = 2.0
    min_volume: float = 0.0


class RiskSettings(BaseModel):
    starting_equity: float = 10_000
    live_trading_cap_usdt: float = 50.0
    max_risk_per_trade_pct: float = 0.005
    max_symbol_exposure_pct: float = 0.20
    max_daily_loss_pct: float = 0.02
    max_consecutive_losses: int = 3
    max_leverage: float = 1.0
    max_portfolio_drawdown_pct: float = 0.05
    max_turnover_per_rebalance_pct: float = 0.50
    kill_switch_file: Path = Path("state/KILL_SWITCH")


class ExecutionSettings(BaseModel):
    fee_rate: float = 0.0008
    slippage_bps: float = 2.0
    live_enabled: bool = False
    require_confirm_live: bool = True
    margin_mode: Literal["cross", "isolated"] = "cross"
    default_order_type: Literal["market", "limit"] = "market"


class BacktestSettings(BaseModel):
    initial_cash: float = 10_000
    benchmark: str = "BTC/USDT"


class ServiceSettings(BaseModel):
    pid_file: Path = Path("state/quant_service.pid")
    watchdog_pid_file: Path = Path("state/quant_watchdog.pid")
    launch_state_file: Path = Path("state/quant_service_launch.json")
    watchdog_launch_state_file: Path = Path("state/quant_watchdog_launch.json")
    stop_file: Path = Path("state/quant_service.stop")
    heartbeat_file: Path = Path("state/quant_service_heartbeat.json")
    watchdog_heartbeat_file: Path = Path("state/quant_watchdog_heartbeat.json")
    log_file: Path = Path("logs/quant_service.log")
    watchdog_log_file: Path = Path("logs/quant_watchdog.log")
    max_consecutive_errors: int = 5
    retry_backoff_seconds: float = 30.0
    log_max_bytes: int = 5_000_000
    log_backup_count: int = 5
    max_candle_age_seconds: float = 7200.0
    rebalance_cooldown_seconds: float = 3600.0
    watchdog_interval_seconds: float = 60.0
    watchdog_max_heartbeat_age_seconds: float = 300.0
    min_free_disk_bytes: int = 100_000_000
    okx_cancel_all_after_seconds: int = 0
    refresh_candles_before_iteration: bool = True
    refresh_candles_limit: int = 300
    event_log_file: Path = Path("logs/quant_events.jsonl")
    notification_log_file: Path = Path("logs/quant_notifications.jsonl")
    notification_webhook_url_env: str = "QUANT_NOTIFICATION_WEBHOOK_URL"
    notification_timeout_seconds: int = 10
    notify_on_orders: bool = True
    notify_on_watchdog_failure: bool = True
    notify_on_kill_switch: bool = True


class AppConfig(BaseModel):
    mode: Literal["paper", "live"] = "paper"
    data_dir: Path = Path("data")
    report_dir: Path = Path("reports")
    state_dir: Path = Path("state")
    log_dir: Path = Path("logs")
    okx: OkxSettings = Field(default_factory=OkxSettings)
    market: MarketSettings = Field(default_factory=MarketSettings)
    strategy: StrategySettings = Field(default_factory=StrategySettings)
    risk: RiskSettings = Field(default_factory=RiskSettings)
    execution: ExecutionSettings = Field(default_factory=ExecutionSettings)
    backtest: BacktestSettings = Field(default_factory=BacktestSettings)
    service: ServiceSettings = Field(default_factory=ServiceSettings)

    @model_validator(mode="after")
    def validate_live_mode(self) -> "AppConfig":
        default_state_paths = {
            "pid_file": Path("state/quant_service.pid"),
            "watchdog_pid_file": Path("state/quant_watchdog.pid"),
            "launch_state_file": Path("state/quant_service_launch.json"),
            "watchdog_launch_state_file": Path("state/quant_watchdog_launch.json"),
            "stop_file": Path("state/quant_service.stop"),
            "heartbeat_file": Path("state/quant_service_heartbeat.json"),
            "watchdog_heartbeat_file": Path("state/quant_watchdog_heartbeat.json"),
        }
        for name, default in default_state_paths.items():
            if getattr(self.service, name) == default:
                setattr(self.service, name, self.state_dir / default.name)
        default_log_paths = {
            "log_file": Path("logs/quant_service.log"),
            "watchdog_log_file": Path("logs/quant_watchdog.log"),
            "event_log_file": Path("logs/quant_events.jsonl"),
            "notification_log_file": Path("logs/quant_notifications.jsonl"),
        }
        for name, default in default_log_paths.items():
            if getattr(self.service, name) == default:
                setattr(self.service, name, self.log_dir / default.name)
        if self.risk.kill_switch_file == Path("state/KILL_SWITCH"):
            self.risk.kill_switch_file = self.state_dir / "KILL_SWITCH"
        if self.mode == "live" and not self.execution.live_enabled:
            # Live config files are allowed to be safe-by-default. Runtime live
            # commands perform the hard failure unless explicitly enabled.
            return self
        return self

    def ensure_dirs(self) -> None:
        for path in [self.data_dir, self.report_dir, self.state_dir, self.log_dir]:
            path.mkdir(parents=True, exist_ok=True)


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_local_env(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_config(config_path: Optional[str | Path] = None) -> AppConfig:
    root = Path.cwd()
    load_local_env(root / ".env")
    default_path = root / "config" / "default.yaml"
    data = load_yaml(default_path)
    if config_path:
        overlay_path = Path(config_path)
        if not overlay_path.is_absolute():
            overlay_path = root / overlay_path
        data = deep_merge(data, load_yaml(overlay_path))
    return AppConfig.model_validate(data)


def okx_inst_id(symbol: str, instrument_type: str) -> str:
    base, quote = symbol.split("/", 1)
    if instrument_type == "swap":
        return f"{base}-{quote}-SWAP"
    return f"{base}-{quote}"


def symbol_from_okx_inst_id(inst_id: str) -> tuple[str, str]:
    parts = inst_id.split("-")
    if len(parts) >= 3 and parts[-1] == "SWAP":
        return f"{parts[0]}/{parts[1]}", "swap"
    return f"{parts[0]}/{parts[1]}", "spot"
