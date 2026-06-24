import argparse
import csv
import json
import math
import os
import shutil
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import msgpack
import msgpack_numpy as mnp
import numpy as np


DEFAULT_EXPERIMENT_ROOT = Path(
    os.environ.get(
        "MB_OOS_EXPERIMENT_ROOT",
        "/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/cpbsd_baselines_v2",
    )
)

DEFAULT_OUTPUT_ROOT = DEFAULT_EXPERIMENT_ROOT / "results" / "mb_oos_attribution"
EPS = 1e-9


def build_assortments(n: int) -> np.ndarray:
    return np.array([list(map(int, format(num, f"0{n}b"))) for num in range(2**n)], dtype=int)


def valuation_means(n: int, heterogeneity: str) -> np.ndarray:
    if heterogeneity == "none":
        return np.ones(n)
    if heterogeneity == "partial":
        n1 = int(0.4 * n)
        means = np.ones(n)
        means[n1:] = 5.0
        return means
    idx = np.arange(n)
    return 1.0 + 9.0 * idx / (n - 1)


def _norm_cdf(x: np.ndarray) -> np.ndarray:
    return 0.5 * (1.0 + np.vectorize(math.erf)(x / np.sqrt(2.0)))


def _norm_ppf(u: np.ndarray) -> np.ndarray:
    import torch

    t = torch.as_tensor(u, dtype=torch.float64)
    z = np.sqrt(2.0) * torch.erfinv(2.0 * t - 1.0)
    return z.numpy()


def _toeplitz_corr(n: int, rho: float) -> np.ndarray:
    idx = np.arange(n)
    return rho ** np.abs(idx[:, None] - idx[None, :])


def sample_valuations(k: int, means: np.ndarray, family: str, rho: float, rng: np.random.Generator) -> np.ndarray:
    n = len(means)
    corr = _toeplitz_corr(n, rho)
    z = rng.multivariate_normal(mean=np.zeros(n), cov=corr, size=k)
    u = np.clip(_norm_cdf(z), 1e-10, 1 - 1e-10)

    if family == "exponential":
        v = -means * np.log(1.0 - u)
    elif family == "logit":
        scale = 0.25
        loc = means - 0.577 * scale
        v = loc + (-scale * np.log(-np.log(u)))
    elif family == "lognormal":
        sigma = 0.5
        mu = np.log(means) - 0.5 * (sigma**2)
        v = np.exp(mu + sigma * _norm_ppf(u))
    elif family == "normal":
        sigma = 0.5
        v = means + sigma * _norm_ppf(u)
    elif family == "uniform":
        v = (means - 1.0) + 2.0 * u
    else:
        raise ValueError(f"Unsupported family: {family}")

    return np.maximum(v, 0.0)


def sample_out_of_sample_valuations(setup: dict, out_k: int) -> np.ndarray:
    rng = np.random.default_rng(int(setup["seed"]) + 99991)
    means = valuation_means(int(setup["n_products"]), setup["heterogeneity"])
    return sample_valuations(
        k=out_k,
        means=means,
        family=setup["dist_family"],
        rho=float(setup["rho"]),
        rng=rng,
    )


def eval_mb_policy(v_eval: np.ndarray, prices: np.ndarray, profits: np.ndarray, assortments: np.ndarray) -> Dict:
    values = v_eval @ assortments.T
    revenue = 0.0
    chosen_bundles = []
    chosen_surplus = []
    for customer_idx in range(v_eval.shape[0]):
        best_bundle = None
        best_surplus = 0.0
        best_profit = 0.0
        for bundle_idx in range(assortments.shape[0]):
            surplus = float(values[customer_idx, bundle_idx] - prices[bundle_idx])
            if abs(surplus) <= EPS:
                surplus = 0.0
            profit = float(profits[bundle_idx])
            if surplus > best_surplus + EPS or (abs(surplus - best_surplus) <= EPS and profit > best_profit + EPS):
                best_bundle = bundle_idx
                best_surplus = surplus
                best_profit = profit
        if best_bundle is None:
            chosen_bundles.append(0)
            chosen_surplus.append(0.0)
            continue
        chosen_bundles.append(int(best_bundle))
        chosen_surplus.append(float(best_surplus))
        revenue += float(profits[best_bundle])
    chosen_bundles = np.asarray(chosen_bundles, dtype=int)
    chosen_surplus = np.asarray(chosen_surplus, dtype=float)
    buy_rate = float(np.mean(chosen_bundles != 0))
    outside_rate = 1.0 - buy_rate
    return {
        "revenue": revenue / v_eval.shape[0],
        "buy_rate": buy_rate,
        "outside_rate": outside_rate,
        "chosen_bundles": chosen_bundles,
        "chosen_surplus": chosen_surplus,
    }


