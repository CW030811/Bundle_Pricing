import argparse
import json
import os
import time
from pathlib import Path
from typing import Dict, Tuple

# Prefer explicit academic license file when present
if not os.environ.get("GRB_LICENSE_FILE") and Path.home().joinpath('.gurobi', 'gurobi.lic').exists():
    os.environ["GRB_LICENSE_FILE"] = str(Path.home().joinpath('.gurobi', 'gurobi.lic'))

import gurobipy as gp
import msgpack
import msgpack_numpy as mnp
import numpy as np
from gurobipy import GRB


# ------------------------------------------------------------
# CPBSD-MILP (paper Section 5) - strict variable/constraint map
# ------------------------------------------------------------
# Decision variables (same symbols as paper):
# p_n, d_s, q_kns, x_kns, y_ks, w_ks, w_k, alpha_ks, beta_kns
#
# Objective:
# max (1/K) * sum_{k,n,s} (q_kns - c_n x_kns)
#
# Constraints numbered exactly as in paper:
# (9)  w_k >= s*alpha_ks + sum_n beta_kns
# (10) alpha_ks + beta_kns >= v_kn - p_n + d_s
# (11) alpha free, beta >= 0
# (12) sum_s y_ks <= 1
# (13) sum_n x_kns = s*y_ks
# (14) sum_s x_kns <= 1
# (15) x_kns <= y_ks
# (16) q_kns >= p_n - d_s - M(1-x_kns)
# (17) q_kns <= p_n - d_s
# (18) w_ks = sum_n (v_kn x_kns - q_kns)
# (19) w_k = sum_s w_ks
# (20) w_k >= sum_{n,s} (v_kn x_jns - q_jns), for j != k
# (21) s d_s >= s1 d_s1 + s2 d_s2, s1+s2=s
# (22) p_n, d_s, q_kns, w_ks, w_k >= 0, d_1 = 0
# (23) x_kns, y_ks in {0,1}


def load_instance_from_msgpack(path: Path) -> Tuple[np.ndarray, np.ndarray]:
    """
    Returns:
      v_kn: (K, N)
      c_n:  (N,)
    Supports the generator output in this repo (valuation_samples_V, production_cost_c).
    """
    with open(path, "rb") as f:
        obj = msgpack.load(f, object_hook=mnp.decode)

    if "valuation_samples_V" not in obj or "production_cost_c" not in obj:
        raise ValueError("msgpack missing required keys: valuation_samples_V / production_cost_c")

    v_kn = np.asarray(obj["valuation_samples_V"], dtype=float)
    c_n = np.asarray(obj["production_cost_c"], dtype=float)

    if v_kn.ndim != 2:
        raise ValueError("valuation_samples_V must be 2D (K,N)")
    if c_n.ndim != 1:
        raise ValueError("production_cost_c must be 1D (N,)")
    if v_kn.shape[1] != c_n.shape[0]:
        raise ValueError(f"dimension mismatch: V has N={v_kn.shape[1]}, c has N={c_n.shape[0]}")

    return v_kn, c_n


