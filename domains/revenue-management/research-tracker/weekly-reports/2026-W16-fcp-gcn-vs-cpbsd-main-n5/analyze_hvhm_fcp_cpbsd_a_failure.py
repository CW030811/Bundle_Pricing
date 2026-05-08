from __future__ import annotations

import json
import math
import sys
import warnings
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

import msgpack
import msgpack_numpy as mnp
import numpy as np
import gurobipy as gp
from gurobipy import GRB


DOMAIN_ROOT = Path("/Users/sensen/.openclaw/workspace/domains/revenue-management")
DATA_SRC = DOMAIN_ROOT / "project-root/code_submission_project/code_submission/src/data"
sys.path.insert(0, str(DATA_SRC))

from generate_data_CPBSD import sample_valuations, valuation_means  # noqa: E402
from run_anchored_fcp_bsp_hvhm_batch import (  # noqa: E402
    evaluate_bsp_choices,
    evaluate_cpbsd_a_choices,
    evaluate_fcp_choices,
)
from solve_anchored_fcp_bsp import (  # noqa: E402
    _bsp_prefix_values_and_costs,
    _cross_menu_fcp_splits,
    _normalize_assortments_and_prices,
)


REPORT_DIR = DOMAIN_ROOT / "research-tracker/weekly-reports/2026-W16-fcp-gcn-vs-cpbsd-main-n5"
INPUT_ROOT = DOMAIN_ROOT / "experiments/fcp_mb_phase2_selected_n10_n30_5inst"
ANCHORED_ROOT = DOMAIN_ROOT / "experiments/anchored_fcp_bsp_hvhm_batch/per_seed"
OUTPUT_PATH = REPORT_DIR / "hvhm_fcp_cpbsd_a_failure_analysis.md"

SETTING = "normal_rho0.0_full_hvhm"
K_OUT = 5000
EPS = 1e-9


def load_json(path: Path) -> dict:
    with path.open("r") as f:
        return json.load(f)


def load_instance(path: Path) -> tuple[dict, np.ndarray, np.ndarray]:
    with path.open("rb") as f:
        obj = msgpack.load(f, object_hook=mnp.decode, strict_map_key=False)
    return obj, np.asarray(obj["valuation_samples_V"], dtype=float), np.asarray(obj["production_cost_c"], dtype=float)


def oos_samples(setup: dict, k_out: int = K_OUT) -> np.ndarray:
    rng = np.random.default_rng(int(setup["seed"]) + 99991)
    means = valuation_means(int(setup["n_products"]), setup["heterogeneity"])
    return sample_valuations(
        k=k_out,
        means=means,
        family=setup["dist_family"],
        rho=float(setup["rho"]),
        rng=rng,
    )


def normalize_numeric_keys(obj: dict | None) -> dict[int, float]:
    return {int(k): float(v) for k, v in (obj or {}).items()}


def run_dir_for(n_products: int, seed: int, setting: str = SETTING) -> Path:
    return INPUT_ROOT / f"n{n_products}" / setting / "runs" / f"seed_{seed}"


def fmt(x: object, digits: int = 4) -> str:
    if x is None:
        return ""
    if isinstance(x, str):
        return x
    if isinstance(x, (int, np.integer)):
        return str(int(x))
    try:
        val = float(x)
    except (TypeError, ValueError):
        return str(x)
    if not math.isfinite(val):
        return str(val)
    return f"{val:.{digits}f}"


def md_table(headers: list[str], rows: Iterable[Iterable[object]], digits: int = 4) -> list[str]:
    rows_list = [list(r) for r in rows]
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows_list:
        out.append("| " + " | ".join(fmt(x, digits) for x in row) + " |")
    return out


def qstats(values: Iterable[float]) -> dict[str, float]:
    arr = np.asarray(list(values), dtype=float)
    if arr.size == 0:
        return {"count": 0, "mean": 0.0, "p10": 0.0, "p25": 0.0, "p50": 0.0, "p75": 0.0, "p90": 0.0, "min": 0.0, "max": 0.0}
    return {
        "count": int(arr.size),
        "mean": float(arr.mean()),
        "p10": float(np.quantile(arr, 0.10)),
        "p25": float(np.quantile(arr, 0.25)),
        "p50": float(np.quantile(arr, 0.50)),
        "p75": float(np.quantile(arr, 0.75)),
        "p90": float(np.quantile(arr, 0.90)),
        "min": float(arr.min()),
        "max": float(arr.max()),
    }


def choice_summary(choices: list[dict]) -> dict:
    buyers = [c for c in choices if c["channel"] != "outside"]
    return {
        "K": len(choices),
        "buyers": len(buyers),
        "outside": len(choices) - len(buyers),
        "avg_profit_all": float(np.mean([c["profit"] for c in choices])) if choices else 0.0,
        "avg_profit_buyers": float(np.mean([c["profit"] for c in buyers])) if buyers else 0.0,
        "avg_surplus_buyers": float(np.mean([c["surplus"] for c in buyers])) if buyers else 0.0,
        "channels": dict(Counter(c["channel"] for c in choices)),
        "size_counts": dict(sorted(Counter(int(c.get("size", 0)) for c in buyers).items())),
        "profit_q_all": qstats(c["profit"] for c in choices),
        "profit_q_buyers": qstats(c["profit"] for c in buyers),
    }