def eval_bsp_policy(v_eval: np.ndarray, c_n: np.ndarray, size_prices: Dict[int, float]) -> float:
    total = 0.0
    k_count, n_products = v_eval.shape
    for k in range(k_count):
        best_surplus = 0.0
        best_size = 0
        best_cost = 0.0
        order = np.argsort(-v_eval[k])
        prefix_val = 0.0
        prefix_cost = 0.0
        for size in range(1, n_products + 1):
            idx = order[size - 1]
            prefix_val += v_eval[k, idx]
            prefix_cost += c_n[idx]
            price = size_prices.get(size)
            if price is None:
                continue
            surplus = prefix_val - float(price)
            if surplus > best_surplus:
                best_surplus = surplus
                best_size = size
                best_cost = prefix_cost
        if best_surplus <= 0.0 or best_size == 0:
            continue
        total += float(size_prices[best_size]) - best_cost
    return total / k_count


def build_folds(k_count: int, seed: int, n_folds: int = 5) -> List[np.ndarray]:
    rng = np.random.default_rng(seed + 20260318)
    idx = np.arange(k_count)
    rng.shuffle(idx)
    return [fold for fold in np.array_split(idx, n_folds) if len(fold) > 0]


def candidate_label(name: str, param) -> str:
    if isinstance(param, float):
        return f"{name}:{param:.2f}"
    return f"{name}:{param}"


def haircut_transform(data: Dict, gamma: float) -> np.ndarray:
    prices = data["mb_prices"].copy()
    sizes = data["bundle_sizes"]
    costs = data["bundle_costs"]
    for bundle_idx in range(1, len(prices)):
        if sizes[bundle_idx] >= 4:
            margin = prices[bundle_idx] - costs[bundle_idx]
            prices[bundle_idx] = costs[bundle_idx] + gamma * margin
    return prices


def shrinkage_transform(data: Dict, alpha: float) -> np.ndarray:
    prices = data["mb_prices"].copy()
    size_prices = data["bsp_size_prices"]
    sizes = data["bundle_sizes"]
    for bundle_idx in range(1, len(prices)):
        bsp_anchor = float(size_prices.get(int(sizes[bundle_idx]), prices[bundle_idx]))
        prices[bundle_idx] = alpha * prices[bundle_idx] + (1.0 - alpha) * bsp_anchor
    return prices


def support_smoothing_transform(data: Dict, threshold: int) -> np.ndarray:
    prices = data["mb_prices"].copy()
    size_prices = data["bsp_size_prices"]
    sizes = data["bundle_sizes"]
    support = data["support_counts"]
    for bundle_idx in range(1, len(prices)):
        if int(support.get(bundle_idx, 0)) <= threshold:
            prices[bundle_idx] = float(size_prices.get(int(sizes[bundle_idx]), prices[bundle_idx]))
    return prices


def margin_buffer_transform(data: Dict, tau: float) -> np.ndarray:
    prices = data["mb_prices"].copy()
    costs = data["bundle_costs"]
    values = data["v_in"] @ data["assortments"].T
    chosen = data["chosen_bundles_in"]
    for bundle_idx in range(1, len(prices)):
        buyer_idx = np.where(chosen == bundle_idx)[0]
        if len(buyer_idx) == 0:
            continue
        cap = float(np.min(values[buyer_idx, bundle_idx] - tau))
        prices[bundle_idx] = max(float(costs[bundle_idx]), min(float(prices[bundle_idx]), cap))
    return prices


