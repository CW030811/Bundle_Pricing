from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .config import AppConfig
from .reports import write_report
from .storage import AuditStore

REQUIRED_STRATEGY_FIELDS = {
    "id",
    "name",
    "family",
    "priority",
    "implementation_status",
    "logic",
    "data_requirements",
    "signal_construction",
    "entry_rules",
    "exit_rules",
    "position_sizing",
    "risk_management",
    "suitable_market_regimes",
    "failure_conditions",
    "reproducibility_difficulty",
    "backtest_status",
    "research_pipeline_stage",
    "factor_pipeline_status",
    "strategy_pipeline_status",
    "promotion_status",
    "pipeline_notes",
    "recommendation",
}

IMPLEMENTED_STATUSES = {
    "implemented_single_asset",
    "implemented_portfolio",
    "implemented_research",
}

BACKTESTED_STATUSES = {
    "partial",
    "walk_forward_and_costs_done",
    "walk_forward_weak",
}


def count_by_field(strategies: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in strategies:
        value = str(item.get(field) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def knowledge_base_path(config: AppConfig) -> Path:
    return Path("knowledge") / "bitcoin_strategy_knowledge_base.yaml"


def load_strategy_knowledge_base(path: Path | None = None) -> dict[str, Any]:
    selected_path = path or knowledge_base_path(AppConfig())
    with selected_path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    payload.setdefault("strategies", [])
    return payload


def validate_strategy_entry(entry: dict[str, Any]) -> list[str]:
    missing = sorted(field for field in REQUIRED_STRATEGY_FIELDS if field not in entry)
    issues = [f"missing:{field}" for field in missing]
    if not entry.get("sources"):
        issues.append("missing:sources")
    if entry.get("priority") not in {"high", "medium", "low"}:
        issues.append("invalid:priority")
    return issues


def registered_strategy_names(path: Path | None = None) -> set[str]:
    payload = load_strategy_knowledge_base(path)
    names: set[str] = set()
    for item in payload.get("strategies", []):
        for key in ("id", "implemented_as"):
            value = item.get(key)
            if value:
                names.add(str(value))
    return names


def missing_strategy_cards(strategy_names: list[str], path: Path | None = None) -> list[str]:
    registered = registered_strategy_names(path)
    return sorted({name for name in strategy_names if name and name not in registered})


def strategy_knowledge_summary(config: AppConfig, path: Path | None = None) -> dict[str, Any]:
    kb_path = path or knowledge_base_path(config)
    payload = load_strategy_knowledge_base(kb_path)
    strategies = payload.get("strategies", [])
    validation = {item.get("id", f"index_{idx}"): validate_strategy_entry(item) for idx, item in enumerate(strategies)}
    implemented = [item for item in strategies if item.get("implementation_status") in IMPLEMENTED_STATUSES]
    backtested = [item for item in strategies if item.get("backtest_status") in BACKTESTED_STATUSES]
    report_files = {path.name for path in config.report_dir.glob("*_latest.json")} if config.report_dir.exists() else set()
    report_coverage: dict[str, bool] = {}
    for item in strategies:
        report_name = item.get("report_name")
        if report_name:
            report_coverage[item["id"]] = f"{report_name}_latest.json" in report_files
        else:
            report_coverage[item["id"]] = False
    missing_implementation = [item["id"] for item in strategies if item.get("implementation_status") == "candidate"]
    missing_backtest = [item["id"] for item in strategies if item.get("backtest_status") == "not_started"]
    high_priority_next = [
        item["id"]
        for item in strategies
        if item.get("priority") == "high" and item.get("id") in (missing_implementation + missing_backtest)
    ]
    pipeline_summary = {
        "research_pipeline_stage": count_by_field(strategies, "research_pipeline_stage"),
        "factor_pipeline_status": count_by_field(strategies, "factor_pipeline_status"),
        "strategy_pipeline_status": count_by_field(strategies, "strategy_pipeline_status"),
        "promotion_status": count_by_field(strategies, "promotion_status"),
        "factor_pipeline_ready": [
            item["id"] for item in strategies if item.get("factor_pipeline_status") == "factor_pipeline_ready"
        ],
        "factor_pipeline_next": [
            item["id"]
            for item in strategies
            if item.get("factor_pipeline_status") in {"factor_pipeline_next_candidate", "factor_pipeline_candidate"}
        ],
        "strategy_validated": [
            item["id"]
            for item in strategies
            if str(item.get("strategy_pipeline_status", "")).startswith("strategy_validated")
        ],
    }
    return {
        "strategy": "bitcoin_strategy_knowledge_base",
        "knowledge_base_path": str(kb_path),
        "version": payload.get("version"),
        "updated_at": payload.get("updated_at"),
        "scope": payload.get("scope"),
        "total_strategies": len(strategies),
        "implemented_count": len(implemented),
        "backtested_count": len(backtested),
        "report_coverage_count": sum(1 for covered in report_coverage.values() if covered),
        "implemented_strategy_ids": [item["id"] for item in implemented],
        "backtested_strategy_ids": [item["id"] for item in backtested],
        "missing_implementation": missing_implementation,
        "missing_backtest": missing_backtest,
        "high_priority_next": high_priority_next,
        "pipeline_summary": pipeline_summary,
        "validation": validation,
        "valid": all(not issues for issues in validation.values()) and len(strategies) >= 10,
        "strategies": strategies,
    }


def strategy_knowledge_report(config: AppConfig, path: Path | None = None) -> Path:
    payload = strategy_knowledge_summary(config, path)
    sync_strategy_registry(config, path)
    return write_report(config.report_dir, "strategy_knowledge_base", payload)


def sync_strategy_registry(config: AppConfig, path: Path | None = None) -> dict[str, Any]:
    kb_path = path or knowledge_base_path(config)
    payload = load_strategy_knowledge_base(kb_path)
    strategies = payload.get("strategies", [])
    audit = AuditStore(config.state_dir)
    for strategy in strategies:
        audit.upsert_strategy_registry(strategy)
    return {
        "strategy_registry_path": str(kb_path),
        "synced_count": len(strategies),
        "strategy_ids": [item.get("id") for item in strategies],
    }