def channel_profit_rows(choices: list[dict]) -> list[list[object]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for choice in choices:
        grouped[str(choice["channel"])].append(choice)
    rows = []
    total_k = len(choices)
    for channel in sorted(grouped):
        group = grouped[channel]
        profits = [float(c["profit"]) for c in group]
        rows.append([
            channel,
            len(group),
            len(group) / total_k,
            np.mean(profits) if profits else 0.0,
            np.sum(profits) / total_k,
            np.quantile(profits, 0.25) if profits else 0.0,
            np.quantile(profits, 0.50) if profits else 0.0,
            np.quantile(profits, 0.75) if profits else 0.0,
        ])
    return rows


def size_count_rows(choices: list[dict]) -> list[list[object]]:
    counts = Counter(int(c.get("size", 0)) for c in choices if c["channel"] != "outside")
    return [[size, count] for size, count in sorted(counts.items())]


def average_profit(choices: list[dict]) -> float:
    return float(np.mean([float(c["profit"]) for c in choices])) if choices else 0.0


def evaluate_fcp_cpbsd_a_hybrid(fcp_choices: list[dict], cpbsd_choices: list[dict]) -> list[dict]:
    hybrid = []
    for fcp, cpbsd in zip(fcp_choices, cpbsd_choices):
        f_surplus = float(fcp["surplus"])
        c_surplus = float(cpbsd["surplus"])
        if f_surplus <= 0.0 and c_surplus <= 0.0:
            hybrid.append({"channel": "outside", "profit": 0.0, "surplus": 0.0, "size": 0})
        elif f_surplus > c_surplus + EPS:
            hybrid.append({**fcp, "channel": "fcp"})
        elif c_surplus > f_surplus + EPS:
            hybrid.append({**cpbsd, "channel": "cpbsd_a"})
        elif float(fcp["profit"]) >= float(cpbsd["profit"]):
            hybrid.append({**fcp, "channel": "fcp"})
        else:
            hybrid.append({**cpbsd, "channel": "cpbsd_a"})
    return hybrid


def fcp_solver_choices(v_in: np.ndarray, c_n: np.ndarray, fcp_res: dict) -> list[dict]:
    prices = normalize_numeric_keys(fcp_res.get("bundle_prices_full") or fcp_res.get("bundle_prices") or {})
    assortments = np.asarray(fcp_res["assortments"], dtype=int)
    costs = assortments @ c_n
    choices = []
    for k, raw_idx in enumerate(fcp_res.get("chosen_bundle_idx_by_customer") or []):
        idx = int(raw_idx)
        if idx <= 0:
            choices.append({"channel": "outside", "profit": 0.0, "surplus": 0.0, "bundle_idx": None, "size": 0})
            continue
        price = float(prices.get(idx, 0.0))
        profit = price - float(costs[idx])
        surplus = float(v_in[k] @ assortments[idx]) - price
        choices.append({
            "channel": "fcp",
            "profit": profit,
            "surplus": surplus,
            "bundle_idx": idx,
            "size": int(assortments[idx].sum()),
        })
    return choices


def anchored_solver_choices(v_in: np.ndarray, c_n: np.ndarray, anchored_res: dict | None) -> list[dict]:
    if not anchored_res:
        return []
    prices = normalize_numeric_keys(anchored_res.get("bundle_prices_full") or {})
    size_prices = normalize_numeric_keys(anchored_res.get("size_prices") or {})
    assortments = np.asarray(anchored_res.get("assortments") or [], dtype=int)
    costs = assortments @ c_n if assortments.size else np.asarray([])
    choices = []
    for k, item in enumerate(anchored_res.get("chosen_option_by_customer") or []):
        channel, raw_idx = item
        if channel == "outside":
            choices.append({"channel": "outside", "profit": 0.0, "surplus": 0.0, "size": 0})
            continue
        idx = int(raw_idx)
        if channel == "fcp":
            price = float(prices.get(idx, 0.0))
            profit = price - float(costs[idx])
            surplus = float(v_in[k] @ assortments[idx]) - price
            choices.append({
                "channel": "fcp",
                "profit": profit,
                "surplus": surplus,
                "bundle_idx": idx,
                "size": int(assortments[idx].sum()),
            })
            continue
        if channel == "bsp":
            size = idx
            order = np.argsort(-v_in[k])
            selected = order[:size]
            price = float(size_prices.get(size, 0.0))
            choices.append({
                "channel": "bsp",
                "profit": price - float(c_n[selected].sum()),
                "surplus": float(v_in[k, selected].sum()) - price,
                "size": size,
            })
            continue
        raise ValueError(f"Unknown anchored channel: {channel}")
    return choices


def migration_counts(base: list[dict], hybrid: list[dict]) -> dict[str, int]:
    counts = Counter((str(a["channel"]), str(b["channel"])) for a, b in zip(base, hybrid))
    return {f"{src}->{dst}": int(count) for (src, dst), count in sorted(counts.items())}


def fcp_cannibalization_rows(
    fcp_choices: list[dict],
    cpbsd_choices: list[dict],
    hybrid_choices: list[dict],
) -> list[list[object]]:
    groups = {
        "CPBSD-A buyer -> FCP": [
            i for i, (c, h) in enumerate(zip(cpbsd_choices, hybrid_choices))
            if c["channel"] == "cpbsd_a" and h["channel"] == "fcp"
        ],
        "CPBSD-A outside -> FCP": [
            i for i, (c, h) in enumerate(zip(cpbsd_choices, hybrid_choices))
            if c["channel"] == "outside" and h["channel"] == "fcp"
        ],
        "FCP outside -> CPBSD-A": [
            i for i, (f, h) in enumerate(zip(fcp_choices, hybrid_choices))
            if f["channel"] == "outside" and h["channel"] == "cpbsd_a"
        ],
    }
    rows = []
    for label, idxs in groups.items():
        if not idxs:
            rows.append([label, 0, 0.0, 0.0, 0.0, 0.0, 0.0])
            continue
        f_profit = np.asarray([fcp_choices[i]["profit"] for i in idxs], dtype=float)
        c_profit = np.asarray([cpbsd_choices[i]["profit"] for i in idxs], dtype=float)
        h_profit = np.asarray([hybrid_choices[i]["profit"] for i in idxs], dtype=float)
        f_surplus = np.asarray([fcp_choices[i]["surplus"] for i in idxs], dtype=float)
        c_surplus = np.asarray([cpbsd_choices[i]["surplus"] for i in idxs], dtype=float)
        rows.append([
            label,
            len(idxs),
            float(f_profit.mean()),
            float(c_profit.mean()),
            float(h_profit.mean()),
            float((h_profit - c_profit).mean()),
            float((f_surplus - c_surplus).mean()),
        ])
    return rows


def fcp_solution_rows(fcp_res: dict, c_n: np.ndarray, in_choices: list[dict]) -> list[list[object]]:
    prices = normalize_numeric_keys(fcp_res.get("bundle_prices_full") or fcp_res.get("bundle_prices") or {})
    selected_prices = normalize_numeric_keys(fcp_res.get("bundle_prices") or {})
    assortments = np.asarray(fcp_res["assortments"], dtype=int)
    costs = assortments @ c_n
    choice_counts = Counter(int(c["bundle_idx"]) for c in in_choices if c["channel"] == "fcp" and c.get("bundle_idx") is not None)
    rows = []
    for idx, count in choice_counts.most_common(12):
        row = assortments[idx]
        rows.append([
            idx,
            int(row.sum()),
            float(prices.get(idx, 0.0)),
            float(costs[idx]),
            float(prices.get(idx, 0.0) - costs[idx]),
            count,
            "yes" if idx in selected_prices else "full-only",
            "".join(str(int(x)) for x in row.tolist()),
        ])
    return rows


def solution_vector_block(label: str, values: Iterable[float]) -> list[str]:
    values_list = list(values)
    chunks = []
    for start in range(0, len(values_list), 10):
        piece = ", ".join(f"{i}:{values_list[i]:.4f}" for i in range(start, min(start + 10, len(values_list))))
        chunks.append(piece)
    return [f"**{label}**", "", "```text", *chunks, "```"]


def price_by_size_rows(size_prices: dict) -> list[list[object]]:
    prices = normalize_numeric_keys(size_prices)
    return [[s, prices[s]] for s in sorted(prices)]


def evaluate_fcp_bsp_hybrid(fcp_choices: list[dict], bsp_choices: list[dict]) -> list[dict]:
    hybrid = []
    for fcp, bsp in zip(fcp_choices, bsp_choices):
        f_surplus = float(fcp["surplus"])
        b_surplus = float(bsp["surplus"])
        if f_surplus <= 0.0 and b_surplus <= 0.0:
            hybrid.append({"channel": "outside", "profit": 0.0, "surplus": 0.0, "size": 0})
        elif f_surplus > b_surplus + EPS:
            hybrid.append({**fcp, "channel": "fcp"})
        elif b_surplus > f_surplus + EPS:
            hybrid.append({**bsp, "channel": "bsp"})
        elif float(fcp["profit"]) >= float(bsp["profit"]):
            hybrid.append({**fcp, "channel": "fcp"})
        else:
            hybrid.append({**bsp, "channel": "bsp"})
    return hybrid


def _max_or_none(items: list[tuple[float, str]]) -> tuple[float, str] | None:
    if not items:
        return None
    return max(items, key=lambda x: x[0])


def q_lower_bound_diagnostics(case: dict) -> dict:
    n_products = int(case["N"])
    v_in = case["v_in"]
    c_n = case["c_n"]
    fcp_res = case["fcp_res"]
    anchored = case["anchored_payload"]["anchored_result"]
    assortments, fixed_prices, old_to_new = _normalize_assortments_and_prices(
        np.asarray(fcp_res["assortments"], dtype=int),
        fcp_res.get("bundle_prices_full") or fcp_res.get("bundle_prices") or {},
        n_products,
    )
    active = sorted(
        i for i, p in fixed_prices.items()
        if i != 0 and p is not None and int(assortments[i].sum()) > 0
    )
    sizes = assortments.sum(axis=1).astype(int)
    v_ki = v_in @ assortments.T
    v_ks, _ = _bsp_prefix_values_and_costs(v_in, c_n)

    chosen = []
    selected_surplus = []
    for k, old_idx in enumerate(fcp_res.get("chosen_bundle_idx_by_customer") or []):
        mapped = old_to_new.get(int(old_idx))
        if mapped in active:
            chosen.append(mapped)
            selected_surplus.append(float(v_ki[k, mapped]) - float(fixed_prices[mapped]))
        else:
            chosen.append(None)
            selected_surplus.append(0.0)

    split_rows_by_size: dict[int, list[tuple[float, str]]] = defaultdict(list)
    for parent, child, delta in _cross_menu_fcp_splits(assortments, active):
        if delta < 1:
            continue
        bound = float(fixed_prices[parent]) - float(fixed_prices[child])
        witness = (
            f"parent {parent} price {fixed_prices[parent]:.4f} "
            f"- child {child} price {fixed_prices[child]:.4f}"
        )
        split_rows_by_size[delta].append((bound, witness))

    raw_bound_rows = []
    for size in range(1, n_products + 1):
        same = [
            (
                float(fixed_prices[i]),
                f"bundle {i} size {size} price {fixed_prices[i]:.4f}",
            )
            for i in active
            if int(sizes[i]) == size
        ]
        protect = []
        c2_all = []
        c2_outside = []
        for k in range(v_in.shape[0]):
            bound = float(v_ks[k, size]) - selected_surplus[k]
            if chosen[k] is None:
                c2_outside.append((bound, f"outside customer {k}: V^B_{{k,{size}}}={v_ks[k, size]:.4f}, u_k=0"))
            else:
                protect.append((
                    bound,
                    f"protected customer {k}: V^B_{{k,{size}}}={v_ks[k, size]:.4f}, "
                    f"FCP surplus={selected_surplus[k]:.4f}",
                ))
            c2_all.append((
                bound,
                f"customer {k}: V^B_{{k,{size}}}={v_ks[k, size]:.4f}, selected surplus={selected_surplus[k]:.4f}",
            ))

        source_candidates = []
        for family, rows in [
            ("c10_same_size", same),
            ("c11_cross_split", split_rows_by_size.get(size, [])),
            ("c12_protect_fcp/c2_surplus_bsp", protect),
            ("c2_surplus_bsp_outside", c2_outside),
        ]:
            best = _max_or_none(rows)
            if best:
                source_candidates.append((best[0], family, best[1]))
        best_source = max(source_candidates, key=lambda x: x[0]) if source_candidates else (0.0, "", "")
        raw_bound_rows.append({
            "size": size,
            "raw_bound": best_source[0],
            "raw_family": best_source[1],
            "raw_witness": best_source[2],
            "same": _max_or_none(same),
            "split": _max_or_none(split_rows_by_size.get(size, [])),
            "protect": _max_or_none(protect),
            "outside": _max_or_none(c2_outside),
            "all_c2": _max_or_none(c2_all),
        })

    model = gp.Model("min_q_diagnostic")
    model.Params.OutputFlag = 0
    q = model.addVars(range(n_products + 1), lb=0.0, ub=float(anchored["price_upper_bound"]), name="q")
    model.addConstr(q[0] == 0.0, name="q0")
    for size in range(n_products):
        model.addConstr(q[size + 1] >= q[size], name=f"mono_{size}")
    for a in range(1, n_products + 1):
        for b in range(a, n_products + 1):
            if a + b <= n_products:
                model.addConstr(q[a + b] <= q[a] + q[b], name=f"subadd_{a}_{b}")
    for i in active:
        size = int(sizes[i])
        if size >= 1:
            model.addConstr(q[size] >= float(fixed_prices[i]), name=f"same_{i}")
    for parent, child, delta in _cross_menu_fcp_splits(assortments, active):
        if delta >= 1:
            model.addConstr(q[delta] >= float(fixed_prices[parent]) - float(fixed_prices[child]), name=f"split_{parent}_{child}")
    for k in range(v_in.shape[0]):
        for size in range(1, n_products + 1):
            model.addConstr(q[size] >= float(v_ks[k, size]) - selected_surplus[k], name=f"c2_{k}_{size}")
    model.setObjective(gp.quicksum(q[size] for size in range(1, n_products + 1)), GRB.MINIMIZE)
    model.optimize()
    min_q = {size: float(q[size].X) for size in range(n_products + 1)}

    actual_q = normalize_numeric_keys(anchored.get("size_prices") or {})
    table_rows = []
    previous_source = None
    for row in raw_bound_rows:
        size = row["size"]
        source = row["raw_family"]
        witness = row["raw_witness"]
        if size > 1 and min_q[size] <= min_q[size - 1] + 1e-6 and min_q[size - 1] > row["raw_bound"] + 1e-6:
            source = "c8_monotonicity"
            witness = f"q_{size} >= q_{size - 1}; inherited from {previous_source or 'previous tier'}"
        previous_source = source
        table_rows.append([
            size,
            actual_q.get(size, 0.0),
            min_q[size],
            source,
            witness,
        ])

    return {"actual_q": actual_q, "min_q": min_q, "rows": table_rows}


def min_q_oos_effect(case: dict, min_q: dict[int, float]) -> dict:
    fcp_choices = case["choices"]["oos"]["FCP"]
    actual_choices = case["choices"]["oos"]["Anchored FCP+BSP"]
    min_bsp_choices = evaluate_bsp_choices(case["v_out"], case["c_n"], min_q)
    min_hybrid_choices = evaluate_fcp_bsp_hybrid(fcp_choices, min_bsp_choices)
    fcp_outside_idx = [i for i, choice in enumerate(fcp_choices) if choice["channel"] == "outside"]
    captured_idx = [i for i in fcp_outside_idx if min_bsp_choices[i]["channel"] == "bsp"]
    return {
        "actual_oos": average_profit(actual_choices),
        "min_q_oos": average_profit(min_hybrid_choices),
        "min_q_bsp_only_oos": average_profit(min_bsp_choices),
        "min_q_bsp_only_counts": dict(Counter(choice["channel"] for choice in min_bsp_choices)),
        "min_q_hybrid_counts": dict(Counter(choice["channel"] for choice in min_hybrid_choices)),
        "fcp_outside_count": len(fcp_outside_idx),
        "fcp_outside_captured_by_min_q_bsp": len(captured_idx),
        "captured_profit": float(np.mean([min_bsp_choices[i]["profit"] for i in captured_idx])) if captured_idx else 0.0,
    }


def fcp_outside_cpbsd_by_size_rows(case: dict, min_q: dict[int, float]) -> list[list[object]]:
    fcp_choices = case["choices"]["oos"]["FCP"]
    cpbsd_choices = case["choices"]["oos"]["CPBSD-A"]
    grouped: dict[int, list[dict]] = defaultdict(list)
    for fcp, cpbsd in zip(fcp_choices, cpbsd_choices):
        if fcp["channel"] == "outside" and cpbsd["channel"] == "cpbsd_a":
            grouped[int(cpbsd["size"])].append(cpbsd)
    rows = []
    for size, choices in sorted(grouped.items()):
        prices = np.asarray([choice["price"] for choice in choices], dtype=float)
        values = np.asarray([choice["price"] + choice["surplus"] for choice in choices], dtype=float)
        profits = np.asarray([choice["profit"] for choice in choices], dtype=float)
        rows.append([
            size,
            len(choices),
            float(prices.mean()),
            float(values.mean()),
            float(profits.mean()),
            min_q.get(size, 0.0),
            float(values.mean() - min_q.get(size, 0.0)),
        ])
    return rows


def hvhm_cost_bias_rows(case: dict) -> tuple[list[list[object]], list[list[object]]]:
    c_n = case["c_n"]
    cpbsd_res = case["cpbsd_res"]
    raw_margin = np.asarray(cpbsd_res["p"], dtype=float) - c_n
    fcp_buyer_profit = [
        choice["profit"] for choice in case["choices"]["oos"]["FCP"]
        if choice["channel"] == "fcp"
    ]
    cpbsd_buyer_profit = [
        choice["profit"] for choice in case["choices"]["oos"]["CPBSD-A"]
        if choice["channel"] == "cpbsd_a"
    ]
    cost_rows = [
        [idx, c_n[idx], valuation_means(len(c_n), "full")[idx], raw_margin[idx]]
        for idx in range(len(c_n))
    ]
    quantile_rows = [
        ["FCP buyer profit", *np.quantile(fcp_buyer_profit, [0.10, 0.25, 0.50, 0.75, 0.90]).tolist()],
        ["CPBSD-A buyer profit", *np.quantile(cpbsd_buyer_profit, [0.10, 0.25, 0.50, 0.75, 0.90]).tolist()],
    ]
    return cost_rows, quantile_rows


def zero_random_contrast_rows() -> list[list[object]]:
    rows = []
    zero_case = load_case(10, 20260413, setting="normal_rho0.0_full_zero")
    rows.append([
        "N=10 zero seed 20260413",
        average_profit(zero_case["choices"]["oos"]["FCP"]),
        average_profit(zero_case["choices"]["oos"]["CPBSD-A"]),
        "same-seed OOS",
    ])
    for exp_name, label in [
        ("fcp_random_cost_eval_n10_random_ind", "N=10 random_ind 5-seed mean"),
        ("fcp_random_cost_eval_n10_random_corr", "N=10 random_corr 5-seed mean"),
    ]:
        summary = load_json(DOMAIN_ROOT / "experiments" / exp_name / "comparison_summary.json")
        fcp_vals = [float(row["revenue_out_sample"]) for row in summary if row["method"] == "FCP-pruned-MB"]
        cpbsd_vals = [float(row["revenue_out_sample"]) for row in summary if row["method"] == "CPBSD-A"]
        rows.append([label, float(np.mean(fcp_vals)), float(np.mean(cpbsd_vals)), "existing aggregate JSON"])
    return rows


def load_case(n_products: int, seed: int, setting: str = SETTING) -> dict:
    run_dir = run_dir_for(n_products, seed, setting=setting)
    instance_path = next((run_dir / "instances").glob("*.msgpack"))
    obj, v_in, c_n = load_instance(instance_path)
    v_out = oos_samples(obj["setup"], K_OUT)
    stem = instance_path.stem
    result_dir = run_dir / "results"
    fcp_res = load_json(result_dir / f"{stem}__fcp_pruned_mb.json")
    bsp_res = load_json(result_dir / f"{stem}__bsp.json")
    cpbsd_res = load_json(result_dir / f"{stem}__cpbsd_a.json")
    comparison_rows = load_json(run_dir / "comparison_summary.json")
    comparison_by_method = {row["method"]: row for row in comparison_rows}
    anchored_path = ANCHORED_ROOT / f"n{n_products}_seed_{seed}.json"
    anchored_payload = load_json(anchored_path) if setting == SETTING and anchored_path.exists() else None

    assortments = np.asarray(fcp_res["assortments"], dtype=int)
    fcp_prices = fcp_res.get("bundle_prices_full") or fcp_res.get("bundle_prices") or {}
    anchored_size_prices = {}
    if anchored_payload and anchored_payload.get("anchored_result", {}).get("feasible"):
        anchored_size_prices = anchored_payload["anchored_result"].get("size_prices") or {}

    datasets = {"in": v_in, "oos": v_out}
    choices = {}
    for split, v in datasets.items():
        fcp = evaluate_fcp_choices(v, c_n, fcp_prices, assortments)
        bsp = evaluate_bsp_choices(v, c_n, bsp_res.get("size_prices") or {})
        anchored_bsp = evaluate_bsp_choices(v, c_n, anchored_size_prices) if anchored_size_prices else []
        cpbsd = evaluate_cpbsd_a_choices(v, c_n, cpbsd_res["p"], cpbsd_res["d"])
        fcp_cpbsd = evaluate_fcp_cpbsd_a_hybrid(fcp, cpbsd)
        fcp_anchored_bsp = evaluate_fcp_cpbsd_a_hybrid(fcp, anchored_bsp) if anchored_bsp else []
        choices[split] = {
            "FCP": fcp,
            "BSP": bsp,
            "Anchored FCP+BSP": fcp_anchored_bsp,
            "CPBSD-A": cpbsd,
            "FCP+CPBSD-A": fcp_cpbsd,
        }
    choices["in"]["FCP"] = fcp_solver_choices(v_in, c_n, fcp_res)
    if anchored_payload and anchored_payload.get("anchored_result", {}).get("feasible"):
        choices["in"]["Anchored FCP+BSP"] = anchored_solver_choices(v_in, c_n, anchored_payload["anchored_result"])

    return {
        "N": n_products,
        "seed": seed,
        "setting": setting,
        "instance_path": instance_path,
        "instance_id": stem,
        "setup": obj["setup"],
        "v_in": v_in,
        "v_out": v_out,
        "c_n": c_n,
        "fcp_res": fcp_res,
        "bsp_res": bsp_res,
        "cpbsd_res": cpbsd_res,
        "comparison_by_method": comparison_by_method,
        "anchored_payload": anchored_payload,
        "choices": choices,
    }


def select_cases() -> list[tuple[int, int]]:
    return [(10, 20260413)]


def append_case(lines: list[str], case: dict) -> None:
    n_products = case["N"]
    seed = case["seed"]
    choices = case["choices"]
    fcp_res = case["fcp_res"]
    bsp_res = case["bsp_res"]
    cpbsd_res = case["cpbsd_res"]
    anchored_payload = case["anchored_payload"]
    c_n = case["c_n"]
    fcp_summary = case["comparison_by_method"].get("FCP-pruned-MB", {})
    q_diag = q_lower_bound_diagnostics(case) if anchored_payload else None
    min_q_effect = min_q_oos_effect(case, q_diag["min_q"]) if q_diag else None

    lines.extend([
        "",
        f"## Case: N={n_products}, seed={seed}",
        "",
        f"- instance: `{case['instance_id']}`",
        f"- instance path: `{case['instance_path']}`",
        f"- cost vector summary: min `{c_n.min():.4f}`, median `{np.median(c_n):.4f}`, max `{c_n.max():.4f}`",
        f"- FCP status `{fcp_res.get('solver_status')}`, objective `{float(fcp_res.get('objective', 0.0)):.6f}`, runtime `{float(fcp_res.get('runtime', 0.0)):.2f}s`, candidate bundles `{len(fcp_res.get('assortments', []))}`",
        f"- FCP runtime note: this is the restricted-MB pricing MILP runtime, not GCN inference time. This seed hit the 300s limit (`status=9`); GCN inference was `{float(fcp_summary.get('gcn_inference_time', 0.0)):.4f}s` and candidate generation was `{float(fcp_summary.get('candidate_generation_time', 0.0)):.6f}s`.",
        f"- BSP objective `{float(bsp_res.get('objective', 0.0)):.6f}`, runtime `{float(bsp_res.get('runtime', 0.0)):.2f}s`",
        f"- CPBSD-A status `{cpbsd_res.get('solver_status')}`, objective `{float(cpbsd_res.get('objective', 0.0)):.6f}`, runtime `{float(cpbsd_res.get('runtime', 0.0)):.2f}s`",
    ])
    if anchored_payload:
        anchored = anchored_payload["anchored_result"]
        lines.append(
            f"- Anchored FCP+BSP objective `{float(anchored.get('objective', 0.0)):.6f}`, "
            f"strict protected BSP choices `{anchored.get('protected_bsp_choice_count')}`, "
            f"OOS `{float(anchored_payload['oos']['anchored']):.6f}`"
        )

    rows = []
    for method in ["FCP", "BSP", "Anchored FCP+BSP", "CPBSD-A", "FCP+CPBSD-A"]:
        in_choices = choices["in"].get(method) or []
        oos_choices = choices["oos"].get(method) or []
        if not in_choices or not oos_choices:
            continue
        sin = choice_summary(in_choices)
        soos = choice_summary(oos_choices)
        rows.append([
            method,
            sin["avg_profit_all"],
            sin["buyers"],
            sin["outside"],
            soos["avg_profit_all"],
            soos["buyers"],
            soos["outside"],
            soos["avg_profit_buyers"],
        ])
    lines.extend(["", "### Revenue And Coverage", ""])
    lines.extend(md_table(
        ["method", "in avg profit", "in buyers", "in outside", "OOS avg profit", "OOS buyers", "OOS outside", "OOS profit/buyer"],
        rows,
        digits=4,
    ))

    cpbsd_oos = average_profit(choices["oos"]["CPBSD-A"])
    hybrid_oos = average_profit(choices["oos"]["FCP+CPBSD-A"])
    fcp_oos = average_profit(choices["oos"]["FCP"])
    lines.extend([
        "",
        "### Main Failure Signal",
        "",
        f"- OOS `FCP+CPBSD-A - CPBSD-A = {hybrid_oos - cpbsd_oos:+.6f}`.",
        f"- OOS `FCP - CPBSD-A = {fcp_oos - cpbsd_oos:+.6f}`.",
        "- The hybrid exposes both menus to the customer, so the customer chooses by surplus, not by firm profit.",
        "- When an FCP option gives slightly higher surplus but lower profit than CPBSD-A, it cannibalizes CPBSD-A revenue.",
        "",
    ])
    lines.extend(md_table(
        ["OOS migration from pure CPBSD-A to FCP+CPBSD-A", "count"],
        migration_counts(choices["oos"]["CPBSD-A"], choices["oos"]["FCP+CPBSD-A"]).items(),
        digits=4,
    ))
    lines.extend(["", "OOS cannibalization / coverage decomposition:", ""])
    lines.extend(md_table(
        ["group", "count", "FCP profit", "CPBSD-A profit", "hybrid profit", "hybrid-CPBSD profit", "FCP-CPBSD surplus"],
        fcp_cannibalization_rows(choices["oos"]["FCP"], choices["oos"]["CPBSD-A"], choices["oos"]["FCP+CPBSD-A"]),
        digits=4,
    ))
    if q_diag:
        lines.extend([
            "",
            "FCP outside but CPBSD-A buys, grouped by CPBSD-A selected size:",
            "",
        ])
        lines.extend(md_table(
            ["CPBSD-A size", "count", "avg CPBSD-A price", "avg value", "avg CPBSD-A profit", "min feasible q_s", "avg value - min q_s"],
            fcp_outside_cpbsd_by_size_rows(case, q_diag["min_q"]),
            digits=4,
        ))

    lines.extend(["", "### FCP Stage-1 Solution", ""])
    fcp_prices_full = normalize_numeric_keys(fcp_res.get("bundle_prices_full") or {})
    fcp_prices_selected = normalize_numeric_keys(fcp_res.get("bundle_prices") or {})
    margins = []
    assortments = np.asarray(fcp_res["assortments"], dtype=int)
    costs = assortments @ c_n
    for idx, price in fcp_prices_full.items():
        margins.append(price - float(costs[idx]))
    lines.extend(md_table(
        ["metric", "value"],
        [
            ["candidate bundles", len(assortments)],
            ["priced selected bundles", len(fcp_prices_selected)],
            ["full price entries incl outside/full-only", len(fcp_prices_full)],
            ["FCP margin mean", np.mean(margins) if margins else 0.0],
            ["FCP margin p25", np.quantile(margins, 0.25) if margins else 0.0],
            ["FCP margin p50", np.quantile(margins, 0.50) if margins else 0.0],
            ["FCP margin p75", np.quantile(margins, 0.75) if margins else 0.0],
        ],
        digits=4,
    ))
    lines.extend(["", "Top in-sample FCP bundles by buyer count:", ""])
    lines.extend(md_table(
        ["bundle idx", "size", "price", "cost", "margin", "in buyers", "priced", "bitmask"],
        fcp_solution_rows(fcp_res, c_n, choices["in"]["FCP"]),
        digits=4,
    ))

    lines.extend(["", "FCP in-sample profit by channel:", ""])
    lines.extend(md_table(
        ["channel", "count", "share", "avg profit", "profit/K", "p25", "p50", "p75"],
        channel_profit_rows(choices["in"]["FCP"]),
        digits=4,
    ))
    lines.extend(["", "FCP OOS profit by channel:", ""])
    lines.extend(md_table(
        ["channel", "count", "share", "avg profit", "profit/K", "p25", "p50", "p75"],
        channel_profit_rows(choices["oos"]["FCP"]),
        digits=4,
    ))

    lines.extend(["", "### Stage-2 BSP / Anchored BSP Solution", ""])
    lines.extend(["Pure BSP size prices:", ""])
    lines.extend(md_table(["size", "q_s"], price_by_size_rows(bsp_res.get("size_prices") or {}), digits=4))
    if anchored_payload:
        anchored = anchored_payload["anchored_result"]
        lines.extend(["", "Anchored FCP+BSP strict size prices:", ""])
        lines.extend(md_table(["size", "q_s"], price_by_size_rows(anchored.get("size_prices") or {}), digits=4))
        if q_diag and min_q_effect:
            lines.extend([
                "",
                "Anchored price lower-bound diagnosis:",
                "",
                "`actual q_s` is the solver-returned second-stage size price. `min feasible q_s` is a diagnostic LP that fixes the same in-sample assignment and minimizes `sum_s q_s` subject to the same BSP monotonicity/subadditivity, FCP anchor, cross-split, and in-sample utility lower-bound constraints.",
                "",
            ])
            lines.extend(md_table(
                ["s", "actual q_s", "min feasible q_s", "dominant hard source", "exact witness"],
                q_diag["rows"],
                digits=4,
            ))
            lines.extend([
                "",
                "Interpretation:",
                "",
                "- `c10_same_size` and `c11_cross_split` are the main hard lower-bound sources. They project fixed FCP anchor prices into a size-only BSP menu.",
                "- `q_9` and `q_10` are much higher in the returned solution than in the min-q diagnostic. That part is a non-unique price artifact: no in-sample customer chooses BSP, so the objective is almost indifferent to unused high-tier `q_s` once feasibility is satisfied.",
                f"- Even after the min-q tie-break, OOS only changes from `{min_q_effect['actual_oos']:.4f}` to `{min_q_effect['min_q_oos']:.4f}`.",
                f"- Under min-q, BSP captures only `{min_q_effect['fcp_outside_captured_by_min_q_bsp']}` of `{min_q_effect['fcp_outside_count']}` FCP-outside OOS customers.",
                "",
                "Min-q OOS diagnostic:",
                "",
            ])
            lines.extend(md_table(
                ["metric", "value"],
                [
                    ["actual Anchored OOS", min_q_effect["actual_oos"]],
                    ["min-q Anchored OOS", min_q_effect["min_q_oos"]],
                    ["min-q BSP-only OOS", min_q_effect["min_q_bsp_only_oos"]],
                    ["min-q BSP-only choice counts", str(min_q_effect["min_q_bsp_only_counts"])],
                    ["min-q hybrid choice counts", str(min_q_effect["min_q_hybrid_counts"])],
                    ["FCP-outside captured by min-q BSP", min_q_effect["fcp_outside_captured_by_min_q_bsp"]],
                ],
                digits=4,
            ))
        lines.extend([
            "",
            f"Anchored in-sample choice summary: `{anchored.get('choice_summary')}`.",
            f"Anchored protected customers: `{anchored.get('protected_customer_count')}`, strict constraints: `{anchored.get('strict_protection_constraint_count')}`, protected BSP choices: `{anchored.get('protected_bsp_choice_count')}`.",
        ])
        lines.extend(["", "Anchored FCP+BSP OOS profit by channel:", ""])
        lines.extend(md_table(
            ["channel", "count", "share", "avg profit", "profit/K", "p25", "p50", "p75"],
            channel_profit_rows(choices["oos"]["Anchored FCP+BSP"]),
            digits=4,
        ))

    lines.extend(["", "### CPBSD-A Solution", ""])
    p_vec = [float(x) for x in cpbsd_res["p"]]
    d_vec = [float(x) for x in cpbsd_res["d"]]
    lines.extend(solution_vector_block("component prices p_n", p_vec))
    lines.extend(solution_vector_block("size discounts d_s", d_vec))
    lines.extend(["", "CPBSD-A in-sample buyer sizes:", ""])
    lines.extend(md_table(["size", "buyers"], size_count_rows(choices["in"]["CPBSD-A"]), digits=4))
    lines.extend(["", "CPBSD-A OOS buyer sizes:", ""])
    lines.extend(md_table(["size", "buyers"], size_count_rows(choices["oos"]["CPBSD-A"]), digits=4))
    lines.extend(["", "CPBSD-A OOS profit by channel:", ""])
    lines.extend(md_table(
        ["channel", "count", "share", "avg profit", "profit/K", "p25", "p50", "p75"],
        channel_profit_rows(choices["oos"]["CPBSD-A"]),
        digits=4,
    ))

    cost_rows, quantile_rows = hvhm_cost_bias_rows(case)
    lines.extend([
        "",
        "### hvhm Cost-Structure Diagnosis",
        "",
        "In this setup, product cost is strongly aligned with valuation means. CPBSD-A learns an almost constant raw component margin `p_n - c_n`, which is a good inductive bias for OOS customers because it can adapt item-by-item while keeping margins stable.",
        "",
    ])
    lines.extend(md_table(
        ["product", "cost c_n", "valuation mean", "CPBSD-A raw margin p_n-c_n"],
        cost_rows,
        digits=4,
    ))
    lines.extend(["", "OOS buyer profit quantiles:", ""])
    lines.extend(md_table(
        ["method", "p10", "p25", "p50", "p75", "p90"],
        quantile_rows,
        digits=4,
    ))

    lines.extend(["", "### FCP+CPBSD-A Hybrid Distribution", ""])
    lines.extend(["In-sample hybrid profit by channel:", ""])
    lines.extend(md_table(
        ["channel", "count", "share", "avg profit", "profit/K", "p25", "p50", "p75"],
        channel_profit_rows(choices["in"]["FCP+CPBSD-A"]),
        digits=4,
    ))
    lines.extend(["", "OOS hybrid profit by channel:", ""])
    lines.extend(md_table(
        ["channel", "count", "share", "avg profit", "profit/K", "p25", "p50", "p75"],
        channel_profit_rows(choices["oos"]["FCP+CPBSD-A"]),
        digits=4,
    ))
    lines.extend(["", "OOS hybrid buyer sizes:", ""])
    lines.extend(md_table(["size", "buyers"], size_count_rows(choices["oos"]["FCP+CPBSD-A"]), digits=4))


def main() -> None:
    warnings.filterwarnings("ignore", category=RuntimeWarning)
    selected = select_cases()
    cases = [load_case(n, seed) for n, seed in selected]

    lines = [
        "# N=10 hvhm FCP+CPBSD-A Deep Failure Analysis",
        "",
        "本文件只分析 `N=10 / normal_rho0.0_full_hvhm / seed=20260413`，使用已有 Phase2 与 Anchored 结果，不重跑 FCP/BSP/CPBSD-A baseline。",
        f"OOS sample 口径沿用现有脚本：`rng = seed + 99991`, `K_out={K_OUT}`。",
        "",
        "## Selected Case",
        "",
        "这个 case 是 N=10 hvhm 中 `FCP+CPBSD-A - CPBSD-A` OOS 损失最大的 seed，也方便和之前 Anchored smoke 结果对齐。",
        "",
    ]
    overview_rows = []
    for case in cases:
        cpbsd_oos = average_profit(case["choices"]["oos"]["CPBSD-A"])
        hybrid_oos = average_profit(case["choices"]["oos"]["FCP+CPBSD-A"])
        fcp_oos = average_profit(case["choices"]["oos"]["FCP"])
        anchored_oos = average_profit(case["choices"]["oos"]["Anchored FCP+BSP"])
        overview_rows.append([
            case["N"],
            case["seed"],
            fcp_oos,
            anchored_oos,
            cpbsd_oos,
            hybrid_oos,
            hybrid_oos - cpbsd_oos,
        ])
    lines.extend(md_table(
        ["N", "seed", "FCP OOS", "Anchored FCP+BSP OOS", "CPBSD-A OOS", "FCP+CPBSD-A OOS", "hybrid - CPBSD-A"],
        overview_rows,
        digits=6,
    ))
    lines.extend([
        "",
        "## Diagnosis Summary",
        "",
        "主结论分两层：",
        "",
        "1. **Anchored FCP+BSP 的 BSP 二阶段价格高**：核心不是 BSP 自身学到高价，而是 formulation 把 fixed FCP anchor prices 通过 `c10_same_size` 和 `c11_cross_split` 投影到 size-only `q_s` 上。`q_9/q_10` 还有 non-unique solver tie-break 漂移，但即使用 min-q 二级诊断压低，也几乎不改善 OOS。",
        "2. **FCP OOS 不如 CPBSD-A**：hvhm 的 cost 与 valuation mean 强相关，CPBSD-A 的 component prices 学成近似 `c_n + constant margin`，能对 OOS customers 做 item-level adaptation。FCP 在 in-sample 的 profit/buyer 接近，但 OOS 同时损失 coverage 和 profit/buyer。",
        "3. 直接 `FCP+CPBSD-A` 混合时，客户按 surplus 选项而不是按 firm profit 选项；FCP 会 cannibalize 一批 CPBSD-A 高利润客户，所以 hybrid 低于纯 CPBSD-A。",
        "",
    ])

    for case in cases:
        append_case(lines, case)

    lines.extend([
        "",
        "## Cross-Setup Contrast",
        "",
        "这不是 FCP formulation 在所有 setup 上都失败的证据。对照已有 N=10 结果，FCP 在 zero cost 与 random cost 上仍然接近或优于 CPBSD-A；hvhm 的特殊点是 cost-valuation 强相关，这正好适合 CPBSD-A 的 component-pricing bias。",
        "",
    ])
    lines.extend(md_table(
        ["setup", "FCP OOS", "CPBSD-A OOS", "source"],
        zero_random_contrast_rows(),
        digits=4,
    ))

    OUTPUT_PATH.write_text("\n".join(lines) + "\n")
    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()