EXPERIMENTS = {
    "exp01_haircut": {
        "title": "Experiment 01: Size-4/5 Margin Haircut",
        "family": "haircut",
        "grid": [1.00, 0.95, 0.90, 0.85, 0.80, 0.75, 0.70],
        "transform": haircut_transform,
        "theory": "Large bundles carry the biggest revenue-loss contribution in the attribution report. A margin haircut should reduce how often they sit exactly on the purchase boundary and therefore lower OOS substitution/outside drift.",
        "selection": "Global 5-fold validation over the 5 baseline instances; one shared gamma is selected for all instances.",
    },
    "exp02_shrinkage": {
        "title": "Experiment 02: MB-to-BSP Price Shrinkage",
        "family": "shrinkage",
        "grid": [1.00, 0.75, 0.50, 0.25, 0.00],
        "transform": shrinkage_transform,
        "theory": "Blend the free-form MB price table toward BSP's size-based price anchor. This preserves some bundle discrimination but cuts variance in poorly supported local price differences.",
        "selection": "Global 5-fold validation over the 5 baseline instances; one shared alpha is selected for all instances.",
    },
    "exp03_support_smoothing": {
        "title": "Experiment 03: Support-Aware Price Smoothing",
        "family": "support_smoothing",
        "grid": [0, 1, 2, 3],
        "transform": support_smoothing_transform,
        "theory": "Bundles with only a handful of in-sample buyers should not get fully trusted custom prices. Replacing low-support bundles with BSP size prices trades some fit for lower variance.",
        "selection": "Global 5-fold validation over the 5 baseline instances; one shared support threshold is selected for all instances.",
    },
    "exp04_validation_selection": {
        "title": "Experiment 04: Validation-Based Candidate Selection",
        "family": "validation_selection",
        "grid": [],
        "transform": None,
        "theory": "Rather than commit to one transform family ex ante, let a validation layer choose the most stable candidate policy for each instance from the candidate library.",
        "selection": "Per-instance 5-fold validation picks the best candidate from baseline, haircut, shrinkage, support smoothing, and margin buffer libraries.",
    },
    "exp05_margin_buffer": {
        "title": "Experiment 05: Minimum Surplus Margin Buffer",
        "family": "margin_buffer",
        "grid": [0.00, 0.05, 0.10, 0.20, 0.30],
        "transform": margin_buffer_transform,
        "theory": "The attribution report shows many in-sample sales occur at tiny positive surplus. Enforcing a minimum surplus buffer lowers prices just enough to move those knife-edge sales away from zero.",
        "selection": "Global 5-fold validation over the 5 baseline instances; one shared tau is selected for all instances.",
    },
}


def write_csv(path: Path, rows: List[Dict]):
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def markdown_table(columns: List[str], rows: List[Dict]) -> str:
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join(["---"] * len(columns)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(col, "")) for col in columns) + " |")
    return "\n".join(lines)


def plot_ratio_boxplot(rows: List[Dict], output_path: Path, title: str):
    methods = []
    by_method = {}
    for row in rows:
        method = row["method"]
        if method not in by_method:
            methods.append(method)
            by_method[method] = {"in": [], "out": []}
        by_method[method]["in"].append(float(row["ratio_in_to_bsp"]))
        by_method[method]["out"].append(float(row["ratio_out_to_bsp"]))

    x = np.arange(len(methods), dtype=float)
    fig, ax = plt.subplots(figsize=(max(6.0, 1.5 * len(methods) + 2.0), 4.8), dpi=180)
    ax.set_facecolor("#ebebeb")
    fig.patch.set_facecolor("white")

    in_sample = [by_method[m]["in"] for m in methods]
    out_sample = [by_method[m]["out"] for m in methods]
    box_in = ax.boxplot(
        in_sample,
        positions=x - 0.18,
        widths=0.32,
        patch_artist=True,
        showfliers=False,
        manage_ticks=False,
    )
    box_out = ax.boxplot(
        out_sample,
        positions=x + 0.18,
        widths=0.32,
        patch_artist=True,
        showfliers=False,
        manage_ticks=False,
    )
    for patch in box_in["boxes"]:
        patch.set(facecolor="#74c0e3", edgecolor="#2b8cbe", linewidth=1.0)
    for patch in box_out["boxes"]:
        patch.set(facecolor="#2b8cbe", edgecolor="#1f5d84", linewidth=1.0)
    for key, color in (("whiskers", "#1f5d84"), ("caps", "#1f5d84"), ("medians", "#1f5d84")):
        for artist in box_in[key] + box_out[key]:
            artist.set(color=color, linewidth=1.0)

    ax.axhline(1.0, color="#cc6d2d", linestyle="--", linewidth=1.2, label="BSP")
    ax.plot([], [], color="#74c0e3", linewidth=6, label="In-sample")
    ax.plot([], [], color="#2b8cbe", linewidth=6, label="Out-of-sample")
    ax.set_xticks(x)
    ax.set_xticklabels(methods)
    ax.set_ylabel("Revenue Ratio vs BSP")
    ax.set_title(title)
    ax.grid(axis="y", color="white", linewidth=1.0)
    ax.set_axisbelow(True)
    ax.legend(loc="upper left", fontsize=8, frameon=True)
    fig.tight_layout()
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)


