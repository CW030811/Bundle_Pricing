"""
Run strict Anchored FCP+BSP on existing hvhm phase2 seeds.

This runner reuses existing FCP, BSP, and CPBSD-A result JSONs. It only solves
Anchored FCP+BSP, then evaluates all methods on the same OOS sample rule used
by the existing phase2 scripts.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import msgpack
import msgpack_numpy as mnp
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from eval_bsp_fcp_hybrid_oos import eval_hybrid_oos
from generate_data_CPBSD import sample_valuations, valuation_means
from solve_anchored_fcp_bsp import (
    _bsp_prefix_values_and_costs,
    _cross_menu_fcp_splits,
    _normalize_assortments_and_prices,
    solve_anchored_fcp_bsp,
)
from solve_mb_bsp_on_cpbsd_v2 import json_default, normalize_numeric_keys


DOMAIN_ROOT = Path("/Users/sensen/.openclaw/workspace/domains/revenue-management")
EXP_ROOT = DOMAIN_ROOT / "experiments"
INPUT_ROOT = EXP_ROOT / "fcp_mb_phase2_selected_n10_n30_5inst"
OUTPUT_ROOT = EXP_ROOT / "anchored_fcp_bsp_hvhm_batch"
SEEDS = [20260413, 20260414, 20260415, 20260416, 20260417]
SETTING = "normal_rho0.0_full_hvhm"
EPS = 1e-9


def load_json(path: Path) -> dict:
    with path.open("r") as f:
        return json.load(f)


def load_instance(path: Path) -> Tuple[dict, np.ndarray, np.ndarray]:
    with path.open("rb") as f:
        obj = msgpack.load(f, object_hook=mnp.decode, strict_map_key=False)
    return obj, np.asarray(obj["valuation_samples_V"], dtype=float), np.asarray(obj["production_cost_c"], dtype=float)


def oos_samples(setup: dict, k_out: int = 5000) -> np.ndarray:
    rng = np.random.default_rng(int(setup["seed"]) + 99991)
    means = valuation_means(int(setup["n_products"]), setup["heterogeneity"])
    return sample_valuations(
        k=k_out,
        means=means,
        family=setup["dist_family"],
        rho=float(setup["rho"]),
        rng=rng,
    )


def run_dir_for(n_products: int, seed: int) -> Path:
    return INPUT_ROOT / f"n{n_products}" / SETTING / "runs" / f"seed_{seed}"


def method_paths(run_dir: Path, instance_name: str) -> Dict[str, Path]:
    result_dir = run_dir / "results"
    return {
        "fcp": result_dir / f"{instance_name}__fcp_pruned_mb.json",
        "bsp": result_dir / f"{instance_name}__bsp.json",
        "cpbsd_a": result_dir / f"{instance_name}__cpbsd_a.json",
    }


def evaluate_fcp_choices(
    v_eval: np.ndarray,
    c_n: np.ndarray,
    bundle_prices: dict,
    assortments: np.ndarray,
) -> List[dict]:
    prices = normalize_numeric_keys(bundle_prices or {})
    assortments = np.asarray(assortments, dtype=int)
    bundle_cost = assortments @ c_n
    choices = []
    for k in range(v_eval.shape[0]):
        best_surplus = 0.0
        best_profit = 0.0
        best_idx = None
        for bi in range(assortments.shape[0]):
            price = prices.get(bi)
            if price is None:
                continue
            surplus = float(v_eval[k] @ assortments[bi]) - float(price)
            if abs(surplus) <= EPS:
                surplus = 0.0
            profit = float(price) - float(bundle_cost[bi])
            if surplus > best_surplus + EPS:
                best_surplus = surplus
                best_profit = profit
                best_idx = bi
            elif abs(surplus - best_surplus) <= EPS and profit > best_profit + EPS:
                best_profit = profit
                best_idx = bi
        if best_idx is None or best_surplus <= 0.0:
            choices.append({"channel": "outside", "profit": 0.0, "surplus": 0.0, "bundle_idx": None, "size": 0})
        else:
            choices.append({
                "channel": "fcp",
                "profit": float(best_profit),
                "surplus": float(best_surplus),
                "bundle_idx": int(best_idx),
                "size": int(assortments[best_idx].sum()),
            })
    return choices


def evaluate_bsp_choices(v_eval: np.ndarray, c_n: np.ndarray, size_prices: dict) -> List[dict]:
    prices = normalize_numeric_keys(size_prices or {})
    choices = []
    n_products = int(v_eval.shape[1])
    for k in range(v_eval.shape[0]):
        order = np.argsort(-v_eval[k])
        prefix_val = 0.0
        prefix_cost = 0.0
        best_surplus = 0.0
        best_profit = 0.0
        best_size = 0
        for size in range(1, n_products + 1):
            idx = order[size - 1]
            prefix_val += float(v_eval[k, idx])
            prefix_cost += float(c_n[idx])
            price = prices.get(size)
            if price is None:
                continue
            surplus = prefix_val - float(price)
            if surplus > best_surplus:
                best_surplus = surplus
                best_profit = float(price) - prefix_cost
                best_size = size
        if best_size == 0 or best_surplus <= 0.0:
            choices.append({"channel": "outside", "profit": 0.0, "surplus": 0.0, "size": 0})
        else:
            choices.append({
                "channel": "bsp",
                "profit": float(best_profit),
                "surplus": float(best_surplus),
                "size": int(best_size),
            })
    return choices


def evaluate_hybrid_choices(
    v_eval: np.ndarray,
    c_n: np.ndarray,
    bundle_prices: dict,
    assortments: np.ndarray,
    size_prices: dict,
) -> List[dict]:
    fcp_choices = evaluate_fcp_choices(v_eval, c_n, bundle_prices, assortments)
    bsp_choices = evaluate_bsp_choices(v_eval, c_n, size_prices)
    choices = []
    for fcp, bsp in zip(fcp_choices, bsp_choices):
        if fcp["surplus"] <= 0 and bsp["surplus"] <= 0:
            choices.append({"channel": "outside", "profit": 0.0, "surplus": 0.0, "size": 0})
        elif fcp["surplus"] > bsp["surplus"] + EPS:
            choices.append({**fcp, "channel": "fcp"})
        elif bsp["surplus"] > fcp["surplus"] + EPS:
            choices.append({**bsp, "channel": "bsp"})
        elif fcp["profit"] >= bsp["profit"]:
            choices.append({**fcp, "channel": "fcp"})
        else:
            choices.append({**bsp, "channel": "bsp"})
    return choices


def evaluate_cpbsd_a_choices(v_eval: np.ndarray, c_n: np.ndarray, p: Iterable[float], d: Iterable[float]) -> List[dict]:
    p_vec = np.asarray(list(p), dtype=float)
    d_vec = np.asarray(list(d), dtype=float)
    choices = []
    n_products = int(v_eval.shape[1])
    for k in range(v_eval.shape[0]):
        best_surplus = 0.0
        best_profit = 0.0
        best_size = 0
        best_idx = None
        best_price = 0.0
        for size in range(1, n_products + 1):
            util = v_eval[k] - p_vec + d_vec[size]
            idx = np.argpartition(util, -size)[-size:]
            surplus = float(util[idx].sum())
            if surplus > best_surplus:
                price = float(p_vec[idx].sum() - size * d_vec[size])
                best_surplus = surplus
                best_profit = float((p_vec[idx] - c_n[idx]).sum() - size * d_vec[size])
                best_size = size
                best_idx = idx
                best_price = price
        if best_idx is None or best_surplus <= 0.0:
            choices.append({"channel": "outside", "profit": 0.0, "surplus": 0.0, "size": 0, "price": 0.0})
        else:
            choices.append({
                "channel": "cpbsd_a",
                "profit": float(best_profit),
                "surplus": float(best_surplus),
                "size": int(best_size),
                "price": float(best_price),
                "items": [int(i) for i in sorted(best_idx.tolist())],
            })
    return choices


def average_profit(choices: List[dict]) -> float:
    return float(np.mean([float(c["profit"]) for c in choices])) if choices else 0.0


def channel_counts(choices: List[dict]) -> Dict[str, int]:
    return dict(Counter(str(c["channel"]) for c in choices))


def migration_counts(base: List[dict], hybrid: List[dict]) -> Dict[str, int]:
    counts = Counter((str(a["channel"]), str(b["channel"])) for a, b in zip(base, hybrid))
    return {f"{src}->{dst}": int(count) for (src, dst), count in sorted(counts.items())}


def lower_bound_diagnostics(
    v_kn: np.ndarray,
    c_n: np.ndarray,
    assortments: np.ndarray,
    fcp_bundle_prices: dict,
    fcp_chosen_bundle_idx_by_customer: list,
    size_prices: dict,
) -> List[dict]:
    n_products = int(v_kn.shape[1])
    assortments_norm, fixed_prices, old_to_new = _normalize_assortments_and_prices(
        assortments=np.asarray(assortments, dtype=int),
        fcp_bundle_prices=fcp_bundle_prices,
        n_products=n_products,
    )
    bundle_sizes = assortments_norm.sum(axis=1).astype(int)
    fcp_active = sorted(
        idx for idx, price in fixed_prices.items()
        if idx != 0 and int(bundle_sizes[idx]) > 0 and price is not None
    )
    same_size_lb = defaultdict(lambda: None)
    for idx in fcp_active:
        size = int(bundle_sizes[idx])
        price = float(fixed_prices[idx])
        same_size_lb[size] = price if same_size_lb[size] is None else max(float(same_size_lb[size]), price)

    split_lb = defaultdict(lambda: None)
    for parent, child, diff in _cross_menu_fcp_splits(assortments_norm, fcp_active):
        bound = float(fixed_prices[parent]) - float(fixed_prices[child])
        split_lb[diff] = bound if split_lb[diff] is None else max(float(split_lb[diff]), bound)

    v_ki = v_kn @ assortments_norm.T
    v_ks, _ = _bsp_prefix_values_and_costs(v_kn, c_n)
    protection_lb = defaultdict(lambda: None)
    for k, old_idx in enumerate(fcp_chosen_bundle_idx_by_customer or []):
        try:
            mapped_idx = old_to_new.get(int(old_idx))
        except (TypeError, ValueError):
            continue
        if mapped_idx not in fcp_active:
            continue
        fcp_surplus = float(v_ki[k, mapped_idx]) - float(fixed_prices[mapped_idx])
        for size in range(1, n_products + 1):
            bound = float(v_ks[k, size]) - fcp_surplus
            protection_lb[size] = bound if protection_lb[size] is None else max(float(protection_lb[size]), bound)

    prices = normalize_numeric_keys(size_prices or {})
    rows = []
    for size in range(1, n_products + 1):
        sources = {
            "same_size": same_size_lb[size],
            "subset_split": split_lb[size],
            "protection": protection_lb[size],
        }
        active_sources = {k: float(v) for k, v in sources.items() if v is not None}
        if active_sources:
            source = max(active_sources.items(), key=lambda kv: kv[1])[0]
            lower_bound = active_sources[source]
        else:
            source = None
            lower_bound = None
        q_val = prices.get(size)
        rows.append({
            "size": int(size),
            "q": None if q_val is None else float(q_val),
            "dominant_lower_bound_source": source,
            "dominant_lower_bound": lower_bound,
            "same_size_lb": None if same_size_lb[size] is None else float(same_size_lb[size]),
            "subset_split_lb": None if split_lb[size] is None else float(split_lb[size]),
            "protection_lb": None if protection_lb[size] is None else float(protection_lb[size]),
        })
    return rows


def cpbsd_vs_anchored_size_price_summary(cpbsd_choices: List[dict], anchored_size_prices: dict) -> List[dict]:
    prices = normalize_numeric_keys(anchored_size_prices or {})
    by_size = defaultdict(list)
    for choice in cpbsd_choices:
        if choice["channel"] != "cpbsd_a" or int(choice["size"]) <= 0:
            continue
        size = int(choice["size"])
        q_val = prices.get(size)
        if q_val is None:
            continue
        by_size[size].append((float(choice["price"]), float(q_val), float(choice["price"]) - float(q_val)))
    rows = []
    for size, vals in sorted(by_size.items()):
        arr = np.asarray(vals, dtype=float)
        rows.append({
            "size": int(size),
            "count": int(arr.shape[0]),
            "avg_cpbsd_a_price": float(arr[:, 0].mean()),
            "anchored_q_size": float(arr[:, 1].mean()),
            "avg_cpbsd_minus_anchored_q": float(arr[:, 2].mean()),
        })
    return rows


def fcp_outside_cpbsd_buy_summary(
    fcp_choices: List[dict],
    anchored_choices: List[dict],
    anchored_bsp_only_choices: List[dict],
    cpbsd_choices: List[dict],
) -> dict:
    idxs = [
        i for i, (fcp, cpbsd) in enumerate(zip(fcp_choices, cpbsd_choices))
        if fcp["channel"] == "outside" and cpbsd["channel"] == "cpbsd_a"
    ]
    if not idxs:
        return {
            "count": 0,
            "anchored_captures": 0,
            "anchored_outside": 0,
            "avg_cpbsd_a_profit": 0.0,
            "avg_anchored_profit": 0.0,
            "avg_anchored_best_bsp_surplus": 0.0,
        }
    return {
        "count": int(len(idxs)),
        "anchored_captures": int(sum(1 for i in idxs if anchored_choices[i]["channel"] != "outside")),
        "anchored_outside": int(sum(1 for i in idxs if anchored_choices[i]["channel"] == "outside")),
        "avg_cpbsd_a_profit": float(np.mean([cpbsd_choices[i]["profit"] for i in idxs])),
        "avg_anchored_profit": float(np.mean([anchored_choices[i]["profit"] for i in idxs])),
        "avg_anchored_best_bsp_surplus": float(np.mean([anchored_bsp_only_choices[i]["surplus"] for i in idxs])),
    }


def write_csv(path: Path, rows: List[dict], fieldnames: List[str]) -> None:
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fieldnames})


def make_markdown_report(summary_rows: List[dict], aggregate_rows: List[dict], diagnostics: Dict[str, dict]) -> str:
    lines = ["# Anchored FCP+BSP hvhm Batch Report", ""]
    lines.append("## Aggregate OOS")
    lines.append("")
    lines.append("| N | FCP | BSP | CPBSD-A | Anchored | Anchored-FCP | Anchored-BSP | Anchored-CPBSD-A |")
    lines.append("| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for row in aggregate_rows:
        lines.append(
            f"| {row['N']} | {row['fcp_oos_mean']:.6f} | {row['bsp_oos_mean']:.6f} | "
            f"{row['cpbsd_a_oos_mean']:.6f} | {row['anchored_oos_mean']:.6f} | "
            f"{row['delta_anchored_fcp_mean']:+.6f} | {row['delta_anchored_bsp_mean']:+.6f} | "
            f"{row['delta_anchored_cpbsd_a_mean']:+.6f} |"
        )
    lines.append("")
    lines.append("## Per-Seed OOS")
    lines.append("")
    lines.append("| N | Seed | FCP | BSP | CPBSD-A | Anchored | A-FCP | A-BSP | A-CPBSD-A | Anchored choice |")
    lines.append("| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |")
    for row in summary_rows:
        choice = f"fcp={row['anchored_oos_fcp']} bsp={row['anchored_oos_bsp']} out={row['anchored_oos_outside']}"
        lines.append(
            f"| {row['N']} | {row['seed']} | {row['fcp_oos']:.6f} | {row['bsp_oos']:.6f} | "
            f"{row['cpbsd_a_oos']:.6f} | {row['anchored_oos']:.6f} | "
            f"{row['delta_anchored_fcp']:+.6f} | {row['delta_anchored_bsp']:+.6f} | "
            f"{row['delta_anchored_cpbsd_a']:+.6f} | {choice} |"
        )
    lines.append("")
    lines.append("## Diagnostic Seeds")
    if not diagnostics:
        lines.append("")
        lines.append("Anchored OOS improved enough under the direct criterion, so no failure diagnostics were selected.")
    else:
        lines.append("")
        for key, diag in diagnostics.items():
            lines.append(f"### {key}")
            lines.append("")
            lines.append(f"- FCP outside but CPBSD-A buys: `{diag['fcp_outside_cpbsd_buy']['count']}`")
            lines.append(f"- Anchored captures among those customers: `{diag['fcp_outside_cpbsd_buy']['anchored_captures']}`")
            lines.append(f"- Anchored outside among those customers: `{diag['fcp_outside_cpbsd_buy']['anchored_outside']}`")
            lines.append(f"- Avg CPBSD-A profit on those customers: `{diag['fcp_outside_cpbsd_buy']['avg_cpbsd_a_profit']:.6f}`")
            lines.append(f"- Avg Anchored best-BSP surplus on those customers: `{diag['fcp_outside_cpbsd_buy']['avg_anchored_best_bsp_surplus']:.6f}`")
            lines.append("")
    return "\n".join(lines) + "\n"


def aggregate_by_n(summary_rows: List[dict]) -> List[dict]:
    rows = []
    by_n = defaultdict(list)
    for row in summary_rows:
        by_n[int(row["N"])].append(row)
    for n_products, group in sorted(by_n.items()):
        rows.append({
            "N": int(n_products),
            "seed_count": int(len(group)),
            "fcp_oos_mean": float(np.mean([r["fcp_oos"] for r in group])),
            "bsp_oos_mean": float(np.mean([r["bsp_oos"] for r in group])),
            "cpbsd_a_oos_mean": float(np.mean([r["cpbsd_a_oos"] for r in group])),
            "anchored_oos_mean": float(np.mean([r["anchored_oos"] for r in group])),
            "delta_anchored_fcp_mean": float(np.mean([r["delta_anchored_fcp"] for r in group])),
            "delta_anchored_bsp_mean": float(np.mean([r["delta_anchored_bsp"] for r in group])),
            "delta_anchored_cpbsd_a_mean": float(np.mean([r["delta_anchored_cpbsd_a"] for r in group])),
            "anchored_beats_fcp_count": int(sum(1 for r in group if r["anchored_oos"] > r["fcp_oos"] + EPS)),
        })
    return rows


def select_diagnostic_rows(summary_rows: List[dict], aggregate_rows: List[dict]) -> List[dict]:
    selected = []
    by_n = defaultdict(list)
    agg_by_n = {int(row["N"]): row for row in aggregate_rows}
    for row in summary_rows:
        by_n[int(row["N"])].append(row)
    for n_products, group in sorted(by_n.items()):
        agg = agg_by_n[n_products]
        improved_mean = agg["anchored_oos_mean"] > agg["fcp_oos_mean"] + 0.05
        majority_beats_fcp = agg["anchored_beats_fcp_count"] >= (len(group) // 2 + 1)
        if improved_mean and majority_beats_fcp:
            continue
        ranked = sorted(
            group,
            key=lambda r: (r["cpbsd_a_oos"] - r["anchored_oos"], -r["anchored_oos"]),
            reverse=True,
        )
        selected.extend(ranked[:2])
    return selected


def run_one(n_products: int, seed: int, args: argparse.Namespace) -> dict:
    run_dir = run_dir_for(n_products, seed)
    instance_paths = sorted((run_dir / "instances").glob("*.msgpack"))
    if len(instance_paths) != 1:
        raise FileNotFoundError(f"Expected one instance under {run_dir / 'instances'}, found {len(instance_paths)}")
    instance_path = instance_paths[0]
    obj, v_kn, c_n = load_instance(instance_path)
    setup = obj["setup"]
    v_out = oos_samples(setup, k_out=args.k_out)
    paths = method_paths(run_dir, instance_path.stem)
    fcp_res = load_json(paths["fcp"])
    bsp_res = load_json(paths["bsp"])
    cpbsd_res = load_json(paths["cpbsd_a"])

    t0 = time.time()
    anchored = solve_anchored_fcp_bsp(
        v_kn=v_kn,
        c_n=c_n,
        assortments=np.asarray(fcp_res["assortments"], dtype=int),
        fcp_bundle_prices=fcp_res.get("bundle_prices_full") or fcp_res.get("bundle_prices") or {},
        fcp_chosen_bundle_idx_by_customer=fcp_res.get("chosen_bundle_idx_by_customer"),
        time_limit=args.time_limit,
        mip_gap=args.mip_gap,
        output_flag=args.output_flag,
        threads=args.threads,
        protect_fcp_sales=True,
        strict_fcp_sales_protection=True,
    )
    anchored_wall = time.time() - t0

    fcp_choices = evaluate_fcp_choices(
        v_out,
        c_n,
        fcp_res.get("bundle_prices_full") or fcp_res.get("bundle_prices") or {},
        np.asarray(fcp_res["assortments"], dtype=int),
    )
    bsp_choices = evaluate_bsp_choices(v_out, c_n, bsp_res.get("size_prices") or {})
    cpbsd_choices = evaluate_cpbsd_a_choices(v_out, c_n, cpbsd_res["p"], cpbsd_res["d"])
    anchored_choices = evaluate_hybrid_choices(
        v_out,
        c_n,
        anchored.get("bundle_prices_full") or {},
        np.asarray(anchored.get("assortments"), dtype=int),
        anchored.get("size_prices") or {},
    ) if anchored.get("feasible") else [{"channel": "outside", "profit": 0.0, "surplus": 0.0, "size": 0} for _ in range(v_out.shape[0])]
    anchored_bsp_only_choices = evaluate_bsp_choices(v_out, c_n, anchored.get("size_prices") or {}) if anchored.get("feasible") else []

    anchored_eval = eval_hybrid_oos(
        v_out,
        c_n,
        anchored.get("bundle_prices_full") or {},
        np.asarray(anchored.get("assortments"), dtype=int),
        anchored.get("size_prices") or {},
    ) if anchored.get("feasible") else {"hybrid_oos": 0.0, "chose_fcp": 0, "chose_bsp": 0, "chose_outside": int(v_out.shape[0])}

    fcp_oos = average_profit(fcp_choices)
    bsp_oos = average_profit(bsp_choices)
    cpbsd_oos = average_profit(cpbsd_choices)
    anchored_oos = float(anchored_eval["hybrid_oos"])

    lower_bounds = lower_bound_diagnostics(
        v_kn,
        c_n,
        np.asarray(fcp_res["assortments"], dtype=int),
        fcp_res.get("bundle_prices_full") or fcp_res.get("bundle_prices") or {},
        fcp_res.get("chosen_bundle_idx_by_customer") or [],
        anchored.get("size_prices") or {},
    ) if anchored.get("feasible") else []

    payload = {
        "N": int(n_products),
        "seed": int(seed),
        "instance_id": instance_path.stem,
        "input_paths": {k: str(v) for k, v in paths.items()},
        "instance_path": str(instance_path),
        "anchored_result": anchored,
        "anchored_wall_time_total": float(anchored_wall),
        "oos": {
            "k_out": int(v_out.shape[0]),
            "fcp": float(fcp_oos),
            "bsp": float(bsp_oos),
            "cpbsd_a": float(cpbsd_oos),
            "anchored": float(anchored_oos),
            "delta_anchored_fcp": float(anchored_oos - fcp_oos),
            "delta_anchored_bsp": float(anchored_oos - bsp_oos),
            "delta_anchored_cpbsd_a": float(anchored_oos - cpbsd_oos),
        },
        "choice_counts": {
            "fcp": channel_counts(fcp_choices),
            "bsp": channel_counts(bsp_choices),
            "cpbsd_a": channel_counts(cpbsd_choices),
            "anchored": {
                "fcp": int(anchored_eval["chose_fcp"]),
                "bsp": int(anchored_eval["chose_bsp"]),
                "outside": int(anchored_eval["chose_outside"]),
            },
        },
        "migration_fcp_to_anchored": migration_counts(fcp_choices, anchored_choices),
        "lower_bound_by_size": lower_bounds,
        "fcp_outside_cpbsd_buy": fcp_outside_cpbsd_buy_summary(
            fcp_choices,
            anchored_choices,
            anchored_bsp_only_choices,
            cpbsd_choices,
        ),
        "cpbsd_vs_anchored_size_price": cpbsd_vs_anchored_size_price_summary(
            cpbsd_choices,
            anchored.get("size_prices") or {},
        ),
    }
    return payload


def row_from_payload(payload: dict) -> dict:
    oos = payload["oos"]
    anchored_choice = payload["choice_counts"]["anchored"]
    anchored_result = payload["anchored_result"]
    return {
        "N": int(payload["N"]),
        "seed": int(payload["seed"]),
        "instance_id": payload["instance_id"],
        "fcp_oos": float(oos["fcp"]),
        "bsp_oos": float(oos["bsp"]),
        "cpbsd_a_oos": float(oos["cpbsd_a"]),
        "anchored_oos": float(oos["anchored"]),
        "delta_anchored_fcp": float(oos["delta_anchored_fcp"]),
        "delta_anchored_bsp": float(oos["delta_anchored_bsp"]),
        "delta_anchored_cpbsd_a": float(oos["delta_anchored_cpbsd_a"]),
        "anchored_feasible": bool(anchored_result.get("feasible")),
        "anchored_status": anchored_result.get("solver_status"),
        "anchored_ins_objective": anchored_result.get("objective"),
        "anchored_runtime": anchored_result.get("runtime"),
        "anchored_wall_time_total": payload.get("anchored_wall_time_total"),
        "protected_customer_count": anchored_result.get("protected_customer_count"),
        "protection_constraint_count": anchored_result.get("protection_constraint_count"),
        "strict_protection_constraint_count": anchored_result.get("strict_protection_constraint_count"),
        "protected_bsp_choice_count": anchored_result.get("protected_bsp_choice_count"),
        "anchored_oos_fcp": int(anchored_choice.get("fcp", 0)),
        "anchored_oos_bsp": int(anchored_choice.get("bsp", 0)),
        "anchored_oos_outside": int(anchored_choice.get("outside", 0)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Anchored FCP+BSP on existing N=10/N=30 hvhm phase2 seeds.")
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--time-limit", type=float, default=600.0)
    parser.add_argument("--mip-gap", type=float, default=1e-2)
    parser.add_argument("--threads", type=int, default=0)
    parser.add_argument("--output-flag", type=int, default=0)
    parser.add_argument("--k-out", type=int, default=5000)
    parser.add_argument("--n-values", type=int, nargs="+", default=[10, 30])
    parser.add_argument("--seeds", type=int, nargs="+", default=SEEDS)
    args = parser.parse_args()

    args.output_root.mkdir(parents=True, exist_ok=True)
    result_dir = args.output_root / "per_seed"
    result_dir.mkdir(parents=True, exist_ok=True)

    payloads = []
    summary_rows = []
    for n_products in args.n_values:
        for seed in args.seeds:
            print(f"Running Anchored FCP+BSP N={n_products} seed={seed}", flush=True)
            payload = run_one(n_products, seed, args)
            payloads.append(payload)
            summary_rows.append(row_from_payload(payload))
            per_seed_path = result_dir / f"n{n_products}_seed_{seed}.json"
            with per_seed_path.open("w") as f:
                json.dump(payload, f, indent=2, default=json_default)
            print(
                f"  OOS Anchored={payload['oos']['anchored']:.6f} "
                f"FCP={payload['oos']['fcp']:.6f} "
                f"BSP={payload['oos']['bsp']:.6f} "
                f"CPBSD-A={payload['oos']['cpbsd_a']:.6f} "
                f"protected_bsp={payload['anchored_result'].get('protected_bsp_choice_count')}",
                flush=True,
            )

    aggregate_rows = aggregate_by_n(summary_rows)
    diagnostic_selected = select_diagnostic_rows(summary_rows, aggregate_rows)
    diagnostics = {}
    payload_by_key = {(p["N"], p["seed"]): p for p in payloads}
    diag_dir = args.output_root / "diagnostics"
    diag_dir.mkdir(parents=True, exist_ok=True)
    for row in diagnostic_selected:
        key = (int(row["N"]), int(row["seed"]))
        payload = payload_by_key[key]
        diag_payload = {
            "N": payload["N"],
            "seed": payload["seed"],
            "instance_id": payload["instance_id"],
            "oos": payload["oos"],
            "choice_counts": payload["choice_counts"],
            "migration_fcp_to_anchored": payload["migration_fcp_to_anchored"],
            "fcp_outside_cpbsd_buy": payload["fcp_outside_cpbsd_buy"],
            "lower_bound_by_size": payload["lower_bound_by_size"],
            "cpbsd_vs_anchored_size_price": payload["cpbsd_vs_anchored_size_price"],
        }
        diag_key = f"N={row['N']} seed={row['seed']}"
        diagnostics[diag_key] = diag_payload
        with (diag_dir / f"n{row['N']}_seed_{row['seed']}_diagnostic.json").open("w") as f:
            json.dump(diag_payload, f, indent=2, default=json_default)

    summary_fields = [
        "N",
        "seed",
        "instance_id",
        "fcp_oos",
        "bsp_oos",
        "cpbsd_a_oos",
        "anchored_oos",
        "delta_anchored_fcp",
        "delta_anchored_bsp",
        "delta_anchored_cpbsd_a",
        "anchored_feasible",
        "anchored_status",
        "anchored_ins_objective",
        "anchored_runtime",
        "anchored_wall_time_total",
        "protected_customer_count",
        "protection_constraint_count",
        "strict_protection_constraint_count",
        "protected_bsp_choice_count",
        "anchored_oos_fcp",
        "anchored_oos_bsp",
        "anchored_oos_outside",
    ]
    aggregate_fields = [
        "N",
        "seed_count",
        "fcp_oos_mean",
        "bsp_oos_mean",
        "cpbsd_a_oos_mean",
        "anchored_oos_mean",
        "delta_anchored_fcp_mean",
        "delta_anchored_bsp_mean",
        "delta_anchored_cpbsd_a_mean",
        "anchored_beats_fcp_count",
    ]
    write_csv(args.output_root / "anchored_hvhm_summary.csv", summary_rows, summary_fields)
    write_csv(args.output_root / "anchored_hvhm_aggregate.csv", aggregate_rows, aggregate_fields)
    with (args.output_root / "anchored_hvhm_summary.json").open("w") as f:
        json.dump(summary_rows, f, indent=2, default=json_default)
    with (args.output_root / "anchored_hvhm_aggregate.json").open("w") as f:
        json.dump(aggregate_rows, f, indent=2, default=json_default)
    report = make_markdown_report(summary_rows, aggregate_rows, diagnostics)
    (args.output_root / "anchored_hvhm_report.md").write_text(report)
    print(f"Saved results to {args.output_root}", flush=True)


if __name__ == "__main__":
    main()
