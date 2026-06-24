from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Dict, List

import msgpack
import msgpack_numpy as mnp
import numpy as np

ROOT = Path("/Users/sensen/.openclaw/workspace/domains/revenue-management")
SRC = ROOT / "project-root" / "code_submission_project" / "code_submission" / "src" / "data"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from generate_data_CPBSD import sample_valuations, valuation_means  # noqa: E402
from solve_mb_bsp_on_cpbsd_v2 import normalize_numeric_keys  # noqa: E402


INSTANCE_PATH = ROOT / "experiments" / "cpbsd_fcp_pruned_mb_compare_n10k50_strict300" / "instances" / "cpbsd_instance_001_N10_K50_normal_rho0.0_full_hvhm.msgpack"
BSP_PATH = ROOT / "experiments" / "cpbsd_fcp_pruned_mb_compare_n10k50_strict300" / "results" / "cpbsd_instance_001_N10_K50_normal_rho0.0_full_hvhm__bsp.json"
FCP_PATH = ROOT / "experiments" / "cpbsd_fcp_pruned_mb_compare_n10k50_strict300" / "results" / "cpbsd_instance_001_N10_K50_normal_rho0.0_full_hvhm__fcp_pruned_mb.json"
OUT_DIR = ROOT / "research-tracker" / "weekly-reports" / "2026-W16-fcp-gcn-vs-cpbsd-main-n5" / "instance001_bsp_fcp_compare"


def load_instance(path: Path):
    with path.open("rb") as f:
        obj = msgpack.load(f, object_hook=mnp.decode, strict_map_key=False)
    setup = obj["setup"]
    v_kn = np.asarray(obj["valuation_samples_V"], dtype=float)
    c_n = np.asarray(obj["production_cost_c"], dtype=float)
    return setup, v_kn, c_n


def load_json(path: Path) -> Dict:
    return json.loads(path.read_text(encoding="utf-8"))


def generate_oos(setup: Dict, k_out: int = 5000) -> np.ndarray:
    rng = np.random.default_rng(int(setup["seed"]) + 99991)
    means = valuation_means(int(setup["n_products"]), setup["heterogeneity"])
    return sample_valuations(
        k=k_out,
        means=means,
        family=setup["dist_family"],
        rho=float(setup["rho"]),
        rng=rng,
    )


def fmt_bundle(bundle: np.ndarray) -> str:
    return "".join(str(int(x)) for x in bundle.tolist())


def choose_bsp_customer(v_row: np.ndarray, c_n: np.ndarray, size_prices: Dict[int, float]) -> Dict:
    n_products = int(v_row.shape[0])
    order = np.argsort(-v_row)
    prefix_val = 0.0
    prefix_cost = 0.0
    best_surplus = 0.0
    best_size = 0
    best_bundle = np.zeros(n_products, dtype=int)
    best_items: List[int] = []

    for size in range(1, n_products + 1):
        idx = int(order[size - 1])
        prefix_val += float(v_row[idx])
        prefix_cost += float(c_n[idx])
        price = size_prices.get(size)
        if price is None:
            continue
        surplus = prefix_val - float(price)
        if surplus > best_surplus:
            best_surplus = surplus
            best_size = size
            best_items = [int(i) for i in order[:size].tolist()]
            best_bundle = np.zeros(n_products, dtype=int)
            best_bundle[order[:size]] = 1

    if best_size == 0 or best_surplus <= 0.0:
        return {
            "purchased": 0,
            "size": 0,
            "price": 0.0,
            "value": 0.0,
            "cost": 0.0,
            "surplus": 0.0,
            "profit": 0.0,
            "bundle": np.zeros(n_products, dtype=int),
            "bundle_str": fmt_bundle(np.zeros(n_products, dtype=int)),
            "items": "",
        }

    price = float(size_prices[best_size])
    cost = float(best_bundle @ c_n)
    value = float(best_bundle @ v_row)
    return {
        "purchased": 1,
        "size": best_size,
        "price": price,
        "value": value,
        "cost": cost,
        "surplus": value - price,
        "profit": price - cost,
        "bundle": best_bundle,
        "bundle_str": fmt_bundle(best_bundle),
        "items": ",".join(map(str, best_items)),
    }