def plot_instance_bars(rows: List[Dict], output_path: Path, title: str):
    instances = [row["instance"] for row in rows if row["method"] == "Baseline MB"]
    baseline_map = {row["instance"]: row for row in rows if row["method"] == "Baseline MB"}
    variant_method = next(row["method"] for row in rows if row["method"] != "Baseline MB")
    variant_map = {row["instance"]: row for row in rows if row["method"] == variant_method}

    x = np.arange(len(instances), dtype=float)
    width = 0.18
    fig, ax = plt.subplots(figsize=(max(7.0, 1.6 * len(instances) + 2.0), 4.8), dpi=180)
    ax.bar(x - 1.5 * width, [baseline_map[i]["revenue_in"] for i in instances], width, label="Baseline In", color="#74c0e3")
    ax.bar(x - 0.5 * width, [baseline_map[i]["revenue_out"] for i in instances], width, label="Baseline Out", color="#2b8cbe")
    ax.bar(x + 0.5 * width, [variant_map[i]["revenue_in"] for i in instances], width, label="Variant In", color="#a8c686")
    ax.bar(x + 1.5 * width, [variant_map[i]["revenue_out"] for i in instances], width, label="Variant Out", color="#5f8c3f")
    ax.set_xticks(x)
    ax.set_xticklabels(instances)
    ax.set_ylabel("Revenue")
    ax.set_title(title)
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    ax.set_axisbelow(True)
    ax.legend(ncol=2, fontsize=8)
    fig.tight_layout()
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)


def plot_candidate_sweep(rows: List[Dict], output_path: Path, title: str, x_label: str):
    if not rows:
        return
    x = [row["param"] for row in rows]
    y_cv = [row["mean_cv_revenue"] for row in rows]
    y_oos = [row["mean_out_revenue"] for row in rows]
    fig, ax = plt.subplots(figsize=(6.5, 4.2), dpi=180)
    ax.plot(x, y_cv, marker="o", label="Mean CV Revenue", color="#2b8cbe")
    ax.plot(x, y_oos, marker="s", label="Mean OOS Revenue", color="#cc6d2d")
    ax.set_xlabel(x_label)
    ax.set_ylabel("Revenue")
    ax.set_title(title)
    ax.grid(alpha=0.35, linestyle="--")
    ax.legend()
    fig.tight_layout()
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)


def load_data(experiment_root: Path, out_k: int) -> List[Dict]:
    data = []
    for instance_idx in range(1, 6):
        instance_path = experiment_root / "instances" / "n5" / f"cpbsd_instance_{instance_idx:03d}_N5_K50_normal_rho0.0_full_hvhm.msgpack"
        mb_path = experiment_root / "results" / f"baseline_mb_n5_inst{instance_idx:03d}.json"
        bsp_path = experiment_root / "results" / f"baseline_bsp_n5_inst{instance_idx:03d}.json"

        with instance_path.open("rb") as f:
            obj = msgpack.load(f, object_hook=mnp.decode)
        v_in = np.asarray(obj["valuation_samples_V"], dtype=float)
        c_n = np.asarray(obj["production_cost_c"], dtype=float)
        setup = obj["setup"]
        v_out = sample_out_of_sample_valuations(setup, out_k)
        assortments = build_assortments(v_in.shape[1])
        bundle_sizes = assortments.sum(axis=1)
        bundle_costs = assortments @ c_n

        mb_res = json.loads(mb_path.read_text(encoding="utf-8"))
        mb_prices = np.array([float(mb_res["bundle_prices_full"][str(i)]) for i in range(assortments.shape[0])], dtype=float)
        support_counts = Counter(int(x) for x in mb_res["chosen_bundle_idx_by_customer"])
        chosen_in = np.asarray(mb_res["chosen_bundle_idx_by_customer"], dtype=int)

        bsp_res = json.loads(bsp_path.read_text(encoding="utf-8"))
        bsp_size_prices = {int(k): float(v) for k, v in (bsp_res["size_prices"] or {}).items()}
        bsp_revenue_in = eval_bsp_policy(v_in, c_n, bsp_size_prices)
        bsp_revenue_out = eval_bsp_policy(v_out, c_n, bsp_size_prices)

        folds = build_folds(v_in.shape[0], int(setup["seed"]), n_folds=5)
        data.append(
            {
                "instance_idx": instance_idx,
                "instance": f"inst{instance_idx:03d}",
                "setup": setup,
                "v_in": v_in,
                "v_out": v_out,
                "c_n": c_n,
                "assortments": assortments,
                "bundle_sizes": bundle_sizes,
                "bundle_costs": bundle_costs,
                "mb_prices": mb_prices,
                "chosen_bundles_in": chosen_in,
                "support_counts": support_counts,
                "bsp_size_prices": bsp_size_prices,
                "bsp_revenue_in": bsp_revenue_in,
                "bsp_revenue_out": bsp_revenue_out,
                "folds": folds,
            }
        )
    return data


