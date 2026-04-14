import csv
import json
import time
from pathlib import Path

import gurobipy as gp
import msgpack
import msgpack_numpy as mnp
import numpy as np

from generate_data_CPBSD import generate_batch, valuation_means, sample_valuations
from solve_cpbsd_milp import load_instance_from_msgpack, solve as solve_milp
from solve_cpbsd_a import load_instance as load_instance_a
from solve_mb_bsp_on_cpbsd import MB_FORMULATION_VERSION, solve_mb, solve_bsp, eval_mb_out_of_sample, eval_bsp_out_of_sample


EXPERIMENT_SCOPE = "main_n5_grid"


def status_text(code):
    m = {
        2: "OPTIMAL",
        9: "TIME_LIMIT",
        3: "INFEASIBLE",
        4: "INF_OR_UNBD",
        5: "UNBOUNDED",
        -1: "LICENSE_LIMIT",
    }
    return m.get(code, f"STATUS_{code}")


def read_setup(msgpack_path: Path):
    with open(msgpack_path, "rb") as f:
        obj = msgpack.load(f, object_hook=mnp.decode)
    return obj.get("setup", {})


def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)


def evaluate_revenue(v_kn: np.ndarray, c_n: np.ndarray, p: np.ndarray, d: np.ndarray) -> float:
    K, N = v_kn.shape
    total = 0.0
    for k in range(K):
        best_surplus = 0.0
        best_idx = None
        best_s = 0
        for s in range(1, N + 1):
            util = v_kn[k] - p + d[s]
            idx = np.argpartition(util, -s)[-s:]
            surplus = float(util[idx].sum())
            if surplus > best_surplus:
                best_surplus = surplus
                best_idx = idx
                best_s = s
        if best_surplus <= 0 or best_idx is None:
            continue
        profit = float((p[best_idx] - c_n[best_idx]).sum() - best_s * d[best_s])
        total += profit
    return total / K


def out_of_sample_revenue(setup: dict, c_n: np.ndarray, p: np.ndarray, d: np.ndarray, out_k: int = 5000) -> float:
    rng = np.random.default_rng(int(setup["seed"]) + 99991)
    means = valuation_means(int(setup["n_products"]), setup["heterogeneity"])
    v_out = sample_valuations(
        k=out_k,
        means=means,
        family=setup["dist_family"],
        rho=float(setup["rho"]),
        rng=rng,
    )
    return evaluate_revenue(v_out, c_n, p, d)


def append_row(rows, setup, method, instance_id, n, k, tl, res, out_json, revenue_in, revenue_out, revenue_in_eval=None, error=False):
    if error:
        sc = -1
        sr = None
        wt = None
        nodes = None
        mg = None
        bb = None
        solc = None
        bm = None
    else:
        sc = int(res.get("solver_status", -99)) if isinstance(res, dict) else -99
        sr = res.get("runtime", None) if isinstance(res, dict) else None
        wt = res.get("wall_time", None) if isinstance(res, dict) else None
        nodes = res.get("node_count", None) if isinstance(res, dict) else None
        mg = res.get("mip_gap", None) if isinstance(res, dict) else None
        bb = res.get("best_bound", None) if isinstance(res, dict) else None
        solc = res.get("sol_count", None) if isinstance(res, dict) else None
        bm = (res.get("meta", {}) or {}).get("big_M", res.get("big_M", None)) if isinstance(res, dict) else None

    rows.append({
        "instance_id": instance_id,
        "seed": setup.get("seed", ""),
        "n": n,
        "k": k,
        "method": method,
        "experiment_scope": EXPERIMENT_SCOPE,
        "dist_family": setup.get("dist_family", ""),
        "rho": setup.get("rho", ""),
        "heterogeneity": setup.get("heterogeneity", ""),
        "cost_scenario": setup.get("cost_scenario", ""),
        "time": wt,
        "solver_runtime": sr,
        "time_limit": tl,
        "revenue": revenue_in,
        "revenue_in_sample": revenue_in,
        "revenue_in_eval": revenue_in_eval,
        "revenue_out_sample": revenue_out,
        "nodes": nodes,
        "status_code": sc,
        "status_text": status_text(sc),
        "mip_gap": mg,
        "best_bound": bb,
        "sol_count": solc,
        "big_m": bm,
        "result_path": str(out_json),
    })


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


