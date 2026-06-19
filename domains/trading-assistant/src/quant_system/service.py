from __future__ import annotations

import json
import logging
import os
import signal
import shutil
import subprocess
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Callable, Iterator, Optional

from .config import AppConfig
from .data import backfill_candles
from .events import append_event, tail_events
from .live import run_okx_demo_once, run_okx_live_portfolio_once, run_paper_portfolio_once
from .models import InstrumentType, OrderIntent, OrderType, PortfolioState, Side
from .notifications import notify, tail_notifications
from .okx import OkxRestClient
from .reports import write_report
from .risk import RiskManager
from .storage import AuditStore


class ServiceLockError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


@contextmanager
def pid_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raw = path.read_text(encoding="utf-8").strip()
        if raw:
            try:
                existing = int(raw)
            except ValueError:
                existing = -1
            if existing > 0 and process_alive(existing):
                raise ServiceLockError(f"service already running with pid {existing}")
    path.write_text(str(os.getpid()), encoding="utf-8")
    try:
        yield
    finally:
        if path.exists() and path.read_text(encoding="utf-8").strip() == str(os.getpid()):
            path.unlink()


def configure_logger(config: AppConfig) -> logging.Logger:
    config.log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("quant_service")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    handler = RotatingFileHandler(
        config.service.log_file,
        maxBytes=config.service.log_max_bytes,
        backupCount=config.service.log_backup_count,
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    return logger


def configure_watchdog_logger(config: AppConfig) -> logging.Logger:
    config.log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("quant_watchdog")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    handler = RotatingFileHandler(
        config.service.watchdog_log_file,
        maxBytes=config.service.log_max_bytes,
        backupCount=config.service.log_backup_count,
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    return logger


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def read_json(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            rows.append({"event": "malformed_jsonl_line", "raw": line})
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def disk_status(path: Path) -> dict[str, object]:
    target = path if path.exists() else path.parent
    target.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(target)
    return {
        "path": str(target),
        "total_bytes": usage.total,
        "used_bytes": usage.used,
        "free_bytes": usage.free,
    }


def enforce_min_free_disk(config: AppConfig) -> dict[str, object]:
    statuses = [
        disk_status(config.state_dir),
        disk_status(config.log_dir),
        disk_status(config.data_dir),
    ]
    min_free = min(int(item["free_bytes"]) for item in statuses)
    payload = {"min_free_bytes": min_free, "required_bytes": config.service.min_free_disk_bytes, "paths": statuses}
    if min_free < config.service.min_free_disk_bytes:
        raise OSError(f"low disk space: free={min_free} required={config.service.min_free_disk_bytes}")
    return payload


def refresh_candles_resilient(
    config: AppConfig,
    client: OkxRestClient,
    symbols: list[str],
    instrument_type: str,
    bar: str,
    limit: int,
) -> dict[str, object]:
    paths: list[str] = []
    errors: list[dict[str, str]] = []
    for symbol in symbols:
        try:
            written = backfill_candles(
                config,
                client,
                symbols=[symbol],
                instrument_types=[instrument_type],
                bar=bar,
                limit=limit,
            )
            paths.extend(str(path) for path in written)
        except Exception as exc:
            errors.append({"symbol": symbol, "error_type": type(exc).__name__, "error": str(exc)})
    return {"paths": paths, "errors": errors}


def filter_records_since(records: list[dict[str, object]], since: datetime | None) -> list[dict[str, object]]:
    if since is None:
        return records
    filtered: list[dict[str, object]] = []
    for record in records:
        ts = parse_ts(record.get("ts"))
        if ts is not None and ts >= since:
            filtered.append(record)
    return filtered


def interruptible_sleep(seconds: float, stopping: dict[str, bool], stop_file: Path | None = None) -> None:
    deadline = time.monotonic() + max(seconds, 0.0)
    while not stopping.get("value", False):
        if stop_file is not None and stop_file.exists():
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(remaining, 1.0))


def service_status(config: AppConfig) -> dict[str, object]:
    pid: Optional[int] = None
    if config.service.pid_file.exists():
        raw = config.service.pid_file.read_text(encoding="utf-8").strip()
        if raw:
            try:
                pid = int(raw)
            except ValueError:
                pid = None
    heartbeat = read_json(config.service.heartbeat_file)
    return {
        "pid": pid,
        "running": bool(pid and process_alive(pid)),
        "stop_requested": config.service.stop_file.exists(),
        "heartbeat": heartbeat,
        "launch": read_json(config.service.launch_state_file),
        "log_file": str(config.service.log_file),
    }


def watchdog_status(config: AppConfig) -> dict[str, object]:
    pid: Optional[int] = None
    if config.service.watchdog_pid_file.exists():
        raw = config.service.watchdog_pid_file.read_text(encoding="utf-8").strip()
        if raw:
            try:
                pid = int(raw)
            except ValueError:
                pid = None
    return {
        "pid": pid,
        "running": bool(pid and process_alive(pid)),
        "heartbeat": read_json(config.service.watchdog_heartbeat_file),
        "launch": read_json(config.service.watchdog_launch_state_file),
        "log_file": str(config.service.watchdog_log_file),
    }


def prepare_service_launch(config: AppConfig, clear_kill_switch: bool = False) -> dict[str, object]:
    removed: list[str] = []
    for path in [config.service.stop_file, config.service.heartbeat_file]:
        if path.exists():
            path.unlink()
            removed.append(str(path))
    if clear_kill_switch and Path(config.risk.kill_switch_file).exists():
        Path(config.risk.kill_switch_file).unlink()
        removed.append(str(config.risk.kill_switch_file))
    heartbeat = {
        "ts": utc_now(),
        "started_at": utc_now(),
        "starting": True,
        "consecutive_errors": 0,
        "last_event": {"ok": True, "event": "service_starting"},
    }
    write_json(config.service.heartbeat_file, heartbeat)
    payload = {"removed": removed, "bootstrap_heartbeat": heartbeat}
    append_event(config, "service_launch_prepared", payload)
    return payload


def launch_detached_command(
    config: AppConfig,
    name: str,
    command: list[str],
    log_file: Path,
    launch_state_file: Path,
) -> dict[str, object]:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    launch_state_file.parent.mkdir(parents=True, exist_ok=True)
    log_handle = log_file.open("ab")
    try:
        process = subprocess.Popen(
            command,
            cwd=str(Path.cwd()),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            env=os.environ.copy(),
        )
    finally:
        log_handle.close()
    payload: dict[str, object] = {
        "name": name,
        "pid": process.pid,
        "command": command,
        "cwd": str(Path.cwd()),
        "log_file": str(log_file),
        "ts": utc_now(),
    }
    write_json(launch_state_file, payload)
    append_event(config, "service_launched", payload)
    return payload


def parse_ts(value: object) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def service_health(
    config: AppConfig,
    max_heartbeat_age_seconds: float = 300.0,
    require_running: bool = False,
) -> dict[str, object]:
    status = service_status(config)
    heartbeat = status.get("heartbeat")
    now = datetime.now(timezone.utc)
    issues: list[str] = []
    heartbeat_age_seconds = None
    if not heartbeat:
        issues.append("missing heartbeat")
    elif isinstance(heartbeat, dict):
        ts = parse_ts(heartbeat.get("ts"))
        if ts is None:
            issues.append("invalid heartbeat timestamp")
        else:
            heartbeat_age_seconds = (now - ts).total_seconds()
            if heartbeat_age_seconds > max_heartbeat_age_seconds:
                issues.append("stale heartbeat")
        consecutive_errors = int(heartbeat.get("consecutive_errors", 0) or 0)
        if consecutive_errors >= config.service.max_consecutive_errors:
            issues.append("consecutive error breaker reached")
        last_event = heartbeat.get("last_event")
        if isinstance(last_event, dict) and last_event.get("ok") is False:
            issues.append(f"last iteration failed: {last_event.get('error_type', 'unknown')}")
    if require_running and not status.get("running"):
        issues.append("service is not running")
    if status.get("stop_requested"):
        issues.append("stop requested")
    try:
        disk = enforce_min_free_disk(config)
    except OSError as exc:
        disk = {"error_type": type(exc).__name__, "error": str(exc)}
        issues.append("low disk space")

    try:
        audit = AuditStore(config.state_dir)
        portfolio = audit.get_state("paper_portfolio", {})
        last_run = audit.get_state("paper_portfolio_last_run", {})
    except Exception as exc:
        issues.append("audit store unavailable")
        portfolio = {}
        last_run = {"error_type": type(exc).__name__, "error": str(exc)}
    return {
        "healthy": not issues,
        "issues": issues,
        "running": status.get("running"),
        "pid": status.get("pid"),
        "disk": disk,
        "heartbeat_age_seconds": heartbeat_age_seconds,
        "heartbeat": heartbeat,
        "paper_portfolio": {
            "equity": portfolio.get("equity") if isinstance(portfolio, dict) else None,
            "drawdown": portfolio.get("drawdown") if isinstance(portfolio, dict) else None,
            "positions": portfolio.get("positions", []) if isinstance(portfolio, dict) else [],
        },
        "last_paper_portfolio_run": {
            "selected": last_run.get("selected", []) if isinstance(last_run, dict) else [],
            "orders": last_run.get("orders", []) if isinstance(last_run, dict) else [],
            "circuit_breaker": last_run.get("circuit_breaker") if isinstance(last_run, dict) else None,
            "stale_data": last_run.get("stale_data") if isinstance(last_run, dict) else None,
            "cooldown_active": last_run.get("cooldown_active") if isinstance(last_run, dict) else None,
        },
        "recent_events": tail_events(config, limit=10),
        "recent_notifications": tail_notifications(config, limit=10),
        "log_file": status.get("log_file"),
    }


def activate_kill_switch(
    config: AppConfig,
    reason: str,
    source: str = "manual",
    details: dict[str, object] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "active": True,
        "ts": utc_now(),
        "source": source,
        "reason": reason,
        "details": details or {},
    }
    path = Path(config.risk.kill_switch_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    AuditStore(config.state_dir).set_state("kill_switch", payload)
    append_event(config, "kill_switch_activated", payload)
    if config.service.notify_on_kill_switch:
        notify(config, "kill_switch_activated", "critical", payload)
    return payload


def request_service_stop(config: AppConfig) -> dict[str, object]:
    config.service.stop_file.parent.mkdir(parents=True, exist_ok=True)
    write_error = None
    try:
        config.service.stop_file.write_text(utc_now() + "\n", encoding="utf-8")
    except Exception as exc:
        write_error = {"error_type": type(exc).__name__, "error": str(exc)}
    status = service_status(config)
    pid = status.get("pid")
    if isinstance(pid, int) and status.get("running"):
        os.kill(pid, signal.SIGTERM)
    try:
        append_event(config, "service_stop_requested", {"status": service_status(config), "write_error": write_error})
    except Exception:
        pass
    return service_status(config)


def recover_paper_service(
    config: AppConfig,
    launcher: Callable[[AppConfig, str, list[str], Path, Path], dict[str, object]] = launch_detached_command,
) -> dict[str, object]:
    config.ensure_dirs()
    if Path(config.risk.kill_switch_file).exists():
        payload = {
            "status": "blocked",
            "reason": "kill switch is active",
            "kill_switch_file": str(config.risk.kill_switch_file),
        }
        append_event(config, "paper_service_recovery_blocked", payload)
        return payload
    status = service_status(config)
    if status.get("running"):
        return {"status": "already_running", "service": status}
    launch = read_json(config.service.launch_state_file)
    if not isinstance(launch, dict):
        payload = {"status": "blocked", "reason": "missing launch state"}
        append_event(config, "paper_service_recovery_blocked", payload)
        return payload
    command = launch.get("command")
    if not isinstance(command, list) or not all(isinstance(item, str) for item in command):
        payload = {"status": "blocked", "reason": "invalid launch command"}
        append_event(config, "paper_service_recovery_blocked", payload)
        return payload
    if launch.get("name") != "paper_portfolio_service" or "run-paper-portfolio" not in command:
        payload = {
            "status": "blocked",
            "reason": "launch state is not a paper portfolio service",
            "launch_name": launch.get("name"),
        }
        append_event(config, "paper_service_recovery_blocked", payload)
        return payload
    if "run-live-portfolio" in command or "--confirm-live" in command:
        payload = {"status": "blocked", "reason": "refusing to recover a live-capable command"}
        append_event(config, "paper_service_recovery_blocked", payload)
        return payload

    recovered = launcher(
        config,
        "paper_portfolio_service",
        [str(item) for item in command],
        config.service.log_file,
        config.service.launch_state_file,
    )
    payload = {
        "status": "recovered",
        "service": recovered,
        "previous_launch": launch,
        "ts": utc_now(),
    }
    append_event(config, "paper_service_recovered", payload)
    notify(config, "paper_service_recovered", "warning", {"service": recovered})
    return payload


def run_watchdog_service(
    config: AppConfig,
    interval_seconds: float | None = None,
    max_heartbeat_age_seconds: float | None = None,
    require_running: bool = True,
    trigger_kill_switch: bool = True,
    stop_service: bool = True,
    max_iterations: Optional[int] = None,
    recover_paper: bool = False,
    recovery_launcher: Callable[[AppConfig, str, list[str], Path, Path], dict[str, object]] = launch_detached_command,
) -> dict[str, object]:
    config.ensure_dirs()
    logger = configure_watchdog_logger(config)
    stopping = {"value": False}
    interval = config.service.watchdog_interval_seconds if interval_seconds is None else interval_seconds
    max_age = (
        config.service.watchdog_max_heartbeat_age_seconds
        if max_heartbeat_age_seconds is None
        else max_heartbeat_age_seconds
    )

    def handle_stop(signum: int, _frame: object) -> None:
        stopping["value"] = True
        logger.info(json.dumps({"ts": utc_now(), "event": "watchdog_signal", "signal": signum}))

    old_term = signal.signal(signal.SIGTERM, handle_stop)
    old_int = signal.signal(signal.SIGINT, handle_stop)
    iteration = 0
    summary: dict[str, object] = {}
    try:
        with pid_lock(config.service.watchdog_pid_file):
            while not stopping["value"]:
                if max_iterations is not None and iteration >= max_iterations:
                    break
                iteration += 1
                health = service_health(
                    config,
                    max_heartbeat_age_seconds=max_age,
                    require_running=require_running,
                )
                event = {
                    "ts": utc_now(),
                    "event": "watchdog_iteration",
                    "iteration": iteration,
                    "healthy": health.get("healthy"),
                    "issues": health.get("issues", []),
                    "running": health.get("running"),
                    "heartbeat_age_seconds": health.get("heartbeat_age_seconds"),
                }
                heartbeat = {
                    **event,
                    "require_running": require_running,
                    "trigger_kill_switch": trigger_kill_switch,
                    "stop_service": stop_service,
                }
                if not health.get("healthy"):
                    details = {
                        "issues": health.get("issues", []),
                        "running": health.get("running"),
                        "heartbeat_age_seconds": health.get("heartbeat_age_seconds"),
                    }
                    actions: dict[str, object] = {}
                    if recover_paper and not health.get("running"):
                        actions["paper_recovery"] = recover_paper_service(config, launcher=recovery_launcher)
                    should_escalate = not actions.get("paper_recovery") or (
                        isinstance(actions.get("paper_recovery"), dict)
                        and actions["paper_recovery"].get("status") not in {"recovered", "already_running"}
                    )
                    if should_escalate and trigger_kill_switch:
                        try:
                            actions["kill_switch"] = activate_kill_switch(
                                config,
                                "watchdog health check failed",
                                source="watchdog",
                                details=details,
                            )
                        except Exception as exc:
                            actions["kill_switch_error"] = {"error_type": type(exc).__name__, "error": str(exc)}
                    if should_escalate and stop_service:
                        try:
                            actions["service_stop"] = request_service_stop(config)
                        except Exception as exc:
                            actions["service_stop_error"] = {"error_type": type(exc).__name__, "error": str(exc)}
                    heartbeat["actions"] = actions
                    try:
                        write_json(config.service.watchdog_heartbeat_file, heartbeat)
                        AuditStore(config.state_dir).set_state("quant_watchdog", heartbeat)
                    except Exception as exc:
                        heartbeat["persistence_error"] = {"error_type": type(exc).__name__, "error": str(exc)}
                    event_name = "watchdog_recovered_paper_service" if not should_escalate else "watchdog_health_failed"
                    try:
                        append_event(config, event_name, {**details, "actions": actions})
                    except Exception:
                        pass
                    if config.service.notify_on_watchdog_failure and should_escalate:
                        notify(config, "watchdog_health_failed", "critical", {**details, "actions": actions})
                    logger.info(json.dumps({**event, "actions": actions}, ensure_ascii=False, default=str))
                    if not should_escalate:
                        summary = {
                            "iterations": iteration,
                            "stopped": False,
                            "stop_reason": "paper_recovered",
                            "issues": health.get("issues", []),
                            "actions": actions,
                        }
                        if max_iterations is not None and iteration >= max_iterations:
                            summary["stopped"] = True
                            return summary
                        if interval > 0:
                            interruptible_sleep(interval, stopping)
                        continue
                    summary = {
                        "iterations": iteration,
                        "stopped": True,
                        "stop_reason": "health_failed",
                        "issues": health.get("issues", []),
                        "actions": actions,
                    }
                    return summary

                try:
                    write_json(config.service.watchdog_heartbeat_file, heartbeat)
                    AuditStore(config.state_dir).set_state("quant_watchdog", heartbeat)
                    append_event(config, "watchdog_iteration", event)
                except Exception as exc:
                    event["persistence_error"] = {"error_type": type(exc).__name__, "error": str(exc)}
                logger.info(json.dumps(event, ensure_ascii=False, default=str))
                if max_iterations is not None and iteration >= max_iterations:
                    break
                if interval > 0:
                    interruptible_sleep(interval, stopping)
            else:
                summary = {"iterations": iteration, "stopped": True, "stop_reason": "signal"}
            summary.setdefault("iterations", iteration)
            summary.setdefault("stopped", True)
            summary.setdefault("stop_reason", "completed")
            try:
                write_json(config.service.watchdog_heartbeat_file, {**summary, "ts": utc_now()})
            except Exception:
                pass
            return summary
    finally:
        signal.signal(signal.SIGTERM, old_term)
        signal.signal(signal.SIGINT, old_int)


def run_demo_service(
    config: AppConfig,
    symbol: str,
    instrument_type: str,
    interval_seconds: float,
    confirm_demo_order: bool = False,
    order_type: str = "limit",
    cancel_after_place: bool = False,
    max_iterations: Optional[int] = None,
) -> dict[str, object]:
    config.ensure_dirs()
    logger = configure_logger(config)
    audit = AuditStore(config.state_dir)
    stopping = {"value": False}

    def handle_stop(signum: int, _frame: object) -> None:
        stopping["value"] = True
        logger.info(json.dumps({"ts": utc_now(), "event": "signal", "signal": signum}))

    old_term = signal.signal(signal.SIGTERM, handle_stop)
    old_int = signal.signal(signal.SIGINT, handle_stop)
    if config.service.stop_file.exists():
        config.service.stop_file.unlink()

    consecutive_errors = 0
    iteration = 0
    summary: dict[str, object] = {}
    try:
        with pid_lock(config.service.pid_file):
            while not stopping["value"]:
                if config.service.stop_file.exists():
                    break
                if max_iterations is not None and iteration >= max_iterations:
                    break
                iteration += 1
                started_at = utc_now()
                try:
                    dead_mans_switch = None
                    if config.service.okx_cancel_all_after_seconds > 0:
                        dead_mans_switch = OkxRestClient(config.okx).cancel_all_after(
                            config.service.okx_cancel_all_after_seconds
                        )
                    result = run_okx_demo_once(
                        config,
                        symbol,
                        instrument_type,
                        confirm_demo_order=confirm_demo_order,
                        order_type=order_type,
                        cancel_after_place=cancel_after_place,
                    )
                    consecutive_errors = 0
                    event = {
                        "ts": utc_now(),
                        "event": "iteration",
                        "iteration": iteration,
                        "ok": True,
                        "message": result.get("message"),
                        "planned_order": result.get("planned_order"),
                        "dead_mans_switch": dead_mans_switch,
                    }
                except Exception as exc:
                    consecutive_errors += 1
                    event = {
                        "ts": utc_now(),
                        "event": "iteration",
                        "iteration": iteration,
                        "ok": False,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    }
                logger.info(json.dumps(event, ensure_ascii=False, default=str))
                heartbeat = {
                    "ts": utc_now(),
                    "started_at": started_at,
                    "symbol": symbol,
                    "instrument_type": instrument_type,
                    "iteration": iteration,
                    "consecutive_errors": consecutive_errors,
                    "last_event": event,
                    "confirm_demo_order": confirm_demo_order,
                }
                write_json(config.service.heartbeat_file, heartbeat)
                audit.set_state("quant_service", heartbeat)
                if consecutive_errors >= config.service.max_consecutive_errors:
                    summary = {
                        "iterations": iteration,
                        "stopped": True,
                        "stop_reason": "max_consecutive_errors",
                        "consecutive_errors": consecutive_errors,
                    }
                    break
                sleep_for = config.service.retry_backoff_seconds if consecutive_errors else interval_seconds
                if max_iterations is not None and iteration >= max_iterations:
                    break
                if sleep_for > 0:
                    interruptible_sleep(sleep_for, stopping, config.service.stop_file)
            else:
                summary = {"iterations": iteration, "stopped": True, "stop_reason": "signal"}
            summary.setdefault("iterations", iteration)
            summary.setdefault("stopped", True)
            summary.setdefault("stop_reason", "completed")
            summary.setdefault("consecutive_errors", consecutive_errors)
            write_json(config.service.heartbeat_file, {**summary, "ts": utc_now()})
            return summary
    finally:
        signal.signal(signal.SIGTERM, old_term)
        signal.signal(signal.SIGINT, old_int)


def run_paper_portfolio_service(
    config: AppConfig,
    symbols: list[str],
    instrument_type: str,
    interval_seconds: float,
    lookback_bars: int = 24 * 30,
    top_n: int = 2,
    min_momentum: float = 0.0,
    allowlist: list[str] | None = None,
    blocklist: list[str] | None = None,
    max_turnover_pct: float | None = None,
    max_portfolio_drawdown_pct: float | None = None,
    max_candle_age_seconds: float | None = None,
    rebalance_cooldown_seconds: float | None = None,
    refresh_candles: bool | None = None,
    refresh_limit: int | None = None,
    max_iterations: Optional[int] = None,
) -> dict[str, object]:
    config.ensure_dirs()
    logger = configure_logger(config)
    stopping = {"value": False}

    def handle_stop(signum: int, _frame: object) -> None:
        stopping["value"] = True
        logger.info(json.dumps({"ts": utc_now(), "event": "signal", "signal": signum}))

    old_term = signal.signal(signal.SIGTERM, handle_stop)
    old_int = signal.signal(signal.SIGINT, handle_stop)
    if config.service.stop_file.exists():
        config.service.stop_file.unlink()

    consecutive_errors = 0
    iteration = 0
    summary: dict[str, object] = {}
    try:
        with pid_lock(config.service.pid_file):
            while not stopping["value"]:
                if config.service.stop_file.exists():
                    break
                if max_iterations is not None and iteration >= max_iterations:
                    break
                iteration += 1
                started_at = utc_now()
                result: dict[str, object] | None = None
                disk: dict[str, object] | None = None
                try:
                    disk = enforce_min_free_disk(config)
                    refresh_enabled = (
                        config.service.refresh_candles_before_iteration if refresh_candles is None else refresh_candles
                    )
                    refreshed_paths: list[str] = []
                    refresh_errors: list[dict[str, str]] = []
                    if refresh_enabled:
                        refresh_result = refresh_candles_resilient(
                            config,
                            OkxRestClient(config.okx),
                            symbols,
                            instrument_type,
                            config.market.bar,
                            refresh_limit or config.service.refresh_candles_limit,
                        )
                        refreshed_paths = list(refresh_result["paths"])
                        refresh_errors = list(refresh_result["errors"])
                    result = run_paper_portfolio_once(
                        config,
                        symbols,
                        instrument_type=instrument_type,
                        lookback_bars=lookback_bars,
                        top_n=top_n,
                        min_momentum=min_momentum,
                        allowlist=allowlist,
                        blocklist=blocklist,
                        max_turnover_pct=max_turnover_pct,
                        max_portfolio_drawdown_pct=max_portfolio_drawdown_pct,
                        max_candle_age_seconds=max_candle_age_seconds,
                        rebalance_cooldown_seconds=rebalance_cooldown_seconds,
                    )
                    consecutive_errors = 0
                    event = {
                        "ts": utc_now(),
                        "event": "paper_portfolio_iteration",
                        "iteration": iteration,
                        "ok": True,
                        "selected": result.get("selected"),
                        "orders": result.get("orders"),
                        "refreshed_candles": refreshed_paths,
                        "refresh_errors": refresh_errors,
                        "disk": disk,
                    }
                except Exception as exc:
                    consecutive_errors += 1
                    event = {
                        "ts": utc_now(),
                        "event": "paper_portfolio_iteration",
                        "iteration": iteration,
                        "ok": False,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    }
                logger.info(json.dumps(event, ensure_ascii=False, default=str))
                heartbeat = {
                    "ts": utc_now(),
                    "started_at": started_at,
                    "symbols": symbols,
                    "instrument_type": instrument_type,
                    "strategy": "cross_sectional_momentum_portfolio",
                    "lookback_bars": lookback_bars,
                    "top_n": top_n,
                    "allowlist": allowlist or config.market.trade_allowlist,
                    "blocklist": blocklist or config.market.trade_blocklist,
                    "max_candle_age_seconds": max_candle_age_seconds
                    if max_candle_age_seconds is not None
                    else config.service.max_candle_age_seconds,
                    "rebalance_cooldown_seconds": rebalance_cooldown_seconds
                    if rebalance_cooldown_seconds is not None
                    else config.service.rebalance_cooldown_seconds,
                    "refresh_candles": config.service.refresh_candles_before_iteration
                    if refresh_candles is None
                    else refresh_candles,
                    "refresh_candles_limit": refresh_limit or config.service.refresh_candles_limit,
                    "iteration": iteration,
                    "consecutive_errors": consecutive_errors,
                    "last_event": event,
                    "disk": disk,
                }
                try:
                    write_json(config.service.heartbeat_file, heartbeat)
                    audit = AuditStore(config.state_dir)
                    audit.set_state("paper_portfolio_service", heartbeat)
                    audit.insert_ads_service_run(
                        service_name="paper_portfolio_service",
                        mode="paper",
                        strategy_id="cross_sectional_momentum_portfolio",
                        symbols=symbols,
                        market_type=instrument_type,
                        interval=config.market.bar,
                        started_at=started_at,
                        completed_at=str(heartbeat["ts"]),
                        iteration=iteration,
                        ok=bool(event.get("ok")),
                        result=result,
                        consecutive_errors=consecutive_errors,
                        stop_reason=None if event.get("ok") else str(event.get("error")),
                        payload={"event": event, "heartbeat": heartbeat},
                    )
                except Exception as exc:
                    consecutive_errors += 1
                    persist_event = {
                        "ts": utc_now(),
                        "event": "paper_portfolio_persistence_error",
                        "iteration": iteration,
                        "ok": False,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    }
                    heartbeat["ts"] = utc_now()
                    heartbeat["consecutive_errors"] = consecutive_errors
                    heartbeat["last_event"] = persist_event
                    logger.info(json.dumps(persist_event, ensure_ascii=False, default=str))
                    try:
                        write_json(config.service.heartbeat_file, heartbeat)
                    except Exception:
                        pass
                if consecutive_errors >= config.service.max_consecutive_errors:
                    summary = {
                        "iterations": iteration,
                        "stopped": True,
                        "stop_reason": "max_consecutive_errors",
                        "consecutive_errors": consecutive_errors,
                    }
                    break
                sleep_for = config.service.retry_backoff_seconds if consecutive_errors else interval_seconds
                if max_iterations is not None and iteration >= max_iterations:
                    break
                if sleep_for > 0:
                    interruptible_sleep(sleep_for, stopping, config.service.stop_file)
            else:
                summary = {"iterations": iteration, "stopped": True, "stop_reason": "signal"}
            summary.setdefault("iterations", iteration)
            summary.setdefault("stopped", True)
            summary.setdefault("stop_reason", "completed")
            summary.setdefault("consecutive_errors", consecutive_errors)
            write_json(config.service.heartbeat_file, {**summary, "ts": utc_now()})
            return summary
    finally:
        signal.signal(signal.SIGTERM, old_term)
        signal.signal(signal.SIGINT, old_int)


def run_live_portfolio_service(
    config: AppConfig,
    symbols: list[str],
    instrument_type: str,
    interval_seconds: float,
    confirm_live: bool,
    lookback_bars: int = 24 * 30,
    top_n: int = 2,
    min_momentum: float = 0.0,
    allowlist: list[str] | None = None,
    blocklist: list[str] | None = None,
    max_turnover_pct: float | None = None,
    max_candle_age_seconds: float | None = None,
    rebalance_cooldown_seconds: float | None = None,
    order_type: str | None = None,
    refresh_candles: bool | None = None,
    refresh_limit: int | None = None,
    max_iterations: Optional[int] = None,
) -> dict[str, object]:
    config.mode = "live"
    config.okx.demo_trading = False
    config.ensure_dirs()
    RiskManager(config.risk, config.execution).validate_live_allowed(
        config.mode,
        OkxRestClient(config.okx).credentials.present,
        confirm_live,
    )
    logger = configure_logger(config)
    audit = AuditStore(config.state_dir)
    stopping = {"value": False}

    def handle_stop(signum: int, _frame: object) -> None:
        stopping["value"] = True
        logger.info(json.dumps({"ts": utc_now(), "event": "signal", "signal": signum}))

    old_term = signal.signal(signal.SIGTERM, handle_stop)
    old_int = signal.signal(signal.SIGINT, handle_stop)
    if config.service.stop_file.exists():
        config.service.stop_file.unlink()

    consecutive_errors = 0
    iteration = 0
    summary: dict[str, object] = {}
    try:
        with pid_lock(config.service.pid_file):
            while not stopping["value"]:
                if config.service.stop_file.exists():
                    break
                if max_iterations is not None and iteration >= max_iterations:
                    break
                iteration += 1
                started_at = utc_now()
                result: dict[str, object] | None = None
                try:
                    client = OkxRestClient(config.okx)
                    dead_mans_switch = None
                    if config.service.okx_cancel_all_after_seconds > 0:
                        dead_mans_switch = client.cancel_all_after(config.service.okx_cancel_all_after_seconds)
                    refresh_enabled = (
                        config.service.refresh_candles_before_iteration if refresh_candles is None else refresh_candles
                    )
                    refreshed_paths: list[str] = []
                    refresh_errors: list[dict[str, str]] = []
                    if refresh_enabled:
                        refresh_result = refresh_candles_resilient(
                            config,
                            client,
                            symbols,
                            instrument_type,
                            config.market.bar,
                            refresh_limit or config.service.refresh_candles_limit,
                        )
                        refreshed_paths = list(refresh_result["paths"])
                        refresh_errors = list(refresh_result["errors"])
                    result = run_okx_live_portfolio_once(
                        config,
                        symbols,
                        instrument_type=instrument_type,
                        lookback_bars=lookback_bars,
                        top_n=top_n,
                        min_momentum=min_momentum,
                        allowlist=allowlist,
                        blocklist=blocklist,
                        max_turnover_pct=max_turnover_pct,
                        max_candle_age_seconds=max_candle_age_seconds,
                        rebalance_cooldown_seconds=rebalance_cooldown_seconds,
                        confirm_live=confirm_live,
                        order_type=order_type,
                        client=client,
                    )
                    consecutive_errors = 0
                    event = {
                        "ts": utc_now(),
                        "event": "live_portfolio_iteration",
                        "iteration": iteration,
                        "ok": True,
                        "selected": result.get("selected"),
                        "orders": result.get("orders"),
                        "refreshed_candles": refreshed_paths,
                        "refresh_errors": refresh_errors,
                        "dead_mans_switch": dead_mans_switch,
                    }
                except Exception as exc:
                    consecutive_errors += 1
                    event = {
                        "ts": utc_now(),
                        "event": "live_portfolio_iteration",
                        "iteration": iteration,
                        "ok": False,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    }
                logger.info(json.dumps(event, ensure_ascii=False, default=str))
                heartbeat = {
                    "ts": utc_now(),
                    "started_at": started_at,
                    "symbols": symbols,
                    "instrument_type": instrument_type,
                    "strategy": "cross_sectional_momentum_live_portfolio",
                    "lookback_bars": lookback_bars,
                    "top_n": top_n,
                    "allowlist": allowlist or config.market.trade_allowlist,
                    "blocklist": blocklist or config.market.trade_blocklist,
                    "max_candle_age_seconds": max_candle_age_seconds
                    if max_candle_age_seconds is not None
                    else config.service.max_candle_age_seconds,
                    "rebalance_cooldown_seconds": rebalance_cooldown_seconds
                    if rebalance_cooldown_seconds is not None
                    else config.service.rebalance_cooldown_seconds,
                    "refresh_candles": config.service.refresh_candles_before_iteration
                    if refresh_candles is None
                    else refresh_candles,
                    "refresh_candles_limit": refresh_limit or config.service.refresh_candles_limit,
                    "confirm_live": confirm_live,
                    "iteration": iteration,
                    "consecutive_errors": consecutive_errors,
                    "last_event": event,
                }
                write_json(config.service.heartbeat_file, heartbeat)
                audit.set_state("live_portfolio_service", heartbeat)
                audit.insert_ads_service_run(
                    service_name="live_portfolio_service",
                    mode="live",
                    strategy_id="cross_sectional_momentum_live_portfolio",
                    symbols=symbols,
                    market_type=instrument_type,
                    interval=config.market.bar,
                    started_at=started_at,
                    completed_at=str(heartbeat["ts"]),
                    iteration=iteration,
                    ok=bool(event.get("ok")),
                    result=result,
                    consecutive_errors=consecutive_errors,
                    stop_reason=None if event.get("ok") else str(event.get("error")),
                    payload={"event": event, "heartbeat": heartbeat},
                )
                if consecutive_errors >= config.service.max_consecutive_errors:
                    summary = {
                        "iterations": iteration,
                        "stopped": True,
                        "stop_reason": "max_consecutive_errors",
                        "consecutive_errors": consecutive_errors,
                    }
                    break
                sleep_for = config.service.retry_backoff_seconds if consecutive_errors else interval_seconds
                if max_iterations is not None and iteration >= max_iterations:
                    break
                if sleep_for > 0:
                    interruptible_sleep(sleep_for, stopping, config.service.stop_file)
            else:
                summary = {"iterations": iteration, "stopped": True, "stop_reason": "signal"}
            summary.setdefault("iterations", iteration)
            summary.setdefault("stopped", True)
            summary.setdefault("stop_reason", "completed")
            summary.setdefault("consecutive_errors", consecutive_errors)
            write_json(config.service.heartbeat_file, {**summary, "ts": utc_now()})
            return summary
    finally:
        signal.signal(signal.SIGTERM, old_term)
        signal.signal(signal.SIGINT, old_int)


def run_unattended_acceptance(
    config: AppConfig,
    symbols: list[str],
    instrument_type: str = "spot",
    iterations: int = 3,
    lookback_bars: int = 24 * 30,
    top_n: int = 2,
    max_heartbeat_age_seconds: float = 300.0,
    write_report_file: bool = True,
) -> dict[str, object]:
    config.ensure_dirs()
    checks: list[dict[str, object]] = []
    runtime_config = config.model_copy(deep=True)
    runtime_config.state_dir = config.state_dir / "acceptance"
    runtime_config.log_dir = config.log_dir / "acceptance"
    runtime_config.service.pid_file = runtime_config.state_dir / "quant_service.pid"
    runtime_config.service.watchdog_pid_file = runtime_config.state_dir / "quant_watchdog.pid"
    runtime_config.service.launch_state_file = runtime_config.state_dir / "quant_service_launch.json"
    runtime_config.service.watchdog_launch_state_file = runtime_config.state_dir / "quant_watchdog_launch.json"
    runtime_config.service.stop_file = runtime_config.state_dir / "quant_service.stop"
    runtime_config.service.heartbeat_file = runtime_config.state_dir / "quant_service_heartbeat.json"
    runtime_config.service.watchdog_heartbeat_file = runtime_config.state_dir / "quant_watchdog_heartbeat.json"
    runtime_config.service.log_file = runtime_config.log_dir / "quant_service.log"
    runtime_config.service.watchdog_log_file = runtime_config.log_dir / "quant_watchdog.log"
    runtime_config.service.event_log_file = runtime_config.log_dir / "quant_events.jsonl"
    runtime_config.service.notification_log_file = runtime_config.log_dir / "quant_notifications.jsonl"
    runtime_config.risk.kill_switch_file = runtime_config.state_dir / "KILL_SWITCH"
    runtime_config.ensure_dirs()

    def add_check(name: str, passed: bool, details: dict[str, object] | None = None) -> None:
        checks.append({"name": name, "passed": passed, "details": details or {}})

    if Path(config.risk.kill_switch_file).exists():
        add_check("kill_switch_precheck", False, {"path": str(config.risk.kill_switch_file)})
        payload = {
            "status": "failed",
            "ts": utc_now(),
            "symbols": symbols,
            "instrument_type": instrument_type,
            "iterations": iterations,
            "checks": checks,
        }
        if write_report_file:
            payload["report_path"] = str(write_report(config.report_dir, "unattended_acceptance", payload))
        return payload
    add_check("kill_switch_precheck", True)

    try:
        paper_summary = run_paper_portfolio_service(
            runtime_config,
            symbols,
            instrument_type,
            interval_seconds=0,
            lookback_bars=lookback_bars,
            top_n=top_n,
            max_candle_age_seconds=0,
            rebalance_cooldown_seconds=0,
            refresh_candles=False,
            max_iterations=iterations,
        )
        add_check(
            "paper_service_iterations",
            paper_summary.get("iterations") == iterations and paper_summary.get("consecutive_errors") == 0,
            paper_summary,
        )
    except Exception as exc:
        add_check("paper_service_iterations", False, {"error_type": type(exc).__name__, "error": str(exc)})

    health = service_health(runtime_config, max_heartbeat_age_seconds=max_heartbeat_age_seconds, require_running=False)
    add_check("service_health_after_run", bool(health.get("healthy")), health)

    try:
        watchdog_summary = run_watchdog_service(
            runtime_config,
            interval_seconds=0,
            max_heartbeat_age_seconds=max_heartbeat_age_seconds,
            require_running=False,
            trigger_kill_switch=False,
            stop_service=False,
            max_iterations=1,
        )
        add_check(
            "watchdog_healthy_path",
            watchdog_summary.get("stop_reason") == "completed" and watchdog_summary.get("iterations") == 1,
            watchdog_summary,
        )
    except Exception as exc:
        add_check("watchdog_healthy_path", False, {"error_type": type(exc).__name__, "error": str(exc)})

    live_gate_config = config.model_copy(deep=True)
    live_gate_config.mode = "live"
    live_gate_config.okx.demo_trading = False
    try:
        RiskManager(live_gate_config.risk, live_gate_config.execution).validate_live_allowed(
            live_gate_config.mode,
            credentials_present=False,
            confirm_live=False,
        )
        add_check("live_gate_blocks_unconfirmed_or_missing_credentials", False, {"error": "live gate allowed"})
    except PermissionError as exc:
        add_check("live_gate_blocks_unconfirmed_or_missing_credentials", True, {"error": str(exc)})

    passed = all(bool(check["passed"]) for check in checks)
    payload = {
        "status": "passed" if passed else "failed",
        "ts": utc_now(),
        "symbols": symbols,
        "instrument_type": instrument_type,
        "iterations": iterations,
        "lookback_bars": lookback_bars,
        "top_n": top_n,
        "isolated_state_dir": str(runtime_config.state_dir),
        "isolated_log_dir": str(runtime_config.log_dir),
        "checks": checks,
    }
    if write_report_file:
        payload["report_path"] = str(write_report(config.report_dir, "unattended_acceptance", payload))
    return payload


def run_live_gate_drill(config: AppConfig, write_report_file: bool = True) -> dict[str, object]:
    config.ensure_dirs()
    checks: list[dict[str, object]] = []

    def add_check(name: str, passed: bool, details: dict[str, object] | None = None) -> None:
        checks.append({"name": name, "passed": passed, "details": details or {}})

    def expect_block(name: str, cfg: AppConfig, credentials_present: bool, confirm_live: bool, expected: str) -> None:
        try:
            RiskManager(cfg.risk, cfg.execution).validate_live_allowed(
                cfg.mode,
                credentials_present=credentials_present,
                confirm_live=confirm_live,
            )
            add_check(name, False, {"error": "live gate allowed unexpectedly"})
        except PermissionError as exc:
            add_check(name, expected in str(exc), {"error": str(exc), "expected": expected})

    base = config.model_copy(deep=True)
    base.mode = "live"
    base.okx.demo_trading = False

    disabled = base.model_copy(deep=True)
    disabled.execution.live_enabled = False
    expect_block("config_live_enabled_false_blocks", disabled, True, True, "live execution is disabled")

    missing_confirm = base.model_copy(deep=True)
    missing_confirm.execution.live_enabled = True
    missing_confirm.execution.require_confirm_live = True
    expect_block("missing_confirm_live_blocks", missing_confirm, True, False, "requires --confirm-live")

    missing_credentials = base.model_copy(deep=True)
    missing_credentials.execution.live_enabled = True
    expect_block("missing_credentials_blocks", missing_credentials, False, True, "credentials are required")

    allowed = base.model_copy(deep=True)
    allowed.execution.live_enabled = True
    try:
        RiskManager(allowed.risk, allowed.execution).validate_live_allowed(
            allowed.mode,
            credentials_present=True,
            confirm_live=True,
        )
        add_check("all_live_gates_pass_when_enabled_confirmed_and_credentialed", True)
    except PermissionError as exc:
        add_check(
            "all_live_gates_pass_when_enabled_confirmed_and_credentialed",
            False,
            {"error": str(exc)},
        )

    isolated = config.model_copy(deep=True)
    isolated.state_dir = config.state_dir / "live_gate_drill"
    isolated.log_dir = config.log_dir / "live_gate_drill"
    isolated.risk.kill_switch_file = isolated.state_dir / "KILL_SWITCH"
    isolated.service.event_log_file = isolated.log_dir / "quant_events.jsonl"
    isolated.service.notification_log_file = isolated.log_dir / "quant_notifications.jsonl"
    isolated.ensure_dirs()
    activate_kill_switch(isolated, "live gate drill", source="live_gate_drill")
    risk = RiskManager(isolated.risk, isolated.execution)
    portfolio = PortfolioState(cash=1000, equity=1000, positions={})
    open_intent = OrderIntent(
        symbol="BTC/USDT",
        instrument_type=InstrumentType.SPOT,
        side=Side.BUY,
        quantity=0.01,
        order_type=OrderType.MARKET,
    )
    reduce_intent = OrderIntent(
        symbol="BTC/USDT",
        instrument_type=InstrumentType.SPOT,
        side=Side.SELL,
        quantity=0.01,
        order_type=OrderType.MARKET,
        reduce_only=True,
    )
    open_decision = risk.evaluate(open_intent, portfolio, mark_price=10000)
    reduce_decision = risk.evaluate(reduce_intent, portfolio, mark_price=10000)
    add_check(
        "kill_switch_blocks_new_orders",
        not open_decision.approved and "kill switch" in open_decision.reason,
        {"decision": {"approved": open_decision.approved, "reason": open_decision.reason}},
    )
    add_check(
        "kill_switch_allows_reduce_only_orders",
        reduce_decision.approved,
        {"decision": {"approved": reduce_decision.approved, "reason": reduce_decision.reason}},
    )

    passed = all(bool(check["passed"]) for check in checks)
    payload = {
        "strategy": "live_gate_drill",
        "status": "passed" if passed else "failed",
        "ts": utc_now(),
        "checks": checks,
        "live_ready": False,
        "live_ready_reason": "This drill proves gate behavior only; production live still requires 24h+ paper stability, webhook alerting, explicit live config, credentials, and --confirm-live.",
    }
    if write_report_file:
        payload["report_path"] = str(write_report(config.report_dir, "live_gate_drill", payload))
    return payload


def run_notification_drill(
    config: AppConfig,
    level: str = "info",
    write_report_file: bool = True,
) -> dict[str, object]:
    config.ensure_dirs()
    before_count = len(tail_notifications(config, limit=1000))
    webhook_configured = bool(os.environ.get(config.service.notification_webhook_url_env))
    item = notify(
        config,
        "notification_drill",
        level,
        {
            "ts": utc_now(),
            "source": "notification_drill",
            "purpose": "pre-live notification drill",
            "webhook_env": config.service.notification_webhook_url_env,
        },
    )
    after = tail_notifications(config, limit=1000)
    local_log_ok = len(after) >= before_count + 1 and after[-1].get("event") == "notification_drill"
    webhook_ok = bool(item.get("webhook_sent")) if webhook_configured else False
    if not local_log_ok:
        status = "failed"
    elif not webhook_configured:
        status = "local_only"
    elif webhook_ok:
        status = "passed"
    else:
        status = "failed"
    payload = {
        "strategy": "notification_drill",
        "status": status,
        "ts": utc_now(),
        "level": level,
        "webhook_configured": webhook_configured,
        "local_log_ok": local_log_ok,
        "webhook_ok": webhook_ok,
        "notification": item,
        "live_ready_contribution": webhook_configured and webhook_ok,
        "live_ready_note": (
            "external webhook passed"
            if webhook_ok
            else "local audit passed; external webhook not configured"
            if local_log_ok and not webhook_configured
            else "notification drill failed"
        ),
    }
    if write_report_file:
        payload["report_path"] = str(write_report(config.report_dir, "notification_drill", payload))
    return payload


def run_pre_live_check(
    config: AppConfig,
    min_observation_hours: float = 24.0,
    max_live_cap_usdt: float = 50.0,
    max_leverage: float = 3.0,
    max_heartbeat_age_seconds: float | None = None,
    require_running: bool = True,
    refresh_stability: bool = True,
    write_report_file: bool = True,
) -> dict[str, object]:
    config.ensure_dirs()
    max_age = (
        config.service.watchdog_max_heartbeat_age_seconds
        if max_heartbeat_age_seconds is None
        else max_heartbeat_age_seconds
    )
    refreshed_stability_report = None
    if refresh_stability:
        refreshed_stability_report = write_service_stability_report(
            config,
            max_heartbeat_age_seconds=max_age,
            require_running=require_running,
        )
    health = service_health(config, max_heartbeat_age_seconds=max_age, require_running=require_running)
    watchdog = watchdog_status(config)
    stability = read_json(config.report_dir / "service_stability_latest.json") or {}
    live_gate = read_json(config.report_dir / "live_gate_drill_latest.json") or {}
    notification = read_json(config.report_dir / "notification_drill_latest.json") or {}
    shortlist = read_json(config.report_dir / "strategy_shortlist_latest.json") or {}
    production_credentials_present = bool(
        os.environ.get(config.okx.api_key_env)
        and os.environ.get(config.okx.api_secret_env)
        and os.environ.get(config.okx.passphrase_env)
    )
    webhook_configured = bool(os.environ.get(config.service.notification_webhook_url_env))
    observation_age = float(stability.get("observation_age_seconds", 0.0) or 0.0)
    stability_summary = stability.get("summary", {}) if isinstance(stability.get("summary"), dict) else {}

    checks: list[dict[str, object]] = []

    def add_check(name: str, passed: bool, details: dict[str, object] | None = None) -> None:
        checks.append({"name": name, "passed": passed, "details": details or {}})

    add_check(
        "paper_service_health",
        bool(health.get("healthy")),
        {"issues": health.get("issues", []), "running": health.get("running")},
    )
    add_check(
        "watchdog_running",
        bool(watchdog.get("running")) if require_running else bool(watchdog.get("heartbeat") or watchdog.get("running")),
        {"running": watchdog.get("running"), "pid": watchdog.get("pid")},
    )
    add_check(
        "paper_stability_window",
        observation_age >= min_observation_hours * 3600,
        {"observation_age_seconds": observation_age, "required_seconds": min_observation_hours * 3600},
    )
    add_check(
        "paper_stability_no_failures",
        int(stability_summary.get("failure_event_count") or 0) == 0,
        {"failure_event_count": stability_summary.get("failure_event_count")},
    )
    add_check(
        "live_gate_drill_passed",
        live_gate.get("status") == "passed",
        {"status": live_gate.get("status"), "check_count": len(live_gate.get("checks", [])) if isinstance(live_gate.get("checks"), list) else 0},
    )
    add_check(
        "notification_webhook_configured",
        webhook_configured,
        {"env": config.service.notification_webhook_url_env},
    )
    add_check(
        "notification_drill_passed",
        notification.get("status") == "passed" and notification.get("live_ready_contribution") is True,
        {
            "status": notification.get("status"),
            "local_log_ok": notification.get("local_log_ok"),
            "webhook_ok": notification.get("webhook_ok"),
        },
    )
    add_check(
        "production_live_config_enabled",
        config.mode == "live" and config.execution.live_enabled and not config.okx.demo_trading,
        {
            "mode": config.mode,
            "live_enabled": config.execution.live_enabled,
            "okx_demo_trading": config.okx.demo_trading,
        },
    )
    add_check(
        "production_credentials_present",
        production_credentials_present,
        {
            "api_key_env": config.okx.api_key_env,
            "api_secret_env": config.okx.api_secret_env,
            "passphrase_env": config.okx.passphrase_env,
        },
    )
    add_check(
        "risk_limits_within_operator_bounds",
        (
            config.risk.live_trading_cap_usdt <= max_live_cap_usdt
            and config.risk.max_leverage <= max_leverage
            and config.risk.max_symbol_exposure_pct <= 0.20
            and config.risk.max_daily_loss_pct <= 0.02
            and config.risk.max_portfolio_drawdown_pct <= 0.05
            and config.risk.max_turnover_per_rebalance_pct <= 0.50
        ),
        {
            "live_trading_cap_usdt": config.risk.live_trading_cap_usdt,
            "max_live_cap_usdt": max_live_cap_usdt,
            "max_leverage": config.risk.max_leverage,
            "operator_max_leverage": max_leverage,
            "max_symbol_exposure_pct": config.risk.max_symbol_exposure_pct,
            "max_daily_loss_pct": config.risk.max_daily_loss_pct,
            "max_portfolio_drawdown_pct": config.risk.max_portfolio_drawdown_pct,
            "max_turnover_per_rebalance_pct": config.risk.max_turnover_per_rebalance_pct,
        },
    )
    add_check(
        "kill_switch_inactive",
        not Path(config.risk.kill_switch_file).exists(),
        {"kill_switch_file": str(config.risk.kill_switch_file)},
    )
    add_check(
        "strategy_shortlist_primary_present",
        bool(shortlist.get("primary")),
        {"primary": shortlist.get("primary"), "backup": shortlist.get("backup")},
    )

    passed = all(bool(check["passed"]) for check in checks)
    payload: dict[str, object] = {
        "strategy": "pre_live_check",
        "status": "passed" if passed else "failed",
        "ts": utc_now(),
        "live_ready": passed,
        "min_observation_hours": min_observation_hours,
        "max_live_cap_usdt": max_live_cap_usdt,
        "max_leverage": max_leverage,
        "refresh_stability": refresh_stability,
        "refreshed_stability_report": str(refreshed_stability_report) if refreshed_stability_report else None,
        "checks": checks,
        "summary": {
            "failed_checks": [check["name"] for check in checks if not check["passed"]],
            "service_running": health.get("running"),
            "watchdog_running": watchdog.get("running"),
            "observation_age_seconds": observation_age,
            "webhook_configured": webhook_configured,
            "production_credentials_present": production_credentials_present,
            "primary_strategy": shortlist.get("primary"),
            "backup_strategy": shortlist.get("backup"),
        },
    }
    if write_report_file:
        payload["report_path"] = str(write_report(config.report_dir, "pre_live_check", payload))
    return payload


def write_runtime_snapshot_report(
    config: AppConfig,
    config_path: str | None = None,
    max_heartbeat_age_seconds: float = 300.0,
    require_running: bool = False,
) -> Path:
    config.ensure_dirs()
    production_credentials_present = bool(
        os.environ.get(config.okx.api_key_env)
        and os.environ.get(config.okx.api_secret_env)
        and os.environ.get(config.okx.passphrase_env)
    )
    demo_credentials_present = bool(
        os.environ.get(config.okx.demo_api_key_env)
        and os.environ.get(config.okx.demo_api_secret_env)
        and os.environ.get(config.okx.demo_passphrase_env)
    )
    payload: dict[str, object] = {
        "strategy": "runtime_snapshot",
        "ts": utc_now(),
        "config_path": config_path,
        "mode": config.mode,
        "okx": {
            "domain": config.okx.domain,
            "base_url": config.okx.base_url,
            "demo_trading": config.okx.demo_trading,
            "timeout_seconds": config.okx.timeout_seconds,
            "proxy_configured": bool(config.okx.effective_proxy_url),
            "production_credentials_present": production_credentials_present,
            "demo_credentials_present": demo_credentials_present,
            "api_key_env": config.okx.api_key_env,
            "api_secret_env": config.okx.api_secret_env,
            "passphrase_env": config.okx.passphrase_env,
            "demo_api_key_env": config.okx.demo_api_key_env,
            "demo_api_secret_env": config.okx.demo_api_secret_env,
            "demo_passphrase_env": config.okx.demo_passphrase_env,
        },
        "market": {
            "base_currency": config.market.base_currency,
            "bar": config.market.bar,
            "symbols": config.market.symbols,
            "instrument_types": config.market.instrument_types,
            "trade_allowlist": config.market.trade_allowlist,
            "trade_blocklist": config.market.trade_blocklist,
        },
        "strategy_config": config.strategy.model_dump(mode="json"),
        "risk": config.risk.model_dump(mode="json"),
        "execution": config.execution.model_dump(mode="json"),
        "service_config": {
            **config.service.model_dump(mode="json"),
            "notification_webhook_configured": bool(os.environ.get(config.service.notification_webhook_url_env)),
        },
        "service": service_status(config),
        "watchdog": watchdog_status(config),
        "health": service_health(
            config,
            max_heartbeat_age_seconds=max_heartbeat_age_seconds,
            require_running=require_running,
        ),
        "latest_reports": {
            "service_stability": read_json(config.report_dir / "service_stability_latest.json"),
            "pre_live_check": read_json(config.report_dir / "pre_live_check_latest.json"),
            "strategy_shortlist": read_json(config.report_dir / "strategy_shortlist_latest.json"),
            "notification_drill": read_json(config.report_dir / "notification_drill_latest.json"),
            "live_gate_drill": read_json(config.report_dir / "live_gate_drill_latest.json"),
        },
    }
    return write_report(config.report_dir, "runtime_snapshot", payload)


def write_service_observation_report(
    config: AppConfig,
    max_heartbeat_age_seconds: float = 300.0,
    require_running: bool = False,
) -> Path:
    payload = {
        "ts": utc_now(),
        "service": service_status(config),
        "watchdog": watchdog_status(config),
        "health": service_health(
            config,
            max_heartbeat_age_seconds=max_heartbeat_age_seconds,
            require_running=require_running,
        ),
    }
    return write_report(config.report_dir, "service_observation", payload)


def write_service_stability_report(
    config: AppConfig,
    max_heartbeat_age_seconds: float = 300.0,
    require_running: bool = False,
    since_hours: float | None = None,
) -> Path:
    status = service_status(config)
    watchdog = watchdog_status(config)
    health = service_health(
        config,
        max_heartbeat_age_seconds=max_heartbeat_age_seconds,
        require_running=require_running,
    )
    now = datetime.now(timezone.utc)
    launch = status.get("launch")
    launch_ts = parse_ts(launch.get("ts")) if isinstance(launch, dict) else None
    since = now - timedelta(hours=since_hours) if since_hours is not None else launch_ts

    event_records = filter_records_since(read_jsonl(Path(config.service.event_log_file)), since)
    service_log_records = filter_records_since(read_jsonl(Path(config.service.log_file)), since)
    watchdog_log_records = filter_records_since(read_jsonl(Path(config.service.watchdog_log_file)), since)

    paper_runs = [record for record in event_records if record.get("event") == "paper_portfolio_run"]
    service_iterations = [
        record for record in service_log_records if record.get("event") == "paper_portfolio_iteration"
    ]
    watchdog_iterations = [
        record
        for record in event_records + watchdog_log_records
        if record.get("event") == "watchdog_iteration"
    ]
    orders = [order for record in paper_runs for order in record.get("orders", []) if isinstance(order, dict)]
    equity_values = [
        float(record["portfolio_equity"])
        for record in paper_runs
        if isinstance(record.get("portfolio_equity"), (int, float))
    ]
    selected_counts: dict[str, int] = {}
    for record in paper_runs:
        selected = record.get("selected", [])
        if not isinstance(selected, list):
            continue
        for symbol in selected:
            selected_counts[str(symbol)] = selected_counts.get(str(symbol), 0) + 1

    failure_events = [
        record
        for record in event_records + service_log_records + watchdog_log_records
        if (
            record.get("ok") is False
            or record.get("event") in {"watchdog_health_failed", "kill_switch_activated", "malformed_jsonl_line"}
            or bool(record.get("circuit_breaker"))
            or bool(record.get("stale_data"))
        )
        and record.get("source") != "live_gate_drill"
    ]
    first_ts = min(
        (ts for ts in (parse_ts(record.get("ts")) for record in event_records + service_log_records) if ts),
        default=None,
    )
    last_ts = max(
        (ts for ts in (parse_ts(record.get("ts")) for record in event_records + service_log_records) if ts),
        default=None,
    )
    payload = {
        "ts": utc_now(),
        "since": since.isoformat() if since else None,
        "launch_ts": launch_ts.isoformat() if launch_ts else None,
        "observation_age_seconds": (now - since).total_seconds() if since else None,
        "first_record_ts": first_ts.isoformat() if first_ts else None,
        "last_record_ts": last_ts.isoformat() if last_ts else None,
        "service": status,
        "watchdog": watchdog,
        "health": health,
        "summary": {
            "healthy": bool(health.get("healthy")),
            "service_running": bool(status.get("running")),
            "watchdog_running": bool(watchdog.get("running")),
            "paper_run_count": len(paper_runs),
            "service_iteration_count": len(service_iterations),
            "watchdog_iteration_count": len(watchdog_iterations),
            "order_count": len(orders),
            "failure_event_count": len(failure_events),
            "min_equity": min(equity_values) if equity_values else None,
            "max_equity": max(equity_values) if equity_values else None,
            "latest_equity": equity_values[-1] if equity_values else None,
            "selected_counts": dict(sorted(selected_counts.items())),
        },
        "latest_paper_runs": paper_runs[-20:],
        "latest_service_iterations": service_iterations[-20:],
        "latest_watchdog_iterations": watchdog_iterations[-20:],
        "failure_events": failure_events[-50:],
    }
    return write_report(config.report_dir, "service_stability", payload)
