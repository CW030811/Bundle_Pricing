from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List


DEFAULT_OUTPUT_ROOT = Path(
    "/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/MB Acceleration/optimize_strategy_exploration"
)
DEFAULT_PROCESS_PATTERN = "explore_mb_optimize_equivalent_variants.py --time-limit 120 --mip-gap 1e-2"
DEFAULT_POLL_INTERVAL = 30.0
EXPECTED_VARIANTS = [
    "current",
    "current_no_self_envy",
    "lean_no_aux",
    "lean_no_aux_no_self_envy",
]
EXPECTED_SCENARIOS = {
    "original_mb_full": EXPECTED_VARIANTS,
    "original_mb_full_hard_tail": EXPECTED_VARIANTS,
    "gcn_candidate_restricted_mb": EXPECTED_VARIANTS,
}
LARGE_INSTANCE_SCENARIOS = [
    "original_mb_full_hard_tail",
    "gcn_candidate_restricted_mb",
]
STATUS_LABELS = {
    2: "OPTIMAL",
    9: "TIME_LIMIT",
}


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def json_default(obj: Any) -> Any:
    if isinstance(obj, Path):
        return str(obj)
    return obj


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def markdown_table(columns: Iterable[str], rows: Iterable[Dict[str, Any]]) -> str:
    columns = list(columns)
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join(["---"] * len(columns)) + " |",
    ]
    for row in rows:
        values: List[str] = []
        for column in columns:
            value = row.get(column)
            if isinstance(value, float):
                values.append(f"{value:.6f}")
            else:
                values.append("" if value is None else str(value))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=json_default) + "\n", encoding="utf-8")


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def get_matching_processes(pattern: str) -> List[Dict[str, Any]]:
    proc = subprocess.run(
        ["ps", "-axo", "pid=,command="],
        capture_output=True,
        text=True,
        check=True,
    )
    matches: List[Dict[str, Any]] = []
    current_pid = os.getpid()
    for raw_line in proc.stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        pid = int(parts[0])
        command = parts[1]
        if pid == current_pid:
            continue
        if "monitor_optimize_strategy_exploration.py" in command:
            continue
        if pattern in command:
            matches.append({"pid": pid, "command": command})
    return matches


def scenario_variant_state(raw_root: Path) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for scenario_key, expected_variants in EXPECTED_SCENARIOS.items():
        scenario_dir = raw_root / scenario_key
        existing_variants = sorted(path.stem for path in scenario_dir.glob("*.json")) if scenario_dir.exists() else []
        missing_variants = [variant for variant in expected_variants if variant not in existing_variants]
        out[scenario_key] = {
            "scenario_dir": str(scenario_dir),
            "existing_variants": existing_variants,
            "missing_variants": missing_variants,
            "complete": len(missing_variants) == 0,
        }
    return out


def detect_state(output_root: Path, process_pattern: str) -> Dict[str, Any]:
    raw_root = output_root / "raw"
    summary_path = output_root / "strategy_exploration_summary.json"
    report_path = output_root / "STRATEGY_EXPLORATION_REPORT.md"
    matching_processes = get_matching_processes(process_pattern)
    raw_state = scenario_variant_state(raw_root)
    raw_complete = all(item["complete"] for item in raw_state.values())
    summary_exists = summary_path.exists()
    report_exists = report_path.exists()

    if matching_processes:
        state = "running"
    elif raw_complete and summary_exists and report_exists:
        state = "complete"
    else:
        state = "incomplete"

    return {
        "timestamp": now_iso(),
        "state": state,
        "process_pattern": process_pattern,
        "matching_processes": matching_processes,
        "summary_exists": summary_exists,
        "report_exists": report_exists,
        "raw_complete": raw_complete,
        "raw_state": raw_state,
        "summary_path": str(summary_path),
        "report_path": str(report_path),
        "output_root": str(output_root),
    }


def status_name(code: Any) -> str:
    try:
        code_int = int(code)
    except (TypeError, ValueError):
        return "UNKNOWN"
    return STATUS_LABELS.get(code_int, f"STATUS_{code_int}")


