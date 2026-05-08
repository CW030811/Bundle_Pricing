import argparse
import csv
import json
import math
import os
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional

import msgpack
import msgpack_numpy as mnp
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent

DEFAULT_EXPERIMENT_ROOT = Path(
    os.environ.get(
        "MB_OOS_ATTRIBUTION_ROOT",
        "/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/cpbsd_baselines_v2",
    )
)

DEFAULT_PROJECT_ROOT = Path(
    os.environ.get(
        "MB_OOS_ATTRIBUTION_PROJECT_ROOT",
        "/Users/sensen/.openclaw/workspace/domains/revenue-management/project-root/code_submission_project/code_submission",
    )
)

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


def load_instance(instance_path: Path):
    with instance_path.open("rb") as f:
        obj = msgpack.load(f, object_hook=mnp.decode)
    return (
        np.asarray(obj["valuation_samples_V"], dtype=float),
        np.asarray(obj["production_cost_c"], dtype=float),
        obj["setup"],
    )


def format_float(value: Optional[float], digits: int = 4) -> str:
    if value is None:
        return ""
    return f"{value:.{digits}f}"


def bundle_bits(bundle_idx: int, n_products: int) -> str:
    return format(bundle_idx, f"0{n_products}b")


def bundle_label(bundle_idx: int, assortments: np.ndarray) -> str:
    return f"{bundle_idx} ({bundle_bits(bundle_idx, assortments.shape[1])})"


def tuple_better(score_a, score_b) -> bool:
    surplus_a, profit_a = score_a
    surplus_b, profit_b = score_b
    return surplus_a > surplus_b + EPS or (abs(surplus_a - surplus_b) <= EPS and profit_a > profit_b + EPS)


def evaluate_customer_choices(
    v_eval: np.ndarray,
    prices: np.ndarray,
    profits: np.ndarray,
    assortments: np.ndarray,
    forced_choices: Optional[np.ndarray] = None,
) -> List[Dict]:
    values = v_eval @ assortments.T
    surpluses = values - prices[None, :]
    rows = []

    for customer_idx in range(v_eval.shape[0]):
        best_bundle = None
        best_score = (0.0, 0.0)
        for bundle_idx in range(assortments.shape[0]):
            surplus = float(surpluses[customer_idx, bundle_idx])
            if abs(surplus) <= EPS:
                surplus = 0.0
            score = (surplus, float(profits[bundle_idx]))
            if tuple_better(score, best_score):
                best_bundle = bundle_idx
                best_score = score

        chosen_bundle = int(forced_choices[customer_idx]) if forced_choices is not None else int(best_bundle or 0)
        chosen_surplus = float(surpluses[customer_idx, chosen_bundle]) if chosen_bundle < assortments.shape[0] else 0.0
        if abs(chosen_surplus) <= EPS:
            chosen_surplus = 0.0

        alt_bundle = 0
        alt_score = (0.0, 0.0)
        for bundle_idx in range(assortments.shape[0]):
            if bundle_idx == chosen_bundle:
                continue
            surplus = float(surpluses[customer_idx, bundle_idx])
            if abs(surplus) <= EPS:
                surplus = 0.0
            score = (surplus, float(profits[bundle_idx]))
            if tuple_better(score, alt_score):
                alt_bundle = bundle_idx
                alt_score = score

        rows.append(
            {
                "customer_id": customer_idx,
                "valuations": [float(x) for x in v_eval[customer_idx].tolist()],
                "chosen_bundle": chosen_bundle,
                "chosen_size": int(assortments[chosen_bundle].sum()),
                "chosen_value": float(values[customer_idx, chosen_bundle]),
                "chosen_surplus": chosen_surplus,
                "chosen_profit": float(profits[chosen_bundle]),
                "alt_bundle": alt_bundle,
                "alt_size": int(assortments[alt_bundle].sum()),
                "alt_value": float(values[customer_idx, alt_bundle]),
                "alt_surplus": float(alt_score[0]),
                "alt_profit": float(profits[alt_bundle]),
                "margin_vs_alt": chosen_surplus - float(alt_score[0]),
                "all_bundle_surpluses": surpluses[customer_idx].copy(),
            }
        )

    return rows


