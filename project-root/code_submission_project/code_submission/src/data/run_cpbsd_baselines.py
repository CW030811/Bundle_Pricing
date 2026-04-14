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
from solve_cpbsd_a import load_instance as load_instance_a, solve_cpbsd_a
from solve_mb_bsp_on_cpbsd import solve_mb, solve_bsp, eval_mb_out_of_sample, eval_bsp_out_of_sample


# NOTE: current run is a smoke/minimal subset, not full-paper grid.
EXPERIMENT_SCOPE = "smoke_subset"


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
    """Consumer chooses bundle that maximizes surplus; firm revenue = profit from chosen bundle."""
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
        sc = int(res.get("solver_status", -99))
        sr = res.get("runtime", None)
        wt = res.get("wall_time", None)
        nodes = res.get("node_count", None)
        mg = res.get("mip_gap", None)
        bb = res.get("best_bound", None)
        solc = res.get("sol_count", None)
        bm = (res.get("meta", {}) or {}).get("big_M", res.get("big_M", None))

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
    """Recursively normalize dict keys to plain int/str for JSON."""
    if isinstance(obj, dict):
        new = {}
        for k, v in obj.items():
            # normalize numpy/scalar keys
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


def main():
    root = Path("/Users/sensen/.openclaw/workspace/domains/revenue-management/experiments/cpbsd_baselines")
    inst_dir = root / "instances"
    res_dir = root / "results"
    ensure_dir(inst_dir)
    ensure_dir(res_dir)

    rows = []
    time_limit_by_n = {5: 300.0, 10: 600.0, 30: 1200.0}

    # CPBSD-MILP oracle (n=5)
    milp_instances = generate_batch(
        out_dir=str(inst_dir / "n5"),
        n_products=5,
        k_samples=50,
        dist_family="normal",
        rho=0.0,
        heterogeneity="full",
        cost_scenario="hvhm",
        n_instances=5,
        seed=20260304,
    )

    for i, pth in enumerate(milp_instances, start=1):
        mp = Path(pth)
        setup = read_setup(mp)
        v_kn, c_n = load_instance_from_msgpack(mp)
        tl = time_limit_by_n[5]

        try:
            res = solve_milp(v_kn=v_kn, c_n=c_n, mip_gap=1e-2, time_limit=tl, output_flag=0)
            sol = (res.get("solution", {}) or {})
            p_vec = np.array(sol.get("p", []), dtype=float)
            d_vec = np.array(sol.get("d", []), dtype=float)
            revenue_in_obj = (res.get("solution", {}) or {}).get("objective", None)
            revenue_in_eval = evaluate_revenue(v_kn, c_n, p_vec, d_vec) if len(p_vec) else None
            revenue_out = out_of_sample_revenue(setup, c_n, p_vec, d_vec) if len(p_vec) else None
            err = False
        except gp.GurobiError as e:
            res = {"error": str(e)}
            revenue_in_obj = None
            revenue_in_eval = None
            revenue_out = None
            err = True

        out_json = res_dir / f"oracle_n5_inst{i:03d}.json"
        out_json.write_text(json.dumps(res, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
        append_row(rows, setup, "CPBSD-MILP", f"n5_inst{i:03d}", 5, setup.get("k_samples", 50), tl, res, out_json, revenue_in_obj, revenue_out, revenue_in_eval=revenue_in_eval, error=err)

    # CPBSD-A baseline (n=10,30)
    for n, k, seed0 in [(10, 100, 20261310)]:
        tl = time_limit_by_n[n]
        a_instances = generate_batch(
            out_dir=str(inst_dir / f"n{n}"),
            n_products=n,
            k_samples=k,
            dist_family="normal",
            rho=0.0,
            heterogeneity="full",
            cost_scenario="hvhm",
            n_instances=5,
            seed=seed0,
        )

        for i, pth in enumerate(a_instances, start=1):
            mp = Path(pth)
            setup = read_setup(mp)
            v_kn, c_n = load_instance_a(mp)
            try:
                res = solve_cpbsd_a(v_kn=v_kn, c_n=c_n, mip_gap=1e-2, time_limit=tl, output_flag=0)
                p_vec = np.array(res.get("p", []), dtype=float)
                d_vec = np.array(res.get("d", []), dtype=float)
                revenue_in_obj = res.get("objective", None)
                revenue_in_eval = evaluate_revenue(v_kn, c_n, p_vec, d_vec) if len(p_vec) else None
                revenue_out = out_of_sample_revenue(setup, c_n, p_vec, d_vec) if len(p_vec) else None
                err = False
            except gp.GurobiError as e:
                res = {"error": str(e)}
                revenue_in_obj = None
                revenue_in_eval = None
                revenue_out = None
                err = True

            out_json = res_dir / f"baseline_cpbsd_a_n{n}_inst{i:03d}.json"
            out_json.write_text(json.dumps(res, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
            append_row(rows, setup, "CPBSD-A", f"n{n}_inst{i:03d}", n, setup.get("k_samples", k), tl, res, out_json, revenue_in_obj, revenue_out, revenue_in_eval=revenue_in_eval, error=err)


    # 3) BSP baseline (n=5/10/30) + MB (n=5 only)
    for n, k in [(5, 50), (10, 100)]:
        tl = time_limit_by_n[n]
        inst_dir_n = inst_dir / f"n{n}"
        for i, mp in enumerate(sorted(inst_dir_n.glob('*.msgpack')), start=1):
            setup = read_setup(mp)
            v_kn, c_n = load_instance_a(mp)
            # BSP
            try:
                res_bsp = solve_bsp(v_kn, c_n, time_limit=tl)
                revenue_in = res_bsp.get('objective', None)
                revenue_in_eval = revenue_in
                revenue_out = eval_bsp_out_of_sample(v_kn, c_n, res_bsp.get('size_prices', {})) if res_bsp.get('size_prices') else None
                status_code = 2 if res_bsp.get('feasible') else 3
            except gp.GurobiError as e:
                res_bsp = {"error": str(e)}
                revenue_in_obj = None
                revenue_in_eval = None
                revenue_out = None
                status_code = -1
            out_json = res_dir / f"baseline_bsp_n{n}_inst{i:03d}.json"
            out_json.write_text(json.dumps(res_bsp, ensure_ascii=False, indent=2, default=_json_default), encoding='utf-8')
            rows.append({
                "instance_id": f"n{n}_inst{i:03d}",
                "seed": setup.get('seed',''),
                "n": n,
                "k": setup.get('k_samples', k),
                "method": "BSP",
                "experiment_scope": EXPERIMENT_SCOPE,
                "dist_family": setup.get('dist_family',''),
                "rho": setup.get('rho',''),
                "heterogeneity": setup.get('heterogeneity',''),
                "cost_scenario": setup.get('cost_scenario',''),
                "time": res_bsp.get('runtime', None),
                "solver_runtime": res_bsp.get('runtime', None),
                "time_limit": tl,
                "revenue": revenue_in,
                "revenue_in_sample": revenue_in,
                "revenue_in_eval": revenue_in_eval,
                "revenue_out_sample": revenue_out,
                "nodes": None,
                "status_code": status_code,
                "status_text": status_text(status_code),
                "mip_gap": res_bsp.get('mip_gap', None),
                "best_bound": None,
                "sol_count": None,
                "big_m": None,
                "result_path": str(out_json),
            })

            # MB (only for n=5)
            if n == 5:
                try:
                    res_mb = solve_mb(v_kn, c_n, time_limit=tl)
                    mb_prices = res_mb.get("bundle_prices_full") or res_mb.get("bundle_prices") or {}
                    revenue_in = res_mb.get("revenue_in_sample", res_mb.get('objective', None))
                    revenue_in_eval = revenue_in
                    revenue_out = eval_mb_out_of_sample(v_kn, c_n, mb_prices, res_mb.get('assortments')) if mb_prices else None
                    status_code = 2 if res_mb.get('feasible') else 3
                except gp.GurobiError as e:
                    res_mb = {"error": str(e)}
                    revenue_in = None
                    revenue_in_eval = None
                    revenue_out = None
                    status_code = -1
                out_json = res_dir / f"baseline_mb_n{n}_inst{i:03d}.json"
                res_mb = _normalize_keys(res_mb)
                out_json.write_text(json.dumps(res_mb, ensure_ascii=False, indent=2, default=_json_default), encoding='utf-8')
                rows.append({
                    "instance_id": f"n{n}_inst{i:03d}",
                    "seed": setup.get('seed',''),
                    "n": n,
                    "k": setup.get('k_samples', k),
                    "method": "MB",
                    "experiment_scope": EXPERIMENT_SCOPE,
                    "dist_family": setup.get('dist_family',''),
                    "rho": setup.get('rho',''),
                    "heterogeneity": setup.get('heterogeneity',''),
                    "cost_scenario": setup.get('cost_scenario',''),
                    "time": res_mb.get('runtime', None),
                    "solver_runtime": res_mb.get('runtime', None),
                    "time_limit": tl,
                    "revenue": revenue_in,
                    "revenue_in_sample": revenue_in,
                    "revenue_in_eval": revenue_in_eval,
                    "revenue_out_sample": revenue_out,
                    "nodes": None,
                    "status_code": status_code,
                    "status_text": status_text(status_code),
                    "mip_gap": res_mb.get('mip_gap', None),
                    "best_bound": None,
                    "sol_count": None,
                    "big_m": None,
                    "result_path": str(out_json),
                })

    # compute revenue ratios (relative to BSP and baseline)
    # baseline: n=5 -> CPBSD-MILP; n>=10 -> CPBSD-A
    by_inst = {}
    for r in rows:
        by_inst.setdefault(r['instance_id'], {})[r['method']] = r
    for inst, m in by_inst.items():
        bsp_rev = m.get('BSP', {}).get('revenue_in_sample', None)
        # baseline selection
        n = m.get('BSP', {}).get('n', None) or next(iter(m.values())).get('n')
        baseline_method = 'CPBSD-MILP' if str(n) == '5' else 'CPBSD-A'
        base_rev = m.get(baseline_method, {}).get('revenue_in_sample', None)
        for r in m.values():
            r['ratio_to_bsp'] = (r['revenue_in_sample'] / bsp_rev) if (bsp_rev not in (None, 0, '')) else None
            r['ratio_to_baseline'] = (r['revenue_in_sample'] / base_rev) if (base_rev not in (None, 0, '')) else None
            r['baseline_method'] = baseline_method

    json_path = root / "unified_log.json"
    csv_path = root / "unified_log.csv"
    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")

    fieldnames = [
        "instance_id", "seed", "n", "k", "method", "experiment_scope",
        "dist_family", "rho", "heterogeneity", "cost_scenario",
        "time", "solver_runtime", "time_limit",
        "revenue", "revenue_in_sample", "revenue_out_sample",
        "nodes", "status_code", "status_text", "mip_gap", "best_bound", "sol_count", "big_m", "result_path",
    ]

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print("Done. Unified logs:")
    print(f"- {json_path}")
    print(f"- {csv_path}")
    print("NOTE: experiment_scope=smoke_subset (not full 5x3x3x3 grid).")


if __name__ == "__main__":
    main()
