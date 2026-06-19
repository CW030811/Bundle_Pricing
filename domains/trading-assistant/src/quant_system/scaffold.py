from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import AppConfig
from .knowledge import load_strategy_knowledge_base


def scaffold_strategy_research(
    config: AppConfig,
    *,
    strategy_id: str,
    name: str | None = None,
    family: str | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    target_dir = output_dir or Path("research_scaffolds")
    target_dir.mkdir(parents=True, exist_ok=True)
    card = _strategy_card(strategy_id)
    selected_name = name or card.get("name") or strategy_id.replace("_", " ").title()
    selected_family = family or card.get("family") or "unknown"
    path = target_dir / f"{strategy_id}_research_scaffold.md"
    path.write_text(
        _template(
            strategy_id=strategy_id,
            name=str(selected_name),
            family=str(selected_family),
            card=card,
            data_dir=str(config.data_dir),
            report_dir=str(config.report_dir),
        ),
        encoding="utf-8",
    )
    return {
        "strategy_id": strategy_id,
        "name": selected_name,
        "family": selected_family,
        "path": str(path),
        "from_existing_card": bool(card),
    }


def _strategy_card(strategy_id: str) -> dict[str, Any]:
    try:
        payload = load_strategy_knowledge_base()
    except FileNotFoundError:
        return {}
    for item in payload.get("strategies", []):
        if item.get("id") == strategy_id or item.get("implemented_as") == strategy_id:
            return item
    return {}


def _template(
    *,
    strategy_id: str,
    name: str,
    family: str,
    card: dict[str, Any],
    data_dir: str,
    report_dir: str,
) -> str:
    return f"""# Strategy Research Scaffold: {name}

Generated at: {datetime.now(timezone.utc).isoformat()}

## Identity

- strategy_id: `{strategy_id}`
- name: {name}
- family: {family}
- source_status: {"existing Strategy Card" if card else "new draft"}

## Hypothesis

{card.get("logic", "State the market phenomenon, who pays the edge, and why it should persist.")}

## Required Data

{_list_block(card.get("data_requirements", ["OHLCV", "fees", "slippage assumptions"]))}

## Signal Rules

- signal_construction: {card.get("signal_construction", "Define exact signal formula using only past/closed data.")}
- entry_rules: {card.get("entry_rules", "Define entry condition and execution timing.")}
- exit_rules: {card.get("exit_rules", "Define exit condition and risk exits.")}
- position_sizing: {card.get("position_sizing", "Define target exposure, caps, leverage, and turnover budget.")}

## Risk And Failure Modes

- risk_management:
{_list_block(card.get("risk_management", ["max exposure", "drawdown breaker", "kill switch"]))}
- suitable_market_regimes:
{_list_block(card.get("suitable_market_regimes", ["bull", "bear", "sideways", "high_volatility", "liquidity_poor"]))}
- failure_conditions:
{_list_block(card.get("failure_conditions", ["overfitting", "cost sensitivity", "regime break"]))}

## Implementation Checklist

- Add or update Strategy Card in `knowledge/bitcoin_strategy_knowledge_base.yaml`.
- Add factor builder if the hypothesis is factor-like.
- Run `research factor-evaluate` where applicable.
- Add strategy research function with confirmed candles and no future data.
- Run grid search with `parameter_stability`.
- Run walk-forward report with `rolling_walk_forward_v1`.
- Run cost sensitivity report with `cost_sensitivity_v1`.
- Compare against cash, buy-and-hold, simple trend, and random-entry baselines.
- Keep result out of paper/live until shortlist and service gates pass.

## Suggested Commands

```bash
PYTHONPATH=src python3 -m quant_system.cli data quality --persist --write-report
PYTHONPATH=src python3 -m quant_system.cli research knowledge-base --sync-registry
PYTHONPATH=src python3 -m quant_system.cli report index --limit 20
PYTHONPATH=src python3 -m quant_system.cli report ads --kind reproducibility --limit 20
```

## Paths

- data_dir: `{data_dir}`
- report_dir: `{report_dir}`
"""


def _list_block(values: Any) -> str:
    if isinstance(values, list):
        return "\n".join(f"  - {value}" for value in values)
    if values:
        return f"  - {values}"
    return "  - TODO"