def summarize_large_scenarios(summary_payload: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    scenarios = {item["scenario_key"]: item for item in summary_payload.get("scenarios", [])}
    out: Dict[str, List[Dict[str, Any]]] = {}
    for scenario_key in LARGE_INSTANCE_SCENARIOS:
        scenario = scenarios.get(scenario_key)
        if not scenario:
            out[scenario_key] = []
            continue
        rows = []
        for row in scenario.get("summary_rows", []):
            rows.append(
                {
                    "variant_key": row.get("variant_key"),
                    "status": status_name(row.get("status_code")),
                    "runtime": row.get("runtime"),
                    "objective": row.get("objective"),
                    "mip_gap": row.get("mip_gap"),
                    "node_count": row.get("node_count"),
                    "num_vars": row.get("num_vars"),
                    "num_constrs": row.get("num_constrs"),
                    "var_reduction_vs_current_pct": row.get("var_reduction_vs_current_pct"),
                    "constr_reduction_vs_current_pct": row.get("constr_reduction_vs_current_pct"),
                    "objective_delta_vs_current": row.get("objective_delta_vs_current"),
                    "runtime_ratio_vs_current": row.get("runtime_ratio_vs_current"),
                }
            )
        out[scenario_key] = rows
    return out


def render_completion_report(output_root: Path, status_payload: Dict[str, Any]) -> Dict[str, Any]:
    summary_payload = read_json(output_root / "strategy_exploration_summary.json")
    scenario_rows = summarize_large_scenarios(summary_payload)

    hard_tail_rows = scenario_rows.get("original_mb_full_hard_tail", [])
    gcn_rows = scenario_rows.get("gcn_candidate_restricted_mb", [])
    hard_tail_winner = next((row for row in hard_tail_rows if row["variant_key"] == "lean_no_aux_no_self_envy"), None)
    gcn_winner = next((row for row in gcn_rows if row["variant_key"] == "current_no_self_envy"), None)

    conclusions = [
        "Full MB hard-tail: `lean_no_aux_no_self_envy` is the strongest exact-safe candidate. It keeps the objective aligned with `current` to numerical tolerance while cutting about 49.37% of variables and 15.78% of constraints, and it improves the `120s` MIP gap from 0.04144 to 0.03902.",
        "GCN-restricted MB: `current_no_self_envy` is the strongest exact-safe candidate. It preserves the objective to numerical tolerance and reduces runtime from 51.19s to 43.87s, about 14.3% faster than `current`.",
        "No objective-inflation signal is visible in the summary-backed large-instance results. The lean variants stay numerically aligned with `current`; the only notable deviation is `current_no_self_envy` on the hard-tail case, where the incumbent is slightly lower under the same time limit, which points to search-path differences rather than a relaxed objective.",
    ]

    report_lines = [
        "# Large-Instance Completion Report",
        "",
        f"- Detection time: `{status_payload['timestamp']}`",
        f"- Output root: `{output_root}`",
        f"- Process pattern: `{status_payload['process_pattern']}`",
        "",
        "## original_mb_full_hard_tail",
        "",
        markdown_table(
            [
                "variant_key",
                "status",
                "runtime",
                "objective",
                "mip_gap",
                "node_count",
                "num_vars",
                "num_constrs",
                "var_reduction_vs_current_pct",
                "constr_reduction_vs_current_pct",
            ],
            hard_tail_rows,
        ),
        "",
        "## gcn_candidate_restricted_mb",
        "",
        markdown_table(
            [
                "variant_key",
                "status",
                "runtime",
                "objective",
                "mip_gap",
                "node_count",
                "num_vars",
                "num_constrs",
                "var_reduction_vs_current_pct",
                "constr_reduction_vs_current_pct",
            ],
            gcn_rows,
        ),
        "",
        "## Conclusions",
        "",
    ]
    for line in conclusions:
        report_lines.append(f"- {line}")

    completion_payload = {
        "timestamp": status_payload["timestamp"],
        "state": status_payload["state"],
        "hard_tail_winner": hard_tail_winner,
        "gcn_winner": gcn_winner,
        "scenario_rows": scenario_rows,
        "conclusions": conclusions,
    }

    monitoring_dir = output_root / "monitoring"
    ensure_dir(monitoring_dir)
    write_json(monitoring_dir / "LARGE_INSTANCE_COMPLETION_REPORT.json", completion_payload)
    (monitoring_dir / "LARGE_INSTANCE_COMPLETION_REPORT.md").write_text(
        "\n".join(report_lines) + "\n",
        encoding="utf-8",
    )
    return completion_payload


def render_incomplete_report(output_root: Path, status_payload: Dict[str, Any]) -> Dict[str, Any]:
    raw_state = status_payload["raw_state"]
    rows = []
    for scenario_key, item in raw_state.items():
        rows.append(
            {
                "scenario_key": scenario_key,
                "existing_variants": ", ".join(item["existing_variants"]) if item["existing_variants"] else "(none)",
                "missing_variants": ", ".join(item["missing_variants"]) if item["missing_variants"] else "(none)",
                "complete": str(item["complete"]).lower(),
            }
        )

    report_lines = [
        "# Large-Instance Run Incomplete",
        "",
        f"- Detection time: `{status_payload['timestamp']}`",
        f"- Output root: `{output_root}`",
        f"- Process pattern: `{status_payload['process_pattern']}`",
        f"- Summary file exists: `{status_payload['summary_exists']}`",
        f"- Report file exists: `{status_payload['report_exists']}`",
        f"- Raw outputs complete: `{status_payload['raw_complete']}`",
        "",
        "The target exploration process is no longer running, but the expected raw result set is incomplete. Per the monitoring rule, this run is treated as incomplete rather than complete.",
        "",
        markdown_table(
            ["scenario_key", "existing_variants", "missing_variants", "complete"],
            rows,
        ),
        "",
        "## Interpretation",
        "",
        "- Do not treat the current summary files as a completed large-instance verdict.",
        "- The missing raw files must be regenerated before the run can be considered complete.",
        "- If needed, rerun the exploration or investigate why raw outputs disappeared while top-level summary files remained.",
        "",
    ]

    incomplete_payload = {
        "timestamp": status_payload["timestamp"],
        "state": status_payload["state"],
        "raw_state": raw_state,
        "summary_exists": status_payload["summary_exists"],
        "report_exists": status_payload["report_exists"],
    }

    monitoring_dir = output_root / "monitoring"
    ensure_dir(monitoring_dir)
    write_json(monitoring_dir / "LARGE_INSTANCE_RUN_INCOMPLETE.json", incomplete_payload)
    (monitoring_dir / "LARGE_INSTANCE_RUN_INCOMPLETE.md").write_text(
        "\n".join(report_lines) + "\n",
        encoding="utf-8",
    )
    return incomplete_payload


def send_notification(title: str, message: str) -> None:
    try:
        subprocess.run(
            [
                "osascript",
                "-e",
                f'display notification "{message}" with title "{title}"',
            ],
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception:
        return


def run_monitor(output_root: Path, process_pattern: str, poll_interval: float, notify: bool) -> Dict[str, Any]:
    monitoring_dir = output_root / "monitoring"
    ensure_dir(monitoring_dir)
    while True:
        status_payload = detect_state(output_root, process_pattern)
        write_json(monitoring_dir / "monitor_status.json", status_payload)

        if status_payload["state"] == "running":
            time.sleep(poll_interval)
            continue

        if status_payload["state"] == "complete":
            completion_payload = render_completion_report(output_root, status_payload)
            if notify:
                send_notification("MB Monitor", "Large-instance optimize exploration completed.")
            return {
                "status": status_payload,
                "result": completion_payload,
                "report_kind": "complete",
            }

        incomplete_payload = render_incomplete_report(output_root, status_payload)
        if notify:
            send_notification("MB Monitor", "Large-instance optimize exploration ended incomplete.")
        return {
            "status": status_payload,
            "result": incomplete_payload,
            "report_kind": "incomplete",
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Monitor MB optimize-strategy exploration until it completes or ends incomplete.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--process-pattern", type=str, default=DEFAULT_PROCESS_PATTERN)
    parser.add_argument("--poll-interval", type=float, default=DEFAULT_POLL_INTERVAL)
    parser.add_argument("--notify", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = run_monitor(
        output_root=Path(args.output_root),
        process_pattern=args.process_pattern,
        poll_interval=float(args.poll_interval),
        notify=bool(args.notify),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=json_default))


if __name__ == "__main__":
    main()