def evaluate_candidate_policy(data: Dict, prices: np.ndarray) -> Dict:
    profits = prices - data["bundle_costs"]
    in_eval = eval_mb_policy(data["v_in"], prices, profits, data["assortments"])
    out_eval = eval_mb_policy(data["v_out"], prices, profits, data["assortments"])
    return {
        "prices": prices,
        "profits": profits,
        "in_eval": in_eval,
        "out_eval": out_eval,
        "ratio_in_to_bsp": in_eval["revenue"] / data["bsp_revenue_in"],
        "ratio_out_to_bsp": out_eval["revenue"] / data["bsp_revenue_out"],
        "drop_pct": 100.0 * (in_eval["revenue"] - out_eval["revenue"]) / max(in_eval["revenue"], EPS),
    }


def cv_revenue(data: Dict, prices: np.ndarray) -> float:
    profits = prices - data["bundle_costs"]
    scores = []
    for val_idx in data["folds"]:
        fold_eval = eval_mb_policy(data["v_in"][val_idx], prices, profits, data["assortments"])
        scores.append(fold_eval["revenue"])
    return float(np.mean(scores))


def run_global_grid_experiment(data_items: List[Dict], exp_key: str, spec: Dict) -> Dict:
    candidate_rows = []
    best_param = None
    best_score = -1e18
    for param in spec["grid"]:
        cv_scores = []
        out_scores = []
        for data in data_items:
            prices = spec["transform"](data, param)
            cv_scores.append(cv_revenue(data, prices))
            out_scores.append(evaluate_candidate_policy(data, prices)["out_eval"]["revenue"])
        row = {
            "param": param,
            "mean_cv_revenue": float(np.mean(cv_scores)),
            "mean_out_revenue": float(np.mean(out_scores)),
        }
        candidate_rows.append(row)
        if row["mean_cv_revenue"] > best_score:
            best_score = row["mean_cv_revenue"]
            best_param = param

    detail_rows = []
    selection_rows = []
    baseline_detail_rows = []
    for data in data_items:
        baseline_eval = evaluate_candidate_policy(data, data["mb_prices"])
        variant_prices = spec["transform"](data, best_param)
        variant_eval = evaluate_candidate_policy(data, variant_prices)

        baseline_detail_rows.append(
            {
                "instance": data["instance"],
                "method": "Baseline MB",
                "param": "baseline",
                "revenue_in": round(baseline_eval["in_eval"]["revenue"], 6),
                "revenue_out": round(baseline_eval["out_eval"]["revenue"], 6),
                "drop_pct": round(baseline_eval["drop_pct"], 6),
                "buy_rate_in": round(baseline_eval["in_eval"]["buy_rate"], 6),
                "buy_rate_out": round(baseline_eval["out_eval"]["buy_rate"], 6),
                "ratio_in_to_bsp": round(baseline_eval["ratio_in_to_bsp"], 6),
                "ratio_out_to_bsp": round(baseline_eval["ratio_out_to_bsp"], 6),
            }
        )
        detail_rows.append(
            {
                "instance": data["instance"],
                "method": spec["title"].split(": ", 1)[1],
                "param": best_param,
                "revenue_in": round(variant_eval["in_eval"]["revenue"], 6),
                "revenue_out": round(variant_eval["out_eval"]["revenue"], 6),
                "drop_pct": round(variant_eval["drop_pct"], 6),
                "buy_rate_in": round(variant_eval["in_eval"]["buy_rate"], 6),
                "buy_rate_out": round(variant_eval["out_eval"]["buy_rate"], 6),
                "ratio_in_to_bsp": round(variant_eval["ratio_in_to_bsp"], 6),
                "ratio_out_to_bsp": round(variant_eval["ratio_out_to_bsp"], 6),
            }
        )
        selection_rows.append(
            {
                "instance": data["instance"],
                "selected_param": best_param,
                "baseline_out_revenue": round(baseline_eval["out_eval"]["revenue"], 6),
                "variant_out_revenue": round(variant_eval["out_eval"]["revenue"], 6),
                "delta_out_revenue": round(variant_eval["out_eval"]["revenue"] - baseline_eval["out_eval"]["revenue"], 6),
            }
        )

    return {
        "selected": best_param,
        "candidate_rows": candidate_rows,
        "baseline_rows": baseline_detail_rows,
        "variant_rows": detail_rows,
        "selection_rows": selection_rows,
    }


