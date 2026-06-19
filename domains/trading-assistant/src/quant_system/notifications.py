from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any
from urllib.request import Request, urlopen

from .config import AppConfig


def notify(config: AppConfig, event_type: str, level: str, payload: dict[str, Any]) -> dict[str, Any]:
    item: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event_type,
        "level": level,
        "payload": payload,
        "webhook_sent": False,
    }
    path = config.service.notification_log_file
    path.parent.mkdir(parents=True, exist_ok=True)

    webhook_url = os.getenv(config.service.notification_webhook_url_env, "")
    if webhook_url:
        body = json.dumps(item, ensure_ascii=False, default=str).encode("utf-8")
        request = Request(
            webhook_url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json", "User-Agent": "quant-system/1.0"},
        )
        try:
            with urlopen(request, timeout=config.service.notification_timeout_seconds) as response:
                item["webhook_status"] = getattr(response, "status", None)
                item["webhook_sent"] = True
        except Exception as exc:
            item["webhook_error"] = f"{type(exc).__name__}: {exc}"

    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(item, ensure_ascii=False, default=str) + "\n")
    return item


def tail_notifications(config: AppConfig, limit: int = 20) -> list[dict[str, Any]]:
    path = config.service.notification_log_file
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()[-max(limit, 1) :]
    rows: list[dict[str, Any]] = []
    for line in lines:
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            rows.append({"event": "malformed_notification_log_line", "raw": line})
    return rows