def top_choice_counter(rows: List[Dict], key: str) -> str:
    counter = Counter(int(row[key]) for row in rows)
    if not counter:
        return ""
    bundle_idx, count = counter.most_common(1)[0]
    return f"{bundle_idx} x {count}"


def markdown_table(columns: List[str], rows: List[Dict]) -> str:
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join(["---"] * len(columns)) + " |",
    ]
    for row in rows:
        vals = [str(row.get(col, "")) for col in columns]
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


def compute_bundle_attribution(
    instance_idx: int,
    assortments: np.ndarray,
    prices: np.ndarray,
    profits: np.ndarray,
    in_rows: List[Dict],
    out_rows: List[Dict],
    near_miss_eps: float,
) -> List[Dict]:
    total_in = len(in_rows)
    total_out = len(out_rows)
    out_by_bundle = Counter(row["chosen_bundle"] for row in out_rows)
    in_by_bundle = Counter(row["chosen_bundle"] for row in in_rows)
    rows = []

    for bundle_idx in range(1, assortments.shape[0]):
        train_buyers = in_by_bundle.get(bundle_idx, 0)
        out_buyers = out_by_bundle.get(bundle_idx, 0)
        in_share = train_buyers / total_in
        out_share = out_buyers / total_out
        near_miss_rows = [
            row
            for row in out_rows
            if -near_miss_eps <= float(row["all_bundle_surpluses"][bundle_idx]) < 0.0
        ]
        rows.append(
            {
                "instance": f"inst{instance_idx:03d}",
                "bundle": bundle_idx,
                "bundle_bits": bundle_bits(bundle_idx, assortments.shape[1]),
                "size": int(assortments[bundle_idx].sum()),
                "price": float(prices[bundle_idx]),
                "profit_per_sale": float(profits[bundle_idx]),
                "train_buyers": train_buyers,
                "train_share": in_share,
                "out_buyers": out_buyers,
                "out_share": out_share,
                "share_delta": out_share - in_share,
                "revenue_delta_per_customer": (out_share - in_share) * float(profits[bundle_idx]),
                "train_avg_surplus": np.mean(
                    [row["chosen_surplus"] for row in in_rows if row["chosen_bundle"] == bundle_idx]
                )
                if train_buyers
                else None,
                "train_min_surplus": np.min(
                    [row["chosen_surplus"] for row in in_rows if row["chosen_bundle"] == bundle_idx]
                )
                if train_buyers
                else None,
                "out_near_miss_count": len(near_miss_rows),
                "out_near_miss_choose_outside": sum(1 for row in near_miss_rows if row["chosen_bundle"] == 0),
                "out_near_miss_choose_other_bundle": sum(1 for row in near_miss_rows if row["chosen_bundle"] != 0),
                "out_top_substitute": top_choice_counter(
                    [row for row in near_miss_rows if row["chosen_bundle"] != 0],
                    "chosen_bundle",
                ),
            }
        )

    rows.sort(key=lambda row: row["revenue_delta_per_customer"])
    return rows


def pick_customer_examples(
    bundle_idx: int,
    in_rows: List[Dict],
    out_rows: List[Dict],
    near_miss_eps: float,
    limit: int,
) -> Dict[str, List[Dict]]:
    edge_rows = [row for row in in_rows if row["chosen_bundle"] == bundle_idx]
    edge_rows.sort(key=lambda row: (row["chosen_surplus"], row["margin_vs_alt"], row["customer_id"]))
    near_miss_rows = [
        row
        for row in out_rows
        if -near_miss_eps <= float(row["all_bundle_surpluses"][bundle_idx]) < 0.0
    ]
    near_miss_rows.sort(
        key=lambda row: (
            -float(row["all_bundle_surpluses"][bundle_idx]),
            row["chosen_bundle"] == 0,
            row["customer_id"],
        )
    )
    return {
        "edge": edge_rows[:limit],
        "near_miss": near_miss_rows[:limit],
    }


