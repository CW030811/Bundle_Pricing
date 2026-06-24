from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Tuple

import msgpack
import msgpack_numpy as mnp
import numpy as np

from generate_data_CPBSD import sample_valuations, valuation_means
from solve_mb_bsp_on_cpbsd_v2 import build_assortments, eval_mb_policy, json_default, normalize_numeric_keys


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def load_msgpack_with_setup(path: Path) -> Tuple[Dict, np.ndarray, np.ndarray]:
    with path.open("rb") as f:
        obj = msgpack.load(f, object_hook=mnp.decode, strict_map_key=False)
    return obj, np.asarray(obj["valuation_samples_V"], dtype=float), np.asarray(obj["production_cost_c"], dtype=float)


def load_json(path: Path) -> Dict:
    return json.loads(path.read_text(encoding="utf-8"))


def generate_v_out(setup: Dict, k_out: int) -> np.ndarray:
    rng = np.random.default_rng(int(setup["seed"]) + 99991)
    means = valuation_means(int(setup["n_products"]), setup["heterogeneity"])
    return sample_valuations(
        k=k_out,
        means=means,
        family=setup["dist_family"],
        rho=float(setup["rho"]),
        rng=rng,
    )


def build_anchor_prices(fcp_result: Dict, full_assortments: np.ndarray) -> Dict[int, float]:
    restricted_assortments = np.asarray(fcp_result["assortments"], dtype=int)
    restricted_prices = normalize_numeric_keys(fcp_result.get("bundle_prices_full") or {})
    full_lookup = {tuple(row.tolist()): idx for idx, row in enumerate(full_assortments)}
    anchor_prices: Dict[int, float] = {}
    for ridx, bundle in enumerate(restricted_assortments):
        price = restricted_prices.get(ridx)
        if price is None:
            continue
        full_idx = full_lookup[tuple(bundle.tolist())]
        anchor_prices[full_idx] = float(price)
    return anchor_prices


def compute_bsp_size_prices_from_probe(probe_json: Path) -> Dict[int, float]:
    payload = json.loads(probe_json.read_text(encoding="utf-8"))
    data = payload.get("payload", payload)
    return normalize_numeric_keys(data["bsp_all_prices"]["size_prices_all"])


def aggregate_anchor_stats_by_size(full_assortments: np.ndarray, anchor_prices: Dict[int, float]) -> Dict[int, Dict[str, float]]:
    by_size: Dict[int, List[float]] = {}
    for idx, price in anchor_prices.items():
        size = int(full_assortments[idx].sum())
        by_size.setdefault(size, []).append(float(price))
    out = {}
    for s, vals in by_size.items():
        vals_arr = np.asarray(vals, dtype=float)
        out[s] = {
            "count": int(len(vals)),
            "min": float(np.min(vals_arr)),
            "max": float(np.max(vals_arr)),
            "mean": float(np.mean(vals_arr)),
            "median": float(np.median(vals_arr)),
        }
    return out


def fill_completed_prices(
    full_assortments: np.ndarray,
    anchor_prices: Dict[int, float],
    size_fill: Dict[int, float],
) -> Dict[int, float]:
    completed = {}
    for idx in range(full_assortments.shape[0]):
        if idx in anchor_prices:
            completed[idx] = float(anchor_prices[idx])
        else:
            size = int(full_assortments[idx].sum())
            completed[idx] = float(size_fill[size])
    return completed


def check_anchor_preservation(completed_prices: Dict[int, float], anchor_prices: Dict[int, float], tol: float = 1e-8) -> bool:
    for idx, price in anchor_prices.items():
        if abs(float(completed_prices[idx]) - float(price)) > tol:
            return False
    return True


def check_global_subadditivity(full_assortments: np.ndarray, completed_prices: Dict[int, float], tol: float = 1e-8) -> Dict:
    bundle_count = full_assortments.shape[0]
    union_index = {tuple(row.tolist()): idx for idx, row in enumerate(full_assortments)}
    max_violation = 0.0
    violation_count = 0
    for i in range(bundle_count):
        for j in range(i, bundle_count):
            union_idx = union_index[tuple(np.maximum(full_assortments[i], full_assortments[j]).tolist())]
            lhs = float(completed_prices[union_idx])
            rhs = float(completed_prices[i]) + float(completed_prices[j])
            violation = lhs - rhs
            if violation > tol:
                violation_count += 1
                max_violation = max(max_violation, violation)
    return {"violation_count": int(violation_count), "max_violation": float(max_violation)}


def build_size_fill_variants(anchor_stats: Dict[int, Dict[str, float]], bsp_size_prices: Dict[int, float], n_products: int) -> Dict[str, Dict[int, float]]:
    variants: Dict[str, Dict[int, float]] = {}

    def fallback(size: int) -> float:
        return float(bsp_size_prices[size])

    for rule in ["min", "mean", "max", "median"]:
        fill = {}
        for s in range(n_products + 1):
            if s in anchor_stats:
                fill[s] = float(anchor_stats[s][rule])
            else:
                fill[s] = fallback(s)
        variants[f"same_size_anchor_{rule}"] = fill

    clipped = {}
    for s in range(n_products + 1):
        if s in anchor_stats:
            lo = float(anchor_stats[s]["min"])
            hi = float(anchor_stats[s]["max"])
            clipped[s] = float(np.clip(float(bsp_size_prices[s]), lo, hi))
        else:
            clipped[s] = fallback(s)
    variants["bsp_clipped_to_anchor_range"] = clipped

    lower = {}
    upper = {}
    for s in range(n_products + 1):
        if s in anchor_stats:
            lower[s] = float(anchor_stats[s]["min"])
            upper[s] = float(anchor_stats[s]["max"])
        else:
            lower[s] = fallback(s)
            upper[s] = fallback(s)
    variants["same_size_anchor_lower_bound"] = lower
    variants["same_size_anchor_upper_bound"] = upper

    return variants