def build_validation_library(data: Dict) -> List[Tuple[str, np.ndarray]]:
    library = [("baseline", data["mb_prices"].copy())]
    for gamma in EXPERIMENTS["exp01_haircut"]["grid"]:
        library.append((candidate_label("haircut", gamma), haircut_transform(data, gamma)))
    for alpha in EXPERIMENTS["exp02_shrinkage"]["grid"]:
        library.append((candidate_label("shrinkage", alpha), shrinkage_transform(data, alpha)))
    for threshold in EXPERIMENTS["exp03_support_smoothing"]["grid"]:
        library.append((candidate_label("support", threshold), support_smoothing_transform(data, threshold)))
    for tau in EXPERIMENTS["exp05_margin_buffer"]["grid"]:
        library.append((candidate_label("margin", tau), margin_buffer_transform(data, tau)))
    return library


def run_validation_selection_experiment(data_items: List[Dict], spec: Dict) -> Dict:
    baseline_rows = []
    variant_rows = []
    selection_rows = []
    candidate_rows = []

    for data in data_items:
        baseline_eval = evaluate_candidate_policy(data, data["mb_prices"])
        baseline_rows.append(
            {
                "instance": data["instance"],
                "method": "Baseline MB",
                "param": "baseline",
                "revenue_in": round(baseline_eval["in_eval"]["revenue"], 6),
                "revenue_out": round(baseline_eval["out_eval"]["revenue"], 6),
                "drop_pct": round(baseline_eval["drop_pct"], 6),
                "buy_rate_in": round(baseline_eval["in_eval"]["buy_rate"], 6),
                "buy_rate_out": round(baseline_eval["out_eval"]["buy_rate"], 6),
                "ratio_in_to_bsp": round(baseline_eval["ratio_in_to_bsp"], 6),
                "ratio_out_to_bsp": round(baseline_eval["ratio_out_to_bsp"], 6),
            }
        )

        best_name = None
        best_prices = None
        best_cv = -1e18
        for name, prices in build_validation_library(data):
            mean_cv = cv_revenue(data, prices)
            candidate_rows.append(
                {
                    "instance": data["instance"],
                    "candidate": name,
                    "mean_cv_revenue": round(mean_cv, 6),
                }
            )
            if mean_cv > best_cv:
                best_cv = mean_cv
                best_name = name
                best_prices = prices

        variant_eval = evaluate_candidate_policy(data, best_prices)
        variant_rows.append(
            {
                "instance": data["instance"],
                "method": spec["title"].split(": ", 1)[1],
                "param": best_name,
                "revenue_in": round(variant_eval["in_eval"]["revenue"], 6),
                "revenue_out": round(variant_eval["out_eval"]["revenue"], 6),
                "drop_pct": round(variant_eval["drop_pct"], 6),
                "buy_rate_in": round(variant_eval["in_eval"]["buy_rate"], 6),
                "buy_rate_out": round(variant_eval["out_eval"]["buy_rate"], 6),
                "ratio_in_to_bsp": round(variant_eval["ratio_in_to_bsp"], 6),
                "ratio_out_to_bsp": round(variant_eval["ratio_out_to_bsp"], 6),
            }
        )
        selection_rows.append(
            {
                "instance": data["instance"],
                "selected_candidate": best_name,
                "baseline_out_revenue": round(baseline_eval["out_eval"]["revenue"], 6),
                "variant_out_revenue": round(variant_eval["out_eval"]["revenue"], 6),
                "delta_out_revenue": round(variant_eval["out_eval"]["revenue"] - baseline_eval["out_eval"]["revenue"], 6),
            }
        )

    return {
        "selected": "per-instance CV",
        "candidate_rows": candidate_rows,
        "baseline_rows": baseline_rows,
        "variant_rows": variant_rows,
        "selection_rows": selection_rows,
    }


