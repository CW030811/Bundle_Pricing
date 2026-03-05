import argparse
import json
import os
import time
from pathlib import Path
from typing import Tuple

# Prefer explicit academic license file when present
if not os.environ.get("GRB_LICENSE_FILE") and Path.home().joinpath('.gurobi', 'gurobi.lic').exists():
    os.environ["GRB_LICENSE_FILE"] = str(Path.home().joinpath('.gurobi', 'gurobi.lic'))

import gurobipy as gp
import msgpack
import msgpack_numpy as mnp
import numpy as np

from generate_data_MB import solve_bundle_MILP
from generate_data_BSP import solve_bundle_size_pricing_MILP


def load_instance(path: Path) -> Tuple[np.ndarray, np.ndarray]:
    with open(path, "rb") as f:
        obj = msgpack.load(f, object_hook=mnp.decode)
    v = np.asarray(obj["valuation_samples_V"], dtype=float)
    c = np.asarray(obj["production_cost_c"], dtype=float)
    return v, c


def build_assortments(n: int) -> np.ndarray:
    return np.array([list(map(int, format(num, '0' + str(n) + 'b'))) for num in range(2**n)], dtype=int)


def eval_mb_out_of_sample(v_kn: np.ndarray, c_n: np.ndarray, bundle_prices: dict, assortments: np.ndarray) -> float:
    K, N = v_kn.shape
    B = assortments.shape[0]
    bundle_cost = assortments @ c_n
    total = 0.0
    for k in range(K):
        best_surplus = 0.0
        best_i = None
        for i in range(B):
            price = bundle_prices.get(i, None)
            if price is None:
                continue
            val = float(v_kn[k] @ assortments[i])
            surplus = val - price
            if surplus > best_surplus:
                best_surplus = surplus
                best_i = i
        if best_surplus <= 0 or best_i is None:
            continue
        price = bundle_prices[str(best_i)] if isinstance(bundle_prices, dict) and str(best_i) in bundle_prices else bundle_prices.get(best_i)
        profit = price - bundle_cost[best_i]
        total += profit
    return total / K


def eval_bsp_out_of_sample(v_kn: np.ndarray, c_n: np.ndarray, size_prices: dict) -> float:
    K, N = v_kn.shape
    total = 0.0
    for k in range(K):
        best_surplus = 0.0
        best_s = 0
        best_cost = 0.0
        order = np.argsort(-v_kn[k])
        prefix_val = 0.0
        prefix_cost = 0.0
        for s in range(1, N + 1):
            idx = order[s-1]
            prefix_val += v_kn[k, idx]
            prefix_cost += c_n[idx]
            price = size_prices.get(s) if isinstance(size_prices, dict) else None
            if price is None:
                continue
            surplus = prefix_val - price
            if surplus > best_surplus:
                best_surplus = surplus
                best_s = s
                best_cost = prefix_cost
        if best_surplus <= 0 or best_s == 0:
            continue
        price = size_prices.get(best_s)
        profit = price - best_cost
        total += profit
    return total / K


def solve_mb(v_kn: np.ndarray, c_n: np.ndarray, time_limit: float = 300.0):
    K, N = v_kn.shape
    assortments = build_assortments(N)
    B = assortments.shape[0]
    # bundle cost broadcast to (K,B)
    bundle_cost = (assortments @ c_n).reshape(1, -1)
    costs = np.repeat(bundle_cost, K, axis=0)
    Rs = v_kn @ assortments.T
    Rbar = np.max(Rs)
    Ns = np.ones((K, 1)) / K

    opt_bundles, opt_prices, opt_rev, runtime, gap, feasible = solve_bundle_MILP(
        N, K, B, assortments, costs, Rs, Rbar, Ns
    )

    return {
        "feasible": feasible,
        "objective": opt_rev,
        "runtime": runtime,
        "mip_gap": gap,
        "bundle_prices": opt_prices,
        "assortments": assortments,
    }


def solve_bsp(v_kn: np.ndarray, c_n: np.ndarray, time_limit: float = 300.0):
    K, N = v_kn.shape
    assortments = build_assortments(N)
    B = assortments.shape[0]
    bundle_cost = (assortments @ c_n).reshape(1, -1)
    costs = np.repeat(bundle_cost, K, axis=0)
    Rs = v_kn @ assortments.T
    Rbar = np.max(Rs)
    Ns = np.ones((K, 1)) / K

    sol_sizes, size_prices, opt_rev, runtime, gap, feasible, obj_hist = solve_bundle_size_pricing_MILP(
        N, K, B, assortments, costs, Rs, Rbar, Ns
    )

    return {
        "feasible": feasible,
        "objective": opt_rev,
        "runtime": runtime,
        "mip_gap": gap,
        "size_prices": size_prices,
    }


def _json_default(obj):
    try:
        import numpy as np
        if isinstance(obj, (np.integer, np.floating)):
            return obj.item()
        if isinstance(obj, np.ndarray):
            return obj.tolist()
    except Exception:
        pass
    return obj


def _json_clean_dict(d):
    return {str(k): v for k, v in d.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--instance", required=True)
    ap.add_argument("--method", choices=["mb", "bsp"], required=True)
    ap.add_argument("--time-limit", type=float, default=300.0)
    ap.add_argument("--save-json", type=str, default="")
    args = ap.parse_args()

    v_kn, c_n = load_instance(Path(args.instance))
    if args.method == "mb":
        res = solve_mb(v_kn, c_n, time_limit=args.time_limit)
        if isinstance(res.get("bundle_prices"), dict):
            res["bundle_prices"] = _json_clean_dict(res["bundle_prices"])
    else:
        res = solve_bsp(v_kn, c_n, time_limit=args.time_limit)
        if isinstance(res.get("size_prices"), dict):
            res["size_prices"] = _json_clean_dict(res["size_prices"])

    text = json.dumps(res, ensure_ascii=False, indent=2, default=_json_default)
    print(text)
    if args.save_json:
        Path(args.save_json).write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