def write_markdown(path: Path, payload: Dict) -> None:
    lines: List[str] = []
    lines.append("# Phase 3 Heuristic Completion Probe")
    lines.append("")
    lines.append(f"- Instance: `{payload['instance_id']}`")
    lines.append(f"- Setup: `{payload['setup_key']}`")
    lines.append(f"- Anchor bundle count: `{payload['anchor_bundle_count']}`")
    lines.append("")
    lines.append("## Baseline")
    lines.append("")
    lines.append(f"- Restricted FCP OOS revenue: `{payload['baseline']['restricted_oos_revenue']:.6f}`")
    lines.append("")
    lines.append("## Heuristic Variants")
    lines.append("")
    lines.append("| Variant | OOS Revenue | Delta vs Restricted | In-Sample Revenue | Anchor Preserved | Subadd Violations | Max Violation |")
    lines.append("| --- | ---: | ---: | ---: | --- | ---: | ---: |")
    for item in payload["variants"]:
        lines.append(
            f"| `{item['name']}` | {item['repaired_oos_revenue']:.6f} | {item['delta_oos_vs_restricted']:.6f} | {item['repaired_in_sample_revenue']:.6f} | `{item['anchor_preserved']}` | `{item['subadditivity']['violation_count']}` | `{item['subadditivity']['max_violation']:.6f}` |"
        )
    lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe coarse heuristic OOS completion variants for FCP-MB.")
    parser.add_argument(
        "--instance-path",
        type=Path,
        default=Path("/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/cpbsd_fcp_pruned_mb_compare_n10k50_strict300/instances/cpbsd_instance_001_N10_K50_normal_rho0.0_full_hvhm.msgpack"),
    )
    parser.add_argument(
        "--fcp-result-path",
        type=Path,
        default=Path("/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/cpbsd_fcp_pruned_mb_compare_n10k50_strict300/results/cpbsd_instance_001_N10_K50_normal_rho0.0_full_hvhm__fcp_pruned_mb.json"),
    )
    parser.add_argument(
        "--bsp-probe-json",
        type=Path,
        default=Path("/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/phase3_oos_bsp_completion_probe_n10_normal_rho0.0_full_hvhm_inst001/probe_summary.json"),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/phase3_oos_heuristic_completion_probe_n10_normal_rho0.0_full_hvhm_inst001"),
    )
    parser.add_argument("--k-out", type=int, default=5000)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ensure_dir(args.output_root)

    obj, v_kn, c_n = load_msgpack_with_setup(args.instance_path)
    setup = obj["setup"]
    fcp_result = load_json(args.fcp_result_path)
    full_assortments = build_assortments(int(setup["n_products"]))
    anchor_prices = build_anchor_prices(fcp_result, full_assortments)
    anchor_stats = aggregate_anchor_stats_by_size(full_assortments, anchor_prices)
    bsp_size_prices = compute_bsp_size_prices_from_probe(args.bsp_probe_json)
    v_out = generate_v_out(setup, args.k_out)

    restricted_assortments = np.asarray(fcp_result["assortments"], dtype=int)
    restricted_prices = normalize_numeric_keys(fcp_result["bundle_prices_full"])
    baseline_oos = float(eval_mb_policy(v_out, c_n, restricted_prices, restricted_assortments))

    variants = []
    for name, size_fill in build_size_fill_variants(anchor_stats, bsp_size_prices, int(setup["n_products"])).items():
        completed_prices = fill_completed_prices(full_assortments, anchor_prices, size_fill)
        repaired_in = float(eval_mb_policy(v_kn, c_n, completed_prices, full_assortments))
        repaired_oos = float(eval_mb_policy(v_out, c_n, completed_prices, full_assortments))
        variants.append(
            {
                "name": name,
                "size_fill": size_fill,
                "repaired_in_sample_revenue": repaired_in,
                "repaired_oos_revenue": repaired_oos,
                "delta_oos_vs_restricted": repaired_oos - baseline_oos,
                "anchor_preserved": check_anchor_preservation(completed_prices, anchor_prices),
                "subadditivity": check_global_subadditivity(full_assortments, completed_prices),
            }
        )

    variants.sort(key=lambda x: x["repaired_oos_revenue"], reverse=True)

    payload = {
        "instance_id": args.instance_path.stem,
        "setup_key": f"{setup['dist_family']}_rho{setup['rho']}_{setup['heterogeneity']}_{setup['cost_scenario']}",
        "anchor_bundle_count": len(anchor_prices),
        "baseline": {"restricted_oos_revenue": baseline_oos},
        "anchor_stats_by_size": anchor_stats,
        "bsp_size_prices": bsp_size_prices,
        "variants": variants,
    }

    json_path = args.output_root / "heuristic_probe_summary.json"
    md_path = args.output_root / "heuristic_probe_summary.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")
    write_markdown(md_path, payload)
    print(json.dumps({"json": str(json_path), "markdown": str(md_path), "payload": payload}, ensure_ascii=False, indent=2, default=json_default))


if __name__ == "__main__":
    main()