def summarize_rows(rows: List[Dict]) -> Dict:
    return {
        "mean_revenue_in": float(np.mean([row["revenue_in"] for row in rows])),
        "mean_revenue_out": float(np.mean([row["revenue_out"] for row in rows])),
        "mean_drop_pct": float(np.mean([row["drop_pct"] for row in rows])),
        "mean_ratio_in_to_bsp": float(np.mean([row["ratio_in_to_bsp"] for row in rows])),
        "mean_ratio_out_to_bsp": float(np.mean([row["ratio_out_to_bsp"] for row in rows])),
    }


def render_report(spec: Dict, result: Dict, output_dir: Path):
    baseline_summary = summarize_rows(result["baseline_rows"])
    variant_summary = summarize_rows(result["variant_rows"])
    delta_out = variant_summary["mean_revenue_out"] - baseline_summary["mean_revenue_out"]
    delta_drop = variant_summary["mean_drop_pct"] - baseline_summary["mean_drop_pct"]

    lines = [
        f"# {spec['title']}",
        "",
        "## Setting",
        "",
        "- Fixed setting: `N=5`, `K=50`, `normal`, `rho=0.0`, `full`, `hvhm`.",
        "- Base policy: cached `baseline_v2` MB full bundle price table.",
        f"- Experiment theory: {spec['theory']}",
        f"- Model selection rule: {spec['selection']}",
        f"- Selected setting: `{result['selected']}`",
        "",
        "## Aggregate Result",
        "",
        markdown_table(
            [
                "method",
                "mean_revenue_in",
                "mean_revenue_out",
                "mean_drop_pct",
                "mean_ratio_in_to_bsp",
                "mean_ratio_out_to_bsp",
            ],
            [
                {
                    "method": "Baseline MB",
                    "mean_revenue_in": f"{baseline_summary['mean_revenue_in']:.4f}",
                    "mean_revenue_out": f"{baseline_summary['mean_revenue_out']:.4f}",
                    "mean_drop_pct": f"{baseline_summary['mean_drop_pct']:.2f}%",
                    "mean_ratio_in_to_bsp": f"{baseline_summary['mean_ratio_in_to_bsp']:.4f}",
                    "mean_ratio_out_to_bsp": f"{baseline_summary['mean_ratio_out_to_bsp']:.4f}",
                },
                {
                    "method": spec["title"].split(": ", 1)[1],
                    "mean_revenue_in": f"{variant_summary['mean_revenue_in']:.4f}",
                    "mean_revenue_out": f"{variant_summary['mean_revenue_out']:.4f}",
                    "mean_drop_pct": f"{variant_summary['mean_drop_pct']:.2f}%",
                    "mean_ratio_in_to_bsp": f"{variant_summary['mean_ratio_in_to_bsp']:.4f}",
                    "mean_ratio_out_to_bsp": f"{variant_summary['mean_ratio_out_to_bsp']:.4f}",
                },
            ],
        ),
        "",
        f"- Mean OOS revenue delta vs baseline MB: `{delta_out:+.4f}`.",
        f"- Mean drop delta vs baseline MB: `{delta_drop:+.2f}%`.",
        "",
        "## Per-Instance Result",
        "",
        markdown_table(
            [
                "instance",
                "method",
                "param",
                "revenue_in",
                "revenue_out",
                "drop_pct",
                "ratio_in_to_bsp",
                "ratio_out_to_bsp",
            ],
            result["baseline_rows"] + result["variant_rows"],
        ),
        "",
        "## Selection Detail",
        "",
        markdown_table(list(result["selection_rows"][0].keys()), result["selection_rows"]),
        "",
        "## Plots",
        "",
        "- `boxplot_ratio_vs_bsp_n5.png`: same ratio-vs-BSP perspective as baseline v2.",
        "- `paired_revenue_bars.png`: per-instance in/out revenue bars for baseline MB vs this experiment.",
    ]
    if result["candidate_rows"]:
        lines.extend(
            [
                "",
                "## Candidate Sweep / CV Trace",
                "",
                markdown_table(list(result["candidate_rows"][0].keys()), result["candidate_rows"][: min(20, len(result["candidate_rows"]))]),
            ]
        )
    (output_dir / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def store_snapshot(output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(Path(__file__), output_dir / Path(__file__).name)


def run_one_experiment(data_items: List[Dict], output_root: Path, exp_key: str, spec: Dict):
    exp_dir = output_root / exp_key
    exp_dir.mkdir(parents=True, exist_ok=True)
    store_snapshot(exp_dir)

    if exp_key == "exp04_validation_selection":
        result = run_validation_selection_experiment(data_items, spec)
    else:
        result = run_global_grid_experiment(data_items, exp_key, spec)

    write_csv(exp_dir / "baseline_rows.csv", result["baseline_rows"])
    write_csv(exp_dir / "variant_rows.csv", result["variant_rows"])
    write_csv(exp_dir / "selection_rows.csv", result["selection_rows"])
    if result["candidate_rows"]:
        write_csv(exp_dir / "candidate_rows.csv", result["candidate_rows"])

    comparison_rows = result["baseline_rows"] + result["variant_rows"]
    plot_ratio_boxplot(
        comparison_rows,
        exp_dir / "boxplot_ratio_vs_bsp_n5.png",
        title=f"{spec['title']} vs Baseline MB",
    )
    plot_instance_bars(
        comparison_rows,
        exp_dir / "paired_revenue_bars.png",
        title=f"{spec['title']} Revenue by Instance",
    )
    if exp_key != "exp04_validation_selection":
        plot_candidate_sweep(
            result["candidate_rows"],
            exp_dir / "candidate_sweep.png",
            title=f"{spec['title']} Candidate Sweep",
            x_label="Param",
        )

    render_report(spec, result, exp_dir)

    summary = summarize_rows(result["variant_rows"])
    return {
        "experiment": exp_key,
        "title": spec["title"],
        "selected": result["selected"],
        "mean_revenue_in": round(summary["mean_revenue_in"], 6),
        "mean_revenue_out": round(summary["mean_revenue_out"], 6),
        "mean_drop_pct": round(summary["mean_drop_pct"], 6),
        "mean_ratio_out_to_bsp": round(summary["mean_ratio_out_to_bsp"], 6),
        "report_path": str(exp_dir / "REPORT.md"),
        "plot_path": str(exp_dir / "boxplot_ratio_vs_bsp_n5.png"),
    }


def main():
    parser = argparse.ArgumentParser(description="Run MB OOS improvement experiments on the fixed N=5, K=50 baseline_v2 setup.")
    parser.add_argument("--experiment-root", type=Path, default=DEFAULT_EXPERIMENT_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--out-k", type=int, default=5000)
    args = parser.parse_args()

    data_items = load_data(args.experiment_root, args.out_k)
    summaries = []
    for exp_key in EXPERIMENTS:
        summary = run_one_experiment(data_items, args.output_root, exp_key, EXPERIMENTS[exp_key])
        summaries.append(summary)
        print(
            json.dumps(
                {
                    "finished_experiment": exp_key,
                    "selected": summary["selected"],
                    "mean_revenue_out": summary["mean_revenue_out"],
                    "mean_drop_pct": summary["mean_drop_pct"],
                    "report_path": summary["report_path"],
                },
                ensure_ascii=False,
            )
        )

    write_csv(args.output_root / "experiment_suite_summary.csv", summaries)
    (args.output_root / "experiment_suite_summary.json").write_text(
        json.dumps(summaries, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({"summary_csv": str(args.output_root / "experiment_suite_summary.csv")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
