from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import AppConfig
from .notifications import notify
from .reports import write_report
from .storage import AuditStore


def read_report(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def review_queue(config: AppConfig, limit: int = 50) -> dict[str, Any]:
    store = AuditStore(config.state_dir)
    tasks: list[dict[str, Any]] = []
    tasks.extend(data_quality_review_tasks(store, limit=limit))
    tasks.extend(service_review_tasks(store, limit=limit))
    tasks.extend(promotion_review_tasks(config))
    tasks.extend(pre_live_review_tasks(config))
    tasks.extend(notification_review_tasks(config))
    deduped = dedupe_tasks(tasks)
    return {
        "schema": "review_queue_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "task_count": len(deduped),
        "tasks": deduped,
        "summary": review_summary(deduped),
    }


def data_quality_review_tasks(store: AuditStore, limit: int) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for row in store.recent_rows("quality_issues", limit=limit):
        item = dict(row)
        if int(item.get("is_resolved") or 0):
            continue
        severity = str(item.get("severity") or "info")
        if severity not in {"error", "warning"}:
            continue
        source_id = str(item.get("id") or f"{item.get('symbol')}-{item.get('issue_type')}")
        tasks.append(
            task(
                source_type="data_quality_issue",
                source_id=source_id,
                category="data_quality",
                severity=severity,
                title=f"{item.get('symbol')} {item.get('issue_type')}",
                details=str(item.get("issue_detail") or ""),
                payload=item,
            )
        )
    return tasks


def service_review_tasks(store: AuditStore, limit: int) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for row in store.recent_rows("service_runs", limit=limit):
        item = dict(row)
        consecutive_errors = int(item.get("consecutive_errors") or 0)
        ok = bool(item.get("ok"))
        if ok and consecutive_errors <= 0:
            continue
        severity = "critical" if not ok else "warning"
        source_id = str(item.get("id") or f"{item.get('service_name')}-{item.get('completed_at')}")
        details = str(item.get("stop_reason") or f"consecutive_errors={consecutive_errors}")
        tasks.append(
            task(
                source_type="service_run",
                source_id=source_id,
                category="service_exception",
                severity=severity,
                title=f"{item.get('service_name')} needs review",
                details=details,
                payload=item,
            )
        )
    return tasks


def promotion_review_tasks(config: AppConfig) -> list[dict[str, Any]]:
    payload = read_report(config.report_dir / "strategy_promotion_scorecard_latest.json")
    if not payload:
        return []
    tasks: list[dict[str, Any]] = []
    for row in payload.get("ranked", []):
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "unknown_strategy")
        stage = str(row.get("stage") or "")
        status = str(row.get("promotion_status") or "")
        research_blocker_count = int(row.get("research_blocker_count") or 0)
        if stage in {"paper", "small_live"}:
            tasks.append(
                task(
                    source_type="promotion_candidate",
                    source_id=name,
                    category="strategy_promotion",
                    severity="info" if status != "blocked" else "warning",
                    title=f"{name} promotion candidate",
                    details=f"stage={stage}; status={status}",
                    payload=row,
                )
            )
        elif status == "blocked" and research_blocker_count > 0:
            tasks.append(
                task(
                    source_type="strategy_downgrade",
                    source_id=name,
                    category="strategy_review",
                    severity="warning",
                    title=f"{name} remains blocked",
                    details="; ".join(str(item) for item in row.get("blockers", [])),
                    payload=row,
                )
            )
    return tasks


def pre_live_review_tasks(config: AppConfig) -> list[dict[str, Any]]:
    payload = read_report(config.report_dir / "pre_live_check_latest.json")
    if not payload or payload.get("status") in {"passed", "ok"}:
        return []
    return [
        task(
            source_type="pre_live_check",
            source_id=str(payload.get("generated_at") or "latest"),
            category="pre_live_gate",
            severity="critical",
            title="pre-live check failed",
            details=str(payload.get("status") or "failed"),
            payload=payload,
        )
    ]


def notification_review_tasks(config: AppConfig) -> list[dict[str, Any]]:
    payload = read_report(config.report_dir / "notification_drill_latest.json")
    if not payload or payload.get("status") == "passed":
        return []
    return [
        task(
            source_type="notification_drill",
            source_id=str(payload.get("status") or "latest"),
            category="notification",
            severity="warning",
            title="external notification drill not passed",
            details=f"status={payload.get('status')}; webhook_configured={payload.get('webhook_configured')}",
            payload=payload,
        )
    ]


def task(
    *,
    source_type: str,
    source_id: str,
    category: str,
    severity: str,
    title: str,
    details: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "source_type": source_type,
        "source_id": source_id,
        "category": category,
        "severity": severity,
        "status": "open",
        "title": title,
        "details": details,
        "payload": payload,
    }


def dedupe_tasks(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[tuple[str, str], dict[str, Any]] = {}
    for item in tasks:
        seen[(str(item["source_type"]), str(item["source_id"]))] = item
    severity_rank = {"critical": 3, "error": 2, "warning": 1, "info": 0}
    return sorted(
        seen.values(),
        key=lambda item: (severity_rank.get(str(item.get("severity")), 0), str(item.get("category")), str(item.get("title"))),
        reverse=True,
    )


def review_summary(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    by_severity: dict[str, int] = {}
    by_category: dict[str, int] = {}
    for item in tasks:
        severity = str(item.get("severity") or "info")
        category = str(item.get("category") or "general")
        by_severity[severity] = by_severity.get(severity, 0) + 1
        by_category[category] = by_category.get(category, 0) + 1
    return {
        "by_severity": by_severity,
        "by_category": by_category,
        "open_count": len(tasks),
        "requires_attention": any(item.get("severity") in {"critical", "error", "warning"} for item in tasks),
    }


def review_queue_report(config: AppConfig, *, send_notification: bool = False, limit: int = 50) -> Path:
    payload = review_queue(config, limit=limit)
    AuditStore(config.state_dir).upsert_review_tasks(payload["tasks"])
    if send_notification and payload["tasks"]:
        notify(
            config,
            "review_queue",
            "warning" if payload["summary"].get("requires_attention") else "info",
            {"task_count": payload["task_count"], "summary": payload["summary"]},
        )
    return write_report(config.report_dir, "review_queue", payload)