def summarize_instance(instance_idx: int, in_rows: List[Dict], out_rows: List[Dict]) -> Dict:
    def calc(rows):
        revenue = sum(row["chosen_profit"] for row in rows) / len(rows)
        buy_rate = sum(1 for row in rows if row["chosen_bundle"] != 0) / len(rows)
        outside_rate = 1.0 - buy_rate
        return revenue, buy_rate, outside_rate

    rev_in, buy_in, outside_in = calc(in_rows)
    rev_out, buy_out, outside_out = calc(out_rows)
    return {
        "instance": f"inst{instance_idx:03d}",
        "revenue_in": rev_in,
        "revenue_out": rev_out,
        "drop_pct": 100.0 * (rev_in - rev_out) / rev_in,
        "buy_rate_in": buy_in,
        "buy_rate_out": buy_out,
        "outside_rate_in": outside_in,
        "outside_rate_out": outside_out,
    }


def as_csv_rows(bundle_rows: List[Dict], in_examples: List[Dict], out_examples: List[Dict]) -> Dict[str, List[Dict]]:
    out = {
        "bundle_rows": [],
        "in_examples": [],
        "out_examples": [],
    }
    for row in bundle_rows:
        cleaned = row.copy()
        for key, value in list(cleaned.items()):
            if isinstance(value, float):
                cleaned[key] = round(value, 6)
        out["bundle_rows"].append(cleaned)
    for row in in_examples:
        out["in_examples"].append(
            {
                "customer_id": row["customer_id"],
                "valuations": row["valuations"] if isinstance(row["valuations"], str) else json.dumps(row["valuations"]),
                "chosen_bundle": row["chosen_bundle"],
                "chosen_surplus": row["chosen_surplus"] if isinstance(row["chosen_surplus"], str) else round(row["chosen_surplus"], 6),
                "chosen_profit": row["chosen_profit"] if isinstance(row["chosen_profit"], str) else round(row["chosen_profit"], 6),
                "alt_bundle": row["alt_bundle"],
                "alt_surplus": row["alt_surplus"] if isinstance(row["alt_surplus"], str) else round(row["alt_surplus"], 6),
                "margin_vs_alt": row["margin_vs_alt"] if isinstance(row["margin_vs_alt"], str) else round(row["margin_vs_alt"], 6),
            }
        )
    for row in out_examples:
        out["out_examples"].append(
            {
                "customer_id": row["customer_id"],
                "valuations": row["valuations"] if isinstance(row["valuations"], str) else json.dumps(row["valuations"]),
                "bundle_surplus": row["bundle_surplus"] if isinstance(row["bundle_surplus"], str) else round(float(row["bundle_surplus"]), 6),
                "chosen_bundle": row["chosen_bundle"],
                "chosen_surplus": row["chosen_surplus"] if isinstance(row["chosen_surplus"], str) else round(row["chosen_surplus"], 6),
                "chosen_profit": row["chosen_profit"] if isinstance(row["chosen_profit"], str) else round(row["chosen_profit"], 6),
                "alt_bundle": row["alt_bundle"],
                "alt_surplus": row["alt_surplus"] if isinstance(row["alt_surplus"], str) else round(row["alt_surplus"], 6),
            }
        )
    return out