def choose_fcp_customer(v_row: np.ndarray, c_n: np.ndarray, bundle_prices: Dict[int, float], assortments: np.ndarray) -> Dict:
    eps = 1e-9
    bundle_cost = assortments @ c_n
    best_surplus = 0.0
    best_profit = 0.0
    best_bundle_idx = None

    for bundle_idx in range(assortments.shape[0]):
        price = bundle_prices.get(bundle_idx)
        if price is None:
            continue
        bundle = assortments[bundle_idx]
        value = float(v_row @ bundle)
        surplus = value - float(price)
        if abs(surplus) <= eps:
            surplus = 0.0
        profit = float(price) - float(bundle_cost[bundle_idx])
        if surplus > best_surplus + eps:
            best_surplus = surplus
            best_profit = profit
            best_bundle_idx = bundle_idx
        elif abs(surplus - best_surplus) <= eps and profit > best_profit + eps:
            best_profit = profit
            best_bundle_idx = bundle_idx

    if best_bundle_idx is None:
        zero = np.zeros(assortments.shape[1], dtype=int)
        return {
            "purchased": 0,
            "bundle_idx": -1,
            "size": 0,
            "price": 0.0,
            "value": 0.0,
            "cost": 0.0,
            "surplus": 0.0,
            "profit": 0.0,
            "bundle": zero,
            "bundle_str": fmt_bundle(zero),
            "items": "",
        }

    bundle = assortments[best_bundle_idx]
    price = float(bundle_prices[best_bundle_idx])
    cost = float(bundle @ c_n)
    value = float(v_row @ bundle)
    return {
        "purchased": 1,
        "bundle_idx": int(best_bundle_idx),
        "size": int(bundle.sum()),
        "price": price,
        "value": value,
        "cost": cost,
        "surplus": value - price,
        "profit": price - cost,
        "bundle": bundle.copy(),
        "bundle_str": fmt_bundle(bundle),
        "items": ",".join(map(str, np.where(bundle == 1)[0].tolist())),
    }


def analyze_sample(sample_name: str, v_eval: np.ndarray, c_n: np.ndarray, size_prices: Dict[int, float], bundle_prices: Dict[int, float], assortments: np.ndarray) -> List[Dict]:
    fcp_bundle_lookup = {tuple(row.tolist()): idx for idx, row in enumerate(assortments)}
    fcp_size_support = sorted({int(row.sum()) for row in assortments})
    rows = []
    for customer_id in range(v_eval.shape[0]):
        v_row = v_eval[customer_id]
        bsp = choose_bsp_customer(v_row, c_n, size_prices)
        fcp = choose_fcp_customer(v_row, c_n, bundle_prices, assortments)
        bsp_bundle_tuple = tuple(int(x) for x in bsp["bundle"].tolist())
        bsp_in_fcp_menu = int(bsp_bundle_tuple in fcp_bundle_lookup) if bsp["purchased"] else 0
        rows.append(
            {
                "sample": sample_name,
                "customer_id": customer_id,
                "bsp_purchased": bsp["purchased"],
                "bsp_size": bsp["size"],
                "bsp_price": bsp["price"],
                "bsp_value": bsp["value"],
                "bsp_cost": bsp["cost"],
                "bsp_surplus": bsp["surplus"],
                "bsp_profit": bsp["profit"],
                "bsp_bundle": bsp["bundle_str"],
                "bsp_items": bsp["items"],
                "bsp_bundle_in_fcp_menu": bsp_in_fcp_menu,
                "fcp_purchased": fcp["purchased"],
                "fcp_bundle_idx": fcp.get("bundle_idx", -1),
                "fcp_size": fcp["size"],
                "fcp_price": fcp["price"],
                "fcp_value": fcp["value"],
                "fcp_cost": fcp["cost"],
                "fcp_surplus": fcp["surplus"],
                "fcp_profit": fcp["profit"],
                "fcp_bundle": fcp["bundle_str"],
                "fcp_items": fcp["items"],
                "same_purchase_decision": int(bsp["purchased"] == fcp["purchased"]),
                "same_bundle": int(bsp["bundle_str"] == fcp["bundle_str"]),
                "same_size": int(bsp["size"] == fcp["size"]),
                "bsp_purchase_fcp_no_purchase": int(bsp["purchased"] == 1 and fcp["purchased"] == 0),
                "profit_gap_bsp_minus_fcp": bsp["profit"] - fcp["profit"],
                "surplus_gap_bsp_minus_fcp": bsp["surplus"] - fcp["surplus"],
                "fcp_size_support": ",".join(map(str, fcp_size_support)),
            }
        )
    return rows