def build_cpbsd_milp(
    v_kn: np.ndarray,
    c_n: np.ndarray,
    big_m: float = None,
    p_ub: float = None,
    d_ub: float = None,
) -> Tuple[gp.Model, Dict]:
    K, N = v_kn.shape
    S = list(range(1, N + 1))
    K_idx = list(range(K))
    N_idx = list(range(N))

    # Safe bounded formulation for big-M linearization
    vmax = float(np.max(v_kn))
    if p_ub is None:
        p_ub = vmax
    if d_ub is None:
        d_ub = p_ub
    if big_m is None:
        # Safe M for q >= p-d-M(1-x): with x=0 and q>=0, need M >= max(p-d)
        big_m = max(0.0, p_ub)

    model = gp.Model("CPBSD_MILP")

    # Variables (bounded)
    p = model.addVars(N_idx, lb=0.0, ub=p_ub, vtype=GRB.CONTINUOUS, name="p")
    d = model.addVars(S, lb=0.0, ub=d_ub, vtype=GRB.CONTINUOUS, name="d")

    x = model.addVars(K_idx, N_idx, S, vtype=GRB.BINARY, name="x")
    y = model.addVars(K_idx, S, vtype=GRB.BINARY, name="y")

    q = model.addVars(K_idx, N_idx, S, lb=0.0, vtype=GRB.CONTINUOUS, name="q")
    w_s = model.addVars(K_idx, S, lb=0.0, vtype=GRB.CONTINUOUS, name="w_s")
    w = model.addVars(K_idx, lb=0.0, vtype=GRB.CONTINUOUS, name="w")

    alpha = model.addVars(K_idx, S, lb=-GRB.INFINITY, vtype=GRB.CONTINUOUS, name="alpha")  # free
    beta = model.addVars(K_idx, N_idx, S, lb=0.0, vtype=GRB.CONTINUOUS, name="beta")

    # Objective: (CPBSD-MILP)
    model.setObjective(
        (1.0 / K)
        * gp.quicksum(q[k, n, s] - c_n[n] * x[k, n, s] for k in K_idx for n in N_idx for s in S),
        GRB.MAXIMIZE,
    )

    # (9)
    model.addConstrs(
        (w[k] >= s * alpha[k, s] + gp.quicksum(beta[k, n, s] for n in N_idx) for k in K_idx for s in S),
        name="c9_dual_upper",
    )

    # (10)
    model.addConstrs(
        (
            alpha[k, s] + beta[k, n, s] >= v_kn[k, n] - p[n] + d[s]
            for k in K_idx
            for n in N_idx
            for s in S
        ),
        name="c10_dual_feas",
    )

    # (11) already encoded by bounds (alpha free, beta>=0)

    # (12)
    model.addConstrs(
        (gp.quicksum(y[k, s] for s in S) <= 1 for k in K_idx),
        name="c12_one_bundle_or_none",
    )

    # (13)
    model.addConstrs(
        (gp.quicksum(x[k, n, s] for n in N_idx) == s * y[k, s] for k in K_idx for s in S),
        name="c13_size_count",
    )

    # (14)
    model.addConstrs(
        (gp.quicksum(x[k, n, s] for s in S) <= 1 for k in K_idx for n in N_idx),
        name="c14_at_most_one_unit",
    )

    # (15)
    model.addConstrs(
        (x[k, n, s] <= y[k, s] for k in K_idx for n in N_idx for s in S),
        name="c15_link_x_y",
    )

    # (16)
    model.addConstrs(
        (
            q[k, n, s] >= p[n] - d[s] - big_m * (1 - x[k, n, s])
            for k in K_idx
            for n in N_idx
            for s in S
        ),
        name="c16_bigM_lower",
    )

    # (17)
    model.addConstrs(
        (q[k, n, s] <= p[n] - d[s] for k in K_idx for n in N_idx for s in S),
        name="c17_q_upper",
    )

    # (18)
    model.addConstrs(
        (
            w_s[k, s] == gp.quicksum(v_kn[k, n] * x[k, n, s] - q[k, n, s] for n in N_idx)
            for k in K_idx
            for s in S
        ),
        name="c18_wks_def",
    )

    # (19)
    model.addConstrs(
        (w[k] == gp.quicksum(w_s[k, s] for s in S) for k in K_idx),
        name="c19_wk_sum",
    )

    # (20)
    model.addConstrs(
        (
            w[k]
            >= gp.quicksum(v_kn[k, n] * x[j, n, s] - q[j, n, s] for n in N_idx for s in S)
            for k in K_idx
            for j in K_idx
            if j != k
        ),
        name="c20_envy_free_like",
    )

    # (21) subadditivity of size discount
    model.addConstrs(
        (
            s * d[s] >= s1 * d[s1] + s2 * d[s2]
            for s in S
            for s1 in range(1, s)
            for s2 in [s - s1]
        ),
        name="c21_discount_subadditivity",
    )

    # (22): d1 = 0
    model.addConstr(d[1] == 0.0, name="c22_d1_zero")

    meta = {
        "K": K,
        "N": N,
        "S": S,
        "big_M": big_m,
        "p_ub": p_ub,
        "d_ub": d_ub,
        "var_counts": {
            "p": len(N_idx),
            "d": len(S),
            "x": len(K_idx) * len(N_idx) * len(S),
            "y": len(K_idx) * len(S),
            "q": len(K_idx) * len(N_idx) * len(S),
            "w_s": len(K_idx) * len(S),
            "w": len(K_idx),
            "alpha": len(K_idx) * len(S),
            "beta": len(K_idx) * len(N_idx) * len(S),
        },
    }

    return model, meta