def write_csv(path: Path, rows: List[Dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description="Analyze MB out-of-sample revenue drop with bundle and customer attribution.")
    parser.add_argument("--experiment-root", type=Path, default=DEFAULT_EXPERIMENT_ROOT)
    parser.add_argument("--instances", type=int, nargs="+", default=[1, 5])
    parser.add_argument("--out-k", type=int, default=5000)
    parser.add_argument("--near-miss-eps", type=float, default=0.10)
    parser.add_argument("--top-bundles", type=int, default=3)
    parser.add_argument("--example-limit", type=int, default=5)
    args = parser.parse_args()

    experiment_root = args.experiment_root
    output_dir = experiment_root / "results" / "mb_oos_attribution"
    output_dir.mkdir(parents=True, exist_ok=True)

    report_lines = [
        "# MB Out-of-Sample Revenue Attribution",
        "",
        f"- Experiment root: `{experiment_root}`",
        f"- Instances analyzed: {', '.join(f'inst{x:03d}' for x in args.instances)}",
        f"- Out-of-sample K: {args.out_k}",
        f"- Near-miss window: surplus in `[-{args.near_miss_eps:.2f}, 0)`",
        "",
        "Method:",
        "1. Reuse the cached MB price table for each instance.",
        "2. Recompute in-sample and out-of-sample customer choices with the same replay rule as the v2 baseline: highest surplus wins, equal-surplus ties go to higher firm profit.",
        "3. Attribute revenue drop bundle-by-bundle via `profit_per_sale x (out_share - in_share)`.",
        "4. Surface boundary in-sample buyers and out-of-sample near misses for the bundles with the largest negative revenue contribution.",
        "",
    ]

    aggregate_bundle_rows = []
    aggregate_in_examples = []
    aggregate_out_examples = []

    for instance_idx in args.instances:
        instance_path = experiment_root / "instances" / "n5" / f"cpbsd_instance_{instance_idx:03d}_N5_K50_normal_rho0.0_full_hvhm.msgpack"
        result_path = experiment_root / "results" / f"baseline_mb_n5_inst{instance_idx:03d}.json"
        if not instance_path.exists() or not result_path.exists():
            raise FileNotFoundError(f"Missing instance or result for inst{instance_idx:03d}")

        v_in, c_n, setup = load_instance(instance_path)
        if int(setup["k_samples"]) != 50 or int(setup["n_products"]) != 5:
            raise ValueError("This attribution script currently expects the N=5, K=50 MB smoke instances.")
        v_out = sample_out_of_sample_valuations(setup, args.out_k)
        assortments = build_assortments(v_in.shape[1])

        result = json.loads(result_path.read_text(encoding="utf-8"))
        if not result.get("bundle_prices_full"):
            raise ValueError(f"Missing full bundle price table in {result_path}")
        prices = np.array([float(result["bundle_prices_full"][str(i)]) for i in range(assortments.shape[0])], dtype=float)
        profits = prices - assortments @ c_n

        forced_in_choices = np.asarray(result["chosen_bundle_idx_by_customer"], dtype=int)
        in_rows = evaluate_customer_choices(v_in, prices, profits, assortments, forced_choices=forced_in_choices)
        out_rows = evaluate_customer_choices(v_out, prices, profits, assortments)

        instance_summary = summarize_instance(instance_idx, in_rows, out_rows)
        bundle_rows = compute_bundle_attribution(
            instance_idx=instance_idx,
            assortments=assortments,
            prices=prices,
            profits=profits,
            in_rows=in_rows,
            out_rows=out_rows,
            near_miss_eps=args.near_miss_eps,
        )
        negative_rows = [row for row in bundle_rows if row["revenue_delta_per_customer"] < 0.0]
        top_loss_rows = negative_rows[: args.top_bundles]
        top_gain_rows = sorted(bundle_rows, key=lambda row: row["revenue_delta_per_customer"], reverse=True)[: args.top_bundles]

        report_lines.extend(
            [
                f"## inst{instance_idx:03d}",
                "",
                markdown_table(
                    [
                        "revenue_in",
                        "revenue_out",
                        "drop_pct",
                        "buy_rate_in",
                        "buy_rate_out",
                        "outside_rate_in",
                        "outside_rate_out",
                    ],
                    [
                        {
                            "revenue_in": format_float(instance_summary["revenue_in"]),
                            "revenue_out": format_float(instance_summary["revenue_out"]),
                            "drop_pct": format_float(instance_summary["drop_pct"], 2) + "%",
                            "buy_rate_in": format_float(instance_summary["buy_rate_in"]),
                            "buy_rate_out": format_float(instance_summary["buy_rate_out"]),
                            "outside_rate_in": format_float(instance_summary["outside_rate_in"]),
                            "outside_rate_out": format_float(instance_summary["outside_rate_out"]),
                        }
                    ],
                ),
                "",
                "Top negative bundle revenue contributions:",
                markdown_table(
                    [
                        "bundle",
                        "bundle_bits",
                        "size",
                        "price",
                        "profit_per_sale",
                        "train_share",
                        "out_share",
                        "revenue_delta_per_customer",
                        "train_min_surplus",
                        "out_near_miss_count",
                        "out_near_miss_choose_outside",
                        "out_near_miss_choose_other_bundle",
                        "out_top_substitute",
                    ],
                    [
                        {
                            "bundle": row["bundle"],
                            "bundle_bits": row["bundle_bits"],
                            "size": row["size"],
                            "price": format_float(row["price"]),
                            "profit_per_sale": format_float(row["profit_per_sale"]),
                            "train_share": format_float(row["train_share"]),
                            "out_share": format_float(row["out_share"]),
                            "revenue_delta_per_customer": format_float(row["revenue_delta_per_customer"]),
                            "train_min_surplus": format_float(row["train_min_surplus"]),
                            "out_near_miss_count": row["out_near_miss_count"],
                            "out_near_miss_choose_outside": row["out_near_miss_choose_outside"],
                            "out_near_miss_choose_other_bundle": row["out_near_miss_choose_other_bundle"],
                            "out_top_substitute": row["out_top_substitute"],
                        }
                        for row in top_loss_rows
                    ],
                ),
                "",
                "Top positive offsets:",
                markdown_table(
                    [
                        "bundle",
                        "bundle_bits",
                        "size",
                        "price",
                        "profit_per_sale",
                        "train_share",
                        "out_share",
                        "revenue_delta_per_customer",
                    ],
                    [
                        {
                            "bundle": row["bundle"],
                            "bundle_bits": row["bundle_bits"],
                            "size": row["size"],
                            "price": format_float(row["price"]),
                            "profit_per_sale": format_float(row["profit_per_sale"]),
                            "train_share": format_float(row["train_share"]),
                            "out_share": format_float(row["out_share"]),
                            "revenue_delta_per_customer": format_float(row["revenue_delta_per_customer"]),
                        }
                        for row in top_gain_rows
                    ],
                ),
                "",
            ]
        )

        instance_in_examples = []
        instance_out_examples = []
        for row in top_loss_rows:
            bundle_idx = row["bundle"]
            examples = pick_customer_examples(
                bundle_idx=bundle_idx,
                in_rows=in_rows,
                out_rows=out_rows,
                near_miss_eps=args.near_miss_eps,
                limit=args.example_limit,
            )

            edge_rows = []
            for example in examples["edge"]:
                edge_row = {
                    "customer_id": example["customer_id"],
                    "valuations": json.dumps(example["valuations"]),
                    "chosen_bundle": f"{example['chosen_bundle']}",
                    "chosen_surplus": format_float(example["chosen_surplus"]),
                    "chosen_profit": format_float(example["chosen_profit"]),
                    "alt_bundle": f"{example['alt_bundle']}",
                    "alt_surplus": format_float(example["alt_surplus"]),
                    "margin_vs_alt": format_float(example["margin_vs_alt"]),
                }
                edge_rows.append(edge_row)
                instance_in_examples.append(
                    {
                        "instance": f"inst{instance_idx:03d}",
                        "focus_bundle": bundle_idx,
                        **edge_row,
                    }
                )

            near_miss_rows = []
            for example in examples["near_miss"]:
                bundle_surplus = float(example["all_bundle_surpluses"][bundle_idx])
                near_miss_row = {
                    "customer_id": example["customer_id"],
                    "valuations": json.dumps(example["valuations"]),
                    "bundle_surplus": format_float(bundle_surplus),
                    "chosen_bundle": f"{example['chosen_bundle']}",
                    "chosen_surplus": format_float(example["chosen_surplus"]),
                    "chosen_profit": format_float(example["chosen_profit"]),
                    "alt_bundle": f"{example['alt_bundle']}",
                    "alt_surplus": format_float(example["alt_surplus"]),
                }
                near_miss_rows.append(near_miss_row)
                instance_out_examples.append(
                    {
                        "instance": f"inst{instance_idx:03d}",
                        "focus_bundle": bundle_idx,
                        **near_miss_row,
                    }
                )

            report_lines.extend(
                [
                    f"### Bundle {bundle_idx} ({bundle_bits(bundle_idx, assortments.shape[1])})",
                    "",
                    f"- Price = `{format_float(row['price'])}`, profit per sale = `{format_float(row['profit_per_sale'])}`.",
                    f"- Share moved from `{format_float(row['train_share'])}` in-sample to `{format_float(row['out_share'])}` out-of-sample, so this bundle alone contributes `{format_float(row['revenue_delta_per_customer'])}` revenue per customer to the drop.",
                    f"- Within the near-miss window, `{row['out_near_miss_count']}` out-of-sample customers fall just below zero surplus for this bundle; `{row['out_near_miss_choose_other_bundle']}` switch to another bundle and `{row['out_near_miss_choose_outside']}` go outside.",
                    "",
                    "Boundary in-sample buyers:",
                    markdown_table(
                        [
                            "customer_id",
                            "chosen_bundle",
                            "chosen_surplus",
                            "chosen_profit",
                            "alt_bundle",
                            "alt_surplus",
                            "margin_vs_alt",
                            "valuations",
                        ],
                        edge_rows,
                    ),
                    "",
                    "Out-of-sample near misses:",
                    markdown_table(
                        [
                            "customer_id",
                            "bundle_surplus",
                            "chosen_bundle",
                            "chosen_surplus",
                            "chosen_profit",
                            "alt_bundle",
                            "alt_surplus",
                            "valuations",
                        ],
                        near_miss_rows,
                    ),
                    "",
                ]
            )

        aggregate_bundle_rows.extend(bundle_rows)
        aggregate_in_examples.extend(instance_in_examples)
        aggregate_out_examples.extend(instance_out_examples)

        csv_payload = as_csv_rows(bundle_rows, instance_in_examples, instance_out_examples)
        write_csv(output_dir / f"inst{instance_idx:03d}_bundle_attribution.csv", csv_payload["bundle_rows"])
        write_csv(output_dir / f"inst{instance_idx:03d}_edge_customers.csv", csv_payload["in_examples"])
        write_csv(output_dir / f"inst{instance_idx:03d}_near_miss_customers.csv", csv_payload["out_examples"])

    report_path = output_dir / "MB_OOS_Attribution_Report.md"
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    write_csv(output_dir / "aggregate_bundle_attribution.csv", as_csv_rows(aggregate_bundle_rows, [], [])["bundle_rows"])
    write_csv(output_dir / "aggregate_edge_customers.csv", aggregate_in_examples)
    write_csv(output_dir / "aggregate_near_miss_customers.csv", aggregate_out_examples)

    print(
        json.dumps(
            {
                "report_path": str(report_path),
                "output_dir": str(output_dir),
                "instances": [f"inst{idx:03d}" for idx in args.instances],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
