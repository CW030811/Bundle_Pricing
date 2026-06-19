from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import AppConfig


def append_event(config: AppConfig, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    event = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event_type,
        **payload,
    }
    path = Path(config.service.event_log_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
    return event


def tail_events(config: AppConfig, limit: int = 20) -> list[dict[str, Any]]:
    path = Path(config.service.event_log_file)
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()[-max(limit, 1) :]
    events: list[dict[str, Any]] = []
    for line in lines:
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            events.append({"event": "malformed_event_log_line", "raw": line})
    return events