def summarize_rows(rows: List[Dict]) -> Dict:
    n = len(rows)
    return {
        "customer_count": n,
        "bsp_avg_profit": sum(r["bsp_profit"] for r in rows) / n,
        "fcp_avg_profit": sum(r["fcp_profit"] for r in rows) / n,
        "bsp_purchase_count": sum(r["bsp_purchased"] for r in rows),
        "fcp_purchase_count": sum(r["fcp_purchased"] for r in rows),
        "bsp_purchase_fcp_no_purchase": sum(r["bsp_purchase_fcp_no_purchase"] for r in rows),
        "bsp_exact_bundle_not_in_fcp_menu_count": sum(int(r["bsp_purchased"] == 1 and r["bsp_bundle_in_fcp_menu"] == 0) for r in rows),
        "same_bundle_count": sum(r["same_bundle"] for r in rows),
        "same_size_count": sum(r["same_size"] for r in rows),
        "fcp_profit_gt_bsp_count": sum(int(r["fcp_profit"] > r["bsp_profit"]) for r in rows),
        "bsp_profit_gt_fcp_count": sum(int(r["bsp_profit"] > r["fcp_profit"]) for r in rows),
    }


def write_csv(path: Path, rows: List[Dict]) -> None:
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    setup, v_kn, c_n = load_instance(INSTANCE_PATH)
    bsp_res = load_json(BSP_PATH)
    fcp_res = load_json(FCP_PATH)

    size_prices = normalize_numeric_keys(bsp_res["size_prices"])
    bundle_prices = normalize_numeric_keys(fcp_res["bundle_prices_full"])
    assortments = np.asarray(fcp_res["assortments"], dtype=int)
    v_out = generate_oos(setup, k_out=5000)

    in_rows = analyze_sample("in_sample", v_kn, c_n, size_prices, bundle_prices, assortments)
    oos_rows = analyze_sample("oos", v_out, c_n, size_prices, bundle_prices, assortments)

    write_csv(OUT_DIR / "customer_comparison_in_sample.csv", in_rows)
    write_csv(OUT_DIR / "customer_comparison_oos.csv", oos_rows)

    summary = {
        "instance_path": str(INSTANCE_PATH),
        "bsp_result_path": str(BSP_PATH),
        "fcp_result_path": str(FCP_PATH),
        "setup": setup,
        "bsp_size_support": sorted(int(k) for k in size_prices.keys()),
        "fcp_bundle_space_size": int(fcp_res["bundle_space_size"]),
        "fcp_price_count_full": len(bundle_prices),
        "fcp_size_support": sorted(int(x) for x in np.unique(assortments.sum(axis=1))),
        "in_sample": summarize_rows(in_rows),
        "oos": summarize_rows(oos_rows),
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    md = []
    md.append("# BSP vs FCP Detailed Choice Analysis")
    md.append("")
    md.append("## Instance")
    md.append("")
    md.append(f"- instance: `{INSTANCE_PATH.name}`")
    md.append(f"- setup: `{setup}`")
    md.append(f"- BSP offered sizes: `{sorted(int(k) for k in size_prices.keys())}`")
    md.append(f"- FCP priced bundles: `{len(bundle_prices)}` over restricted assortment size `{int(fcp_res['bundle_space_size'])}`")
    md.append(f"- FCP size support: `{sorted(int(x) for x in np.unique(assortments.sum(axis=1)))}`")
    md.append("")
    for sample_name in ("in_sample", "oos"):
        s = summary[sample_name]
        md.append(f"## {sample_name.replace('_', ' ').title()}")
        md.append("")
        md.append(f"- customer count: `{s['customer_count']}`")
        md.append(f"- BSP avg profit: `{s['bsp_avg_profit']:.6f}`")
        md.append(f"- FCP avg profit: `{s['fcp_avg_profit']:.6f}`")
        md.append(f"- BSP purchase count: `{s['bsp_purchase_count']}`")
        md.append(f"- FCP purchase count: `{s['fcp_purchase_count']}`")
        md.append(f"- BSP purchase but FCP no-purchase: `{s['bsp_purchase_fcp_no_purchase']}`")
        md.append(f"- BSP chosen exact bundle not in FCP menu: `{s['bsp_exact_bundle_not_in_fcp_menu_count']}`")
        md.append(f"- Same bundle count: `{s['same_bundle_count']}`")
        md.append(f"- Same size count: `{s['same_size_count']}`")
        md.append(f"- BSP profit > FCP profit count: `{s['bsp_profit_gt_fcp_count']}`")
        md.append(f"- FCP profit > BSP profit count: `{s['fcp_profit_gt_bsp_count']}`")
        md.append("")
    md.append("## Files")
    md.append("")
    md.append(f"- [customer_comparison_in_sample.csv]({OUT_DIR / 'customer_comparison_in_sample.csv'})")
    md.append(f"- [customer_comparison_oos.csv]({OUT_DIR / 'customer_comparison_oos.csv'})")
    md.append(f"- [summary.json]({OUT_DIR / 'summary.json'})")
    (OUT_DIR / "summary.md").write_text("\n".join(md) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