def _normalize_keys(obj):
    if isinstance(obj, dict):
        new = {}
        for k, v in obj.items():
            try:
                import numpy as np
                if isinstance(k, (np.integer, np.floating)):
                    k = k.item()
            except Exception:
                pass
            if not isinstance(k, (str, int, float, bool)) and k is not None:
                k = str(k)
            new[k] = _normalize_keys(v)
        return new
    if isinstance(obj, list):
        return [_normalize_keys(x) for x in obj]
    if isinstance(obj, tuple):
        return tuple(_normalize_keys(x) for x in obj)
    return obj


def _mb_prices(result: dict):
    return (result or {}).get("bundle_prices_full") or (result or {}).get("bundle_prices") or {}


def _needs_mb_resolve(result: dict) -> bool:
    result = result or {}
    return not _mb_prices(result) or result.get("mb_formulation_version") != MB_FORMULATION_VERSION


def main():
    root = Path("/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/cpbsd_main_n5")
    inst_dir = root / "instances" / "n5"
    res_dir = root / "results"
    ensure_dir(inst_dir)
    ensure_dir(res_dir)

    rows = []
    time_limit = 300.0

    dist_families = ["exponential", "logit", "lognormal", "normal", "uniform"]
    rhos = [-0.5, 0.0, 0.5]
    heteros = ["none", "partial", "full"]
    costs = ["zero", "hvhm", "hvlm"]

    seed0 = 20260306
    setup_idx = 0

    # Generate instances for full grid (N=5)
    for dist in dist_families:
        for rho in rhos:
            for hetero in heteros:
                for cost in costs:
                    setup_seed = seed0 + setup_idx * 1000
                    generate_batch(
                        out_dir=str(inst_dir),
                        n_products=5,
                        k_samples=50,
                        dist_family=dist,
                        rho=rho,
                        heterogeneity=hetero,
                        cost_scenario=cost,
                        n_instances=5,
                        seed=setup_seed,
                    )
                    setup_idx += 1

    # Solve for each instance
    for mp in sorted(inst_dir.glob("*.msgpack")):
        setup = read_setup(mp)
        instance_id = mp.stem
        v_kn, c_n = load_instance_from_msgpack(mp)

        # CPBSD-MILP
        out_json = res_dir / f"{instance_id}__cpbsd_milp.json"
        if not out_json.exists():
            try:
                res = solve_milp(v_kn=v_kn, c_n=c_n, mip_gap=1e-2, time_limit=time_limit, output_flag=0)
                sol = (res.get("solution", {}) or {})
                p_vec = np.array(sol.get("p", []), dtype=float)
                d_vec = np.array(sol.get("d", []), dtype=float)
                revenue_in_obj = (res.get("solution", {}) or {}).get("objective", None)
                revenue_in_eval = evaluate_revenue(v_kn, c_n, p_vec, d_vec) if len(p_vec) else None
                revenue_out = out_of_sample_revenue(setup, c_n, p_vec, d_vec) if len(p_vec) else None
                out_json.write_text(json.dumps(res, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
                append_row(rows, setup, "CPBSD-MILP", instance_id, 5, 50, time_limit, res, out_json, revenue_in_obj, revenue_out, revenue_in_eval=revenue_in_eval, error=False)
            except gp.GurobiError as e:
                res = {"error": str(e)}
                out_json.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
                append_row(rows, setup, "CPBSD-MILP", instance_id, 5, 50, time_limit, res, out_json, None, None, error=True)
        else:
            res = json.loads(out_json.read_text())
            sol = (res.get("solution", {}) or {})
            p_vec = np.array(sol.get("p", []), dtype=float)
            d_vec = np.array(sol.get("d", []), dtype=float)
            revenue_in_obj = (res.get("solution", {}) or {}).get("objective", None)
            revenue_in_eval = evaluate_revenue(v_kn, c_n, p_vec, d_vec) if len(p_vec) else None
            revenue_out = out_of_sample_revenue(setup, c_n, p_vec, d_vec) if len(p_vec) else None
            append_row(rows, setup, "CPBSD-MILP", instance_id, 5, 50, time_limit, res, out_json, revenue_in_obj, revenue_out, revenue_in_eval=revenue_in_eval, error=False)

        # BSP
        out_json = res_dir / f"{instance_id}__bsp.json"
        if not out_json.exists():
            try:
                res_bsp = solve_bsp(v_kn, c_n, time_limit=time_limit)
                res_bsp = _normalize_keys(res_bsp)
                out_json.write_text(json.dumps(res_bsp, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
                revenue_in = res_bsp.get("objective")
                revenue_out = eval_bsp_out_of_sample(v_kn, c_n, res_bsp.get("size_prices") or {}) if res_bsp.get("size_prices") else None
                rows.append({
                    "instance_id": instance_id,
                    "seed": setup.get("seed", ""),
                    "n": 5,
                    "k": 50,
                    "method": "BSP",
                    "experiment_scope": EXPERIMENT_SCOPE,
                    "dist_family": setup.get("dist_family", ""),
                    "rho": setup.get("rho", ""),
                    "heterogeneity": setup.get("heterogeneity", ""),
                    "cost_scenario": setup.get("cost_scenario", ""),
                    "time": None,
                    "solver_runtime": res_bsp.get("runtime"),
                    "time_limit": time_limit,
                    "revenue": revenue_in,
                    "revenue_in_sample": revenue_in,
                    "revenue_out_sample": revenue_out,
                    "status_code": 2 if res_bsp.get("feasible") else 3,
                    "status_text": status_text(2 if res_bsp.get("feasible") else 3),
                    "mip_gap": res_bsp.get("mip_gap"),
                    "best_bound": None,
                    "sol_count": None,
                    "big_m": None,
                    "result_path": str(out_json),
                })
            except gp.GurobiError as e:
                res_bsp = {"error": str(e)}
                out_json.write_text(json.dumps(res_bsp, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            res_bsp = json.loads(out_json.read_text())
            revenue_in = res_bsp.get("objective")
            revenue_out = eval_bsp_out_of_sample(v_kn, c_n, res_bsp.get("size_prices") or {}) if res_bsp.get("size_prices") else None
            rows.append({
                "instance_id": instance_id,
                "seed": setup.get("seed", ""),
                "n": 5,
                "k": 50,
                "method": "BSP",
                "experiment_scope": EXPERIMENT_SCOPE,
                "dist_family": setup.get("dist_family", ""),
                "rho": setup.get("rho", ""),
                "heterogeneity": setup.get("heterogeneity", ""),
                "cost_scenario": setup.get("cost_scenario", ""),
                "time": None,
                "solver_runtime": res_bsp.get("runtime"),
                "time_limit": time_limit,
                "revenue": revenue_in,
                "revenue_in_sample": revenue_in,
                "revenue_out_sample": revenue_out,
                "status_code": 2 if res_bsp.get("feasible") else 3,
                "status_text": status_text(2 if res_bsp.get("feasible") else 3),
                "mip_gap": res_bsp.get("mip_gap"),
                "best_bound": None,
                "sol_count": None,
                "big_m": None,
                "result_path": str(out_json),
            })

        # MB
        out_json = res_dir / f"{instance_id}__mb.json"
        cached_mb = None
        if out_json.exists():
            try:
                cached_mb = json.loads(out_json.read_text())
            except Exception:
                cached_mb = None
        if cached_mb is None or _needs_mb_resolve(cached_mb):
            try:
                res_mb = solve_mb(v_kn, c_n, time_limit=time_limit)
                res_mb = _normalize_keys(res_mb)
                out_json.write_text(json.dumps(res_mb, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
                revenue_in = res_mb.get("revenue_in_sample", res_mb.get("objective"))
                mb_prices = _mb_prices(res_mb)
                revenue_out = eval_mb_out_of_sample(v_kn, c_n, mb_prices, np.array(res_mb.get("assortments"))) if mb_prices else None
                rows.append({
                    "instance_id": instance_id,
                    "seed": setup.get("seed", ""),
                    "n": 5,
                    "k": 50,
                    "method": "MB",
                    "experiment_scope": EXPERIMENT_SCOPE,
                    "dist_family": setup.get("dist_family", ""),
                    "rho": setup.get("rho", ""),
                    "heterogeneity": setup.get("heterogeneity", ""),
                    "cost_scenario": setup.get("cost_scenario", ""),
                    "time": None,
                    "solver_runtime": res_mb.get("runtime"),
                    "time_limit": time_limit,
                    "revenue": revenue_in,
                    "revenue_in_sample": revenue_in,
                    "revenue_out_sample": revenue_out,
                    "status_code": 2 if res_mb.get("feasible") else 3,
                    "status_text": status_text(2 if res_mb.get("feasible") else 3),
                    "mip_gap": res_mb.get("mip_gap"),
                    "best_bound": None,
                    "sol_count": None,
                    "big_m": None,
                    "result_path": str(out_json),
                })
            except gp.GurobiError as e:
                res_mb = {"error": str(e)}
                out_json.write_text(json.dumps(res_mb, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            res_mb = cached_mb
            revenue_in = res_mb.get("revenue_in_sample", res_mb.get("objective"))
            mb_prices = _mb_prices(res_mb)
            revenue_out = eval_mb_out_of_sample(v_kn, c_n, mb_prices, np.array(res_mb.get("assortments"))) if mb_prices else None
            rows.append({
                "instance_id": instance_id,
                "seed": setup.get("seed", ""),
                "n": 5,
                "k": 50,
                "method": "MB",
                "experiment_scope": EXPERIMENT_SCOPE,
                "dist_family": setup.get("dist_family", ""),
                "rho": setup.get("rho", ""),
                "heterogeneity": setup.get("heterogeneity", ""),
                "cost_scenario": setup.get("cost_scenario", ""),
                "time": None,
                "solver_runtime": res_mb.get("runtime"),
                "time_limit": time_limit,
                "revenue": revenue_in,
                "revenue_in_sample": revenue_in,
                "revenue_out_sample": revenue_out,
                "status_code": 2 if res_mb.get("feasible") else 3,
                "status_text": status_text(2 if res_mb.get("feasible") else 3),
                "mip_gap": res_mb.get("mip_gap"),
                "best_bound": None,
                "sol_count": None,
                "big_m": None,
                "result_path": str(out_json),
            })

    # compute ratios to BSP
    by_inst = {}
    for r in rows:
        by_inst.setdefault(r["instance_id"], {})[r["method"]] = r

    for inst, m in by_inst.items():
        bsp_rev = m.get("BSP", {}).get("revenue_in_sample", None)
        base_rev = m.get("CPBSD-MILP", {}).get("revenue_in_sample", None)
        for r in m.values():
            if isinstance(bsp_rev, (int, float)) and bsp_rev != 0 and isinstance(r.get("revenue_in_sample"), (int, float)):
                r["ratio_to_bsp"] = r["revenue_in_sample"] / bsp_rev
            else:
                r["ratio_to_bsp"] = None
            if isinstance(base_rev, (int, float)) and base_rev != 0 and isinstance(r.get("revenue_in_sample"), (int, float)):
                r["ratio_to_cpbsd"] = r["revenue_in_sample"] / base_rev
            else:
                r["ratio_to_cpbsd"] = None

    # write logs
    json_path = root / "unified_log.json"
    csv_path = root / "unified_log.csv"
    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    fieldnames = sorted({k for r in rows for k in r.keys()})
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"written: {json_path}")
    print(f"written: {csv_path}")


if __name__ == "__main__":
    main()