def extract_solution(model: gp.Model, v_kn: np.ndarray, c_n: np.ndarray) -> Dict:
    K, N = v_kn.shape
    S = list(range(1, N + 1))

    p = np.array([model.getVarByName(f"p[{n}]").X for n in range(N)])
    d = np.array([0.0] + [model.getVarByName(f"d[{s}]").X for s in S])

    x = np.zeros((K, N, N + 1), dtype=int)
    y = np.zeros((K, N + 1), dtype=int)
    q = np.zeros((K, N, N + 1), dtype=float)
    w = np.zeros(K, dtype=float)
    w_s = np.zeros((K, N + 1), dtype=float)
    alpha = np.zeros((K, N + 1), dtype=float)
    beta = np.zeros((K, N, N + 1), dtype=float)

    for k in range(K):
        for s in S:
            y[k, s] = int(round(model.getVarByName(f"y[{k},{s}]").X))
            for n in range(N):
                x[k, n, s] = int(round(model.getVarByName(f"x[{k},{n},{s}]").X))
                q[k, n, s] = model.getVarByName(f"q[{k},{n},{s}]").X
                beta[k, n, s] = model.getVarByName(f"beta[{k},{n},{s}]").X
            w_s[k, s] = model.getVarByName(f"w_s[{k},{s}]").X
            alpha[k, s] = model.getVarByName(f"alpha[{k},{s}]").X
        w[k] = model.getVarByName(f"w[{k}]").X

    objective = model.ObjVal if model.SolCount > 0 else None

    return {
        "objective": objective,
        "p": p,
        "d": d,
        "x": x,
        "y": y,
        "q": q,
        "w": w,
        "w_s": w_s,
        "alpha": alpha,
        "beta": beta,
        "status": int(model.Status),
        "runtime": model.Runtime,
        "mip_gap": getattr(model, "MIPGap", None),
    }


def solve(
    v_kn: np.ndarray,
    c_n: np.ndarray,
    mip_gap: float,
    time_limit: float,
    output_flag: int,
    big_m: float = None,
    p_ub: float = None,
    d_ub: float = None,
):
    model, meta = build_cpbsd_milp(v_kn=v_kn, c_n=c_n, big_m=big_m, p_ub=p_ub, d_ub=d_ub)
    model.setParam("MIPGap", mip_gap)
    model.setParam("TimeLimit", time_limit)
    model.setParam("OutputFlag", output_flag)

    t0 = time.time()
    model.optimize()
    t1 = time.time()

    result = {
        "meta": meta,
        "solver_status": int(model.Status),
        "wall_time": t1 - t0,
        "runtime": model.Runtime,
        "sol_count": model.SolCount,
        "node_count": float(model.NodeCount),
        "mip_gap": float(model.MIPGap) if model.SolCount > 0 else None,
        "best_bound": float(model.ObjBound) if model.SolCount > 0 else None,
    }

    if model.SolCount > 0:
        result["solution"] = extract_solution(model, v_kn=v_kn, c_n=c_n)

    return result


def parse_args():
    ap = argparse.ArgumentParser(description="Solve CPBSD-MILP with strict paper variable/constraint mapping")
    ap.add_argument("--instance", type=str, default="", help="Path to msgpack instance with valuation_samples_V & production_cost_c")
    ap.add_argument("--K", type=int, default=8, help="Used only when --instance is empty")
    ap.add_argument("--N", type=int, default=5, help="Used only when --instance is empty")
    ap.add_argument("--seed", type=int, default=20260304)
    ap.add_argument("--mip-gap", type=float, default=1e-2)
    ap.add_argument("--time-limit", type=float, default=300.0)
    ap.add_argument("--output-flag", type=int, default=1)
    ap.add_argument("--big-m", type=float, default=-1.0)
    ap.add_argument("--p-ub", type=float, default=-1.0)
    ap.add_argument("--d-ub", type=float, default=-1.0)
    ap.add_argument("--build-only", action="store_true", help="Only build model and print size; do not optimize")
    ap.add_argument("--save-json", type=str, default="", help="Optional output json path")
    return ap.parse_args()


def main():
    args = parse_args()

    if args.instance:
        v_kn, c_n = load_instance_from_msgpack(Path(args.instance))
    else:
        rng = np.random.default_rng(args.seed)
        v_kn = np.maximum(rng.normal(loc=2.0, scale=0.8, size=(args.K, args.N)), 0.0)
        c_n = rng.uniform(0.1, 1.2, size=args.N)

    big_m = None if args.big_m <= 0 else args.big_m
    p_ub = None if args.p_ub <= 0 else args.p_ub
    d_ub = None if args.d_ub <= 0 else args.d_ub

    if args.build_only:
        model, meta = build_cpbsd_milp(v_kn=v_kn, c_n=c_n, big_m=big_m, p_ub=p_ub, d_ub=d_ub)
        model.update()
        out = {
            "build_only": True,
            "num_vars": model.NumVars,
            "num_constrs": model.NumConstrs,
            "meta": meta,
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    result = solve(
        v_kn=v_kn,
        c_n=c_n,
        mip_gap=args.mip_gap,
        time_limit=args.time_limit,
        output_flag=args.output_flag,
        big_m=big_m,
        p_ub=p_ub,
        d_ub=d_ub,
    )

    text = json.dumps(result, ensure_ascii=False, indent=2, default=lambda x: x.tolist() if isinstance(x, np.ndarray) else x)
    print(text)

    if args.save_json:
        out_path = Path(args.save_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
